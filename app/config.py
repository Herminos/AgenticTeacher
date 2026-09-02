from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover - useful for minimal local environments
    from pydantic import BaseSettings  # type: ignore

    class SettingsConfigDict(dict):
        pass


class Settings(BaseSettings):
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "lecture_math"
    collection_map_file: str = "./config/collections.yaml"
    grade_thresholds_file: str = "./config/grade_thresholds.yaml"
    model_cache_dir: str = "./models"
    log_level: str = "INFO"
    llm_provider: str = "mock"
    llm_base_url: str | None = None
    llm_model: str = "mock-teacher"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    hf_embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    hf_local_files_only: bool = False
    hf_trust_remote_code: bool = True
    hf_enable_local_models: bool = False
    hf_enable_reranker: bool = False
    reranker_max_length: int = 4096
    reranker_batch_size: int = 4
    model_device: str = "auto"
    model_dtype: str = "auto"
    openai_api_key: str | None = None
    allowed_origins: str = "http://localhost:3000"
    max_agent_iterations: int = 3
    max_top_k: int = 15
    retrieval_candidate_k: int = 15
    reranker_top_k: int = 5
    request_connect_timeout_ms: int = 5000
    request_read_timeout_ms: int = 30000
    generate_total_timeout_ms: int = 120000
    compute_timeout_ms: int = 3000
    max_context_tokens: int = 12000
    max_upload_mb: int = 10
    grade_threshold_default: float = 0.70
    api_auth_mode: str = "none"
    max_query_chars: int = 4000
    max_messages: int = 20
    max_image_count: int = 4
    max_inline_image_bytes: int = 5 * 1024 * 1024
    files_dir: str = "/tmp/agentic_teacher_files"
    max_index_files: int = 100
    # RAG indexing accepts large textbook files.  Keep this separate from
    # max_upload_mb, which protects small answer attachments sent to /files.
    max_index_file_mb: int = 10240
    max_index_total_mb: int = 10240
    index_timeout_ms: int = 600000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def reranker_model_ref(self) -> str:
        value = self.reranker_model.strip()
        return value if "/" in value else f"Qwen/{value}"

    def effective_iterations(self, requested: int | None) -> int:
        value = requested if requested is not None else self.max_agent_iterations
        return max(1, min(3, int(value)))

    def effective_top_k(self, requested: int | None) -> int:
        value = requested if requested is not None else 3
        return max(1, min(self.max_top_k, int(value)))

    def collection_for(self, subject: str | None) -> str:
        if not subject:
            return self.qdrant_collection
        mapping = _read_simple_map(self.collection_map_file)
        return mapping.get(subject, self.qdrant_collection)

    def grade_threshold_for(self, collection: str) -> float:
        mapping = _read_simple_map(self.grade_thresholds_file, numeric=True)
        raw = mapping.get(collection, self.grade_threshold_default)
        try:
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return self.grade_threshold_default


def _read_simple_map(path: str, numeric: bool = False) -> dict[str, Any]:
    """Read a tiny YAML-like key/value file without requiring PyYAML at runtime."""
    file_path = Path(path)
    if not file_path.exists():
        return {}
    result: dict[str, Any] = {}
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        value = value.strip('"\'')
        result[key] = float(value) if numeric else value
    return result


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.files_dir).mkdir(parents=True, exist_ok=True)
    return settings
