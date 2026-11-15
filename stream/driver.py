"""Consume one driver's routing pattern and ACK or NACK each event."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from common import (
    configure_logging,
    decode_message,
    declare_bound_queue,
    open_connection,
    rabbitmq_url,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Driver name, for example Ravi")
    parser.add_argument("--pattern", required=True, help="Binding pattern, for example bangalore.koramangala.*")
    parser.add_argument("--url", default=None, help="RabbitMQ URL; defaults to RABBITMQ_URL")
    parser.add_argument("--queue", default=None, help="Queue name; defaults to rapido.<name>")
    parser.add_argument("--prefetch", type=int, default=1)
    parser.add_argument("--max-messages", type=int, default=0, help="Stop after N deliveries; 0 means unlimited")
    parser.add_argument("--duration", type=float, default=0.0, help="Optional wall-clock limit in seconds")
    return parser.parse_args()


def safe_queue_name(name: str) -> str:
    return "rapido." + "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")


def process_delivery(channel, method, properties, body, name: str, counter: int) -> None:
    try:
        message = decode_message(body)
    except (ValueError, UnicodeDecodeError) as exc:
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        print(f"NACK {name} seq={counter} reason=malformed_json error={exc}", flush=True)
        return

    if str(message.get("zone") or "").strip():
        channel.basic_ack(delivery_tag=method.delivery_tag)
        print(
            f"ACK  {name} seq={counter} key={message.get('city')}."
            f"{message.get('zone')}.{message.get('type')} id={message.get('message_id')}",
            flush=True,
        )
    else:
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        print(
            f"NACK {name} seq={counter} reason=missing_zone id={message.get('message_id')}",
            flush=True,
        )


def main() -> None:
    args = parse_args()
    configure_logging()
    connection, channel = open_connection(rabbitmq_url(args.url))
    queue = args.queue or safe_queue_name(args.name)
    declare_bound_queue(channel, queue, args.pattern)
    channel.basic_qos(prefetch_count=args.prefetch)

    started = time.monotonic()
    count = 0
    print(
        f"LISTEN {args.name} queue={queue} pattern={args.pattern} "
        f"at={datetime.now(timezone.utc).isoformat()}",
        flush=True,
    )

    try:
        for method, properties, body in channel.consume(queue, inactivity_timeout=1.0):
            if args.duration and time.monotonic() - started >= args.duration:
                break
            if method is None:
                continue
            count += 1
            process_delivery(channel, method, properties, body, args.name, count)
            connection.process_data_events(time_limit=0)
            if args.max_messages and count >= args.max_messages:
                break
    except KeyboardInterrupt:
        print(f"Driver {args.name} interrupted", flush=True)
    finally:
        channel.cancel()
        connection.close()
        print(f"TOTAL {args.name} delivered={count}", flush=True)


if __name__ == "__main__":
    main()
