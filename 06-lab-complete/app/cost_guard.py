"""
Cost guard (tiêu chí 8).
Cộng dồn chi phí LLM vào Redis theo ngày và theo tháng; vượt budget → 402.
"""
import time

import redis
from fastapi import HTTPException

from app import redis_client
from app.config import settings

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _keys() -> tuple[str, str]:
    return "cost:day:" + time.strftime("%Y-%m-%d"), "cost:month:" + time.strftime("%Y-%m")


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → 402. Redis lỗi → 503."""
    if redis_client.r is None:
        raise HTTPException(status_code=503, detail="Cost guard unavailable.")
    day_key, month_key = _keys()
    try:
        day_spent, month_spent = redis_client.r.mget(day_key, month_key)
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Cost guard unavailable.")
    if float(day_spent or 0) >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded.")
    if float(month_spent or 0) >= settings.monthly_budget_usd:
        raise HTTPException(status_code=402, detail="Monthly budget exceeded.")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    if redis_client.r is None:
        return cost
    day_key, month_key = _keys()
    try:
        pipe = redis_client.r.pipeline()
        pipe.incrbyfloat(day_key, cost)
        pipe.expire(day_key, 2 * 86400)
        pipe.incrbyfloat(month_key, cost)
        pipe.expire(month_key, 32 * 86400)
        pipe.execute()
    except redis.RedisError:
        pass  # request đã phục vụ xong; check_budget lần sau sẽ báo nếu Redis còn lỗi
    return cost
