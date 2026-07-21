import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.parsers import parse_pdf_file
from core.chunker import StructureAwareChunker

@pytest.mark.asyncio
async def test_docling_parser_integration() -> None:
    # Test Docling mock conversion
    mock_doc = MagicMock()
    mock_doc.export_to_markdown.return_value = (
        "# System Architecture\n\n"
        "Here is the database connection sample code:\n\n"
        "```python\n"
        "def connect_db(uri: str):\n"
        "    return Database(uri)\n"
        "```\n\n"
        "| Service | Port | Status |\n"
        "| --- | --- | --- |\n"
        "| Auth | 8080 | Active |\n"
    )
    
    mock_page = MagicMock()
    mock_page.export_to_markdown.return_value = mock_doc.export_to_markdown.return_value
    mock_doc.pages = {1: mock_page}

    mock_converter_instance = MagicMock()
    mock_converter_instance.convert.return_value = MagicMock(document=mock_doc)

    with patch("docling.document_converter.DocumentConverter", return_value=mock_converter_instance):
        results = await parse_pdf_file(Path("sample_architecture.pdf"))

        assert len(results) == 1
        assert results[0]["page_number"] == 1
        assert "```python" in results[0]["text"]
        assert "| Service | Port | Status |" in results[0]["text"]
        assert results[0]["has_code_blocks"] is True
        assert results[0]["has_tables"] is True

def test_structure_aware_chunker_layout_preservation() -> None:
    text = (
        "# Code & Table Layout Test\n\n"
        "This section tests code block and table preservation in chunking.\n\n"
        "```python\n"
        "class Microservice:\n"
        "    def run(self):\n"
        "        pass\n"
        "```\n\n"
        "| Parameter | Value |\n"
        "| timeout | 30s |\n"
        "| retries | 3 |\n"
    )
    
    chunker = StructureAwareChunker(parent_size=500, child_size=150)
    chunks = chunker.chunk_document("doc_1", text, metadata={"has_code_blocks": True, "has_tables": True})
    
    assert len(chunks) > 0
    # Verify code block chunk preserves ```python
    code_chunks = [c for c in chunks if "```python" in c["text"]]
    assert len(code_chunks) > 0
    assert code_chunks[0]["metadata"]["has_code_blocks"] is True

    # Verify table chunk preserves markdown table pipes |
    table_chunks = [c for c in chunks if "| Parameter | Value |" in c["text"]]
    assert len(table_chunks) > 0
    assert table_chunks[0]["metadata"]["has_tables"] is True
