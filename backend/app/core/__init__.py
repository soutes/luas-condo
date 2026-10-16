"""
Core application configuration, database session management, and telemetry.
No emojis used.
"""

from app.core.database import Base, SessionLocal, engine, get_db, init_db
from app.core.telemetry import (
    condo_cycle_sla_days_remaining,
    condo_processing_duration_seconds,
    condo_reimbursement_amount_brl,
    condo_submissions_total,
    get_current_trace_id,
    get_or_create_trace_id,
    get_prometheus_metrics,
    get_tracer,
    sanitize_log_data,
    sanitize_text,
    trace_step,
)

__all__ = [
    "Base",
    "SessionLocal",
    "condo_cycle_sla_days_remaining",
    "condo_processing_duration_seconds",
    "condo_reimbursement_amount_brl",
    "condo_submissions_total",
    "engine",
    "get_current_trace_id",
    "get_db",
    "get_or_create_trace_id",
    "get_prometheus_metrics",
    "get_tracer",
    "init_db",
    "sanitize_log_data",
    "sanitize_text",
    "trace_step",
]
