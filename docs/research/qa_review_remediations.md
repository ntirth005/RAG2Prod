# Ingestion QA Review & Remediations

This document summarizes the edge cases, vulnerabilities, and logic flaws identified during critical human-like testing of the Stage 1 Ingestion pipeline, along with the remediations applied.

---

## 1. Concurrency Cache Corruption
* **Issue:** Concurrent asynchronous ingestion tasks calling the `LLM_OCR` tool could read or write the same `.cache/ocr/{hash}.json` files simultaneously under high load, causing corrupted JSON or write permissions crashes.
* **Remediation:** Refactored cache writing to use **Atomic File Replacement** (writing to a temporary file `.tmp` first, then calling `temp_file.replace(cache_file)`). This prevents file corruption and partial reads under parallel execution without third-party database locking engines.

## 2. Unclosed Code Blocks
* **Issue:** Malformed or truncated Markdown inputs containing opening triple backticks `` ``` `` but missing the closing marker would break regex segmentation, treating the remainder of the document as regular text.
* **Remediation:** Upgraded the block segmenter in the chunker. If a text segment starts with `` ``` `` but does not end with `` ``` ``, the chunker dynamically appends the closing marker, auto-healing the code block so formatting does not bleed into downstream chunks.

## 3. Scanned PDF Vector Drawings (Watermark / Scanning Detection)
* **Issue:** Digital watermarks, stamps, or page headers on scanned PDFs return 10–100 characters of text, bypassing traditional 0-character scanned checks and leaving the core page image skipped.
* **Remediation:** Lowered character thresholds to `10` for normal pages, but created an **image-to-text presence ratio check**: if the extracted text is under `150` characters but the page contains image elements, the parser assumes the text is just a header/footer watermark and triggers LLM OCR extraction on the underlying page image.

## 4. Concurrent Testing Side-Effects
* **Issue:** Modifying the global configuration `settings.OCR_CACHE_DIR` directly in pytest fixtures creates side-effects that cause test flakiness if tests are executed in parallel.
* **Future Recommendation:** Transition testing to pass the cache path explicitly to helper calls (dependency injection) or patch settings mock variables dynamically.
