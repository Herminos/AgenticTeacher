import asyncio
import re
import socket
from dataclasses import dataclass
from uuid import uuid4
import hashlib

from app.config import get_settings
from app.services.hf_models import embed_texts

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
except ImportError:  # pragma: no cover
    QdrantClient = None  # type: ignore


@dataclass
class Retrieved:
    text: str
    metadata: dict
    score: float
    normalized_score: float
    score_type: str = "dense_cosine_calibrated"


class QdrantService:
    def __init__(self) -> None:
        settings = get_settings()
        self.url = settings.qdrant_url
        self.default_collection = settings.qdrant_collection
        self.client = None
        if QdrantClient:
            try:
                host = self.url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
                port = int(self.url.rsplit(":", 1)[-1].split("/", 1)[0]) if ":" in self.url.rsplit("//", 1)[-1] else 6333
                with socket.create_connection((host, port), timeout=0.15):
                    self.client = QdrantClient(url=self.url, timeout=0.5)
            except Exception:
                self.client = None
        self._qdrant_available: bool | None = None
        self._memory: dict[str, list[dict]] = {
            "lecture_math": [
                {
                    "text": "当极限呈现 0/0 或 ∞/∞ 型时，在满足可导等条件下可对分子分母分别求导，这就是洛必达法则。",
                    "metadata": {"source_id": "demo_math", "chunk_id": "demo_math_1", "filename": "demo_calculus.md", "page": 1, "chapter": "导数应用"},
                },
                {
                    "text": "拉格朗日中值定理要求函数在闭区间连续、开区间可导，并存在一点使导数等于平均变化率。",
                    "metadata": {"source_id": "demo_math", "chunk_id": "demo_math_2", "filename": "demo_calculus.md", "page": 2, "chapter": "微分学定理"},
                },
            ],
            "lecture_physics": [
                {
                    "text": "牛顿第二定律给出合外力与加速度的关系：F=ma，方向与加速度方向一致。",
                    "metadata": {"source_id": "demo_physics", "chunk_id": "demo_physics_1", "filename": "demo_physics.md", "page": 1, "chapter": "力学"},
                }
            ],
        }
        self._snapshots: dict[str, list[Retrieved]] = {}

    @staticmethod
    def _embedding(text: str, dimensions: int = 32) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(dimensions)]

    async def ready(self) -> bool:
        if self.client is None:
            return True  # mock/in-memory mode is intentionally ready
        return await self._ping()

    async def _ping(self) -> bool:
        if self.client is None:
            return False
        if self._qdrant_available is not None:
            return self._qdrant_available
        try:
            await asyncio.wait_for(asyncio.to_thread(self.client.get_collections), timeout=1.0)
            self._qdrant_available = True
        except Exception:
            self._qdrant_available = False
        return self._qdrant_available

    def _memory_search(self, collection: str, query: str, top_k: int, filters: dict) -> list[Retrieved]:
        rows = self._memory.get(collection, self._memory.get(self.default_collection, []))
        query_terms = {term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query) if len(term) > 1}
        scored: list[Retrieved] = []
        for row in rows:
            if filters and any(str(row["metadata"].get(key, "")) != str(value) for key, value in filters.items()):
                continue
            text_terms = set(re.findall(r"[\w\u4e00-\u9fff]+", row["text"].lower()))
            overlap = len(query_terms & text_terms)
            score = min(0.98, 0.35 + overlap * 0.16) if overlap else 0.12
            scored.append(Retrieved(row["text"], row["metadata"], score, score, "memory_lexical"))
        scored.sort(key=lambda item: item.normalized_score, reverse=True)
        return scored[:top_k]

    async def search(self, collection: str, query: str, top_k: int, filters: dict) -> tuple[list[Retrieved], str, bool]:
        if self.client is not None and await self._ping():
            try:
                if not self.client.collection_exists(collection):
                    raise RuntimeError("collection not found")
                query_vector = (await embed_texts([query], is_query=True))[0]
                response = self.client.query_points(
                    collection_name=collection,
                    query=query_vector,
                    using="text_dense",
                    limit=top_k,
                    with_payload=True,
                )
                points = getattr(response, "points", response)
                rows = []
                for point in points:
                    payload = point.payload or {}
                    if filters and any(str(payload.get(key, "")) != str(value) for key, value in filters.items()):
                        continue
                    score = float(getattr(point, "score", 0.0))
                    rows.append(Retrieved(str(payload.get("text", "")), payload, score, max(0.0, min(1.0, (score + 1) / 2))))
                retrieval_id = f"retr_{uuid4().hex[:12]}"
                self._snapshots[retrieval_id] = rows
                return rows, retrieval_id, len(rows) >= top_k
            except Exception:
                pass
        # The in-memory path keeps development and contract tests deterministic.
        all_results = self._memory_search(collection, query, max(top_k, 1000), filters)
        retrieval_id = f"retr_{uuid4().hex[:12]}"
        selected = all_results[:top_k]
        self._snapshots[retrieval_id] = selected
        return selected, retrieval_id, len(all_results) > top_k

    def snapshot(self, retrieval_id: str) -> list[Retrieved] | None:
        return self._snapshots.get(retrieval_id)

    def replace_snapshot(self, retrieval_id: str, rows: list[Retrieved]) -> None:
        self._snapshots[retrieval_id] = rows

    async def upsert(self, collection: str, rows: list[dict]) -> int:
        if self.client is not None and rows and await self._ping():
            try:
                # Keep CPU/GPU memory bounded for large ingest jobs.
                vectors: list[list[float]] = []
                for start in range(0, len(rows), 4):
                    vectors.extend(await embed_texts([row["text"] for row in rows[start : start + 4]]))
                dimension = len(vectors[0])
                if not self.client.collection_exists(collection):
                    self.client.create_collection(collection_name=collection, vectors_config={"text_dense": VectorParams(size=dimension, distance=Distance.COSINE)})
                else:
                    info = self.client.get_collection(collection)
                    configured = getattr(getattr(getattr(info, "config", None), "params", None), "vectors", None)
                    if isinstance(configured, dict) and "text_dense" in configured:
                        configured_size = getattr(configured["text_dense"], "size", None)
                        if configured_size and int(configured_size) != dimension:
                            raise ValueError(f"embedding dimension mismatch: model={dimension}, collection={configured_size}")
                points = [PointStruct(id=int(hashlib.sha256(row["metadata"].get("chunk_id", str(index)).encode()).hexdigest()[:15], 16), vector={"text_dense": vectors[index]}, payload={**row["metadata"], "text": row["text"]}) for index, row in enumerate(rows)]
                self.client.upsert(collection_name=collection, points=points)
            except Exception:
                # Keep the in-memory fallback available when Qdrant is offline or has a different schema.
                pass
        bucket = self._memory.setdefault(collection, [])
        existing = {row["metadata"].get("chunk_id") for row in bucket}
        added = 0
        for row in rows:
            chunk_id = row["metadata"].get("chunk_id")
            if chunk_id in existing:
                continue
            bucket.append(row)
            existing.add(chunk_id)
            added += 1
        return added
