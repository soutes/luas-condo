"""
Tests for OpenTelemetry Instrumentation, Correlated Tracing, and LGPD Sanitization.
No emojis used.
"""

import os
import re
import sys
from pathlib import Path
import pytest
from opentelemetry.trace import StatusCode
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from starlette.testclient import TestClient

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.telemetry import (
    get_tracer,
    get_current_trace_id,
    trace_step,
    sanitize_text,
    sanitize_log_data,
    get_prometheus_metrics,
    condo_submissions_total,
    condo_reimbursement_amount_brl,
    condo_processing_duration_seconds,
    condo_cycle_sla_days_remaining,
)
from app.main import app


HEX_TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture(autouse=True)
def setup_span_exporter():
    """Configure an in-memory span exporter for testing trace captures."""
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = get_tracer("test-telemetry", provider=tracer_provider)
    yield exporter, tracer_provider
    exporter.clear()


def test_get_tracer():
    tracer = get_tracer("test-tracer")
    assert tracer is not None


def test_get_current_trace_id_format():
    # Outside active span, should generate a 32-char hex trace ID
    trace_id = get_current_trace_id()
    assert len(trace_id) == 32
    assert HEX_TRACE_ID_PATTERN.match(trace_id) is not None


def test_trace_step_creates_span_and_propagates_trace_id(setup_span_exporter):
    exporter, provider = setup_span_exporter

    with trace_step("test_step_root", attributes={"step": "ingestion"}, tracer_provider=provider) as root_span:
        root_trace_id = get_current_trace_id()
        assert len(root_trace_id) == 32
        assert HEX_TRACE_ID_PATTERN.match(root_trace_id) is not None

        # Nested span must propagate identical trace_id
        with trace_step("test_step_child", attributes={"step": "parsing"}, tracer_provider=provider) as child_span:
            child_trace_id = get_current_trace_id()
            assert child_trace_id == root_trace_id

    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    names = [s.name for s in spans]
    assert "test_step_child" in names
    assert "test_step_root" in names

    # Verify both spans share the same trace ID
    trace_ids = {f"{s.context.trace_id:032x}" for s in spans}
    assert len(trace_ids) == 1
    assert root_trace_id in trace_ids


def test_trace_step_records_exception_and_error_status(setup_span_exporter):
    exporter, provider = setup_span_exporter

    with pytest.raises(ValueError, match="Simulated parsing failure"):
        with trace_step("faulty_step", tracer_provider=provider):
            raise ValueError("Simulated parsing failure")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    failed_span = spans[0]
    assert failed_span.status.status_code == StatusCode.ERROR
    assert "Simulated parsing failure" in failed_span.status.description

    # Verify exception event recorded
    events = [e.name for e in failed_span.events]
    assert "exception" in events


def test_trace_step_sanitizes_pii_attributes(setup_span_exporter):
    exporter, provider = setup_span_exporter

    attributes = {
        "tenant_cpf": "123.456.789-01",
        "user_password": "supersecretpassword123",
        "api_token": "token-xyz-abc",
        "valid_key": "ordinary_value",
    }

    with trace_step("sanitized_step", attributes=attributes, tracer_provider=provider) as span:
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span_attrs = spans[0].attributes

    # Sensitive values must be redacted in span attributes
    assert span_attrs.get("tenant_cpf") == "[REDACTED_CPF]"
    assert span_attrs.get("user_password") == "[REDACTED_SECRET]"
    assert span_attrs.get("api_token") == "[REDACTED_SECRET]"
    assert span_attrs.get("valid_key") == "ordinary_value"


def test_sanitize_text():
    # Test CPF redaction
    raw_cpf_text = "Processando boleto do CPF 123.456.789-00 referente a taxa de condominio."
    sanitized_cpf = sanitize_text(raw_cpf_text)
    assert "123.456.789-00" not in sanitized_cpf
    assert "[REDACTED_CPF]" in sanitized_cpf

    # Test sensitive key-value pairs redaction
    raw_secret_text = "Autenticando email com password=minhasenha123 e email_pass: pass456"
    sanitized_secret = sanitize_text(raw_secret_text)
    assert "minhasenha123" not in sanitized_secret
    assert "pass456" not in sanitized_secret
    assert "[REDACTED_SECRET]" in sanitized_secret

    # Test Bearer token, chave_pix, and CPF together in text
    raw_pix_bearer = "Chave PIX chave_pix=minhachavepix para locatario CPF 123.456.789-00 com Bearer eyJhbGciOiJIUz"
    sanitized_pix_bearer = sanitize_text(raw_pix_bearer)
    assert "minhachavepix" not in sanitized_pix_bearer
    assert "eyJhbGciOiJIUz" not in sanitized_pix_bearer
    assert "123.456.789-00" not in sanitized_pix_bearer
    assert "[REDACTED_SECRET]" in sanitized_pix_bearer
    assert "[REDACTED_CPF]" in sanitized_pix_bearer


def test_sanitize_log_data():
    raw_data = {
        "condominio": "Residencial Solar dos Ventos",
        "cpf": "999.888.777-66",
        "password": "unmasked_secret_password",
        "auth": {
            "email_pass": "smtp_secret_pass",
            "token": "bearer-token-123",
            "secret": "top-secret-val",
            "chave_pix": "pix-key-999",
        },
        "items": [
            {"description": "Taxa ordinaria", "amount": 500.0},
            {"description": "Boleto CPF 111.222.333-44", "amount": 25.0},
        ],
    }

    sanitized = sanitize_log_data(raw_data)

    assert sanitized["condominio"] == "Residencial Solar dos Ventos"
    assert sanitized["cpf"] == "[REDACTED_CPF]"
    assert sanitized["password"] == "[REDACTED_SECRET]"
    assert sanitized["auth"]["email_pass"] == "[REDACTED_SECRET]"
    assert sanitized["auth"]["token"] == "[REDACTED_SECRET]"
    assert sanitized["auth"]["secret"] == "[REDACTED_SECRET]"
    assert sanitized["auth"]["chave_pix"] == "[REDACTED_SECRET]"

    # Verify list items
    assert sanitized["items"][0]["description"] == "Taxa ordinaria"
    assert "111.222.333-44" not in sanitized["items"][1]["description"]
    assert "[REDACTED_CPF]" in sanitized["items"][1]["description"]


def test_prometheus_metrics_collection_and_exposition():
    # Increment counter
    condo_submissions_total.labels(status="SUCESSO", target="mock-bitrix").inc()
    condo_submissions_total.labels(status="ERRO", target="mock-bitrix").inc(2)

    # Observe histograms
    condo_reimbursement_amount_brl.observe(389.50)
    condo_processing_duration_seconds.observe(4.75)

    # Set gauge
    condo_cycle_sla_days_remaining.set(6)

    metrics_text = get_prometheus_metrics()
    assert isinstance(metrics_text, str)
    assert "condo_submissions_total" in metrics_text
    assert 'status="SUCESSO"' in metrics_text
    assert 'target="mock-bitrix"' in metrics_text
    assert "condo_reimbursement_amount_brl" in metrics_text
    assert "condo_processing_duration_seconds" in metrics_text
    assert "condo_cycle_sla_days_remaining" in metrics_text


def test_fastapi_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert data.get("service") == "luas-condo"
    assert "trace_id" in data
    assert HEX_TRACE_ID_PATTERN.match(data["trace_id"]) is not None
    assert "x-trace-id" in response.headers


def test_fastapi_metrics_endpoint():
    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "condo_submissions_total" in response.text


def test_fastapi_trace_id_header_propagation():
    client = TestClient(app)
    custom_trace_id = "0123456789abcdef0123456789abcdef"
    response = client.get("/api/health", headers={"x-trace-id": custom_trace_id})

    assert response.status_code == 200
    assert response.headers.get("x-trace-id") == custom_trace_id
    assert response.json().get("trace_id") == custom_trace_id
