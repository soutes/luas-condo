"""
Main FastAPI Application Entrypoint.
Exposes endpoints for health checks, Prometheus metrics, and OpenTelemetry instrumentation.
No emojis used.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.core.database import init_db
from app.core.telemetry import (
    get_current_trace_id,
    get_prometheus_metrics,
    trace_step,
)
from app.routes.alert_webhook import router as alert_router
from app.routes.ciclos import router as ciclos_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler ensuring database schema initialization and background poller."""
    try:
        init_db()
    except Exception:
        pass

    from app.services.poller import start_poller, stop_poller
    start_poller()
    try:
        yield
    finally:
        stop_poller()


app = FastAPI(
    title="Luas Condo Service",
    description="Condo Audit and Reimbursement Backend Automation Service",
    version="1.0.0",
    lifespan=lifespan,
)

# OpenTelemetry FastAPI automatic instrumentation
FastAPIInstrumentor.instrument_app(app)

# Include API routers
app.include_router(alert_router)
app.include_router(ciclos_router)



@app.middleware("http")
async def trace_correlation_middleware(request: Request, call_next):
    """
    HTTP middleware extracting or propagating trace correlation header x-trace-id.
    """
    incoming_trace_id = request.headers.get("x-trace-id")
    attributes = {
        "http.method": request.method,
        "http.path": request.url.path,
    }
    if incoming_trace_id:
        attributes["inbound_trace_id"] = incoming_trace_id

    with trace_step(f"{request.method} {request.url.path}", attributes=attributes):
        active_trace_id = incoming_trace_id if incoming_trace_id else get_current_trace_id()
        response: Response = await call_next(request)
        response.headers["x-trace-id"] = active_trace_id
        return response


@app.get("/api/health")
async def health_check(request: Request):
    """
    Service health check endpoint returning status and correlated trace ID.
    """
    trace_id = request.headers.get("x-trace-id") or get_current_trace_id()
    return {
        "status": "ok",
        "service": "luas-condo",
        "trace_id": trace_id,
    }


@app.get("/metrics")
async def metrics_endpoint():
    """
    Prometheus scraping endpoint exposing operational metrics.
    """
    return Response(
        content=get_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/")
async def root():
    """
    Root informative endpoint.
    """
    return {
        "service": "luas-condo",
        "status": "running",
        "endpoints": {
            "health": "/api/health",
            "metrics": "/metrics",
            "docs": "/docs",
        },
    }
