from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class Citation(BaseModel):
    document: str
    page: int | None = None
    excerpt: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    abstained: bool
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class IngestResponse(BaseModel):
    document: str
    chunks_indexed: int


class HealthResponse(BaseModel):
    status: str
    indexed_chunks: int
