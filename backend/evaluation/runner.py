"""Run the eval suite through the whole assistant and report accuracy, routing and retrieval.

uv run python -m evaluation.runner                      # local DuckDB warehouse
WAREHOUSE=athena uv run python -m evaluation.runner     # Athena
uv run python -m evaluation.runner --only q04 q12 --min-accuracy 0.6
WAREHOUSE=athena uv run python -m evaluation.runner --api-url https://...lambda-url...on.aws/
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.agents.planner import HistoryTurn
from app.config import Settings
from app.graph import Assistant
from app.models import ChatResponse
from app.retrieval.factory import build_retriever
from app.safety import validate_select_sql
from app.warehouse import Warehouse
from app.warehouse.catalog import load_catalog, table_names
from app.warehouse.factory import build_warehouse
from evaluation.scoring import score

REPO = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONS = REPO / "evals" / "questions.yaml"
DEFAULT_RESULTS = REPO / "evals" / "results"
GOLD_MAX_ROWS = 1000


class ApiAssistant:
    """Asks a deployed API instead of an in-process Assistant, so the eval covers the real
    Lambda, pgvector and session memory. Earlier turns are replayed into a fresh session."""

    def __init__(self, url: str, timeout_s: int = 150):
        self.url = url.rstrip("/") + "/chat"
        self.timeout_s = timeout_s

    def ask(self, question: str, history: list[HistoryTurn]) -> ChatResponse:
        session_id = str(uuid.uuid4())
        for turn in history:
            self._post(turn.question, session_id)
        return ChatResponse.model_validate(self._post(question, session_id))

    def _post(self, question: str, session_id: str) -> dict[str, Any]:
        body = json.dumps({"question": question, "session_id": session_id}).encode()
        request = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}: {exc.read()[:300]!r}") from exc


def run_question(
    question: dict[str, Any],
    assistant: Assistant | ApiAssistant,
    warehouse: Warehouse,
    settings: Settings,
) -> dict[str, Any]:
    history = [HistoryTurn(t["question"], t["answer"]) for t in question.get("history", [])]
    started = time.perf_counter()
    try:
        response = assistant.ask(question["question"], history)
    except Exception as exc:  # an eval run reports agent crashes rather than stopping
        return _record(question, False, f"agent error: {exc}", time.perf_counter() - started)
    latency_s = time.perf_counter() - started

    if "gold_sql" in question:
        correct, reason = _score_sql(question, response, warehouse, settings)
    elif "answer_contains" in question:
        correct, reason = _score_answer(question["answer_contains"], response.answer)
    else:
        correct = route_ok(question, response.route)
        reason = "ok" if correct else f"routed to {response.route}"

    result = response.result
    return _record(
        question,
        correct,
        reason,
        latency_s,
        route=response.route,
        route_correct=route_ok(question, response.route),
        recall_at_5=_recall(question, response),
        sql=result.sql if result else None,
        attempts=result.attempts if result else None,
        bytes_scanned=result.bytes_scanned if result else None,
        tokens=sum((t.input_tokens or 0) + (t.output_tokens or 0) for t in response.trace),
        answer=response.answer,
    )


def route_ok(question: dict[str, Any], route: str) -> bool:
    expected = question["route"]
    return route in expected if isinstance(expected, list) else route == expected


def _score_sql(
    question: dict[str, Any], response: ChatResponse, warehouse: Warehouse, settings: Settings
) -> tuple[bool, str]:
    result = response.result
    if result is None:
        return False, f"no query: routed to {response.route}"
    if result.error:
        return False, f"no result: {result.error}"
    catalog = load_catalog(settings.catalog_path)
    gold_sql = validate_select_sql(question["gold_sql"], table_names(catalog), catalog["database"])
    gold = warehouse.run(gold_sql, GOLD_MAX_ROWS)
    return score(
        gold.rows,
        result.rows,
        question.get("compare", gold.columns),
        result.columns,
        ordered=question.get("ordered", False),
    )


def _score_answer(expected: list[str | list[str]], answer: str) -> tuple[bool, str]:
    text = answer.lower()
    for item in expected:
        options = item if isinstance(item, list) else [item]
        if not any(o.lower() in text for o in options):
            return False, f"answer lacks {options}: {answer[:200]}"
    return True, "ok"


def _recall(question: dict[str, Any], response: ChatResponse) -> float | None:
    """Share of the expected documents among everything retrieval returned (top 5)."""
    expected = question.get("docs")
    if not expected:
        return None
    retrieved = {
        hit["doc_id"]
        for step in response.trace
        if step.step == "retrieval"
        for hit in step.detail["hits"]
    }
    return sum(d in retrieved for d in expected) / len(expected)


def _record(question: dict, correct: bool, reason: str, latency_s: float, **extra) -> dict:
    return {
        "id": question["id"],
        "category": question["category"],
        "question": question["question"],
        "has_gold_sql": "gold_sql" in question,
        "correct": correct,
        "reason": reason,
        "latency_s": round(latency_s, 2),
        **extra,
    }


def summarize(results: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    by_category: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r["correct"])
    latencies = sorted(r["latency_s"] for r in results)
    attempts = [r["attempts"] for r in results if r.get("attempts")]
    routed = [r["route_correct"] for r in results if "route_correct" in r]
    recalls = [r["recall_at_5"] for r in results if r.get("recall_at_5") is not None]
    sql_scored = [r["correct"] for r in results if r.get("has_gold_sql")]
    tokens = [r["tokens"] for r in results if r.get("tokens")]
    return {
        **meta,
        "questions": len(results),
        "correct": sum(r["correct"] for r in results),
        "accuracy": round(sum(r["correct"] for r in results) / len(results), 4),
        "execution_accuracy": round(sum(sql_scored) / len(sql_scored), 4) if sql_scored else None,
        "routing_accuracy": round(sum(routed) / len(routed), 4) if routed else None,
        "recall_at_5": round(sum(recalls) / len(recalls), 4) if recalls else None,
        "avg_tokens": round(sum(tokens) / len(tokens)) if tokens else None,
        "by_category": {
            c: {"correct": sum(v), "total": len(v)} for c, v in sorted(by_category.items())
        },
        "latency_p50_s": latencies[len(latencies) // 2],
        "latency_max_s": latencies[-1],
        "avg_attempts": round(sum(attempts) / len(attempts), 2) if attempts else None,
    }


def to_markdown(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    def pct(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.0%}"

    lines = [
        f"### Assistant eval: {summary['correct']}/{summary['questions']} "
        f"({summary['accuracy']:.0%})",
        "",
        "| Execution accuracy | Routing accuracy | Retrieval recall@5 | p50 latency | Avg tokens |",
        "|---|---|---|---|---|",
        f"| {pct(summary['execution_accuracy'])} | {pct(summary['routing_accuracy'])} | "
        f"{pct(summary['recall_at_5'])} | {summary['latency_p50_s']}s | {summary['avg_tokens']} |",
        "",
        f"Models: SQL `{summary['sql_model_id']}`, planner `{summary['planner_model_id']}` · "
        f"warehouse `{summary['warehouse']}` · retrieval `{summary['retrieval_store']}`",
        "",
        "| Category | Correct |",
        "|---|---|",
    ]
    lines += [f"| {c} | {v['correct']}/{v['total']} |" for c, v in summary["by_category"].items()]
    failures = [r for r in results if not r["correct"]]
    if failures:
        lines += ["", "| Failed | Question | Reason |", "|---|---|---|"]
        lines += [
            f"| {r['id']} | {r['question']} | {r['reason'][:120].replace('|', '/')} |"
            for r in failures
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--only", nargs="*", help="question ids to run")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--api-url", help="evaluate a deployed API instead of in-process")
    parser.add_argument("--min-accuracy", type=float, default=0.0, help="exit 1 below this")
    args = parser.parse_args()

    settings = Settings()
    warehouse = build_warehouse(settings)
    assistant: Assistant | ApiAssistant
    if args.api_url:
        assistant, retrieval_store = ApiAssistant(args.api_url), "deployed API"
    else:
        retriever = build_retriever(settings)
        assistant, retrieval_store = (
            Assistant(warehouse, retriever, settings),
            retriever.store.engine,
        )
    questions = yaml.safe_load(args.questions.read_text())["questions"]
    if args.only:
        questions = [q for q in questions if q["id"] in set(args.only)]

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(
            pool.map(lambda q: run_question(q, assistant, warehouse, settings), questions)
        )

    meta = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sql_model_id": settings.sql_model_id,
        "planner_model_id": settings.planner_model_id,
        "retrieval_store": retrieval_store,
        "api_url": args.api_url,
        "warehouse": warehouse.engine,
        "git_sha": os.environ.get("GITHUB_SHA"),
    }
    summary = summarize(results, meta)
    markdown = to_markdown(summary, results)
    print(markdown)

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = "api" if args.api_url else warehouse.engine
    out_file = args.out / f"{stamp}-{target}.json"
    out_file.write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str))
    print(f"wrote {out_file}")
    if step_summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(step_summary, "a") as fh:
            fh.write(markdown)

    if summary["accuracy"] < args.min_accuracy:
        raise SystemExit(f"accuracy {summary['accuracy']:.0%} is below {args.min_accuracy:.0%}")


if __name__ == "__main__":
    main()
