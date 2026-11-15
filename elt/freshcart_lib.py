"""FreshCart ELT helpers, Snowflake SQL, and local validation utilities.

The Snowflake SQL is intentionally explicit so every rubric step can be
demonstrated and explained. The local Python functions are a small, testable
mirror of the SQL fixture expectations; Snowflake remains the source of truth.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from freshcart_data import (
    MOCK_CRM_EVENT_B4,
    MOCK_CRM_TIER_EVENTS,
    MOCK_FX_RATES,
    MOCK_ORDERS,
)

TIER_MULTIPLIERS = {"Bronze": 1.0, "Silver": 1.5, "Gold": 2.0}
SUPPORTED_CURRENCIES = ("INR", "USD")

SQL_SETUP = """
CREATE DATABASE IF NOT EXISTS FRESHCART;
CREATE SCHEMA IF NOT EXISTS FRESHCART.RAW;
CREATE SCHEMA IF NOT EXISTS FRESHCART.CLEAN;
CREATE SCHEMA IF NOT EXISTS FRESHCART.QUARANTINE;
CREATE SCHEMA IF NOT EXISTS FRESHCART.REF;
CREATE SCHEMA IF NOT EXISTS FRESHCART.CRM;
CREATE SCHEMA IF NOT EXISTS FRESHCART.GOLD;
CREATE FILE FORMAT IF NOT EXISTS FRESHCART.RAW.JSON_FF
  TYPE = JSON
  STRIP_OUTER_ARRAY = FALSE;
CREATE STAGE IF NOT EXISTS FRESHCART.RAW.ORDERS_STAGE
  FILE_FORMAT = (FORMAT_NAME = FRESHCART.RAW.JSON_FF);
"""

SQL_CREATE_RAW = """
CREATE TABLE IF NOT EXISTS FRESHCART.RAW.ORDERS (
  order_id STRING,
  customer_id STRING,
  email STRING,
  order_date STRING,
  product STRING,
  quantity STRING,
  unit_price STRING,
  amount STRING,
  currency STRING,
  channel STRING,
  updated_at STRING,
  _source_file STRING,
  _loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
"""

SQL_CREATE_QUARANTINE = """
CREATE TABLE IF NOT EXISTS FRESHCART.QUARANTINE.ORDERS_QUARANTINE (
  order_id STRING,
  row_hash STRING,
  reasons ARRAY,
  raw_record VARIANT,
  first_seen_at TIMESTAMP_NTZ,
  last_seen_at TIMESTAMP_NTZ
);
"""

SQL_CREATE_FX = """
CREATE TABLE IF NOT EXISTS FRESHCART.REF.FX_RATES (
  currency STRING,
  rate_to_inr NUMBER(12, 6)
);
"""

SQL_CREATE_CRM_EVENTS = """
CREATE TABLE IF NOT EXISTS FRESHCART.CRM.CUSTOMER_TIER_EVENTS (
  event_id STRING,
  customer_id STRING,
  email STRING,
  tier STRING,
  effective_from TIMESTAMP_NTZ,
  loaded_at TIMESTAMP_NTZ
);
"""

SQL_CREATE_CRM_HISTORY = """
CREATE TABLE IF NOT EXISTS FRESHCART.CRM.CUSTOMER_TIER_HISTORY (
  event_id STRING,
  customer_id STRING,
  email STRING,
  tier STRING,
  effective_from TIMESTAMP_NTZ,
  effective_to TIMESTAMP_NTZ,
  is_current BOOLEAN,
  loaded_at TIMESTAMP_NTZ
);
"""

SQL_CREATE_GOLD = """
CREATE TABLE IF NOT EXISTS FRESHCART.GOLD.FACT_ORDERS (
  order_id STRING,
  customer_id STRING,
  email STRING,
  order_date TIMESTAMP_NTZ,
  product STRING,
  quantity NUMBER,
  unit_price NUMBER(12, 2),
  amount_original NUMBER(12, 2),
  currency STRING,
  channel STRING,
  amount_inr NUMBER(12, 2),
  tier STRING,
  multiplier NUMBER(4, 2),
  points_earned NUMBER,
  row_hash STRING,
  published_at TIMESTAMP_NTZ,
  last_updated_at TIMESTAMP_NTZ
);
"""

_SQL_CLEAN_TEMPLATE = """
CREATE OR REPLACE TABLE FRESHCART.CLEAN.ORDERS_CLEAN AS
WITH candidate AS (
  SELECT
    order_id,
    customer_id,
    email,
    TRY_TO_TIMESTAMP_NTZ(order_date, 'YYYY-MM-DD HH24:MI:SS') AS order_date,
    product,
    TRY_TO_NUMBER(quantity) AS quantity,
    TRY_TO_NUMBER(unit_price, 10, 2) AS unit_price,
    TRY_TO_NUMBER(amount, 12, 2) AS amount,
    UPPER(TRIM(currency)) AS currency,
    LOWER(TRIM(channel)) AS channel,
    TRY_TO_TIMESTAMP_NTZ(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at,
    _source_file,
    _loaded_at,
    ARRAY_CONSTRUCT_COMPACT(
      IFF(order_id IS NULL OR TRIM(order_id) = '', 'missing_order_id', NULL),
      IFF(customer_id IS NULL OR TRIM(customer_id) = '', 'missing_customer', NULL),
      IFF(TRY_TO_NUMBER(quantity) IS NULL OR TRY_TO_NUMBER(quantity) <= 0,
          'invalid_quantity', NULL),
      IFF(amount IS NOT NULL AND
          (TRY_TO_NUMBER(amount, 12, 2) IS NULL OR TRY_TO_NUMBER(amount, 12, 2) <= 0),
          'invalid_amount', NULL),
      IFF(TRY_TO_TIMESTAMP_NTZ(order_date, 'YYYY-MM-DD HH24:MI:SS') IS NULL,
          'missing_order_date', NULL)
      {unsupported_currency}
    ) AS validation_errors
  FROM FRESHCART.RAW.ORDERS
)
SELECT
  order_id,
  customer_id,
  email,
  order_date,
  product,
  quantity,
  unit_price,
  amount,
  currency,
  channel,
  updated_at,
  _source_file,
  _loaded_at,
  validation_errors,
  ARRAY_SIZE(validation_errors) = 0 AS is_valid,
  SHA2(CONCAT_WS('|',
    COALESCE(order_id, ''),
    COALESCE(customer_id, ''),
    COALESCE(email, ''),
    COALESCE(TO_VARCHAR(order_date), ''),
    COALESCE(product, ''),
    COALESCE(TO_VARCHAR(quantity), ''),
    COALESCE(TO_VARCHAR(unit_price), ''),
    COALESCE(TO_VARCHAR(amount), ''),
    COALESCE(currency, ''),
    COALESCE(channel, ''),
    COALESCE(TO_VARCHAR(updated_at), '')
  ), 256) AS row_hash
FROM candidate;
"""

SQL_10_ORDERS_CLEAN = _SQL_CLEAN_TEMPLATE.format(unsupported_currency="")
SQL_11_ORDERS_CLEAN_B3 = _SQL_CLEAN_TEMPLATE.format(
    unsupported_currency=(
        ",\n      IFF(UPPER(TRIM(currency)) NOT IN ('INR', 'USD'), "
        "'unsupported_currency', NULL)"
    )
)

SQL_20_ORDERS_DEDUP = """
CREATE OR REPLACE TABLE FRESHCART.CLEAN.ORDERS_DEDUP AS
SELECT
  order_id,
  customer_id,
  email,
  order_date,
  product,
  quantity,
  unit_price,
  amount,
  currency,
  channel,
  updated_at,
  _source_file,
  _loaded_at,
  row_hash
FROM FRESHCART.CLEAN.ORDERS_CLEAN
WHERE is_valid
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY order_id
  ORDER BY updated_at DESC NULLS LAST, _loaded_at DESC, _source_file DESC
) = 1;
"""

SQL_30_QUARANTINE_MERGE = """
MERGE INTO FRESHCART.QUARANTINE.ORDERS_QUARANTINE t
USING (
  SELECT
    order_id,
    row_hash,
    validation_errors AS reasons,
    OBJECT_CONSTRUCT(
      'order_id', order_id,
      'customer_id', customer_id,
      'email', email,
      'order_date', TO_VARCHAR(order_date),
      'product', product,
      'quantity', quantity,
      'unit_price', unit_price,
      'amount', amount,
      'currency', currency,
      'channel', channel,
      'updated_at', TO_VARCHAR(updated_at)
    ) AS raw_record
  FROM FRESHCART.CLEAN.ORDERS_CLEAN
  WHERE NOT is_valid
) s
ON t.order_id = s.order_id AND t.row_hash = s.row_hash
WHEN MATCHED THEN UPDATE SET
  t.reasons = s.reasons,
  t.raw_record = s.raw_record,
  t.last_seen_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
  order_id, row_hash, reasons, raw_record, first_seen_at, last_seen_at
) VALUES (
  s.order_id, s.row_hash, s.reasons, s.raw_record,
  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);
"""

SQL_41_SCD2_INSERT = """
INSERT INTO FRESHCART.CRM.CUSTOMER_TIER_HISTORY (
  event_id, customer_id, email, tier, effective_from,
  effective_to, is_current, loaded_at
)
WITH dedup AS (
  SELECT event_id, customer_id, email, tier, effective_from
  FROM FRESHCART.CRM.CUSTOMER_TIER_EVENTS
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY customer_id, effective_from
    ORDER BY event_id DESC
  ) = 1
),
ordered AS (
  SELECT
    event_id, customer_id, email, tier, effective_from,
    LAG(tier) OVER (
      PARTITION BY customer_id ORDER BY effective_from, event_id
    ) AS previous_tier
  FROM dedup
)
SELECT
  o.event_id, o.customer_id, o.email, o.tier, o.effective_from,
  NULL, TRUE, CURRENT_TIMESTAMP()
FROM ordered o
WHERE (o.previous_tier IS NULL OR o.previous_tier <> o.tier)
  AND NOT EXISTS (
    SELECT 1
    FROM FRESHCART.CRM.CUSTOMER_TIER_HISTORY h
    WHERE h.customer_id = o.customer_id
      AND h.effective_from = o.effective_from
      AND h.tier = o.tier
  );
"""

SQL_42_SCD2_CLOSE = """
UPDATE FRESHCART.CRM.CUSTOMER_TIER_HISTORY t
SET effective_to = (
      SELECT MIN(e.effective_from)
      FROM FRESHCART.CRM.CUSTOMER_TIER_EVENTS e
      WHERE e.customer_id = t.customer_id
        AND e.effective_from > t.effective_from
        AND e.tier <> t.tier
    ),
    is_current = FALSE
WHERE t.is_current
  AND EXISTS (
    SELECT 1
    FROM FRESHCART.CRM.CUSTOMER_TIER_EVENTS e
    WHERE e.customer_id = t.customer_id
      AND e.effective_from > t.effective_from
      AND e.tier <> t.tier
  );
"""

SQL_60_GOLD_STAGE = """
CREATE OR REPLACE TABLE FRESHCART.GOLD.FACT_ORDERS_STAGE AS
WITH priced AS (
  SELECT
    d.order_id,
    d.customer_id,
    d.email,
    d.order_date,
    d.product,
    d.quantity,
    d.unit_price,
    d.amount AS amount_original,
    d.currency,
    d.channel,
    ROUND(d.amount * f.rate_to_inr, 2) AS amount_inr
  FROM FRESHCART.CLEAN.ORDERS_DEDUP d
  JOIN FRESHCART.REF.FX_RATES f
    ON d.currency = f.currency
),
tiered AS (
  SELECT
    p.*,
    h.tier,
    CASE h.tier
      WHEN 'Bronze' THEN 1.0
      WHEN 'Silver' THEN 1.5
      WHEN 'Gold' THEN 2.0
    END AS multiplier
  FROM priced p
  LEFT JOIN FRESHCART.CRM.CUSTOMER_TIER_HISTORY h
    ON p.customer_id = h.customer_id
   AND p.order_date >= h.effective_from
   AND (h.effective_to IS NULL OR p.order_date < h.effective_to)
)
SELECT
  order_id,
  customer_id,
  email,
  order_date,
  product,
  quantity,
  unit_price,
  amount_original,
  currency,
  channel,
  amount_inr,
  tier,
  multiplier,
  FLOOR(amount_inr * multiplier / 100) AS points_earned,
  SHA2(CONCAT_WS('|',
    order_id,
    customer_id,
    COALESCE(TO_VARCHAR(order_date), ''),
    COALESCE(TO_VARCHAR(amount_inr), ''),
    COALESCE(tier, ''),
    COALESCE(TO_VARCHAR(multiplier), ''),
    COALESCE(TO_VARCHAR(FLOOR(amount_inr * multiplier / 100)), '')
  ), 256) AS row_hash,
  CURRENT_TIMESTAMP() AS published_at,
  CURRENT_TIMESTAMP() AS last_updated_at
FROM tiered;
"""

SQL_70_MERGE_GOLD = """
MERGE INTO FRESHCART.GOLD.FACT_ORDERS t
USING FRESHCART.GOLD.FACT_ORDERS_STAGE s
ON t.order_id = s.order_id
WHEN MATCHED AND t.row_hash <> s.row_hash THEN UPDATE SET
  t.customer_id = s.customer_id,
  t.email = s.email,
  t.order_date = s.order_date,
  t.product = s.product,
  t.quantity = s.quantity,
  t.unit_price = s.unit_price,
  t.amount_original = s.amount_original,
  t.currency = s.currency,
  t.channel = s.channel,
  t.amount_inr = s.amount_inr,
  t.tier = s.tier,
  t.multiplier = s.multiplier,
  t.points_earned = s.points_earned,
  t.row_hash = s.row_hash,
  t.published_at = CURRENT_TIMESTAMP(),
  t.last_updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
  order_id, customer_id, email, order_date, product, quantity,
  unit_price, amount_original, currency, channel, amount_inr, tier,
  multiplier, points_earned, row_hash, published_at, last_updated_at
) VALUES (
  s.order_id, s.customer_id, s.email, s.order_date, s.product, s.quantity,
  s.unit_price, s.amount_original, s.currency, s.channel, s.amount_inr,
  s.tier, s.multiplier, s.points_earned, s.row_hash, s.published_at,
  s.last_updated_at
);
"""

SQL_B5_FUTURE_CHECK = """
SELECT COUNT(*) AS future_rows
FROM FRESHCART.CLEAN.ORDERS_DEDUP
WHERE order_date > CURRENT_TIMESTAMP();
"""

SQL_B5_INSERT_FUTURE = """
INSERT INTO FRESHCART.CLEAN.ORDERS_DEDUP (
  order_id, customer_id, email, order_date, product, quantity,
  unit_price, amount, currency, channel, updated_at,
  _source_file, _loaded_at, row_hash
) VALUES (
  'ORD-FUTURE-TEST', 'CUST-01', 'priya.sharma@gmail.com',
  TO_TIMESTAMP_NTZ('2099-01-01 00:00:00'), 'Future Test Item', 1,
  100.00, 100.00, 'INR', 'website', TO_TIMESTAMP_NTZ('2099-01-01 00:00:00'),
  'b5_future_probe', CURRENT_TIMESTAMP(), 'b5-future-test-hash'
);
"""

SQL_B5_DELETE_FUTURE = """
DELETE FROM FRESHCART.CLEAN.ORDERS_DEDUP
WHERE order_id = 'ORD-FUTURE-TEST';
"""

QUALITY_CHECKS = {
    "duplicate_dedup_order_ids": """
        SELECT COUNT(*) FROM (
          SELECT order_id
          FROM FRESHCART.CLEAN.ORDERS_DEDUP
          GROUP BY order_id
          HAVING COUNT(*) > 1
        )
    """,
    "gold_null_amount_inr": """
        SELECT COUNT(*)
        FROM FRESHCART.GOLD.FACT_ORDERS
        WHERE amount_inr IS NULL AND amount_original IS NOT NULL
    """,
    "gold_negative_points": """
        SELECT COUNT(*)
        FROM FRESHCART.GOLD.FACT_ORDERS
        WHERE points_earned < 0
    """,
    "dedup_without_tier_match": """
        SELECT COUNT(*)
        FROM FRESHCART.CLEAN.ORDERS_DEDUP d
        WHERE NOT EXISTS (
          SELECT 1
          FROM FRESHCART.CRM.CUSTOMER_TIER_HISTORY h
          WHERE d.customer_id = h.customer_id
            AND d.order_date >= h.effective_from
            AND (h.effective_to IS NULL OR d.order_date < h.effective_to)
        )
    """,
    "dedup_without_fx_rate": """
        SELECT COUNT(*)
        FROM FRESHCART.CLEAN.ORDERS_DEDUP d
        WHERE NOT EXISTS (
          SELECT 1
          FROM FRESHCART.REF.FX_RATES f
          WHERE d.currency = f.currency
        )
    """,
}


def connect_snowflake(**overrides: Any):
    """Create a Snowflake connection; credentials come from the environment."""
    try:
        import snowflake.connector
    except ImportError as exc:
        raise RuntimeError(
            "Install snowflake-connector-python[pandas] before running Snowflake cells"
        ) from exc

    params = {
        "account": overrides.get("account", os.getenv("SNOWFLAKE_ACCOUNT")),
        "user": overrides.get("user", os.getenv("SNOWFLAKE_USER")),
        "password": overrides.get("password", os.getenv("SNOWFLAKE_PASSWORD")),
        "warehouse": overrides.get(
            "warehouse", os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
        ),
        "role": overrides.get("role", os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN")),
        "database": overrides.get("database", os.getenv("SNOWFLAKE_DATABASE", "FRESHCART")),
    }
    params = {k: v for k, v in params.items() if v is not None}
    return snowflake.connector.connect(**params)


def execute_statements(conn, sql: str) -> None:
    """Execute semicolon-delimited setup statements one at a time."""
    for statement in (part.strip() for part in sql.split(";")):
        if statement:
            conn.cursor().execute(statement)


def run_query(conn, sql: str):
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        return cursor.fetchall()
    finally:
        cursor.close()


def scalar(conn, sql: str):
    rows = run_query(conn, sql)
    return rows[0][0] if rows else None


def setup_snowflake(conn) -> None:
    execute_statements(conn, SQL_SETUP)
    for sql in (
        SQL_CREATE_RAW,
        SQL_CREATE_QUARANTINE,
        SQL_CREATE_FX,
        SQL_CREATE_CRM_EVENTS,
        SQL_CREATE_CRM_HISTORY,
        SQL_CREATE_GOLD,
    ):
        execute_statements(conn, sql)
    insert_fx_rates(conn)


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def insert_mock_orders(conn) -> int:
    """Reset RAW.ORDERS to the reconstructed eight-row fixture."""
    execute_statements(conn, "TRUNCATE TABLE FRESHCART.RAW.ORDERS;")
    sql = """
        INSERT INTO FRESHCART.RAW.ORDERS (
          order_id, customer_id, email, order_date, product, quantity,
          unit_price, amount, currency, channel, updated_at,
          _source_file, _loaded_at
        )
        SELECT
          f.value:order_id::STRING,
          f.value:customer_id::STRING,
          f.value:email::STRING,
          f.value:order_date::STRING,
          f.value:product::STRING,
          f.value:quantity::STRING,
          f.value:unit_price::STRING,
          f.value:amount::STRING,
          f.value:currency::STRING,
          f.value:channel::STRING,
          f.value:updated_at::STRING,
          'mock_baseline',
          CURRENT_TIMESTAMP()
        FROM (SELECT PARSE_JSON(%s) AS payload) p,
        LATERAL FLATTEN(input => p.payload) f
    """
    conn.cursor().execute(sql, (json.dumps(MOCK_ORDERS),))
    return scalar(conn, "SELECT COUNT(*) FROM FRESHCART.RAW.ORDERS")


def insert_crm_events(conn, events: Iterable[dict] | None = None) -> int:
    events = list(events if events is not None else MOCK_CRM_TIER_EVENTS)
    rows = ",\n".join(
        "(" + ", ".join(
            [
                _sql_literal(e["event_id"]),
                _sql_literal(e["customer_id"]),
                _sql_literal(e["email"]),
                _sql_literal(e["tier"]),
                f"TO_TIMESTAMP_NTZ({_sql_literal(e['effective_from'])})",
            ]
        ) + ")"
        for e in events
    )
    sql = f"""
        MERGE INTO FRESHCART.CRM.CUSTOMER_TIER_EVENTS t
        USING (
          SELECT column1 AS event_id, column2 AS customer_id, column3 AS email,
                 column4 AS tier, column5 AS effective_from
          FROM VALUES {rows}
        ) s
        ON t.event_id = s.event_id
        WHEN MATCHED THEN UPDATE SET
          t.customer_id = s.customer_id,
          t.email = s.email,
          t.tier = s.tier,
          t.effective_from = s.effective_from,
          t.loaded_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (
          event_id, customer_id, email, tier, effective_from, loaded_at
        ) VALUES (
          s.event_id, s.customer_id, s.email, s.tier, s.effective_from,
          CURRENT_TIMESTAMP()
        )
    """
    execute_statements(conn, sql)
    return scalar(conn, "SELECT COUNT(*) FROM FRESHCART.CRM.CUSTOMER_TIER_EVENTS")


def insert_fx_rates(conn, rates: Iterable[dict] | None = None) -> int:
    rates = list(rates if rates is not None else MOCK_FX_RATES)
    rows = ",\n".join(
        f"({_sql_literal(r['currency'])}, {r['rate_to_inr']})" for r in rates
    )
    sql = f"""
        MERGE INTO FRESHCART.REF.FX_RATES t
        USING (SELECT column1 AS currency, column2 AS rate_to_inr FROM VALUES {rows}) s
        ON t.currency = s.currency
        WHEN MATCHED THEN UPDATE SET t.rate_to_inr = s.rate_to_inr
        WHEN NOT MATCHED THEN INSERT (currency, rate_to_inr)
          VALUES (s.currency, s.rate_to_inr)
    """
    execute_statements(conn, sql)
    return scalar(conn, "SELECT COUNT(*) FROM FRESHCART.REF.FX_RATES")


def write_landing(conn, frame, landing_dir: str | Path = "landing") -> str:
    """Write a timestamped NDJSON file and PUT it to the Snowflake stage."""
    directory = Path(landing_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"orders_{stamp}_{uuid.uuid4().hex[:8]}.json"
    local_path = (directory / filename).resolve()
    frame.to_json(local_path, orient="records", lines=True, date_format="iso")

    snowflake_path = str(local_path).replace("\\", "/")
    execute_statements(
        conn,
        f"PUT 'file://{snowflake_path}' "
        "FRESHCART.RAW.ORDERS_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;",
    )
    return filename


def load_file(conn, filename: str, force: bool = False) -> list:
    """COPY one staged NDJSON file into RAW.ORDERS."""
    force_clause = "TRUE" if force else "FALSE"
    sql = f"""
        COPY INTO FRESHCART.RAW.ORDERS (
          order_id, customer_id, email, order_date, product, quantity,
          unit_price, amount, currency, channel, updated_at,
          _source_file, _loaded_at
        )
        FROM (
          SELECT
            $1:order_id::STRING,
            $1:customer_id::STRING,
            $1:email::STRING,
            $1:order_date::STRING,
            $1:product::STRING,
            $1:quantity::STRING,
            $1:unit_price::STRING,
            $1:amount::STRING,
            $1:currency::STRING,
            $1:channel::STRING,
            $1:updated_at::STRING,
            METADATA$FILENAME::STRING,
            CURRENT_TIMESTAMP()
          FROM @FRESHCART.RAW.ORDERS_STAGE/{filename}
        )
        FILE_FORMAT = (FORMAT_NAME = FRESHCART.RAW.JSON_FF)
        ON_ERROR = 'ABORT_STATEMENT'
        FORCE = {force_clause}
    """
    return run_query(conn, sql)


def refresh_clean(conn, include_unsupported: bool = False) -> int:
    execute_statements(conn, SQL_11_ORDERS_CLEAN_B3 if include_unsupported else SQL_10_ORDERS_CLEAN)
    return scalar(conn, "SELECT COUNT(*) FROM FRESHCART.CLEAN.ORDERS_CLEAN")


def reject_orders(conn) -> int:
    execute_statements(conn, SQL_20_ORDERS_DEDUP)
    execute_statements(conn, SQL_30_QUARANTINE_MERGE)
    return scalar(conn, "SELECT COUNT(*) FROM FRESHCART.CLEAN.ORDERS_DEDUP")


def load_crm_history(conn) -> int:
    execute_statements(conn, SQL_41_SCD2_INSERT)
    execute_statements(conn, SQL_42_SCD2_CLOSE)
    return scalar(conn, "SELECT COUNT(*) FROM FRESHCART.CRM.CUSTOMER_TIER_HISTORY")


def build_gold(conn) -> int:
    execute_statements(conn, SQL_60_GOLD_STAGE)
    execute_statements(conn, SQL_70_MERGE_GOLD)
    return scalar(conn, "SELECT COUNT(*) FROM FRESHCART.GOLD.FACT_ORDERS")


def quality_report(conn, include_b5: bool = False) -> list[dict]:
    checks = dict(QUALITY_CHECKS)
    if include_b5:
        checks["future_order_dates"] = SQL_B5_FUTURE_CHECK
    report = []
    for name, sql in checks.items():
        value = int(scalar(conn, sql) or 0)
        report.append(
            {"check": name, "count": value, "status": "PASS" if value == 0 else "PROBLEM"}
        )
    return report


def print_quality(report: list[dict]) -> None:
    for row in report:
        print(f"{row['status']:<8} {row['check']:<30} {row['count']}")


def counts(conn) -> dict:
    queries = {
        "raw": "SELECT COUNT(*) FROM FRESHCART.RAW.ORDERS",
        "clean": "SELECT COUNT(*) FROM FRESHCART.CLEAN.ORDERS_CLEAN",
        "valid": "SELECT COUNT(*) FROM FRESHCART.CLEAN.ORDERS_CLEAN WHERE is_valid",
        "quarantine": "SELECT COUNT(*) FROM FRESHCART.QUARANTINE.ORDERS_QUARANTINE",
        "dedup": "SELECT COUNT(*) FROM FRESHCART.CLEAN.ORDERS_DEDUP",
        "crm_history": "SELECT COUNT(*) FROM FRESHCART.CRM.CUSTOMER_TIER_HISTORY",
        "gold": "SELECT COUNT(*) FROM FRESHCART.GOLD.FACT_ORDERS",
        "gold_amount_inr": "SELECT COALESCE(SUM(amount_inr), 0) FROM FRESHCART.GOLD.FACT_ORDERS",
        "gold_points": "SELECT COALESCE(SUM(points_earned), 0) FROM FRESHCART.GOLD.FACT_ORDERS",
    }
    return {name: scalar(conn, sql) for name, sql in queries.items()}


def tier_for_order(order_date: datetime, customer_id: str, events: list[dict]) -> str:
    applicable = [
        e for e in events
        if e["customer_id"] == customer_id
        and datetime.fromisoformat(e["effective_from"]) <= order_date
    ]
    if not applicable:
        raise ValueError(f"No CRM tier event covers {customer_id} on {order_date}")
    return max(applicable, key=lambda e: e["effective_from"])["tier"]


def validate_order(order: dict, include_unsupported: bool = True) -> list[str]:
    reasons = []
    if not str(order.get("order_id") or "").strip():
        reasons.append("missing_order_id")
    if not str(order.get("customer_id") or "").strip():
        reasons.append("missing_customer")
    try:
        quantity = float(order.get("quantity"))
    except (TypeError, ValueError):
        quantity = None
    if quantity is None or quantity <= 0:
        reasons.append("invalid_quantity")
    if order.get("amount") is not None:
        try:
            amount = float(order.get("amount"))
        except (TypeError, ValueError):
            amount = None
        if amount is None or amount <= 0:
            reasons.append("invalid_amount")
    try:
        datetime.fromisoformat(order.get("order_date"))
    except (TypeError, ValueError):
        reasons.append("missing_order_date")
    if (
        include_unsupported
        and str(order.get("currency") or "").upper() not in SUPPORTED_CURRENCIES
    ):
        reasons.append("unsupported_currency")
    return reasons


def clean_orders(
    orders: list[dict] | None = None,
    include_unsupported: bool = False,
) -> list[dict]:
    cleaned = []
    for index, order in enumerate(orders or MOCK_ORDERS):
        reasons = validate_order(order, include_unsupported=include_unsupported)
        cleaned.append(
            {
                **order,
                "quantity": float(order["quantity"]),
                "amount": None if order["amount"] is None else float(order["amount"]),
                "order_date": datetime.fromisoformat(order["order_date"]),
                "updated_at": datetime.fromisoformat(order["updated_at"]),
                "validation_errors": reasons,
                "is_valid": not reasons,
                "_row_index": index,
            }
        )
    return cleaned


def deduplicate_orders(cleaned: list[dict]) -> list[dict]:
    winners: dict[str, dict] = {}
    for row in cleaned:
        if not row["is_valid"]:
            continue
        current = winners.get(row["order_id"])
        key = (row["updated_at"], row["_row_index"])
        if current is None or key > (current["updated_at"], current["_row_index"]):
            winners[row["order_id"]] = row
    return sorted(winners.values(), key=lambda row: row["order_id"])


def compute_gold_orders(
    dedup_rows: list[dict],
    events: list[dict] | None = None,
    fx_rates: dict[str, float] | None = None,
) -> list[dict]:
    events = events if events is not None else MOCK_CRM_TIER_EVENTS
    fx_rates = fx_rates or {
        item["currency"]: float(item["rate_to_inr"]) for item in MOCK_FX_RATES
    }
    gold = []
    for row in dedup_rows:
        tier = tier_for_order(row["order_date"], row["customer_id"], events)
        multiplier = TIER_MULTIPLIERS[tier]
        amount_inr = round(row["amount"] * fx_rates[row["currency"]], 2)
        gold.append(
            {
                "order_id": row["order_id"],
                "customer_id": row["customer_id"],
                "currency": row["currency"],
                "amount_inr": amount_inr,
                "tier": tier,
                "multiplier": multiplier,
                "points_earned": int(amount_inr * multiplier // 100),
            }
        )
    return sorted(gold, key=lambda row: row["order_id"])


def apply_b4(events: list[dict] | None = None) -> list[dict]:
    return list(events or MOCK_CRM_TIER_EVENTS) + [MOCK_CRM_EVENT_B4]


def expected_baseline() -> dict:
    cleaned = clean_orders()
    dedup = deduplicate_orders(cleaned)
    gold = compute_gold_orders(dedup)
    return {
        "raw": len(MOCK_ORDERS),
        "clean": len(cleaned),
        "valid": sum(row["is_valid"] for row in cleaned),
        "quarantine": sum(not row["is_valid"] for row in cleaned),
        "dedup": len(dedup),
        "gold": len(gold),
        "amount_inr": round(sum(row["amount_inr"] for row in gold), 2),
        "points": sum(row["points_earned"] for row in gold),
    }
