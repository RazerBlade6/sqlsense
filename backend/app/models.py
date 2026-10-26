from typing import Any, Literal

from pydantic import BaseModel, Field

ChartType = Literal["table", "bar", "line", "pie", "number"]
Route = Literal["sql", "docs", "both", "clarify", "refuse"]


class ChartSpec(BaseModel):
    type: ChartType = "table"
    x_column: str | None = None
    y_columns: list[str] = Field(default_factory=list)


class Attempt(BaseModel):
    attempt: int
    sql: str | None = None
    status: Literal["rejected", "failed", "succeeded"]
    error: str | None = None
    generate_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    execution_ms: int | None = None
    bytes_scanned: int | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    max_attempts: int = Field(default=3, ge=1, le=5)


class QueryResponse(BaseModel):
    question: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    chart: ChartSpec = Field(default_factory=ChartSpec)
    explanation: str | None = None
    attempts: int = 0
    attempt_log: list[Attempt] = Field(default_factory=list)
    engine: str | None = None
    bytes_scanned: int | None = None
    execution_ms: int | None = None
    truncated: bool = False
    error: str | None = None


class SchemaResponse(BaseModel):
    engine: str
    summary: str


class Citation(BaseModel):
    id: int = Field(description="The [n] marker used in the answer.")
    chunk_id: str
    doc_id: str
    doc_type: str
    title: str
    heading: str
    path: str
    content: str
    score: float


class TraceStep(BaseModel):
    step: Literal["memory", "planner", "retrieval", "sql", "synthesizer"]
    label: str
    status: Literal["ok", "rejected", "failed"] = "ok"
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    bytes_scanned: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{8,64}$")


class ChatResponse(BaseModel):
    session_id: str
    question: str
    standalone_question: str
    route: Route
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    result: QueryResponse | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    total_ms: int
    error: str | None = None
