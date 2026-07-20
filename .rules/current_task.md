# Active Stage: Stage 3 — Basic Retrieval Complete

You have completed **Milestone 1: First Working RAG** — **Stage 2: Storage Layer** and **Stage 3: Basic Retrieval**.

---

## Stage 2 & Stage 3 Objectives
Set up the relational and vector storage layers (PostgreSQL and Pgvector) to store raw documents, parent-child chunks, and dense vector embeddings, alongside an object storage interface, DAO storage service, and REST retrieval API endpoints.

---

## Task Checklist
- [x] **Setup Relational DB (Postgres) Connection Management:**
  - Create `src/core/database.py` with async connection pool using SQLAlchemy and `asyncpg`.
- [x] **Define Database Models:**
  - Create `src/core/models.py` with SQLAlchemy async models for `Document`, `ParentChunk`, and `ChildChunk`.
  - Link child chunks to parent chunks and document metadata, and define a vector column for embeddings (dimension 384).
- [x] **Implement Database Initialization & HNSW Vector Index:**
  - Write async schema initialization to create tables.
  - Enable the `pgvector` extension dynamically.
  - Create an **HNSW vector index** on the `ChildChunk.embedding` column with Cosine Distance (`<=>`) for sub-linear similarity search.
- [x] **Implement Storage DAO & High-Level Ingestion Service:**
  - Create `src/core/storage_service.py` to handle parsing, chunking, embedding, object storage, and DB persistence atomically.
- [x] **Implement Dense Vector Retrieval Engine:**
  - Create `src/core/retriever.py` with cosine distance (`<=>`) queries, score thresholds, parent-context expansion, and JSONB metadata filtering.
- [x] **Implement Object Storage Layer:**
  - Create `src/core/object_storage.py` defining a generic file storage interface with local directory fallback.
- [x] **Implement REST API Endpoints:**
  - `POST /api/v1/documents/ingest` and `POST /api/v1/retrieval/search` in `src/main.py`.
- [x] **Add Test Suites:**
  - Write comprehensive tests in `tests/test_storage.py`, `tests/test_storage_service.py`, `tests/test_retriever.py`, and `tests/test_api.py`.
