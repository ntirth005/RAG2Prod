"""
Tests for the Context Engineering module (Stage 4).
Tests ContextBuilder, PromptBuilder, and CitationMapper.
"""
import pytest
from core.schemas import (
    RetrievalResult,
    RetrievalResultItem,
    FormattedContext,
    CitationSource,
    PromptPayload,
)
from core.context_builder import ContextBuilder, PromptBuilder, CitationMapper


# ── Fixtures ──

def _make_retrieval_items(count: int = 3, same_parent: bool = False) -> list[RetrievalResultItem]:
    """Create mock RetrievalResultItem instances for testing."""
    items = []
    for i in range(count):
        parent_id = "parent_shared" if same_parent else f"parent_{i}"
        items.append(
            RetrievalResultItem(
                chunk_id=f"chunk_{i}",
                parent_id=parent_id,
                document_id=f"doc_{i % 2}",
                chunk_text=f"This is the child chunk text number {i} with detailed content.",
                parent_text=f"This is the full parent text for chunk {i} providing broader context around the topic.",
                similarity_score=round(0.95 - (i * 0.05), 4),
                source_metadata={"page_number": i + 1, "section": f"Section {i}"},
            )
        )
    return items


def _make_retrieval_result(count: int = 3, same_parent: bool = False) -> RetrievalResult:
    items = _make_retrieval_items(count, same_parent)
    return RetrievalResult(
        query_text="What is the main topic?",
        total_retrieved=len(items),
        items=items,
    )


# ── CitationMapper Tests ──

def test_citation_mapper_assigns_indexes() -> None:
    """Citation indexes should start at 1 and increment."""
    items = _make_retrieval_items(3)
    mapper = CitationMapper(items)
    citations = mapper.build()

    assert len(citations) == 3
    assert citations[0].index == 1
    assert citations[1].index == 2
    assert citations[2].index == 3


def test_citation_mapper_deduplicates_by_parent() -> None:
    """Chunks sharing the same parent_id should produce only one citation."""
    items = _make_retrieval_items(3, same_parent=True)
    mapper = CitationMapper(items)
    citations = mapper.build()

    assert len(citations) == 1
    assert citations[0].index == 1
    assert citations[0].chunk_id == "chunk_0"


def test_citation_source_has_text_snippet() -> None:
    """Each citation should include a text_snippet for UI highlighting."""
    items = _make_retrieval_items(1)
    mapper = CitationMapper(items)
    citations = mapper.build()

    assert citations[0].text_snippet != ""
    assert "child chunk text" in citations[0].text_snippet


def test_citation_source_page_number() -> None:
    """Page number should be extracted from source_metadata."""
    items = _make_retrieval_items(1)
    mapper = CitationMapper(items)
    citations = mapper.build()

    assert citations[0].page_number == 1


# ── ContextBuilder Tests ──

def test_build_context_with_citations() -> None:
    """ContextBuilder should produce evidence blocks with [Source N] prefixes."""
    result = _make_retrieval_result(3)
    builder = ContextBuilder(max_context_tokens=8000)
    context = builder.build(result)

    assert isinstance(context, FormattedContext)
    assert len(context.evidence_blocks) == 3
    assert "[Source 1]" in context.evidence_blocks[0]
    assert "[Source 2]" in context.evidence_blocks[1]
    assert "[Source 3]" in context.evidence_blocks[2]
    assert context.total_tokens > 0
    assert context.truncated is False


def test_context_truncation() -> None:
    """ContextBuilder should truncate when evidence exceeds max_context_tokens."""
    result = _make_retrieval_result(5)
    # Very small token budget to force truncation
    builder = ContextBuilder(max_context_tokens=60)
    context = builder.build(result)

    assert context.truncated is True
    # Should have fewer evidence blocks than total items
    assert len(context.evidence_blocks) <= 5


def test_build_context_empty_result() -> None:
    """Empty retrieval result should produce empty context."""
    result = RetrievalResult(query_text="test", total_retrieved=0, items=[])
    builder = ContextBuilder()
    context = builder.build(result)

    assert len(context.evidence_blocks) == 0
    assert len(context.citations) == 0
    assert context.total_tokens == 0
    assert context.truncated is False


def test_deduplicate_parent_chunks_in_context() -> None:
    """Same parent_id chunks should appear once in evidence blocks."""
    result = _make_retrieval_result(3, same_parent=True)
    builder = ContextBuilder()
    context = builder.build(result)

    assert len(context.evidence_blocks) == 1
    assert len(context.citations) == 1


# ── PromptBuilder Tests ──

def test_prompt_builder_structure() -> None:
    """PromptBuilder should produce system and user messages."""
    result = _make_retrieval_result(2)
    context_builder = ContextBuilder()
    context = context_builder.build(result)

    prompt_builder = PromptBuilder()
    payload = prompt_builder.build(context, "What is the main topic?")

    assert isinstance(payload, PromptPayload)
    assert "ONLY" in payload.system_message
    assert "[Source N]" in payload.system_message or "Source" in payload.system_message
    assert "What is the main topic?" in payload.user_message
    assert "[Source 1]" in payload.user_message
    assert payload.context_tokens > 0


def test_prompt_builder_custom_system_prompt() -> None:
    """PromptBuilder should accept a custom system prompt."""
    result = _make_retrieval_result(1)
    context_builder = ContextBuilder()
    context = context_builder.build(result)

    custom_prompt = "You are a helpful assistant. Be brief."
    prompt_builder = PromptBuilder(system_prompt=custom_prompt)
    payload = prompt_builder.build(context, "test query")

    assert payload.system_message == custom_prompt


def test_prompt_builder_no_sources() -> None:
    """When no sources exist, user message should indicate no sources found."""
    result = RetrievalResult(query_text="test", total_retrieved=0, items=[])
    context = ContextBuilder().build(result)

    payload = PromptBuilder().build(context, "test query")
    assert "No relevant sources found" in payload.user_message
