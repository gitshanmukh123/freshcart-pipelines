"""Build the runnable FreshCart Colab notebook without requiring nbformat."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "elt" / "freshcart_elt.ipynb"


def md(source: str) -> dict:
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


cells = [
    md(
        """
# FreshCart Bronze to Gold ELT
**Course:** Data Engineering (CS8037) - From Git to Gold

**Status:** reconstructed runnable scaffold. The original FreshCart classroom
notebook was not available, so this notebook follows the assignment PDF and
documents every dataset assumption in `ASSUMPTIONS.md`. Outputs that require a
live Snowflake account or the Mage UI are intentionally NOT RUN here.

> Student checkpoints are left blank for your own predictions, observations,
> and explanations. Fill them before the viva and do not claim that generated
> scaffolding is an original instructor notebook.
"""
    ),
    md("## 0. Environment\nRun this cell once in Colab. Do not put credentials in the notebook."),
    code(
        """
!pip -q install "snowflake-connector-python[pandas]>=3.10,<4" "pika>=1.3,<2" "pytest>=8.2,<9"
"""
    ),
    code(
        """
import getpass
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
for path in (ROOT, ROOT / "elt"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from freshcart_data import (
    MOCK_CRM_EVENT_B4,
    MOCK_CRM_TIER_EVENTS,
    MOCK_ORDERS,
)
from freshcart_lib import (
    SQL_10_ORDERS_CLEAN,
    SQL_11_ORDERS_CLEAN_B3,
    SQL_B5_DELETE_FUTURE,
    SQL_B5_INSERT_FUTURE,
    build_gold,
    clean_orders,
    compute_gold_orders,
    connect_snowflake,
    counts,
    deduplicate_orders,
    execute_statements,
    expected_baseline,
    insert_crm_events,
    load_crm_history,
    load_file,
    print_quality,
    quality_report,
    refresh_clean,
    reject_orders,
    run_query,
    scalar,
    setup_snowflake,
    write_landing,
)

print("Repo root:", ROOT)
print("Local expected baseline:", expected_baseline())
"""
    ),
    md(
        """
## 1. Snowflake credentials
Use a personal Snowflake trial/account. The password is requested with
`getpass` and is not written to the notebook or repository.
"""
    ),
    code(
        """
if not os.getenv("SNOWFLAKE_ACCOUNT"):
    os.environ["SNOWFLAKE_ACCOUNT"] = getpass.getpass("Snowflake account identifier: ")
if not os.getenv("SNOWFLAKE_USER"):
    os.environ["SNOWFLAKE_USER"] = getpass.getpass("Snowflake user: ")
if not os.getenv("SNOWFLAKE_PASSWORD"):
    os.environ["SNOWFLAKE_PASSWORD"] = getpass.getpass("Snowflake password: ")
os.environ.setdefault("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
os.environ.setdefault("SNOWFLAKE_ROLE", "ACCOUNTADMIN")
os.environ.setdefault("SNOWFLAKE_DATABASE", "FRESHCART")
print("Credentials present for account:", os.environ["SNOWFLAKE_ACCOUNT"])
"""
    ),
    code(
        """
conn = connect_snowflake()
print("Connected:", conn.account, conn.user)
"""
    ),
    md(
        """
## Part A - Git and reproducible workflow

### A1. Repository evidence
Run these commands from the repository. Replace the URL only if your fork is
different. Paste the real output into the report; do not fabricate commit hashes.
"""
    ),
    code(
        """
!git remote -v
!git status --short --branch
!git log --oneline --decorate -10
"""
    ),
    md(
        """
### A2. Student identity and secret hygiene
Fill in your own details. `.gitignore` already excludes credentials, data,
pickles, and the reference PDF.
"""
    ),
    code(
        """
STUDENT_NAME = ""
STUDENT_ID = ""
STUDENT_EMAIL = ""
print("Student:", STUDENT_NAME or "<fill in>", STUDENT_ID or "<fill in>", STUDENT_EMAIL or "<fill in>")
print("RABBITMQ_URL set:", bool(os.getenv("RABBITMQ_URL")))
"""
    ),
    md(
        """
### A3. Failing test, then green test
The test asserts exactly 120 train rows and 30 test rows. For the red run,
temporarily change `test_size=0.2` to `test_size=0.3` in
`iris_project/transformers/prepare_data.py`, run the test, record the failure,
restore `0.2`, and rerun. Then commit and show the GitHub Actions run.

**Student checkpoint A3** - failure message, commit hash, Actions URL, and your
one-paragraph explanation:
"""
    ),
    code(
        """
!python -m pytest tests/test_prepare_data.py -q
!grep -n "test_size" iris_project/transformers/prepare_data.py
"""
    ),
    md(
        """
## Part B - FreshCart ELT

### B0. Create database, schemas, stage, and tables
"""
    ),
    code(
        """
setup_snowflake(conn)
print("Schemas:", run_query(conn, "SHOW SCHEMAS IN DATABASE FRESHCART"))
"""
    ),
    md(
        """
### B1. Land reconstructed raw data and build CLEAN
This cell writes timestamped NDJSON with `write_landing`, `PUT`s it to the
Snowflake stage, and uses `COPY INTO` through `load_file`. The fixture has 8 raw
rows: 6 website rows plus 2 mobile updates. `ORD-1003` website has a NULL amount
and is superseded later by the mobile row. Rewrite this section with your own
explanation before submission.
"""
    ),
    code(
        """
import pandas as pd

execute_statements(conn, "TRUNCATE TABLE FRESHCART.RAW.ORDERS;")
batch_file = write_landing(conn, pd.DataFrame(MOCK_ORDERS))
print("Landed file:", batch_file)
print("COPY result:", load_file(conn, batch_file))
raw_count = scalar(conn, "SELECT COUNT(*) FROM FRESHCART.RAW.ORDERS")
print("RAW rows:", raw_count)
print(run_query(conn, "SELECT channel, COUNT(*) FROM FRESHCART.RAW.ORDERS GROUP BY channel ORDER BY channel"))
print(SQL_10_ORDERS_CLEAN[:1200])
"""
    ),
    code(
        """
clean_count = refresh_clean(conn, include_unsupported=False)
rows = run_query(conn, '''
  SELECT order_id, channel, quantity, amount, currency, validation_errors, is_valid
  FROM FRESHCART.CLEAN.ORDERS_CLEAN
  ORDER BY order_id, channel
''')
for row in rows:
    print(row)
print("CLEAN rows:", clean_count)
print("Quarantine count:", scalar(conn, "SELECT COUNT(*) FROM FRESHCART.CLEAN.ORDERS_CLEAN WHERE NOT is_valid"))
"""
    ),
    md(
        """
**Expected B1:** 8 raw, 6 valid, 2 quarantined. At this point `ORD-1006` is
quarantined for `invalid_quantity`; B3 adds the unsupported-currency reason.
"""
    ),
    md(
        """
### B2. Reject invalid rows and deduplicate
Quarantine is MERGE-keyed by `order_id` plus `row_hash`. Deduplication keeps the
latest `updated_at` for each `order_id`, falling back to load time and filename.
"""
    ),
    code(
        """
dedup_count = reject_orders(conn)
print("DEDUP rows:", dedup_count)
print(run_query(conn, '''
  SELECT order_id, channel, amount, updated_at
  FROM FRESHCART.CLEAN.ORDERS_DEDUP
  ORDER BY order_id
'''))
print(run_query(conn, '''
  SELECT order_id, reasons
  FROM FRESHCART.QUARANTINE.ORDERS_QUARANTINE
  ORDER BY order_id
'''))
print_quality([{
    "check": "duplicate_dedup_order_ids",
    "count": scalar(conn, "SELECT COUNT(*) FROM (SELECT order_id FROM FRESHCART.CLEAN.ORDERS_DEDUP GROUP BY order_id HAVING COUNT(*) > 1)"),
    "status": "PASS" if scalar(conn, "SELECT COUNT(*) FROM (SELECT order_id FROM FRESHCART.CLEAN.ORDERS_DEDUP GROUP BY order_id HAVING COUNT(*) > 1)") == 0 else "PROBLEM",
}])
"""
    ),
    md(
        """
**Student checkpoint B2** - explain why there are 2 quarantine rows and 4
deduplicated orders. State which raw row won each duplicate and why.
"""
    ),
    md(
        """
### B3. Add unsupported-currency validation
The final CLEAN definition adds `unsupported_currency`. `ORD-1006` already has
an invalid quantity, so its reasons become a two-element array. The quarantine
MERGE updates the existing row rather than adding a duplicate.
"""
    ),
    code(
        """
refresh_clean(conn, include_unsupported=True)
reject_orders(conn)
print("Quarantine rows:", scalar(conn, "SELECT COUNT(*) FROM FRESHCART.QUARANTINE.ORDERS_QUARANTINE"))
print(run_query(conn, '''
  SELECT order_id, reasons
  FROM FRESHCART.QUARANTINE.ORDERS_QUARANTINE
  WHERE order_id = 'ORD-1006'
'''))
print(SQL_11_ORDERS_CLEAN_B3[-700:])
"""
    ),
    md(
        """
**Student checkpoint B3** - why must `ORD-1006` not create a second quarantine
row? Refer to the MERGE key and the reason-array update.
"""
    ),
    md(
        """
### B4. CRM tier history as SCD Type 2
`CUSTOMER_TIER_HISTORY` stores one row per tier version. Close the old current
row at the next different tier's `effective_from`; a repeated same-tier event is
not a new version. The Gold fact is refreshed through a staging table and a
MERGE keyed by `order_id`, with `row_hash` preventing no-change rewrites.
"""
    ),
    code(
        """
insert_crm_events(conn)
print("CRM events:", scalar(conn, "SELECT COUNT(*) FROM FRESHCART.CRM.CUSTOMER_TIER_EVENTS"))
print("CRM history rows:", load_crm_history(conn))
print(run_query(conn, '''
  SELECT customer_id, tier, effective_from, effective_to, is_current
  FROM FRESHCART.CRM.CUSTOMER_TIER_HISTORY
  ORDER BY customer_id, effective_from
'''))
"""
    ),
    code(
        """
print("Gold rows:", build_gold(conn))
base_gold = run_query(conn, '''
  SELECT order_id, tier, amount_inr, points_earned
  FROM FRESHCART.GOLD.FACT_ORDERS
  ORDER BY order_id
''')
for row in base_gold:
    print(row)
print("Baseline totals:", run_query(conn, "SELECT SUM(amount_inr), SUM(points_earned) FROM FRESHCART.GOLD.FACT_ORDERS"))
base_hashes = dict(run_query(conn, "SELECT order_id, row_hash FROM FRESHCART.GOLD.FACT_ORDERS"))
"""
    ),
    md(
        """
**Student checkpoint B4 predictions (write before running B4 event addition):**

1. Which customer's tier changes, and from what to what?
2. How many Gold rows change on the first B4 run?
3. What happens to totals and to the count of changed rows when the same event is repeated?

Your predictions:
"""
    ),
    code(
        """
print("Before B4:", run_query(conn, "SELECT SUM(amount_inr), SUM(points_earned) FROM FRESHCART.GOLD.FACT_ORDERS"))
insert_crm_events(conn, [MOCK_CRM_EVENT_B4])
print("History rows after B4:", load_crm_history(conn))
print("Gold rows after B4:", build_gold(conn))
print(run_query(conn, '''
  SELECT order_id, customer_id, tier, amount_inr, points_earned
  FROM FRESHCART.GOLD.FACT_ORDERS
  ORDER BY order_id
'''))
print("After B4 totals:", run_query(conn, "SELECT SUM(amount_inr), SUM(points_earned) FROM FRESHCART.GOLD.FACT_ORDERS"))
after_b4_hashes = dict(run_query(conn, "SELECT order_id, row_hash FROM FRESHCART.GOLD.FACT_ORDERS"))
print("Changed order ids on first B4 run:", sorted(k for k in base_hashes if base_hashes[k] != after_b4_hashes[k]))
"""
    ),
    code(
        """
before_repeat = dict(run_query(conn, "SELECT order_id, row_hash FROM FRESHCART.GOLD.FACT_ORDERS"))
insert_crm_events(conn, [MOCK_CRM_EVENT_B4])
print("History rows after repeat:", load_crm_history(conn))
print("Gold rows after repeat:", build_gold(conn))
after_repeat = dict(run_query(conn, "SELECT order_id, row_hash FROM FRESHCART.GOLD.FACT_ORDERS"))
print("Changed order ids on no-change repeat:", sorted(k for k in before_repeat if before_repeat[k] != after_repeat[k]))
print("Totals after repeat:", run_query(conn, "SELECT SUM(amount_inr), SUM(points_earned) FROM FRESHCART.GOLD.FACT_ORDERS"))
"""
    ),
    md(
        """
**Expected B4:** Arjun (`CUST-02`) moves Bronze -> Gold on `2026-08-15`.
`ORD-1002` becomes Gold and earns 39 points. The first B4 run changes exactly one
Gold row; the no-change repeat changes zero and keeps totals at INR 7785 / 146.
The time-window query above is only a demo; in the report prefer a before/after
row snapshot or `row_hash` comparison.
"""
    ),
    md(
        """
### B5. Data-quality checks plus future-date probe
Five baseline checks must all return 0. The sixth check looks for future order
dates. Insert a temporary 2099 row directly into `CLEAN.ORDERS_DEDUP`, show the
problem, delete it, and show zero again. This keeps RAW unchanged.
"""
    ),
    code(
        """
print("Baseline five checks:")
print_quality(quality_report(conn, include_b5=False))
print("Future check before probe:")
print_quality(quality_report(conn, include_b5=True)[-1:])
execute_statements(conn, SQL_B5_INSERT_FUTURE)
print("Future check with probe:")
print_quality(quality_report(conn, include_b5=True)[-1:])
execute_statements(conn, SQL_B5_DELETE_FUTURE)
print("Future check after cleanup:")
print_quality(quality_report(conn, include_b5=True))
"""
    ),
    md(
        """
**Student checkpoint B5** - explain why a zero-row check is evidence of quality,
and why the probe is inserted into `CLEAN.ORDERS_DEDUP` rather than RAW.
"""
    ),
    md(
        """
## Part C - Mage Iris pipeline

### C1. Baseline pipeline
The Mage project lives in `iris_project/`. Blocks: `load_iris -> prepare_data ->
train_model -> save_results`. The final pipeline adds `validate_data` before
`prepare_data` and `evaluate_model` beside `save_results`. The split is
stratified 80/20 with `random_state=42`; the tree uses `random_state=42` and a
default `max_depth=3`; the test threshold is 0.90.

Run the commands below in a terminal with Mage installed. They are NOT RUN in
this notebook because the Mage runtime is not available in the scaffold.
"""
    ),
    code(
        """
# Not executed in the scaffold: Mage UI/runtime commands.
# !pip -q install -r requirements-mage.txt
# !mage start iris_project
# Then open the Iris pipeline in the Mage UI and run it.
!python -m pytest tests/test_prepare_data.py tests/test_validate_data.py -q
"""
    ),
    md(
        """
**Student checkpoint C1** - paste a hand-drawn or Mermaid pipeline diagram and
your own one-paragraph explanation of the two extra blocks.
"""
    ),
    md(
        """
### C2-C4. Depth experiment, evaluation, and validation
The cells below use a local fallback call to the same Mage block functions, so
you can reproduce the numbers without the Mage UI. This is **not** a substitute
for the required Mage run screenshots. Record both: fallback evidence and Mage
UI evidence.
"""
    ),
    code(
        """
from iris_project.data_loaders.load_iris import load_data
from iris_project.transformers.prepare_data import transform as prepare_transform
from iris_project.transformers.validate_data import transform as validate_transform
from iris_project.transformers.train_model import train
from iris_project.transformers.evaluate_model import evaluate

iris = load_data()
iris = validate_transform(iris)
prepared = prepare_transform(iris)
results = []
for depth in [1, 2, 3, 5, None]:
    result = train(prepared, max_depth=depth)
    results.append((depth, round(result["accuracy"], 4)))
print("depth, accuracy")
for row in results:
    print(row)
"""
    ),
    code(
        """
chosen = train(prepared, max_depth=3)
evaluation = evaluate(chosen)
print(evaluation["confusion_matrix"])
print(evaluation["metrics"].to_string(index=False))
"""
    ),
    md(
        """
**Student checkpoint C2** - record the Mage UI experiment table and choose the
best depth. Explain underfitting/overfitting and why a deeper tree is not always
better. **C3** - include the confusion matrix and classification report.
**C4** - explain what `validate_data` checks and what happens on malformed Iris data.
"""
    ),
    md(
        """
## Part D - RabbitMQ topic exchange

### D1. Predictions (write before running)
CloudAMQP or another broker is required. Set `RABBITMQ_URL` in the environment;
never paste the URL into a committed cell.
"""
    ),
    md(
        """
| Scenario | Driver(s) that receive it | Why |
|---|---|---|
| `bangalore.koramangala.ride` |  |  |
| `bangalore.indiranagar.food` |  |  |
| `bangalore.whitefield.food` |  |  |
| `bangalore.jayanagar.ride` |  |  |
| `chennai.tnagar.food` |  |  |
| A message whose JSON omits `zone` |  |  |

**Student checkpoint D1** - fill the table and explain `*` versus `#`, including
whether Control receives every Bangalore event.
"""
    ),
    code(
        """
if not os.getenv("RABBITMQ_URL"):
    os.environ["RABBITMQ_URL"] = getpass.getpass("RabbitMQ URL (hidden): ")
print("RabbitMQ URL configured:", bool(os.getenv("RABBITMQ_URL")))
"""
    ),
    md(
        """
### D2. Dispatch and consume
This cell starts the six drivers as bounded background processes, publishes 30
events with fault mode on, and writes each driver's log under `stream/logs/`.
Open the logs and paste the real ACK/NACK lines into the report.
"""
    ),
    code(
        """
from stream.common import DRIVER_BINDINGS

log_dir = ROOT / "stream" / "logs"
log_dir.mkdir(exist_ok=True)
processes = []
for name, pattern in DRIVER_BINDINGS.items():
    log_handle = open(log_dir / f"{name.lower()}.log", "w", encoding="utf-8")
    processes.append((
        name,
        log_handle,
        subprocess.Popen(
            [sys.executable, "stream/driver.py", "--name", name, "--pattern", pattern, "--duration", "8"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        ),
    ))
time.sleep(2)
subprocess.run(
    [sys.executable, "stream/dispatcher.py", "--count", "30", "--interval", "0.05", "--fault-mode"],
    check=False,
    env=os.environ.copy(),
)
for name, handle, process in processes:
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        process.terminate()
    handle.close()
for name in DRIVER_BINDINGS:
    print("=" * 20, name)
    print((log_dir / f"{name.lower()}.log").read_text(encoding="utf-8")[-1500:])
"""
    ),
    md(
        """
### D3. ACK/NACK behaviour
A valid message with `zone` is ACKed after processing. A message whose JSON omits
`zone` is NACKed with `requeue=False`, even though its routing key still reaches
the driver's queue. Record one real ACK and one real NACK log line.

**Student checkpoint D3** - explain why an ACK without a valid zone would be
wrong, and why `requeue=False` is chosen.
"""
    ),
    md(
        """
### D4. Bonus - RabbitMQ to lakehouse
The producer publishes `freshcart.order.<channel>` on the same exchange. The
consumer binds `freshcart.order.#`, writes NDJSON and `fsync`s it before ACK,
then loads a local deduplicated table. Replaying the same batch keeps the table
row count stable. Add `--snowflake` to load `ORDER_EVENTS_RAW` and
`GOLD.ORDER_EVENTS` in Snowflake.
"""
    ),
    code(
        """
consumer_log = open(ROOT / "stream" / "logs" / "lakehouse.log", "w", encoding="utf-8")
consumer = subprocess.Popen(
    [sys.executable, "stream/lakehouse_consumer.py", "--max-messages", "8"],
    stdout=consumer_log,
    stderr=subprocess.STDOUT,
    env=os.environ.copy(),
)
time.sleep(2)
subprocess.run(
    [sys.executable, "stream/order_producer.py", "--interval", "0.05"],
    check=False,
    env=os.environ.copy(),
)
try:
    consumer.wait(timeout=20)
except subprocess.TimeoutExpired:
    consumer.terminate()
consumer_log.close()
print((ROOT / "stream" / "logs" / "lakehouse.log").read_text(encoding="utf-8")[-2500:])
print("Replay: run stream/lakehouse_consumer.py --replay <batch.ndjson>.")
"""
    ),
    md(
        """
**Student checkpoint D4** - include the persisted batch filename, before/after
table row counts, and the replay comparison. Explain why persist-before-ACK is
safer than ACK-before-persist.
"""
    ),
    md(
        """
## Part E - Report
Use `Report_Template.docx` and keep the report within 8 pages excluding
appendices. Include your own explanations, real screenshots/logs, commit hashes,
and the viva-ready design rationale. Do not include the reference PDF or secrets.
"""
    ),
    md(
        """
### Final reproducibility check
"""
    ),
    code(
        """
print("Counts:", counts(conn))
print("Final quality report:")
print_quality(quality_report(conn, include_b5=True))
print("Expected after B4: 8 raw, 6 valid, 2 quarantine, 4 dedup, 4 gold, INR 7785, 146 points")
"""
    ),
]

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12",
        },
        "colab": {
            "provenance": [],
            "toc_visible": True,
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {OUT} with {len(cells)} cells")
