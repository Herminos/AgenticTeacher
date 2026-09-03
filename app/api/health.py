from typing import Any

from fastapi import APIRouter, Response, status

from app.config import get_settings
from app.core.device import runtime_status
from app.services.qdrant_service import QdrantService
from app.services.hf_models import hf_runtime_status

router = APIRouter()
qdrant = QdrantService()


@router.get("/health/live")
async def live() -> dict[str, bool]:
    return {"live": True}


@router.get("/health/ready")
async def ready(response: Response) -> dict[str, Any]:
    ok = await qdrant.ready()
    settings = get_settings()
    provider_ok = settings.llm_provider.lower() == "mock" or bool(settings.openai_api_key or settings.llm_base_url)
    runtime = runtime_status(settings.model_device, settings.model_dtype)
    hf_runtime = hf_runtime_status()
    # Auto/CPU + Mock may intentionally run without optional ML dependencies.
    # Invalid settings and explicit CUDA requests must still fail readiness
    # instead of silently selecting a different execution path.
    device_ok = bool(runtime.get("configuration_ok"))
    if runtime.get("engine") == "unavailable":
        device_ok = (
            not settings.hf_enable_local_models
            and settings.model_device.lower() in {"auto", "cpu"}
            and settings.model_dtype.lower() in {"auto", "float32", "bfloat16"}
        )
    models_enabled = settings.hf_enable_local_models and settings.hf_enable_reranker
    models_ok = models_enabled and hf_runtime.get("status") == "ready"
    is_ready = ok and provider_ok and device_ok and models_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "ready": is_ready,
        "qdrant": ok,
        "provider": provider_ok,
        "local_models_enabled": settings.hf_enable_local_models,
        "reranker_enabled": settings.hf_enable_reranker or settings.hf_enable_local_models,
        "rag_ready": models_ok and ok,
        "embedding_backend": settings.hf_embedding_model if models_ok else "unavailable",
        "reranker_backend": settings.reranker_model_ref if models_ok else "unavailable",
        "embedding_model": settings.hf_embedding_model,
        "reranker_model": settings.reranker_model_ref,
        "model_device": runtime.get("selected_device", settings.model_device),
        "model_dtype": runtime.get("selected_dtype", settings.model_dtype),
        "runtime": runtime,
        "models": hf_runtime,
    }
