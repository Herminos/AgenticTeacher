import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.core.telemetry import log_event
from app.schemas import ComputeRequest, ComputeResponse
from app.services.compute_service import ComputeService

router = APIRouter()
service = ComputeService()


@router.post("/compute", response_model=ComputeResponse)
async def compute(payload: ComputeRequest, request: Request) -> ComputeResponse:
    settings = get_settings()
    timeout = min(payload.timeout_ms, settings.compute_timeout_ms)
    started = perf_counter()
    try:
        result, warnings, verified = await service.compute(payload.expression, timeout)
    except ValueError as exc:
        log_event(
            "symbolic_compute",
            level=logging.WARNING,
            request_id=request.state.request_id,
            agent_run_id=payload.agent_run_id,
            stage="compute",
            status="failed",
            duration_ms=round((perf_counter() - started) * 1000, 2),
            input_chars=len(payload.expression),
        )
        raise HTTPException(status_code=422, detail={"code": "COMPUTE_FAILED", "message": str(exc), "retryable": False}) from exc
    duration_ms = round((perf_counter() - started) * 1000, 2)
    log_event(
        "symbolic_compute",
        request_id=request.state.request_id,
        agent_run_id=payload.agent_run_id,
        stage="compute",
        status="succeeded",
        duration_ms=duration_ms,
        input_chars=len(payload.expression),
    )
    return ComputeResponse(result=result, warnings=warnings, verified=verified, duration_ms=duration_ms)
