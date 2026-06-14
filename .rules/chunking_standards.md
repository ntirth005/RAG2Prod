# Ingestion, Parsing & Chunking Standards

Rules for parsing, structuring, chunking, and generating metadata for files.

## 1. Re-Structuring Data (Parsing)
* **Document Parser:** Convert raw document files into semantic nodes.
  * **PDFs:** Support page-by-page text extraction, preserving headers/footers separation and mapping text to page numbers.
  * **LLM-OCR Agent Tool:** Scanned documents, screenshots, and visual assets are processed by exposing an LLM-OCR tool to the agent. The tool uses a Multimodal LLM to extract text, preserving visual formatting (such as tables and heading trees) into clean Markdown.
  * **HTML/Web Search Results:** Strip navigation bars, ads, cookie popups, and footers. Extract clean main-article text.
  * **Code Files / Code Blocks:** Identify code blocks (e.g., code boundaries wrapped in triple backticks) and preserve language tags and formatting.
  * **Text Cleaning:** 
    * Normalize Unicode formatting (e.g., replace non-breaking spaces `\u00a0` and smart quotes).
    * Rejoin hyphenated words split across page breaks/newlines (e.g., `retrie-` `val` $\rightarrow$ `retrieval`).
* **Structure Analyzer:** Extract structural hierarchy (headings, list trees, tables) and preserve document formatting.

## 2. Structure-Aware Chunking
* **Table Preserver:** Tables must be kept intact and not split across chunks. Convert tables to Markdown format to preserve structure and searchability.
* **Code Block Preserver:** Never split a code block across chunks. A code block must remain whole in a single chunk to retain context and syntax correctness.
* **Heading Detector:** Detect structural headings (`#`, `##`, `###`) to ensure chunks do not split immediately after a heading, and attach headings as context to child chunks.
* **Boundary Detector (Dynamic Balancing):** 
  * Avoid cutting off small paragraph fragments at chunk boundaries (e.g., leaving 20 orphan tokens). 
  * If a paragraph causes an overflow, either start a new chunk or dynamically balance the split (e.g., two 250-token chunks split at a sentence boundary) instead of a strict token-limit cutoff.
  * Target chunk sizes:
    * **Parent Chunks:** 1000 tokens (for LLM context).
    * **Child Chunks:** 200–250 tokens (for vector search indexing).
  * **Token Safety Margin:** Enforce a 10% safety buffer under maximum model limits (e.g., maximum child size of 225 tokens for a 250 limit) to prevent tokenization drift on special characters and code blocks.
* **Parent-Child Mapping:** Map multiple child chunks back to their single parent chunk ID to enable high-precision retrieval with broad context window QA.

## 3. Metadata Creation & Deduplication
Every chunk must generate and include the following metadata:
* **Deterministic Chunk IDs:** Generate unique `chunk_id` values deterministically (e.g., UUID v5 based on a namespace and hash of `doc_id + chunk_text` or `doc_id + page_offset`) to prevent duplicate chunk ingestion.
* **System Metadata:** `doc_id`, `page_number` (if PDF), `timestamp`, `author`/`source`, and RBAC `access_group`.
* **Summary Generator:** A brief LLM-generated summary of the parent context.
* **Keyword Extractor:** Key terms extracted to boost sparse (BM25) search.
* **Question Generator:** Synthetic questions that this chunk answers (used to improve retrieval accuracy).
