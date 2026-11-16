# Assumptions and Reference Notes

The FreshCart fixture and SQL follow the classroom workbook under `references/`.
The submitted notebook is a sanitized copy: classroom outputs and credentials
were removed. The Mage block code follows the classroom Iris pipeline.

## FreshCart fixture

| Item | Reference value |
|---|---|
| Raw rows | 8: six web rows `ORD-1001`..`ORD-1006`, plus mobile updates for `ORD-1002` and `ORD-1003` |
| Valid rows | 6 |
| Quarantine rows | 2: `ORD-1004` and `ORD-1006` |
| Deduplicated orders | 4: `ORD-1001`, `ORD-1002`, `ORD-1003`, `ORD-1005` |
| Gold amount | INR `7785.00` |
| Gold points, baseline | `126` |
| Rejection rate | `2 / 8 = 25%` |
| `ORD-1003` | Web amount is NULL; mobile amount INR `2100.00` and later `updated_at` wins |
| `ORD-1004` | Amount `-500`; reason `non_positive_amount` |
| `ORD-1006` | Currency `EUR`, bad email and bad pincode; baseline reasons `["bad_email","bad_pincode"]` |
| B3 reason | Adds `unsupported_currency` to `ORD-1006`; row count stays 2 |
| FX | `2026-09-01: 83.20`, `2026-09-02: 83.35`, `2026-09-03: 83.10` |
| Tier multipliers | Silver `1`, Gold `2`, Platinum `3` |
| Points formula | `FLOOR(amount_inr / 100) * multiplier` |

Baseline points: `ORD-1001=12` (Silver), `ORD-1002=35` (Silver),
`ORD-1003=63` (Platinum), `ORD-1005=16` (Gold).

## CRM and B4

- Initial CRM events: CUST-01 Silver `2023-04-10`, CUST-01 Gold `2026-09-03`,
  CUST-02 Silver `2024-01-15`, CUST-03 Platinum `2022-11-01`.
- B4 appends CUST-02 Arjun Gold with `effective_from = 2026-08-15`.
- B4 result: CUST-02 has 2 SCD2 rows, ORD-1002 uses Gold, earns `70` points,
  total Gold points become `161`, and exactly 1 Gold row's `published_at`
  changes.
- Repeating the same B4 run changes 0 Gold rows and keeps totals at
  INR `7785.00` / `161`.
- SCD2 deduplicates repeated same-tier/same-effective-date events.

## Validation and deduplication

- Validation reasons include `missing_order_id`, `bad_email`, `bad_pincode`,
  `unparseable_date`, `unparseable_updated_at`, `non_positive_amount`, and after
  B3 `unsupported_currency`.
- A NULL amount is allowed at validation time; the mobile row supplies it for
  `ORD-1003`. Amount `<= 0` is rejected when present.
- Deduplication keeps the latest `updated_at`, then latest `ingest_seq`.
- Quarantine uses `NOT EXISTS` plus `QUALIFY` so a reason-only change updates the
  logical row instead of creating a duplicate.
- Gold is MERGE-keyed by `order_id`; `row_hash` covers business values.
- Bronze is append-only, so each run adds 8 order rows plus CRM/FX rows.

## Data-quality checks

The baseline five checks are:

1. Rows gained or lost while enriching.
2. Duplicate `order_id` values in Gold.
3. Orders with no customer match.
4. Amounts without an FX rate.
5. Orders with no city.

The sixth B5 check is future `order_date` in `silver.orders_dedup`. Probe row
`ORD-FUTURE-TEST` dated `2099-01-01` is inserted, detected, and deleted.

## Mage Iris

- Dataset: sklearn Iris, 150 rows, 3 classes.
- Split: 80/20, `random_state=42`, no stratify, literal `test_size=0.2`.
- Model: `DecisionTreeClassifier(max_depth=3, random_state=42)`.
- Accuracy gate: `0.8`.
- C2 experiments: `max_depth` values 1, 2, 3, 4 and 5.
- Observed local fallback accuracies are not substitutes for Mage run evidence.

## RabbitMQ

- Exchange: durable topic exchange `rapido-dispatch`.
- Routing key: `city.zone.type`.
- Message shape: `{"id","city","zone","type","ts"}`.
- Drivers: Ravi, Priya, Arjun, Meena, Karthik, Control.
- Fault mode omits the JSON `zone` field every 10th message but keeps a valid
  routing key, so the driver receives and NACKs it.
- NACK uses `requeue=False`; a crashing consumer leaves an unacked message
  eligible for redelivery.
- Bonus producer uses `freshcart.order.<channel>` and the consumer writes and
  fsyncs NDJSON before ACK. Replay deduplicates on `event_id`.

## Environment and security

- Local Python: 3.12.3. CI uses Python 3.12.
- Snowflake authentication uses Google SSO with
  `authenticator="externalbrowser"` and values from `.env`.
- `SNOWFLAKE_DATABASE` selects the target database. Use a fresh isolated
  `FRESHCART_DE_LAB` locally; the setup SQL creates and switches to that name.
- `.env`, generated CSV/pickle files, logs, lakehouse output and references are
  excluded from Git.
- The classroom RabbitMQ notebook contains plaintext credentials and was not
  reused.

## Evidence status

| Evidence | Status |
|---|---|
| Repository source, tests, SQL, scripts, notebook JSON | Implemented locally |
| Local pytest suite | 18 passed |
| GitHub Actions | Initial, A3 red and A3 green runs recorded in `EVIDENCE.md` |
| Snowflake notebook execution | In progress with Google SSO |
| Mage UI runs and C2 screenshots | Pending Mage installation |
| RabbitMQ ACK/NACK logs | Pending live run |
| Bonus replay evidence | Pending live run |
| Report and student checkpoints | Student-owned |
