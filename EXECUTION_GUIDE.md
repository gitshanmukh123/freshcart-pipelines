# End-to-End Execution Guide

This is the practical path from the local repository to the submitted evidence.
Commands assume Windows PowerShell unless a cell says otherwise.

## 0. Current status

| Item | Status |
|---|---|
| Source, tests, SQL, Mage blocks, stream scripts, notebook JSON | Implemented |
| Local pytest | 15 passed |
| GitHub repository / Actions | Not yet pushed from this workspace |
| Snowflake run | Pending personal credentials |
| Mage UI run | Pending Mage installation |
| Live RabbitMQ run | Pending broker URL |
| Bonus live run | Pending broker URL and optional Snowflake |
| Report | Student-owned; template checklist below |

Do not state that pending items passed. Replace every pending row only after you
have the real output.

## 1. Verify locally

```powershell
cd "C:\Users\saish\Music\data eng project\freshcart-pipelines"
python --version
python -m pip install -r requirements.txt
python -m pytest -q
python -c "import json; json.load(open('elt/freshcart_elt.ipynb', encoding='utf-8')); print('notebook JSON valid')"
```

Expected: Python 3.12.x, `15 passed`, and `notebook JSON valid`.

If `pytest` is missing, install it explicitly:

```powershell
python -m pip install pytest==8.3.5
```

## 2. Git and GitHub

The parent folder is already a Git repository. Do not initialize Git there. The
project must be its own repository.

```powershell
cd "C:\Users\saish\Music\data eng project\freshcart-pipelines"
git init -b main
git status
git add .gitignore README.md ASSUMPTIONS.md EXECUTION_GUIDE.md requirements*.txt .github elt iris_project stream tests tools
git commit -m "Scaffold FreshCart pipelines and local verification"
git remote add origin https://github.com/gitshanmukh123/freshcart-pipelines.git
git push -u origin main
```

If the remote already has a README or commits, fetch and reconcile before
pushing. Never force-push a shared repository.

Check what is staged before committing:

```powershell
git status --short
git diff --cached --stat
```

Never stage `Assignment_DE.docx.pdf`, `.env`, generated CSV/pickle files,
`stream/logs`, or `stream/lakehouse`.

## 3. A3 red/green test and Actions evidence

1. Confirm the clean state:

   ```powershell
   python -m pytest tests/test_prepare_data.py -q
   ```

2. Open `iris_project/transformers/prepare_data.py` and change the literal:

   ```python
   test_size=0.2
   ```

   to:

   ```python
   test_size=0.3
   ```

3. Run the same test. Capture the failure:

   ```powershell
   python -m pytest tests/test_prepare_data.py -q
   ```

   Expected failure: train count 105 and test count 45, not 120 and 30.

4. Commit and push the red state:

   ```powershell
   git add iris_project/transformers/prepare_data.py
   git commit -m "A3: deliberately break the 80/20 split test"
   git push
   ```

5. Open GitHub Actions and copy the failing run URL. Take a screenshot of the
   failing assertion.

6. Restore `test_size=0.2`, rerun, commit, and push:

   ```powershell
   python -m pytest tests/test_prepare_data.py -q
   git add iris_project/transformers/prepare_data.py
   git commit -m "A3: restore 80/20 split and green test"
   git push
   ```

7. Copy the green Actions run URL and screenshot.

Report checkpoint A3: red commit hash, red run URL, green commit hash, green run
URL, and your own explanation of why the test is meaningful.

## 4. Snowflake and Colab

### 4.1 Account setup

1. Create a Snowflake trial account.
2. Confirm a warehouse named `COMPUTE_WH` exists, or use your own warehouse name
   in `SNOWFLAKE_WAREHOUSE`.
3. Use a role that can create databases and schemas; `ACCOUNTADMIN` works for a
   course trial.
4. Keep the account identifier, user, and password out of the repository.

### 4.2 Colab

1. Upload the repository folder to Colab, or clone it:

   ```python
   !git clone https://github.com/gitshanmukh123/freshcart-pipelines.git
   %cd freshcart-pipelines
   ```

2. Install notebook dependencies if the notebook's first cell did not:

   ```python
   !pip -q install "snowflake-connector-python[pandas]>=3.10,<4" "pika>=1.3,<2" "pytest>=8.2,<9"
   ```

3. Open `elt/freshcart_elt.ipynb`.
4. Run the credentials cell. It asks for:
   - Snowflake account identifier, for example `abc12345.us-east-1`
   - user
   - password
5. Run the connection cell. Fix the account format if connection fails.

### 4.3 Expected Snowflake results

| Point | Expected |
|---|---|
| B1 raw | 8 |
| B1 valid / quarantine | 6 / 2 |
| B2 dedup | 4 |
| B3 `ORD-1006` reasons | `["invalid_quantity","unsupported_currency"]` |
| B4 baseline Gold | 4 rows, INR 7785, 126 points |
| B4 after Arjun event | ORD-1002 Gold, 39 points, INR 7785, 146 points |
| B4 first run changed rows | exactly 1 |
| B4 repeat changed rows | 0 |
| CRM history after B4 | 6 rows |
| B5 baseline checks | all 0 |
| B5 future probe | 1 PROBLEM, then 0 PASS after delete |

If a count differs, inspect the printed `validation_errors`, the CRM history
rows, and the dedup `updated_at` values before changing SQL. Do not hardcode the
expected totals into the transformation.

### 4.4 Save evidence

For the report, capture:

- Warehouse/database/schema tree.
- `RAW.ORDERS` row count and sample rows.
- `CLEAN.ORDERS_CLEAN` validation errors.
- `CLEAN.ORDERS_DEDUP` four rows.
- `QUARANTINE.ORDERS_QUARANTINE` two rows and `ORD-1006` reasons.
- CRM history with `effective_from`, `effective_to`, `is_current`.
- Baseline Gold totals and B4 Gold totals.
- B4 first-run and repeat changed-row evidence.
- B5 baseline and probe outputs.

## 5. Mage Iris

### 5.1 Install and run

```powershell
cd "C:\Users\saish\Music\data eng project\freshcart-pipelines"
python -m pip install -r requirements-mage.txt
mage start iris_project
```

Open the Mage UI and run the Iris pipeline. Capture:

- C1 pipeline diagram.
- C1 run success.
- C1 saved predictions file.
- C3 confusion matrix and classification report.
- C4 validation block success/failure demonstration.

### 5.2 C2 depth experiment

The cleanest reproducible record is the local fallback loop in the notebook.
For the required Mage evidence, run the pipeline once per depth by changing the
default in `iris_project/transformers/train_model.py`:

```python
max_depth = int(kwargs.get("max_depth", 3))
```

Use values 1, 2, 3, 5, and `None` (or remove the cap), run the pipeline each
time, and record accuracy. Restore the default to 3 for submission. Alternatively,
set `max_depth` through your Mage block configuration if your Mage version
supports it.

Report checkpoint C2: Mage table, chosen depth, your explanation of
underfitting/overfitting, and why the deeper tree is not automatically better.

## 6. RabbitMQ

### 6.1 Broker

1. Create a free CloudAMQP instance or use a local RabbitMQ broker.
2. Copy the AMQP/AMQPS URL.
3. Set it only in the current PowerShell session:

   ```powershell
   $env:RABBITMQ_URL = "amqps://USER:PASSWORD@HOST/VHOST"
   ```

Do not write it into a notebook, script, README, screenshot, or commit. If a
broker URL was previously exposed in a reference notebook, rotate that instance.

### 6.2 D1 predictions

Before starting any consumer, fill the six-row prediction table in the notebook.
Predict which named drivers receive each routing key. This must be your own work.

### 6.3 Run the drivers

Open six PowerShell terminals in the repository root and run one command per
terminal:

```powershell
python stream/driver.py --name Ravi --pattern "bangalore.koramangala.*" --duration 30
python stream/driver.py --name Priya --pattern "bangalore.indiranagar.*" --duration 30
python stream/driver.py --name Arjun --pattern "bangalore.*.ride" --duration 30
python stream/driver.py --name Meena --pattern "bangalore.*.food" --duration 30
python stream/driver.py --name Karthik --pattern "chennai.tnagar.food" --duration 30
python stream/driver.py --name Control --pattern "bangalore.#" --duration 30
```

Each driver declares a durable queue and binds it to the topic exchange. Keep the
terminals open.

### 6.4 Publish and observe

In a seventh terminal:

```powershell
python stream/dispatcher.py --count 30 --interval 0.05 --fault-mode
```

Fault mode omits the JSON `zone` every 10th message but leaves the routing key
intact. Expected pattern:

- Most deliveries log `ACK`.
- Fault-mode messages log `NACK ... reason=missing_zone`.
- Arjun receives only Bangalore `ride`.
- Meena receives only Bangalore `food`.
- Karthik receives only Chennai T. Nagar `food`.
- Control receives every Bangalore ride/food event.

If a driver receives nothing, check:

```powershell
python -c "from stream.common import topic_matches; print(topic_matches('bangalore.#', 'bangalore.koramangala.ride'))"
```

Also confirm the queue/exchange in the CloudAMQP management UI.

### 6.5 D3 explanation

For each ACK/NACK log line, explain:

- Why the message reached that driver.
- Why a missing `zone` cannot be ACKed.
- Why `requeue=False` is appropriate for this exercise.
- What would happen with `requeue=True` and a permanently malformed message.

## 7. Bonus - RabbitMQ to lakehouse

In one terminal, start the consumer:

```powershell
python stream/lakehouse_consumer.py --max-messages 8
```

In another, publish the eight FreshCart fixture events:

```powershell
python stream/order_producer.py --interval 0.05
```

Expected:

- Consumer logs `ACK persisted` for each event after `fsync`.
- `stream/lakehouse/landing/freshcart_orders_*.ndjson` exists.
- `stream/lakehouse/table/order_events.jsonl` has 8 event IDs.
- A manifest row is appended to `stream/lakehouse/table/batches.jsonl`.

Replay the same batch:

```powershell
python stream/lakehouse_consumer.py --replay "stream/lakehouse/landing/<batch>.ndjson"
```

Expected: table row count does not grow because `event_id` is the idempotency key.
The manifest grows. Replay evidence should show before/after counts.

Optional Snowflake load:

```powershell
python stream/lakehouse_consumer.py --replay "stream/lakehouse/landing/<batch>.ndjson" --snowflake
```

Expected: `RAW.ORDER_EVENTS_RAW` grows with copied files; `GOLD.ORDER_EVENTS`
deduplicates by `event_id` and does not double-count a replay. This path is
optional and should be marked NOT RUN unless you actually execute it.

## 8. Report and submission

Use the supplied `Report_Template.docx`. Keep the report within 8 pages excluding
appendices. Suggested structure:

1. Objective and architecture.
2. Git workflow and A3 red/green evidence.
3. FreshCart Bronze-to-Gold design and results.
4. B4 SCD2 predictions, result, and no-change explanation.
5. B5 data-quality checks and future-date probe.
6. Mage pipeline diagram, C2 results, C3 evaluation, C4 validation.
7. RabbitMQ topology, D1 predictions, ACK/NACK evidence.
8. Bonus design and replay evidence (or clearly mark as optional/not run).

Include your own words for every checkpoint. Do not submit the reference PDF,
secrets, generated caches, or screenshots from a run you did not perform.

## 9. Final checklist

- [ ] `python -m pytest -q` is green.
- [ ] Notebook JSON loads.
- [ ] Git remote is correct.
- [ ] A3 red and green Actions URLs captured.
- [ ] Snowflake B1-B5 evidence captured or marked not run.
- [ ] Mage UI evidence captured or marked not run.
- [ ] RabbitMQ ACK and NACK lines captured or marked not run.
- [ ] D1 and B4 predictions were written before running.
- [ ] Report within 8 pages and explanations are student-owned.
- [ ] No credentials, PDF, CSV, pickle, logs, or lakehouse output committed.
- [ ] Final `git status` shows only intended files.
