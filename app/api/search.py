from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..core.dependencies import get_current_user
from ..db.database import get_db
from ..db.models.user import User
from ..schemas.search import ContentSearchResult, ReindexResponse
from ..services.search_service import SearchService
from ..tasks.file_task import enqueue_file_index


router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=list[ContentSearchResult])
def search_content(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return SearchService(db).search(
        user=current_user,
        query=q,
        limit=limit,
    )


@router.post("/index/{file_id}", status_code=status.HTTP_202_ACCEPTED)
def index_file(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    SearchService(db).validate_index_request(
        file_id=file_id,
        user=current_user,
    )
    enqueue_file_index(file_id)
    return {"status": "queued", "file_id": str(file_id)}


@router.post(
    "/reindex-all",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReindexResponse,
)
def reindex_all_clean_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_ids = SearchService(db).reindexable_file_ids(user=current_user)
    for file_id in file_ids:
        enqueue_file_index(file_id)
    return ReindexResponse(status="queued", queued=len(file_ids))
