"""Text-to-SQL tool: NL question -> LLM-generated SQL -> validate -> execute.

Implements the "Text-to-SQL validation loop" from the milestone spec: if the
generated query fails validation, the violation is fed back to the LLM once
for a repair attempt before giving up.
"""
from __future__ import annotations

import sqlite3

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.config import SALES_DB_PATH, get_settings
from app.instrumentation import get_tracer
from app.logging_utils import log_event
from app.schemas import SQLQueryResult
from app.tools.sql_validation import ALLOWED_TABLES, validate_sql

SCHEMA_DESCRIPTION = """
Tables available in sales.db (SQLite):

competitors(competitor_id INTEGER, company_name TEXT, industry TEXT, headquarters TEXT,
            CEO TEXT, website TEXT, market_share REAL, employee_count INTEGER,
            annual_revenue_million INTEGER)

products(product_id TEXT, competitor_id INTEGER, product_name TEXT, category TEXT,
         launch_date DATE, pricing_model TEXT, subscription_price INTEGER,
         ai_features TEXT, target_market TEXT)

quarterly_sales(sales_id INTEGER, competitor_id INTEGER, year INTEGER, quarter TEXT,
                 revenue_million INTEGER, growth_percent REAL, new_customers INTEGER,
                 renewals INTEGER, churn_rate REAL)

market_news(news_id INTEGER, date TEXT, company_name TEXT, headline TEXT, category TEXT,
            sentiment TEXT, source TEXT, url TEXT)

pricing_comparison(company_name TEXT, product_name TEXT, monthly_price INTEGER,
                    annual_price INTEGER, free_trial TEXT, enterprise_support TEXT)
""".strip()

_SYSTEM_PROMPT = f"""You translate natural-language business questions into a single
read-only SQLite SELECT statement.

{SCHEMA_DESCRIPTION}

Rules:
- Output ONLY the SQL query, no explanation, no markdown fences, no trailing semicolon required.
- Use only the tables/columns listed above.
- Never write INSERT/UPDATE/DELETE/DROP or any statement other than SELECT.
- Prefer explicit column lists over SELECT *.
- Add a LIMIT clause for exploratory queries.
"""


def _get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        api_key=settings.openai_api_key or "not-set",
    )


def generate_sql(question: str) -> str:
    settings = get_settings()
    with get_tracer().span("tool.text_to_sql.generate", agent="researcher") as span:
        llm = _get_llm()
        response = llm.invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=question)]
        )
        span.record_llm_usage(settings.openai_model, prompt_text=_SYSTEM_PROMPT + question, completion_text=response.content)
        return _strip_fences(response.content)


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("sql"):
            cleaned = cleaned[3:]
    return cleaned.strip()


def execute_sql(sanitized_sql: str, row_limit: int) -> tuple[list[str], list[list]]:
    with get_tracer().span("tool.text_to_sql.execute", agent="researcher") as span:
        con = sqlite3.connect(SALES_DB_PATH)
        try:
            cur = con.cursor()
            cur.execute(sanitized_sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [list(row) for row in cur.fetchmany(row_limit)]
            span.set_metadata(sql=sanitized_sql[:300], row_count=len(rows))
            return columns, rows
        finally:
            con.close()


def run_text_to_sql(question: str, session_id: str = "-") -> SQLQueryResult:
    settings = get_settings()
    raw_sql = generate_sql(question)
    validation = validate_sql(raw_sql, row_limit=settings.sql_row_limit)

    if not validation.is_valid:
        # One repair attempt: tell the LLM exactly what was wrong.
        with get_tracer().span("tool.text_to_sql.repair", agent="researcher") as span:
            llm = _get_llm()
            repair_prompt = (
                f"The SQL you produced was rejected by validation: {'; '.join(validation.violations)}.\n"
                f"Only these tables are permitted: {', '.join(sorted(ALLOWED_TABLES))}.\n"
                f"Original question: {question}\n"
                "Return a corrected single SELECT statement only."
            )
            response = llm.invoke(
                [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=repair_prompt)]
            )
            span.record_llm_usage(settings.openai_model, prompt_text=repair_prompt, completion_text=response.content)
            span.set_metadata(violations=validation.violations)
        raw_sql = _strip_fences(response.content)
        validation = validate_sql(raw_sql, row_limit=settings.sql_row_limit)

    log_event(
        session_id=session_id,
        agent="researcher",
        action="text_to_sql_validate",
        input_summary=question,
        output_summary=raw_sql,
        is_valid=validation.is_valid,
        violations=validation.violations,
    )

    if not validation.is_valid:
        return SQLQueryResult(
            question=question,
            sql=raw_sql,
            columns=[],
            rows=[],
            row_count=0,
            error=f"SQL rejected by validator: {'; '.join(validation.violations)}",
        )

    try:
        columns, rows = execute_sql(validation.sanitized_sql, settings.sql_row_limit)
        result = SQLQueryResult(
            question=question,
            sql=validation.sanitized_sql,
            columns=columns,
            rows=rows,
            row_count=len(rows),
        )
    except sqlite3.Error as exc:
        result = SQLQueryResult(
            question=question,
            sql=validation.sanitized_sql,
            columns=[],
            rows=[],
            row_count=0,
            error=str(exc),
        )

    log_event(
        session_id=session_id,
        agent="researcher",
        action="text_to_sql_execute",
        input_summary=validation.sanitized_sql,
        output_summary=f"{result.row_count} rows",
        error=result.error,
    )
    return result


@tool("text_to_sql")
def text_to_sql_tool(question: str) -> str:
    """Answer a question about competitors, products, quarterly sales, market news,
    or pricing by generating and running a validated read-only SQL query against
    the enterprise database. Returns a compact text table of results."""
    result = run_text_to_sql(question)
    if result.error:
        return f"SQL error: {result.error}"
    header = " | ".join(result.columns)
    body = "\n".join(" | ".join(str(v) for v in row) for row in result.rows[:50])
    return f"SQL: {result.sql}\n{header}\n{body}"
