import os
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

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
    )->tuple[str,str]:
        
        stored_name=self.generate_filename(
            file.filename,
        )

        storage_path=self.upload_dir/stored_name

        with storage_path.open("wb") as buffer:
            shutil.copyfileobj(
                file.file,
                buffer,
            )

        return (
            stored_name,
            str(storage_path),
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