"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
Không có secret nào được hard-code; AGENT_API_KEY rỗng nghĩa là chưa cấu hình
(khi đó mọi request /ask đều bị từ chối 401).
"""
import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    port: int = field(default_factory=lambda: _int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    rate_limit_per_minute: int = field(default_factory=lambda: _int("RATE_LIMIT_PER_MINUTE", 10))
    daily_budget_usd: float = field(default_factory=lambda: _float("DAILY_BUDGET_USD", 1.0))
    monthly_budget_usd: float = field(default_factory=lambda: _float("MONTHLY_BUDGET_USD", 10.0))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())


settings = Settings()
