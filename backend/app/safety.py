"""Static checks on generated SQL before it reaches the warehouse.

Checks run on the parsed syntax tree (Athena dialect), not on keywords, so a column or string
that happens to contain "update" is fine while any write, DDL or file access is rejected.
"""

import sqlglot
from sqlglot import exp


class SQLSafetyError(ValueError):
    """Raised when generated SQL is not safe to execute."""


READ_ONLY_ROOTS = (exp.Select, exp.Union, exp.Except, exp.Intersect, exp.Subquery)

WRITE_NODES = (
    exp.Alter,
    exp.Command,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Into,
    exp.Merge,
    exp.TruncateTable,
    exp.Update,
)


def validate_select_sql(
    sql: str, allowed_tables: set[str], database: str, max_rows: int | None = None
) -> str:
    """Return normalized Athena SQL, or raise SQLSafetyError.

    allowed_tables: catalog table names; every table reference must be one of these or a CTE.
    max_rows: if given, a LIMIT is added to the outermost query when it has none.
    """
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise SQLSafetyError("empty SQL is not allowed")
    try:
        # Tokenizing (not substring matching) so '--' or '/*' inside a string literal is fine.
        if any(token.comments for token in sqlglot.tokenize(cleaned, read="athena")):
            raise SQLSafetyError("comments are not allowed in generated SQL")
        statements = [s for s in sqlglot.parse(cleaned, read="athena") if s is not None]
    except sqlglot.errors.SqlglotError as exc:
        raise SQLSafetyError(f"SQL could not be parsed: {exc}") from exc
    if len(statements) != 1:
        raise SQLSafetyError("exactly one SQL statement is required")

    expression = statements[0]
    if not isinstance(expression, READ_ONLY_ROOTS):
        raise SQLSafetyError("only SELECT queries are allowed")

    for node in expression.walk():
        if isinstance(node, WRITE_NODES):
            raise SQLSafetyError(f"{node.key.upper()} is not allowed")

    _check_tables(expression, allowed_tables, database)

    if (
        max_rows is not None
        and isinstance(expression, exp.Select)
        and not expression.args.get("limit")
    ):
        expression = expression.limit(max_rows)

    return expression.sql(dialect="athena")


def _check_tables(expression: exp.Expression, allowed_tables: set[str], database: str) -> None:
    cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
    allowed = {name.lower() for name in allowed_tables}
    for table in expression.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            # Table functions such as read_csv(...) parse as tables with a function body.
            raise SQLSafetyError(f"table function {table.this.sql()} is not allowed")
        name = table.name.lower()
        if table.catalog and table.catalog.lower() != "awsdatacatalog":
            raise SQLSafetyError(f"catalog {table.catalog} is not allowed")
        if table.db and table.db.lower() != database.lower():
            raise SQLSafetyError(f"database {table.db} is not allowed; use {database}")
        if name in cte_names and not table.db:
            continue
        if name not in allowed:
            raise SQLSafetyError(f"unknown table {name}; available: {', '.join(sorted(allowed))}")
