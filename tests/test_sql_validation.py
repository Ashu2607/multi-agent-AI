from __future__ import annotations

import pytest

from app.tools.sql_validation import validate_sql


def test_valid_select_passes():
    result = validate_sql("SELECT company_name, market_share FROM competitors")
    assert result.is_valid
    assert "LIMIT" in result.sanitized_sql


def test_existing_limit_not_duplicated():
    result = validate_sql("SELECT * FROM competitors LIMIT 10")
    assert result.is_valid
    assert result.sanitized_sql.count("LIMIT") == 1


def test_join_across_whitelisted_tables_passes():
    sql = (
        "SELECT c.company_name, p.product_name FROM competitors c "
        "JOIN products p ON p.competitor_id = c.competitor_id"
    )
    result = validate_sql(sql)
    assert result.is_valid


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE competitors",
        "DELETE FROM competitors",
        "INSERT INTO competitors (company_name) VALUES ('x')",
        "UPDATE competitors SET market_share = 0",
        "ALTER TABLE competitors ADD COLUMN x TEXT",
    ],
)
def test_rejects_ddl_dml(sql):
    result = validate_sql(sql)
    assert not result.is_valid
    assert result.violations


def test_rejects_multiple_statements():
    result = validate_sql("SELECT * FROM competitors; DROP TABLE competitors;")
    assert not result.is_valid
    assert any("multiple statements" in v for v in result.violations)


def test_rejects_sql_comments():
    result = validate_sql("SELECT * FROM competitors -- sneaky comment")
    assert not result.is_valid


def test_rejects_table_not_in_whitelist():
    result = validate_sql("SELECT * FROM sqlite_master")
    assert not result.is_valid
    assert any("not permitted" in v for v in result.violations)


def test_rejects_empty_query():
    result = validate_sql("")
    assert not result.is_valid
