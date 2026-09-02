import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.core.telemetry import log_event
from app.schemas import IndexResponse
from app.services.index_service import IndexService

router = APIRouter()
service = IndexService()


@router.post("/index", response_model=IndexResponse)
async def index_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    subject: str | None = Form("calculus"),
    hyde_count: int = Form(0),
) -> IndexResponse:
    try:
        return await service.index(files, subject, hyde_count, request.state.request_id)
    except TimeoutError as exc:
        log_event("rag_index", level=logging.ERROR, request_id=request.state.request_id, stage="index", status="failed")
        raise HTTPException(status_code=408, detail={"code": "INDEX_TIMEOUT", "message": str(exc), "retryable": True}) from exc
    except ValueError as exc:
        log_event("rag_index", level=logging.WARNING, request_id=request.state.request_id, stage="index", status="failed")
        status = 413 if "large" in str(exc) or "too many" in str(exc) else 422
        raise HTTPException(status_code=status, detail={"code": "INDEX_REJECTED", "message": str(exc), "retryable": False}) from exc
