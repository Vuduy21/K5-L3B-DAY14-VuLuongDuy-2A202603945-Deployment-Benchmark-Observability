"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Client được tạo lazy (from_url không mở kết nối), nên app vẫn khởi động được
khi Redis chưa sẵn sàng.
"""
import redis

from app.config import settings

r = (
    redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=2,
    )
    if settings.redis_url
    else None
)


def redis_healthy() -> bool:
    """Dùng cho GET /ready: không kết nối được → False."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False
