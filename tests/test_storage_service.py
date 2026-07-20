import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from sqlalchemy import select

from core.database import init_db, async_session_maker
from core.storage_service import StorageService
from core.object_storage import LocalObjectStorage
from core.models import ChildChunk


@pytest.mark.asyncio
async def test_storage_service_ingestion_and_deletion() -> None:
    """
    Integration test verifying end-to-end ingestion pipeline via StorageService.
    Skips if live PostgreSQL database is unreachable.
    """
    initialized = await init_db()
    if not initialized:
        pytest.skip("PostgreSQL database is unreachable. Skipping StorageService integration test.")

    with TemporaryDirectory() as temp_dir:
        # Create a sample text file
        doc_file = Path(temp_dir) / "sample_doc.txt"
        doc_file.write_text(
            "# Chapter 1: Introduction\n\n"
            "Retrieval-Augmented Generation bridges LLMs with domain knowledge.\n\n"
            "```python\ndef hello():\n    print('world')\n```\n\n"
            "| Feature | Status |\n| --- | --- |\n| Chunking | Done |\n",
            encoding="utf-8",
        )

        obj_storage = LocalObjectStorage(base_dir=str(Path(temp_dir) / "storage"))

        async with async_session_maker() as session:
            service = StorageService(session=session, object_storage=obj_storage)

            # Test Ingestion
            response = await service.ingest_file(
                file_path=doc_file,
                doc_id="test_service_doc_1",
                metadata={"author": "Unit Tester", "domain": "RAG"},
            )

            assert response.document_id == "test_service_doc_1"
            assert response.filename == "sample_doc.txt"
            assert response.parent_chunks_count > 0
            assert response.child_chunks_count > 0
            assert Path(response.storage_path).exists()

            # Test Deletion
            deleted = await service.delete_document("test_service_doc_1")
            assert deleted is True
            assert not Path(response.storage_path).exists()


@pytest.mark.asyncio
async def test_repeating_chunks_deduplication() -> None:
    """
    Integration test verifying that repeating text chunks within a document are deduplicated
    and stored only ONCE in the database.
    """
    initialized = await init_db()
    if not initialized:
        pytest.skip("PostgreSQL database is unreachable. Skipping deduplication test.")

    with TemporaryDirectory() as temp_dir:
        repeating_file = Path(temp_dir) / "repeating_doc.txt"
        # Repeating footer block on multiple pages
        repeating_file.write_text(
            "Page 1 content.\n\nPlacement Confidential Footer 2026\n\n"
            "Page 2 content.\n\nPlacement Confidential Footer 2026\n\n"
            "Page 3 content.\n\nPlacement Confidential Footer 2026\n",
            encoding="utf-8",
        )

        async with async_session_maker() as session:
            service = StorageService(session=session)
            response = await service.ingest_file(
                file_path=repeating_file,
                doc_id="doc_dedup_test",
            )

            # Verify ChildChunk records in DB for repeating footer
            stmt = select(ChildChunk).where(
                ChildChunk.document_id == "doc_dedup_test",
                ChildChunk.text.contains("Placement Confidential Footer 2026"),
            )
            result = await session.execute(stmt)
            matching_chunks = result.scalars().all()

            # The repeating footer text must be stored ONLY ONCE in the database
            assert len(matching_chunks) == 1

            await service.delete_document("doc_dedup_test")
