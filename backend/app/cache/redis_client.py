from __future__ import annotations

import json
import time
from dataclasses import dataclass

from backend.app.config import Settings


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    retry_after: int | None = None


class RedisCache:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._memory: dict[str, tuple[float, str]] = {}
        self._redis = None

    async def connect(self) -> None:
        try:
            from redis.asyncio import from_url
        except ImportError:
            return
        self._redis = from_url(self.settings.REDIS_URL, decode_responses=True)

    async def get_json(self, key: str):
        if self._redis:
            value = await self._redis.get(key)
        else:
            expires, value = self._memory.get(key, (0, ""))
            if expires and expires < time.time():
                self._memory.pop(key, None)
                value = ""
        return json.loads(value) if value else None

    async def set_json(self, key: str, value, ttl: int) -> None:
        serialized = json.dumps(value, default=str)
        if self._redis:
            await self._redis.set(key, serialized, ex=ttl)
        else:
            self._memory[key] = (time.time() + ttl, serialized)

    async def delete(self, key: str) -> None:
        if self._redis:
            await self._redis.delete(key)
        else:
            self._memory.pop(key, None)


class RateLimiter:
    def __init__(self, settings: Settings, cache: RedisCache):
        self.settings = settings
        self.cache = cache
        self._memory: dict[str, list[float]] = {}

    async def check_and_increment(self, client_id: str, tier: str = "anon") -> RateLimitResult:
        limit = self.settings.RATE_LIMIT_AUTH if tier == "auth" else self.settings.RATE_LIMIT_ANON
        window = self.settings.RATE_LIMIT_WINDOW
        key = f"rate:{client_id}"
        now = time.time()

        if self.cache._redis:
            redis = self.cache._redis
            await redis.zremrangebyscore(key, 0, now - window)
            count = await redis.zcard(key)
            if count >= limit:
                oldest = await redis.zrange(key, 0, 0, withscores=True)
                retry_after = int(max(1, window - (now - oldest[0][1]))) if oldest else window
                return RateLimitResult(False, 0, limit, retry_after)
            await redis.zadd(key, {str(now): now})
            await redis.expire(key, window)
            return RateLimitResult(True, max(0, limit - count - 1), limit)

        timestamps = [stamp for stamp in self._memory.get(key, []) if stamp > now - window]
        if len(timestamps) >= limit:
            retry_after = int(max(1, window - (now - timestamps[0])))
            self._memory[key] = timestamps
            return RateLimitResult(False, 0, limit, retry_after)
        timestamps.append(now)
        self._memory[key] = timestamps
        return RateLimitResult(True, limit - len(timestamps), limit)

