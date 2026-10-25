from typing import Any, Literal

from pydantic import BaseModel, Field

ChartType = Literal["table", "bar", "line", "pie", "number"]


class ChartSpec(BaseModel):
    type: ChartType = "table"
    x_column: str | None = None
    y_columns: list[str] = Field(default_factory=list)


class Attempt(BaseModel):
    attempt: int
    sql: str | None = None
    status: Literal["rejected", "failed", "succeeded"]
    error: str | None = None


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
