from typing import Any

from fastapi import APIRouter

from app.config import get_settings
from app.core.device import runtime_status
from app.services.qdrant_service import QdrantService

router = APIRouter()
qdrant = QdrantService()


@router.get("/health/live")
async def live() -> dict[str, bool]:
    return {"live": True}


@router.get("/health/ready")
async def ready() -> dict[str, Any]:
    ok = await qdrant.ready()
    settings = get_settings()
    provider_ok = settings.llm_provider.lower() == "mock" or bool(settings.openai_api_key or settings.llm_base_url)
    runtime = runtime_status(settings.model_device, settings.model_dtype)
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
    return {
        "ready": ok and provider_ok and device_ok,
        "qdrant": ok,
        "provider": provider_ok,
        "local_models_enabled": settings.hf_enable_local_models,
        "reranker_enabled": settings.hf_enable_reranker or settings.hf_enable_local_models,
        "embedding_model": settings.hf_embedding_model,
        "reranker_model": settings.reranker_model_ref,
        "model_device": runtime.get("selected_device", settings.model_device),
        "model_dtype": runtime.get("selected_dtype", settings.model_dtype),
        "runtime": runtime,
    }
