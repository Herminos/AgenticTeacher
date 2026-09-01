from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import RequestMeta


ProviderName = Literal["mock", "deepseek", "qwen", "openai"]


class LLMConfig(BaseModel):
    """Per-request model settings supplied by the UI.

    The API key is intentionally never returned, persisted, or included in
    trace events. Deployments should use HTTPS and may disable this field when
    centrally managed credentials are preferred.
    """

    provider: ProviderName = "mock"
    base_url: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, max_length=128)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        return value.rstrip("/")

    @field_validator("api_key", "model")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RewriteRequest(RequestMeta):
    query: str = Field(min_length=1, max_length=4000)
    subject: str | None = Field(default=None, max_length=64)
    previous_query: str = Field(default="", max_length=4000)
    missing_aspects: list[str] = Field(default_factory=list, max_length=12)
    llm: LLMConfig | None = None


class RewriteResponse(BaseModel):
    rewritten_query: str = ""
    query_terms: list[str] = Field(default_factory=list)
    should_retrieve: bool = False
    duration_ms: float = 0

    @model_validator(mode="after")
    def validate_retrieval_decision(self) -> "RewriteResponse":
        if self.should_retrieve and not self.rewritten_query.strip():
            raise ValueError("rewritten_query is required when should_retrieve is true")
        if not self.should_retrieve:
            self.rewritten_query = ""
            self.query_terms = []
        return self


class EvidenceDocument(BaseModel):
    text: str = Field(max_length=12000)
    source_id: str = Field(default="", max_length=128)
    normalized_score: float | None = Field(default=None, ge=0, le=1)


class AssessRequest(RequestMeta):
    query: str = Field(min_length=1, max_length=4000)
    rewritten_query: str = Field(min_length=1, max_length=4000)
    documents: list[EvidenceDocument] = Field(default_factory=list, max_length=5)
    attempt: int = Field(ge=1, le=3)
    llm: LLMConfig | None = None


class AssessResponse(BaseModel):
    sufficient: bool
    missing_aspects: list[str] = Field(default_factory=list, max_length=3)
    next_query: str = Field(default="", max_length=4000)
    duration_ms: float = 0

    @model_validator(mode="after")
    def validate_next_query(self) -> "AssessResponse":
        if self.sufficient:
            self.missing_aspects = []
            self.next_query = ""
        elif not self.next_query.strip():
            raise ValueError("next_query is required when evidence is insufficient")
        return self


class RetrieveRequest(RequestMeta):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=3, ge=1, le=32)
    subject: str | None = Field(default=None, max_length=64)
    filters: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    text: str
    metadata: dict[str, Any]
    score: float | None = None
    normalized_score: float | None = None
    score_type: str | None = None


class QualityHint(BaseModel):
    qualified_count: int = 0
    has_more: bool = False
    candidate_count: int = 0
    reranked_count: int = 0
    retrieval_ms: float = 0
    reranker_ms: float = 0


class RetrieveResponse(BaseModel):
    documents: list[DocumentResponse]
    quality_hint: QualityHint
    retrieval_id: str


class ComputeRequest(RequestMeta):
    expression: str = Field(min_length=1, max_length=1000)
    timeout_ms: int = Field(default=3000, ge=100, le=10000)


class ComputeResponse(BaseModel):
    result: str
    warnings: list[str] = Field(default_factory=list)
    verified: bool = False
    duration_ms: float = 0


class ImageRef(BaseModel):
    file_id: str | None = Field(default=None, max_length=128)
    data: str | None = None
    mime_type: str = Field(default="image/png", max_length=64)

    @field_validator("file_id", "data")
    @classmethod
    def not_empty(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("must not be empty")
        return value


class SourceRef(BaseModel):
    source_id: str = Field(max_length=128)
    citation: str = Field(default="", max_length=512)


class GenerateRequest(RequestMeta):
    messages: list[dict[str, str]] = Field(min_length=1, max_length=20)
    context: str = Field(default="", max_length=100000)
    images: list[ImageRef] = Field(default_factory=list, max_length=4)
    file_ids: list[str] = Field(default_factory=list, max_length=4)
    sources: list[SourceRef] = Field(default_factory=list, max_length=16)
    retrieval_id: str | None = Field(default=None, max_length=128)
    retrieval_attempts: int = Field(default=0, ge=0, le=3)
    rag_exhausted: bool = False
    llm: LLMConfig | None = None

    @field_validator("messages")
    @classmethod
    def validate_roles(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        for message in value:
            if message.get("role") not in {"user", "assistant"}:
                raise ValueError("message role must be user or assistant")
            if not message.get("content"):
                raise ValueError("message content must not be empty")
        return value
