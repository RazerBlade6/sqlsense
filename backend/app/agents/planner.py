from dataclasses import dataclass

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import Settings
from app.llm import LLMCall, invoke_structured, with_structured_output
from app.models import Route

SYSTEM_PROMPT = """You are the planner of a retail analytics assistant. The assistant has two sources:
1. A SQL data warehouse of one year (2017) of grocery transactions, products, households, promotions, campaigns and coupons.
2. Business documents: metric definitions, policies (fiscal calendar, reporting rules, privacy) and campaign briefs.

Warehouse tables:
{tables}

Terms the documents define:
{glossary}

Choose one route for the latest question:
- sql: the tables alone answer it: counts, totals, rankings, trends, comparisons. Choose this when no documented term, period or target is involved.
- docs: it asks what something means or what a policy, campaign objective, audience or target is, and needs no numbers from the data.
- both: it needs numbers from the warehouse and also a documented term, period or target, for example an "active household" count, sales in a fiscal quarter or the holiday period, or whether a campaign met its target.
- clarify: it is too vague to answer even with the conversation so far, for example "how did it do?" with no earlier topic.
- refuse: it asks to change, delete or export data, to identify or contact a household, or is unrelated to retail analytics.

Also:
- standalone_question: rewrite the latest question so it can be understood without the conversation, resolving words like "it", "that" or "the bottom 5 instead". Keep it unchanged if it already stands alone.
- needs_definitions: the documented terms the question depends on, copied from the list above (empty for sql).
- message: for clarify, the question to ask the user; for refuse, a one-sentence reason. Otherwise empty."""

HUMAN_PROMPT = """Conversation so far:
{history}

Latest question: {question}"""


class Plan(BaseModel):
    """How the assistant should answer the latest question."""

    route: Route
    standalone_question: str = Field(description="The question rewritten to stand alone.")
    needs_definitions: list[str] = Field(
        default_factory=list, description="Documented terms the question depends on."
    )
    # A plain string, not Optional: Nova Micro emits malformed tool calls for nullable fields.
    message: str = Field(
        default="", description="Clarifying question (clarify) or reason (refuse); else empty."
    )


@dataclass
class HistoryTurn:
    question: str
    answer: str
    sql: str | None = None


class Planner:
    def __init__(self, settings: Settings, tables: str, glossary: str):
        self.llm = with_structured_output(settings.planner_model_id, Plan, settings)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
        ).partial(tables=tables, glossary=glossary)

    def plan(self, question: str, history: list[HistoryTurn]) -> LLMCall[Plan]:
        return invoke_structured(
            self.prompt | self.llm,
            {"question": question, "history": format_history(history)},
            Plan,
        )


def format_history(history: list[HistoryTurn]) -> str:
    if not history:
        return "none"
    lines = []
    for turn in history:
        lines.append(f"User: {turn.question}")
        if turn.sql:
            lines.append(f"SQL used: {turn.sql}")
        lines.append(f"Assistant: {turn.answer}")
    return "\n".join(lines)
