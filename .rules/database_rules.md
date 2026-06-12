# Database & Storage Rules

Guidelines for interacting with Postgres, Pgvector, and Knowledge Graphs.

## 1. Connection Management
* Always use async connection pools (`asyncpg` or SQLAlchemy async sessions) for Postgres. Never open/close single connections per request.

## 2. Pgvector & Embeddings
* Ensure all similarity searches use the HNSW index for sub-linear query times.
* Use cosine distance (`<=>`) for vector comparisons, matching the embedding model configuration.

## 3. GraphDB (Neo4j)
* Parametrize all Cypher queries to prevent injection attacks.
* Cache frequent graph queries to avoid database bottlenecks.
