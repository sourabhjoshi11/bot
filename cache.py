import redis.asyncio as redis
import json
import hashlib

class CacheManager:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
        self.TTL = 3600

    def _key(self, url: str) -> str:
        return f"terabox:{hashlib.md5(url.encode()).hexdigest()}"

    async def get(self, url: str) -> dict | None:
        data = await self.redis.get(self._key(url))
        return json.loads(data) if data else None

    async def set(self, url: str, info: dict):
        await self.redis.setex(self._key(url), self.TTL, json.dumps(info))

    async def close(self):
        await self.redis.aclose()
