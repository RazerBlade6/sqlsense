"""Supervisor graph: plan → (retrieve) → (SQL agent) → synthesize, with a trace of every step."""

import operator
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.planner import HistoryTurn, Plan, Planner
from app.agents.sql_agent import SQLQueryAgent
from app.agents.synthesizer import Synthesizer, format_documents
from app.config import Settings
from app.models import ChatResponse, Citation, QueryResponse, TraceStep
from app.retrieval import Retriever
from app.retrieval.corpus import defined_terms, find_terms, glossary, load_corpus
from app.warehouse import Warehouse
from app.warehouse.catalog import load_catalog

DEFAULT_MESSAGES = {
    "clarify": "Could you say a bit more about what you'd like to know?",
    "refuse": "I can only answer read-only questions about the retail data and its documentation.",
}


class GraphState(TypedDict, total=False):
    question: str
    history: list[HistoryTurn]
    plan: Plan
    citations: list[Citation]
    result: QueryResponse | None
    answer: str
    trace: Annotated[list[TraceStep], operator.add]


class Assistant:
    def __init__(self, warehouse: Warehouse, retriever: Retriever, settings: Settings):
        self.settings = settings
        self.retriever = retriever
        self.sql_agent = SQLQueryAgent(warehouse, settings)
        catalog = load_catalog(settings.catalog_path)
        tables = "\n".join(f"- {t['name']}: {t['description']}" for t in catalog["tables"])
        docs = load_corpus(settings.corpus_path)
        self.terms = defined_terms(docs)
        self.planner = Planner(settings, tables, glossary(docs))
        self.synthesizer = Synthesizer(settings)
        self.graph = self._build_graph()

    def ask(
        self, question: str, history: list[HistoryTurn] | None = None, session_id: str = "local"
    ) -> ChatResponse:
        started = time.perf_counter()
        state: GraphState = self.graph.invoke(
            {"question": question, "history": history or [], "trace": []}
        )
        plan = state["plan"]
        result = state.get("result")
        return ChatResponse(
            session_id=session_id,
            question=question,
            standalone_question=plan.standalone_question,
            route=plan.route,
            answer=state.get("answer", ""),
            citations=state.get("citations", []),
            result=result,
            trace=state["trace"],
            total_ms=int((time.perf_counter() - started) * 1000),
            error=result.error if result else None,
        )

    def _build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("plan", self._plan)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("query", self._query)
        graph.add_node("synthesize", self._synthesize)
        graph.add_node("respond", self._respond)

        graph.set_entry_point("plan")
        graph.add_conditional_edges(
            "plan",
            lambda s: s["plan"].route,
            {
                "sql": "query",
                "docs": "retrieve",
                "both": "retrieve",
                "clarify": "respond",
                "refuse": "respond",
            },
        )
        graph.add_conditional_edges(
            "retrieve",
            lambda s: "query" if s["plan"].route == "both" else "synthesize",
            {"query": "query", "synthesize": "synthesize"},
        )
        graph.add_edge("query", "synthesize")
        graph.add_edge("synthesize", END)
        graph.add_edge("respond", END)
        return graph.compile()

    def _plan(self, state: GraphState) -> GraphState:
        call = self.planner.plan(state["question"], state.get("history", []))
        plan = call.output
        if not plan.standalone_question.strip():
            plan.standalone_question = state["question"]
        # Guard the LLM router: a documented metric or period means the SQL needs its definition.
        matched = find_terms(f"{state['question']}\n{plan.standalone_question}", self.terms)
        upgraded = plan.route == "sql" and bool(matched)
        if upgraded:
            plan.route = "both"
        plan.needs_definitions = list(dict.fromkeys([*plan.needs_definitions, *matched]))
        step = TraceStep(
            step="planner",
            label=f"Route: {plan.route}",
            duration_ms=call.duration_ms,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            detail={
                "route": plan.route,
                "standalone_question": plan.standalone_question,
                "needs_definitions": plan.needs_definitions,
                "upgraded_by_glossary": upgraded,
            },
        )
        return {"plan": plan, "trace": [step]}

    def _retrieve(self, state: GraphState) -> GraphState:
        plan = state["plan"]
        queries = [plan.standalone_question, *plan.needs_definitions]
        started = time.perf_counter()
        hits = self.retriever.search(queries, k=self.settings.retrieval_k)
        citations = [
            Citation(
                id=i,
                chunk_id=h.chunk.chunk_id,
                doc_id=h.chunk.doc_id,
                doc_type=h.chunk.doc_type,
                title=h.chunk.title,
                heading=h.chunk.heading,
                path=h.chunk.path,
                content=h.chunk.content,
                score=round(h.score, 5),
            )
            for i, h in enumerate(hits, start=1)
        ]
        step = TraceStep(
            step="retrieval",
            label=f"{len(citations)} chunks from {self.retriever.store.engine}",
            duration_ms=int((time.perf_counter() - started) * 1000),
            detail={
                "queries": queries,
                "hits": [
                    {
                        "doc_id": h.chunk.doc_id,
                        "title": h.chunk.title,
                        "vector_rank": h.vector_rank,
                        "keyword_rank": h.keyword_rank,
                        "score": round(h.score, 5),
                    }
                    for h in hits
                ],
            },
        )
        return {"citations": citations, "trace": [step]}

    def _query(self, state: GraphState) -> GraphState:
        plan = state["plan"]
        context = format_documents(state.get("citations", [])) if plan.route == "both" else None
        result = self.sql_agent.run(plan.standalone_question, context=context)
        steps = [
            TraceStep(
                step="sql",
                label=f"SQL attempt {a.attempt}: {a.status}",
                status="ok" if a.status == "succeeded" else a.status,
                duration_ms=(a.generate_ms or 0) + (a.execution_ms or 0),
                input_tokens=a.input_tokens,
                output_tokens=a.output_tokens,
                bytes_scanned=a.bytes_scanned,
                detail={"sql": a.sql, "error": a.error, "engine": result.engine},
            )
            for a in result.attempt_log
        ]
        return {"result": result, "trace": steps}

    def _synthesize(self, state: GraphState) -> GraphState:
        citations = state.get("citations", [])
        call = self.synthesizer.answer(
            state["plan"].standalone_question, citations, state.get("result")
        )
        cited = set(call.output.cited)
        if cited:
            citations = [c for c in citations if c.id in cited]
        step = TraceStep(
            step="synthesizer",
            label="Answer",
            duration_ms=call.duration_ms,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            detail={"cited": sorted(cited)},
        )
        return {"answer": call.output.answer, "citations": citations, "trace": [step]}

    def _respond(self, state: GraphState) -> GraphState:
        plan = state["plan"]
        return {"answer": plan.message or DEFAULT_MESSAGES[plan.route]}
