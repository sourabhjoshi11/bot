import redis.asyncio as redis
import time

class RateLimiter:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.MAX_REQUESTS = 5
        self.WINDOW = 60

    async def is_allowed(self, user_id: int) -> tuple[bool, int]:
        key = f"rate:{user_id}"
        now = int(time.time())
        window_start = now - self.WINDOW

        # BUG 4 FIX: Pipeline commands pe await nahi lagta
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, self.WINDOW)
        results = await pipe.execute()

        count = results[2]
        if count > self.MAX_REQUESTS:
            oldest = await self.redis.zrange(key, 0, 0, withscores=True)
            wait = int(oldest[0][1]) + self.WINDOW - now if oldest else self.WINDOW
            return False, wait
        return True, 0
