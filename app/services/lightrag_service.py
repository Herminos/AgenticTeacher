"""LightRAG orchestration used by the production indexing and retrieval paths.

The application deliberately keeps this adapter small: parsing, chunking,
storage, retrieval and document deletion are delegated to LightRAG.  Qwen
models are supplied through LightRAG's callback interfaces so the browser and
business code never implement a second vector pipeline.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import types
import inspect
from types import SimpleNamespace
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.core.telemetry import log_event
from app.services.hf_models import embed_texts, rerank_texts


class _TextTokenizer:
    """Small offline tokenizer used until the Qwen tokenizer is available."""

    def encode(self, text: str, **_: Any) -> list[int]:
        return [ord(char) for char in text]

    def decode(self, tokens: list[int], **_: Any) -> str:
        return "".join(chr(token) for token in tokens)

    def __deepcopy__(self, memo: dict[int, Any]) -> "_TextTokenizer":
        return self


def _stable_vector(text: str, dimension: int = 1024) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(dimension)]
    norm = sum(value * value for value in values) ** 0.5 or 1.0
    return [value / norm for value in values]


class LightRAGService:
    """Cached LightRAG workspaces, one workspace per validated subject."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._instances: dict[str, Any] = {}
        self._backend: dict[str, str] = {}
        self._loops: dict[str, Any] = {}
        # Retrieval snapshots are short-lived request handoff data. The
        # durable source of truth remains LightRAG; this map only lets the
        # subsequent /generate request rebuild trusted context by ID.
        self._snapshots: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _workspace(subject: str | None) -> str:
        value = re.sub(r"[^a-zA-Z0-9_-]", "_", subject or "default").strip("_")
        return value[:48] or "default"

    def _qdrant_reachable(self) -> bool:
        url = self.settings.qdrant_url.split("://", 1)[-1].split("/", 1)[0]
        host, _, port_text = url.partition(":")
        try:
            with socket.create_connection((host, int(port_text or 6333)), timeout=0.2):
                return True
        except OSError:
            return False

    async def _embedding(self, texts: list[str], **_: Any) -> Any:
        """LightRAG embedding callback; Qwen is used when local models enabled."""
        if self.settings.hf_enable_local_models:
            try:
                import numpy as np

                return np.asarray(await embed_texts(texts), dtype="float32")
            except Exception as exc:  # pragma: no cover - depends on model files
                log_event("embedding_fallback", level="WARNING", stage="embedding", error=str(exc)[:200])
        import numpy as np

        return np.asarray([_stable_vector(text) for text in texts], dtype="float32")

    async def _rerank(self, query: str, documents: list[str], top_n: int | None = None, **_: Any) -> list[dict[str, Any]]:
        scores: list[float] = []
        if self.settings.hf_enable_reranker or self.settings.hf_enable_local_models:
            try:
                scores = await rerank_texts(query, documents)
            except Exception as exc:  # pragma: no cover - depends on model files
                log_event("reranker_fallback", level="WARNING", stage="rerank", error=str(exc)[:200])
                scores = []
        if len(scores) != len(documents):
            query_terms = set(re.findall(r"[\w\u4e00-\u9fff]+", query.lower()))
            scores = [
                0.01 + len(query_terms & set(re.findall(r"[\w\u4e00-\u9fff]+", str(doc).lower()))) / max(1, len(query_terms))
                for doc in documents
            ]
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        if top_n:
            ranked = ranked[:top_n]
        return [{"index": index, "relevance_score": float(score)} for index, score in ranked]

    async def _llm(self, prompt: str, system_prompt: str | None = None, **_: Any) -> str:
        """Adapter for LightRAG entity extraction.

        Mock deployments return an empty, valid JSON graph immediately.  A
        configured provider receives the extraction prompt server-side.
        """
        provider = self.settings.llm_provider
        if provider == "mock" or not self.settings.openai_api_key:
            return '{"entities": [], "relationships": []}'
        import httpx

        base = (self.settings.llm_base_url or "").rstrip("/")
        if not base:
            return '{"entities": [], "relationships": []}'
        body = {
            "model": self.settings.llm_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt or "Extract entities and relationships as JSON."},
                {"role": "user", "content": prompt},
            ],
        }
        timeout = httpx.Timeout(self.settings.request_read_timeout_ms / 1000, connect=self.settings.request_connect_timeout_ms / 1000)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {self.settings.openai_api_key}"}, json=body)
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])

    async def _create(self, subject: str | None, chunk_chars: int) -> Any:
        from lightrag import LightRAG
        from lightrag.utils import EmbeddingFunc, Tokenizer

        # The package's bounded executor can deadlock in restricted containers
        # where worker threads are disabled.  Keep LightRAG's persistence
        # semantics but execute its tiny atomic JSON commits inline there.
        async def direct_commit(fn: Any, on_committed: Any) -> Any:
            result = fn()
            if inspect.isawaitable(result):
                result = await result
            callback_result = on_committed()
            if inspect.isawaitable(callback_result):
                await callback_result
            return result
        for module_name in ("lightrag.kg.json_kv_impl", "lightrag.kg.json_doc_status_impl", "lightrag.kg.nano_vector_db_impl", "lightrag.kg.networkx_impl"):
            try:
                module = __import__(module_name, fromlist=["commit_in_storage_io"])
                module.commit_in_storage_io = direct_commit
            except Exception:
                pass

        workspace = self._workspace(subject)
        current_loop = __import__("asyncio").get_running_loop()
        if workspace in self._instances and self._loops.get(workspace) is current_loop:
            return self._instances[workspace]
        os.environ.setdefault("QDRANT_URL", self.settings.qdrant_url)
        use_qdrant = self._qdrant_reachable()
        storage = "QdrantVectorDBStorage" if use_qdrant else "NanoVectorDBStorage"
        working_dir = Path(self.settings.lightrag_working_dir) / workspace
        working_dir.mkdir(parents=True, exist_ok=True)
        # Avoid LightRAG's dataclasses.asdict deepcopy of asyncio ContextVars
        # during both construction and query (see compatibility note below).
        def build_config(instance: Any) -> dict[str, Any]:
            config: dict[str, Any] = {}
            for field in getattr(instance, "__dataclass_fields__", {}).values():
                name = field.name
                if name.startswith("_") or name == "addon_params":
                    continue
                if hasattr(instance, name):
                    config[name] = getattr(instance, name)
            config["tokenizer"] = instance.tokenizer
            config["embedding_func"] = instance.embedding_func
            config["addon_params"] = dict(getattr(instance, "_addon_params", {}))
            states = getattr(instance, "_role_llm_states", {}) or {}
            config["role_llm_funcs"] = {name: getattr(state, "wrapped", instance.llm_model_func) for name, state in states.items()}
            for name in ("extract", "query", "keyword", "summarize", "vlm"):
                config["role_llm_funcs"].setdefault(name, instance.llm_model_func)
            config["llm_cache_identities"] = {}
            return config
        LightRAG._build_global_config = build_config
        rag = LightRAG(
            working_dir=str(working_dir),
            workspace=workspace,
            vector_storage=storage,
            chunk_token_size=max(128, min(8192, int(chunk_chars))),
            chunk_overlap_token_size=min(64, max(16, int(chunk_chars) // 8)),
            tokenizer=Tokenizer("qwen", _TextTokenizer()),
            embedding_func=EmbeddingFunc(embedding_dim=1024, max_token_size=8192, func=self._embedding, model_name=self.settings.hf_embedding_model),
            rerank_model_func=self._rerank,
            min_rerank_score=0.0,
            llm_model_func=self._llm,
            entity_extraction_use_json=True,
            entity_extract_max_gleaning=0,
            max_parallel_insert=1,
            llm_model_max_async=1,
            enable_llm_cache=True,
        )
        # LightRAG 1.5.7 deep-copies its dataclass for each query.  Its
        # observable addon-params callback otherwise references a partially
        # reconstructed LightRAG instance during deepcopy.
        try:
            rag._addon_params._on_change = None
        except AttributeError:
            pass
        rag._build_global_config = types.MethodType(build_config, rag)
        await rag.initialize_storages()
        self._instances[workspace] = rag
        self._backend[workspace] = storage
        self._loops[workspace] = current_loop
        log_event("lightrag_ready", stage="rag", status="succeeded", workspace=workspace, backend=storage)
        return rag

    async def index_document(self, text: str, doc_id: str, filename: str, subject: str | None, chunk_chars: int) -> dict[str, Any]:
        rag = await self._create(subject, chunk_chars)
        await rag.ainsert(text, ids=[doc_id], file_paths=[filename])
        status = await rag.doc_status.get_by_id(doc_id)
        if status is None:
            raise RuntimeError("LightRAG did not create document status")
        return self._status_dict(status)

    @staticmethod
    def _status_dict(status: Any) -> dict[str, Any]:
        def value(name: str, default: Any = None) -> Any:
            return status.get(name, default) if isinstance(status, dict) else getattr(status, name, default)
        raw_status = value("status", "")
        return {"status": str(getattr(raw_status, "value", raw_status)), "chunks": int(value("chunks", value("chunks_count", 0)) or 0), "chunks_list": list(value("chunks_list", []) or []), "file_path": value("file_path", "")}

    async def retrieve(self, query: str, subject: str | None, top_k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rag = await self._create(subject, self.settings.rag_chunk_chars)
        from lightrag import QueryParam

        result = await rag.aquery_data(query, QueryParam(mode="naive", top_k=top_k, chunk_top_k=top_k, enable_rerank=True, include_references=True))
        data = result.get("data", {}) if isinstance(result, dict) else {}
        chunks = data.get("chunks", []) if isinstance(data, dict) else []
        # A provider outage or malformed local-model output must not turn a
        # successful vector recall into an empty answer. LightRAG's own
        # no-rerank path still returns the original top-k chunks.
        if not chunks and isinstance(result, dict) and result.get("status") == "failure":
            result = await rag.aquery_data(query, QueryParam(mode="naive", top_k=top_k, chunk_top_k=top_k, enable_rerank=False, include_references=True))
            data = result.get("data", {}) if isinstance(result, dict) else {}
            chunks = data.get("chunks", []) if isinstance(data, dict) else []
        documents: list[dict[str, Any]] = []
        from app.services.rag_registry import get_rag_registry
        file_records = {Path(str(item.get("filename", ""))).name: item for item in get_rag_registry().list_files(subject)}
        for index, chunk in enumerate(chunks[:top_k]):
            content = str(chunk.get("content", chunk.get("text", ""))).strip()
            if not content:
                continue
            filename = Path(str(chunk.get("file_path", ""))).name
            record = file_records.get(filename, {})
            documents.append({
                "text": content,
                "metadata": {"source_id": record.get("source_id", chunk.get("reference_id", "")), "chunk_id": chunk.get("chunk_id", ""), "filename": filename},
                "score": max(0.0, 1.0 - index / max(1, top_k)),
                "normalized_score": max(0.0, 1.0 - index / max(1, top_k)),
                "score_type": "lightrag_reranked",
            })
        return documents, result.get("metadata", {}) if isinstance(result, dict) else {}

    def save_snapshot(self, retrieval_id: str, rows: list[dict[str, Any]]) -> None:
        self._snapshots[retrieval_id] = [dict(row) for row in rows]
        # Keep only a bounded handoff cache; persisted LightRAG data is not
        # affected when old request snapshots are evicted.
        while len(self._snapshots) > 128:
            self._snapshots.pop(next(iter(self._snapshots)))

    def snapshot(self, retrieval_id: str) -> list[Any] | None:
        rows = self._snapshots.get(retrieval_id)
        if rows is None:
            return None
        return [SimpleNamespace(text=str(row.get("text", ""))) for row in rows]

    async def document_status(self, doc_id: str, subject: str | None) -> dict[str, Any] | None:
        rag = await self._create(subject, self.settings.rag_chunk_chars)
        status = await rag.doc_status.get_by_id(doc_id)
        if status is None:
            return None
        return self._status_dict(status)

    async def list_chunks(self, doc_id: str, subject: str | None, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        rag = await self._create(subject, self.settings.rag_chunk_chars)
        status = await rag.doc_status.get_by_id(doc_id)
        if status is None:
            return []
        ids = list(status.chunks_list or [])[max(0, offset) : max(0, offset) + min(500, max(1, limit))]
        rows = await rag.text_chunks.get_by_ids(ids)
        status_data = self._status_dict(status)
        return [{"chunk_id": chunk_id, "text": str(row.get("content", "")), "source_id": doc_id, "filename": status_data.get("file_path", ""), "chunk_index": row.get("chunk_order_index")} for chunk_id, row in zip(ids, rows) if row]

    async def delete_document(self, doc_id: str, subject: str | None) -> None:
        rag = await self._create(subject, self.settings.rag_chunk_chars)
        await rag.adelete_by_doc_id(doc_id)

    async def delete_chunk(self, doc_id: str, chunk_id: str, subject: str | None) -> bool:
        rag = await self._create(subject, self.settings.rag_chunk_chars)
        status = await rag.doc_status.get_by_id(doc_id)
        if status is None or chunk_id not in (status.chunks_list or []):
            return False
        await rag.text_chunks.delete([chunk_id])
        await rag.chunks_vdb.delete([chunk_id])
        status_data = dict(status) if isinstance(status, dict) else {"status": status.status, "chunks_count": status.chunks_count, "chunks_list": status.chunks_list, "file_path": status.file_path, "content_summary": status.content_summary, "content_length": status.content_length, "created_at": status.created_at, "updated_at": status.updated_at}
        status_data["chunks_list"] = [item for item in status_data.get("chunks_list", []) if item != chunk_id]
        status_data["chunks_count"] = len(status_data["chunks_list"])
        await rag.doc_status.upsert({doc_id: status_data})
        await rag._flush_storages([rag.text_chunks, rag.chunks_vdb, rag.doc_status])
        return True

    async def finalize(self) -> None:
        """Flush and close workspace storages during graceful API shutdown."""
        for rag in list(self._instances.values()):
            try:
                await rag.finalize_storages()
            except Exception:
                continue


_service: LightRAGService | None = None


def get_lightrag_service() -> LightRAGService:
    global _service
    if _service is None:
        _service = LightRAGService()
    return _service
