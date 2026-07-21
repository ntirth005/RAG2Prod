import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from core.storage_service import StorageService
from core.object_storage import LocalObjectStorage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

@pytest.mark.asyncio
async def test_rollback_and_cleanup_on_db_failure(tmp_path):
    """
    Ensure that if the DB commit fails during ingestion, 
    the system rolls back and deletes the orphaned file from disk.
    """
    
    # 1. Setup mock session that raises an IntegrityError on commit
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.commit.side_effect = IntegrityError("statement", "params", "orig")
    mock_session.get.return_value = None  # Ensure it doesn't trigger delete_document
    
    # 2. Setup mock object storage
    mock_object_storage = MagicMock(spec=LocalObjectStorage)
    mock_object_storage.delete_file = MagicMock()
    
    # 3. Initialize StorageService
    service = StorageService(session=mock_session, object_storage=mock_object_storage)
    
    # 4. Execute - it should raise the IntegrityError eventually (after Tenacity retries)
    with pytest.raises(IntegrityError):
        await service.save_document(
            doc_id="test-doc-999",
            doc_metadata={"filename": "dummy.txt"},
            parent_records={},
            child_records=[],
            dest_filename="mock_dest.txt"
        )
        
    # 6. Assertions
    # It should have called rollback at least once for each retry attempt
    assert mock_session.rollback.called
    
    # It should have attempted to delete the orphaned file from object storage 
    # as part of the rollback sequence to prevent disk leak.
    mock_object_storage.delete_file.assert_called_with("mock_dest.txt")
