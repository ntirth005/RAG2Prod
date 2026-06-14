import pytest
from core.chunker import StructureAwareChunker, count_tokens, generate_chunk_id

def test_token_counting() -> None:
    text = "This is a simple sentence for counting tokens."
    assert count_tokens(text) > 0

def test_deterministic_ids() -> None:
    text = "Unique chunk text content."
    doc_id = "doc_123"
    id1 = generate_chunk_id(doc_id, text)
    id2 = generate_chunk_id(doc_id, text)
    id3 = generate_chunk_id("doc_456", text)
    
    assert id1 == id2
    assert id1 != id3

def test_code_block_preservation() -> None:
    # A single code block that should stay whole
    code_text = (
        "Here is some text before.\n\n"
        "```python\n"
        "def hello_world():\n"
        "    print('hello world')\n"
        "    return 42\n"
        "```\n\n"
        "And some text after."
    )
    # Instantiate chunker with small limits to force splitting, but code block must remain whole
    chunker = StructureAwareChunker(parent_size=100, child_size=50)
    results = chunker.chunk_document("doc_1", code_text, {"source": "test"})
    
    # Verify that the code block was preserved without being split internally
    code_found = False
    for chunk in results:
        if "def hello_world()" in chunk["text"]:
            code_found = True
            # Make sure both the start and end backticks are present in the same chunk
            assert chunk["text"].startswith("```python")
            assert chunk["text"].endswith("```")
            
    assert code_found

def test_table_preservation() -> None:
    table_text = (
        "Below is a table:\n\n"
        "| Item | Price |\n"
        "|---|---|\n"
        "| Apple | $1.00 |\n"
        "| Banana | $0.50 |\n\n"
        "End of document."
    )
    chunker = StructureAwareChunker(parent_size=100, child_size=50)
    results = chunker.chunk_document("doc_1", table_text, {"source": "test"})
    
    # Ensure the table is kept whole in a single chunk
    table_found = False
    for chunk in results:
        if "| Item | Price |" in chunk["text"]:
            table_found = True
            assert "| Apple | $1.00 |" in chunk["text"]
            assert "| Banana | $0.50 |" in chunk["text"]
            
    assert table_found

def test_boundary_balancing() -> None:
    # Set limit to 100 tokens. A paragraph of 120 tokens would split into 100 + 20 naively.
    # The balancer should divide it into ~60 + ~60 tokens at sentence boundary.
    paragraph = (
        "First sentence representing introductory context. "
        "Second sentence adds more descriptions and details to pack the tokens. "
        "Third sentence contains intermediate information and explanations. "
        "Fourth sentence provides concluding remarks to make it slightly longer. "
        "Fifth sentence has final takeaways."
    )
    chunker = StructureAwareChunker(parent_size=40, child_size=20)
    results = chunker.chunk_document("doc_1", paragraph, {"source": "test"})
    
    # Check that parent chunks are split and balanced
    parent_ids = list(set(chunk["parent_id"] for chunk in results))
    assert len(parent_ids) >= 2
    
    # Extract unique parent texts
    parent_texts = list(set(chunk["parent_text"] for chunk in results))
    for pt in parent_texts:
        pt_tokens = count_tokens(pt)
        # Verify that no chunk was left with a tiny number of tokens (e.g. 5 tokens)
        assert pt_tokens > 15
