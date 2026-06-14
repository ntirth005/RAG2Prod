from fastapi.testclient import TestClient
from core.config import settings

def test_pytest_sanity() -> None:
    """
    Ensure that pytest runs and basic assertions work.
    """
    assert 1 + 1 == 2

def test_settings_sanity() -> None:
    """
    Verify configuration loaded settings fields properly.
    """
    assert settings.PROJECT_NAME == "RAG2Prod"
    assert settings.API_V1_STR == "/api/v1"
    assert settings.POSTGRES_DB == "rag2prod"

def test_health_endpoint(client: TestClient) -> None:
    """
    Test the FastAPI health check endpoint.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["project"] == "RAG2Prod"
