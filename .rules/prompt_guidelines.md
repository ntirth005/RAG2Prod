# Prompt Engineering & LLM Guidelines

Rules for prompt structuring, versioning, and guardrails.

## 1. System Prompt Isolation
* Always store system prompts as external config constants or template files, never inline in function logic.
* Use strict system instructions specifying the model's role, rules (e.g., "Answer only from context"), and response formats.

## 2. Structured Outputs
* Enforce structured output parsing using Pydantic schemas via JSON schema modes (e.g., OpenAI Structured Outputs or Gemini JSON Schema).

## 3. Context & Prompt Injection
* Sanitize user queries inside prompts to prevent adversarial instructions from bypassing validation checks.
