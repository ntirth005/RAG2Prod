# Observability & Logging Standards

All logging, tracing, and metric collection must adhere to the following rules:

## 1. Centralized Logging
* Never use raw `print()` statements for production code.
* Use Python's built-in `logging` library configured to output JSON formatted logs to `stdout`.
* Every log message must include:
  * `timestamp` (ISO 8601 format)
  * `log_level` (INFO, WARNING, ERROR, CRITICAL)
  * `module` (the module name)
  * `trace_id` (if available in the request context)

## 2. Distributed Tracing
* Propagate trace context using the W3C Trace Context standard.
* Extract `traceparent` and `tracestate` headers at the entrypoint of the API.
* Log execution time metrics (latency) for all DB queries, retriever calls, and LLM inferences.
