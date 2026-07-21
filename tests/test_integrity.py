import pytest
from core.chunker import StructureAwareChunker

def test_chunker_handles_duplicate_paragraphs():
    """
    Ensure the chunker does not generate identical chunk_ids for identical text blocks
    that appear in different positions (e.g. repeated disclaimers on multiple pages).
    """
    chunker = StructureAwareChunker(parent_size=50, child_size=10, child_overlap=2)
    
    # Text with a repeated paragraph
    repeated_text = "This is a repeated disclaimer."
    
    document_text = f"""
# Page 1
Some introductory content.
{repeated_text}

# Page 2
Some other content.
{repeated_text}
"""
    
    doc_id = "test-doc-777"
    chunk_results = chunker.chunk_document(doc_id, document_text, metadata={})
    
    # We should have multiple child chunks
    assert len(chunk_results) > 1
    
    # Collect all chunk IDs
    child_ids = [res["chunk_id"] for res in chunk_results]
    
    # Assert that all chunk IDs are unique, even though the text is repeated
    assert len(child_ids) == len(set(child_ids)), "Duplicate chunk IDs found!"
    
    # Find the child chunks that contain the repeated text
    disclaimer_chunks = [res for res in chunk_results if repeated_text in res["text"]]
    
    # There should be exactly two disclaimers found
    assert len(disclaimer_chunks) == 2
    
    # They MUST have different IDs
    assert disclaimer_chunks[0]["chunk_id"] != disclaimer_chunks[1]["chunk_id"]
