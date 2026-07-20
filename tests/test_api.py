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


@pytest.mark.asyncio
async def test_list_and_delete_documents_api() -> None:
    """Verify listing and deleting documents via REST API."""
    initialized = await init_db()
    if not initialized:
        pytest.skip("PostgreSQL database is unreachable. Skipping API integration tests.")

    test_doc_id = f"doc_api_test_{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        # 1. Ingest document
        files = {"file": ("test_api_doc.txt", b"Mock document content for list and delete testing.", "text/plain")}
        data = {"doc_id": test_doc_id, "metadata_json": '{"tag": "temp"}'}
        ingest_res = await async_client.post("/api/v1/documents/ingest", files=files, data=data)
        assert ingest_res.status_code == 201

        # 2. List documents
        list_res = await async_client.get("/api/v1/documents")
        assert list_res.status_code == 200
        docs = list_res.json()
        assert len(docs) > 0
        
        # Verify our document is in the list
        matched_doc = next((d for d in docs if d["document_id"] == test_doc_id), None)
        assert matched_doc is not None
        assert matched_doc["filename"] == "test_api_doc.txt"

        # 3. Delete document
        del_res = await async_client.delete(f"/api/v1/documents/{test_doc_id}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        # Verify it's gone
        list_res_after = await async_client.get("/api/v1/documents")
        docs_after = list_res_after.json()
        assert not any(d["document_id"] == test_doc_id for d in docs_after)


@pytest.mark.asyncio
async def test_get_document_file_api() -> None:
    """Verify downloading original document files via REST API."""
    initialized = await init_db()
    if not initialized:
        pytest.skip("PostgreSQL database is unreachable. Skipping API integration tests.")

    test_doc_id = f"doc_api_test_{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        # 1. Ingest document
        files = {"file": ("test_api_doc.txt", b"Mock document content for file retrieval testing.", "text/plain")}
        data = {"doc_id": test_doc_id, "metadata_json": '{"tag": "download"}'}
        ingest_res = await async_client.post("/api/v1/documents/ingest", files=files, data=data)
        assert ingest_res.status_code == 201

        # 2. Get file
        file_res = await async_client.get(f"/api/v1/documents/{test_doc_id}/file")
        assert file_res.status_code == 200
        assert file_res.headers["content-type"] == "text/plain; charset=utf-8"
        assert b"Mock document content for file retrieval testing." in file_res.content

        # Clean up
        await async_client.delete(f"/api/v1/documents/{test_doc_id}")


@pytest.mark.asyncio
async def test_batch_ingest_documents_api() -> None:
    """Verify batch ingesting multiple documents via POST /api/v1/documents/ingest/batch."""
    initialized = await init_db()
    if not initialized:
        pytest.skip("PostgreSQL database is unreachable. Skipping API integration tests.")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        files = [
            ("files", ("batch_doc1.txt", b"First document in batch ingestion.", "text/plain")),
            ("files", ("batch_doc2.txt", b"Second document in batch ingestion with more details.", "text/plain")),
        ]
        data = {"metadata_json": '{"batch": "test_run"}'}

        response = await async_client.post("/api/v1/documents/ingest/batch", files=files, data=data)
        assert response.status_code == 201
        res_data = response.json()
        assert res_data["total_files"] == 2
        assert res_data["successful"] == 2
        assert res_data["failed"] == 0
        assert len(res_data["results"]) == 2

        # Clean up created docs
        for item in res_data["results"]:
            await async_client.delete(f"/api/v1/documents/{item['document_id']}")

