from dataclasses import dataclass, field
from typing import Any, Protocol


class WarehouseError(RuntimeError):
    """A query was rejected or failed in the warehouse. The message is safe to show the LLM."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    engine: str
    bytes_scanned: int | None = None
    execution_ms: int | None = None
    query_id: str | None = None
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class Warehouse(Protocol):
    """Read-only SQL over the retail warehouse. SQL is always written in the Athena dialect."""

    engine: str

    def run(self, sql: str, max_rows: int) -> QueryResult: ...

    def schema_summary(self) -> str: ...
