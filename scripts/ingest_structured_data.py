"""One-time data prep: load market_news.csv and pricing_comparison.csv into
sales.db so the Text-to-SQL tool can query all structured data (competitors,
products, quarterly_sales, market_news, pricing_comparison) from one place.

competitors / products / quarterly_sales already exist in sales.db and are
left untouched. Safe to re-run (tables are replaced).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import SALES_DB_PATH, STRUCTURED_DIR  # noqa: E402


def main() -> None:
    con = sqlite3.connect(SALES_DB_PATH)
    try:
        for csv_name, table in [
            ("market_news.csv", "market_news"),
            ("pricing_comparison.csv", "pricing_comparison"),
        ]:
            df = pd.read_csv(STRUCTURED_DIR / csv_name)
            df.to_sql(table, con, if_exists="replace", index=False)
            print(f"Loaded {len(df)} rows into '{table}'")

        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cur.fetchall()]
        print("sales.db tables:", tables)
    finally:
        con.close()


if __name__ == "__main__":
    main()
