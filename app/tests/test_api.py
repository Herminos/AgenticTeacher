import httpx
import pytest

from app.main import app

pytestmark = pytest.mark.asyncio


async def request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def test_health_live() -> None:
    response = await request("GET", "/health/live")
    assert response.status_code == 200
    assert response.json()["live"] is True


async def test_health_ready_exposes_pytorch_runtime() -> None:
    response = await request("GET", "/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert "runtime" in body
    assert "cuda_available" in body["runtime"]
    assert body["model_device"] in {"cpu", "cuda"}


async def test_rewrite_contract() -> None:
    response = await request(
        "POST",
        "/v1/rewrite",
        json={"query": "那个洛必达怎么用的？", "subject": "calculus", "llm": {"provider": "mock"}},
    )
    assert response.status_code == 200
    assert "rewritten_query" in response.json()
    assert response.json()["should_retrieve"] is True


async def test_teaching_rewrite_and_non_teaching_empty_decision() -> None:
    teaching = await request(
        "POST",
        "/v1/rewrite",
        json={"query": "拉普拉斯变换是什么", "subject": "calculus", "llm": {"provider": "mock"}},
    )
    assert teaching.status_code == 200
    assert teaching.json()["rewritten_query"] == "拉普拉斯变换的定义"
    greeting = await request(
        "POST",
        "/v1/rewrite",
        json={"query": "你好，你是谁", "subject": "calculus", "llm": {"provider": "mock"}},
    )
    assert greeting.status_code == 200
    assert greeting.json()["should_retrieve"] is False
    assert greeting.json()["rewritten_query"] == ""


async def test_evidence_assessment_contract() -> None:
    response = await request(
        "POST",
        "/v1/assess",
        json={
            "query": "拉普拉斯变换是什么",
            "rewritten_query": "拉普拉斯变换的定义",
            "documents": [],
            "attempt": 1,
            "llm": {"provider": "mock"},
        },
    )
    assert response.status_code == 200
    assert response.json()["sufficient"] is False
    assert response.json()["next_query"] == "拉普拉斯变换的定义"


async def test_retrieve_contract() -> None:
    response = await request(
        "POST",
        "/v1/retrieve",
        json={"query": "洛必达法则", "subject": "calculus", "top_k": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert "retrieval_id" in body
    assert "quality_hint" in body
    assert len(body["documents"]) <= 5
    assert body["quality_hint"]["reranked_count"] <= 5


async def test_server_enforces_three_rag_attempts() -> None:
    run_id = "run_budget_contract"
    for _ in range(3):
        response = await request(
            "POST",
            "/v1/retrieve",
            json={"query": "洛必达法则", "subject": "calculus", "top_k": 15, "agent_run_id": run_id},
        )
        assert response.status_code == 200
    blocked = await request(
        "POST",
        "/v1/retrieve",
        json={"query": "洛必达法则", "subject": "calculus", "top_k": 15, "agent_run_id": run_id},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RAG_ITERATION_LIMIT"


async def test_generate_sse_contract() -> None:
    response = await request(
        "POST",
        "/v1/generate",
        json={"messages": [{"role": "user", "content": "解释中值定理"}], "context": "教材片段"},
    )
    assert response.status_code == 200
    assert "event: token" in response.text
    assert "event: done" in response.text


async def test_rag_index_upload_returns_statistics(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.index import service as index_service
    from app.schemas import IndexResponse

    async def fake_index(files, subject, hyde_count, request_id=None):
        assert len(files) == 1
        assert subject == "calculus"
        return IndexResponse(
            index_id="idx_test",
            collection="lecture_math",
            subject=subject,
            status="completed",
            duration_ms=2,
            files_received=1,
            files_indexed=1,
            chunks=1,
            added_chunks=1,
            hyde_count=hyde_count,
            embedding_model="Qwen/Qwen3-Embedding-0.6B",
        )

    monkeypatch.setattr(index_service, "index", fake_index)
    response = await request(
        "POST",
        "/v1/index",
        data={"subject": "calculus", "hyde_count": "1"},
        files={"files": ("chapter.md", "## 极限\n\n洛必达法则用于 0/0 型极限。".encode("utf-8"), "text/markdown")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["files_received"] == 1
    assert body["files_indexed"] == 1
    assert body["chunks"] >= 1
    assert body["added_chunks"] == body["chunks"]


async def test_rag_index_rejects_unsupported_file() -> None:
    response = await request(
        "POST",
        "/v1/index",
        data={"subject": "calculus"},
        files={"files": ("notes.exe", b"not a document", "application/octet-stream")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INDEX_REJECTED"


async def test_generate_rejects_empty_assistant_placeholder() -> None:
    response = await request(
        "POST",
        "/v1/generate",
        json={
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": ""},
            ],
            "llm": {"provider": "mock"},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_exhausted_rag_emits_world_knowledge_notice() -> None:
    response = await request(
        "POST",
        "/v1/generate",
        json={
            "messages": [{"role": "user", "content": "解释未知定理"}],
            "context": "",
            "retrieval_attempts": 3,
            "rag_exhausted": True,
            "llm": {"provider": "mock"},
        },
    )
    assert response.status_code == 200
    assert "未在已索引教材中找到足够相关片段" in response.text
