"""Run the eval suite against the SQL agent and report execution accuracy.

uv run python -m evaluation.runner                      # local DuckDB warehouse
WAREHOUSE=athena uv run python -m evaluation.runner     # Athena
uv run python -m evaluation.runner --only q04 q12 --min-accuracy 0.6
"""

import argparse
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.agents.sql_agent import SQLQueryAgent
from app.config import Settings
from app.safety import validate_select_sql
from app.warehouse import Warehouse
from app.warehouse.catalog import load_catalog, table_names
from app.warehouse.factory import build_warehouse
from evaluation.scoring import score

REPO = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONS = REPO / "evals" / "questions.yaml"
DEFAULT_RESULTS = REPO / "evals" / "results"
GOLD_MAX_ROWS = 1000


def run_question(
    question: dict[str, Any], agent: SQLQueryAgent, warehouse: Warehouse, settings: Settings
) -> dict[str, Any]:
    catalog = load_catalog(settings.catalog_path)
    gold_sql = validate_select_sql(question["gold_sql"], table_names(catalog), catalog["database"])
    gold = warehouse.run(gold_sql, GOLD_MAX_ROWS)

    started = time.perf_counter()
    try:
        response = agent.run(question["question"])
    except Exception as exc:  # an eval run reports agent crashes rather than stopping
        return _record(question, False, f"agent error: {exc}", time.perf_counter() - started)
    latency_s = time.perf_counter() - started

    if response.error:
        correct, reason = False, f"no result: {response.error}"
    else:
        correct, reason = score(
            gold.rows,
            response.rows,
            question.get("compare", gold.columns),
            response.columns,
            ordered=question.get("ordered", False),
        )
    return _record(
        question,
        correct,
        reason,
        latency_s,
        sql=response.sql,
        attempts=response.attempts,
        bytes_scanned=response.bytes_scanned,
    )


def _record(question: dict, correct: bool, reason: str, latency_s: float, **extra) -> dict:
    return {
        "id": question["id"],
        "category": question["category"],
        "question": question["question"],
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
    return {
        **meta,
        "questions": len(results),
        "correct": sum(r["correct"] for r in results),
        "accuracy": round(sum(r["correct"] for r in results) / len(results), 4),
        "by_category": {
            c: {"correct": sum(v), "total": len(v)} for c, v in sorted(by_category.items())
        },
        "latency_p50_s": latencies[len(latencies) // 2],
        "latency_max_s": latencies[-1],
        "avg_attempts": round(sum(attempts) / len(attempts), 2) if attempts else None,
    }


def to_markdown(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    lines = [
        f"### SQL agent eval: {summary['correct']}/{summary['questions']} "
        f"({summary['accuracy']:.0%})",
        "",
        f"Model `{summary['sql_model_id']}` · warehouse `{summary['warehouse']}` · "
        f"p50 latency {summary['latency_p50_s']}s · avg attempts {summary['avg_attempts']}",
        "",
        "| Category | Correct |",
        "|---|---|",
    ]
    lines += [f"| {c} | {v['correct']}/{v['total']} |" for c, v in summary["by_category"].items()]
    failures = [r for r in results if not r["correct"]]
    if failures:
        lines += ["", "| Failed | Question | Reason |", "|---|---|---|"]
        lines += [f"| {r['id']} | {r['question']} | {r['reason'][:120]} |" for r in failures]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--only", nargs="*", help="question ids to run")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--min-accuracy", type=float, default=0.0, help="exit 1 below this")
    args = parser.parse_args()

    settings = Settings()
    warehouse = build_warehouse(settings)
    agent = SQLQueryAgent(warehouse, settings)
    questions = yaml.safe_load(args.questions.read_text())["questions"]
    if args.only:
        questions = [q for q in questions if q["id"] in set(args.only)]

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda q: run_question(q, agent, warehouse, settings), questions))

    meta = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sql_model_id": settings.sql_model_id,
        "warehouse": warehouse.engine,
        "git_sha": os.environ.get("GITHUB_SHA"),
    }
    summary = summarize(results, meta)
    markdown = to_markdown(summary, results)
    print(markdown)

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_file = args.out / f"{stamp}-{warehouse.engine}.json"
    out_file.write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str))
    print(f"wrote {out_file}")
    if step_summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(step_summary, "a") as fh:
            fh.write(markdown)

    if summary["accuracy"] < args.min_accuracy:
        raise SystemExit(f"accuracy {summary['accuracy']:.0%} is below {args.min_accuracy:.0%}")


if __name__ == "__main__":
    main()
