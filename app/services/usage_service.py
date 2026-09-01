from collections import defaultdict
from threading import Lock
from typing import Any


_shared_service: "UsageService | None" = None


class UsageService:
    """Small in-memory ledger; replace with durable billing storage in production."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[str, dict[str, Any]] = defaultdict(dict)

    def record(self, agent_run_id: str, **usage: Any) -> None:
        with self._lock:
            current = self._records[agent_run_id]
            for key, value in usage.items():
                if isinstance(value, (int, float)) and isinstance(current.get(key), (int, float)):
                    current[key] += value
                else:
                    current[key] = value

    def snapshot(self, agent_run_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._records.get(agent_run_id, {}))

    def consume_limited(self, agent_run_id: str, counter: str, limit: int) -> int | None:
        with self._lock:
            current = int(self._records[agent_run_id].get(counter, 0))
            if current >= limit:
                return None
            current += 1
            self._records[agent_run_id][counter] = current
            return current


def get_usage_service() -> UsageService:
    global _shared_service
    if _shared_service is None:
        _shared_service = UsageService()
    return _shared_service
