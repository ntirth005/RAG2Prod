import uuid
import pytest
import httpx
from httpx import ASGITransport

from main import app
from core.database import init_db


@pytest.mark.asyncio
async def test_health_and_root_endpoints() -> None:
    """Verify health and root API endpoints."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        res_health = await async_client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "healthy"

        res_root = await async_client.get("/")
        assert res_root.status_code == 200
        assert "RAG2Prod" in res_root.text


@pytest.mark.asyncio
async def test_ingest_and_search_api_flow() -> None:
    """
    Integration test for POST /api/v1/documents/ingest and POST /api/v1/retrieval/search APIs.
    Skips live database operations if PostgreSQL is unreachable.
    """
    initialized = await init_db()
    if not initialized:
        pytest.skip("PostgreSQL database is unreachable. Skipping API integration tests.")

    test_doc_id = f"doc_api_test_{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        # 1. Ingest via API
        files = {"file": ("test_api_doc.txt", b"FastAPI provides fast REST API endpoints for RAG ingestion.", "text/plain")}
        data = {"doc_id": test_doc_id, "metadata_json": '{"author": "API Tester"}'}

        response = await async_client.post("/api/v1/documents/ingest", files=files, data=data)
        assert response.status_code == 201
        resp_data = response.json()
        assert resp_data["document_id"] == test_doc_id
        assert resp_data["filename"] == "test_api_doc.txt"
        assert resp_data["parent_chunks_count"] > 0

        # 2. Search via API
        search_payload = {
            "query_text": "What does FastAPI provide?",
            "top_k": 3,
            "score_threshold": 0.0,
            "filter": {
                "document_id": test_doc_id
            }
        }
        search_res = await async_client.post("/api/v1/retrieval/search", json=search_payload)
        assert search_res.status_code == 200
        search_data = search_res.json()
        assert search_data["total_retrieved"] > 0
        assert search_data["items"][0]["document_id"] == test_doc_id
