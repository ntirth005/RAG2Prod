# Active Stage: Stage 6 — Query Understanding Complete

You have completed **Milestone 2 (second half):** **Stage 6: Query Understanding**.

---

## Stage 6 Objectives
Build an intelligent Query Understanding subsystem that preprocesses incoming user queries: performs PII detection & redaction, classifies intent and complexity (`SIMPLE`, `MEDIUM`, `COMPLEX`), and dynamically applies Query Rewriting, Query Expansion, or HyDE (Hypothetical Document Embeddings) to improve retrieval accuracy.

---

## Task Checklist
- [x] **Schemas & Models:**
  - Add `QueryTrace` model to `src/core/schemas.py` and link to `GenerationResult`.
- [x] **Query Understanding Subsystem:**
  - Create `src/core/query_understanding.py` containing `PIIDetector` (PII scanning & redaction), `IntentClassifier` (intent & complexity classification), `QueryTransformer` (Query Rewriting for SIMPLE, Query Expansion for MEDIUM, HyDE for COMPLEX), and `QueryUnderstandingEngine`.
- [x] **Multi-Query Vector Retrieval:**
  - Add `search_multi()` method to `DenseRetriever` in `src/core/retriever.py` to search multiple query variations and deduplicate candidate chunks by max similarity score.
- [x] **Pipeline & Stream Integration:**
  - Update `RAGPipeline` in `src/core/generator.py` and endpoints in `src/main.py` to transmit `query_trace` events over SSE and JSON APIs.
- [x] **Dashboard UI Upgrade:**
  - Add an expandable **Query Understanding Accordion & Badges** (`#queryTraceBox`) to `src/templates/dashboard.html` showing Intent, Complexity, PII status, expanded query variations, and generated HyDE passages.
- [x] **Test Suites:**
  - Create `tests/test_query_understanding.py` (11 tests).
  - All 53 tests passing across repository.
