import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.telemetry import log_event
from app.schemas import LLMConfig, ModelSettingsResponse
from app.services.model_settings import get_model_settings_store

router = APIRouter(prefix="/model-settings", tags=["model-settings"])
store = get_model_settings_store()


@router.get("", response_model=ModelSettingsResponse)
async def get_model_settings() -> ModelSettingsResponse:
    values = store.get()
    return store._response(values)


@router.put("", response_model=ModelSettingsResponse)
async def save_model_settings(payload: LLMConfig, request: Request) -> ModelSettingsResponse:
    try:
        response = store.save(payload)
    except OSError as exc:
        log_event("model_settings", level=logging.ERROR, request_id=request.state.request_id, stage="model_settings", status="failed")
        raise HTTPException(status_code=500, detail={"code": "MODEL_SETTINGS_WRITE_FAILED", "message": "模型设置保存失败", "retryable": True}) from exc
    log_event("model_settings", request_id=request.state.request_id, stage="model_settings", status="succeeded", provider=response.provider, model=response.model, api_key_configured=response.api_key_configured)
    return response


@router.delete("", response_model=ModelSettingsResponse)
async def reset_model_settings(request: Request) -> ModelSettingsResponse:
    response = store.clear()
    log_event("model_settings_reset", request_id=request.state.request_id, stage="model_settings", status="succeeded")
    return response
