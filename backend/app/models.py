from typing import Any, Literal

from pydantic import BaseModel, Field

ChartType = Literal["table", "bar", "line", "pie", "number"]


class ChartSpec(BaseModel):
    type: ChartType = "table"
    x_column: str | None = None
    y_columns: list[str] = Field(default_factory=list)


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
    error: str | None = None


class SchemaResponse(BaseModel):
    schemas: list[str]
    summary: str
