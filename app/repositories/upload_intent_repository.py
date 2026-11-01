from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models.upload_intent import UploadIntent


class UploadIntentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, intent: UploadIntent) -> UploadIntent:
        self.db.add(intent)
        return intent

    def get_for_user_for_update(
        self,
        *,
        intent_id: UUID,
        user_id: UUID,
    ) -> UploadIntent | None:
        statement = (
            select(UploadIntent)
            .where(
                UploadIntent.id == intent_id,
                UploadIntent.user_id == user_id,
            )
            .with_for_update()
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_expired_open(self, *, now: datetime) -> list[UploadIntent]:
        statement = select(UploadIntent).where(
            UploadIntent.status == "OPEN",
            UploadIntent.expires_at <= now,
        )
        return list(self.db.execute(statement).scalars().all())
