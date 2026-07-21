import json
import time
import aiofiles
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import settings
from core.database import get_db_session
from core.storage_service import StorageService
from core.ingestion import IngestionPipeline
from core.retriever import DenseRetriever
from core.generator import RAGPipeline
from core.models import Document
from core.schemas import (
    IngestionResponse,
    BatchIngestionResponse,
    RetrievalQuery,
    RetrievalResult,
    QueryRequest,
    GenerationResult,
    DocumentItem,
)
from core.logger import info, error as log_error

from contextlib import asynccontextmanager
from core.database import get_db_session, init_db, async_session_maker
import asyncio
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Initialize database schema & pgvector extension on startup."""
    info("app", "Starting up RAG2Prod FastAPI Server...")
    await init_db()
    instrumentator.expose(app_instance)
    yield
    info("app", "Shutting down RAG2Prod FastAPI Server...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

instrumentator = Instrumentator().instrument(app)


@app.get("/health/liveness", tags=["Health"])
async def liveness_probe() -> dict[str, str]:
    """Basic liveness probe indicating process is running."""
    return {"status": "alive"}

@app.get("/health/readiness", tags=["Health"])
async def readiness_probe(db: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    """Readiness probe checking database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        log_error("health", f"Readiness probe failed: {e}")
        raise HTTPException(status_code=503, detail="Database is unavailable")


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
            tmp_path = Path(tmp.name)
            
        async with aiofiles.open(tmp_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):
                await out_file.write(content)

        service = StorageService(session=db)
        pipeline = IngestionPipeline(storage_service=service)
        response = await pipeline.ingest_file(
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
    f"{settings.API_V1_STR}/documents/ingest/batch",
    response_model=BatchIngestionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Ingestion"],
)
async def ingest_documents_batch(
    files: List[UploadFile] = File(...),
    metadata_json: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_session),
) -> BatchIngestionResponse:
    """
    Upload and ingest multiple documents concurrently in a single batch request.
    Extracts text, creates parent-child chunks, generates embeddings, and saves all documents.
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

    async def process_single_file(file: UploadFile) -> Dict[str, Any]:
        suffix = Path(file.filename).suffix if file.filename else ".txt"
        tmp_path = None
        try:
            with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp_path = Path(tmp.name)
                
            async with aiofiles.open(tmp_path, 'wb') as out_file:
                while content := await file.read(1024 * 1024):
                    await out_file.write(content)

            async with async_session_maker() as session:
                service = StorageService(session=session)
                pipeline = IngestionPipeline(storage_service=service)
                response = await pipeline.ingest_file(
                    file_path=tmp_path,
                    metadata=metadata,
                    original_filename=file.filename,
                )
                return {"success": True, "response": response}
        except Exception as e:
            log_error("api", f"Batch ingestion error for {file.filename}: {e}")
            return {"success": False, "filename": file.filename or "unknown", "error": str(e)}
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    tasks = [process_single_file(file) for file in files]
    task_results = await asyncio.gather(*tasks)

    results: List[IngestionResponse] = []
    errors: List[Dict[str, str]] = []

    for res in task_results:
        if res["success"]:
            results.append(res["response"])
        else:
            errors.append({"filename": res["filename"], "error": res["error"]})

    return BatchIngestionResponse(
        total_files=len(files),
        successful=len(results),
        failed=len(errors),
        results=results,
        errors=errors,
    )



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


@app.get(
    f"{settings.API_V1_STR}/documents/{{doc_id}}/file",
    tags=["Ingestion"],
)
async def get_document_file(
    doc_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieve the original PDF or text document file from object storage."""
    try:
        doc = await db.get(Document, doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID '{doc_id}' not found.",
            )

        storage_path_rel = doc.source_metadata.get("storage_path")
        if not storage_path_rel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Storage path reference not found in metadata.",
            )

        base_dir = Path(settings.OBJECT_STORAGE_LOCAL_DIR).resolve()
        
        # Try relative to base dir first
        file_path = (base_dir / Path(storage_path_rel)).resolve()
        if not file_path.is_relative_to(base_dir) or not file_path.exists():
            # Try filename only fallback securely
            file_path = (base_dir / Path(storage_path_rel).name).resolve()
            if not file_path.is_relative_to(base_dir) or not file_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Physical document file not found in storage directory.",
                )

        filename = doc.source_metadata.get("filename", doc_id)
        
        media_type = "application/octet-stream"
        if file_path.suffix.lower() == ".pdf":
            media_type = "application/pdf"
        elif file_path.suffix.lower() in (".html", ".htm"):
            media_type = "text/html"
        elif file_path.suffix.lower() in (".txt", ".md"):
            media_type = "text/plain"

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=filename,
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error("api", f"Fetch document file error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch document file: {str(e)}",
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
