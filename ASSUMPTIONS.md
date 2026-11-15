# Assumptions and Reconstruction Notes

The original FreshCart classroom notebook and the instructor Mage Iris notebook
were not available in the workspace. This repository is a **reconstruction**
driven by the assignment PDF. It is not a recovered copy of either notebook.
Every reconstructed value below must be disclosed in the report.

## FreshCart fixture

| Item | Assumption |
|---|---|
| Raw rows | 8: six website rows `ORD-1001`..`ORD-1006`, plus mobile updates for `ORD-1002` and `ORD-1003` |
| Valid rows | 6 |
| Quarantine rows | 2: `ORD-1004` and `ORD-1006` |
| Deduplicated orders | 4: `ORD-1001`, `ORD-1002`, `ORD-1003`, `ORD-1005` |
| Gold orders | 4 |
| Gold amount | INR `7785.00` |
| Gold points, baseline | `126` |
| Rejection rate | `2 / 8 = 25%` |
| `ORD-1003` | Website row has `amount = NULL`; later mobile row has INR `2100.00` and a later `updated_at` |
| `ORD-1004` | Quantity `0`, amount `100.00`; quarantine reason `invalid_quantity` |
| `ORD-1006` | Quantity `0`, currency `EUR`; before B3 reasons `["invalid_quantity"]`, after B3 `["invalid_quantity","unsupported_currency"]` |
| Currency support | INR and USD only; EUR is unsupported |
| FX rate | USD `83.00` INR per USD; INR `1.00` |
| Tier multiplier | Bronze `1.0`, Silver `1.5`, Gold `2.0` |
| Points formula | `FLOOR(amount_inr * multiplier / 100)` |

## CRM and B4

- Initial CRM events: CUST-01 Priya Silver `2026-08-01`, CUST-02 Arjun Bronze
  `2026-08-01`, CUST-03 Meera Gold `2026-08-01`, CUST-04 Rahul Bronze
  `2026-08-01`, CUST-01 Priya Gold `2026-08-10`.
- B4 adds `EVT-006`, CUST-02 Arjun, `arjun.k@yahoo.in`, Gold,
  `effective_from = 2026-08-15`.
- After B4: `ORD-1002` becomes Gold, earns 39 points, total points become 146.
- First B4 run changes exactly one Gold row. Repeating the same event changes
  zero Gold rows, keeps Gold at 4 rows, and keeps totals at INR 7785 / 146.
- CRM history after B4 has 6 rows: Priya has two versions, Arjun has two
  versions, Meera and Rahul have one each. Priya Silver and Arjun Bronze are
  closed at their next tier's effective date.
- B4's SCD2 definition treats a repeated same-tier event as no new version.

## Validation and deduplication

- Required validation reasons: `missing_order_id`, `missing_customer`,
  `invalid_quantity`, `invalid_amount`, `missing_order_date`, and after B3
  `unsupported_currency`.
- A NULL `amount` is allowed at validation time; `ORD-1003`'s mobile row supplies
  the amount. Amount `<= 0` is invalid when the value is present.
- Deduplication keeps the row with the latest `updated_at`, then latest
  `_loaded_at`, then latest `_source_file`.
- Quarantine is keyed by `(order_id, row_hash)`. A reason-only change updates the
  existing row, so `ORD-1006` remains a single quarantine row after B3.
- Gold is MERGE-keyed by `order_id`. `row_hash` changes only when business values
  change; a no-change refresh does not rewrite `published_at`.
- Bronze is append-only. There are no UPDATE or DELETE statements against RAW;
  B5 inserts and deletes only the temporary row in `CLEAN.ORDERS_DEDUP`.

## Data-quality checks

The baseline five checks are:

1. Duplicate `order_id` values in `CLEAN.ORDERS_DEDUP`.
2. Gold rows with NULL `amount_inr` while original amount is not NULL.
3. Gold rows with negative points.
4. Dedup rows without a covering SCD2 tier version.
5. Dedup rows without an FX rate.

The sixth B5 check is future `order_date` in `CLEAN.ORDERS_DEDUP`. The probe row
is `ORD-FUTURE-TEST` with `2099-01-01`; it is inserted, detected, and deleted.

## Mage Iris

- Dataset: sklearn Iris, 150 rows, 3 classes.
- Split: stratified 80/20, `random_state=42`, literal `test_size=0.2`.
- Model: `DecisionTreeClassifier`, `random_state=42`, default `max_depth=3`.
- Accuracy gate: `0.90`, checked by `train_model`'s Mage test.
- C2 experiments: `max_depth` values 1, 2, 3, 5, and `None`.
- The Mage runtime was not installed in this workspace. Local fallback calls are
  reproducible, but they are not evidence of a Mage UI run.

## RabbitMQ

- Exchange: durable topic exchange `rapido-dispatch`.
- Routing key: `city.zone.type`.
- Bangalore zones: `koramangala`, `indiranagar`, `whitefield`, `jayanagar`.
- Chennai zones: `tnagar`, `adyar`, `velachery`.
- Types: `ride`, `food`.
- Driver bindings are in `stream/common.py`.
- Fault mode omits the JSON `zone` field every 10th message but keeps a valid
  routing key, so the driver receives the message and must NACK it.
- NACK uses `requeue=False`; malformed JSON is also NACKed.
- Bonus producer uses `freshcart.order.<channel>` on the same exchange.
- The lakehouse consumer writes and `fsync`s NDJSON before ACK. Replaying a batch
  is idempotent on `event_id` at the local table and Snowflake layers.

## Environment and security

- Local Python: 3.12.3. CI uses Python 3.12.
- Snowflake credentials and RabbitMQ URLs must come from environment variables or
  `getpass`; they must never be committed.
- The RabbitMQ reference notebook found under Downloads contains plaintext
  broker and API credentials. It was not reused. Rotate those credentials if that
  notebook is shared or submitted.
- The assignment PDF, generated CSV/pickle files, logs, and lakehouse output are
  excluded from Git.
- The parent home directory is an existing Git repository. The submission uses
  an isolated repository at `freshcart-pipelines`.

## Evidence status

| Evidence | Status |
|---|---|
| Repository source, tests, SQL, scripts, notebook JSON | Implemented locally |
| Local pytest suite | Last run: 15 passed |
| GitHub Actions | Initial, A3 red, and A3 green runs recorded in `EVIDENCE.md` |
| Snowflake notebook execution | Pending user credentials |
| Mage UI runs and C2 screenshots | Pending Mage installation |
| RabbitMQ ACK/NACK logs | Pending live broker |
| Bonus replay evidence | Pending live broker / optional Snowflake |
| Report and student checkpoints | Student-owned; blank scaffolds provided |
