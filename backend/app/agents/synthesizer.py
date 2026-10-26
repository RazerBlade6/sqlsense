import json
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm import LLMCall, invoke_structured, with_structured_output
from app.models import Citation, QueryResponse

SYSTEM_PROMPT = """You write the final answer of a retail analytics assistant for a business user.

- Answer the question directly in the first sentence, using the numbers from the query result exactly as given. Never invent or estimate numbers.
- When the result has several rows, summarise the main points in at most 4 short bullets; the user also sees the full table and a chart.
- When a document defines the metric, period or target used, say so briefly and cite it with its marker, like [1]. Cite only documents you actually used.
- When the question asks about a target, state the target and the actual number, then whether the actual is above or below the target. Compare the numbers carefully.
- If the query failed or returned no rows, say that the data could not answer the question and why, in one sentence.
- Plain, concise language. No preamble, and do not repeat the SQL."""

HUMAN_PROMPT = """Question: {question}

Documents:
{documents}

Query result:
{result}"""

RESULT_ROWS_SHOWN = 25


class Answer(BaseModel):
    """The final answer shown to the user."""

    answer: str = Field(description="Markdown answer, citing documents as [n].")
    cited: list[int] = Field(default_factory=list, description="Markers of documents used.")


class Synthesizer:
    def __init__(self, settings: Settings):
        self.llm = with_structured_output(settings.synthesizer_model_id, Answer, settings)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
        )

    def answer(
        self, question: str, citations: list[Citation], result: QueryResponse | None
    ) -> LLMCall[Answer]:
        return invoke_structured(
            self.prompt | self.llm,
            {
                "question": question,
                "documents": format_documents(citations),
                "result": format_result(result),
            },
            Answer,
        )


def format_documents(citations: list[Citation]) -> str:
    if not citations:
        return "none"
    return "\n\n".join(f"[{c.id}] {c.title} ({c.path})\n{c.content}" for c in citations)


def format_result(result: QueryResponse | None) -> str:
    if result is None:
        return "not queried"
    if result.error:
        return f"The query failed: {result.error}"
    rows: list[dict[str, Any]] = result.rows[:RESULT_ROWS_SHOWN]
    lines = [f"SQL: {result.sql}", f"Columns: {', '.join(result.columns)}"]
    lines += [json.dumps(row, default=str) for row in rows]
    hidden = len(result.rows) - len(rows)
    if hidden > 0 or result.truncated:
        lines.append(f"(more rows not shown: {max(hidden, 0)} here, truncated={result.truncated})")
    if not result.rows:
        lines.append("(no rows)")
    return "\n".join(lines)
