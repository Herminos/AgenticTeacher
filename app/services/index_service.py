"""Server-side document indexing for browser-uploaded files."""

import asyncio
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from time import perf_counter
from uuid import uuid4

from fastapi import UploadFile

from app.config import get_settings
from app.core.telemetry import log_event
from app.schemas import IndexResponse, IndexedFileResult
from app.services.qdrant_service import QdrantService
from ingest import build_rows


_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


def _safe_relative_name(filename: str | None, fallback: str) -> str:
    raw = (filename or "").replace("\\", "/")
    parts = [part for part in PurePosixPath(raw).parts if part not in {"", ".", ".."}]
    safe_parts = [re.sub(r"[^\w.\-\u4e00-\u9fff ]", "_", part) for part in parts]
    return "/".join(safe_parts) or fallback


class IndexService:
    def __init__(self, qdrant: QdrantService | None = None) -> None:
        self.qdrant = qdrant or QdrantService()

    async def index(
        self,
        uploads: list[UploadFile],
        subject: str | None,
        hyde_count: int = 0,
        request_id: str | None = None,
    ) -> IndexResponse:
        settings = get_settings()
        started = perf_counter()
        index_id = f"idx_{uuid4().hex[:12]}"
        hyde_count = max(0, min(3, int(hyde_count)))
        if not uploads:
            raise ValueError("at least one file is required")
        if len(uploads) > settings.max_index_files:
            raise ValueError(f"too many files; maximum is {settings.max_index_files}")

        collection = settings.collection_for(subject)
        file_limit = settings.max_index_file_mb * 1024 * 1024
        total_limit = settings.max_index_total_mb * 1024 * 1024
        temp_root = Path(tempfile.mkdtemp(prefix=f"{index_id}_", dir=settings.files_dir))
        written: list[tuple[str, Path]] = []
        total_bytes = 0
        try:
            for number, upload in enumerate(uploads, start=1):
                name = _safe_relative_name(upload.filename, f"upload_{number}.bin")
                suffix = Path(name).suffix.lower()
                expected_mime = _MIME_BY_SUFFIX.get(suffix)
                if expected_mime is None:
                    raise ValueError(f"unsupported file type: {name}")
                if upload.content_type not in {None, "", expected_mime}:
                    raise ValueError(f"MIME type does not match filename: {name}")
                target = temp_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                # Stream to disk instead of reading the whole upload into RAM.
                # This is required for the 10 GB per-file limit and also keeps
                # concurrent indexing requests from exhausting the API process.
                file_bytes = 0
                with target.open("wb") as output:
                    while True:
                        chunk = await upload.read(8 * 1024 * 1024)
                        if not chunk:
                            break
                        file_bytes += len(chunk)
                        total_bytes += len(chunk)
                        if file_bytes > file_limit:
                            raise ValueError(f"file is too large: {name}; maximum is {settings.max_index_file_mb} MB")
                        if total_bytes > total_limit:
                            raise ValueError(f"total upload is too large; maximum is {settings.max_index_total_mb} MB")
                        output.write(chunk)
                written.append((name, target))

            timeout = max(1, settings.index_timeout_ms) / 1000
            rows = await asyncio.wait_for(
                asyncio.to_thread(build_rows, temp_root, hyde_count),
                timeout=timeout,
            )
            added = await asyncio.wait_for(self.qdrant.upsert(collection, rows), timeout=timeout)
            counts = Counter(str(row["metadata"].get("filename", "")) for row in rows)
            file_results = [
                IndexedFileResult(filename=name, chunks=counts.get(Path(name).name, 0), status="indexed")
                for name, _ in written
            ]
            duration_ms = round((perf_counter() - started) * 1000, 2)
            log_event(
                "rag_index",
                request_id=request_id,
                stage="index",
                status="succeeded",
                duration_ms=duration_ms,
                subject=subject,
                candidate_count=len(rows),
                result_count=added,
            )
            return IndexResponse(
                index_id=index_id,
                collection=collection,
                subject=subject,
                status="completed",
                duration_ms=duration_ms,
                files_received=len(uploads),
                files_indexed=len(file_results),
                chunks=len(rows),
                added_chunks=added,
                hyde_count=hyde_count,
                embedding_model=settings.hf_embedding_model,
                files=file_results,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError("indexing timed out") from exc
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)
