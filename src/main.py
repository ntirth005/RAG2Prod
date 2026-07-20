import json
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import settings
from core.database import get_db_session
from core.storage_service import StorageService
from core.retriever import DenseRetriever
from core.generator import RAGPipeline
from core.models import Document
from core.schemas import (
    IngestionResponse,
    RetrievalQuery,
    RetrievalResult,
    QueryRequest,
    GenerationResult,
    DocumentItem,
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


@app.get(
    f"{settings.API_V1_STR}/documents",
    response_model=List[DocumentItem],
    status_code=status.HTTP_200_OK,
    tags=["Ingestion"],
)
async def list_documents(
    db: AsyncSession = Depends(get_db_session),
) -> List[DocumentItem]:
    """Retrieve all previously ingested documents from the database."""
    try:
        stmt = select(Document).order_by(Document.created_at.desc())
        result = await db.execute(stmt)
        docs = result.scalars().all()
        
        items = []
        for doc in docs:
            filename = doc.source_metadata.get("filename", doc.id)
            storage_path = doc.source_metadata.get("storage_path")
            pub_meta = {k: v for k, v in doc.source_metadata.items() if k not in ("filename", "storage_path")}
            
            items.append(
                DocumentItem(
                    document_id=doc.id,
                    filename=filename,
                    created_at=doc.created_at.isoformat(),
                    storage_path=storage_path,
                    metadata=pub_meta,
                )
            )
        return items
    except Exception as e:
        log_error("api", f"List documents error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {str(e)}",
        )


@app.delete(
    f"{settings.API_V1_STR}/documents/{{doc_id}}",
    status_code=status.HTTP_200_OK,
    tags=["Ingestion"],
)
async def delete_document_endpoint(
    doc_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a document, its file, and all associated parent/child chunks cascadingly."""
    try:
        service = StorageService(session=db)
        success = await service.delete_document(doc_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID '{doc_id}' not found.",
            )
        return {"status": "deleted", "document_id": doc_id}
    except HTTPException:
        raise
    except Exception as e:
        log_error("api", f"Delete document error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}",
        )


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


@app.post(
    f"{settings.API_V1_STR}/query",
    response_model=GenerationResult,
    status_code=status.HTTP_200_OK,
    tags=["Generation"],
)
async def query_rag(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Full RAG pipeline: retrieve → context engineering → LLM generation.
    If stream=true, returns Server-Sent Events (SSE) instead of JSON.
    """
    try:
        pipeline = RAGPipeline(session=db, provider=request.provider)

        if request.stream:
            return await _stream_response(pipeline, request)

        result = await pipeline.run(request)
        return result
    except Exception as e:
        log_error("api", f"Query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}",
        )


@app.post(
    f"{settings.API_V1_STR}/query/stream",
    tags=["Generation"],
)
async def query_rag_stream(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Dedicated SSE streaming endpoint for RAG query.
    Streams token-by-token and sends a final citation summary event.
    """
    try:
        pipeline = RAGPipeline(session=db, provider=request.provider)
        return await _stream_response(pipeline, request)
    except Exception as e:
        log_error("api", f"Stream query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stream query: {str(e)}",
        )


async def _stream_response(pipeline: RAGPipeline, request: QueryRequest) -> StreamingResponse:
    """Build an SSE StreamingResponse from the RAG pipeline."""
    token_stream, context, model_id, query_trace = await pipeline.run_stream(request)
    start_time = time.perf_counter()

    async def event_generator():
        try:
            # Emit query trace event first
            yield f"data: {json.dumps({'type': 'query_trace', 'query_trace': query_trace.model_dump()})}\n\n"

            async for token in token_stream:
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            # Send citation summary as final event
            latency = round((time.perf_counter() - start_time) * 1000, 1)
            citations_data = [c.model_dump() for c in context.citations]
            yield f"data: {json.dumps({'type': 'citations', 'citations': citations_data, 'model': model_id, 'latency_ms': latency, 'query_trace': query_trace.model_dump()})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            log_error("api", f"SSE stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
