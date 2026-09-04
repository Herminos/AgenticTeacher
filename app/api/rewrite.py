import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException, Request

from app.core.telemetry import log_event
from app.schemas import AssessRequest, AssessResponse, RewriteRequest, RewriteResponse
from app.services.model_provider import classify_provider_error, get_provider
from app.services.usage_service import get_usage_service

router = APIRouter()
usage_service = get_usage_service()


@router.post("/rewrite", response_model=RewriteResponse)
async def rewrite(payload: RewriteRequest, request: Request) -> RewriteResponse:
    started = perf_counter()
    provider_name = payload.llm.provider if payload.llm else "server_default"
    try:
        result = await get_provider(payload.llm).rewrite(
            payload.query,
            payload.subject,
            payload.previous_query,
            payload.missing_aspects,
        )
    except Exception as exc:
        log_event(
            "model_rewrite",
            level=logging.ERROR,
            request_id=request.state.request_id,
            agent_run_id=payload.agent_run_id,
            stage="rewrite",
            status="failed",
            duration_ms=round((perf_counter() - started) * 1000, 2),
            provider=provider_name,
        )
        code, message, retryable, upstream_status = classify_provider_error(exc)
        if code == "PROVIDER_TIMEOUT":
            status_code = 504
        elif code == "PROVIDER_RATE_LIMITED":
            status_code = 429
        elif code == "PROVIDER_UNREACHABLE":
            status_code = 503
        else:
            status_code = 502
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "retryable": retryable,
                "upstream_status": upstream_status,
            },
        ) from exc
    duration_ms = round((perf_counter() - started) * 1000, 2)
    response = RewriteResponse.model_validate({**result, "duration_ms": duration_ms})
    usage_service.record(payload.agent_run_id or request.state.request_id, rewrite_ms=duration_ms)
    log_event(
        "model_rewrite",
        request_id=request.state.request_id,
        agent_run_id=payload.agent_run_id,
        stage="rewrite",
        status="succeeded",
        duration_ms=duration_ms,
        provider=provider_name,
        subject=payload.subject,
        input_chars=len(payload.query),
        result_count=1 if response.should_retrieve else 0,
    )
    return response


@router.post("/assess", response_model=AssessResponse)
async def assess(payload: AssessRequest, request: Request) -> AssessResponse:
    started = perf_counter()
    provider_name = payload.llm.provider if payload.llm else "server_default"
    try:
        result = await get_provider(payload.llm).assess(
            payload.query,
            payload.rewritten_query,
            [item.model_dump() for item in payload.documents],
            payload.attempt,
        )
    except Exception as exc:
        log_event(
            "evidence_assessment",
            level=logging.ERROR,
            request_id=request.state.request_id,
            agent_run_id=payload.agent_run_id,
            stage="grade",
            status="failed",
            duration_ms=round((perf_counter() - started) * 1000, 2),
            provider=provider_name,
            attempt=payload.attempt,
        )
        code, message, retryable, upstream_status = classify_provider_error(exc)
        if code == "PROVIDER_TIMEOUT":
            status_code = 504
        elif code == "PROVIDER_RATE_LIMITED":
            status_code = 429
        elif code == "PROVIDER_UNREACHABLE":
            status_code = 503
        else:
            status_code = 502
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "retryable": retryable,
                "upstream_status": upstream_status,
            },
        ) from exc
    duration_ms = round((perf_counter() - started) * 1000, 2)
    response = AssessResponse.model_validate({**result, "duration_ms": duration_ms})
    usage_service.record(payload.agent_run_id or request.state.request_id, assessment_ms=duration_ms)
    log_event(
        "evidence_assessment",
        request_id=request.state.request_id,
        agent_run_id=payload.agent_run_id,
        stage="grade",
        status="succeeded",
        duration_ms=duration_ms,
        provider=provider_name,
        attempt=payload.attempt,
        candidate_count=len(payload.documents),
        sufficient=response.sufficient,
    )
    return response
