"""
Tests for user impact alerting and autonomous on-call responder agent.
Covers Alertmanager rules, self-healing remediation (selector drift repair,
HTTP 5xx retry dead-letter queue replay, unrecoverable escalation), and webhook API.
Follows TDD methodology.
No emojis used.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import sys
import uuid
import yaml
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

backend_dir = Path(__file__).resolve().parent.parent
root_dir = backend_dir.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import Base, get_db
from app.models.entities import (
    CicloCondominio,
    IncidenteOnCall,
    StatusCiclo,
    StatusIncidente,
    StatusSubmissao,
    SubmissaoRessarcimento,
)
from app.agents.on_call import (
    handle_incident_alert,
    remediate_selector_mismatch,
    remediate_http_5xx_timeout,
    set_default_http_client,
)
from app.main import app
from mock_bitrix.main import app as mock_bitrix_app


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database session using StaticPool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def mock_bitrix_client():
    """In-memory TestClient targeting mock_bitrix app."""
    return TestClient(mock_bitrix_app)


@pytest.fixture
def client_app(db_session: Session, mock_bitrix_client):
    """FastAPI TestClient with overridden get_db dependency and injected test transport."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    set_default_http_client(mock_bitrix_client)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    set_default_http_client(None)



# ---------------------------------------------------------------------------
# 1. Prometheus Alert Rules Validation
# ---------------------------------------------------------------------------

def test_alert_rules_yaml_structure_and_metrics():
    """Validate monitoring/alert_rules.yml structure, rules and user-impact metrics."""
    rules_path = root_dir / "monitoring" / "alert_rules.yml"
    assert rules_path.exists(), f"Alert rules file not found at {rules_path}"

    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "groups" in data, "Prometheus alert rules must contain groups list"
    groups = data["groups"]
    assert len(groups) > 0

    all_rules = {}
    for group in groups:
        for rule in group.get("rules", []):
            if "alert" in rule:
                all_rules[rule["alert"]] = rule

    # 1. CondoSubmissionFailed rule
    assert "CondoSubmissionFailed" in all_rules, "CondoSubmissionFailed rule must be defined"
    sub_rule = all_rules["CondoSubmissionFailed"]
    assert "condo_submissions_total" in sub_rule["expr"]
    assert 'status="failed"' in sub_rule["expr"] or "failed" in sub_rule["expr"]
    assert sub_rule["labels"].get("severity") == "critical"

    # 2. CondoSlaBreachWarning rule
    assert "CondoSlaBreachWarning" in all_rules, "CondoSlaBreachWarning rule must be defined"
    sla_rule = all_rules["CondoSlaBreachWarning"]
    assert "condo_cycle_sla_days_remaining" in sla_rule["expr"]
    assert "< 3" in sla_rule["expr"]
    assert sla_rule["labels"].get("severity") == "warning"


# ---------------------------------------------------------------------------
# 2. On-Call Agent Self-Healing: Selector Mismatch
# ---------------------------------------------------------------------------

def test_on_call_agent_fixes_selector_mismatch(db_session: Session, mock_bitrix_client):
    """
    On-Call agent detects SELECTOR_MISMATCH, applies dynamic selector repair,
    re-submits successfully, updates SubmissaoRessarcimento to SUCESSO, and marks incident RESOLVIDO.
    """
    trace_id = uuid.uuid4().hex
    ciclo = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/tmp/mock_boleto.pdf",
        comprovante_pix_path="/tmp/mock_pix.pdf",
        status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
    )
    db_session.add(ciclo)
    db_session.flush()

    submissao = SubmissaoRessarcimento(
        ciclo_id=ciclo.id,
        contrato_numero="09638.003.03",
        payload_enviado={
            "nome": "Luiz Augusto Soutes",
            "email": "luiz@example.com",
            "telefone": "55 48 99999-9999",
            "contrato": "09638.003.03",
            "observacoes": "Taxa condominial ordinaria e fundo reserva",
        },
        status=StatusSubmissao.ERRO,
        protocolo_retorno=None,
        tentativas=1,
        trace_id=trace_id,
        enviado_em=datetime.now(timezone.utc),
    )
    db_session.add(submissao)
    db_session.commit()

    alert_payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "CondoSubmissionFailed",
                    "severity": "critical",
                },
                "annotations": {
                    "trace_id": trace_id,
                    "error_type": "SELECTOR_MISMATCH",
                    "description": "Field contrato could not be located in Bitrix24 DOM",
                },
            }
        ],
    }

    incidente = handle_incident_alert(
        alert_data=alert_payload,
        db_session=db_session,
        client=mock_bitrix_client,
    )

    assert isinstance(incidente, IncidenteOnCall)
    assert incidente.status == StatusIncidente.RESOLVIDO
    assert incidente.trace_id == trace_id
    assert incidente.alerta_nome == "CondoSubmissionFailed"
    assert "SELECTOR_MISMATCH" in incidente.diagnostico or "seletor" in incidente.diagnostico.lower()
    assert "reparo" in incidente.acao_executada.lower() or "dinamico" in incidente.acao_executada.lower()

    # Verify database persistence of incident
    saved_incidente = db_session.get(IncidenteOnCall, incidente.id)
    assert saved_incidente is not None
    assert saved_incidente.status == StatusIncidente.RESOLVIDO

    # Verify updated submission in database
    db_session.refresh(submissao)
    assert submissao.status == StatusSubmissao.SUCESSO
    assert submissao.protocolo_retorno is not None
    assert submissao.protocolo_retorno.startswith("IBAGY-2026-")
    assert submissao.tentativas >= 2

    # Verify cycle status updated to ENVIADO
    db_session.refresh(ciclo)
    assert ciclo.status_ciclo == StatusCiclo.ENVIADO


# ---------------------------------------------------------------------------
# 3. On-Call Agent Self-Healing: Transient HTTP 5xx / Network Timeout
# ---------------------------------------------------------------------------

def test_on_call_agent_fixes_http_5xx_timeout_via_fallback(db_session: Session, mock_bitrix_client):
    """
    On-Call agent detects HTTP_5XX_TIMEOUT, activates direct HTTP fallback,
    replays dead-letter submission queue, updates SubmissaoRessarcimento to SUCESSO, and marks incident RESOLVIDO.
    """
    trace_id = uuid.uuid4().hex
    submissao = SubmissaoRessarcimento(
        ciclo_id=None,
        contrato_numero="09638.003.03",
        payload_enviado={
            "nome": "Luiz Augusto Soutes",
            "email": "luiz@example.com",
            "telefone": "55 48 99999-9999",
            "contrato": "09638.003.03",
            "observacoes": "Replay dead-letter submission",
        },
        status=StatusSubmissao.ERRO,
        protocolo_retorno=None,
        tentativas=1,
        trace_id=trace_id,
        enviado_em=datetime.now(timezone.utc),
    )
    db_session.add(submissao)
    db_session.commit()

    alert_payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "CondoSubmissionFailed",
                    "severity": "critical",
                },
                "annotations": {
                    "trace_id": trace_id,
                    "error_type": "HTTP_5XX_TIMEOUT",
                    "description": "HTTP 500 server error received from Bitrix CRM endpoint",
                },
            }
        ],
    }

    incidente = handle_incident_alert(
        alert_data=alert_payload,
        db_session=db_session,
        client=mock_bitrix_client,
    )

    assert isinstance(incidente, IncidenteOnCall)
    assert incidente.status == StatusIncidente.RESOLVIDO
    assert incidente.trace_id == trace_id
    assert "HTTP_5XX_TIMEOUT" in incidente.diagnostico or "5xx" in incidente.diagnostico.lower()
    assert "fallback" in incidente.acao_executada.lower() or "replay" in incidente.acao_executada.lower()

    # Verify submission updated to SUCESSO
    db_session.refresh(submissao)
    assert submissao.status == StatusSubmissao.SUCESSO
    assert submissao.protocolo_retorno is not None
    assert submissao.protocolo_retorno.startswith("IBAGY-2026-")


# ---------------------------------------------------------------------------
# 4. On-Call Agent Escalation: Unrecoverable Issue
# ---------------------------------------------------------------------------

def test_on_call_agent_escalates_unrecoverable_issue(db_session: Session):
    """
    On-Call agent detects unrecoverable error (e.g. unknown error type or non-existent submission),
    sets status to ESCALADO_HUMANO, persists diagnosis and human escalation reason.
    """
    trace_id = uuid.uuid4().hex
    alert_payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "CondoSubmissionFailed",
                    "severity": "critical",
                },
                "annotations": {
                    "trace_id": trace_id,
                    "error_type": "CORRUPTED_DOCUMENT_PAYLOAD",
                    "description": "Attachment PDF corrupted and checksum validation failed",
                },
            }
        ],
    }

    incidente = handle_incident_alert(
        alert_data=alert_payload,
        db_session=db_session,
    )

    assert isinstance(incidente, IncidenteOnCall)
    assert incidente.status == StatusIncidente.ESCALADO_HUMANO
    assert incidente.trace_id == trace_id
    assert "CORRUPTED_DOCUMENT_PAYLOAD" in incidente.diagnostico or "corrompido" in incidente.diagnostico.lower() or "irrecuperavel" in incidente.diagnostico.lower()
    assert "escalado" in incidente.acao_executada.lower() or "humano" in incidente.acao_executada.lower()

    saved = db_session.get(IncidenteOnCall, incidente.id)
    assert saved is not None
    assert saved.status == StatusIncidente.ESCALADO_HUMANO


def test_on_call_agent_escalates_unrecoverable_with_existing_submission(db_session: Session):
    """
    On-Call agent detects unrecoverable error for an existing submission,
    sets status to ESCALADO_HUMANO, leaves submission in ERRO status.
    """
    trace_id = uuid.uuid4().hex
    submissao = SubmissaoRessarcimento(
        ciclo_id=None,
        contrato_numero="09638.003.03",
        payload_enviado={
            "nome": "Luiz Soutes",
            "email": "luiz@example.com",
            "telefone": "55 48 99999-9999",
            "contrato": "09638.003.03",
        },
        status=StatusSubmissao.ERRO,
        protocolo_retorno=None,
        tentativas=1,
        trace_id=trace_id,
        enviado_em=datetime.now(timezone.utc),
    )
    db_session.add(submissao)
    db_session.commit()

    alert_payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "CondoSubmissionFailed",
                    "severity": "critical",
                },
                "annotations": {
                    "trace_id": trace_id,
                    "error_type": "DATA_CORRUPTION_FATAL",
                    "description": "Unrecoverable database corruption in submission payload",
                },
            }
        ],
    }

    incidente = handle_incident_alert(
        alert_data=alert_payload,
        db_session=db_session,
    )

    assert isinstance(incidente, IncidenteOnCall)
    assert incidente.status == StatusIncidente.ESCALADO_HUMANO
    assert "DATA_CORRUPTION_FATAL" in incidente.diagnostico or "irrecuperavel" in incidente.diagnostico.lower()

    # Submission status must remain ERRO
    db_session.refresh(submissao)
    assert submissao.status == StatusSubmissao.ERRO
    assert submissao.protocolo_retorno is None



# ---------------------------------------------------------------------------
# 5. On-Call Agent Escalation: SLA Breach Warning
# ---------------------------------------------------------------------------

def test_on_call_agent_handles_sla_breach_warning(db_session: Session):
    """
    On-Call agent receives CondoSlaBreachWarning, diagnoses SLA threshold (<3 days),
    persists incident with status ESCALADO_HUMANO and prioritizes human review.
    """
    trace_id = uuid.uuid4().hex
    alert_payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "CondoSlaBreachWarning",
                    "severity": "warning",
                },
                "annotations": {
                    "trace_id": trace_id,
                    "error_type": "SLA_BREACH_WARNING",
                    "description": "condo_cycle_sla_days_remaining is under 3 days (1.5 days left)",
                },
            }
        ],
    }

    incidente = handle_incident_alert(
        alert_data=alert_payload,
        db_session=db_session,
    )

    assert isinstance(incidente, IncidenteOnCall)
    assert incidente.status == StatusIncidente.ESCALADO_HUMANO
    assert incidente.alerta_nome == "CondoSlaBreachWarning"
    assert "sla" in incidente.diagnostico.lower()
    assert "notificacao" in incidente.acao_executada.lower() or "escalado" in incidente.acao_executada.lower()


# ---------------------------------------------------------------------------
# 6. Webhook Endpoint: POST /api/alerts/webhook
# ---------------------------------------------------------------------------

def test_alertmanager_webhook_endpoint_resolves_incident(client_app, db_session: Session):
    """
    POST /api/alerts/webhook receives Alertmanager alert payload, executes On-Call
    agent, repairs incident, and returns HTTP 200 with incident details.
    """
    trace_id = uuid.uuid4().hex
    submissao = SubmissaoRessarcimento(
        ciclo_id=None,
        contrato_numero="09638.003.03",
        payload_enviado={
            "nome": "Luiz Soutes",
            "email": "luiz@example.com",
            "telefone": "55 48 99999-9999",
            "contrato": "09638.003.03",
        },
        status=StatusSubmissao.ERRO,
        protocolo_retorno=None,
        tentativas=1,
        trace_id=trace_id,
        enviado_em=datetime.now(timezone.utc),
    )
    db_session.add(submissao)
    db_session.commit()

    webhook_payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "CondoSubmissionFailed",
                    "severity": "critical",
                },
                "annotations": {
                    "trace_id": trace_id,
                    "error_type": "SELECTOR_MISMATCH",
                    "description": "Field contrato could not be located in Bitrix24 DOM",
                },
            }
        ],
    }

    response = client_app.post("/api/alerts/webhook", json=webhook_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("processed", "ok", "success")
    assert "incidentes" in data
    assert len(data["incidentes"]) > 0

    first_incident = data["incidentes"][0]
    assert first_incident["trace_id"] == trace_id
    assert first_incident["status"] == "RESOLVIDO"

    # Verify DB record
    incidente_db = db_session.query(IncidenteOnCall).filter_by(trace_id=trace_id).first()
    assert incidente_db is not None
    assert incidente_db.status == StatusIncidente.RESOLVIDO


def test_alertmanager_webhook_endpoint_escalates_unrecoverable(client_app, db_session: Session):
    """
    POST /api/alerts/webhook returns ESCALADO_HUMANO when receiving an unrecoverable incident.
    """
    trace_id = uuid.uuid4().hex
    webhook_payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "CondoSubmissionFailed",
                    "severity": "critical",
                },
                "annotations": {
                    "trace_id": trace_id,
                    "error_type": "UNKNOWN_UNRECOVERABLE_FATAL",
                    "description": "Critical database integrity failure",
                },
            }
        ],
    }

    response = client_app.post("/api/alerts/webhook", json=webhook_payload)
    assert response.status_code == 200
    data = response.json()
    assert "incidentes" in data
    assert data["incidentes"][0]["status"] == "ESCALADO_HUMANO"


def test_alertmanager_webhook_ignores_resolved_alerts(client_app):
    """
    POST /api/alerts/webhook cleanly ignores alerts with status='resolved'.
    """
    webhook_payload = {
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "CondoSubmissionFailed",
                    "severity": "critical",
                },
                "annotations": {
                    "trace_id": uuid.uuid4().hex,
                    "description": "Resolved incident notification from Alertmanager",
                },
            }
        ],
    }

    response = client_app.post("/api/alerts/webhook", json=webhook_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("processed", "ok")
    assert data["count"] == 0
    assert len(data["incidentes"]) == 0

    # Also verify direct single alert payload with status='resolved'
    single_resolved = {
        "status": "resolved",
        "labels": {
            "alertname": "CondoSubmissionFailed",
            "severity": "critical",
        },
        "annotations": {
            "trace_id": uuid.uuid4().hex,
            "description": "Single resolved notification",
        },
    }
    resp_single = client_app.post("/api/alerts/webhook", json=single_resolved)
    assert resp_single.status_code == 200
    data_single = resp_single.json()
    assert data_single["count"] == 0
    assert len(data_single["incidentes"]) == 0

