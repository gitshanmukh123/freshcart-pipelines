"""Build a sanitized, runnable FreshCart notebook from the classroom workbook."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT.parent / "references" / "freshcart_elt_commented.ipynb"
OUT = ROOT / "elt" / "freshcart_elt.ipynb"


def markdown(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.strip("\n").splitlines(keepends=True),
    }


def code(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.strip("\n").splitlines(keepends=True),
    }


def clean_cell(cell: dict) -> dict:
    result = copy.deepcopy(cell)
    if result.get("cell_type") == "code":
        result["outputs"] = []
        result["execution_count"] = None
    elif result.get("cell_type") == "markdown":
        text = "".join(result.get("source", []))
        text = re.sub(r"!\[[^\]]*\]\(data:image/[^)]+\)", "[reference image omitted]", text)
        text = re.sub(r"<img[^>]+>", "[reference image omitted]", text)
        result["source"] = text.splitlines(keepends=True)
    return result


def build_cells() -> list[dict]:
    nb = json.loads(REFERENCE.read_text(encoding="utf-8"))
    cells = [clean_cell(cell) for cell in nb["cells"]]

    credential_source = """
import os
from getpass import getpass
import snowflake.connector

SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT") or getpass("Snowflake account identifier: ")
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER") or getpass("Snowflake user: ")
SNOWFLAKE_ROLE = os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN")
SNOWFLAKE_AUTHENTICATOR = os.getenv("SNOWFLAKE_AUTHENTICATOR", "externalbrowser")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE", "FRESHCART_WH")
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE", "FRESHCART")

LANDING_DIR = os.getenv("FRESHCART_LANDING", "freshcart_landing")

params = {
    "account": SNOWFLAKE_ACCOUNT,
    "user": SNOWFLAKE_USER,
    "role": SNOWFLAKE_ROLE,
    "authenticator": SNOWFLAKE_AUTHENTICATOR,
}
if SNOWFLAKE_AUTHENTICATOR.lower() != "externalbrowser":
    params["password"] = os.getenv("SNOWFLAKE_PASSWORD") or getpass("Snowflake password: ")

conn = snowflake.connector.connect(**params)
print("Connected:", conn.cursor().execute("SELECT CURRENT_USER(), CURRENT_ROLE()").fetchone())
print("Target database:", SNOWFLAKE_DATABASE, "| warehouse:", SNOWFLAKE_WAREHOUSE)
""".strip("\n")

    quality_source = """
def quality_checks():
    \"\"\"Each of these numbers should be 0.\"\"\"
    checks = {
        "rows gained or lost while enriching":
            "SELECT (SELECT COUNT(*) FROM silver.orders_enriched) - (SELECT COUNT(*) FROM silver.orders_dedup)",
        "duplicate orders in gold":
            "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM gold.fct_orders",
        "orders with no customer match":
            "SELECT COUNT_IF(cust_id IS NULL) FROM silver.orders_enriched",
        "orders with an amount but no FX rate":
            "SELECT COUNT_IF(amount IS NOT NULL AND fx_rate IS NULL) FROM silver.orders_enriched",
        "orders with no city":
            "SELECT COUNT_IF(city IS NULL) FROM silver.orders_enriched",
        "future order dates":
            "SELECT COUNT(*) FROM silver.orders_dedup WHERE order_date > CURRENT_DATE()",
    }
    for name, sql in checks.items():
        value = query(sql)[0][0]
        print(f"   {name:38s} {value}   {'OK' if value == 0 else 'PROBLEM'}")
    rejected = query("SELECT COUNT_IF(ARRAY_SIZE(reasons) > 0) / NULLIF(COUNT(*), 0) FROM silver.orders_checked")[0][0]
    print(f"   {'share of rows rejected':38s} {float(rejected or 0):.0%}")
""".strip("\n")

    for cell in cells:
        source = "".join(cell.get("source", []))
        if "SNOWFLAKE_ACCOUNT" in source and "snowflake.connector.connect" in source:
            cell["source"] = credential_source.splitlines(keepends=True)
        if "def quality_checks():" in source:
            cell["source"] = quality_source.splitlines(keepends=True)
        if "SQL_00_SETUP" in source and "CREATE DATABASE IF NOT EXISTS FRESHCART;" in source:
            text = source.replace(
                "CREATE DATABASE IF NOT EXISTS FRESHCART;",
                "CREATE DATABASE IF NOT EXISTS {database};",
            ).replace("USE DATABASE FRESHCART;", "USE DATABASE {database};")
            cell["source"] = text.splitlines(keepends=True)
        if "run_sql(SQL_00_SETUP)" in source:
            cell["source"] = (
                "SQL_00_SETUP = SQL_00_SETUP.format(database=SNOWFLAKE_DATABASE)\n"
                "run_sql(SQL_00_SETUP)\n"
                'print("Setup done in database", SNOWFLAKE_DATABASE)\n'
            ).splitlines(keepends=True)

    cells = cells[:49]

    additions = [
        markdown(
            """
## Assignment checkpoints

This is a sanitized copy of the classroom workbook. Outputs were cleared, the
classroom Snowflake account was removed, and the B3/B4/B5 changes below are
student work. Run it with your own Snowflake account.

**B1 checkpoint** - paste your own baseline screenshot and the final line:
`GOLD: 4 orders, revenue ₹7785.00, 126 loyalty points`.
"""
        ),
        markdown(
            """
**B2 checkpoint** - trace ORD-1003 and ORD-1005 in your own words. Include the
two raw shapes, the SQL expressions that unify them, the winning dedup row, and
the amount_inr / loyalty_points arithmetic.
"""
        ),
        markdown(
            """
## B3. Add the unsupported-currency rule

The baseline rule is shown first. The replacement below adds
`unsupported_currency` inside `ARRAY_CONSTRUCT_COMPACT`, then reruns the pipeline.
"""
        ),
        code(
            """
# Show the baseline quarantine reasons before changing the rule.
show("SELECT order_id, reasons FROM quarantine.orders ORDER BY order_id")

_OLD = "IFF(amount <= 0, 'non_positive_amount', NULL)"
_NEW = (
    "IFF(amount <= 0, 'non_positive_amount', NULL),\\n"
    "    IFF(UPPER(TRIM(currency)) NOT IN ('INR', 'USD'), 'unsupported_currency', NULL)"
)
SQL_10_ORDERS_CLEAN = SQL_10_ORDERS_CLEAN.replace(_OLD, _NEW)
print("unsupported_currency rule present:", "unsupported_currency" in SQL_10_ORDERS_CLEAN)
print(SQL_10_ORDERS_CLEAN[SQL_10_ORDERS_CLEAN.index("ARRAY_CONSTRUCT_COMPACT"):][:700])
"""
        ),
        code(
            """
run_pipeline()

show("SELECT order_id, reasons FROM silver.orders_checked WHERE ARRAY_SIZE(reasons) > 0 ORDER BY order_id")
show("SELECT order_id, reasons FROM quarantine.orders ORDER BY order_id")
show("SELECT COUNT(*) AS quarantine_rows FROM quarantine.orders")
show("SELECT COUNT(*) AS orders, SUM(amount_inr) AS revenue_inr, SUM(loyalty_points) AS points FROM gold.fct_orders")
"""
        ),
        markdown(
            """
**B3 checkpoint** - show ORD-1006's reasons before and after, state whether the
gold total changed, and point to the `NOT EXISTS` / `QUALIFY` logic that prevents
a second quarantine row.
"""
        ),
        markdown(
            """
## B4. Change history and idempotency

**Write your predictions BEFORE running the next cell:**

| Quantity | Your prediction | Actual after run |
|---|---|---|
| Rows for CUST-02 in dim.customers_scd2 |  |  |
| Tier used for ORD-1002 |  |  |
| Loyalty points for ORD-1002 |  |  |
| Total loyalty points in gold |  |  |
| Gold rows whose published_at changed |  |  |
"""
        ),
        code(
            """
before_gold = show("SELECT order_id, tier, amount_inr, loyalty_points, published_at FROM gold.fct_orders ORDER BY order_id")
before_points = query("SELECT SUM(loyalty_points) FROM gold.fct_orders")[0][0]
print("Before B4 points:", before_points)

MOCK_CRM_TIER_EVENTS.append({
    "cust_id": "CUST-02",
    "email": "arjun.k@yahoo.in",
    "tier": "Gold",
    "effective_from": "2026-08-15",
})

run_pipeline()

show("SELECT cust_id, email, tier, valid_from, valid_to FROM dim.customers_scd2 WHERE cust_id = 'CUST-02' ORDER BY valid_from")
show("SELECT order_id, tier, amount_inr, loyalty_points FROM gold.fct_orders WHERE order_id = 'ORD-1002'")
after_gold = show("SELECT order_id, tier, amount_inr, loyalty_points, published_at FROM gold.fct_orders ORDER BY order_id")
after_points = query("SELECT SUM(loyalty_points) FROM gold.fct_orders")[0][0]
print("After B4 points:", after_points)
merged = before_gold.merge(after_gold, on="ORDER_ID", suffixes=("_before", "_after"))
changed = merged[merged["PUBLISHED_AT_before"] != merged["PUBLISHED_AT_after"]]
print("Gold rows whose published_at changed:", len(changed))
display(after_gold)
"""
        ),
        markdown(
            """
**B4 explanation** - in 4-6 sentences explain row_hash and MERGE idempotency,
and why bronze still grows by 8 rows on every run.
"""
        ),
        code(
            """
repeat_before = show("SELECT order_id, published_at FROM gold.fct_orders ORDER BY order_id")
run_pipeline()
repeat_after = show("SELECT order_id, published_at FROM gold.fct_orders ORDER BY order_id")
repeat_merged = repeat_before.merge(repeat_after, on="ORDER_ID", suffixes=("_before", "_after"))
print("Gold rows changed on unchanged rerun:", (repeat_merged["PUBLISHED_AT_before"] != repeat_merged["PUBLISHED_AT_after"]).sum())
show("SELECT COUNT(*) AS gold_orders, SUM(amount_inr) AS revenue_inr, SUM(loyalty_points) AS points FROM gold.fct_orders")
"""
        ),
        markdown(
            """
## B5. Sixth data-quality check

The sixth check is `future order dates`. It should be 0 after B4. Insert a
temporary 2099 order directly into `silver.orders_dedup`, show the PROBLEM
output, then delete the probe.
"""
        ),
        code(
            """
print("Quality checks before probe:")
quality_checks()

query('''
INSERT INTO silver.orders_dedup (
  ingest_seq, source, order_id, email, name, order_date, amount, currency,
  pincode, updated_at, amount_missing
) VALUES (
  999999, 'web', 'ORD-FUTURE-TEST', 'priya.r@gmail.com', 'Priya R',
  '2099-01-01'::DATE, 100.00, 'INR', '600041', '2099-01-01 00:00:00'::TIMESTAMP_NTZ, FALSE
)
''')
print("Quality checks with deliberate future-order probe:")
quality_checks()

query("DELETE FROM silver.orders_dedup WHERE order_id = 'ORD-FUTURE-TEST'")
print("Quality checks after cleanup:")
quality_checks()
"""
        ),
        markdown(
            """
**B5 explanation** - answer the ELT-vs-ETL question in 3-4 sentences, including
one situation from the lecture where ETL would still win.
"""
        ),
        code(
            """
conn.close()
# query("DROP DATABASE IF EXISTS FRESHCART")
# query("DROP WAREHOUSE IF EXISTS FRESHCART_WH")
"""
        ),
    ]

    header = markdown(
        """
# FreshCart ELT - student run

This notebook follows the classroom workbook with outputs cleared and
credentials removed. Replace the placeholders in the checkpoints before
submission and use your own Snowflake account.
"""
    )
    return [header] + cells + additions


notebook = {
    "cells": build_cells(),
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.12"},
        "colab": {"provenance": [], "toc_visible": True},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {OUT} with {len(notebook['cells'])} cells")
