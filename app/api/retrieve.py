import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.core.telemetry import log_event
from app.schemas import DocumentResponse, QualityHint, RetrieveRequest, RetrieveResponse
from app.services.hf_models import rerank_texts
from app.services.qdrant_service import QdrantService
from app.services.usage_service import get_usage_service

router = APIRouter()
service = QdrantService()
usage_service = get_usage_service()


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(payload: RetrieveRequest, request: Request) -> RetrieveResponse:
    settings = get_settings()
    agent_run_id = payload.agent_run_id or request.state.request_id
    attempt = usage_service.consume_limited(
        agent_run_id,
        "retrieval_attempts",
        settings.max_agent_iterations,
    )
    if attempt is None:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RAG_ITERATION_LIMIT",
                "message": "RAG retrieval limit of 3 attempts reached",
                "retryable": False,
            },
        )
    collection = settings.collection_for(payload.subject)
    retrieve_started = perf_counter()
    candidates, retrieval_id, has_more = await service.search(
        collection,
        payload.query,
        settings.retrieval_candidate_k,
        payload.filters,
    )
    retrieval_ms = round((perf_counter() - retrieve_started) * 1000, 2)
    rows = candidates
    reranker_ms = 0.0
    reranker_used = settings.hf_enable_reranker or settings.hf_enable_local_models
    if reranker_used and candidates:
        reranker_started = perf_counter()
        try:
            scores = await rerank_texts(payload.query, [row.text for row in candidates])
            for row, score in zip(candidates, scores, strict=True):
                row.normalized_score = max(0.0, min(1.0, score))
                row.score_type = "qwen3_reranker_probability"
            rows = sorted(candidates, key=lambda row: row.normalized_score, reverse=True)
        except Exception:
            reranker_used = False
            log_event(
                "reranker_failed",
                level=logging.WARNING,
                request_id=request.state.request_id,
                agent_run_id=agent_run_id,
                stage="rerank",
                status="failed",
                attempt=attempt,
                candidate_count=len(candidates),
            )
        reranker_ms = round((perf_counter() - reranker_started) * 1000, 2)
    rows = rows[: settings.reranker_top_k]
    service.replace_snapshot(retrieval_id, rows)
    threshold = settings.grade_threshold_for(collection)
    documents = [
        DocumentResponse(
            text=row.text,
            metadata=row.metadata,
            score=row.score,
            normalized_score=row.normalized_score,
            score_type=row.score_type,
        )
        for row in rows
    ]
    qualified = sum(1 for row in rows if row.normalized_score >= threshold)
    usage_service.record(
        agent_run_id,
        retrieval_ms=retrieval_ms,
        reranker_ms=reranker_ms,
        reranker_calls=1 if reranker_used else 0,
    )
    log_event(
        "rag_retrieval",
        request_id=request.state.request_id,
        agent_run_id=agent_run_id,
        stage="retrieve",
        status="succeeded",
        duration_ms=round(retrieval_ms + reranker_ms, 2),
        retrieval_ms=retrieval_ms,
        reranker_ms=reranker_ms,
        subject=payload.subject,
        attempt=attempt,
        candidate_count=len(candidates),
        result_count=len(rows),
        reranker_used=reranker_used,
    )
    return RetrieveResponse(
        documents=documents,
        quality_hint=QualityHint(
            qualified_count=qualified,
            has_more=has_more,
            candidate_count=len(candidates),
            reranked_count=len(rows),
            retrieval_ms=retrieval_ms,
            reranker_ms=reranker_ms,
        ),
        retrieval_id=retrieval_id,
    )
