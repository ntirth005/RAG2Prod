from typing import Generator
import pytest
from fastapi.testclient import TestClient
from src.main import app

@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """
    Fixture providing a test client for the FastAPI app.
    """
    with TestClient(app) as c:
        yield c
