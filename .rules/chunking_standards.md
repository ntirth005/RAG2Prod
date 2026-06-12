# Ingestion, Parsing & Chunking Standards

Rules for parsing and preparing files for retrieval.

## 1. Document Parsing
* Always preserve original text structure (headings, tables, lists).
* Extract document structure hierarchy (e.g., `#`, `##`, `###`) to populate metadata.

## 2. Chunking Strategy
* Default to **Recursive Character Text Splitter** with:
  * `chunk_size`: 500–1000 tokens (depending on the model window).
  * `chunk_overlap`: 10–20% to prevent losing border context.
* Implement **Parent-Child Chunking** for highly detailed texts:
  * Store small child chunks (e.g., 200 tokens) for vector search.
  * Retrieve and pass the larger parent chunk (e.g., 1000 tokens) to the LLM.

## 3. Metadata Generation
* Every chunk must be tagged with:
  * `doc_id`
  * `page_number` (if PDF)
  * `timestamp` of ingestion
  * `author` or `source` identifier
  * `access_group` (for RBAC)
