from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base_model import BaseModel


class StorageBlob(BaseModel):
    __tablename__ = "storage_blobs"
    __table_args__ = (
        UniqueConstraint(
            "storage_backend",
            "content_sha256",
            name="uq_storage_blob_backend_sha256",
        ),
    )

    storage_backend: Mapped[str] = mapped_column(String(20), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
