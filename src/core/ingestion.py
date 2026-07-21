import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

from core.models import ParentChunk, ChildChunk
from core.chunker import StructureAwareChunker
from core.embeddings import EmbeddingClient
from core.storage_service import StorageService
from core.parsers import parse_pdf_file, parse_html_content, parse_text_content
from core.schemas import IngestionResponse
from core.logger import info

class IngestionPipeline:
    """
    ETL Pipeline for document ingestion.
    Extracts text -> Transforms (chunks) -> Enriches (embeddings) -> Loads (StorageService)
    """
    def __init__(
        self,
        storage_service: StorageService,
        embedding_client: Optional[EmbeddingClient] = None,
        chunker: Optional[StructureAwareChunker] = None,
    ):
        self.storage = storage_service
        self.embedding_client = embedding_client or EmbeddingClient()
        self.chunker = chunker or StructureAwareChunker()

    async def ingest_file(
        self,
        file_path: Path,
        doc_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        original_filename: Optional[str] = None,
    ) -> IngestionResponse:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found for ingestion: {file_path}")

        doc_id = doc_id or f"doc_{uuid.uuid4().hex[:12]}"
        base_metadata = metadata or {}
        filename = original_filename or file_path.name

        info("ingestion", f"Starting ingestion for '{filename}' (doc_id={doc_id})")

        # 1. Upload raw file to Object Storage
        dest_filename = f"{doc_id}_{filename}"
        storage_path = self.storage.object_storage.upload_file(file_path, dest_filename)

        # 2. Extract Text
        extracted_text = ""
        ext = file_path.suffix.lower()
        pages = []

        if ext == ".pdf":
            pages = await parse_pdf_file(file_path)
            extracted_text = "\n\n".join([page["text"] for page in pages])
        elif ext in {".html", ".htm"}:
            raw_content = file_path.read_text(encoding="utf-8", errors="ignore")
            extracted_text = parse_html_content(raw_content)
        else:
            raw_content = file_path.read_text(encoding="utf-8", errors="ignore")
            extracted_text = parse_text_content(raw_content)

        if not extracted_text.strip():
            extracted_text = f"[Empty text content in document {filename}]"

        doc_metadata = {
            "filename": filename,
            "file_type": ext,
            "storage_path": storage_path,
            **base_metadata,
        }

        # 3. Transform: Structure-aware chunking
        if ext == ".pdf" and pages:
            chunk_results = []
            for p in pages:
                p_text = p["text"]
                p_raw = p.get("raw_text", p_text)
                if not p_text.strip():
                    p_text = f"[Empty page {p['page_number']} in document {filename}]"
                page_meta = {**doc_metadata, "page_number": p["page_number"]}
                chunk_results.extend(self.chunker.chunk_document(doc_id, p_text, page_meta, raw_text=p_raw))
        elif ext in {".html", ".htm"}:
            raw_content = file_path.read_text(encoding="utf-8", errors="ignore")
            extracted_text = parse_html_content(raw_content)
            chunk_results = self.chunker.chunk_document(doc_id, extracted_text, doc_metadata, raw_text=raw_content)
        else:
            raw_content = file_path.read_text(encoding="utf-8", errors="ignore")
            extracted_text = parse_text_content(raw_content)
            chunk_results = self.chunker.chunk_document(doc_id, extracted_text, doc_metadata, raw_text=raw_content)

        # Deduplicate parent & child chunks
        parent_records: Dict[str, ParentChunk] = {}
        unique_child_info: List[Dict[str, Any]] = []
        unique_child_ids = set()

        for c_info in chunk_results:
            p_id = c_info["parent_id"]
            c_id = c_info["chunk_id"]

            if p_id not in parent_records:
                parent_meta = {
                    **c_info["metadata"],
                    "start_char": c_info["metadata"].get("parent_start_char"),
                    "end_char": c_info["metadata"].get("parent_end_char"),
                    "start_line": c_info["metadata"].get("parent_start_line"),
                    "end_line": c_info["metadata"].get("parent_end_line"),
                }
                parent_records[p_id] = ParentChunk(
                    id=p_id,
                    document_id=doc_id,
                    text=c_info["parent_text"],
                    source_metadata=parent_meta,
                )

            if c_id not in unique_child_ids:
                unique_child_ids.add(c_id)
                unique_child_info.append(c_info)

        # 4. Enrich: Generate embeddings
        child_texts = [c["text"] for c in unique_child_info]
        embeddings = await self.embedding_client.get_embeddings(child_texts)

        child_records: List[ChildChunk] = [
            ChildChunk(
                id=c_info["chunk_id"],
                parent_id=c_info["parent_id"],
                document_id=doc_id,
                text=c_info["text"],
                embedding=emb,
                source_metadata=c_info["metadata"],
            )
            for c_info, emb in zip(unique_child_info, embeddings)
        ]

        # 5. Load: Database persistence
        await self.storage.save_document(
            doc_id=doc_id,
            doc_metadata=doc_metadata,
            parent_records=parent_records,
            child_records=child_records,
            dest_filename=dest_filename,
        )

        return IngestionResponse(
            document_id=doc_id,
            filename=filename,
            storage_path=storage_path,
            parent_chunks_count=len(parent_records),
            child_chunks_count=len(child_records),
        )
