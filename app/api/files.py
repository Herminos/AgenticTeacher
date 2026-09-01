from fastapi import APIRouter, File, Form, UploadFile

from app.services.file_service import FileService

router = APIRouter()
service = FileService()


@router.post("/files")
async def upload_file(file: UploadFile = File(...), purpose: str = Form("answer_attachment")) -> dict:
    try:
        return await service.save(file, purpose)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=413 if "large" in str(exc) else 422, detail={"code": "FILE_REJECTED", "message": str(exc), "retryable": False}) from exc
