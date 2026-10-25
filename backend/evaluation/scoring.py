"""Execution-accuracy scoring: does the agent's result contain the gold result?

The agent may alias, reorder or add columns. Each gold column in `compare` must match a distinct
agent column by value; then rows are compared as a multiset, or in order for ordered questions.
"""

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

ABS_TOL = 0.01
REL_TOL = 1e-4


def normalize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float | Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value).strip()


def values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def _sort_key(value: Any) -> tuple:
    # Floats are rounded so tolerance-equal values sort together.
    if value is None:
        return (0, "")
    if isinstance(value, float):
        return (1, round(value, 2))
    return (2, str(value))


def _column(rows: list[dict[str, Any]], name: str) -> list[Any]:
    return [normalize(row.get(name)) for row in rows]


def _same_values(gold: list[Any], pred: list[Any], ordered: bool) -> bool:
    if not ordered:
        gold, pred = sorted(gold, key=_sort_key), sorted(pred, key=_sort_key)
    return all(values_equal(g, p) for g, p in zip(gold, pred, strict=True))


def match_columns(
    gold_rows: list[dict[str, Any]],
    pred_rows: list[dict[str, Any]],
    gold_columns: list[str],
    pred_columns: list[str],
) -> dict[str, str] | None:
    """Map each gold column to an unused agent column holding the same values, or None.

    Matching ignores row order; order is checked afterwards on whole rows.
    """
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for gold_col in gold_columns:
        gold_values = _column(gold_rows, gold_col)
        for pred_col in pred_columns:
            if pred_col in used:
                continue
            if _same_values(gold_values, _column(pred_rows, pred_col), ordered=False):
                mapping[gold_col] = pred_col
                used.add(pred_col)
                break
        else:
            return None
    return mapping


def score(
    gold_rows: list[dict[str, Any]],
    pred_rows: list[dict[str, Any]],
    gold_columns: list[str],
    pred_columns: list[str],
    ordered: bool = False,
) -> tuple[bool, str]:
    """Return (correct, reason)."""
    if len(gold_rows) != len(pred_rows):
        return False, f"row count {len(pred_rows)} != expected {len(gold_rows)}"
    mapping = match_columns(gold_rows, pred_rows, gold_columns, pred_columns)
    if mapping is None:
        return False, "no column in the result matches an expected column"

    def tuples(rows: list[dict[str, Any]], columns: list[str]) -> list[tuple]:
        return [tuple(normalize(row.get(c)) for c in columns) for row in rows]

    gold_tuples = tuples(gold_rows, gold_columns)
    pred_tuples = tuples(pred_rows, [mapping[c] for c in gold_columns])
    if not ordered:
        row_key = lambda row: tuple(_sort_key(v) for v in row)  # noqa: E731
        gold_tuples, pred_tuples = (
            sorted(gold_tuples, key=row_key),
            sorted(pred_tuples, key=row_key),
        )
    aligned = all(
        all(values_equal(g, p) for g, p in zip(gt, pt, strict=True))
        for gt, pt in zip(gold_tuples, pred_tuples, strict=True)
    )
    if aligned:
        return True, "ok"
    return False, "rows are in the wrong order" if ordered else "rows don't match the expected rows"
