# Deployment & CI/CD Standards

Guidelines for containerizing and hosting the RAG application.

## 1. Containerization
* Use official, slim Python base images (e.g., `python:3.10-slim`).
* Multi-stage builds should be used to minimize final image size.
* Run containers as non-root users (`USER 1000`) to enforce security boundaries.

## 2. API Servers
* Run FastAPI apps using `uvicorn` or `gunicorn` with uvicorn workers.
* Expose a `/health` endpoint that checks:
  * Database connection health.
  * Vector store accessibility.
  * LLM API response state.

## 3. Environment Variables
* Declare all system configs in a `.env.template` file at the root.
* Check for missing critical environment variables at startup and crash early if they are absent.
