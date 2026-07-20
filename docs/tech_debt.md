# Technical Debt & Feature Backlog

This document tracks known technical debt, missing edge-case handlers, and planned parser/retrieval improvements for upcoming stages.

---

## 1. Knowledge Ingestion & Parsing

### `TD-001`: Integration of `pdfplumber` for Table-Aware Extraction
- **Description**: Standard `pypdf` digital text extraction collapses multi-column tables into raw space-separated text lines, causing loss of table grid boundaries.
- **Impact**: Queries searching for specific table cells or numerical statistics (e.g. placement rates, salary tables) may miss matched chunks or lose row-column relationships unless processed via Vision OCR.
- **Proposed Solution**:
  - Integrate `pdfplumber` into `src/core/parsers.py` to detect tabular bounding boxes in digital PDFs and render them as Markdown tables (`| Col 1 | Col 2 |`).
  - Add a `force_ocr` parameter in `StorageService.ingest_file()` to force full multimodal vision OCR on table-heavy documents.
- **Target Stage**: Stage 7 / Stage 18 (Ingestion Improvements).

---

## 2. Retrieval & Generation

### `TD-002`: Cross-Encoder Reranking for Numerical Tables
- **Description**: Dense vector embeddings (`all-MiniLM-L6-v2`) prioritize high-level semantic descriptions over specific numeric rows.
- **Proposed Solution**: Add Cross-Encoder Reranker in Stage 7 to reorder top 50 candidates, elevating exact numerical chunks to top position.
