"""FreshCart ELT helpers and the classroom SQL scripts.

The Snowflake SQL follows the reference workbook. The Python helpers below are a
small local mirror of the same rules so the fixture can be checked in CI without
a live Snowflake account.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from freshcart_data import (
    MOCK_CRM_EVENT_B4,
    MOCK_CRM_TIER_EVENTS,
    MOCK_FX_RESPONSES,
    MOCK_MOBILE_ORDERS,
    MOCK_PINCODES,
    MOCK_WEB_ORDERS,
    mock_pincode_response,
)

TIER_MULTIPLIERS = {"Silver": 1, "Gold": 2, "Platinum": 3}
SUPPORTED_CURRENCIES = ("INR", "USD")
STATE_REGION = {
    "Tamil Nadu": "South",
    "Karnataka": "South",
    "Kerala": "South",
    "Andhra Pradesh": "South",
    "Telangana": "South",
    "Puducherry": "South",
    "Maharashtra": "West",
    "Gujarat": "West",
    "Goa": "West",
    "Rajasthan": "West",
    "Delhi": "North",
    "Haryana": "North",
    "Punjab": "North",
    "Uttar Pradesh": "North",
    "Himachal Pradesh": "North",
    "Jammu and Kashmir": "North",
    "Uttarakhand": "North",
    "West Bengal": "East",
    "Odisha": "East",
    "Bihar": "East",
    "Jharkhand": "East",
    "Assam": "East",
    "Madhya Pradesh": "Central",
    "Chhattisgarh": "Central",
}

LANDING_DIR = os.getenv("FRESHCART_LANDING", "landing")

SQL_00_SETUP = r"""
CREATE WAREHOUSE IF NOT EXISTS FRESHCART_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
USE WAREHOUSE FRESHCART_WH;

CREATE DATABASE IF NOT EXISTS {database};
USE DATABASE {database};

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS dim;
CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS quarantine;

CREATE FILE FORMAT IF NOT EXISTS bronze.ff_ndjson TYPE = JSON COMPRESSION = AUTO;
CREATE STAGE IF NOT EXISTS bronze.landing FILE_FORMAT = bronze.ff_ndjson;

CREATE TABLE IF NOT EXISTS bronze.orders_raw (
  ingest_seq   NUMBER AUTOINCREMENT START 1 INCREMENT 1 ORDER,
  source       STRING,
  raw          VARIANT,
  run_id       STRING,
  extracted_at TIMESTAMP_TZ,
  src_file     STRING,
  src_row      NUMBER,
  loaded_at    TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);
CREATE TABLE IF NOT EXISTS bronze.customers_raw (
  ingest_seq NUMBER AUTOINCREMENT START 1 INCREMENT 1 ORDER, source STRING, raw VARIANT,
  run_id STRING, extracted_at TIMESTAMP_TZ, src_file STRING, src_row NUMBER,
  loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);
CREATE TABLE IF NOT EXISTS bronze.fx_raw (
  ingest_seq NUMBER AUTOINCREMENT START 1 INCREMENT 1 ORDER, source STRING, raw VARIANT,
  run_id STRING, extracted_at TIMESTAMP_TZ, src_file STRING, src_row NUMBER,
  loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);
CREATE TABLE IF NOT EXISTS bronze.pincode_raw (
  ingest_seq NUMBER AUTOINCREMENT START 1 INCREMENT 1 ORDER, source STRING, raw VARIANT,
  run_id STRING, extracted_at TIMESTAMP_TZ, src_file STRING, src_row NUMBER,
  loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE ref.tier_multiplier AS
SELECT * FROM VALUES ('Silver', 1), ('Gold', 2), ('Platinum', 3) AS v(tier, multiplier);

CREATE OR REPLACE TABLE ref.state_region AS
SELECT * FROM VALUES
  ('Tamil Nadu','South'), ('Karnataka','South'), ('Kerala','South'), ('Andhra Pradesh','South'),
  ('Telangana','South'), ('Puducherry','South'),
  ('Maharashtra','West'), ('Gujarat','West'), ('Goa','West'), ('Rajasthan','West'),
  ('Delhi','North'), ('Haryana','North'), ('Punjab','North'), ('Uttar Pradesh','North'),
  ('Himachal Pradesh','North'), ('Jammu and Kashmir','North'), ('Uttarakhand','North'),
  ('West Bengal','East'), ('Odisha','East'), ('Bihar','East'), ('Jharkhand','East'), ('Assam','East'),
  ('Madhya Pradesh','Central'), ('Chhattisgarh','Central')
  AS v(state, region);

CREATE TABLE IF NOT EXISTS ref.pincode_geo (
  pincode STRING PRIMARY KEY, city STRING, state STRING, region STRING,
  updated_at TIMESTAMP_LTZ
);

CREATE TABLE IF NOT EXISTS quarantine.orders (
  run_id STRING, quarantined_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  ingest_seq NUMBER, source STRING, order_id STRING, reasons ARRAY, row_data VARIANT
);

CREATE TABLE IF NOT EXISTS gold.fct_orders (
  order_id STRING PRIMARY KEY, order_date DATE, cust_id STRING, email STRING,
  tier STRING, multiplier NUMBER, amount NUMBER(12,2), currency STRING,
  fx_rate NUMBER(12,4), amount_inr NUMBER(14,2), loyalty_points NUMBER,
  is_high_value BOOLEAN, city STRING, state STRING, region STRING,
  updated_at TIMESTAMP_NTZ, row_hash NUMBER, published_at TIMESTAMP_LTZ
);
"""

SQL_10_ORDERS_CLEAN = r"""
CREATE OR REPLACE TRANSIENT TABLE silver.orders_checked AS
WITH unified AS (
  SELECT ingest_seq, source,
         raw:order_id::STRING   AS order_id,
         raw:cust_email::STRING AS cust_email,
         raw:cust_name::STRING  AS cust_name,
         raw:order_date::STRING AS order_date,
         raw:amount::STRING     AS amount,
         raw:currency::STRING   AS currency,
         raw:pincode::STRING    AS pincode,
         raw:updated_at::STRING AS updated_at
  FROM bronze.orders_raw WHERE source = 'web'
  UNION ALL
  SELECT ingest_seq, source,
         raw:orderId::STRING, raw:customer.email::STRING, raw:customer.name::STRING,
         raw:orderDate::STRING, raw:total.value::STRING, raw:total.currency::STRING,
         raw:deliveryPin::STRING, raw:updatedAt::STRING
  FROM bronze.orders_raw WHERE source = 'mobile'
),
typed AS (
  SELECT
    ingest_seq, source,
    TRIM(order_id)                                    AS order_id,
    LOWER(TRIM(cust_email))                           AS email,
    INITCAP(RTRIM(TRIM(cust_name), '.'))              AS name,
    COALESCE(
      TRY_TO_DATE(order_date, 'YYYY-MM-DD'),
      TRY_TO_DATE(order_date, 'DD/MM/YYYY'),
      TRY_TO_DATE(order_date, 'MON DD, YYYY')
    )                                                 AS order_date,
    TRY_TO_DECIMAL(REGEXP_REPLACE(amount, '[^0-9.-]', ''), 12, 2) AS amount,
    UPPER(TRIM(currency))                             AS currency,
    TRIM(pincode)                                     AS pincode,
    TRY_TO_TIMESTAMP_NTZ(updated_at)                  AS updated_at
  FROM unified
)
SELECT *,
  ARRAY_CONSTRUCT_COMPACT(
    IFF(order_id IS NULL, 'missing_order_id', NULL),
    IFF(email IS NULL OR NOT REGEXP_LIKE(email, '^[^@\\s]+@[^@\\s]+\\.[a-z]{2,}$'), 'bad_email', NULL),
    IFF(pincode IS NULL OR NOT REGEXP_LIKE(pincode, '^[1-9][0-9]{5}$'), 'bad_pincode', NULL),
    IFF(order_date IS NULL, 'unparseable_date', NULL),
    IFF(updated_at IS NULL, 'unparseable_updated_at', NULL),
    IFF(amount <= 0, 'non_positive_amount', NULL)          -- NULL amount is allowed (flagged below)
  ) AS reasons
FROM typed;

CREATE OR REPLACE TABLE silver.orders_clean AS
SELECT * EXCLUDE reasons, (amount IS NULL) AS amount_missing
FROM silver.orders_checked
WHERE ARRAY_SIZE(reasons) = 0;

INSERT INTO quarantine.orders (run_id, ingest_seq, source, order_id, reasons, row_data)
SELECT $run_id, c.ingest_seq, c.source, c.order_id, c.reasons, OBJECT_CONSTRUCT(*)
FROM silver.orders_checked c
WHERE ARRAY_SIZE(c.reasons) > 0
  AND NOT EXISTS (
        SELECT 1 FROM quarantine.orders q
        WHERE q.source = c.source
          AND EQUAL_NULL(q.order_id, c.order_id)
          AND EQUAL_NULL(q.row_data:UPDATED_AT::TIMESTAMP_NTZ, c.updated_at))
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.source, c.order_id, c.updated_at
                           ORDER BY c.ingest_seq DESC) = 1;
"""

SQL_10_ORDERS_CLEAN_B3 = SQL_10_ORDERS_CLEAN.replace(
    "    IFF(amount <= 0, 'non_positive_amount', NULL)          -- NULL amount is allowed (flagged below)\n",
    "    IFF(amount <= 0, 'non_positive_amount', NULL),         -- NULL amount is allowed (flagged below)\n"
    "    IFF(UPPER(TRIM(currency)) NOT IN ('INR', 'USD'), 'unsupported_currency', NULL)\n",
)

SQL_20_ORDERS_DEDUP = r"""
CREATE OR REPLACE TABLE silver.orders_dedup AS
SELECT *
FROM silver.orders_clean
QUALIFY ROW_NUMBER() OVER (
          PARTITION BY order_id
          ORDER BY updated_at DESC, ingest_seq DESC
        ) = 1;
"""

SQL_30_CUSTOMERS_SCD2 = r"""
CREATE OR REPLACE TABLE dim.customers_scd2 AS
WITH events AS (
  SELECT raw:cust_id::STRING                 AS cust_id,
         LOWER(TRIM(raw:email::STRING))      AS email,
         INITCAP(TRIM(raw:tier::STRING))     AS tier,
         TRY_TO_DATE(raw:effective_from::STRING) AS valid_from,
         loaded_at, ingest_seq
  FROM bronze.customers_raw
  QUALIFY ROW_NUMBER() OVER (PARTITION BY cust_id, valid_from
                             ORDER BY loaded_at DESC, ingest_seq DESC) = 1
)
SELECT cust_id, email, tier, valid_from,
       COALESCE(DATEADD(day, -1, LEAD(valid_from) OVER (PARTITION BY cust_id ORDER BY valid_from)),
                '9999-12-31'::DATE)                                       AS valid_to,
       LEAD(valid_from) OVER (PARTITION BY cust_id ORDER BY valid_from) IS NULL AS is_current
FROM events
WHERE cust_id IS NOT NULL AND valid_from IS NOT NULL;
"""

SQL_31_FX_DAILY = r"""
CREATE OR REPLACE TABLE ref.fx_daily AS
WITH published AS (
  SELECT r.raw:base::STRING          AS currency,
         f.key::DATE                 AS rate_date,
         f.value:INR::NUMBER(12,4)   AS rate_to_inr
  FROM bronze.fx_raw r, LATERAL FLATTEN(input => r.raw:rates) f
  QUALIFY ROW_NUMBER() OVER (PARTITION BY currency, rate_date
                             ORDER BY r.loaded_at DESC, r.ingest_seq DESC) = 1
),
bounds AS (
  SELECT MIN(rate_date) AS d0, GREATEST(MAX(rate_date), CURRENT_DATE()) AS d1 FROM published
),
spine AS (
  SELECT DATEADD(day, ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1, b.d0) AS d
  FROM bounds b, TABLE(GENERATOR(ROWCOUNT => 4000))
  QUALIFY d <= (SELECT d1 FROM bounds)
),
filled AS (
  SELECT c.currency, s.d AS rate_date,
         LAST_VALUE(p.rate_to_inr) IGNORE NULLS OVER (
           PARTITION BY c.currency ORDER BY s.d
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS rate_to_inr,
         p.rate_to_inr IS NULL AS is_carried_forward
  FROM spine s
  CROSS JOIN (SELECT DISTINCT currency FROM published) c
  LEFT JOIN published p ON p.currency = c.currency AND p.rate_date = s.d
)
SELECT currency, rate_date, rate_to_inr, is_carried_forward FROM filled
UNION ALL
SELECT 'INR', d, 1.0, FALSE FROM spine;
"""

SQL_32_PINCODE_GEO = r"""
MERGE INTO ref.pincode_geo t
USING (
  SELECT p.pincode, p.city, p.state, sr.region
  FROM (
    SELECT raw:pincode::STRING                                  AS pincode,
           raw:response[0]:PostOffice[0]:District::STRING       AS city,
           raw:response[0]:PostOffice[0]:State::STRING          AS state,
           loaded_at, ingest_seq
    FROM bronze.pincode_raw
    WHERE raw:response[0]:Status::STRING = 'Success'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY pincode ORDER BY loaded_at DESC, ingest_seq DESC) = 1
  ) p
  LEFT JOIN ref.state_region sr ON sr.state = p.state
) s
ON t.pincode = s.pincode
WHEN MATCHED AND (t.city <> s.city OR t.state <> s.state OR NVL(t.region,'') <> NVL(s.region,''))
  THEN UPDATE SET city = s.city, state = s.state, region = s.region, updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED
  THEN INSERT (pincode, city, state, region, updated_at)
       VALUES (s.pincode, s.city, s.state, s.region, CURRENT_TIMESTAMP());
"""

SQL_40_GOLD = r"""
CREATE OR REPLACE TABLE silver.orders_enriched AS
SELECT o.*,
       c.cust_id, c.tier,
       m.multiplier,
       fx.rate_to_inr                              AS fx_rate,
       ROUND(o.amount * fx.rate_to_inr, 2)         AS amount_inr,
       FLOOR(amount_inr / 100) * m.multiplier      AS loyalty_points,
       amount_inr >= 2000                          AS is_high_value,
       g.city, g.state, g.region
FROM silver.orders_dedup o
LEFT JOIN dim.customers_scd2 c
       ON  c.email = o.email
       AND o.order_date BETWEEN c.valid_from AND c.valid_to
LEFT JOIN ref.tier_multiplier m ON m.tier = c.tier
LEFT JOIN ref.fx_daily fx
       ON  fx.currency = o.currency AND fx.rate_date = o.order_date
LEFT JOIN ref.pincode_geo g ON g.pincode = o.pincode;

MERGE INTO gold.fct_orders t
USING (
  SELECT order_id, order_date, cust_id, email, tier, multiplier, amount, currency, fx_rate,
         amount_inr, loyalty_points, is_high_value, city, state, region, updated_at,
         HASH(order_date, cust_id, email, tier, multiplier, amount, currency, fx_rate,
              amount_inr, loyalty_points, is_high_value, city, state, region, updated_at) AS row_hash
  FROM silver.orders_enriched
) s
ON t.order_id = s.order_id
WHEN MATCHED AND t.row_hash <> s.row_hash THEN UPDATE SET
  order_date = s.order_date, cust_id = s.cust_id, email = s.email, tier = s.tier,
  multiplier = s.multiplier, amount = s.amount, currency = s.currency, fx_rate = s.fx_rate,
  amount_inr = s.amount_inr, loyalty_points = s.loyalty_points, is_high_value = s.is_high_value,
  city = s.city, state = s.state, region = s.region, updated_at = s.updated_at,
  row_hash = s.row_hash, published_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT
  (order_id, order_date, cust_id, email, tier, multiplier, amount, currency, fx_rate, amount_inr,
   loyalty_points, is_high_value, city, state, region, updated_at, row_hash, published_at)
VALUES
  (s.order_id, s.order_date, s.cust_id, s.email, s.tier, s.multiplier, s.amount, s.currency,
   s.fx_rate, s.amount_inr, s.loyalty_points, s.is_high_value, s.city, s.state, s.region,
   s.updated_at, s.row_hash, CURRENT_TIMESTAMP());
"""

SQL_QUALITY_CHECKS = {
    "rows gained or lost while enriching": (
        "SELECT (SELECT COUNT(*) FROM silver.orders_enriched) - "
        "(SELECT COUNT(*) FROM silver.orders_dedup)"
    ),
    "duplicate orders in gold": (
        "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM gold.fct_orders"
    ),
    "orders with no customer match": (
        "SELECT COUNT_IF(cust_id IS NULL) FROM silver.orders_enriched"
    ),
    "orders with an amount but no FX rate": (
        "SELECT COUNT_IF(amount IS NOT NULL AND fx_rate IS NULL) FROM silver.orders_enriched"
    ),
    "orders with no city": (
        "SELECT COUNT_IF(city IS NULL) FROM silver.orders_enriched"
    ),
    "future order dates": (
        "SELECT COUNT(*) FROM silver.orders_dedup WHERE order_date > CURRENT_DATE()"
    ),
}

SQL_B5_INSERT_FUTURE = r"""
INSERT INTO silver.orders_dedup (
  ingest_seq, source, order_id, email, name, order_date, amount, currency,
  pincode, updated_at, amount_missing
) VALUES (
  999999, 'web', 'ORD-FUTURE-TEST', 'priya.r@gmail.com', 'Priya R',
  '2099-01-01'::DATE, 100.00, 'INR', '600041', '2099-01-01 00:00:00'::TIMESTAMP_NTZ, FALSE
);
"""

SQL_B5_DELETE_FUTURE = """
DELETE FROM silver.orders_dedup WHERE order_id = 'ORD-FUTURE-TEST';
"""


def connect_snowflake(**overrides: Any):
    try:
        import snowflake.connector
    except ImportError as exc:
        raise RuntimeError(
            "Install snowflake-connector-python[pandas] before running Snowflake cells"
        ) from exc

    params = {
        "account": overrides.get("account", os.getenv("SNOWFLAKE_ACCOUNT")),
        "user": overrides.get("user", os.getenv("SNOWFLAKE_USER")),
        "role": overrides.get("role", os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN")),
        "authenticator": overrides.get(
            "authenticator", os.getenv("SNOWFLAKE_AUTHENTICATOR")
        ),
    }
    if overrides.get("warehouse"):
        params["warehouse"] = overrides["warehouse"]
    if overrides.get("database"):
        params["database"] = overrides["database"]
    authenticator = str(params.get("authenticator") or "").lower()
    if authenticator != "externalbrowser":
        password = overrides.get("password", os.getenv("SNOWFLAKE_PASSWORD"))
        if password:
            params["password"] = password
    params = {key: value for key, value in params.items() if value is not None}
    return snowflake.connector.connect(**params)


def run_sql(conn, sql_text: str) -> None:
    conn.execute_string(sql_text, remove_comments=True)


def query(conn, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def show(conn, sql: str):
    import pandas as pd

    with conn.cursor() as cur:
        cur.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


def write_landing(source: str, records: Iterable[dict], run_id: str, landing_dir: str | Path | None = None) -> Path:
    folder = Path(landing_dir or LANDING_DIR) / source
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{source}__{run_id}.json.gz"
    now = datetime.now(timezone.utc).isoformat()
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for record in records:
            envelope = {
                "source": source,
                "run_id": run_id,
                "extracted_at": now,
                "data": record,
            }
            handle.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    print(f"   {source}: {len(records)} records -> {path}")
    return path


def load_file(conn, local_path: str | Path, table: str, stage_dir: str) -> None:
    uri = Path(local_path).resolve().as_uri()
    query(
        conn,
        f"PUT '{uri}' @bronze.landing/{stage_dir}/ AUTO_COMPRESS=FALSE OVERWRITE=FALSE",
    )
    rows = query(
        conn,
        f"""
        COPY INTO {table} (source, raw, run_id, extracted_at, src_file, src_row)
        FROM (
          SELECT $1:source::STRING, $1:data, $1:run_id::STRING,
                 $1:extracted_at::TIMESTAMP_TZ, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
          FROM @bronze.landing/{stage_dir}/
        )
        FILE_FORMAT = (FORMAT_NAME = 'bronze.ff_ndjson')
        ON_ERROR = 'ABORT_STATEMENT'
        """,
    )
    loaded = sum(int(row[3]) for row in rows if len(row) > 3)
    print(f"   {loaded} rows -> {table}")


def run_pipeline(
    conn,
    run_id: str | None = None,
    crm_events: Iterable[dict] | None = None,
    include_unsupported: bool = False,
    landing_dir: str | Path | None = None,
) -> dict:
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    crm_events = list(crm_events if crm_events is not None else MOCK_CRM_TIER_EVENTS)
    print("run_id:", run_id)

    print("1. EXTRACT: sample data -> raw files")
    web_file = write_landing("web", MOCK_WEB_ORDERS, run_id, landing_dir)
    mobile_file = write_landing("mobile", MOCK_MOBILE_ORDERS, run_id, landing_dir)
    crm_file = write_landing("crm", crm_events, run_id, landing_dir)
    fx_file = write_landing("fx", MOCK_FX_RESPONSES, run_id, landing_dir)

    print("2. LOAD: raw files -> bronze tables")
    load_file(conn, web_file, "bronze.orders_raw", f"orders_web/{run_id}")
    load_file(conn, mobile_file, "bronze.orders_raw", f"orders_mobile/{run_id}")
    load_file(conn, crm_file, "bronze.customers_raw", f"crm/{run_id}")
    load_file(conn, fx_file, "bronze.fx_raw", f"fx/{run_id}")

    print("3. TRANSFORM: bronze -> silver -> gold")
    query(conn, f"SET run_id = '{run_id}'")
    run_sql(conn, SQL_10_ORDERS_CLEAN_B3 if include_unsupported else SQL_10_ORDERS_CLEAN)
    run_sql(conn, SQL_20_ORDERS_DEDUP)

    pins = [
        row[0]
        for row in query(
            conn,
            """
            SELECT DISTINCT o.pincode FROM silver.orders_dedup o
            WHERE NOT EXISTS (SELECT 1 FROM ref.pincode_geo g WHERE g.pincode = o.pincode)
            """,
        )
    ]
    print("   new pincodes to look up:", pins)
    if pins:
        lookups = [{"pincode": pin, "response": mock_pincode_response(pin)} for pin in pins]
        pin_file = write_landing("pincode", lookups, run_id, landing_dir)
        load_file(conn, pin_file, "bronze.pincode_raw", f"pincode/{run_id}")

    run_sql(conn, SQL_30_CUSTOMERS_SCD2)
    run_sql(conn, SQL_31_FX_DAILY)
    run_sql(conn, SQL_32_PINCODE_GEO)
    run_sql(conn, SQL_40_GOLD)

    print("4. CHECK")
    report = quality_report(conn, include_b5=True)
    print_quality(report)
    rejected = query(
        conn,
        "SELECT COUNT_IF(ARRAY_SIZE(reasons) > 0) / NULLIF(COUNT(*), 0) FROM silver.orders_checked",
    )[0][0]
    print(f"   {'share of rows rejected':38s} {float(rejected or 0):.0%}")
    orders, revenue, points = query(
        conn,
        "SELECT COUNT(*), SUM(amount_inr), SUM(loyalty_points) FROM gold.fct_orders",
    )[0]
    print(f"GOLD: {orders} orders, revenue ₹{revenue}, {points} loyalty points")
    return {
        "run_id": run_id,
        "orders": orders,
        "revenue": revenue,
        "points": points,
        "quality": report,
    }


def setup_snowflake(conn, database: str | None = None) -> None:
    name = database or os.getenv("SNOWFLAKE_DATABASE", "FRESHCART")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", name):
        raise ValueError(f"Unsafe database name: {name!r}")
    run_sql(conn, SQL_00_SETUP.format(database=name))


def quality_report(conn, include_b5: bool = False) -> list[dict]:
    checks = dict(SQL_QUALITY_CHECKS)
    if not include_b5:
        checks.pop("future order dates", None)
    report = []
    for name, sql in checks.items():
        value = int(query(conn, sql)[0][0] or 0)
        report.append(
            {"check": name, "count": value, "status": "OK" if value == 0 else "PROBLEM"}
        )
    return report


def print_quality(report: list[dict]) -> None:
    for row in report:
        print(f"   {row['check']:38s} {row['count']}   {row['status']}")


def counts(conn) -> dict:
    queries = {
        "raw": "SELECT COUNT(*) FROM bronze.orders_raw",
        "clean": "SELECT COUNT(*) FROM silver.orders_clean",
        "quarantine": "SELECT COUNT(*) FROM quarantine.orders",
        "dedup": "SELECT COUNT(*) FROM silver.orders_dedup",
        "customers": "SELECT COUNT(*) FROM dim.customers_scd2",
        "gold": "SELECT COUNT(*) FROM gold.fct_orders",
        "revenue_inr": "SELECT COALESCE(SUM(amount_inr), 0) FROM gold.fct_orders",
        "points": "SELECT COALESCE(SUM(loyalty_points), 0) FROM gold.fct_orders",
    }
    return {name: query(conn, sql)[0][0] for name, sql in queries.items()}


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    text = re.sub(r"[^0-9.-]", "", str(value))
    if not text or text in {"-", "."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _unified_rows() -> list[dict]:
    rows = []
    ingest_seq = 0
    for record in MOCK_WEB_ORDERS:
        ingest_seq += 1
        rows.append(
            {
                "ingest_seq": ingest_seq,
                "source": "web",
                "order_id": record.get("order_id"),
                "cust_email": record.get("cust_email"),
                "cust_name": record.get("cust_name"),
                "order_date": record.get("order_date"),
                "amount": record.get("amount"),
                "currency": record.get("currency"),
                "pincode": record.get("pincode"),
                "updated_at": record.get("updated_at"),
            }
        )
    for record in MOCK_MOBILE_ORDERS:
        ingest_seq += 1
        customer = record.get("customer") or {}
        total = record.get("total") or {}
        rows.append(
            {
                "ingest_seq": ingest_seq,
                "source": "mobile",
                "order_id": record.get("orderId"),
                "cust_email": customer.get("email"),
                "cust_name": customer.get("name"),
                "order_date": record.get("orderDate"),
                "amount": total.get("value"),
                "currency": total.get("currency"),
                "pincode": record.get("deliveryPin"),
                "updated_at": record.get("updatedAt"),
            }
        )
    return rows


def clean_orders(include_unsupported: bool = False) -> list[dict]:
    cleaned = []
    for row in _unified_rows():
        email = str(row.get("cust_email") or "").strip().lower()
        name = str(row.get("cust_name") or "").strip().rstrip(".").title()
        order_date = _parse_date(row.get("order_date"))
        amount = _parse_amount(row.get("amount"))
        currency = str(row.get("currency") or "").strip().upper()
        pincode = str(row.get("pincode") or "").strip()
        updated_at = _parse_timestamp(row.get("updated_at"))
        reasons = []
        if not str(row.get("order_id") or "").strip():
            reasons.append("missing_order_id")
        if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", email):
            reasons.append("bad_email")
        if not re.match(r"^[1-9][0-9]{5}$", pincode):
            reasons.append("bad_pincode")
        if order_date is None:
            reasons.append("unparseable_date")
        if updated_at is None:
            reasons.append("unparseable_updated_at")
        if amount is not None and amount <= 0:
            reasons.append("non_positive_amount")
        if include_unsupported and currency not in SUPPORTED_CURRENCIES:
            reasons.append("unsupported_currency")
        cleaned.append(
            {
                **row,
                "email": email,
                "name": name,
                "order_date": order_date,
                "amount": amount,
                "currency": currency,
                "pincode": pincode,
                "updated_at": updated_at,
                "amount_missing": amount is None,
                "reasons": reasons,
                "is_valid": not reasons,
            }
        )
    return cleaned


def deduplicate_orders(cleaned: list[dict]) -> list[dict]:
    winners: dict[str, dict] = {}
    for row in cleaned:
        if not row["is_valid"]:
            continue
        key = (row["updated_at"], row["ingest_seq"])
        current = winners.get(row["order_id"])
        if current is None or key > (current["updated_at"], current["ingest_seq"]):
            winners[row["order_id"]] = row
    return sorted(winners.values(), key=lambda row: row["order_id"])


def build_customer_history(events: Iterable[dict] | None = None) -> list[dict]:
    latest = {}
    for event in events if events is not None else MOCK_CRM_TIER_EVENTS:
        valid_from = _parse_date(event.get("effective_from"))
        if valid_from is None:
            continue
        key = (event.get("cust_id"), valid_from)
        latest[key] = {
            "cust_id": event.get("cust_id"),
            "email": str(event.get("email") or "").strip().lower(),
            "tier": str(event.get("tier") or "").strip().title(),
            "valid_from": valid_from,
        }
    ordered = sorted(latest.values(), key=lambda row: (row["cust_id"], row["valid_from"]))
    history = []
    for index, row in enumerate(ordered):
        next_row = ordered[index + 1] if index + 1 < len(ordered) else None
        if next_row and next_row["cust_id"] == row["cust_id"]:
            valid_to = next_row["valid_from"] - timedelta(days=1)
            is_current = False
        else:
            valid_to = date(9999, 12, 31)
            is_current = True
        history.append({**row, "valid_to": valid_to, "is_current": is_current})
    return history


def apply_b4(events: Iterable[dict] | None = None) -> list[dict]:
    return list(events if events is not None else MOCK_CRM_TIER_EVENTS) + [MOCK_CRM_EVENT_B4]


def tier_for_order(order_date: date, email: str, history: list[dict]) -> str:
    email = email.strip().lower()
    for row in history:
        if row["email"] == email and row["valid_from"] <= order_date <= row["valid_to"]:
            return row["tier"]
    raise ValueError(f"No customer tier covers {email} on {order_date}")


def _fx_rates() -> dict[tuple[str, date], float]:
    rates: dict[tuple[str, date], float] = {}
    for response in MOCK_FX_RESPONSES:
        base = str(response["base"]).upper()
        for day, values in response["rates"].items():
            rates[(base, _parse_date(day))] = float(values["INR"])
    return rates


def _fx_rate_for(currency: str, order_date: date) -> float:
    if currency == "INR":
        return 1.0
    rates = _fx_rates()
    eligible = [(day, rate) for (base, day), rate in rates.items() if base == currency and day <= order_date]
    if not eligible:
        raise ValueError(f"No FX rate for {currency} on {order_date}")
    return max(eligible, key=lambda item: item[0])[1]


def compute_gold_orders(
    dedup_rows: list[dict],
    events: Iterable[dict] | None = None,
) -> list[dict]:
    history = build_customer_history(events)
    gold = []
    for row in dedup_rows:
        tier = tier_for_order(row["order_date"], row["email"], history)
        multiplier = TIER_MULTIPLIERS[tier]
        if row["amount"] is None:
            amount_inr = None
            points = None
        else:
            amount_inr = round(row["amount"] * _fx_rate_for(row["currency"], row["order_date"]), 2)
            points = math.floor(amount_inr / 100) * multiplier
        city, state = MOCK_PINCODES.get(row["pincode"], (None, None))
        gold.append(
            {
                "order_id": row["order_id"],
                "order_date": row["order_date"],
                "email": row["email"],
                "tier": tier,
                "multiplier": multiplier,
                "amount": row["amount"],
                "currency": row["currency"],
                "amount_inr": amount_inr,
                "loyalty_points": points,
                "is_high_value": amount_inr is not None and amount_inr >= 2000,
                "city": city,
                "state": state,
                "region": STATE_REGION.get(state) if state else None,
            }
        )
    return sorted(gold, key=lambda row: row["order_id"])


def expected_baseline() -> dict:
    cleaned = clean_orders()
    dedup = deduplicate_orders(cleaned)
    gold = compute_gold_orders(dedup)
    return {
        "raw": len(MOCK_WEB_ORDERS) + len(MOCK_MOBILE_ORDERS),
        "clean": len(cleaned),
        "valid": sum(row["is_valid"] for row in cleaned),
        "quarantine": sum(not row["is_valid"] for row in cleaned),
        "dedup": len(dedup),
        "gold": len(gold),
        "amount_inr": round(sum(row["amount_inr"] for row in gold), 2),
        "points": sum(row["loyalty_points"] for row in gold),
        "rejected_share": 0.25,
    }
