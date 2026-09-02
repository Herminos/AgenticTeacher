import hashlib
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import get_settings


class FileService:
    async def save(self, upload: UploadFile, purpose: str) -> dict:
        settings = get_settings()
        if purpose not in {"answer_attachment", "ingest_source"}:
            raise ValueError("unsupported file purpose")
        allowed = {"image/png", "image/jpeg", "image/webp"}
        if purpose == "ingest_source":
            allowed |= {"application/pdf", "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
        if upload.content_type not in allowed:
            raise ValueError("unsupported MIME type")
        max_mb = settings.max_index_file_mb if purpose == "ingest_source" else settings.max_upload_mb
        max_bytes = max_mb * 1024 * 1024
        file_id = f"file_{uuid4().hex[:16]}"
        suffix = Path(upload.filename or "").suffix.lower() or mimetypes.guess_extension(upload.content_type or "") or ".bin"
        path = Path(settings.files_dir) / f"{file_id}{suffix}"
        digest_builder = hashlib.sha256()
        written = 0
        try:
            # Ingest sources may be as large as 10 GB; never buffer the whole
            # multipart body in the API process.
            with path.open("wb") as output:
                while True:
                    chunk = await upload.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError(f"file is too large; maximum is {max_mb} MB")
                    digest_builder.update(chunk)
                    output.write(chunk)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        digest = digest_builder.hexdigest()
        status = "queued" if purpose == "ingest_source" else "ready"
        return {
            "file_id": file_id,
            "status": status,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "job_id": f"job_{uuid4().hex[:12]}" if status == "queued" else None,
            "sha256": digest,
            "path": str(path),
        }
