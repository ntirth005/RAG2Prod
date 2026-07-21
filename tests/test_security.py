import pytest
import httpx
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from main import app
from core.models import Document
from sqlalchemy.ext.asyncio import AsyncSession

from main import app

@pytest.fixture
def client():
    with patch("main.init_db", new_callable=AsyncMock):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

@pytest.mark.asyncio
async def test_path_traversal_rejection_absolute_path(client):
    """Ensure that absolute path payloads like /etc/passwd are blocked"""
    
    mock_doc = Document(
        id="test-doc-123",
        source_metadata={"storage_path": "/etc/passwd"}
    )
    
    # Mock database get
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = mock_doc

    # Override the FastAPI dependency
    from core.database import get_db_session

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db

    response = client.get("/api/v1/documents/test-doc-123/file")
    
    # Should throw 404 since it's not relative to our base directory
    assert response.status_code == 404
    assert "not found in storage directory" in response.json()["detail"]
    
    # Clean up
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_path_traversal_rejection_relative_path(client):
    """Ensure that relative path payloads like ../../etc/passwd are blocked"""
    
    mock_doc = Document(
        id="test-doc-456",
        source_metadata={"storage_path": "../../../../../etc/passwd"}
    )
    
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.return_value = mock_doc

    from core.database import get_db_session

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db

    response = client.get("/api/v1/documents/test-doc-456/file")
    
    assert response.status_code == 404
    assert "not found in storage directory" in response.json()["detail"]
    
    app.dependency_overrides.clear()
