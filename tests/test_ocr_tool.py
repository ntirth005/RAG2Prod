import pytest
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.config import settings
from tools.ocr_tool import ocr_page, OCRExtractionResult, get_image_hash, get_cache_path

# Temporary test cache directory
TEST_CACHE_DIR = ".cache/test_ocr"

@pytest.fixture(autouse=True)
def setup_test_cache():
    # Override settings OCR cache directory
    old_cache_dir = settings.OCR_CACHE_DIR
    settings.OCR_CACHE_DIR = TEST_CACHE_DIR
    yield
    # Clean up test cache directory
    settings.OCR_CACHE_DIR = old_cache_dir
    shutil.rmtree(TEST_CACHE_DIR, ignore_errors=True)

@pytest.mark.asyncio
async def test_ocr_page_caching() -> None:
    image_bytes = b"fake_image_payload_bytes_123"
    cache_key = get_image_hash(image_bytes)
    cache_file = get_cache_path(cache_key)

    # Assert cache does not exist initially
    assert not cache_file.exists()

    # Mock the API request
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"markdown_content": "## Section 1\\nPreserved Text", "has_tables": false, "detected_language": "en"}'
                }]
            }
        }]
    }

    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        # First call (Cache Miss)
        result1 = await ocr_page(image_bytes, api_key="dummy_key")
        assert result1.markdown_content == "## Section 1\nPreserved Text"
        assert not result1.has_tables
        assert cache_file.exists()
        assert mock_post.call_count == 1

        # Second call (Cache Hit)
        result2 = await ocr_page(image_bytes, api_key="dummy_key")
        assert result2.markdown_content == "## Section 1\nPreserved Text"
        # Verify post was not called again
        assert mock_post.call_count == 1
