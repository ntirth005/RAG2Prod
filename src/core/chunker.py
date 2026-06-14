import re
import uuid
from typing import List, Dict, Any, Tuple
import tiktoken
from core.config import settings

# Initialize tiktoken encoder
try:
    _encoder = tiktoken.get_encoding("cl100k_base")
except Exception:
    _encoder = tiktoken.get_encoding("gpt2")

def count_tokens(text: str) -> int:
    """Return the number of tokens in the given text using the tiktoken encoding."""
    return len(_encoder.encode(text))

def generate_chunk_id(doc_id: str, text: str) -> str:
    """Generate a deterministic UUID v5 chunk ID from doc_id and chunk text."""
    # Using NAMESPACE_DNS as namespace
    name = f"{doc_id}:{hashlib_sha256_hash(text)}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))

def hashlib_sha256_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

class StructureAwareChunker:
    """
    Splits document text into parent-child chunks while preserving structural blocks 
    (headings, code blocks, tables) and balancing boundaries dynamically.
    """
    def __init__(
        self,
        parent_size: int = 1000,
        child_size: int = 200,
        child_overlap: int = 50,
        safety_margin_percent: float = 0.10
    ):
        self.parent_size = parent_size
        self.child_size = child_size
        self.child_overlap = child_overlap
        # Apply safety margin to limit packing
        self.parent_limit = int(parent_size * (1 - safety_margin_percent))
        self.child_limit = int(child_size * (1 - safety_margin_percent))

    def _segment_into_blocks(self, text: str) -> List[Dict[str, Any]]:
        """
        Segment document into structural blocks: headings, code blocks, tables, and paragraphs.
        """
        blocks = []
        
        # Regex to split on code block boundaries
        # This keeps the code block together with its language tags
        parts = re.split(r"(```[\s\S]*?```)", text)
        
        for part in parts:
            if not part.strip():
                continue
            
            # If it's a code block, preserve it (auto-close if unclosed)
            if part.startswith("```"):
                if not part.endswith("```") or len(part) < 6:
                    if not part.endswith("```"):
                        part = part + "\n```"
                blocks.append({
                    "type": "code",
                    "text": part,
                    "tokens": count_tokens(part)
                })
            else:
                # Process normal text parts, splitting on tables and paragraphs
                subparts = part.split("\n\n")
                for subpart in subparts:
                    if not subpart.strip():
                        continue
                    
                    # Check if the subpart represents a markdown table
                    lines = subpart.strip().split("\n")
                    is_table = any(line.strip().startswith("|") and line.strip().endswith("|") for line in lines)
                    
                    if is_table:
                        blocks.append({
                            "type": "table",
                            "text": subpart,
                            "tokens": count_tokens(subpart)
                        })
                    # Check if it's a heading
                    elif re.match(r"^#{1,6}\s+", subpart.strip()):
                        blocks.append({
                            "type": "heading",
                            "text": subpart,
                            "tokens": count_tokens(subpart)
                        })
                    else:
                        blocks.append({
                            "type": "paragraph",
                            "text": subpart,
                            "tokens": count_tokens(subpart)
                        })
        return blocks

    def _split_large_block(self, text: str, limit: int) -> List[str]:
        """
        Splits a single block (e.g. a huge paragraph) that exceeds limits into 
        dynamically balanced smaller chunks split at sentence boundaries.
        """
        # Split on sentence boundaries
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = count_tokens(sentence)
            if current_tokens + sentence_tokens > limit:
                if current_chunk:
                    # Balance check: if remaining sentence is small, merge or balance
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [sentence]
                    current_tokens = sentence_tokens
                else:
                    # Single sentence is larger than limit; split by words
                    words = sentence.split(" ")
                    word_chunk = []
                    word_tokens = 0
                    for word in words:
                        w_tokens = count_tokens(word)
                        if word_tokens + w_tokens > limit:
                            chunks.append(" ".join(word_chunk))
                            word_chunk = [word]
                            word_tokens = w_tokens
                        else:
                            word_chunk.append(word)
                            word_tokens += w_tokens
                    if word_chunk:
                        current_chunk = word_chunk
                        current_tokens = word_tokens
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens
                
        if current_chunk:
            chunks.append(" ".join(current_chunk))
            
        # Dynamic balancing: if we ended up with a small spillover, balance size
        if len(chunks) > 1:
            last_chunk = chunks[-1]
            last_tokens = count_tokens(last_chunk)
            # If last chunk is very small (e.g., less than 50 tokens or 20% of limit), balance it with the second-to-last
            if last_tokens < int(limit * 0.20):
                prev_chunk = chunks[-2]
                combined = prev_chunk + " " + last_chunk
                combined_sentences = re.split(r"(?<=[.!?])\s+", combined)
                
                # Split roughly down the middle sentence count
                midpoint = len(combined_sentences) // 2
                chunks[-2] = " ".join(combined_sentences[:midpoint])
                chunks[-1] = " ".join(combined_sentences[midpoint:])
                
        return chunks

    def chunk_document(
        self, 
        doc_id: str, 
        text: str, 
        metadata: dict
    ) -> List[Dict[str, Any]]:
        """
        Chunks the document into Parent-Child mappings.
        Returns a list of chunk dictionaries containing:
        - parent_id, parent_text
        - child_id, child_text
        - metadata
        """
        blocks = self._segment_into_blocks(text)
        parents = []
        current_parent_blocks = []
        current_tokens = 0

        for block in blocks:
            # If a single block is larger than parent limit, split it first (unless code/table)
            if block["tokens"] > self.parent_limit:
                if block["type"] in {"code", "table"}:
                    # Keep whole even if slightly large, but close the previous parent first
                    if current_parent_blocks:
                        parents.append("\n\n".join([b["text"] for b in current_parent_blocks]))
                        current_parent_blocks = []
                        current_tokens = 0
                    parents.append(block["text"])
                else:
                    # Split huge paragraph block into balanced sub-blocks
                    sub_blocks = self._split_large_block(block["text"], self.parent_limit)
                    for sb in sub_blocks:
                        if current_tokens + count_tokens(sb) > self.parent_limit:
                            if current_parent_blocks:
                                parents.append("\n\n".join([b["text"] for b in current_parent_blocks]))
                            current_parent_blocks = [{"text": sb, "tokens": count_tokens(sb)}]
                            current_tokens = count_tokens(sb)
                        else:
                            current_parent_blocks.append({"text": sb, "tokens": count_tokens(sb)})
                            current_tokens += count_tokens(sb)
            else:
                if current_tokens + block["tokens"] > self.parent_limit:
                    parents.append("\n\n".join([b["text"] for b in current_parent_blocks]))
                    current_parent_blocks = [block]
                    current_tokens = block["tokens"]
                else:
                    current_parent_blocks.append(block)
                    current_tokens += block["tokens"]

        if current_parent_blocks:
            parents.append("\n\n".join([b["text"] for b in current_parent_blocks]))

        results = []
        for parent_text in parents:
            parent_id = generate_chunk_id(doc_id, parent_text)
            
            # Split parent text into child chunks
            child_texts = self._create_child_chunks(parent_text)
            
            for child_text in child_texts:
                child_id = generate_chunk_id(doc_id, child_text)
                
                results.append({
                    "document_id": doc_id,
                    "parent_id": parent_id,
                    "parent_text": parent_text,
                    "chunk_id": child_id,
                    "text": child_text,
                    "metadata": {
                        **metadata,
                        "parent_id": parent_id,
                        "chunk_id": child_id
                    }
                })
        return results

    def _create_child_chunks(self, parent_text: str) -> List[str]:
        """
        Creates child chunks from parent text, ensuring code blocks and tables stay whole
        and text is split cleanly into overlapping segments.
        """
        # Segment parent into blocks
        blocks = self._segment_into_blocks(parent_text)
        child_chunks = []
        current_child_text = []
        current_tokens = 0
        
        for block in blocks:
            # Code blocks and tables are kept intact as children if they fit
            if block["type"] in {"code", "table"}:
                if current_child_text:
                    child_chunks.append("\n\n".join(current_child_text))
                    current_child_text = []
                    current_tokens = 0
                child_chunks.append(block["text"])
            else:
                # Standard paragraph or heading
                # Split block into sentences to pack child chunks
                sentences = re.split(r"(?<=[.!?])\s+", block["text"])
                for sentence in sentences:
                    sentence_tokens = count_tokens(sentence)
                    if current_tokens + sentence_tokens > self.child_limit:
                        if current_child_text:
                            child_chunks.append(" ".join(current_child_text))
                            # Apply overlap by taking the last sentence if any
                            overlap_sentence = current_child_text[-1] if current_child_text else ""
                            overlap_tokens = count_tokens(overlap_sentence)
                            if overlap_tokens < self.child_overlap:
                                current_child_text = [overlap_sentence, sentence] if overlap_sentence else [sentence]
                                current_tokens = overlap_tokens + sentence_tokens
                            else:
                                current_child_text = [sentence]
                                current_tokens = sentence_tokens
                        else:
                            # Single sentence is huge; force split it
                            sub_sentences = self._split_large_block(sentence, self.child_limit)
                            child_chunks.extend(sub_sentences)
                            current_child_text = []
                            current_tokens = 0
                    else:
                        current_child_text.append(sentence)
                        current_tokens += sentence_tokens
                        
        if current_child_text:
            child_chunks.append(" ".join(current_child_text))
            
        # Clean any empty chunks
        return [c.strip() for c in child_chunks if c.strip()]
