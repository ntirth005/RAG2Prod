import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional
from html.parser import HTMLParser
from pypdf import PdfReader
from tools.ocr_tool import ocr_page, OCRExtractionResult
from core.logger import info, timer_step

def clean_text(text: str) -> str:
    """
    Standardize text formatting:
    1. Normalize Unicode symbols (smart quotes, spaces).
    2. Rejoin hyphenated words split across newlines (e.g. 'retrie- \n val' -> 'retrieval').
    """
    if not text:
        return ""
    
    # Unicode normalization (NFKC decomposes compatibility characters and recomposes)
    text = unicodedata.normalize("NFKC", text)
    
    # Replace non-breaking spaces and tabs with normal spaces
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")  # zero-width space
    
    # Rejoin hyphenated words split across page breaks or newlines
    text = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", text)
    
    # Rejoin single-letter spaced PDF kerning artifacts (e.g. 'S c h o o l' -> 'School')
    text = re.sub(r'(?<=\b[A-Za-z]) (?=[A-Za-z]\b)', '', text)
    
    # Standardize multiple newlines/whitespaces slightly, but preserve double-newline paragraph separation
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r\n", "\n", text)
    
    return text

class BoilerplateHTMLStripper(HTMLParser):
    """
    Custom HTML parser that extracts text content from main article tags
    while stripping navigation, script, footer, style, and header boilerplate tags.
    """
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
        self.ignore_tags = {"script", "style", "nav", "footer", "header", "noscript", "aside"}
        self.tag_stack = []

    def handle_starttag(self, tag, attrs):
        self.tag_stack.append(tag)
        # Add basic markdown equivalents for structural blocks
        if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"}:
            self.fed.append("\n")

    def handle_endtag(self, tag):
        if self.tag_stack:
            self.tag_stack.pop()
        if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"}:
            self.fed.append("\n")

    def handle_data(self, data):
        # Check if we are inside any ignored boilerplate tags
        if not any(ignored in self.tag_stack for ignored in self.ignore_tags):
            self.fed.append(data)

    def get_data(self) -> str:
        raw_text = "".join(self.fed)
        # Clean up excessive newlines
        return re.sub(r"\n{3,}", "\n\n", raw_text).strip()

def parse_html_content(html_content: str) -> str:
    """Strip boilerplate tags and extract structured text from HTML content."""
    stripper = BoilerplateHTMLStripper()
    stripper.feed(html_content)
    return clean_text(stripper.get_data())

def parse_text_content(content: str) -> str:
    """Parse and clean raw text or Markdown contents."""
    return clean_text(content)

async def parse_pdf_file(
    file_path: Path, 
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Parses a PDF file page-by-page.
    If programmatic extraction yields empty text, triggers the vision LLM-OCR tool on the page.
    Returns a list of dicts: [{"page_number": int, "text": str}]
    """
    info("parser", f"Opening PDF: {file_path.name}")
    reader = PdfReader(file_path)
    parsed_pages = []

    for i, page in enumerate(reader.pages):
        page_num = i + 1
        text = page.extract_text() or ""
        text = text.strip()

        # Heuristic check: trigger OCR if text is extremely short (<10 chars)
        # OR if text is short (<150 chars) and page contains images (likely a digital watermark/header on a scan)
        has_images = len(page.images) > 0
        trigger_ocr = (len(text) < 10) or (len(text) < 150 and has_images)

        if trigger_ocr:
            image_data = None
            if has_images:
                try:
                    # Get the first image on the page
                    image_data = page.images[0].data
                except Exception:
                    pass
            
            if image_data:
                try:
                    ocr_res: OCRExtractionResult = await ocr_page(image_data, api_key=api_key)
                    text = ocr_res.markdown_content
                except Exception as e:
                    text = f"[OCR Failed on page {page_num}: {e}]"
            else:
                text = f"[Scanned page {page_num} detected, but no extractable image data was found.]"
        else:
            text = clean_text(text)

        parsed_pages.append({
            "page_number": page_num,
            "text": text
        })

    return parsed_pages
