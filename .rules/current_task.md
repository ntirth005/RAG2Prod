# Active Stage: Stage 0 — Foundation & Project Setup

You are currently working on **Milestone 1: First Working RAG**, specifically **Stage 0**.

---

## Stage 0 Objectives
Prepare the repository workspace, configuration mechanisms, and dependency management systems so we have a clean, reproducible base for the RAG implementation.

## Task Checklist
- [x] **Establish Repository Folder Structure:**
  - Create `/src` directory for active code.
  - Create `/tests` directory for unit/integration tests.
  - Create configuration directory (e.g., `/config` or `/src/config`).
- [x] **Setup Configuration Management:**
  - Choose a configuration framework (e.g., `pydantic-settings` or Python `dotenv`).
  - Create a `.env.template` file with base config placeholders (API keys, Postgres URLs, Vector DB hosts).
- [x] **Verify Dependencies:**
  - Audit `requirements.txt` and ensure core libraries (`fastapi`, `uvicorn`, `pytest`, `pytest-asyncio`, `pydantic`) are ready for installation.
- [x] **Define Base Test Suite:**
  - Set up a dummy test (e.g., `tests/test_sanity.py`) to verify `pytest` works correctly on execution.

---

## Core Data Contracts / Configurations
No network communication data models are required for this stage. Only the settings container class needs to be defined:

```python
# Proposed Settings Schema (Pydantic Settings)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG2Prod"
    API_V1_STR: str = "/api/v1"
    
    # Database Configurations (Stage 2)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "rag2prod"
    
    # LLM Settings (Stage 5)
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    class Config:
        case_sensitive = True
        env_file = ".env"
```
