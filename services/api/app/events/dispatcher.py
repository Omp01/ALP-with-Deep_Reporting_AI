"""
Background delivery of committed events to the stream.

Runs for the life of the API process. Each pass publishes the events whose outbox rows are
due (see store.dispatch_pending); a stream outage only postpones delivery, and each failure
is recorded on the outbox row so it can be inspected.
"""

import asyncio
import json
import logging

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.events import event_publisher
from app.events.store import dispatch_pending

logger = logging.getLogger("api.events")


async def run_dispatcher() -> None:
    while True:
        try:
            result = await dispatch_pending(AsyncSessionLocal, event_publisher)
            if result.published or result.failed:
                logger.info(json.dumps({"event": "event_dispatch", "published": result.published, "failed": result.failed}))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("event dispatch pass failed")
        await asyncio.sleep(settings.event_dispatch_interval_seconds)
