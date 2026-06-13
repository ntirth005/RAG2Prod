# Ingestion, Parsing & Chunking Standards

Rules for parsing, structuring, chunking, and generating metadata for files.

## 1. Re-Structuring Data (Parsing)
* **Document Parser:** Convert raw document files (PDFs, Markdown, text) into semantic nodes.
* **Structure Analyzer:** Extract structural hierarchy (headings, list trees, tables) and preserve document formatting.

## 2. Structure-Aware Chunking
* **Table Preserver:** Tables must be kept intact and not split across chunks. Convert tables to Markdown format to preserve structure and searchability.
* **Heading Detector:** Detect structural headings (`#`, `##`, `###`) to ensure chunks do not split immediately after a heading, and attach headings as context to child chunks.
* **Boundary Detector (Dynamic Balancing):** 
  * Avoid cutting off small paragraph fragments at chunk boundaries (e.g., leaving 20 orphan tokens). 
  * If a paragraph causes an overflow, either start a new chunk or dynamically balance the split (e.g., two 250-token chunks split at a sentence boundary) instead of a strict token-limit cutoff.
  * Target chunk sizes:
    * **Parent Chunks:** 1000 tokens (for LLM context).
    * **Child Chunks:** 200–250 tokens (for vector search indexing).

## 3. Metadata Creation
Every chunk must generate and include the following metadata:
* **System Metadata:** `doc_id`, `page_number` (if PDF), `timestamp`, `author`/`source`, and RBAC `access_group`.
* **Summary Generator:** A brief LLM-generated summary of the parent context.
* **Keyword Extractor:** Key terms extracted to boost sparse (BM25) search.
* **Question Generator:** Synthetic questions that this chunk answers (used to improve retrieval accuracy).
