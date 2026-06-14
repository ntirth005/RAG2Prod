import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.parsers import clean_text, parse_html_content, parse_text_content, parse_pdf_file

def test_clean_text() -> None:
    # Test unicode normalization
    assert clean_text("hello\u00a0world") == "hello world"
    assert clean_text("hello\u200bworld") == "helloworld"
    
    # Test hyphen rejoining
    assert clean_text("retrie-\nval") == "retrieval"
    assert clean_text("docu-\n   ment") == "document"
    
    # Test whitespace normalization
    assert clean_text("multiple   spaces") == "multiple spaces"
    assert clean_text("line1\r\nline2") == "line1\nline2"

def test_parse_html_content() -> None:
    html = """
    <html>
        <head><style>body { color: red; }</style></head>
        <body>
            <nav>Menu link</nav>
            <h1>Main Title</h1>
            <p>This is the first paragraph with some <b>bold</b> text.</p>
            <footer>Footer boilerplate</footer>
        </body>
    </html>
    """
    cleaned = parse_html_content(html)
    assert "Main Title" in cleaned
    assert "first paragraph" in cleaned
    assert "Menu link" not in cleaned
    assert "Footer boilerplate" not in cleaned

def test_parse_text_content() -> None:
    text = "hello\u00a0world"
    assert parse_text_content(text) == "hello world"

@patch("core.parsers.PdfReader")
@pytest.mark.asyncio
async def test_parse_pdf_file(mock_pdf_reader) -> None:
    # Mocking PdfReader pages
    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = "This is digital text from page 1."
    mock_page_1.images = []

    mock_page_2 = MagicMock()
    mock_page_2.extract_text.return_value = ""  # empty text to trigger OCR
    
    # Mock image data on page 2
    mock_image = MagicMock()
    mock_image.data = b"fake_image_bytes"
    mock_page_2.images = [mock_image]

    # Mock reader setup
    mock_reader_instance = MagicMock()
    mock_reader_instance.pages = [mock_page_1, mock_page_2]
    mock_pdf_reader.return_value = mock_reader_instance

    # Patch ocr_page tool
    with patch("core.parsers.ocr_page") as mock_ocr:
        mock_ocr.return_value = MagicMock(markdown_content="OCR extracted text for page 2.")
        
        results = await parse_pdf_file(Path("fake.pdf"), api_key="fake_key")
        
        assert len(results) == 2
        assert results[0]["page_number"] == 1
        assert results[0]["text"] == "This is digital text from page 1."
        assert results[1]["page_number"] == 2
        assert results[1]["text"] == "OCR extracted text for page 2."
        mock_ocr.assert_called_once_with(b"fake_image_bytes", api_key="fake_key")
