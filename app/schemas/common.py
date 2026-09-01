from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class RequestMeta(BaseModel):
    request_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    agent_run_id: str | None = Field(default=None, max_length=128)
    client_version: str | None = Field(default=None, max_length=64)
