"""Publish simulated Rapido ride and food events to the topic exchange."""

from __future__ import annotations

import argparse
import random
import time

from common import (
    CITIES,
    SERVICE_TYPES,
    build_ride_message,
    configure_logging,
    open_connection,
    publish_json,
    rabbitmq_url,
    routing_key,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None, help="RabbitMQ URL; defaults to RABBITMQ_URL")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between messages")
    parser.add_argument("--count", type=int, default=20, help="Messages to publish; 0 means unlimited")
    parser.add_argument("--duration", type=float, default=0.0, help="Optional wall-clock limit in seconds")
    parser.add_argument("--fault-mode", action="store_true", help="Omit zone JSON every 10th message")
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    rng = random.Random(args.seed)
    connection, channel = open_connection(rabbitmq_url(args.url))
    started = time.monotonic()
    sequence = 0

    try:
        while True:
            if args.duration and time.monotonic() - started >= args.duration:
                break
            if args.count and sequence >= args.count:
                break
            sequence += 1
            city = rng.choice(list(CITIES))
            zone = rng.choice(CITIES[city])
            service_type = rng.choice(SERVICE_TYPES)
            omit_zone = args.fault_mode and sequence % 10 == 0
            message = build_ride_message(city, zone, service_type, sequence, omit_zone)
            key = routing_key(city, zone, service_type)
            publish_json(channel, key, message)
            print(
                f"PUBLISH seq={sequence} routing_key={key} "
                f"json_zone={'MISSING' if omit_zone else zone}",
                flush=True,
            )
            if args.interval:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Dispatcher interrupted", flush=True)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
