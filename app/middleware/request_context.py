from time import perf_counter
from uuid import uuid4

from app.core.telemetry import log_event
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestContextMiddleware:
    """Attach a request id to every request and response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode() or str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started = perf_counter()
        response_status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message.get("status", 500))
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            log_event(
                "http_request",
                request_id=request_id,
                http_method=scope.get("method"),
                http_path=scope.get("path"),
                http_status=response_status,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                status="succeeded" if response_status < 400 else "failed",
            )
