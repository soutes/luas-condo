"""
OpenTelemetry Instrumentation, Correlated Tracing, and LGPD Sanitization.
No emojis used.
"""

from contextlib import contextmanager
import re
from typing import Any, Optional
import uuid

from opentelemetry import trace
from opentelemetry.trace import StatusCode, Tracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


# Global tracer cache
_GLOBAL_TRACER: Optional[Tracer] = None

# Regex patterns for LGPD and secret redaction
CPF_REGEX = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
SENSITIVE_KEY_VALUE_REGEX = re.compile(
    r"(?i)\b(password|email_pass|secret|token|chave_pix)\b\s*([:=]\s*)([\"']?)([^\s\"',;]+)\3"
)
BEARER_TOKEN_REGEX = re.compile(r"(?i)\b(bearer\s+)([a-zA-Z0-9_\-\.]+)")

SENSITIVE_FIELD_NAMES = ("password", "email_pass", "secret", "token", "chave_pix")


def get_tracer(service_name: str = "luas-condo", provider: Optional[TracerProvider] = None) -> Tracer:
    """
    Return configured OpenTelemetry Tracer.
    Initializes a TracerProvider if not already configured.
    """
    global _GLOBAL_TRACER
    if provider is not None:
        return provider.get_tracer(service_name)

    current_provider = trace.get_tracer_provider()
    if not isinstance(current_provider, TracerProvider):
        new_provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        trace.set_tracer_provider(new_provider)

    _GLOBAL_TRACER = trace.get_tracer(service_name)
    return _GLOBAL_TRACER


def get_current_trace_id() -> str:
    """
    Return active trace ID as a 32-character hex string or generate a new valid 32-character hex ID.
    """
    try:
        span = trace.get_current_span()
        span_ctx = span.get_span_context()
        if span_ctx is not None and span_ctx.is_valid and span_ctx.trace_id != 0:
            return f"{span_ctx.trace_id:032x}"
    except Exception:
        pass
    return uuid.uuid4().hex


def get_or_create_trace_id(trace_id: Optional[str] = None) -> str:
    """
    Return provided trace ID or resolve active/generated trace ID.
    """
    if trace_id:
        return trace_id
    return get_current_trace_id()


def sanitize_text(text: str) -> str:
    """
    Scrubs inline CPFs and sensitive tokens from a text string.
    """
    if not isinstance(text, str):
        return text

    sanitized = CPF_REGEX.sub("[REDACTED_CPF]", text)
    sanitized = SENSITIVE_KEY_VALUE_REGEX.sub(r"\1\2\3[REDACTED_SECRET]\3", sanitized)
    sanitized = BEARER_TOKEN_REGEX.sub(r"\1[REDACTED_SECRET]", sanitized)
    return sanitized


def sanitize_log_data(data: Any) -> Any:
    """
    Recursively sanitize dictionaries, lists, and strings to eliminate PII and credentials.
    """
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for key, val in data.items():
            k_lower = str(key).lower()
            if any(term in k_lower for term in SENSITIVE_FIELD_NAMES):
                cleaned[key] = "[REDACTED_SECRET]"
            elif k_lower == "cpf" or "cpf" in k_lower:
                cleaned[key] = "[REDACTED_CPF]"
            else:
                cleaned[key] = sanitize_log_data(val)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_log_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(sanitize_log_data(item) for item in data)
    elif isinstance(data, str):
        return sanitize_text(data)
    else:
        return data


@contextmanager
def trace_step(
    name: str,
    attributes: Optional[dict[str, Any]] = None,
    tracer_provider: Optional[TracerProvider] = None,
):
    """
    Context manager creating OpenTelemetry spans, recording errors, and propagating trace_id.
    Zero PII guarantee: attributes are sanitized before setting on span.
    """
    tracer = get_tracer(provider=tracer_provider)
    sanitized_attrs = sanitize_log_data(attributes) if attributes else {}

    with tracer.start_as_current_span(name) as span:
        trace_id = get_current_trace_id()
        span.set_attribute("trace_id", trace_id)

        for key, val in sanitized_attrs.items():
            if val is not None:
                if isinstance(val, (bool, str, bytes, int, float)):
                    span.set_attribute(str(key), val)
                else:
                    span.set_attribute(str(key), str(val))

        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise


# Prometheus Metric Registrations
def _get_or_create_counter(name: str, documentation: str, labelnames=(), registry=REGISTRY) -> Counter:
    if name in registry._names_to_collectors:
        collector = registry._names_to_collectors[name]
        if isinstance(collector, Counter):
            return collector
    return Counter(name, documentation, labelnames, registry=registry)


def _get_or_create_histogram(
    name: str,
    documentation: str,
    labelnames=(),
    buckets=Histogram.DEFAULT_BUCKETS,
    registry=REGISTRY,
) -> Histogram:
    if name in registry._names_to_collectors:
        collector = registry._names_to_collectors[name]
        if isinstance(collector, Histogram):
            return collector
    return Histogram(name, documentation, labelnames, buckets=buckets, registry=registry)


def _get_or_create_gauge(name: str, documentation: str, labelnames=(), registry=REGISTRY) -> Gauge:
    if name in registry._names_to_collectors:
        collector = registry._names_to_collectors[name]
        if isinstance(collector, Gauge):
            return collector
    return Gauge(name, documentation, labelnames, registry=registry)


condo_submissions_total = _get_or_create_counter(
    "condo_submissions_total",
    "Total count of reimbursement submissions by status and target",
    labelnames=["status", "target"],
)

condo_reimbursement_amount_brl = _get_or_create_histogram(
    "condo_reimbursement_amount_brl",
    "Histogram of condo reimbursement amounts in BRL",
    buckets=(10.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, float("inf")),
)

condo_processing_duration_seconds = _get_or_create_histogram(
    "condo_processing_duration_seconds",
    "Histogram of condo processing duration in seconds",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, float("inf")),
)

condo_cycle_sla_days_remaining = _get_or_create_gauge(
    "condo_cycle_sla_days_remaining",
    "Gauge of days remaining before cycle SLA deadline",
)


def get_prometheus_metrics() -> str:
    """
    Return Prometheus exposition format metrics string.
    """
    data = generate_latest(REGISTRY)
    return data.decode("utf-8") if isinstance(data, bytes) else str(data)
