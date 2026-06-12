"""
Lightweight session store for the messaging layer.

Holds two small pieces of per-user state:
  1. The user's currently selected vertical (so they don't re-pick it every turn).
  2. A short-lived dedupe key per inbound message id (channels retry webhooks).

Backed by Redis when MESSAGING_REDIS_URL is set; otherwise an in-process dict with
TTL semantics good enough for a single replica and for tests.
"""

from __future__ import annotations

import time

from .config import settings


class SessionStore:
    """Async key/value store with TTL. Redis-backed or in-memory."""

    def __init__(self, redis_url: str = "") -> None:
        self._redis_url = redis_url or settings.redis_url
        self._redis = None
        self._mem: dict[str, tuple[str, float]] = {}  # key -> (value, expires_at)

    async def _client(self):
        if not self._redis_url:
            return None
        if self._redis is None:
            import redis.asyncio as aioredis  # imported lazily so dev needs no redis
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def get(self, key: str) -> str | None:
        client = await self._client()
        if client is not None:
            return await client.get(key)
        value = self._mem.get(key)
        if value is None:
            return None
        text, expires = value
        if expires and expires < time.time():
            self._mem.pop(key, None)
            return None
        return text

    async def set(self, key: str, value: str, ttl_seconds: int = 0) -> None:
        client = await self._client()
        if client is not None:
            await client.set(key, value, ex=ttl_seconds or None)
            return
        expires = time.time() + ttl_seconds if ttl_seconds else 0.0
        self._mem[key] = (value, expires)

    # ── Domain helpers ────────────────────────────────────────────────────────

    async def get_vertical(self, channel: str, user_id: str) -> str | None:
        return await self.get(f"vertical:{channel}:{user_id}")

    async def set_vertical(self, channel: str, user_id: str, vertical: str) -> None:
        # 24h — long enough to persist a shopping session, short enough to reset.
        await self.set(f"vertical:{channel}:{user_id}", vertical, ttl_seconds=86_400)

    async def seen_message(self, channel: str, message_id: str) -> bool:
        """Return True if this message id was already processed (dedupe)."""
        if not message_id:
            return False
        key = f"seen:{channel}:{message_id}"
        if await self.get(key) is not None:
            return True
        await self.set(key, "1", ttl_seconds=600)
        return False

    async def aclose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()


store = SessionStore()
