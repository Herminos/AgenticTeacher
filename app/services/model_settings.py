"""Persistent single-user model configuration.

This is intentionally a small JSON store for self-hosted deployments. It
persists the active provider configuration, including its API key, but is not
a multi-tenant secret manager. Production deployments should put the file on
an encrypted volume and add authentication.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from app.config import get_settings
from app.schemas import LLMConfig, ModelSettingsResponse


class ModelSettingsStore:
    def __init__(self, path: str | None = None) -> None:
        configured = path or get_settings().model_settings_file
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    def _write(self, value: dict[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(prefix="model_settings_", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def get(self) -> dict[str, Any]:
        settings = get_settings()
        provider = settings.llm_provider if settings.llm_provider in {"mock", "deepseek", "qwen", "openai"} else "mock"
        defaults = {
            "provider": provider,
            "base_url": settings.llm_base_url,
            "model": settings.llm_model,
            "temperature": 0.2,
            # OPENAI_API_KEY is an environment fallback for OpenAI only; it
            # must never be presented as a DeepSeek/Qwen credential.
            "api_key": settings.openai_api_key if provider == "openai" else None,
        }
        with self._lock:
            defaults.update({key: value for key, value in self._read().items() if key in defaults})
        return defaults

    def save(self, config: LLMConfig) -> ModelSettingsResponse:
        with self._lock:
            current = self.get()
            values = config.model_dump()
            # An empty key means “keep the already persisted key” only when the
            # active provider stays the same. Never carry a key across providers.
            if not values.get("api_key") and values.get("provider") == current.get("provider"):
                values["api_key"] = current.get("api_key")
            elif not values.get("api_key"):
                values["api_key"] = None
            self._write(values)
            return self._response(values)

    def clear(self) -> ModelSettingsResponse:
        with self._lock:
            self._write({"provider": "mock", "base_url": None, "model": "mock-teacher", "temperature": 0.2, "api_key": None})
            return self._response(self.get())

    @staticmethod
    def _response(values: dict[str, Any]) -> ModelSettingsResponse:
        return ModelSettingsResponse(
            provider=values.get("provider", "mock"),
            base_url=values.get("base_url"),
            model=values.get("model"),
            temperature=float(values.get("temperature", 0.2)),
            api_key_configured=bool(values.get("api_key")),
        )

    def as_llm_config(self, config: LLMConfig | None = None) -> LLMConfig:
        persisted = self.get()
        if config is None:
            return LLMConfig(**{key: persisted.get(key) for key in ("provider", "base_url", "model", "temperature", "api_key")})
        values = config.model_dump()
        if not values.get("api_key"):
            values["api_key"] = persisted.get("api_key") if values.get("provider") == persisted.get("provider") else None
        return LLMConfig(**values)


_store: ModelSettingsStore | None = None


def get_model_settings_store() -> ModelSettingsStore:
    global _store
    if _store is None:
        _store = ModelSettingsStore()
    return _store
