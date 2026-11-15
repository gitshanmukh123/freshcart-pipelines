# FreshCart Pipelines - From Git to Gold

A reproducible course project covering Git/GitHub Actions, a Snowflake
Bronze-to-Gold ELT pipeline, a Mage Iris pipeline, a RabbitMQ topic exchange with
driver consumers, and an optional RabbitMQ-to-lakehouse bonus.

> The FreshCart and Mage notebooks are **reconstructions** from the assignment
> PDF, not recovered classroom originals. Read `ASSUMPTIONS.md` before submitting.

## Repository map

```text
freshcart-pipelines/
├── .github/workflows/ci.yml          # Python 3.12 + pytest CI
├── elt/
│   ├── freshcart_data.py             # reconstructed 8-row fixture + CRM/FX
│   ├── freshcart_lib.py              # Snowflake SQL, helpers, local checks
│   └── freshcart_elt.ipynb           # runnable Colab/Snowflake notebook
├── iris_project/                     # Mage project
│   ├── data_loaders/load_iris.py
│   ├── transformers/prepare_data.py
│   ├── transformers/validate_data.py
│   ├── transformers/train_model.py
│   ├── transformers/evaluate_model.py
│   ├── data_exporters/save_results.py
│   └── pipelines/iris_classifier/metadata.yaml
├── stream/
│   ├── common.py                     # topic matching + broker helpers
│   ├── dispatcher.py                 # Rapido event producer
│   ├── driver.py                     # ACK/NACK consumer
│   ├── order_producer.py             # bonus FreshCart producer
│   └── lakehouse_consumer.py         # bonus persist-before-ACK consumer
├── tests/                            # 15 local tests
├── tools/build_freshcart_notebook.py
├── requirements.txt                  # CI/local test dependencies
├── requirements-colab.txt
├── requirements-mage.txt
├── ASSUMPTIONS.md
├── EXECUTION_GUIDE.md
└── README.md
```

## Quick start

```powershell
cd "C:\Users\saish\Music\data eng project\freshcart-pipelines"
python -m pip install -r requirements.txt
python -m pytest -q
```

Expected local result: `15 passed`.

Open `elt/freshcart_elt.ipynb` in Colab/Jupyter and follow the cells. The
notebook requests Snowflake credentials with `getpass`; do not paste credentials
into notebook cells.

## Assignment coverage

| Part | What exists | What still needs live evidence |
|---|---|---|
| A1-A2 | Isolated repo plan, `.gitignore`, CI, commit guidance | Real commit hashes and remote URL output |
| A3 | Exact 120/30 pytest test and 0.2/0.3 red-green procedure | Red failure log, green CI run URL |
| B1 | 8-row fixture, CLEAN validation, expected 6 valid / 2 quarantine | Snowflake run output |
| B2 | Dedup (4 rows), quarantine MERGE, duplicate check | Snowflake run output |
| B3 | `unsupported_currency` final CLEAN definition | `ORD-1006` two-reason output |
| B4 | SCD2 CRM history and Gold MERGE | Baseline 126, B4 146, no-change repeat |
| B5 | Five baseline checks plus future-date probe | Six zero-check output |
| C1-C4 | Mage blocks, metadata, CI test, fallback experiment | Mage UI diagrams/screenshots |
| D1-D3 | Dispatcher, six drivers, topic matching tests, NACK path | Real ACK/NACK logs |
| D4 | Bonus producer/consumer, local dedup table, optional Snowflake load | Batch and replay counts |
| E | Report checklist in `EXECUTION_GUIDE.md` | Student-written report |

## Key commands

### Tests and CI

```powershell
python -m pytest -q
git status
git remote -v
git log --oneline --decorate -10
```

The CI workflow runs the same `pytest` command on every push and pull request.

### Snowflake / Colab

1. Upload or clone the repository into Colab.
2. Install `requirements-colab.txt`.
3. Run `elt/freshcart_elt.ipynb` from top to bottom.
4. Enter the Snowflake account, user, and password through `getpass`.

The notebook creates database `FRESHCART`, schemas `RAW`, `CLEAN`,
`QUARANTINE`, `REF`, `CRM`, and `GOLD`, then runs B1-B5.

### Mage

```powershell
python -m pip install -r requirements-mage.txt
mage start iris_project
```

Open the Mage UI, run the Iris pipeline, and capture the diagram and runs for
C1-C4. The exact local fallback numbers in the notebook are not Mage evidence.

### RabbitMQ

Set the broker URL without committing it:

```powershell
$env:RABBITMQ_URL = "amqps://USER:PASSWORD@HOST/VHOST"
python stream/driver.py --name Control --pattern "bangalore.#" --duration 20
python stream/dispatcher.py --count 30 --interval 0.05 --fault-mode
```

Run each driver in its own terminal. A valid message logs `ACK`; a fault-mode
message with missing JSON `zone` logs `NACK ... requeue=False`.

### Bonus

```powershell
python stream/lakehouse_consumer.py --max-messages 8
python stream/order_producer.py --interval 0.05
python stream/lakehouse_consumer.py --replay stream/lakehouse/landing/<batch>.ndjson
```

Add `--snowflake` to load `RAW.ORDER_EVENTS_RAW` and `GOLD.ORDER_EVENTS`.

## Status and evidence rules

- Code and tests are committed.
- Do not claim Snowflake, Mage UI, RabbitMQ, or GitHub Actions outputs until they
  have actually run.
- Do not paste screenshots from a different run or fabricate commit hashes.
- Keep B4/D1 predictions and all report explanations student-owned.
- Never commit `.env`, the broker URL, Snowflake passwords, API keys, the reference
  PDF, generated CSV/pickle files, logs, or lakehouse output.

See `ASSUMPTIONS.md` for reconstruction details and `EXECUTION_GUIDE.md` for the
end-to-end evidence workflow.
