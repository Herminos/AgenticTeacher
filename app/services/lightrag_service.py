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
from time import perf_counter
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


_FORMULA_QUERY_TERMS = re.compile(r"(方程|公式|表达式|方程组|定律|关系式|写出|列出|推导式|数学形式)")
_FORMULA_MARKERS = re.compile(r"(\$\$|\\\(|\\\[|\\begin\{|∇|∂|∮|∫|\b(?:div|curl)\b|[A-Za-z]_[A-Za-z0-9])")


def is_formula_request(query: str) -> bool:
    """Whether the user explicitly asks for an equation/formula result."""
    return bool(_FORMULA_QUERY_TERMS.search(query))


def is_formula_chunk(text: str) -> bool:
    """Detect Markdown/TeX or plain-text mathematical equation chunks."""
    return bool(_FORMULA_MARKERS.search(text))


class LightRAGService:
    """Cached LightRAG workspaces, one workspace per validated subject."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._instances: dict[str, Any] = {}
        self._backend: dict[str, str] = {}
        self._loops: dict[str, Any] = {}
        self._reranker_timings: dict[str, list[float]] = {}
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

    async def _embedding(self, texts: list[str], **kwargs: Any) -> Any:
        """Embed with Qwen or fail closed; fake vectors must never reach Qdrant."""
        if not self.settings.hf_enable_local_models:
            raise RuntimeError("Qwen embedding is disabled; set HF_ENABLE_LOCAL_MODELS=true")
        try:
            import numpy as np

            is_query = str(kwargs.get("context", "document")).lower() == "query"
            return np.asarray(await embed_texts(texts, is_query=is_query), dtype="float32")
        except Exception as exc:  # pragma: no cover - depends on model files
            log_event("embedding_failed", level="ERROR", stage="embedding", error=str(exc)[:200])
            raise RuntimeError("Qwen embedding failed; refusing to create non-semantic vectors") from exc

    async def _rerank(self, query: str, documents: list[str], top_n: int | None = None, **_: Any) -> list[dict[str, Any]]:
        if not self.settings.hf_enable_reranker:
            raise RuntimeError("Qwen reranker is disabled; set HF_ENABLE_RERANKER=true")
        started = perf_counter()
        try:
            scores = await rerank_texts(query, documents)
        except Exception as exc:  # pragma: no cover - depends on model files
            log_event("reranker_failed", level="ERROR", stage="rerank", error=str(exc)[:200])
            raise RuntimeError("Qwen reranker failed; refusing to use lexical fallback") from exc
        duration_ms = round((perf_counter() - started) * 1000, 2)
        self._reranker_timings.setdefault(query, []).append(duration_ms)
        log_event(
            "qwen_reranker",
            stage="rerank",
            status="succeeded",
            duration_ms=duration_ms,
            candidate_count=len(documents),
            result_count=min(len(documents), top_n or len(documents)),
            model=self.settings.reranker_model_ref,
        )
        if len(scores) != len(documents):
            raise RuntimeError(
                f"Qwen reranker returned {len(scores)} scores for {len(documents)} documents"
            )
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

        if not self.settings.hf_enable_local_models or not self.settings.hf_enable_reranker:
            raise RuntimeError(
                "Real RAG requires HF_ENABLE_LOCAL_MODELS=true and HF_ENABLE_RERANKER=true"
            )
        workspace = self._workspace(subject)
        current_loop = __import__("asyncio").get_running_loop()
        if workspace in self._instances and self._loops.get(workspace) is current_loop:
            return self._instances[workspace]
        os.environ.setdefault("QDRANT_URL", self.settings.qdrant_url)
        if not self._qdrant_reachable():
            raise RuntimeError(f"Qdrant is unavailable at {self.settings.qdrant_url}")
        storage = "QdrantVectorDBStorage"
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
        # Always return the requested candidate window, including
        # equation-only chunks whose lexical signal is weak. The Qwen
        # reranker (or our deterministic fallback) performs final
        # relevance filtering; LightRAG's default 0.2 cosine cutoff can
        # otherwise discard valid formula blocks before reranking.
            cosine_better_than_threshold=-1.0,
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

    async def index_document(self, text: str, doc_id: str, filename: str, subject: str | None, chunk_chars: int, child_chunks: list[str] | None = None) -> dict[str, Any]:
        rag = await self._create(subject, chunk_chars)
        if child_chunks:
            await rag.ainsert_custom_chunks(text, child_chunks, doc_id=doc_id)
        else:
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
        self._reranker_timings.pop(query, None)

        # Keep a wider candidate window than the UI's final TopK. Formula-only
        # chunks often have little lexical text and can otherwise be pushed
        # out before the reranker gets a chance to compare them.
        candidate_k = min(64, max(top_k, top_k * 4))
        result = await rag.aquery_data(query, QueryParam(mode="naive", top_k=candidate_k, chunk_top_k=candidate_k, enable_rerank=True, include_references=True))
        data = result.get("data", {}) if isinstance(result, dict) else {}
        chunks = data.get("chunks", []) if isinstance(data, dict) else []
        if isinstance(result, dict) and result.get("status") == "failure":
            raise RuntimeError(str(result.get("message") or "LightRAG query failed"))
        documents: list[dict[str, Any]] = []
        from app.services.rag_registry import get_rag_registry
        records = get_rag_registry().list_files(subject)
        file_records = {Path(str(item.get("filename", ""))).name: item for item in records}
        file_by_source = {str(item.get("source_id", "")): item for item in records}
        # `aquery_data` intentionally exposes a compact reference payload and
        # LightRAG 1.5.x may leave `reference_id` empty for custom chunks. Read
        # the authoritative chunk rows once to recover full_doc_id, which also
        # keeps older indexes (created before parent mappings were introduced)
        # addressable.
        chunk_doc_ids: dict[str, str] = {}
        try:
            raw_rows = await rag.text_chunks.get_by_ids([str(item.get("chunk_id", "")) for item in chunks if item.get("chunk_id")])
            for item in raw_rows:
                if isinstance(item, dict) and item.get("_id") and item.get("full_doc_id"):
                    chunk_doc_ids[str(item["_id"])] = str(item["full_doc_id"])
        except Exception:
            chunk_doc_ids = {}
        chunk_by_id = {
            str(chunk_id): item
            for item in records
            for chunk_id in (item.get("child_ids", {}) or {})
        }
        # LightRAG has already applied the Qwen reranker at this point. Select
        # the top N *child* hits first, then expand each selected child to its
        # complete parent. A long parent can therefore occupy one result even
        # when several children matched it; no independent parent TopK is
        # applied.
        reranker_top_k = get_rag_registry().runtime_settings()["reranker_top_k"]
        selected_children = chunks[: max(1, int(reranker_top_k))]
        seen_parents: set[str] = set()
        parent_documents: dict[str, dict[str, Any]] = {}
        for index, chunk in enumerate(selected_children):
            content = str(chunk.get("content", chunk.get("text", ""))).strip()
            if not content:
                continue
            filename = Path(str(chunk.get("file_path", ""))).name
            source_id = str(chunk.get("full_doc_id", "")) or chunk_doc_ids.get(str(chunk.get("chunk_id", "")), "")
            record = file_records.get(filename, {}) or file_by_source.get(source_id, {})
            if not record:
                record = chunk_by_id.get(str(chunk.get("chunk_id", "")), {})
            parent_text, parent_id = self._parent_for_child(record, content, str(chunk.get("chunk_id", "")))
            # A parent is the unit returned to the agent. If multiple child
            # vectors from the same section match, keep the best-ranked parent
            # only; this prevents one long section from consuming every slot.
            parent_key = f"{record.get('source_id', '')}:{parent_id or chunk.get('chunk_id', '')}"
            if parent_key in seen_parents:
                existing = parent_documents[parent_key]
                metadata = existing["metadata"]
                metadata.setdefault("child_ids", []).append(chunk.get("chunk_id", ""))
                metadata.setdefault("child_texts", []).append(content)
                metadata["matched_child_count"] = len(metadata["child_ids"])
                continue
            seen_parents.add(parent_key)
            resolved_filename = filename if filename and filename != "unknown_source" else str(record.get("filename", ""))
            document = {
                "text": parent_text or content,
                "metadata": {"source_id": record.get("source_id", chunk.get("reference_id", "")), "chunk_id": chunk.get("chunk_id", ""), "child_id": chunk.get("chunk_id", ""), "child_ids": [chunk.get("chunk_id", "")], "parent_id": parent_id, "block_type": "parent" if parent_text else "child_fallback", "filename": resolved_filename, "child_text": content, "child_texts": [content], "matched_child_count": 1, "child_chars": len(content), "parent_chars": len(parent_text or content)},
                "score": max(0.0, 1.0 - index / max(1, top_k)),
                "normalized_score": max(0.0, 1.0 - index / max(1, top_k)),
                "score_type": "lightrag_reranked",
            }
            documents.append(document)
            parent_documents[parent_key] = document
        metadata = dict(result.get("metadata", {}) or {}) if isinstance(result, dict) else {}
        metadata["reranker_ms"] = sum(self._reranker_timings.pop(query, []))
        metadata["embedding_backend"] = self.settings.hf_embedding_model
        metadata["reranker_backend"] = self.settings.reranker_model_ref
        return documents, metadata

    @staticmethod
    def _parent_for_child(record: dict[str, Any], child_text: str, child_id: str | None = None) -> tuple[str, str | None]:
        parents = record.get("parent_blocks", []) if isinstance(record, dict) else []
        child_parents = record.get("child_parents", {}) if isinstance(record, dict) else {}
        child_ids = record.get("child_ids", {}) if isinstance(record, dict) else {}
        parent_id = child_ids.get(str(child_id or "")) if child_id else None
        parent_id = parent_id or child_parents.get(hashlib.sha256(child_text.encode("utf-8")).hexdigest())
        if not parent_id:
            # LightRAG may normalize whitespace before returning content. A
            # short prefix fallback still safely associates the child with its
            # persisted parent in that case.
            probe = " ".join(child_text.split())[:100]
            if probe:
                for parent in parents:
                    candidate = " ".join(str(parent.get("text", "")).split()) if isinstance(parent, dict) else ""
                    if probe in candidate:
                        parent_id = str(parent.get("parent_id"))
                        break
        if not parent_id:
            return "", None
        for parent in parents:
            if isinstance(parent, dict) and parent.get("parent_id") == parent_id:
                return str(parent.get("text", ""))[:12000], parent_id
        return "", parent_id

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
        status_data = self._status_dict(status)
        ids = list(status_data.get("chunks_list", []) or [])[max(0, offset) : max(0, offset) + min(500, max(1, limit))]
        rows = await rag.text_chunks.get_by_ids(ids)
        from app.services.rag_registry import get_rag_registry
        record = next((item for item in get_rag_registry().list_files(subject) if str(item.get("source_id")) == doc_id), {})
        result = []
        for chunk_id, row in zip(ids, rows):
            if not row:
                continue
            child_text = str(row.get("content", ""))
            parent_text, parent_id = self._parent_for_child(record, child_text, str(chunk_id))
            source_name = status_data.get("file_path", "")
            if not source_name or source_name == "unknown_source":
                source_name = record.get("filename", "")
            result.append({"chunk_id": chunk_id, "child_id": chunk_id, "text": child_text, "source_id": doc_id, "filename": source_name, "chunk_index": row.get("chunk_order_index"), "content_hash": hashlib.sha256(child_text.encode("utf-8")).hexdigest(), "parser_version": record.get("parser_version", ""), "parent_id": parent_id, "parent_text": parent_text, "child_chars": len(child_text), "parent_chars": len(parent_text or child_text)})
        return result

    async def delete_document(self, doc_id: str, subject: str | None) -> None:
        rag = await self._create(subject, self.settings.rag_chunk_chars)
        await rag.adelete_by_doc_id(doc_id)

    async def delete_chunk(self, doc_id: str, chunk_id: str, subject: str | None) -> bool:
        rag = await self._create(subject, self.settings.rag_chunk_chars)
        status = await rag.doc_status.get_by_id(doc_id)
        status_data = self._status_dict(status) if status is not None else {}
        if status is None or chunk_id not in (status_data.get("chunks_list") or []):
            return False
        await rag.text_chunks.delete([chunk_id])
        await rag.chunks_vdb.delete([chunk_id])
        if isinstance(status, dict):
            status_data = dict(status)
        else:
            # Preserve LightRAG's status fields when the backend returns a
            # dataclass/object, while relying on the normalized list above.
            status_data = {
                "status": getattr(status, "status", "processed"),
                "chunks_count": status_data.get("chunks", 0),
                "chunks_list": status_data.get("chunks_list", []),
                "file_path": status_data.get("file_path", ""),
            }
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
