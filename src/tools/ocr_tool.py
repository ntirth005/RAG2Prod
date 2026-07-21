import os
import hashlib
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional
import httpx
from pydantic import BaseModel, Field
from core.config import settings
from core.logger import info

class OCRExtractionResult(BaseModel):
    markdown_content: str = Field(..., description="The parsed text, formatted in clean Markdown.")
    has_tables: bool = Field(False, description="True if tables were parsed/found in the document page.")
    has_code_blocks: bool = Field(False, description="True if code blocks were parsed/found.")
    detected_language: str = Field("en", description="ISO language code detected.")

def get_image_hash(image_bytes: bytes) -> str:
    """Calculate SHA-256 hash of image bytes for cache key validation."""
    return hashlib.sha256(image_bytes).hexdigest()

def get_cache_path(cache_key: str) -> Path:
    """Generate the local cache file path based on the cache key."""
    cache_dir = Path(settings.OCR_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_key}.json"

def read_from_cache(cache_key: str) -> Optional[OCRExtractionResult]:
    """Read OCR results from local file cache if it exists."""
    cache_file = get_cache_path(cache_key)
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return OCRExtractionResult.model_validate(data)
        except Exception:
            return None
    return None

def write_to_cache(cache_key: str, result: OCRExtractionResult) -> None:
    """Write OCR results to local file cache using atomic replacement."""
    cache_file = get_cache_path(cache_key)
    temp_file = cache_file.with_suffix(".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
        temp_file.replace(cache_file)
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass

async def ocr_page(
    image_bytes: bytes, 
    mime_type: str = "image/png", 
    api_key: Optional[str] = None
) -> OCRExtractionResult:
    """
    Extracts text and structure from page image bytes using a Multimodal LLM (Gemini).
    Utilizes local file-based SHA-256 caching.
    """
    cache_key = get_image_hash(image_bytes)
    cached_result = read_from_cache(cache_key)
    if cached_result is not None:
        info("ocr", f"Cache hit for image hash {cache_key[:12]}…")
        return cached_result

    # Fallback to API Key from settings if not passed
    gemini_key = api_key or settings.GEMINI_API_KEY
    if not gemini_key:
        # For testing/dev environments, return a mock/error result if no key is found
        return OCRExtractionResult(
            markdown_content="[Error: GEMINI_API_KEY not configured. LLM OCR requires a valid API key.]",
            has_tables=False,
            has_code_blocks=False,
            detected_language="en"
        )

    # Base64 encode the image bytes
    base64_data = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "Perform lossless layout-aware document OCR on this page image.\n"
        "Rules:\n"
        "1. Preserve headings exactly (using markdown #, ##, ###).\n"
        "2. Preserve CODE BLOCKS using fenced code blocks (```language ... ```) with syntax tags.\n"
        "3. Convert tables into clean, aligned Markdown tables (| col1 | col2 |).\n"
        "4. Describe flowcharts, diagrams, and figures comprehensively as `![Figure: Title](Detailed description)`.\n"
        "5. Output your result strictly as JSON matching this schema:\n"
        "{\n"
        "  \"markdown_content\": \"string\",\n"
        "  \"has_tables\": true/false,\n"
        "  \"has_code_blocks\": true/false,\n"
        "  \"detected_language\": \"en\"\n"
        "}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    
    # Configure the payload for Gemini 2.5 Flash structured output
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": base64_data
                    }
                }
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "markdown_content": {"type": "STRING"},
                    "has_tables": {"type": "BOOLEAN"},
                    "has_code_blocks": {"type": "BOOLEAN"},
                    "detected_language": {"type": "STRING"}
                },
                "required": ["markdown_content", "has_tables", "has_code_blocks", "detected_language"]
            }
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
        resp_data = response.json()

    try:
        # Extract the structured JSON content returned by Gemini
        text_response = resp_data["candidates"][0]["content"]["parts"][0]["text"]
        result_dict = json.loads(text_response)
        result = OCRExtractionResult.model_validate(result_dict)
    except Exception as e:
        raise ValueError(f"Failed to parse structured OCR response from Gemini: {e}. Raw response: {resp_data}")

    # Write to local cache
    write_to_cache(cache_key, result)
    return result
