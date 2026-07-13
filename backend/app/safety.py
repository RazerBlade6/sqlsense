import re

import sqlglot
from sqlglot import exp


class SQLSafetyError(ValueError):
    """Raised when generated SQL is not safe to execute."""


FORBIDDEN_KEYWORDS = {
    "ALTER",
    "ANALYZE",
    "CALL",
    "COMMENT",
    "COMMIT",
    "COPY",
    "CREATE",
    "DEALLOCATE",
    "DELETE",
    "DO",
    "DROP",
    "EXECUTE",
    "EXPLAIN",
    "GRANT",
    "INSERT",
    "LISTEN",
    "LOCK",
    "MERGE",
    "NOTIFY",
    "PREPARE",
    "REASSIGN",
    "REFRESH",
    "REINDEX",
    "RESET",
    "REVOKE",
    "ROLLBACK",
    "SECURITY",
    "SET",
    "TRUNCATE",
    "UNLISTEN",
    "UPDATE",
    "VACUUM",
}

FORBIDDEN_EXPRESSION_NAMES = {
    "Alter",
    "Command",
    "Create",
    "Delete",
    "Drop",
    "Insert",
    "Into",
    "Merge",
    "TruncateTable",
    "Update",
}

FORBIDDEN_FUNCTIONS = {
    "dblink",
    "dblink_exec",
    "lo_export",
    "lo_import",
    "pg_advisory_lock",
    "pg_advisory_xact_lock",
    "pg_read_binary_file",
    "pg_read_file",
    "pg_reload_conf",
    "pg_sleep",
    "pg_terminate_backend",
}


def validate_select_sql(sql: str) -> str:
    cleaned = _normalize_sql(sql)

    if _has_comments(cleaned):
        raise SQLSafetyError("comments are not allowed in generated SQL")

    if ";" in cleaned.rstrip(";"):
        raise SQLSafetyError("multiple SQL statements are not allowed")

    cleaned = cleaned.rstrip(";").strip()
    _reject_forbidden_keywords(cleaned)

    try:
        parsed_statements = sqlglot.parse(cleaned, read="postgres")
    except sqlglot.errors.SqlglotError as exc:
        raise SQLSafetyError(f"SQL could not be parsed: {exc}") from exc

    if len(parsed_statements) != 1:
        raise SQLSafetyError("exactly one SQL statement is required")

    expression = parsed_statements[0]
    if not _is_read_only_root(expression):
        raise SQLSafetyError("only SELECT-style read queries are allowed")

    for node in expression.walk():
        if node.__class__.__name__ in FORBIDDEN_EXPRESSION_NAMES:
            raise SQLSafetyError(f"{node.key.upper()} is not allowed")
        if isinstance(node, exp.Func):
            name = (node.name or node.sql_name()).lower()
            if name in FORBIDDEN_FUNCTIONS:
                raise SQLSafetyError(f"function {name} is not allowed")

    return cleaned


def _normalize_sql(sql: str) -> str:
    cleaned = sql.strip()
    if not cleaned:
        raise SQLSafetyError("empty SQL is not allowed")
    return cleaned


def _has_comments(sql: str) -> bool:
    return "--" in sql or "/*" in sql or "*/" in sql


def _reject_forbidden_keywords(sql: str) -> None:
    tokens = set(re.findall(r"\b[A-Z_]+\b", sql.upper()))
    blocked = sorted(tokens.intersection(FORBIDDEN_KEYWORDS))
    if blocked:
        raise SQLSafetyError(f"forbidden keyword found: {', '.join(blocked)}")


def _is_read_only_root(expression: exp.Expression) -> bool:
    return expression.__class__.__name__ in {"Select", "Subquery", "Union", "Except", "Intersect"}
