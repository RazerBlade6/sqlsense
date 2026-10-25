import pytest

from app.safety import SQLSafetyError, validate_select_sql

TABLES = {"fact_transactions", "dim_product", "dim_date"}


def validate(sql: str, max_rows: int | None = None) -> str:
    return validate_select_sql(sql, TABLES, "retail", max_rows=max_rows)


@pytest.mark.parametrize(
    "sql",
    [
        "select count(*) from fact_transactions",
        "SELECT p.department, sum(t.sales_value) FROM retail.fact_transactions t "
        "JOIN dim_product p ON t.product_id = p.product_id WHERE t.week BETWEEN 40 AND 53 GROUP BY 1",
        "WITH weekly AS (SELECT week, sum(sales_value) s FROM fact_transactions GROUP BY 1) "
        "SELECT * FROM weekly ORDER BY week",
        "SELECT date_format(date_day, '%Y-%m') AS m FROM awsdatacatalog.retail.dim_date",
        "SELECT x.n FROM dim_date CROSS JOIN UNNEST(ARRAY[1, 2]) AS x(n)",
        "SELECT 'update the comment' AS note FROM dim_date",
        "SELECT 'a -- b /* c */' AS literal FROM dim_date",
    ],
)
def test_allows_read_queries(sql: str) -> None:
    assert validate(sql)


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("DROP TABLE fact_transactions", "only SELECT"),
        ("DELETE FROM fact_transactions", "only SELECT"),
        ("INSERT INTO dim_date SELECT * FROM dim_date", "only SELECT"),
        ("CREATE TABLE x AS SELECT * FROM dim_date", "only SELECT"),
        ("SELECT * FROM dim_date; DROP TABLE dim_date", "exactly one"),
        ("SELECT * FROM dim_date -- hide", "comments"),
        ("SELECT /* hide */ * FROM dim_date", "comments"),
        ("SELECT * FROM users", "unknown table"),
        ("SELECT * FROM information_schema.tables", "database information_schema"),
        ("SELECT * FROM other_db.dim_date", "database other_db"),
        ("SELECT * FROM read_csv('/etc/passwd')", "table function"),
        ("SELECT * FROM read_parquet('s3://bucket/*.parquet')", "table function"),
        ("", "empty"),
    ],
)
def test_rejects_unsafe_queries(sql: str, reason: str) -> None:
    with pytest.raises(SQLSafetyError, match=reason):
        validate(sql)


def test_adds_limit_when_missing() -> None:
    assert validate("SELECT * FROM dim_date", max_rows=50).endswith("LIMIT 50")


def test_keeps_existing_limit() -> None:
    assert validate("SELECT * FROM dim_date LIMIT 5", max_rows=50).endswith("LIMIT 5")
