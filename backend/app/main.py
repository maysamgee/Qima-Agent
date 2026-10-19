import json
import logging
import time
from collections import defaultdict, deque
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.routes import router
from app.auth import authorize, reader
from app.config import get_settings
from app.database import get_engine, session_factory
from app.models import AuditEvent, Candidate, ScoringResult, SearchJob
from app.observability import correlation_id

settings = get_settings()
app = FastAPI(
    title="Qima Coffee — Discovery & Outreach",
    version="0.1.0",
    docs_url="/docs" if settings.app_env != "prod" else None,
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
logger = logging.getLogger("qima.api")
logging.basicConfig(level=logging.INFO, format="%(message)s")
limits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def controls(request: Request, call_next):
    started = time.monotonic()
    correlation = str(uuid4())
    correlation_id.set(correlation)
    request.state.correlation_id = correlation
    host = request.client.host if request.client else "unknown"
    recent = limits[host]
    while recent and recent[0] < started - 60:
        recent.popleft()
    if request.method != "GET" and len(recent) >= 90:
        return JSONResponse(
            {"detail": "Too many requests; retry shortly"}, status_code=429, headers={"Retry-After": "60"}
        )
    if request.method != "GET":
        recent.append(started)
    if len(limits) > 10000:
        for key in list(limits):
            if not limits[key] or limits[key][-1] < started - 60:
                limits.pop(key, None)
    length = request.headers.get("content-length", "0")
    if not length.isdigit() or int(length) > 11 * 1024 * 1024:
        return JSONResponse({"detail": "Request exceeds size limit"}, status_code=413)
    response = await call_next(request)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "X-Correlation-ID": correlation,
        }
    )
    if settings.app_env == "prod":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logger.info(
        json.dumps(
            {
                "event": "http.request",
                "correlation_id": correlation,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round((time.monotonic() - started) * 1000),
            }
        )
    )
    return response


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(
        {"detail": "Conflicting or repeated change. Refresh and retry using the same idempotency key."},
        status_code=409,
    )


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse(
        {"detail": "The provider or request returned invalid structured data."}, status_code=422
    )


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1 FROM alembic_version"))
        return {"status": "ready"}
    except Exception:
        raise HTTPException(503, "Database unavailable or migrations not applied") from None


@app.get("/health/dependencies")
def dependencies(actor=Depends(reader)):
    return {
        "database": ready()["status"],
        "ai": settings.ai_provider,
        "search": settings.search_provider,
        "queue": settings.queue_provider,
        "storage": settings.storage_provider,
        "email": "mock",
        "instagram": "manual",
        "aws_live_check": "Not probed; configured adapter status only",
    }


@app.get("/metrics")
def metrics(actor=Depends(reader)):
    authorize(actor, admin=True)
    with session_factory()() as db:
        status_counts = db.execute(select(SearchJob.status, func.count()).group_by(SearchJob.status)).all()
        events = db.execute(select(AuditEvent.action, func.count()).group_by(AuditEvent.action)).all()
        lines = [f'qima_jobs{{status="{status}"}} {count}' for status, count in status_counts]
        lines += [f'qima_events_total{{action="{action}"}} {count}' for action, count in events]
        lines += [
            f"qima_candidates_total {db.scalar(select(func.count(Candidate.id)))}",
            f"qima_average_historical_score {db.scalar(select(func.avg(ScoringResult.total))) or 0}",
        ]
    return Response("\n".join(lines) + "\n", media_type="text/plain")


app.include_router(router)
