"""Lazy Hugging Face models for Chinese embeddings and reranking.

Imports are deferred so the API can still run in Mock/in-memory mode when the
optional ML dependencies or model weights are not installed.
"""

import asyncio
from functools import lru_cache
from threading import Lock
from time import perf_counter
from typing import Any

from app.config import get_settings
from app.core.device import configure_torch, resolve_device, resolve_dtype
from app.core.telemetry import log_event


_runtime_lock = Lock()
_runtime: dict[str, Any] = {"status": "not_started", "error": None}


def _model_ref(model_id: str, cache_dir: str, local_only: bool) -> str:
    """Resolve a cached snapshot path to avoid tokenizer metadata network calls."""
    try:
        from huggingface_hub import snapshot_download

        return snapshot_download(model_id, cache_dir=cache_dir, local_files_only=local_only)
    except Exception:
        return model_id


class HFEmbeddingModel:
    def __init__(self) -> None:
        self.tokenizer: Any = None
        self.model: Any = None
        self.dimension: int | None = None
        self.device = "cpu"
        self._load_lock = Lock()

    def _load(self) -> None:
        if self.model is not None:
            return
        with self._load_lock:
            if self.model is not None:
                return
            import torch
            from transformers import AutoModel, AutoTokenizer

            settings = get_settings()
            self.device = resolve_device(settings.model_device)
            dtype = resolve_dtype(self.device, settings.model_dtype)
            configure_torch(self.device)
            model_ref = _model_ref(
                settings.hf_embedding_model,
                settings.model_cache_dir,
                settings.hf_local_files_only,
            )
            tokenizer = AutoTokenizer.from_pretrained(
                model_ref,
                padding_side="left",
                cache_dir=settings.model_cache_dir,
                local_files_only=settings.hf_local_files_only,
                trust_remote_code=settings.hf_trust_remote_code,
            )
            model = AutoModel.from_pretrained(
                model_ref,
                cache_dir=settings.model_cache_dir,
                local_files_only=settings.hf_local_files_only,
                trust_remote_code=settings.hf_trust_remote_code,
                low_cpu_mem_usage=True,
                dtype=dtype,
            )
            model.eval()
            model.to(self.device)
            dimension = int(getattr(model.config, "hidden_size", 0)) or None
            if dimension is None:
                raise RuntimeError("embedding model does not expose hidden_size")
            self.tokenizer = tokenizer
            self.model = model
            self.dimension = dimension
            self._torch = torch

    def encode(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        self._load()
        torch = self._torch
        settings = get_settings()
        instruction = (
            "Given a Chinese university STEM question, retrieve textbook passages that directly answer it, "
            "prioritizing exact terminology, definitions, and equations."
        )
        prepared = [f"Instruct: {instruction}\nQuery: {text}" for text in texts] if is_query else texts
        inputs = self.tokenizer(
            prepared,
            padding=True,
            truncation=True,
            max_length=2048,
            return_tensors="pt",
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            output = self.model(**inputs).last_hidden_state
        attention_mask = inputs["attention_mask"]
        if bool((attention_mask[:, -1].sum() == attention_mask.shape[0]).item()):
            pooled = output[:, -1]
        else:
            sequence_lengths = attention_mask.sum(dim=1) - 1
            pooled = output[
                torch.arange(output.shape[0], device=output.device), sequence_lengths
            ]
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        return pooled.cpu().tolist()


class HFRerankerModel:
    def __init__(self) -> None:
        self.tokenizer: Any = None
        self.model: Any = None
        self.device = "cpu"
        self._load_lock = Lock()
        self._prefix_tokens: list[int] = []
        self._suffix_tokens: list[int] = []
        self._true_token_id = 0
        self._false_token_id = 0

    def _load(self) -> None:
        if self.model is not None:
            return
        with self._load_lock:
            if self.model is not None:
                return
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            settings = get_settings()
            self.device = resolve_device(settings.model_device)
            dtype = resolve_dtype(self.device, settings.model_dtype)
            configure_torch(self.device)
            model_ref = _model_ref(
                settings.reranker_model_ref,
                settings.model_cache_dir,
                settings.hf_local_files_only,
            )
            tokenizer = AutoTokenizer.from_pretrained(
                model_ref,
                padding_side="left",
                cache_dir=settings.model_cache_dir,
                local_files_only=settings.hf_local_files_only,
                trust_remote_code=settings.hf_trust_remote_code,
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_ref,
                cache_dir=settings.model_cache_dir,
                local_files_only=settings.hf_local_files_only,
                trust_remote_code=settings.hf_trust_remote_code,
                low_cpu_mem_usage=True,
                dtype=dtype,
            )
            model.eval()
            model.to(self.device)
            prefix = (
                '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query '
                'and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n'
                '<|im_start|>user\n'
            )
            suffix = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
            self.tokenizer = tokenizer
            self.model = model
            self._torch = torch
            self._prefix_tokens = tokenizer.encode(prefix, add_special_tokens=False)
            self._suffix_tokens = tokenizer.encode(suffix, add_special_tokens=False)
            self._true_token_id = tokenizer.convert_tokens_to_ids("yes")
            self._false_token_id = tokenizer.convert_tokens_to_ids("no")

    def score(self, query: str, documents: list[str]) -> list[float]:
        self._load()
        settings = get_settings()
        instruction = "Given a Chinese teaching query, retrieve textbook passages that directly answer the query"
        pairs = [
            f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {document}"
            for document in documents
        ]
        scores: list[float] = []
        content_length = settings.reranker_max_length - len(self._prefix_tokens) - len(self._suffix_tokens)
        for start in range(0, len(pairs), settings.reranker_batch_size):
            batch = pairs[start : start + settings.reranker_batch_size]
            encoded = self.tokenizer(
                batch,
                padding=False,
                truncation="longest_first",
                return_attention_mask=False,
                max_length=content_length,
            )
            for index, token_ids in enumerate(encoded["input_ids"]):
                encoded["input_ids"][index] = self._prefix_tokens + token_ids + self._suffix_tokens
            inputs = self.tokenizer.pad(encoded, padding=True, return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            with self._torch.inference_mode():
                logits = self.model(**inputs).logits[:, -1, :]
            yes_logits = logits[:, self._true_token_id]
            no_logits = logits[:, self._false_token_id]
            probabilities = self._torch.softmax(
                self._torch.stack([no_logits, yes_logits], dim=1),
                dim=1,
            )[:, 1]
            scores.extend(float(value) for value in probabilities.cpu().tolist())
        return scores


@lru_cache(maxsize=1)
def get_embedding_model() -> HFEmbeddingModel:
    return HFEmbeddingModel()


@lru_cache(maxsize=1)
def get_reranker_model() -> HFRerankerModel:
    return HFRerankerModel()


async def embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]]:
    return await asyncio.to_thread(get_embedding_model().encode, texts, is_query)


async def rerank_texts(query: str, documents: list[str]) -> list[float]:
    if not documents:
        return []
    return await asyncio.to_thread(get_reranker_model().score, query, documents)


def hf_runtime_status() -> dict[str, Any]:
    settings = get_settings()
    with _runtime_lock:
        status = dict(_runtime)
    embedding = get_embedding_model()
    reranker = get_reranker_model()
    status.update(
        enabled=settings.hf_enable_local_models and settings.hf_enable_reranker,
        embedding_loaded=embedding.model is not None,
        reranker_loaded=reranker.model is not None,
        embedding_device=embedding.device if embedding.model is not None else None,
        reranker_device=reranker.device if reranker.model is not None else None,
        embedding_dimension=embedding.dimension,
        embedding_model=settings.hf_embedding_model,
        reranker_model=settings.reranker_model_ref,
    )
    return status


async def warmup_hf_models() -> None:
    """Load and execute both Qwen models once so readiness reflects reality."""
    settings = get_settings()
    if not settings.hf_enable_local_models or not settings.hf_enable_reranker:
        with _runtime_lock:
            _runtime.update(status="disabled", error="Qwen embedding or reranker is disabled")
        return
    with _runtime_lock:
        if _runtime["status"] in {"loading", "ready"}:
            return
        _runtime.update(status="loading", error=None)
    started = perf_counter()
    try:
        vectors = await embed_texts(["麦克斯韦方程组"], is_query=True)
        scores = await rerank_texts("麦克斯韦方程组", ["麦克斯韦方程组描述电磁场规律。"])
        if len(vectors) != 1 or not vectors[0] or len(scores) != 1:
            raise RuntimeError("model warmup returned an invalid result")
        with _runtime_lock:
            _runtime.update(status="ready", error=None)
        log_event(
            "hf_models_ready",
            stage="model_warmup",
            status="succeeded",
            duration_ms=round((perf_counter() - started) * 1000, 2),
            embedding_model=settings.hf_embedding_model,
            reranker_model=settings.reranker_model_ref,
        )
    except Exception as exc:
        with _runtime_lock:
            _runtime.update(status="failed", error=str(exc)[:300])
        log_event(
            "hf_models_failed",
            level="ERROR",
            stage="model_warmup",
            status="failed",
            duration_ms=round((perf_counter() - started) * 1000, 2),
            error=str(exc)[:300],
        )
