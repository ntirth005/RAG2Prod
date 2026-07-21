import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.models import Document, ParentChunk, ChildChunk
from core.object_storage import BaseObjectStorage, LocalObjectStorage
from core.logger import info, error as log_error

class StorageService:
    """
    Data Access Object (DAO) exclusively for object storage persistence
    and relational vector database insertions/deletions.
    """

    def __init__(
        self,
        session: AsyncSession,
        object_storage: Optional[BaseObjectStorage] = None,
    ):
        self.session = session
        self.object_storage = object_storage or LocalObjectStorage()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(IntegrityError),
        reraise=True
    )
    async def save_document(
        self,
        doc_id: str,
        doc_metadata: Dict[str, Any],
        parent_records: Dict[str, ParentChunk],
        child_records: List[ChildChunk],
        dest_filename: str,
    ) -> None:
        """Saves chunks into PostgreSQL using an atomic transaction."""
        
        # If document already exists, remove previous version for clean re-ingestion
        existing_doc = await self.session.get(Document, doc_id)
        if existing_doc:
            info("storage_service", f"Document '{doc_id}' already exists — overwriting previous version.")
            await self.delete_document(doc_id)

        try:
            doc = Document(id=doc_id, source_metadata=doc_metadata)
            self.session.add(doc)
    
            for p_obj in parent_records.values():
                self.session.add(p_obj)
    
            for c_obj in child_records:
                self.session.add(c_obj)
    
            await self.session.commit()
            info(
                "storage_service",
                f"Successfully saved '{doc_id}' to DB: {len(parent_records)} parents, {len(child_records)} children.",
            )
        except Exception as e:
            await self.session.rollback()
            # Clean up object storage to prevent leak
            log_error("storage_service", f"Database commit failed: {e}. Rolling back and deleting {dest_filename}")
            try:
                self.object_storage.delete_file(dest_filename)
            except Exception as del_err:
                log_error("storage_service", f"Failed to delete orphaned file {dest_filename}: {del_err}")
            raise e

    async def delete_document(self, doc_id: str) -> bool:
        """Deletes a document and its associated parent/child chunks via cascading delete."""
        doc = await self.session.get(Document, doc_id)
        if not doc:
            return False

        # If object storage reference exists, attempt removal
        storage_path = doc.source_metadata.get("storage_path")
        if storage_path:
            try:
                dest_name = Path(storage_path).name
                self.object_storage.delete_file(dest_name)
            except Exception as e:
                log_error("storage_service", f"Could not delete storage file: {e}")

        await self.session.delete(doc)
        await self.session.commit()
        return True
