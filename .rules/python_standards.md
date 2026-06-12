# Python Coding Standards

All Python code implemented in this repository must adhere to the following guidelines:

## 1. Type Hinting
* Use explicit, strict type hints for all function signatures and variable declarations.
* Avoid using `Any` wherever possible. Prefer Union types or custom Pydantic types.
* Run type verification tools (like `mypy`) to ensure correct signatures.

## 2. Testing
* Every module in `src/` must have a corresponding test file in `tests/` named `test_<module_name>.py`.
* Use `pytest` and `pytest-asyncio` for asynchronous testing.
* Mock database connections and external API calls using pytest fixtures.

## 3. Code Quality
* Follow PEP 8 guidelines.
* Do not leave commented-out block code or developer test prints. Use the centralized logging system.

## 4. Interface-First Gating & Shared Schemas
* Before implementing module logic, define all shared models, schemas, and function signatures in `src/core/schemas.py`.
* Always import and inherit from these shared schemas. Do NOT write custom inline dictionaries or ad-hoc data models in service layers. This prevents interface drift across components.

