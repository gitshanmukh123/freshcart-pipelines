"""Shared RabbitMQ topic helpers used by dispatchers, drivers and bonus consumers."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

EXCHANGE = "rapido-dispatch"
EVENT_TYPE = "topic"

CITIES = {
    "bangalore": ["koramangala", "indiranagar", "whitefield", "jayanagar"],
    "chennai": ["tnagar", "adyar", "velachery"],
}
SERVICE_TYPES = ["ride", "food"]

DRIVER_BINDINGS = {
    "Ravi": "bangalore.koramangala.*",
    "Priya": "bangalore.indiranagar.*",
    "Arjun": "bangalore.*.ride",
    "Meena": "bangalore.*.food",
    "Karthik": "chennai.tnagar.food",
    "Control": "bangalore.#",
}


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def topic_matches(pattern: str, routing_key: str) -> bool:
    """Match MQTT-style topic patterns, including '*' and '#'."""
    pattern_parts = pattern.split(".")
    key_parts = routing_key.split(".")

    @lru_cache(maxsize=None)
    def match(pattern_index: int, key_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return key_index == len(key_parts)
        token = pattern_parts[pattern_index]
        if token == "#":
            return match(pattern_index + 1, key_index) or (
                key_index < len(key_parts) and match(pattern_index, key_index + 1)
            )
        if key_index == len(key_parts):
            return False
        if token == "*" or token == key_parts[key_index]:
            return match(pattern_index + 1, key_index + 1)
        return False

    return match(0, 0)


def routing_key(city: str, zone: str, service_type: str) -> str:
    return f"{city}.{zone}.{service_type}"


def build_ride_message(
    city: str,
    zone: str,
    service_type: str,
    sequence: int,
    omit_zone: bool = False,
) -> dict[str, Any]:
    message = {
        "id": f"MSG-{sequence:06d}",
        "city": city,
        "zone": zone,
        "type": service_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        "sequence": sequence,
    }
    if omit_zone:
        message.pop("zone")
    return message


def encode_message(message: dict[str, Any]) -> bytes:
    return json.dumps(message, separators=(",", ":")).encode("utf-8")


def decode_message(body: bytes) -> dict[str, Any]:
    value = json.loads(body.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Message body must be a JSON object")
    return value


def rabbitmq_url(explicit: str | None = None) -> str:
    return explicit or os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")


def connection_parameters(url: str):
    try:
        import pika
    except ImportError as exc:
        raise RuntimeError("Install pika before running RabbitMQ scripts") from exc
    return pika.URLParameters(url)


def open_connection(url: str):
    try:
        import pika
    except ImportError as exc:
        raise RuntimeError("Install pika before running RabbitMQ scripts") from exc
    connection = pika.BlockingConnection(connection_parameters(url))
    channel = connection.channel()
    channel.exchange_declare(
        exchange=EXCHANGE,
        exchange_type=EVENT_TYPE,
        durable=True,
    )
    return connection, channel


def declare_bound_queue(channel, queue: str, pattern: str) -> None:
    channel.queue_declare(queue=queue, durable=True, exclusive=False, auto_delete=False)
    channel.queue_bind(exchange=EXCHANGE, queue=queue, routing_key=pattern)


def publish_json(channel, routing_key_value: str, message: dict[str, Any]) -> None:
    try:
        import pika
    except ImportError as exc:
        raise RuntimeError("Install pika before running RabbitMQ scripts") from exc
    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key=routing_key_value,
        body=encode_message(message),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
        ),
    )
