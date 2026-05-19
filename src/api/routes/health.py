from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.limiter import limiter
from src.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
@limiter.limit("60/minute")
def health_check(request: Request, db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return HealthResponse(status="ok", db=db_status)
