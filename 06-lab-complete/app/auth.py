"""
API Key authentication (tiêu chí 6).
Header X-API-Key phải trùng AGENT_API_KEY; thiếu hoặc sai → 401.
"""
import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """Dependency cho /ask. Trả về key hợp lệ (dùng làm định danh cho rate limit)."""
    expected = settings.agent_api_key
    if not api_key or not expected or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
