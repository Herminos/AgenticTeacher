from collections.abc import Callable
from typing import Any

from app.config import get_settings


class LazyModelLoader:
    """Framework-neutral lazy loader; real Transformers loaders can be injected."""

    def __init__(self, name: str, factory: Callable[[], Any] | None = None) -> None:
        self.name = name
        self.factory = factory
        self._model: Any = None
        self.error: str | None = None

    def load(self) -> Any:
        if self._model is not None:
            return self._model
        if self.factory is None:
            self.error = f"no loader configured for {self.name}"
            raise RuntimeError(self.error)
        try:
            self._model = self.factory()
            return self._model
        except Exception as exc:
            self.error = str(exc)
            raise

    @property
    def ready(self) -> bool:
        return self._model is not None or self.factory is None


class EmbeddingLoader(LazyModelLoader):
    def __init__(self, factory: Callable[[], Any] | None = None) -> None:
        settings = get_settings()
        super().__init__(settings.embedding_model, factory)
        self.dimensions: int | None = None

    def validate_dimensions(self, collection_dimensions: int) -> None:
        if self.dimensions is not None and self.dimensions != collection_dimensions:
            raise ValueError(f"embedding dimension mismatch: model={self.dimensions}, collection={collection_dimensions}")


class RerankerLoader(LazyModelLoader):
    def __init__(self, factory: Callable[[], Any] | None = None) -> None:
        super().__init__(get_settings().reranker_model_ref, factory)
