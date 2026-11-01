import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from ..core.exceptions import StorageQuotaExceededException

class StorageService:
    def __init__(self):

        self.upload_dir=Path("uploads")

        self.upload_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def generate_filename(
            self,
            filename:str,
    )->str:
        extension=Path(filename).suffix

        return f"{uuid4()}{extension}"
    
    def save_file(
            self,
            file:UploadFile,
            *,
            max_bytes:int | None=None,
    )->tuple[str,str,int,str]:
        
        stored_name=self.generate_filename(
            file.filename or "upload",
        )

        storage_path=self.upload_dir/stored_name
        size=0
        digest=hashlib.sha256()

        try:
            with storage_path.open("wb") as buffer:
                while chunk:=file.file.read(1024 * 1024):
                    if max_bytes is not None and size+len(chunk)>max_bytes:
                        raise StorageQuotaExceededException()

                    buffer.write(chunk)
                    digest.update(chunk)
                    size+=len(chunk)
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise

        return (
            stored_name,
            str(storage_path),
            size,
            digest.hexdigest(),
        )
    
    def get_file_path(
            self,
            storage_path:str,
    )->Path:
        return Path(storage_path)
    
    def delete_file(
            self,
            storage_path:str,
    ):
        path=Path(storage_path)

        if path.exists():
            path.unlink()