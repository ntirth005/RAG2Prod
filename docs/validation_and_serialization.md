# Reference Guide: Schema Validation, Error Handling & Performance

This document outlines how schema validation (using Pydantic's `BaseModel`) works in our RAG pipeline, how validation errors are handled at runtime, and performance trade-offs.

---

## 1. Schema Validation & Runtime Errors

When incoming data violates type definitions in `src/core/schemas.py`, Pydantic raises a `ValidationError` exception at runtime. The application does not crash if these exceptions are managed correctly.

### Error Handling Strategies in the Pipeline

#### A. API Boundary (FastAPI Route Handling)
FastAPI automatically catches `ValidationError` exceptions at the routing layer.
* **Behavior:** Intercepts invalid requests and responds with an `HTTP 422 Unprocessable Entity` status code.
* **Response:** Returns a structured JSON detailing the missing or invalid fields to the client.

#### B. Ingestion & Internal Code (Manual Exception Catching)
For file ingestion, database loading, or configurations:
* **Behavior:** Wrap schema initialization in `try-except ValidationError` blocks.
* **Resolution:** Fall back to defaults, log warnings, or skip corrupt records rather than terminating the process.

#### C. LLM Structured Outputs (Self-Correction Loop)
When asking an LLM for structured outputs:
1. Try loading the output using `BaseModel.model_validate_json()`.
2. Catch any `ValidationError`.
3. Feed the error message back to the LLM and prompt it to correct the schema.

---

## 2. Validation & Serialization Performance

### Is Pydantic v2 Fast Enough?
**Yes.** Pydantic v2 is written in Rust (`pydantic-core`) and performs validation in **microseconds**. 

In RAG pipelines, latency is dominated by external calls:
* **LLM API:** 1,000 to 5,000 ms
* **Vector DB Lookup:** 10 to 100 ms
* **Network Latency:** 10 to 50 ms
* **Pydantic Validation:** < 0.1 ms (negligible)

### Performance Alternatives

| library | Type | Speed vs. Pydantic v2 | Trade-off |
| :--- | :--- | :--- | :--- |
| **`msgspec`** | JSON Validation (C-based) | 2x - 4x Faster | Extremely fast, but lacks deep FastAPI integration and rich metadata field features. |
| **`mashumaro`** | Dataclass Serialization | Slightly Faster | Compiles code at import time. Requires standard Python dataclasses. |
| **`dataclasses`** | Standard Library | Slightly Faster | Has **no** runtime validation (only types checked by static analyzers). |
