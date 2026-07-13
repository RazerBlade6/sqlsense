import pytest

from app.safety import SQLSafetyError, validate_select_sql


@pytest.mark.parametrize(
    "sql",
    [
        "select count(*) from public.users",
        "WITH recent_users AS (SELECT * FROM public.users) SELECT count(*) FROM recent_users",
        "SELECT date(created_at), count(*) FROM public.users GROUP BY 1 ORDER BY 1",
    ],
)
def test_allows_select_queries(sql: str) -> None:
    assert validate_select_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "DELETE FROM users",
        "UPDATE users SET email = 'x'",
        "SELECT * INTO new_table FROM users",
        "SELECT * FROM users; DELETE FROM users",
        "SELECT pg_sleep(10)",
        "SELECT * FROM users -- hide something",
    ],
)
def test_rejects_unsafe_queries(sql: str) -> None:
    with pytest.raises(SQLSafetyError):
        validate_select_sql(sql)
