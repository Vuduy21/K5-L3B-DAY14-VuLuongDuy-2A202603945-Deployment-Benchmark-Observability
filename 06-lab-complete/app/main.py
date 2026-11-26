"""
Production AI Agent — Part 6 Final Project
Chạy: uvicorn app.main:app --workers 2
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import redis_client
from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from utils.mock_llm import ask as llm_ask


# ── Structured logging: mỗi dòng là 1 JSON object ──
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "lvl": record.levelname,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        return json.dumps(entry, ensure_ascii=False)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
logger = logging.getLogger("agent")
logger.handlers = [_handler]
logger.setLevel(settings.log_level)
logger.propagate = False


def log(event: str, level: int = logging.INFO, **fields):
    logger.log(level, event, extra={"fields": fields})


@asynccontextmanager
async def lifespan(app: FastAPI):
    log("startup", environment=settings.environment, redis_configured=bool(settings.redis_url))
    yield
    # Uvicorn nhận SIGTERM → ngừng nhận kết nối mới, chờ request đang chạy xong rồi mới vào đây.
    if redis_client.r is not None:
        try:
            redis_client.r.close()
        except Exception:
            pass
    log("shutdown")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=100)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log("request", path=request.url.path, method=request.method,
        status=response.status_code, ms=round((time.perf_counter() - start) * 1000, 1))
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    # Ghi chi tiết vào log, trả về client thông báo chung (không lộ stack trace)
    log("unhandled_error", logging.ERROR, path=request.url.path, error=type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health")
def health():
    """Liveness: luôn 200 khi process còn chạy, kể cả khi Redis chưa sẵn sàng."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: 503 khi Redis không kết nối được."""
    if not redis_client.redis_healthy():
        return JSONResponse(status_code=503, content={"status": "not ready", "redis": "down"})
    return {"status": "ready"}


def _tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    cost = record_cost(_tokens(body.question), _tokens(answer))
    log("ask", user_id=body.user_id, cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
