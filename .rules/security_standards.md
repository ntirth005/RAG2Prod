# Security & Access Control Standards

Guidelines for keeping the RAG pipeline secure and compliant.

## 1. PII Detection & Redaction
* Scan all raw user inputs for Personally Identifiable Information (PII) before ingestion or query understanding.
* Redact sensitive details (emails, phone numbers, SSNs) using local libraries (e.g., Microsoft Presidio) before forwarding queries to external LLMs.

## 2. API Keys & Secrets
* Never hardcode API keys or credentials. Use `env` variables validated through the Pydantic Settings class.

## 3. Authorization (RBAC)
* Always verify request authorization tokens against the Postgres DB roles.
* Enforce Row-Level Security (RLS) on document retrievals so users only retrieve chunks they have permissions to view.
