"""
RAG2Prod — Context Engineering Module (Stage 4)

Transforms raw retrieved chunks into structured, cited LLM prompt payloads.
Handles parent-chunk deduplication, citation indexing, token-budget truncation,
and final prompt assembly.
"""
from typing import List, Dict, Optional

import tiktoken

from core.config import settings
from core.schemas import (
    RetrievalResult,
    RetrievalResultItem,
    CitationSource,
    SourceLocation,
    FormattedContext,
    PromptPayload,
)
from core.prompts import RAG_SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE
from core.logger import info, timer_step


# Use cl100k_base tokenizer (GPT-4 / DeepSeek compatible)
_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    """Count tokens using the cl100k_base encoding."""
    return len(_TOKENIZER.encode(text))


class CitationMapper:
    """
    Maps retrieved chunks to numbered citation sources.
    Deduplicates by parent_id so the same parent context appears only once.
    """

    def __init__(self, items: List[RetrievalResultItem]):
        self.items = items

    def build(self) -> List[CitationSource]:
        """
        Assign citation indexes and build provenance list.
        Deduplicates by parent_id — if two child chunks share a parent,
        only the highest-scoring child is kept as the citation representative.
        """
        seen_parents: Dict[str, int] = {}
        citations: List[CitationSource] = []
        citation_index = 1

        for item in self.items:
            if item.parent_id in seen_parents:
                continue

            seen_parents[item.parent_id] = citation_index
            meta = item.source_metadata or {}
            page_number = meta.get("page_number")
            file_type = meta.get("file_type", ".txt")

            # Set the full chunk_text as snippet for high-fidelity frontend highlighting
            snippet = item.chunk_text

            loc = None
            if any(k in meta for k in ("start_char", "raw_start_char", "start_line")):
                loc = SourceLocation(
                    start_char=meta.get("start_char"),
                    end_char=meta.get("end_char"),
                    raw_start_char=meta.get("raw_start_char"),
                    raw_end_char=meta.get("raw_end_char"),
                    start_line=meta.get("start_line"),
                    end_line=meta.get("end_line"),
                    bbox=meta.get("bbox"),
                    dom_selector=meta.get("dom_selector"),
                )

            citations.append(
                CitationSource(
                    index=citation_index,
                    document_id=item.document_id,
                    chunk_id=item.chunk_id,
                    page_number=int(page_number) if page_number is not None else None,
                    file_type=file_type,
                    similarity_score=item.similarity_score,
                    text_snippet=snippet,
                    parent_text=item.parent_text or item.chunk_text,
                    location=loc,
                )
            )
            citation_index += 1

        return citations



class ContextBuilder:
    """
    Builds the formatted context from retrieved chunks with citation indexes
    and token-budget truncation.
    """

    def __init__(self, max_context_tokens: Optional[int] = None):
        self.max_context_tokens = max_context_tokens or settings.MAX_CONTEXT_TOKENS

    def build(self, retrieval_result: RetrievalResult) -> FormattedContext:
        """
        Transforms a RetrievalResult into a FormattedContext:
        1. Deduplicate overlapping parent chunks (same parent_id → keep once).
        2. Assign [Source N] citation indexes.
        3. Build numbered evidence blocks from parent text.
        4. Truncate to max_context_tokens budget.
        """
        with timer_step("context", "Building formatted context with citations"):
            items = retrieval_result.items
            if not items:
                return FormattedContext(
                    evidence_blocks=[],
                    citations=[],
                    total_tokens=0,
                    truncated=False,
                )

            # Build citation map (deduplicated by parent)
            mapper = CitationMapper(items)
            citations = mapper.build()

            # Build evidence blocks using parent text for richer context
            evidence_blocks: List[str] = []
            total_tokens = 0
            truncated = False

            for citation in citations:
                # Find the corresponding item for this citation
                matching_item = self._find_item_by_chunk_id(items, citation.chunk_id)
                if not matching_item:
                    continue

                # Use parent text for broader context, fall back to chunk text
                source_text = matching_item.parent_text or matching_item.chunk_text

                # Build the evidence block
                page_info = f" (Page {citation.page_number})" if citation.page_number else ""
                block = f"[Source {citation.index}]{page_info}:\n{source_text}"

                block_tokens = _count_tokens(block)

                # Check token budget
                if total_tokens + block_tokens > self.max_context_tokens:
                    # Truncate this block to fit remaining budget
                    remaining_tokens = self.max_context_tokens - total_tokens
                    if remaining_tokens > 50:
                        # Truncate by encoding → slicing → decoding
                        tokens = _TOKENIZER.encode(block)
                        truncated_block = _TOKENIZER.decode(tokens[:remaining_tokens])
                        evidence_blocks.append(truncated_block + "\n[...truncated]")
                        total_tokens += remaining_tokens
                    truncated = True
                    break

                evidence_blocks.append(block)
                total_tokens += block_tokens

            info("context", f"Built {len(evidence_blocks)} evidence blocks, {total_tokens} tokens, truncated={truncated}")

            return FormattedContext(
                evidence_blocks=evidence_blocks,
                citations=citations,
                total_tokens=total_tokens,
                truncated=truncated,
            )

    @staticmethod
    def _find_item_by_chunk_id(
        items: List[RetrievalResultItem], chunk_id: str
    ) -> Optional[RetrievalResultItem]:
        """Find a retrieval item by its chunk_id."""
        for item in items:
            if item.chunk_id == chunk_id:
                return item
        return None


class PromptBuilder:
    """
    Assembles the final LLM prompt payload from a FormattedContext and user query.
    System prompts are loaded from external constants (per prompt_guidelines.md).
    """

    def __init__(self, system_prompt: Optional[str] = None):
        self.system_prompt = system_prompt or RAG_SYSTEM_PROMPT

    def build(self, context: FormattedContext, query: str) -> PromptPayload:
        """
        Build the final prompt payload for the LLM:
        1. Join evidence blocks into a single context string.
        2. Format the user message using the context template.
        3. Return system + user messages.
        """
        with timer_step("prompt", "Assembling LLM prompt payload"):
            evidence_text = "\n\n".join(context.evidence_blocks) if context.evidence_blocks else "(No relevant sources found)"

            user_message = RAG_CONTEXT_TEMPLATE.format(
                evidence_blocks=evidence_text,
                query=query,
            )

            context_tokens = context.total_tokens + _count_tokens(self.system_prompt) + _count_tokens(query)

            return PromptPayload(
                system_message=self.system_prompt,
                user_message=user_message,
                context_tokens=context_tokens,
            )
