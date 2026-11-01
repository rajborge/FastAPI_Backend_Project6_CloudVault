import hashlib
import math
import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services.embedding_service import embed_text, model_name

from ..core.exceptions import FileNotFoundException, FileNotReadyException
from ..db.models.user import User
from ..repositories.file_repository import FileRepository


VECTOR_DIMENSIONS = 384


def hashed_text_vector(value: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float]:
    """Return a deterministic lightweight lexical vector.

    This is intentionally dependency-free. pgvector is still used for storage and
    similarity search, while exact phrase and PostgreSQL full-text ranking handle
    precise content queries. Replace this function later with a transformer
    embedding model if synonym-level semantic search is required.
    """
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9]+", value.lower())

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        index = raw % dimensions
        sign = 1.0 if (raw >> 8) & 1 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0:
        return vector

    return [component / norm for component in vector]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


class SearchService:
    def __init__(self, db: Session):
        self.db = db
        self.file_repository = FileRepository(db)

    def validate_index_request(self, *, file_id: UUID, user: User):
        file = self.file_repository.get_by_id_and_user(
            file_id=file_id,
            user_id=user.id,
        )
        if file is None:
            raise FileNotFoundException()
        if file.scan_status != "CLEAN":
            raise FileNotReadyException()
        return file

    def reindexable_file_ids(self, *, user: User) -> list[UUID]:
        """Return all clean, non-deleted files owned by the user.

        Re-indexing all clean files is deliberate: it is useful after changing
        extraction/vector logic and it also backfills files uploaded before the
        content-search pipeline existed.
        """
        statement = text(
            """
            SELECT f.id
            FROM files AS f
            WHERE f.user_id = :user_id
              AND f.is_deleted = FALSE
              AND f.version_of IS NULL
              AND f.scan_status = 'CLEAN'
            ORDER BY f.created_at ASC
            """
        )
        rows = self.db.execute(statement, {"user_id": user.id}).scalars().all()
        return [UUID(str(file_id)) for file_id in rows]

    def search(self, *, user: User, query: str, limit: int = 20) -> list[dict]:
        query = query.strip()
        if len(query) < 2:
            return []

        embedding = vector_literal(embed_text(query))

        statement = text(
            """
            WITH ranked AS (
                SELECT
                    f.id,
                    f.original_name,
                    f.mime_type,
                    f.size,
                    f.scan_status,
                    f.folder_id,
                    f.created_at,

                    (
                        POSITION(
                            LOWER(:query) IN LOWER(
                                COALESCE(f.original_name, '') ||
                                ' ' ||
                                COALESCE(s.extracted_text, '')
                            )
                        ) > 0
                    ) AS exact_phrase,

                    ts_rank_cd(
                        to_tsvector(
                            'english',
                            COALESCE(f.original_name, '') ||
                            ' ' ||
                            COALESCE(s.extracted_text, '')
                        ),
                        plainto_tsquery('english', :query)
                    ) AS text_score,

                    GREATEST(
                        0.0,
                        1.0 - (
                            s.embedding <=> CAST(:embedding AS vector)
                        )
                    ) AS vector_score,

                    ts_headline(
                        'english',
                        COALESCE(NULLIF(s.extracted_text, ''), f.original_name),
                        plainto_tsquery('english', :query),
                        'MaxWords=45, MinWords=12, MaxFragments=2, StartSel=<b>, StopSel=</b>'
                    ) AS snippet

                FROM file_search_documents AS s
                JOIN files AS f ON f.id = s.file_id
                WHERE f.user_id = :user_id
                  AND f.is_deleted = FALSE
              AND f.version_of IS NULL
                  AND f.scan_status = 'CLEAN'
                  AND s.embedding IS NOT NULL
                  AND s.embedding_model = :embedding_model
            )
            SELECT
                id,
                original_name,
                mime_type,
                size,
                scan_status,
                folder_id,
                created_at,

                CASE
                    WHEN exact_phrase THEN 1.0
                    WHEN text_score > 0 THEN
                        LEAST(
                            0.99,
                            0.70 +
                            LEAST(text_score, 1.0) * 0.20 +
                            LEAST(vector_score, 1.0) * 0.09
                        )
                    ELSE
                        LEAST(vector_score, 1.0) * 0.50
                END AS score,

                snippet
            FROM ranked
            WHERE exact_phrase = TRUE
               OR text_score > 0
               OR vector_score >= 0.15
            ORDER BY
                exact_phrase DESC,
                text_score DESC,
                vector_score DESC,
                created_at DESC
            LIMIT :limit
            """
        )

        rows = self.db.execute(
            statement,
            {
                "query": query,
                "embedding": embedding,
                "embedding_model": model_name(),
                "user_id": user.id,
                "limit": limit,
            },
        ).mappings().all()

        return [dict(row) for row in rows]
