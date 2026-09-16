"""
Event Worker — Consumes learning events from Redis Streams and triggers
competency updates and adaptive evaluations in the Adaptive Engine.
"""
import asyncio
import json
import logging
import os
import signal
import sys
from typing import Dict, Any

import httpx
import redis.asyncio as aioredis
from shared.events.types import COMPETENCY_EVENTS, ADAPTIVE_TRIGGER_EVENTS

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("event-worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STREAM_NAME = os.getenv("EVENT_STREAM_NAME", "learning_events")
CONSUMER_GROUP = os.getenv("EVENT_CONSUMER_GROUP", "event_workers")
CONSUMER_NAME = os.getenv("HOSTNAME", "event-worker-1")
ADAPTIVE_ENGINE_URL = os.getenv("ADAPTIVE_ENGINE_URL", "http://adaptive-engine:8001")

shutdown_event = asyncio.Event()


def handle_signal(sig, frame):
    logger.info(f'{{"event": "shutdown_signal", "service": "event-worker", "signal": "{sig}"}}')
    shutdown_event.set()


async def process_event(client: httpx.AsyncClient, event_data: Dict[str, Any]) -> bool:
    """
    Process a single learning event from the Redis stream.
    Forward competency/adaptive trigger events to Adaptive Engine.
    """
    event_type = event_data.get("event_type")
    event_id = event_data.get("event_id")

    # Deserialize any json fields if needed
    payload = event_data.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            pass

    logger.info(
        f'{{"event": "event_received", "service": "event-worker", '
        f'"event_id": "{event_id}", "event_type": "{event_type}"}}'
    )

    if event_type in [e.value for e in ADAPTIVE_TRIGGER_EVENTS] or event_type in [e.value for e in COMPETENCY_EVENTS]:
        try:
            resp = await client.post(
                f"{ADAPTIVE_ENGINE_URL}/api/v1/adaptive/events",
                json={
                    "event_id": event_id,
                    "org_id": event_data.get("org_id"),
                    "user_id": event_data.get("user_id"),
                    "event_type": event_type,
                    "session_id": event_data.get("session_id"),
                    "course_id": event_data.get("course_id"),
                    "module_id": event_data.get("module_id"),
                    "timestamp": event_data.get("timestamp"),
                    "payload": payload,
                },
                timeout=5.0,
            )
            logger.info(
                f'{{"event": "adaptive_forwarded", "service": "event-worker", '
                f'"event_id": "{event_id}", "status": {resp.status_code}}}'
            )
        except Exception as e:
            logger.warning(
                f'{{"event": "adaptive_forward_failed", "service": "event-worker", '
                f'"event_id": "{event_id}", "error": "{str(e)}"}}'
            )

    return True


async def main():
    """Main event loop for consuming from Redis Streams."""
    logger.info(
        f'{{"event": "startup", "service": "event-worker", '
        f'"stream": "{STREAM_NAME}", "group": "{CONSUMER_GROUP}", '
        f'"consumer": "{CONSUMER_NAME}", "redis": "{REDIS_URL}"}}'
    )

    redis_client = None
    while not shutdown_event.is_set():
        try:
            redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
            # Create consumer group if it does not exist
            try:
                await redis_client.xgroup_create(STREAM_NAME, CONSUMER_GROUP, id="0", mkstream=True)
                logger.info(f'{{"event": "group_created", "group": "{CONSUMER_GROUP}", "stream": "{STREAM_NAME}"}}')
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    logger.debug(f"Consumer group notice: {e}")
            break
        except Exception as conn_err:
            logger.warning(f'{{"event": "redis_connect_retry", "error": "{conn_err}"}}')
            await asyncio.sleep(2)

    if not redis_client:
        logger.error('{"event": "redis_connect_failed", "message": "Failed to connect to Redis"}')
        return

    async with httpx.AsyncClient() as http_client:
        while not shutdown_event.is_set():
            try:
                # Read new messages from stream for this consumer group
                entries = await redis_client.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_NAME: ">"},
                    count=10,
                    block=1500,
                )

                if not entries:
                    continue

                for stream, messages in entries:
                    for message_id, raw_fields in messages:
                        try:
                            await process_event(http_client, raw_fields)
                            # Acknowledge the message once processed
                            await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                        except Exception as proc_err:
                            logger.error(
                                f'{{"event": "process_error", "message_id": "{message_id}", "error": "{proc_err}"}}'
                            )
            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                if not shutdown_event.is_set():
                    logger.warning(f'{{"event": "stream_read_warning", "error": "{loop_err}"}}')
                    await asyncio.sleep(1)

    if redis_client:
        await redis_client.aclose()
    logger.info('{"event": "shutdown", "service": "event-worker", "message": "Event worker stopped"}')


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    asyncio.run(main())
