import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
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
    Parses a PDF file using IBM Docling for layout-aware structure extraction (preserving code blocks, 
    tables, headings, and reading order).
    Falls back to pypdf + Gemini Vision OCR if Docling is unavailable or page text is sparse.
    Returns a list of dicts: [{"page_number": int, "text": str, "raw_text": str, "has_code_blocks": bool, "has_tables": bool}]
    """
    info("parser", f"Opening PDF with layout-aware parser: {file_path.name}")
    parsed_pages = []

    # Attempt Docling DocumentConverter for lossless layout parsing
    try:
        from docling.document_converter import DocumentConverter
        info("parser", f"Initializing Docling DocumentConverter for {file_path.name}")
        converter = DocumentConverter()
        doc_result = converter.convert(str(file_path))
        doc = doc_result.document
        
        # Docling allows exporting full markdown or per-page content
        # Check if per-page export is supported or iterate pages
        if hasattr(doc, "pages") and doc.pages:
            for page_no, page_obj in doc.pages.items():
                # Export page markdown or text elements
                page_md = ""
                if hasattr(page_obj, "export_to_markdown"):
                    page_md = page_obj.export_to_markdown()
                else:
                    # Fallback to page text export
                    page_md = str(page_obj)

                if not page_md.strip():
                    # If page markdown is empty, export full doc or fallback
                    page_md = doc.export_to_markdown()

                has_code = "```" in page_md
                has_tables = "|" in page_md and "\n" in page_md

                parsed_pages.append({
                    "page_number": int(page_no),
                    "text": page_md.strip(),
                    "raw_text": page_md.strip(),
                    "has_code_blocks": has_code,
                    "has_tables": has_tables
                })
        else:
            full_md = doc.export_to_markdown()
            has_code = "```" in full_md
            has_tables = "|" in full_md
            parsed_pages.append({
                "page_number": 1,
                "text": full_md.strip(),
                "raw_text": full_md.strip(),
                "has_code_blocks": has_code,
                "has_tables": has_tables
            })
            
        if parsed_pages and any(p["text"] for p in parsed_pages):
            info("parser", f"Docling successfully parsed {len(parsed_pages)} pages for {file_path.name}")
            return parsed_pages

    except Exception as e:
        info("parser", f"Docling parsing notice for {file_path.name}: {e}. Proceeding with pypdf + Vision fallback.")

    # Fallback: pypdf page-by-page + Gemini Vision OCR for scanned/sparse pages
    reader = PdfReader(file_path)
    for i, page in enumerate(reader.pages):
        page_num = i + 1
        text = page.extract_text() or ""
        text = text.strip()

        has_images = len(page.images) > 0
        trigger_ocr = (len(text) < 10) or (len(text) < 150 and has_images)
        has_code = "```" in text
        has_tables = "|" in text

        if trigger_ocr:
            image_data = None
            if has_images:
                try:
                    image_data = page.images[0].data
                except Exception:
                    pass
            
            if image_data:
                try:
                    ocr_res: OCRExtractionResult = await ocr_page(image_data, api_key=api_key)
                    text = ocr_res.markdown_content
                    has_code = ocr_res.has_code_blocks
                    has_tables = ocr_res.has_tables
                except Exception as ex:
                    text = f"[OCR Failed on page {page_num}: {ex}]"
            else:
                text = f"[Scanned page {page_num} detected, but no extractable image data was found.]"
        else:
            text = clean_text(text)

        parsed_pages.append({
            "page_number": page_num,
            "text": text,
            "raw_text": page.extract_text() or text,
            "has_code_blocks": has_code,
            "has_tables": has_tables
        })

    return parsed_pages


def compute_offsets(
    full_text: str,
    snippet: str,
    search_from: int = 0
) -> Tuple[int, int, int, int]:
    """
    Computes (start_char, end_char, start_line, end_line) of snippet within full_text starting from search_from.
    Lines are 1-indexed.
    """
    if not snippet or not full_text:
        return 0, 0, 1, 1

    start_idx = full_text.find(snippet, search_from)
    if start_idx == -1:
        start_idx = full_text.find(snippet)

    if start_idx == -1:
        # Fuzzy fallback: match leading 30 characters
        short_prefix = snippet[:30].strip()
        if short_prefix:
            start_idx = full_text.find(short_prefix, search_from)
            if start_idx == -1:
                start_idx = full_text.find(short_prefix)

    if start_idx == -1:
        start_idx = min(search_from, len(full_text))
        end_idx = min(start_idx + len(snippet), len(full_text))
    else:
        end_idx = min(start_idx + len(snippet), len(full_text))

    start_line = 1 + full_text.count("\n", 0, start_idx)
    end_line = 1 + full_text.count("\n", 0, end_idx)

    return start_idx, end_idx, start_line, end_line

