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

## 5. Git Commit Conventions
When proposing or executing commits, use Conventional Commit messages in the format `<type>(<scope>): <description>` (scope is optional and minimal):
* **`feat(<scope>)`**: Introducing new user-facing capabilities, routes, or modules (e.g., `feat(core): added microsoft and discord oauth`, `feat(prototype): add main app orchestrator...`).
* **`chore(<scope>)`**: Routine maintenance tasks such as updating dependencies (`pyproject.toml`), lockfiles (`uv.lock`), or configuring system parameters (e.g., `chore(config): update environment keys`).
* **`fix(<scope>)`**: Resolving validation issues, bug fixes, or framework quirks (e.g., `fix(auth): resolve cookie path boundary issue`).
* **`docs(<scope>)`**: Modifying or creating files containing instructional details (e.g., `docs: finalize project environment configurations`).
* **`refactor(<scope>)`**: Cleanups or adjustments to code structure that do not change external logic (e.g., `refactor(db): streamline pool initialization`).

