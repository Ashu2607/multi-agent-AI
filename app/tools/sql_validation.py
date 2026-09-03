"""SQL validation gate (Policy 3: SQL queries must be validated).

Every query produced by the Text-to-SQL step must pass through
`validate_sql` before it is ever executed against sales.db. The gate:
  - allows only a single read-only SELECT statement
  - blocks DDL/DML keywords, comments, and statement stacking
  - restricts FROM/JOIN targets to a table whitelist
  - enforces a row LIMIT so a single query can't dump the whole database
"""
from __future__ import annotations

import re

from app.schemas import SQLValidationResult

ALLOWED_TABLES = {
    "competitors",
    "products",
    "quarterly_sales",
    "market_news",
    "pricing_comparison",
}

_FORBIDDEN_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "REPLACE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "VACUUM",
    "REINDEX",
    "TRIGGER",
)

_TABLE_REF_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


def validate_sql(raw_sql: str, row_limit: int = 200) -> SQLValidationResult:
    violations: list[str] = []
    sql = (raw_sql or "").strip()

    if not sql:
        return SQLValidationResult(is_valid=False, violations=["empty query"])

    # Strip a single trailing semicolon; reject anything with more statements.
    stripped = sql.rstrip()
    if stripped.endswith(";"):
        stripped = stripped[:-1]
    if ";" in stripped:
        violations.append("multiple statements are not allowed")

    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        violations.append("SQL comments are not allowed")

    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        violations.append("only SELECT statements are allowed")

    upper = stripped.upper()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            violations.append(f"forbidden keyword: {keyword}")

    referenced_tables = {m.group(1).lower() for m in _TABLE_REF_RE.finditer(stripped)}
    if not referenced_tables:
        violations.append("could not determine referenced table(s)")
    else:
        disallowed = referenced_tables - ALLOWED_TABLES
        if disallowed:
            violations.append(f"table(s) not permitted: {', '.join(sorted(disallowed))}")

    if violations:
        return SQLValidationResult(is_valid=False, violations=violations)

    sanitized = stripped
    if not re.search(r"\bLIMIT\s+\d+\b", sanitized, re.IGNORECASE):
        sanitized = f"{sanitized} LIMIT {row_limit}"

    return SQLValidationResult(is_valid=True, sanitized_sql=sanitized, violations=[])
