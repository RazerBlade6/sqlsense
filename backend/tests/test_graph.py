"""Routing through the supervisor graph, with the LLM-backed agents replaced by stubs."""

import pytest

from app.agents.planner import Plan
from app.agents.synthesizer import Answer
from app.config import Settings
from app.graph import Assistant
from app.llm import LLMCall
from app.models import Attempt, QueryResponse
from app.retrieval.corpus import chunk_corpus, load_corpus
from app.retrieval.retriever import Retriever
from app.retrieval.store import LocalChunkStore
from tests.fakes import HashEmbedder


class StubWarehouse:
    engine = "stub"

    def schema_summary(self) -> str:
        return "tables"


def call(output) -> LLMCall:
    return LLMCall(output=output, input_tokens=10, output_tokens=5, duration_ms=7)


@pytest.fixture
def assistant(monkeypatch: pytest.MonkeyPatch) -> Assistant:
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    embedder = HashEmbedder()
    retriever = Retriever(LocalChunkStore(chunk_corpus(load_corpus()), embedder), embedder)
    return Assistant(StubWarehouse(), retriever, Settings())


def stub_agents(monkeypatch, assistant: Assistant, plan: Plan) -> dict:
    seen: dict = {}
    monkeypatch.setattr(assistant.planner, "plan", lambda q, h: call(plan))

    def run_sql(question, max_attempts=3, context=None):
        seen["sql_question"], seen["context"] = question, context
        return QueryResponse(
            question=question,
            sql="SELECT 1",
            columns=["n"],
            rows=[{"n": 1}],
            attempts=1,
            attempt_log=[Attempt(attempt=1, sql="SELECT 1", status="succeeded", bytes_scanned=99)],
            engine="stub",
        )

    def answer(question, citations, result):
        seen["synth_citations"] = [c.id for c in citations]
        return call(Answer(answer="It is 1 [1].", cited=[1]))

    monkeypatch.setattr(assistant.sql_agent, "run", run_sql)
    monkeypatch.setattr(assistant.synthesizer, "answer", answer)
    return seen


def test_sql_route_skips_retrieval(monkeypatch, assistant: Assistant) -> None:
    seen = stub_agents(monkeypatch, assistant, Plan(route="sql", standalone_question="Total?"))

    response = assistant.ask("Total?")

    assert [t.step for t in response.trace] == ["planner", "sql", "synthesizer"]
    assert seen["context"] is None
    assert response.trace[1].bytes_scanned == 99


def test_both_route_passes_definitions_to_sql(monkeypatch, assistant: Assistant) -> None:
    plan = Plan(
        route="both",
        standalone_question="How many active households are there?",
        needs_definitions=["active household"],
    )
    seen = stub_agents(monkeypatch, assistant, plan)

    response = assistant.ask("How many active households?")

    assert [t.step for t in response.trace] == ["planner", "retrieval", "sql", "synthesizer"]
    assert "weeks 46 to 53" in seen["context"]
    assert seen["sql_question"] == "How many active households are there?"
    assert [c.id for c in response.citations] == [1]


def test_docs_route_never_queries(monkeypatch, assistant: Assistant) -> None:
    seen = stub_agents(monkeypatch, assistant, Plan(route="docs", standalone_question="Q?"))

    response = assistant.ask("Q?")

    assert "sql_question" not in seen
    assert response.result is None and response.citations


@pytest.mark.parametrize("route", ["refuse", "clarify"])
def test_refuse_and_clarify_stop_after_planning(monkeypatch, assistant, route) -> None:
    seen = stub_agents(
        monkeypatch, assistant, Plan(route=route, standalone_question="x", message="No.")
    )

    response = assistant.ask("x")

    assert response.answer == "No."
    assert [t.step for t in response.trace] == ["planner"] and not seen
