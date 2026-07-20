import pytest
from fastapi.testclient import TestClient

from main import app
from core.database import init_db

client = TestClient(app)


def test_health_and_root_endpoints() -> None:
    """Verify health and root API endpoints."""
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "Welcome" in res_root.json()["message"]


@pytest.mark.asyncio
async def test_ingest_and_search_api_flow() -> None:
    """
    Integration test for POST /api/v1/documents/ingest and POST /api/v1/retrieval/search APIs.
    Skips live database operations if PostgreSQL is unreachable.
    """
    initialized = await init_db()
    if not initialized:
        pytest.skip("PostgreSQL database is unreachable. Skipping API integration tests.")

    # 1. Ingest via API
    files = {"file": ("test_api_doc.txt", b"FastAPI provides fast REST API endpoints for RAG ingestion.", "text/plain")}
    data = {"doc_id": "doc_api_test_100", "metadata_json": '{"author": "API Tester"}'}

    response = client.post("/api/v1/documents/ingest", files=files, data=data)
    assert response.status_code == 201
    resp_data = response.json()
    assert resp_data["document_id"] == "doc_api_test_100"
    assert resp_data["filename"] == "test_api_doc.txt"
    assert resp_data["parent_chunks_count"] > 0

    # 2. Search via API
    search_payload = {
        "query_text": "What does FastAPI provide?",
        "top_k": 3,
        "score_threshold": 0.0,
        "filter": {
            "document_id": "doc_api_test_100"
        }
    }
    search_res = client.post("/api/v1/retrieval/search", json=search_payload)
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total_retrieved"] > 0
    assert search_data["items"][0]["document_id"] == "doc_api_test_100"
