import shutil
from pathlib import Path
from core.config import settings
from core.logger import info

class BaseObjectStorage:
    """Interface defining basic object storage interactions."""
    
    def upload_file(self, file_path: Path, destination_name: str) -> str:
        raise NotImplementedError

    def download_file(self, source_name: str, local_path: Path) -> None:
        raise NotImplementedError

    def delete_file(self, source_name: str) -> None:
        raise NotImplementedError

    def file_exists(self, source_name: str) -> bool:
        raise NotImplementedError


class LocalObjectStorage(BaseObjectStorage):
    """
    Mock object storage implementation using local disk directory.
    Stores raw files under settings.OBJECT_STORAGE_LOCAL_DIR.
    """
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir or settings.OBJECT_STORAGE_LOCAL_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def upload_file(self, file_path: Path, destination_name: str) -> str:
        """
        Uploads a file to local storage.
        Copies the file from file_path to the local base directory destination_name.
        Returns the resolved string path of the destination file.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Source file {file_path} does not exist.")
            
        dest_path = self.base_dir / destination_name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest_path)
        info("storage", f"Uploaded {file_path.name} → {destination_name}")
        return str(dest_path.resolve())

    def download_file(self, source_name: str, local_path: Path) -> None:
        """
        Downloads a file from local storage.
        Copies the file from the local storage mock back to local_path.
        """
        src_path = self.base_dir / source_name
        if not src_path.exists():
            raise FileNotFoundError(f"Source file {source_name} does not exist in storage.")
            
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, local_path)

    def delete_file(self, source_name: str) -> None:
        """Deletes a file from local storage."""
        src_path = self.base_dir / source_name
        if src_path.exists():
            src_path.unlink()

    def file_exists(self, source_name: str) -> bool:
        """Checks if a file exists in local storage."""
        return (self.base_dir / source_name).exists()
