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

try:
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover - dependency is declared in requirements
    MarkdownIt = None  # type: ignore[assignment,misc]

_SUPPORTED = {".pdf", ".pptx", ".txt", ".md", ".markdown"}
_MIME_BY_SUFFIX = {".pdf": "application/pdf", ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".txt": "text/plain", ".md": "text/markdown", ".markdown": "text/markdown"}


def _safe_relative_name(filename: str | None, fallback: str) -> str:
    raw = (filename or "").replace("\\", "/")
    parts = [part for part in PurePosixPath(raw).parts if part not in {"", ".", ".."}]
    safe = [re.sub(r"[^\w.\-\u4e00-\u9fff ]", "_", part) for part in parts]
    return "/".join(safe) or fallback


def _doc_id(name: str, content_hash: str) -> str:
    return "doc_" + hashlib.sha256(f"{name}\0{content_hash}".encode()).hexdigest()[:32]


def _parent_blocks(text: str, max_parent_chars: int = 8192) -> list[str]:
    """Split source text into semantic parent sections.

    Markdown is first parsed as block structure so headings inside fenced code
    are not mistaken for section boundaries and formula/list/table blocks stay
    intact. For plain extracted PDF/PPT text, blank-line paragraphs are used.
    ``max_parent_chars`` only controls aggregation between complete blocks; a
    single oversized paragraph is never cut in the middle.
    """
    markdown_blocks: list[tuple[int, int, str]] = []
    if MarkdownIt is not None:
        try:
            parser = MarkdownIt("commonmark", {"html": False}).enable("table")
            lines = text.splitlines()
            block_types = {"heading_open", "paragraph_open", "bullet_list_open", "ordered_list_open", "blockquote_open", "table_open", "fence", "code_block", "hr"}
            heading_positions: list[int] = []
            for token in parser.parse(text):
                if token.map and token.level == 0 and token.type in block_types:
                    start, end = token.map
                    value = "\n".join(lines[start:end]).strip()
                    if value:
                        markdown_blocks.append((start, end, value))
                        if token.type == "heading_open":
                            heading_positions.append(start)
            if markdown_blocks:
                if heading_positions:
                    return _aggregate_heading_blocks(text, sorted(set(heading_positions)))
                return _aggregate_semantic_blocks([value for _, _, value in markdown_blocks], max_parent_chars)
        except Exception:
            # Malformed Markdown should still be indexable through the simple
            # line/paragraph fallback below.
            markdown_blocks = []

    lines = text.splitlines()
    heading_positions = [index for index, line in enumerate(lines) if re.match(r"^\s{0,3}#{1,6}\s+\S", line)]
    blocks: list[str] = []
    if heading_positions:
        # A document may begin with a heading; de-duplicate the initial
        # position so we never emit an empty parent section.
        starts = sorted(set([0, *heading_positions]))
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(lines)
            value = "\n".join(lines[start:end]).strip()
            if value:
                blocks.append(value)
    else:
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
        current = ""
        for paragraph in paragraphs:
            if current and len(current) + len(paragraph) + 2 > max_parent_chars:
                blocks.append(current)
                current = ""
            current = f"{current}\n\n{paragraph}".strip()
        if current:
            blocks.append(current)
    return blocks or [text.strip()]


def _aggregate_heading_blocks(text: str, heading_positions: list[int]) -> list[str]:
    lines = text.splitlines()
    starts = sorted(set([0, *heading_positions]))
    blocks: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        value = "\n".join(lines[start:end]).strip()
        if value:
            blocks.append(value)
    return blocks


def _aggregate_semantic_blocks(blocks: list[str], max_parent_chars: int) -> list[str]:
    parents: list[str] = []
    current = ""
    for block in blocks:
        if current and len(current) + len(block) + 2 > max_parent_chars:
            parents.append(current)
            current = ""
        current = f"{current}\n\n{block}".strip()
    if current:
        parents.append(current)
    return parents


def _child_chunks(parents: list[str], chunk_chars: int) -> tuple[list[str], dict[str, str]]:
    children: list[str] = []
    child_parents: dict[str, str] = {}
    for parent_index, parent in enumerate(parents):
        parent_id = f"parent_{parent_index + 1}"
        for offset in range(0, len(parent), chunk_chars):
            child = parent[offset : offset + chunk_chars].strip()
            if not child:
                continue
            children.append(child)
            child_parents[hashlib.sha256(child.encode("utf-8")).hexdigest()] = parent_id
    return children, child_parents


def _light_rag_child_ids(doc_id: str, children: list[str], child_parents: dict[str, str]) -> dict[str, str]:
    """Build the exact IDs used by pinned LightRAG custom-chunk insertion."""
    from lightrag.utils import sanitize_text_for_encoding
    from lightrag.utils_pipeline import make_custom_chunk_id

    result: dict[str, str] = {}
    for child in children:
        sanitized = sanitize_text_for_encoding(child)
        parent_id = child_parents.get(hashlib.sha256(child.encode("utf-8")).hexdigest())
        if sanitized and parent_id:
            result[make_custom_chunk_id(doc_id, sanitized)] = parent_id
    return result


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
        retrieval_top_k = max(4, min(settings.max_top_k, int(retrieval_top_k or runtime["retrieval_top_k"])))
        reranker_top_k = 4
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
                parents = _parent_blocks(text)
                children, child_parents = _child_chunks(parents, chunk_chars)
                status = await asyncio.wait_for(self.lightrag.index_document(text, doc_id, name, subject, chunk_chars, children), timeout=timeout)
                chunks = int(status.get("chunks", 0))
                # LightRAG's status list is not an ordering contract. Derive
                # the same deterministic document-scoped IDs it uses instead
                # of zipping returned IDs to input positions.
                child_ids = _light_rag_child_ids(doc_id, children, child_parents)
                file_id = f"file_{doc_id[4:]}"
                self.registry.upsert_file({"file_id": file_id, "source_id": doc_id, "filename": name, "subject": subject, "collection": f"lightrag_{self.lightrag._workspace(subject)}", "size_bytes": size, "content_hash": content_hash, "chunks": chunks, "parent_count": len(parents), "child_count": len(children), "parent_blocks": [{"parent_id": f"parent_{index + 1}", "text": parent} for index, parent in enumerate(parents)], "child_parents": child_parents, "child_ids": child_ids, "chunk_chars": chunk_chars, "retrieval_top_k": retrieval_top_k, "reranker_top_k": reranker_top_k, "embedding_model": settings.hf_embedding_model, "parser_version": "lightrag-1.5.7-parent-child", "status": "indexed" if status.get("status") == "processed" else str(status.get("status", "processing"))})
                results.append(IndexedFileResult(filename=name, chunks=chunks, parent_count=len(parents), child_count=len(children), status="indexed" if status.get("status") == "processed" else "failed", file_id=file_id, collection=f"lightrag_{self.lightrag._workspace(subject)}"))
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
