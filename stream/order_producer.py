"""Bonus: publish FreshCart order events on freshcart.order.<channel>."""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "elt"))

from freshcart_data import MOCK_ORDERS

from common import configure_logging, open_connection, publish_json, rabbitmq_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None, help="RabbitMQ URL; defaults to RABBITMQ_URL")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--count", type=int, default=0, help="Messages; 0 means all fixture rows")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat the fixture batch N times")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    connection, channel = open_connection(rabbitmq_url(args.url))
    total = args.count or len(MOCK_ORDERS) * max(args.repeat, 1)
    sent = 0
    try:
        while sent < total:
            for order in MOCK_ORDERS:
                if sent >= total:
                    break
                sent += 1
                event = {
                    **order,
                    "event_id": f"EVT-{uuid.uuid4().hex}",
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
                channel_name = order["channel"]
                key = f"freshcart.order.{channel_name}"
                publish_json(channel, key, event)
                print(
                    f"PUBLISH seq={sent} routing_key={key} order_id={order['order_id']}",
                    flush=True,
                )
                if args.interval:
                    time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Order producer interrupted", flush=True)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
