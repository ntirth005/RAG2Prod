# API Design Standards

Guidelines for implementing FastAPI endpoints.

## 1. Routing & Versioning
* Prefix all routes with version numbers (e.g., `/api/v1/query`, `/api/v1/ingest`).
* Use plural nouns for resource paths (e.g., `/api/v1/documents`, not `/api/v1/document`).

## 2. Response Codes
* Successful GET/PUT/PATCH calls: return `200 OK`.
* Successful POST creation calls: return `201 Created`.
* Authentication failures: return `401 Unauthorized`.
* Access control failures: return `403 Forbidden`.
* Missing resources: return `404 Not Found`.
* Unhandled server errors: return `500 Internal Server Error`.

## 3. Error Schemas
* All errors must return a consistent payload:
  ```json
  {
    "detail": {
      "error_code": "string_identifier",
      "message": "Human readable message"
    }
  }
  ```
