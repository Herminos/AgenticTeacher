import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.telemetry import log_event
from app.services.model_provider import get_provider
from app.services.usage_service import get_usage_service
from app.api.retrieve import service as retrieval_service
from app.schemas import GenerateRequest

router = APIRouter()
usage_service = get_usage_service()


def _generation_error(exc: Exception) -> tuple[str, str, bool, int | None]:
    error_type = type(exc).__name__
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in {401, 403}:
        return "PROVIDER_AUTH_FAILED", "模型供应商鉴权失败，请检查 API Key", False, status
    if status == 404:
        return "PROVIDER_NOT_FOUND", "模型或 Base URL 不存在，请检查模型设置", False, status
    if status == 429:
        return "PROVIDER_RATE_LIMITED", "模型供应商限流或额度不足，请稍后重试", True, status
    if isinstance(status, int):
        return "PROVIDER_HTTP_ERROR", f"模型供应商请求失败（HTTP {status}）", status >= 500, status
    if "Timeout" in error_type:
        return "PROVIDER_TIMEOUT", "模型供应商响应超时，请重试", True, None
    if "RequestError" in error_type or "Connect" in error_type:
        return "PROVIDER_UNREACHABLE", "无法连接模型供应商，请检查 Base URL 和网络", True, None
    return "GENERATION_FAILED", "模型生成失败，请检查供应商与模型设置", True, None


def _event(event: str, request_id: str, agent_run_id: str, seq: int, payload: dict) -> str:
    body = {"request_id": request_id, "agent_run_id": agent_run_id, "stream": "generate", "seq": seq, **payload}
    return f"event: {event}\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"


@router.post("/generate")
async def generate(payload: GenerateRequest, request: Request) -> StreamingResponse:
    request_id = payload.request_id or request.state.request_id
    agent_run_id = payload.agent_run_id or f"run_{uuid4().hex[:12]}"
    context = payload.context
    if payload.retrieval_id:
        snapshot = retrieval_service.snapshot(payload.retrieval_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail={"code": "RETRIEVAL_NOT_FOUND", "message": "retrieval snapshot expired or is invalid", "retryable": False})
        context = "\n\n".join(f"[S{index}] {row.text}" for index, row in enumerate(snapshot, start=1))
    images = [item.model_dump(exclude_none=True) for item in payload.images]

    async def stream() -> AsyncIterator[str]:
        seq = 0
        output_chars = 0
        started = perf_counter()
        first_token_ms: float | None = None
        provider_name = payload.llm.provider if payload.llm else "server_default"
        try:
            seq += 1
            yield _event("trace", request_id, agent_run_id, seq, {"step": "generate", "status": "running"})
            if payload.sources:
                for source in payload.sources:
                    seq += 1
                    yield _event("source", request_id, agent_run_id, seq, {"source_id": source.source_id})
            if payload.rag_exhausted:
                log_event(
                    "rag_exhausted_world_knowledge_fallback",
                    level=logging.WARNING,
                    request_id=request_id,
                    agent_run_id=agent_run_id,
                    stage="generate",
                    status="fallback",
                    retrieval_attempts=payload.retrieval_attempts,
                    rag_exhausted=True,
                )
                warning = "未在已索引教材中找到足够相关片段，以下基于模型通用知识回答。\n\n"
                output_chars += len(warning)
                seq += 1
                yield _event("token", request_id, agent_run_id, seq, {"content": warning})
            provider = get_provider(payload.llm)
            async for chunk in provider.generate(
                payload.messages,
                context,
                images,
                payload.rag_exhausted,
            ):
                if first_token_ms is None:
                    first_token_ms = round((perf_counter() - started) * 1000, 2)
                output_chars += len(chunk)
                seq += 1
                yield _event("token", request_id, agent_run_id, seq, {"content": chunk})
            generation_ms = round((perf_counter() - started) * 1000, 2)
            accumulated = usage_service.snapshot(agent_run_id)
            usage = {
                "input_tokens": max(0, (len(context) + sum(len(m["content"]) for m in payload.messages)) // 4),
                "output_tokens": max(0, output_chars // 4),
                "retrieval_count": payload.retrieval_attempts,
                "reranker_calls": accumulated.get("reranker_calls", 0),
                "compute_ms": 0,
                "generation_ms": generation_ms,
                "first_token_ms": first_token_ms,
            }
            usage_service.record(agent_run_id, **usage)
            seq += 1
            yield _event(
                "trace",
                request_id,
                agent_run_id,
                seq,
                {
                    "step": "generate",
                    "status": "succeeded",
                    "duration_ms": generation_ms,
                    "summary": "模型回答生成完成",
                },
            )
            seq += 1
            yield _event("done", request_id, agent_run_id, seq, {"finish": True, "usage": usage})
            log_event(
                "model_generation",
                request_id=request_id,
                agent_run_id=agent_run_id,
                stage="generate",
                status="succeeded",
                duration_ms=generation_ms,
                first_token_ms=first_token_ms,
                provider=provider_name,
                output_chars=output_chars,
                retrieval_attempts=payload.retrieval_attempts,
                rag_exhausted=payload.rag_exhausted,
                rewrite_ms=accumulated.get("rewrite_ms"),
                assessment_ms=accumulated.get("assessment_ms"),
                retrieval_ms=accumulated.get("retrieval_ms"),
                reranker_ms=accumulated.get("reranker_ms"),
            )
        except Exception as exc:
            usage_service.record(agent_run_id, failed_generations=1)
            duration_ms = round((perf_counter() - started) * 1000, 2)
            code, message, retryable, upstream_status = _generation_error(exc)
            log_event(
                "model_generation",
                level=logging.ERROR,
                request_id=request_id,
                agent_run_id=agent_run_id,
                stage="generate",
                status="failed",
                duration_ms=duration_ms,
                provider=provider_name,
                output_chars=output_chars,
                retrieval_attempts=payload.retrieval_attempts,
                error_type=type(exc).__name__,
                upstream_status=upstream_status,
            )
            seq += 1
            yield _event(
                "error",
                request_id,
                agent_run_id,
                seq,
                {
                    "code": code,
                    "message": message,
                    "retryable": retryable,
                },
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
