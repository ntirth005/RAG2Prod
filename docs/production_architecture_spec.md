# RAG2Prod: Production Architecture & Design Specification

**Status:** Approved for Implementation
**Target Environment:** High-Concurrency Production (Kubernetes)

This document outlines the architectural requirements and critical design decisions that MUST be adhered to during the development of the RAG2Prod system. These requirements are derived from standard Site Reliability Engineering (SRE), Security, and Systems Architecture best practices to ensure the system is resilient, scalable, and secure from day one.

---

## 1. System Resilience & Concurrency

### 1.1 Non-Blocking Event Loop
FastAPI relies on a single-threaded async event loop. 
- **Requirement:** CPU-bound Machine Learning tasks (such as `CrossEncoderReranker.rerank`) MUST NOT run synchronously on the main thread. 
- **Implementation:** Wrap all heavy CPU-bound inference calls in `asyncio.to_thread` to push them to a background thread pool, ensuring the server remains responsive to concurrent API requests.
- **Library Selection:** Python's native `asyncio.to_thread`.
  - *Evaluated:* `concurrent.futures.ThreadPoolExecutor`, `asyncio.to_thread`.
  - *Why Selected:* `asyncio.to_thread` is a native, lightweight wrapper around threadpools introduced in Python 3.9 that requires zero configuration and avoids manually managing executor lifecycles.

### 1.2 HTTP Connection Pooling
- **Requirement:** Do not instantiate ephemeral HTTP clients per request. High throughput will lead to TCP port exhaustion and socket hangs.
- **Implementation:** Both the `LLMClient` and `EmbeddingClient` MUST utilize a global, long-lived `httpx.AsyncClient` with explicit connection pooling (e.g., `Limits(max_connections=100, max_keepalive_connections=20)`).
- **Library Selection:** `httpx`
  - *Evaluated:* `requests` (synchronous, blocks event loop), `aiohttp` (good, but less ergonomic API), `httpx`.
  - *Why Selected:* `httpx` offers first-class async support, strict connection pooling configurations, thread-safety, and an API identical to `requests`.

---

## 2. Security & Data Integrity

### 2.1 Path Traversal Prevention
- **Requirement:** Endpoints that retrieve files from disk (e.g., `/documents/{doc_id}/file`) are highly susceptible to Directory Traversal (`../../etc/passwd`).
- **Implementation:** Metadata storage paths MUST be resolved to absolute paths and strictly validated using `path.resolve().is_relative_to(base_storage_dir)` before yielding the file.

### 2.2 Strict Transaction Rollbacks & Retries (No Silent Failures)
- **Requirement:** Partial ingestions cause vector store corruption. If an API or database transaction fails, the system must not silently mock the data. It must safely rollback, clean up, and retry transient failures.
- **Implementation:** 
  1. Remove all `except Exception` blocks that return empty or mock data.
  2. Implement atomic database transactions. If `session.commit()` fails, the system MUST catch the exception, execute `session.rollback()`, and explicitly delete any orphaned files from Object Storage.
  3. Apply exponential backoff decorators to transient database operations (e.g., `IntegrityError`).
- **Library Selection:** `tenacity`
  - *Evaluated:* Custom `while/sleep` loop, `backoff`, `tenacity`.
  - *Why Selected:* `tenacity` provides powerful declarative decorators, exponential backoff, jitter, and granular exception targeting (e.g., `retry_if_exception_type`), making it the industry standard for retry logic in Python.

---

## 3. Scalability & Performance

### 3.1 Database-Native Full Text Search (FTS)
- **Requirement:** Do not use in-memory sparse retrieval. Loading thousands of documents into Python RAM on every startup/request is unscalable and causes OOM crashes.
- **Implementation:** Utilize **PostgreSQL Full Text Search** natively. Store `to_tsvector` in the database and query using `websearch_to_tsquery`.
- **Library Selection:** `PostgreSQL FTS` via `SQLAlchemy`
  - *Evaluated:* `rank_bm25` (in-memory Python, OOM risk), `ElasticSearch` (heavy infrastructure overhead), `PostgreSQL FTS`.
  - *Why Selected:* Reuses our existing relational database (pgvector), eliminates the network hop to a separate ElasticSearch cluster, requires zero extra infrastructure, and scales far beyond Python's RAM limitations.

### 3.2 SQL-Level Filtering
- **Requirement:** Do not fetch excessive rows from the database only to filter them in Python (e.g., retrieving `top_k * 2` and applying `score_threshold` in memory).
- **Implementation:** Push `score_threshold` filters directly into the PostgreSQL `WHERE` clause to avoid false-negative limits and reduce data transfer overhead.

### 3.3 Large File Streaming (OOM Prevention)
- **Requirement:** The system must support massive file uploads (e.g., 10GB videos/PDFs) without crashing the server.
- **Implementation:** Avoid `await file.read()`. Use `aiofiles` to stream uploaded bytes in 1MB chunks directly to local object storage.
- **Library Selection:** `aiofiles`
  - *Evaluated:* `shutil.copyfileobj` (blocks the async event loop), raw `os.write`, `aiofiles`.
  - *Why Selected:* `aiofiles` provides native async/await support for disk I/O, preventing the event loop from hanging while dumping massive 10GB file streams to disk.

---

## 4. Architectural Boundaries

### 4.1 Extract-Transform-Load (ETL) Separation
- **Requirement:** Avoid the "God Class" anti-pattern where a single service handles parsing, chunking, embeddings, and database persistence.
- **Implementation:** 
  - Create a dedicated `IngestionPipeline` (ETL orchestrator).
  - Reduce `StorageService` to a pure Data Access Object (DAO) that strictly handles SQL queries and transaction boundaries.

### 4.2 Deterministic Chunk Hashing
- **Requirement:** Chunk deduplication must support documents with identical paragraphs (e.g., repeated disclaimers on multiple pages).
- **Implementation:** The `chunk_id` UUID generation MUST incorporate the sequence `index` alongside the SHA-256 hash of the text to prevent hash collisions on duplicate text blocks.

---

## 5. Observability (SRE Standards)

### 5.1 Structured Logging
- **Requirement:** Terminal print logs are insufficient for Datadog or ELK Stack ingestion.
- **Implementation:** Use `python-json-logger` to output structured JSON logs in production environments, ensuring all log events contain timestamps, module names, and trace context.
- **Library Selection:** `python-json-logger`
  - *Evaluated:* `loguru` (heavy, complex formatting), `structlog` (excellent but complex setup), `python-json-logger`.
  - *Why Selected:* It plugs directly into Python's standard `logging` library, seamlessly overriding the formatter to output raw JSON out-of-the-box for Datadog/ELK with zero structural overhead.

### 5.2 Telemetry & Probes
- **Requirement:** Kubernetes must be able to automatically restart frozen pods and stop routing traffic to disconnected pods.
- **Implementation:**
  - Add `prometheus-fastapi-instrumentator` to expose a `/metrics` endpoint for latency and throughput tracking.
  - Implement `/health/liveness` (fast boolean check).
  - Implement `/health/readiness` (executes `SELECT 1` against PostgreSQL).
- **Library Selection:** `prometheus-fastapi-instrumentator`
  - *Evaluated:* Raw `prometheus_client` (requires manual middleware and route tracking), `prometheus-fastapi-instrumentator`.
  - *Why Selected:* Zero-config FastAPI integration. It automatically hooks into ASGI middleware to track latency, HTTP statuses, and throughput without polluting application business logic.
