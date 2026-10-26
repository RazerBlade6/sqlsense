from typing import Any, Literal, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm import invoke_structured, with_structured_output
from app.models import Attempt, ChartSpec, QueryResponse
from app.safety import SQLSafetyError, validate_select_sql
from app.warehouse import Warehouse, WarehouseError
from app.warehouse.catalog import load_catalog, table_names

SYSTEM_PROMPT = """You are a senior analytics engineer writing SQL for a read-only retail analytics assistant.

Write one Amazon Athena (Trino) SELECT query that answers the question from the tables below.
- Use only the listed tables and columns; qualify columns with table aliases when joining.
- Follow the column comments. They state units, codes, and caveats (for example which households have demographics).
- The data covers calendar year 2017 (weeks 1-53). Interpret relative periods such as "last 4 weeks" or "recent" against the end of the data, not today's date.
- Filter on week when the question covers a subset of weeks; the large fact tables are partitioned by it.
- Round money to 2 decimal places. Give result columns short, readable snake_case aliases.
- Return only the columns needed to answer, ordered sensibly, with a LIMIT for row-level or "top N" results.
- When business definitions are given, follow them exactly: they set the metric formula, the period (for example which weeks a fiscal quarter covers) and any filters. If a definition includes an SQL pattern, start from that pattern (keeping its joins and denominators) and adapt only the filters and grouping.
- If the previous attempt failed, read the error and fix the query.
Pick the chart that best shows the result: number for a single value, line for time series, bar for comparisons across categories, table otherwise."""

HUMAN_PROMPT = """Tables:
{schema}

Business definitions:
{context}

Question: {question}

Previous attempt: {feedback}"""


class GeneratedSQL(BaseModel):
    """A single Athena SELECT query that answers the question, plus how to chart the result."""

    sql: str = Field(description="One Athena (Trino) SELECT statement. No markdown, no comments.")
    explanation: str = Field(description="One or two sentences on what the query returns.")
    chart_type: Literal["table", "bar", "line", "pie", "number"] = "table"
    x_column: str | None = Field(default=None, description="Result column for the x axis.")
    y_columns: list[str] = Field(default_factory=list, description="Result columns to plot.")


class AgentState(TypedDict, total=False):
    question: str
    schema: str
    context: str
    sql: str
    explanation: str
    chart: dict[str, Any]
    attempts: int
    max_attempts: int
    is_valid: bool
    columns: list[str]
    rows: list[dict[str, Any]]
    bytes_scanned: int | None
    execution_ms: int | None
    truncated: bool
    attempt_log: list[dict[str, Any]]
    generation: dict[str, Any]
    error: str | None


class SQLQueryAgent:
    """Generate → validate → execute, feeding validation and warehouse errors back for retries."""

    def __init__(self, warehouse: Warehouse, settings: Settings):
        self.warehouse = warehouse
        self.settings = settings
        catalog = load_catalog(settings.catalog_path)
        self.database = catalog["database"]
        self.allowed_tables = table_names(catalog)
        self.sql_llm = with_structured_output(settings.sql_model_id, GeneratedSQL, settings)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
        )
        self.graph = self._build_graph()

    def run(
        self, question: str, max_attempts: int = 3, context: str | None = None
    ) -> QueryResponse:
        """Answer from the warehouse. `context` carries document excerpts such as metric definitions."""
        final_state = self.graph.invoke(
            {
                "question": question,
                "schema": self.warehouse.schema_summary(),
                "context": context or "none",
                "attempts": 0,
                "max_attempts": max_attempts,
                "attempt_log": [],
                "error": None,
            },
            {"recursion_limit": max_attempts * 4 + 6},
        )
        return QueryResponse(
            question=question,
            sql=final_state.get("sql"),
            columns=final_state.get("columns", []),
            rows=final_state.get("rows", []),
            chart=ChartSpec.model_validate(final_state.get("chart", {})),
            explanation=final_state.get("explanation"),
            attempts=final_state.get("attempts", 0),
            attempt_log=[Attempt.model_validate(a) for a in final_state.get("attempt_log", [])],
            engine=self.warehouse.engine,
            bytes_scanned=final_state.get("bytes_scanned"),
            execution_ms=final_state.get("execution_ms"),
            truncated=final_state.get("truncated", False),
            error=final_state.get("error"),
        )

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("generate_sql", self._generate_sql)
        graph.add_node("validate_sql", self._validate_sql)
        graph.add_node("execute_sql", self._execute_sql)

        graph.set_entry_point("generate_sql")
        graph.add_edge("generate_sql", "validate_sql")
        graph.add_conditional_edges(
            "validate_sql",
            self._route_after_validation,
            {"execute": "execute_sql", "retry": "generate_sql", "done": END},
        )
        graph.add_conditional_edges(
            "execute_sql",
            self._route_after_execution,
            {"retry": "generate_sql", "done": END},
        )
        return graph.compile()

    def _generate_sql(self, state: AgentState) -> AgentState:
        feedback = state.get("error") or "none"
        call = invoke_structured(
            self.prompt | self.sql_llm,
            {
                "schema": state["schema"],
                "context": state.get("context", "none"),
                "question": state["question"],
                "feedback": feedback,
            },
            GeneratedSQL,
        )
        generated = call.output
        return {
            "generation": {
                "generate_ms": call.duration_ms,
                "input_tokens": call.input_tokens,
                "output_tokens": call.output_tokens,
            },
            "attempts": state.get("attempts", 0) + 1,
            "sql": generated.sql.strip(),
            "explanation": generated.explanation,
            "chart": {
                "type": generated.chart_type,
                "x_column": generated.x_column,
                "y_columns": generated.y_columns,
            },
            "error": None,
        }

    def _validate_sql(self, state: AgentState) -> AgentState:
        try:
            safe_sql = validate_select_sql(
                state.get("sql", ""),
                self.allowed_tables,
                self.database,
                max_rows=self.settings.max_result_rows,
            )
        except SQLSafetyError as exc:
            error = f"Rejected SQL `{state.get('sql', '')}`: {exc}"
            return {"is_valid": False, "error": error, **self._log(state, "rejected", error)}
        return {"sql": safe_sql, "is_valid": True, "error": None}

    def _execute_sql(self, state: AgentState) -> AgentState:
        try:
            result = self.warehouse.run(state["sql"], self.settings.max_result_rows)
        except WarehouseError as exc:
            error = f"Query failed for SQL `{state['sql']}`: {exc}"
            return {"columns": [], "rows": [], "error": error, **self._log(state, "failed", error)}
        return {
            "columns": result.columns,
            "rows": result.rows,
            "bytes_scanned": result.bytes_scanned,
            "execution_ms": result.execution_ms,
            "truncated": result.truncated,
            "error": None,
            **self._log(
                state,
                "succeeded",
                None,
                execution_ms=result.execution_ms,
                bytes_scanned=result.bytes_scanned,
            ),
        }

    @staticmethod
    def _log(state: AgentState, status: str, error: str | None, **metrics: Any) -> AgentState:
        entry = {
            "attempt": state.get("attempts", 0),
            "sql": state.get("sql"),
            "status": status,
            **state.get("generation", {}),
            **metrics,
        }
        if error:
            entry["error"] = error
        return {"attempt_log": [*state.get("attempt_log", []), entry]}

    def _route_after_validation(self, state: AgentState) -> str:
        if state.get("is_valid"):
            return "execute"
        if state.get("attempts", 0) < state.get("max_attempts", 3):
            return "retry"
        return "done"

    def _route_after_execution(self, state: AgentState) -> str:
        if state.get("error") and state.get("attempts", 0) < state.get("max_attempts", 3):
            return "retry"
        return "done"
