import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, Dict, Any

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db_session
from core.storage_service import StorageService
from core.retriever import DenseRetriever
from core.schemas import (
    IngestionResponse,
    RetrievalQuery,
    RetrievalResult,
)
from core.logger import info, error as log_error

from contextlib import asynccontextmanager
from core.database import get_db_session, init_db

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Initialize database schema & pgvector extension on startup."""
    info("app", "Starting up RAG2Prod FastAPI Server...")
    await init_db()
    yield
    info("app", "Shutting down RAG2Prod FastAPI Server...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": "0.1.0"
    }


@app.get("/", response_class=HTMLResponse, tags=["Root"])
async def root() -> HTMLResponse:
    """RAG2Prod Interactive Dashboard."""
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>RAG2Prod Engine API</h1><p>Visit <a href='/docs'>/docs</a> for API documentation.</p>")


@app.post(
    f"{settings.API_V1_STR}/documents/ingest",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Ingestion"],
)
async def ingest_document(
    file: UploadFile = File(...),
    doc_id: Optional[str] = Form(None),
    metadata_json: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_session),
) -> IngestionResponse:
    """
    Upload and ingest a document into Object Storage and Pgvector.
    Extracts text, creates parent-child chunks, generates embeddings, and saves to database.
    """
    metadata: Dict[str, Any] = {}
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid metadata_json string: {e}",
            )

    # Save uploaded bytes to a temporary file for parsing
    suffix = Path(file.filename).suffix if file.filename else ".txt"
    try:
        with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        service = StorageService(session=db)
        response = await service.ingest_file(
            file_path=tmp_path,
            doc_id=doc_id,
            metadata=metadata,
            original_filename=file.filename,
        )
        return response
    except Exception as e:
        log_error("api", f"Ingestion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest document: {str(e)}",
        )
    finally:
        if 'tmp_path' in locals() and tmp_path.exists():
            tmp_path.unlink()


@app.post(
    f"{settings.API_V1_STR}/retrieval/search",
    response_model=RetrievalResult,
    status_code=status.HTTP_200_OK,
    tags=["Retrieval"],
)
async def search_chunks(
    query: RetrievalQuery,
    db: AsyncSession = Depends(get_db_session),
) -> RetrievalResult:
    """
    Search indexed document chunks using dense vector similarity search (HNSW Cosine Distance)
    with optional JSONB metadata filtering.
    """
    try:
        retriever = DenseRetriever(session=db)
        results = await retriever.search(query)
        return results
    except Exception as e:
        log_error("api", f"Search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform search: {str(e)}",
        )
