"""Bonus: persist FreshCart order events before ACK, then load a deduplicated table."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "elt"))

from common import (
    configure_logging,
    decode_message,
    declare_bound_queue,
    open_connection,
    rabbitmq_url,
)

SNOWFLAKE_SETUP = """
CREATE DATABASE IF NOT EXISTS FRESHCART;
CREATE SCHEMA IF NOT EXISTS FRESHCART.RAW;
CREATE SCHEMA IF NOT EXISTS FRESHCART.GOLD;
CREATE FILE FORMAT IF NOT EXISTS FRESHCART.RAW.JSON_FF
  TYPE = JSON
  STRIP_OUTER_ARRAY = FALSE;
CREATE STAGE IF NOT EXISTS FRESHCART.RAW.ORDER_EVENTS_STAGE
  FILE_FORMAT = (FORMAT_NAME = FRESHCART.RAW.JSON_FF);
CREATE TABLE IF NOT EXISTS FRESHCART.RAW.ORDER_EVENTS_RAW (
  event_id STRING,
  payload VARIANT,
  event_hash STRING,
  _source_file STRING,
  _loaded_at TIMESTAMP_NTZ
);
CREATE TABLE IF NOT EXISTS FRESHCART.GOLD.ORDER_EVENTS (
  event_id STRING,
  order_id STRING,
  channel STRING,
  amount NUMBER(12, 2),
  currency STRING,
  order_date STRING,
  event_hash STRING,
  loaded_at TIMESTAMP_NTZ
);
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None, help="RabbitMQ URL; defaults to RABBITMQ_URL")
    parser.add_argument("--name", default="Control")
    parser.add_argument("--pattern", default="freshcart.order.#")
    parser.add_argument("--queue", default="rapido.freshcart.lakehouse")
    parser.add_argument("--prefetch", type=int, default=10)
    parser.add_argument("--max-messages", type=int, default=0)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--landing-dir", default=str(ROOT / "stream" / "lakehouse" / "landing"))
    parser.add_argument("--lakehouse-dir", default=str(ROOT / "stream" / "lakehouse" / "table"))
    parser.add_argument("--replay", default=None, help="Replay an existing NDJSON batch file")
    parser.add_argument("--snowflake", action="store_true", help="Also load the batch into Snowflake")
    return parser.parse_args()


def read_ndjson(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_ndjson_atomic(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def load_batch(batch_file: Path, lakehouse_dir: Path, replay: bool = False) -> tuple[int, int]:
    table_file = lakehouse_dir / "order_events.jsonl"
    existing = {}
    if table_file.exists():
        for row in read_ndjson(table_file):
            existing[row["event_id"]] = row
    before = len(existing)

    batch_rows = read_ndjson(batch_file)
    for row in batch_rows:
        event_id = row.get("event_id")
        if not event_id:
            raise ValueError(f"Event without event_id in {batch_file}")
        existing[event_id] = row

    write_ndjson_atomic(table_file, sorted(existing.values(), key=lambda row: row["event_id"]))
    lakehouse_dir.mkdir(parents=True, exist_ok=True)
    with (lakehouse_dir / "batches.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                {
                    "batch_file": str(batch_file),
                    "rows": len(batch_rows),
                    "table_rows": len(existing),
                    "replay": replay,
                    "loaded_at": datetime.now(timezone.utc).isoformat(),
                },
                separators=(",", ":"),
            )
            + "\n"
        )
    return before, len(existing)


def load_batch_to_snowflake(batch_file: Path) -> tuple[int, int]:
    from freshcart_lib import connect_snowflake, execute_statements, scalar

    connection = connect_snowflake()
    try:
        execute_statements(connection, SNOWFLAKE_SETUP)
        file_path = str(batch_file.resolve()).replace("\\", "/")
        execute_statements(
            connection,
            f"PUT 'file://{file_path}' FRESHCART.RAW.ORDER_EVENTS_STAGE "
            "AUTO_COMPRESS=FALSE OVERWRITE=TRUE;",
        )
        filename = batch_file.name
        execute_statements(
            connection,
            f"""
            COPY INTO FRESHCART.RAW.ORDER_EVENTS_RAW (
              event_id, payload, event_hash, _source_file, _loaded_at
            )
            FROM (
              SELECT
                $1:event_id::STRING,
                $1,
                SHA2(TO_VARCHAR($1), 256),
                METADATA$FILENAME::STRING,
                CURRENT_TIMESTAMP()
              FROM @FRESHCART.RAW.ORDER_EVENTS_STAGE/{filename}
            )
            FILE_FORMAT = (FORMAT_NAME = FRESHCART.RAW.JSON_FF)
            ON_ERROR = 'ABORT_STATEMENT'
            FORCE = TRUE;
            """,
        )
        execute_statements(
            connection,
            """
            MERGE INTO FRESHCART.GOLD.ORDER_EVENTS t
            USING (
              SELECT
                event_id,
                payload:order_id::STRING AS order_id,
                payload:channel::STRING AS channel,
                TRY_TO_NUMBER(payload:amount::STRING, 12, 2) AS amount,
                payload:currency::STRING AS currency,
                payload:order_date::STRING AS order_date,
                event_hash
              FROM FRESHCART.RAW.ORDER_EVENTS_RAW
              QUALIFY ROW_NUMBER() OVER (
                PARTITION BY event_id ORDER BY _loaded_at DESC
              ) = 1
            ) s
            ON t.event_id = s.event_id
            WHEN MATCHED AND t.event_hash <> s.event_hash THEN UPDATE SET
              t.order_id = s.order_id,
              t.channel = s.channel,
              t.amount = s.amount,
              t.currency = s.currency,
              t.order_date = s.order_date,
              t.event_hash = s.event_hash,
              t.loaded_at = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (
              event_id, order_id, channel, amount, currency,
              order_date, event_hash, loaded_at
            ) VALUES (
              s.event_id, s.order_id, s.channel, s.amount, s.currency,
              s.order_date, s.event_hash, CURRENT_TIMESTAMP()
            );
            """,
        )
        raw_count = int(scalar(connection, "SELECT COUNT(*) FROM FRESHCART.RAW.ORDER_EVENTS_RAW") or 0)
        gold_count = int(scalar(connection, "SELECT COUNT(*) FROM FRESHCART.GOLD.ORDER_EVENTS") or 0)
        return raw_count, gold_count
    finally:
        connection.close()


def replay_batch(args: argparse.Namespace) -> None:
    batch_file = Path(args.replay)
    if not batch_file.exists():
        raise FileNotFoundError(batch_file)
    before, after = load_batch(batch_file, Path(args.lakehouse_dir), replay=True)
    print(f"REPLAY file={batch_file.name} table_rows_before={before} table_rows_after={after}")
    if args.snowflake:
        raw_count, gold_count = load_batch_to_snowflake(batch_file)
        print(f"SNOWFLAKE raw_rows={raw_count} gold_rows={gold_count}")


def consume(args: argparse.Namespace) -> None:
    landing_dir = Path(args.landing_dir)
    landing_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    batch_file = landing_dir / f"freshcart_orders_{stamp}.ndjson"

    connection, channel = open_connection(rabbitmq_url(args.url))
    declare_bound_queue(channel, args.queue, args.pattern)
    channel.basic_qos(prefetch_count=args.prefetch)
    started = time.monotonic()
    count = 0

    try:
        with batch_file.open("w", encoding="utf-8", newline="\n") as handle:
            for method, properties, body in channel.consume(args.queue, inactivity_timeout=1.0):
                if args.duration and time.monotonic() - started >= args.duration:
                    break
                if method is None:
                    continue
                try:
                    event = decode_message(body)
                    if not event.get("event_id") or not event.get("order_id"):
                        raise ValueError("event_id and order_id are required")
                except (ValueError, UnicodeDecodeError) as exc:
                    channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    print(f"NACK reason=invalid_event error={exc}", flush=True)
                    continue

                handle.write(json.dumps(event, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                channel.basic_ack(delivery_tag=method.delivery_tag)
                count += 1
                print(
                    f"ACK persisted event_id={event['event_id']} "
                    f"order_id={event['order_id']} channel={event.get('channel')}",
                    flush=True,
                )
                if args.max_messages and count >= args.max_messages:
                    break
    except KeyboardInterrupt:
        print("Lakehouse consumer interrupted", flush=True)
    finally:
        channel.cancel()
        connection.close()

    if count:
        before, after = load_batch(batch_file, Path(args.lakehouse_dir))
        print(
            f"LOAD batch={batch_file.name} messages={count} "
            f"table_rows_before={before} table_rows_after={after}"
        )
        if args.snowflake:
            raw_count, gold_count = load_batch_to_snowflake(batch_file)
            print(f"SNOWFLAKE raw_rows={raw_count} gold_rows={gold_count}")
    else:
        batch_file.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    configure_logging()
    if args.replay:
        replay_batch(args)
    else:
        consume(args)


if __name__ == "__main__":
    main()
