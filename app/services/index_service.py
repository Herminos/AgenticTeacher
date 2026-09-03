"""Safe upload handling and LightRAG document indexing."""

import asyncio
import hashlib
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from time import perf_counter
from uuid import uuid4

from fastapi import UploadFile

from app.config import get_settings
from app.core.telemetry import log_event
from app.schemas import IndexResponse, IndexedFileResult
from app.services.lightrag_service import get_lightrag_service
from app.services.rag_registry import get_rag_registry
from ingest import _read_pages

_SUPPORTED = {".pdf", ".pptx", ".txt", ".md", ".markdown"}
_MIME_BY_SUFFIX = {".pdf": "application/pdf", ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".txt": "text/plain", ".md": "text/markdown", ".markdown": "text/markdown"}


def _safe_relative_name(filename: str | None, fallback: str) -> str:
    raw = (filename or "").replace("\\", "/")
    parts = [part for part in PurePosixPath(raw).parts if part not in {"", ".", ".."}]
    safe = [re.sub(r"[^\w.\-\u4e00-\u9fff ]", "_", part) for part in parts]
    return "/".join(safe) or fallback


def _doc_id(name: str, content_hash: str) -> str:
    return "doc_" + hashlib.sha256(f"{name}\0{content_hash}".encode()).hexdigest()[:32]


class IndexService:
    def __init__(self) -> None:
        self.registry = get_rag_registry()
        self.lightrag = get_lightrag_service()

    async def index(self, uploads: list[UploadFile], subject: str | None, hyde_count: int = 0, request_id: str | None = None, chunk_chars: int | None = None, retrieval_top_k: int | None = None, reranker_top_k: int | None = None) -> IndexResponse:
        settings = get_settings()
        started = perf_counter()
        if not uploads:
            raise ValueError("at least one file is required")
        if len(uploads) > settings.max_index_files:
            raise ValueError(f"too many files; maximum is {settings.max_index_files}")
        runtime = self.registry.runtime_settings()
        chunk_chars = max(128, min(8192, int(chunk_chars or runtime["chunk_chars"])))
        retrieval_top_k = max(1, min(settings.max_top_k, int(retrieval_top_k or runtime["retrieval_top_k"])))
        reranker_top_k = max(1, min(settings.max_top_k, int(reranker_top_k or runtime["reranker_top_k"])))
        self.registry.update_runtime_settings({"chunk_chars": chunk_chars, "retrieval_top_k": retrieval_top_k, "reranker_top_k": reranker_top_k})
        file_limit = settings.max_index_file_mb * 1024 * 1024
        total_limit = settings.max_index_total_mb * 1024 * 1024
        temp_root = Path(tempfile.mkdtemp(prefix=f"idx_{uuid4().hex[:8]}_", dir=settings.files_dir))
        results: list[IndexedFileResult] = []
        total_chunks = 0
        indexed = 0
        total_bytes = 0
        try:
            for number, upload in enumerate(uploads, start=1):
                name = _safe_relative_name(upload.filename, f"upload_{number}.bin")
                suffix = Path(name).suffix.lower()
                if suffix not in _SUPPORTED:
                    raise ValueError(f"unsupported file type: {name}")
                if upload.content_type not in {None, "", _MIME_BY_SUFFIX[suffix]}:
                    raise ValueError(f"MIME type does not match filename: {name}")
                target = temp_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                digest = hashlib.sha256()
                with target.open("wb") as output:
                    while data := await upload.read(8 * 1024 * 1024):
                        size += len(data)
                        total_bytes += len(data)
                        if size > file_limit:
                            raise ValueError(f"file is too large: {name}; maximum is {settings.max_index_file_mb} MB")
                        if total_bytes > total_limit:
                            raise ValueError(f"total upload is too large; maximum is {settings.max_index_total_mb} MB")
                        digest.update(data)
                        output.write(data)
                content_hash = digest.hexdigest()
                doc_id = _doc_id(name, content_hash)
                previous = next((item for item in self.registry.list_files(subject) if item.get("filename") == name), None)
                if previous and previous.get("source_id") != doc_id:
                    await self.lightrag.delete_document(str(previous["source_id"]), subject)
                    self.registry.delete_file(str(previous["file_id"]))
                text = "\n\n".join(page_text for _, page_text in _read_pages(target) if page_text.strip())
                if not text.strip():
                    results.append(IndexedFileResult(filename=name, status="skipped", file_id=doc_id, collection=f"lightrag_{self.lightrag._workspace(subject)}"))
                    continue
                timeout = max(1, settings.index_timeout_ms) / 1000
                status = await asyncio.wait_for(self.lightrag.index_document(text, doc_id, name, subject, chunk_chars), timeout=timeout)
                chunks = int(status.get("chunks", 0))
                file_id = f"file_{doc_id[4:]}"
                self.registry.upsert_file({"file_id": file_id, "source_id": doc_id, "filename": name, "subject": subject, "collection": f"lightrag_{self.lightrag._workspace(subject)}", "size_bytes": size, "content_hash": content_hash, "chunks": chunks, "chunk_chars": chunk_chars, "retrieval_top_k": retrieval_top_k, "reranker_top_k": reranker_top_k, "embedding_model": settings.hf_embedding_model, "parser_version": "lightrag-1.5.7", "status": "indexed" if status.get("status") == "processed" else str(status.get("status", "processing"))})
                results.append(IndexedFileResult(filename=name, chunks=chunks, status="indexed" if status.get("status") == "processed" else "failed", file_id=file_id, collection=f"lightrag_{self.lightrag._workspace(subject)}"))
                total_chunks += chunks
                indexed += 1
            duration = round((perf_counter() - started) * 1000, 2)
            log_event("rag_index", request_id=request_id, stage="index", status="succeeded", duration_ms=duration, candidate_count=total_chunks, result_count=total_chunks)
            workspace_collection = f"lightrag_{self.lightrag._workspace(subject)}"
            return IndexResponse(index_id=f"idx_{uuid4().hex[:12]}", collection=workspace_collection, subject=subject, status="completed", duration_ms=duration, files_received=len(uploads), files_indexed=indexed, chunks=total_chunks, added_chunks=total_chunks, hyde_count=max(0, min(3, int(hyde_count))), embedding_model=settings.hf_embedding_model, files=results, chunk_chars=chunk_chars, retrieval_top_k=retrieval_top_k, reranker_top_k=reranker_top_k, collections=[workspace_collection])
        except asyncio.TimeoutError as exc:
            raise TimeoutError("indexing timed out") from exc
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)
