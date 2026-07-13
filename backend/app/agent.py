from typing import Any, Literal, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from app.config import Settings
from app.models import ChartSpec, QueryResponse
from app.safety import SQLSafetyError, validate_select_sql
from app.schema import build_schema_summary, execute_read_only_sql


class GeneratedSQL(BaseModel):
    sql: str = Field(description="One PostgreSQL SELECT query. No markdown.")
    explanation: str = Field(description="Brief explanation of what the query returns.")
    chart_type: Literal["table", "bar", "line", "pie", "number"] = "table"
    x_column: str | None = None
    y_columns: list[str] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    question: str
    schema: str
    sql: str
    explanation: str
    chart: dict[str, Any]
    attempts: int
    max_attempts: int
    is_valid: bool
    columns: list[str]
    rows: list[dict[str, Any]]
    error: str | None


class SQLQueryAgent:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        self.settings = settings
        llm_kwargs: dict[str, Any] = {
            "model": settings.openai_model,
            "temperature": 0,
        }
        if settings.openai_api_key:
            llm_kwargs["api_key"] = settings.openai_api_key
        self.llm = ChatOpenAI(**llm_kwargs)
        self.graph = self._build_graph()

    def run(self, question: str, max_attempts: int = 3) -> QueryResponse:
        schema_summary = build_schema_summary(self.engine, self.settings.schema_names)
        final_state = self.graph.invoke(
            {
                "question": question,
                "schema": schema_summary,
                "attempts": 0,
                "max_attempts": max_attempts,
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
            {
                "execute": "execute_sql",
                "retry": "generate_sql",
                "done": END,
            },
        )
        graph.add_conditional_edges(
            "execute_sql",
            self._route_after_execution,
            {
                "retry": "generate_sql",
                "done": END,
            },
        )
        return graph.compile()

    def _generate_sql(self, state: AgentState) -> AgentState:
        attempts = state.get("attempts", 0) + 1
        feedback = state.get("error") or "No previous error."

        prompt = ChatPromptTemplate.from_messages([(
            "system",
            """
            You are a senior analytics engineer generating PostgreSQL for a read-only reporting app.

            Rules:
            - Return exactly one SQL statement.
            - The SQL must be a SELECT-style read query only.
            - Never use DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, CREATE, COPY, CALL, DO, SET, SELECT INTO, or administrative commands.
            - Prefer explicit schema-qualified table names from the supplied schema.
            - Add a LIMIT of 100 unless the query is an aggregate that naturally returns a small result.
            - If previous SQL failed, use the error feedback to repair it.
            - Choose a chart type that fits the returned columns.
            """,
        ),
        (
            "human",
            """
            Database schema:
            {schema}

            User question:
            {question}

            Previous error or feedback:
            {feedback}
            """,
        ),])

        chain = prompt | self.llm.with_structured_output(GeneratedSQL)
        raw_generated = chain.invoke(
            {
                "schema": state.get("schema", ""),
                "question": state.get("question", ""),
                "feedback": feedback,
            }
        )
        generated: GeneratedSQL = (
            raw_generated
            if isinstance(raw_generated, GeneratedSQL)
            else GeneratedSQL.model_validate(raw_generated)
        )

        return {
            "attempts": attempts,
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
        sql = state.get("sql")
        if not sql:
            return {"is_valid": False, "error": "No SQL was generated."}

        try:
            safe_sql = validate_select_sql(sql)
            return {"sql": safe_sql, "is_valid": True, "error": None}
        except SQLSafetyError as exc:
            return {
                "is_valid": False,
                "error": f"Safety validation failed for SQL `{state.get('sql', '')}`: {exc}",
            }

    def _execute_sql(self, state: AgentState) -> AgentState:
        sql = state.get("sql")
        if not sql:
            return {"columns": [], "rows": [], "error": "No SQL was available to execute."}

        try:
            columns, rows = execute_read_only_sql(
                self.engine,
                sql,
                self.settings.max_result_rows,
                self.settings.sql_statement_timeout_ms,
            )
            return {"columns": columns, "rows": rows, "error": None}
        except Exception as exc:
            return {
                "columns": [],
                "rows": [],
                "error": f"Database execution failed for SQL `{state.get('sql', '')}`: {exc}",
            }

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
