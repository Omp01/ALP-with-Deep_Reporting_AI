"""
Redis Stream Publisher for Learning Events.
Publishes events asynchronously using XADD for event-driven workers.
"""

import json
from typing import Dict, Any, Optional
import redis.asyncio as aioredis
from app.core.config import settings


class EventPublisher:
    """Publishes telemetry learning events to Redis Streams."""

    def __init__(self):
        self.stream_name = settings.event_stream_name
        self._redis: Optional[aioredis.Redis] = None

    async def get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def publish_event(self, event_data: Dict[str, Any]) -> str:
        """
        Appends event to Redis Stream using XADD.
        Returns: stream message ID (e.g. '1726450000000-0')
        """
        r = await self.get_redis()
        # Redis Stream values must be strings or bytes
        serialized = {k: json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v) for k, v in event_data.items() if v is not None}
        message_id = await r.xadd(self.stream_name, serialized)
        return str(message_id)

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


event_publisher = EventPublisher()
