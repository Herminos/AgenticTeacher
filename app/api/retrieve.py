import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.core.telemetry import log_event
from app.schemas import DocumentResponse, QualityHint, RetrieveRequest, RetrieveResponse
from app.services.lightrag_service import get_lightrag_service, is_formula_chunk, is_formula_request
from app.services.rag_registry import get_rag_registry
from app.services.usage_service import get_usage_service

router = APIRouter()
service = get_lightrag_service()
usage_service = get_usage_service()
registry = get_rag_registry()


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(payload: RetrieveRequest, request: Request) -> RetrieveResponse:
    settings = get_settings()
    agent_run_id = payload.agent_run_id or request.state.request_id
    attempt = usage_service.consume_limited(agent_run_id, "retrieval_attempts", settings.max_agent_iterations)
    if attempt is None:
        raise HTTPException(status_code=429, detail={"code": "RAG_ITERATION_LIMIT", "message": "RAG retrieval limit of 3 attempts reached", "retryable": False})
    runtime = registry.runtime_settings()
    candidate_k = min(settings.max_top_k, max(4, int(payload.top_k or runtime["retrieval_top_k"])))
    retrieval_id = f"lightrag_{request.state.request_id}_{attempt}"
    if not any(item.get("status") in {"indexed", "processed"} for item in registry.list_files(payload.subject)):
        service.save_snapshot(retrieval_id, [])
        return RetrieveResponse(
            documents=[],
            quality_hint=QualityHint(candidate_count=0, reranked_count=0),
            retrieval_id=retrieval_id,
        )
    started = perf_counter()
    try:
        # `candidate_k` controls the wide vector-recall window; the final
        # reranker TopK is applied to child chunks inside the LightRAG adapter
        # before they are expanded to parent blocks.
        rows, metadata = await service.retrieve(payload.query, payload.subject, candidate_k)
    except Exception as exc:
        log_event("rag_retrieval", level=logging.ERROR, request_id=request.state.request_id, agent_run_id=agent_run_id, stage="retrieve", status="failed", attempt=attempt, error=str(exc)[:200])
        raise HTTPException(status_code=503, detail={"code": "RAG_UNAVAILABLE", "message": "LightRAG retrieval is unavailable", "retryable": True}) from exc
    retrieval_ms = round((perf_counter() - started) * 1000, 2)
    reranker_ms = float(metadata.get("reranker_ms") or 0)
    if is_formula_request(payload.query):
        # A mathematical answer should include its displayed equation, even
        # when surrounding prose receives a slightly higher reranker score.
        formula_rows = [row for row in rows if is_formula_chunk(str(row.get("text", "")))]
        prose_rows = [row for row in rows if not is_formula_chunk(str(row.get("text", "")))]
        rows = formula_rows + prose_rows
    documents = [DocumentResponse(text=row["text"], metadata=row.get("metadata", {}), score=row.get("score"), normalized_score=row.get("normalized_score"), score_type=row.get("score_type")) for row in rows]
    threshold = settings.grade_threshold_default
    qualified = sum(1 for row in rows if float(row.get("normalized_score") or 0) >= threshold)
    usage_service.record(agent_run_id, retrieval_ms=retrieval_ms, reranker_ms=reranker_ms, reranker_calls=1 if rows else 0)
    # GenerateRequest exposes at most 16 source references and the generation
    # context has a bounded budget. Keep the UI response at the configured
    # parent TopK, but hand off only the highest-ranked 16 parent blocks to the
    # server-side generation snapshot.
    service.save_snapshot(retrieval_id, rows[:16])
    log_event("rag_retrieval", request_id=request.state.request_id, agent_run_id=agent_run_id, stage="retrieve", status="succeeded", duration_ms=retrieval_ms, retrieval_ms=retrieval_ms, reranker_ms=reranker_ms, subject=payload.subject, attempt=attempt, candidate_count=candidate_k, result_count=len(rows), reranker_used=True, embedding_backend=metadata.get("embedding_backend"), reranker_backend=metadata.get("reranker_backend"))
    return RetrieveResponse(documents=documents, quality_hint=QualityHint(qualified_count=qualified, has_more=len(rows) >= candidate_k, candidate_count=candidate_k, reranked_count=len(rows), retrieval_ms=retrieval_ms, reranker_ms=reranker_ms), retrieval_id=retrieval_id)
