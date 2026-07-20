# Active Stage: Stage 4 & 5 — Context Engineering + Generation Layer Complete

You have completed **Milestone 2 (first half):** **Stage 4: Context Engineering** and **Stage 5: Generation Layer**.

---

## Stage 4 & 5 Objectives
Build the context engineering pipeline (citation indexing, token-budget truncation, prompt assembly) and generation layer (multi-provider LLM client, SSE streaming, RAG pipeline orchestrator) to transform raw vector search results into fluent, cited answers.

---

## Task Checklist
- [x] **Context Engineering Schemas:**
  - Add `CitationSource`, `FormattedContext`, `PromptPayload`, `TokenUsage`, `GenerationResult`, `QueryRequest` to `src/core/schemas.py`.
- [x] **Config Updates:**
  - Add DeepSeek + OpenAI provider settings, LLM generation parameters to `src/core/config.py` and `.env`.
- [x] **System Prompt Constants:**
  - Create `src/core/prompts.py` with externalized RAG system prompt, context template, and fallback messages.
- [x] **Context Builder Module:**
  - Create `src/core/context_builder.py` with `ContextBuilder` (token truncation), `PromptBuilder` (prompt assembly), and `CitationMapper` (parent dedup + citation indexing).
- [x] **Generator Module:**
  - Create `src/core/generator.py` with multi-provider `LLMClient` (DeepSeek + OpenAI via OpenAI-compatible API), mock fallback, and `RAGPipeline` orchestrator.
- [x] **REST API Endpoints:**
  - Add `POST /api/v1/query` (JSON or SSE) and `POST /api/v1/query/stream` (dedicated SSE) to `src/main.py`.
- [x] **Dashboard Upgrade:**
  - Add "Ask RAG2Prod" Q&A panel with SSE streaming animation, [Source N] clickable badges, expandable source cards with highlighted text snippets, and provider toggle.
- [x] **Test Suites:**
  - Create `tests/test_context_builder.py` (11 tests) and `tests/test_generator.py` (9 tests).
  - All 42 tests passing across full suite.
- [x] **Current Task Update:**
  - Update `.rules/current_task.md` with Stage 4 & 5 checklist.
