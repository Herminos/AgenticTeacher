"""Management endpoints backed by LightRAG document status and chunks."""

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.telemetry import log_event
from app.schemas import RagChunkResponse, RagFileDetailResponse, RagFileResponse, RagSettingsResponse, RagSettingsUpdate
from app.services.lightrag_service import get_lightrag_service
from app.services.rag_registry import get_rag_registry

router = APIRouter(prefix="/rag", tags=["rag-management"])
registry = get_rag_registry()
lightrag = get_lightrag_service()


def _file_response(record: dict) -> RagFileResponse:
    return RagFileResponse.model_validate(record)


@router.get("/settings", response_model=RagSettingsResponse)
async def get_settings() -> RagSettingsResponse:
    return RagSettingsResponse(**registry.runtime_settings())


@router.put("/settings", response_model=RagSettingsResponse)
async def update_settings(payload: RagSettingsUpdate, request: Request) -> RagSettingsResponse:
    updated = registry.update_runtime_settings(payload.model_dump(exclude_none=True))
    log_event("rag_settings", request_id=request.state.request_id, stage="rag_settings", status="succeeded", **updated)
    return RagSettingsResponse(**updated)


@router.get("/indexes", response_model=list[RagFileResponse])
async def list_indexes(subject: str | None = Query(default=None, max_length=64)) -> list[RagFileResponse]:
    return [_file_response(item) for item in registry.list_files(subject)]


@router.get("/indexes/{file_id}", response_model=RagFileDetailResponse)
async def get_index(file_id: str, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)) -> RagFileDetailResponse:
    record = registry.get_file(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "RAG_FILE_NOT_FOUND", "message": "RAG file not found", "retryable": False})
    rows = await lightrag.list_chunks(str(record["source_id"]), record.get("subject"), offset, limit)
    chunks = [RagChunkResponse.model_validate(row) for row in rows]
    status = await lightrag.document_status(str(record["source_id"]), record.get("subject"))
    if status:
        record["status"] = status["status"]
        record["chunks"] = status["chunks"]
        # Child chunks are the LightRAG document units. Keep the registry
        # count synchronized after per-child deletion or a resumed operation.
        record["child_count"] = status["chunks"]
    return RagFileDetailResponse(**record, chunk_items=chunks, chunk_offset=offset, chunk_limit=limit)


@router.delete("/indexes/{file_id}/chunks/{chunk_id}")
async def delete_chunk(file_id: str, chunk_id: str, request: Request) -> dict:
    record = registry.get_file(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "RAG_FILE_NOT_FOUND", "message": "RAG file not found", "retryable": False})
    deleted = await lightrag.delete_chunk(str(record["source_id"]), chunk_id, record.get("subject"))
    if not deleted:
        raise HTTPException(status_code=404, detail={"code": "RAG_CHUNK_NOT_FOUND", "message": "RAG chunk not found", "retryable": False})
    record["chunks"] = max(0, int(record.get("chunks", 0)) - 1)
    record["child_count"] = max(0, int(record.get("child_count", record["chunks"] + 1)) - 1)
    if isinstance(record.get("child_ids"), dict):
        record["child_ids"].pop(chunk_id, None)
    registry.upsert_file(record)
    log_event("rag_chunk_delete", request_id=request.state.request_id, stage="rag_management", status="succeeded", file_id=file_id)
    return {"file_id": file_id, "chunk_id": chunk_id, "deleted": True}


@router.delete("/indexes/{file_id}")
async def delete_index(file_id: str, request: Request) -> dict:
    record = registry.get_file(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "RAG_FILE_NOT_FOUND", "message": "RAG file not found", "retryable": False})
    await lightrag.delete_document(str(record["source_id"]), record.get("subject"))
    registry.delete_file(file_id)
    log_event("rag_file_delete", request_id=request.state.request_id, stage="rag_management", status="succeeded", file_id=file_id)
    return {"file_id": file_id, "deleted": True}
