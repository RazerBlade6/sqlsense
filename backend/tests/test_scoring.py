from datetime import date

from evaluation.scoring import score

GOLD = [{"department": "GROCERY", "sales": 100.0}, {"department": "MEAT", "sales": 50.0}]
GOLD_COLS = ["department", "sales"]


def test_accepts_aliases_extra_columns_and_column_order() -> None:
    pred = [
        {"total": 100.004, "dept": "GROCERY", "share": 0.66},
        {"total": 50.0, "dept": "MEAT", "share": 0.33},
    ]
    assert score(GOLD, pred, GOLD_COLS, ["total", "dept", "share"]) == (True, "ok")


def test_unordered_ignores_row_order() -> None:
    assert score(GOLD, list(reversed(GOLD)), GOLD_COLS, GOLD_COLS)[0]


def test_ordered_requires_row_order() -> None:
    correct, reason = score(GOLD, list(reversed(GOLD)), GOLD_COLS, GOLD_COLS, ordered=True)
    assert not correct and reason == "rows are in the wrong order"


def test_rejects_wrong_values_and_row_counts() -> None:
    wrong = [{"department": "GROCERY", "sales": 90.0}, {"department": "MEAT", "sales": 50.0}]
    assert not score(GOLD, wrong, GOLD_COLS, GOLD_COLS)[0]
    assert score(GOLD, GOLD[:1], GOLD_COLS, GOLD_COLS) == (False, "row count 1 != expected 2")


def test_rejects_misaligned_rows_even_when_columns_match() -> None:
    swapped = [{"department": "GROCERY", "sales": 50.0}, {"department": "MEAT", "sales": 100.0}]
    assert not score(GOLD, swapped, GOLD_COLS, GOLD_COLS)[0]


def test_compare_subset_skips_label_format() -> None:
    gold = [{"month": 1, "sales": 10.0}, {"month": 2, "sales": 20.0}]
    pred = [{"month": "January", "sales": 10.0}, {"month": "February", "sales": 20.0}]
    assert score(gold, pred, ["sales"], ["month", "sales"], ordered=True)[0]
    assert not score(gold, pred, ["month", "sales"], ["month", "sales"], ordered=True)[0]


def test_tolerance_and_types() -> None:
    gold = [{"d": date(2017, 1, 1), "n": 3, "v": 28.42}]
    pred = [{"d": date(2017, 1, 1), "n": 3.0, "v": 28.415}]
    assert score(gold, pred, ["d", "n", "v"], ["d", "n", "v"])[0]
