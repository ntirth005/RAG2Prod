import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from sqlalchemy import select, text
from core.config import settings
from core.database import init_db, async_session_maker, engine
from core.models import Document, ParentChunk, ChildChunk
from core.object_storage import LocalObjectStorage

# --- Object Storage Tests ---

def test_local_object_storage() -> None:
    """Verifies that LocalObjectStorage successfully uploads, checks, downloads, and deletes files."""
    with TemporaryDirectory() as temp_dir:
        # Create temp source directory and source file
        src_dir = Path(temp_dir) / "source"
        src_dir.mkdir()
        src_file = src_dir / "test_doc.txt"
        src_file.write_text("Hello, Object Storage!", encoding="utf-8")

        storage_dir = Path(temp_dir) / "storage"
        download_dir = Path(temp_dir) / "download"
        download_dir.mkdir()
        download_file = download_dir / "downloaded.txt"

        # Initialize mock storage
        storage = LocalObjectStorage(base_dir=str(storage_dir))
        dest_name = "test_doc_dest.txt"

        # Test upload
        storage.upload_file(src_file, dest_name)
        assert storage.file_exists(dest_name) is True

        # Test download
        storage.download_file(dest_name, download_file)
        assert download_file.exists() is True
        assert download_file.read_text(encoding="utf-8") == "Hello, Object Storage!"

        # Test delete
        storage.delete_file(dest_name)
        assert storage.file_exists(dest_name) is False


# --- Database & Vector Search Tests ---

@pytest.mark.asyncio
async def test_database_and_vector_operations() -> None:
    """
    Verifies database CRUD, pgvector Cosine similarity search, and cascading deletes.
    Gracefully skips if PostgreSQL/pgvector is not reachable.
    """
    # Attempt DB initialization
    initialized = await init_db()
    
    # If database initialization failed (Postgres not running), skip the integration tests
    if not initialized:
        pytest.skip("PostgreSQL database is not reachable. Skipping live database and pgvector integration tests.")

    async with async_session_maker() as session:
        # Clean any existing test records
        await session.execute(text("TRUNCATE TABLE documents CASCADE;"))
        await session.commit()

        # 1. Insert Document
        doc_id = "doc_test_123"
        doc = Document(id=doc_id, source_metadata={"filename": "test.pdf", "author": "Tester"})
        session.add(doc)
        await session.commit()

        # Retrieve and verify document
        db_doc = await session.get(Document, doc_id)
        assert db_doc is not None
        assert db_doc.source_metadata["filename"] == "test.pdf"

        # 2. Insert Parent Chunk
        parent_id = "parent_test_123"
        parent = ParentChunk(
            id=parent_id,
            document_id=doc_id,
            text="This is the parent text block representing a large paragraph.",
            source_metadata={"section": "introduction"}
        )
        session.add(parent)
        await session.commit()

        # Retrieve and verify parent chunk
        db_parent = await session.get(ParentChunk, parent_id)
        assert db_parent is not None
        assert db_parent.text == "This is the parent text block representing a large paragraph."
        assert db_parent.document_id == doc_id

        # 3. Insert Child Chunk with Embeddings
        child_id = "child_test_123"
        embedding_dim = settings.EMBEDDING_DIMENSION
        mock_embedding = [0.1] * embedding_dim

        child = ChildChunk(
            id=child_id,
            parent_id=parent_id,
            document_id=doc_id,
            text="representing a large paragraph.",
            embedding=mock_embedding,
            source_metadata={"page": 1}
        )
        session.add(child)
        await session.commit()

        # Retrieve and verify child chunk
        db_child = await session.get(ChildChunk, child_id)
        assert db_child is not None
        assert len(db_child.embedding) == embedding_dim
        assert db_child.parent_id == parent_id

        # 4. Perform vector similarity query using Cosine Distance (<=> / .cosine_distance)
        query_vector = mock_embedding
        stmt = (
            select(ChildChunk)
            .order_by(ChildChunk.embedding.cosine_distance(query_vector))
            .limit(1)
        )
        result = await session.execute(stmt)
        closest_chunk = result.scalar_one_or_none()
        
        assert closest_chunk is not None
        assert closest_chunk.id == child_id

        # 5. Verify cascading deletion (deleting document deletes parent and child chunks)
        await session.delete(doc)
        await session.commit()

        db_parent_after = await session.get(ParentChunk, parent_id)
        db_child_after = await session.get(ChildChunk, child_id)
        
        assert db_parent_after is None
        assert db_child_after is None
