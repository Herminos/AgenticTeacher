"""Persistent registry for isolated RAG files and runtime retrieval settings."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from app.config import get_settings


class RagRegistry:
    """Small JSON registry shared by the API and the RAG management UI.

    Qdrant remains the source of truth for vectors and chunk payloads. The
    registry stores only file-level metadata, collection names and settings so
    management operations survive API restarts without duplicating document
    text in another database.
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or get_settings().rag_registry_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload.setdefault("version", 1)
                payload.setdefault("settings", {})
                payload.setdefault("files", {})
                return payload
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return {"version": 1, "settings": {}, "files": {}}

    def _write(self, payload: dict[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(prefix="rag_registry_", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def runtime_settings(self) -> dict[str, int]:
        settings = get_settings()
        defaults = {
            "chunk_chars": settings.rag_chunk_chars,
            "retrieval_top_k": settings.retrieval_candidate_k,
            # The parent-child retrieval contract always selects the best four
            # reranked child chunks and expands those children to parents.
            "reranker_top_k": 4,
        }
        with self._lock:
            saved = self._read().get("settings", {})
        for key in defaults:
            value = saved.get(key)
            if isinstance(value, int):
                defaults[key] = value
        defaults["chunk_chars"] = max(128, min(8192, defaults["chunk_chars"]))
        defaults["retrieval_top_k"] = max(4, min(64, settings.max_top_k, defaults["retrieval_top_k"]))
        defaults["reranker_top_k"] = 4
        return defaults

    def update_runtime_settings(self, values: dict[str, int]) -> dict[str, int]:
        settings = get_settings()
        bounds = {
            "chunk_chars": (128, 8192),
            "retrieval_top_k": (4, min(64, settings.max_top_k)),
            "reranker_top_k": (4, 4),
        }
        with self._lock:
            payload = self._read()
            current = self.runtime_settings()
            for key, value in values.items():
                if key not in bounds:
                    continue
                lower, upper = bounds[key]
                current[key] = max(lower, min(upper, int(value)))
            payload["settings"] = current
            self._write(payload)
            return current

    def upsert_file(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = self._read()
            record = {**record, "updated_at": datetime.now(timezone.utc).isoformat()}
            payload["files"][str(record["file_id"])] = record
            self._write(payload)
            return record

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._read().get("files", {}).get(file_id)
            return dict(record) if isinstance(record, dict) else None

    def list_files(self, subject: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            records = [dict(item) for item in self._read().get("files", {}).values() if isinstance(item, dict)]
        if subject:
            records = [item for item in records if item.get("subject") == subject]
        return sorted(records, key=lambda item: str(item.get("updated_at", "")), reverse=True)

    def delete_file(self, file_id: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self._read()
            record = payload.get("files", {}).pop(file_id, None)
            if record is None:
                return None
            self._write(payload)
            return dict(record) if isinstance(record, dict) else None


_registry: RagRegistry | None = None


def get_rag_registry() -> RagRegistry:
    global _registry
    if _registry is None:
        _registry = RagRegistry()
    return _registry
