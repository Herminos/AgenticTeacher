import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import compute, files, generate, health, index, providers, retrieve, rewrite
from app.config import get_settings
from app.core.telemetry import configure_logging, log_event
from app.middleware import RequestContextMiddleware

settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(title="Agentic Teacher API", version="1.1.0")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rewrite.router, prefix="/v1")
app.include_router(retrieve.router, prefix="/v1")
app.include_router(compute.router, prefix="/v1")
app.include_router(generate.router, prefix="/v1")
app.include_router(files.router, prefix="/v1")
app.include_router(index.router, prefix="/v1")
app.include_router(providers.router, prefix="/v1")
app.include_router(health.router)


@app.exception_handler(RequestValidationError)
async def validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    validation_fields = ",".join(
        f"{'.'.join(str(part) for part in error.get('loc', ())) or 'body'}:{error.get('type', 'invalid')}"
        for error in exc.errors()[:12]
    )
    log_event(
        "request_validation",
        level=logging.WARNING,
        request_id=request_id,
        http_method=request.method,
        http_path=request.url.path,
        http_status=422,
        status="failed",
        validation_fields=validation_fields,
    )
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "request validation failed", "retryable": False, "request_id": request_id}},
    )


@app.exception_handler(HTTPException)
async def http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail), "retryable": False}
    detail.setdefault("request_id", request_id)
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "internal server error", "retryable": True, "request_id": request_id}},
    )
