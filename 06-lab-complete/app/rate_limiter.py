"""
Rate limiting (tiêu chí 7) — sliding window 60 giây trên Redis sorted set.
State nằm trong Redis nên mọi worker/instance dùng chung và còn nguyên sau restart.
"""
import hashlib
import math
import time
import uuid

import redis
from fastapi import HTTPException

from app import redis_client
from app.config import settings

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Vượt RATE_LIMIT_PER_MINUTE trong 60s → 429 + Retry-After. Redis lỗi → 503."""
    if redis_client.r is None:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable.")

    # Không đặt API key thô vào tên key Redis
    rkey = "rl:" + hashlib.sha256(key.encode()).hexdigest()[:32]
    now = time.time()
    try:
        pipe = redis_client.r.pipeline()
        pipe.zremrangebyscore(rkey, 0, now - WINDOW_SECONDS)
        pipe.zcard(rkey)
        _, count = pipe.execute()

        if count >= settings.rate_limit_per_minute:
            oldest = redis_client.r.zrange(rkey, 0, 0, withscores=True)
            wait = WINDOW_SECONDS - (now - oldest[0][1]) if oldest else WINDOW_SECONDS
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} requests/minute.",
                headers={"Retry-After": str(max(1, math.ceil(wait)))},
            )

        pipe = redis_client.r.pipeline()
        pipe.zadd(rkey, {f"{now}:{uuid.uuid4().hex[:8]}": now})
        pipe.expire(rkey, WINDOW_SECONDS + 5)
        pipe.execute()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable.")
