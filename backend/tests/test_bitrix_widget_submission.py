"""
Tests for the real-portal submission path: Bitrix24 widget form driven by Playwright.
The mock server exposes /widget/ressarcimento/, a page that imitates the real widget
(b24-form classes, name/email/phone fields, 'Enviar' button, success/error states).
Follows TDD methodology.
No emojis used.
"""

import asyncio
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
import uvicorn

backend_dir = Path(__file__).resolve().parent.parent
root_dir = backend_dir.parent
for path in (root_dir, backend_dir):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.database import Base  # noqa: E402
from app.models.entities import (  # noqa: E402
    CicloCondominio,
    StatusCiclo,
    StatusSubmissao,
    SubmissaoRessarcimento,
)
from app.services import bitrix_submitter  # noqa: E402
from app.services.bitrix_submitter import (  # noqa: E402
    SubmissionPayload,
    SubmissionReceipt,
    format_phone_br,
    submit_reimbursement,
)
from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402
from mock_bitrix.main import app as mock_bitrix_app  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def live_mock_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(mock_bitrix_app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=2.0)


@pytest.fixture
def payload():
    with tempfile.TemporaryDirectory() as tmp:
        boleto = os.path.join(tmp, "boleto.pdf")
        comprovante = os.path.join(tmp, "comprovante.pdf")
        Path(boleto).write_bytes(b"%PDF-1.4 boleto")
        Path(comprovante).write_bytes(b"%PDF-1.4 comprovante")
        yield SubmissionPayload(
            nome="Luiz Soutes",
            email="soutes@example.com",
            telefone="48999998888",
            contrato="09638.003.03",
            observacoes="Pedido automatizado",
            boleto_path=boleto,
            comprovante_path=comprovante,
        )


@pytest.fixture(autouse=True)
def plenty_of_memory(monkeypatch):
    monkeypatch.setattr(bitrix_submitter, "_available_memory_mb", lambda: 4096)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("48999998888", "55 48 99999-8888"),
        ("5548999998888", "55 48 99999-8888"),
        ("+55 (48) 99999-8888", "55 48 99999-8888"),
        ("55 48 99999-8888", "55 48 99999-8888"),
        ("4833334444", "55 48 3333-4444"),
        ("123", "123"),
    ],
)
def test_format_phone_br(raw, expected):
    assert format_phone_br(raw) == expected


def test_find_result_id_handles_nested_payloads():
    find = bitrix_submitter._find_result_id
    assert find({"status": "success", "data": {"resultId": 4242}}) == "4242"
    assert find({"data": {"result": {"resultId": "77"}}}) == "77"
    assert find({"data": {}}) is None
    assert find("not a dict") is None


# ---------------------------------------------------------------------------
# Widget flow against the mock widget page
# ---------------------------------------------------------------------------

def test_widget_submission_success_reports_crm_result_id(live_mock_server, payload, db_session: Session):
    receipt = asyncio.run(
        submit_reimbursement(
            payload=payload,
            db_session=db_session,
            target_url=f"{live_mock_server}/widget/ressarcimento/",
            use_browser=True,
        )
    )
    assert receipt.status == StatusSubmissao.SUCESSO, receipt.mensagem
    assert receipt.protocolo == "BITRIX-4242"
    assert receipt.screenshot_path and os.path.exists(receipt.screenshot_path)
    assert db_session.query(SubmissaoRessarcimento).count() == 1


def test_widget_submission_failure_state_is_reported_as_error(live_mock_server, payload):
    receipt = asyncio.run(
        submit_reimbursement(
            payload=payload,
            target_url=f"{live_mock_server}/widget/ressarcimento/?fail=1",
            use_browser=True,
        )
    )
    assert receipt.status == StatusSubmissao.ERRO
    assert receipt.protocolo is None


def test_widget_dry_run_fills_everything_but_does_not_submit(live_mock_server, payload, db_session: Session):
    receipt = asyncio.run(
        submit_reimbursement(
            payload=payload,
            db_session=db_session,
            target_url=f"{live_mock_server}/widget/ressarcimento/",
            use_browser=True,
            dry_run=True,
        )
    )
    assert receipt.dry_run is True
    assert receipt.status == StatusSubmissao.ERRO
    assert receipt.protocolo is None
    assert receipt.screenshot_path and os.path.exists(receipt.screenshot_path)
    assert "nao foi enviado" in receipt.mensagem.lower()
    assert db_session.query(SubmissaoRessarcimento).count() == 0


# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------

def test_browser_refuses_to_start_when_memory_is_low(monkeypatch, live_mock_server, payload):
    monkeypatch.setattr(bitrix_submitter, "_available_memory_mb", lambda: 120)
    receipt = asyncio.run(
        submit_reimbursement(
            payload=payload,
            target_url=f"{live_mock_server}/widget/ressarcimento/",
            use_browser=True,
        )
    )
    assert receipt.status == StatusSubmissao.ERRO
    assert "memoria" in receipt.mensagem.lower()


def test_missing_browser_binary_gives_actionable_message(monkeypatch, live_mock_server, payload):
    async def fake_launch(_playwright):
        raise Exception("BrowserType.launch: Executable doesn't exist at /ms-playwright/chromium")

    monkeypatch.setattr(bitrix_submitter, "_launch_browser", fake_launch)
    receipt = asyncio.run(
        submit_reimbursement(
            payload=payload,
            target_url=f"{live_mock_server}/widget/ressarcimento/",
            use_browser=True,
        )
    )
    assert receipt.status == StatusSubmissao.ERRO
    assert "INSTALL_BROWSER" in receipt.mensagem


def test_real_portal_always_uses_the_browser(monkeypatch, payload):
    """With MOCK_SUBMISSION=false a plain HTTP POST can never work against the widget."""
    monkeypatch.setenv("MOCK_SUBMISSION", "false")
    calls = []

    async def fake_browser(**kwargs):
        calls.append("browser")
        return SubmissionReceipt(status=StatusSubmissao.SUCESSO, protocolo="BITRIX-1", mensagem="ok", trace_id="t")

    async def fake_http(**kwargs):
        calls.append("http")
        return SubmissionReceipt(status=StatusSubmissao.ERRO, mensagem="no", trace_id="t")

    monkeypatch.setattr(bitrix_submitter, "_submit_via_browser", fake_browser)
    monkeypatch.setattr(bitrix_submitter, "_submit_via_http", fake_http)

    receipt = asyncio.run(submit_reimbursement(payload=payload))
    assert calls == ["browser"]
    assert receipt.status == StatusSubmissao.SUCESSO


def test_success_without_protocol_does_not_print_none_in_cycle_details(monkeypatch, payload, db_session: Session):
    ciclo = CicloCondominio(
        competencia="2026-10",
        condominio_nome="CONDOMINIO TESTE",
        data_vencimento=date(2026, 11, 10),
        valor_total=Decimal("1000.00"),
        valor_ressarcimento=Decimal("300.00"),
        valor_saldo_residual=Decimal("300.00"),
        status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
    )
    db_session.add(ciclo)
    db_session.commit()
    payload.ciclo_id = ciclo.id

    async def fake_browser(**kwargs):
        return SubmissionReceipt(status=StatusSubmissao.SUCESSO, protocolo=None, mensagem="ok", trace_id="t")

    monkeypatch.setattr(bitrix_submitter, "_submit_via_browser", fake_browser)
    asyncio.run(
        submit_reimbursement(
            payload=payload,
            db_session=db_session,
            target_url="http://x/widget",
            use_browser=True,
        )
    )
    db_session.refresh(ciclo)
    assert ciclo.status_ciclo == StatusCiclo.ENVIADO
    assert "None" not in ciclo.detalhes_verificacao


# ---------------------------------------------------------------------------
# Dry-run command line tool
# ---------------------------------------------------------------------------

def test_dry_run_tool_requires_tenant_settings(monkeypatch, payload, capsys):
    from app.tools import ibagy_dry_run

    for var in ("IBAGY_TENANT_NAME", "IBAGY_TENANT_EMAIL", "IBAGY_TENANT_PHONE", "IBAGY_CONTRACT_NUM"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(
        sys, "argv", ["x", "--boleto", payload.boleto_path, "--comprovante", payload.comprovante_path]
    )
    assert ibagy_dry_run.main() == 2
    assert "IBAGY_TENANT" in capsys.readouterr().err


def test_dry_run_tool_fills_form_and_stops(monkeypatch, live_mock_server, payload, capsys):
    from app.tools import ibagy_dry_run

    monkeypatch.setenv("IBAGY_TENANT_NAME", payload.nome)
    monkeypatch.setenv("IBAGY_TENANT_EMAIL", payload.email)
    monkeypatch.setenv("IBAGY_TENANT_PHONE", payload.telefone)
    monkeypatch.setenv("IBAGY_CONTRACT_NUM", payload.contrato)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--boleto", payload.boleto_path,
            "--comprovante", payload.comprovante_path,
            "--url", f"{live_mock_server}/widget/ressarcimento/",
        ],
    )
    assert ibagy_dry_run.main() == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "Screenshot:" in out
