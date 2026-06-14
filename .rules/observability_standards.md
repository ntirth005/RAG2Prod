# Observability & Logging Standards

All logging, tracing, and metric collection must adhere to the following rules:

## 1. Centralized Logging
* **No Raw Prints:** Never use raw `print()` statements in codebase modules.
* **Unified Logging API:** Use the centralized logging system defined in [logger.py](file:///home/ntirth005/Documents/RAG2Prod/src/core/logger.py). Import `get_logger`, `timer_step`, or `pipeline` from `core.logger`.
* **Standard Library Bypass:** Avoid invoking `logging.getLogger()` directly. All log statements must go through the configured `structlog` wrappers.
* **Dual-Channel Output:**
  * **Local CLI (Developer UX):** Outputs pretty-printed, colorized, and timed statements to standard console.
  * **Machine Logs (Agent / Aggregator UX):** Appends thread-safe, flat JSON lines format directly to the current run's log file (`logs/<date>/<time>/execution.log`).
* **Required Log Context Fields:** Every structured log record must include:
  * `timestamp` (ISO 8601 UTC timestamp format)
  * `level` (INFO, WARNING, ERROR, CRITICAL)
  * `module` (name of the subsystem generating the log, bound at logger retrieval)
  * `message` (clear, descriptive log message)
  * `trace_id` (when available in execution context/headers)
  * `duration_ms` / `status` (for any performance-tracked execution steps)

## 2. Distributed Tracing
* **W3C Context:** Propagate trace context using the W3C Trace Context standard.
* **Header Extraction:** Extract `traceparent` and `tracestate` headers at the entrypoint of the API.
* **Performance Timings:** Always wrap database queries, external API calls (e.g. LLM, OCR), and major parsing/chunking pipelines in `timer_step` context managers to log timing metrics.

