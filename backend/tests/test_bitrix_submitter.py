"""
Tests for Bitrix24 mock server and reimbursement submitter service.
Follows TDD methodology.
No emojis used.
"""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
import uuid

import httpx
from httpx import ASGITransport
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
import uvicorn

# Ensure project root and backend dir are in sys.path
test_dir = Path(__file__).resolve().parent
backend_dir = test_dir.parent
root_dir = backend_dir.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import Base
from app.models.entities import (
    CicloCondominio,
    StatusCiclo,
    StatusSubmissao,
    SubmissaoRessarcimento,
)
from app.services.bitrix_submitter import (
    SubmissionPayload,
    SubmissionReceipt,
    resolve_target_url,
    submit_reimbursement,
)
from mock_bitrix.main import app as mock_bitrix_app


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database session with foreign keys enabled."""
    engine = create_engine("sqlite:///:memory:", echo=False)
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


@pytest.fixture(scope="module")
def live_mock_server():
    """Spin up live Uvicorn server running mock_bitrix app for browser tests."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(
        mock_bitrix_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to bind
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.should_exit = True
    thread.join(timeout=2.0)


@pytest.fixture
def sample_files():
    """Create dummy boleto and comprovante PDF files for submission testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        boleto_path = os.path.join(tmpdir, "boleto_villa_salomy_2026_09.pdf")
        comprovante_path = os.path.join(tmpdir, "comprovante_pix_2026_09.pdf")
        with open(boleto_path, "wb") as f:
            f.write(b"%PDF-1.4 Mock Boleto Condominio Villa Salomy Content")
        with open(comprovante_path, "wb") as f:
            f.write(b"%PDF-1.4 Mock Comprovante PIX Pagamento Content")
        yield {
            "tmpdir": tmpdir,
            "boleto_path": boleto_path,
            "comprovante_path": comprovante_path,
        }


# ---------------------------------------------------------------------------
# 1. Mock Server Endpoint Tests
# ---------------------------------------------------------------------------

def test_mock_server_renders_html_form():
    """GET / renders Bitrix reimbursement form with all required fields."""
    async def run():
        async with httpx.AsyncClient(
            transport=ASGITransport(app=mock_bitrix_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/condominioressarcimento/ressarcimento/")
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")
            html = resp.text
            assert 'name="nome"' in html
            assert 'name="email"' in html
            assert 'name="telefone"' in html
            assert 'name="contrato"' in html
            assert 'name="observacoes"' in html
            assert 'name="boleto"' in html
            assert 'name="comprovante"' in html
            assert 'id="submit-btn"' in html

    asyncio.run(run())


def test_mock_server_alters_selector_on_simulation_header():
    """GET with x-simulate-selector alters field names (contrato_num)."""
    async def run():
        async with httpx.AsyncClient(
            transport=ASGITransport(app=mock_bitrix_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get(
                "/condominioressarcimento/ressarcimento/",
                headers={"x-simulate-selector": "contrato_num"},
            )
            assert resp.status_code == 200
            html = resp.text
            assert 'name="contrato_num"' in html
            assert 'name="contrato"' not in html

    asyncio.run(run())


def test_mock_server_simulates_status_error():
    """x-simulate-status header forces HTTP status error (e.g. 500, 503)."""
    async def run():
        async with httpx.AsyncClient(
            transport=ASGITransport(app=mock_bitrix_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                "/condominioressarcimento/ressarcimento/",
                headers={"x-simulate-status": "500"},
            )
            assert resp.status_code == 500

            resp_503 = await client.get(
                "/condominioressarcimento/ressarcimento/",
                headers={"x-simulate-status": "503"},
            )
            assert resp_503.status_code == 503

    asyncio.run(run())


def test_mock_server_validates_mandatory_fields():
    """POST without required fields returns HTTP 400 Bad Request."""
    async def run():
        async with httpx.AsyncClient(
            transport=ASGITransport(app=mock_bitrix_app),
            base_url="http://testserver",
        ) as client:
            # Missing contrato
            data = {
                "nome": "Luiz Soutes",
                "email": "luiz@example.com",
                "telefone": "55 48 99999-9999",
            }
            files = {
                "boleto": ("b.pdf", b"pdf content", "application/pdf"),
                "comprovante": ("c.pdf", b"pix content", "application/pdf"),
            }
            resp = await client.post(
                "/condominioressarcimento/ressarcimento/",
                data=data,
                files=files,
            )
            assert resp.status_code == 400
            assert "contrato" in resp.text.lower()

    asyncio.run(run())


def test_mock_server_successful_submission_returns_protocol():
    """POST with valid fields returns protocol format IBAGY-2026-XXXX."""
    async def run():
        async with httpx.AsyncClient(
            transport=ASGITransport(app=mock_bitrix_app),
            base_url="http://testserver",
        ) as client:
            data = {
                "nome": "Luiz Soutes",
                "email": "luiz@example.com",
                "telefone": "55 48 99999-9999",
                "contrato": "09638.003.03",
                "observacoes": "Ressarcimento fundo reserva setembro 2026",
            }
            files = {
                "boleto": ("boleto.pdf", b"%PDF-1.4 boleto content", "application/pdf"),
                "comprovante": ("pix.pdf", b"%PDF-1.4 pix content", "application/pdf"),
            }
            resp = await client.post(
                "/condominioressarcimento/ressarcimento/",
                data=data,
                files=files,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "protocolo" in body
            protocol = body["protocolo"]
            assert re.match(r"^IBAGY-2026-[A-Z0-9]+$", protocol)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 2. Submitter Service HTTP Multipart Tests
# ---------------------------------------------------------------------------

def test_submit_reimbursement_http_success(sample_files, db_session: Session):
    """submit_reimbursement via HTTP multipart successfully posts and records receipt."""
    async def run():
        async with httpx.AsyncClient(
            transport=ASGITransport(app=mock_bitrix_app),
            base_url="http://testserver",
        ) as client:
            payload = SubmissionPayload(
                nome="Luiz Soutes",
                email="luiz@example.com",
                telefone="55 48 99999-9999",
                contrato="09638.003.03",
                observacoes="Ressarcimento extraordinarias",
                boleto_path=sample_files["boleto_path"],
                comprovante_path=sample_files["comprovante_path"],
            )

            receipt = await submit_reimbursement(
                payload=payload,
                db_session=db_session,
                target_url="http://testserver/condominioressarcimento/ressarcimento/",
                use_browser=False,
                client=client,
            )

            assert receipt.status == StatusSubmissao.SUCESSO
            assert receipt.protocolo is not None
            assert receipt.protocolo.startswith("IBAGY-2026-")
            assert receipt.trace_id is not None

            # Verify persisted in database
            records = db_session.query(SubmissaoRessarcimento).all()
            assert len(records) == 1
            rec = records[0]
            assert rec.contrato_numero == "09638.003.03"
            assert rec.status == StatusSubmissao.SUCESSO
            assert rec.protocolo_retorno == receipt.protocolo
            assert rec.trace_id == receipt.trace_id

    asyncio.run(run())


def test_submit_reimbursement_http_simulated_error(sample_files, db_session: Session):
    """submit_reimbursement records ERRO receipt and DB record on server 500 error."""
    async def run():
        async with httpx.AsyncClient(
            transport=ASGITransport(app=mock_bitrix_app),
            base_url="http://testserver",
        ) as client:
            payload = SubmissionPayload(
                nome="Luiz Soutes",
                email="luiz@example.com",
                telefone="55 48 99999-9999",
                contrato="09638.003.03",
                boleto_path=sample_files["boleto_path"],
                comprovante_path=sample_files["comprovante_path"],
            )

            receipt = await submit_reimbursement(
                payload=payload,
                db_session=db_session,
                target_url="http://testserver/condominioressarcimento/ressarcimento/",
                use_browser=False,
                client=client,
                extra_headers={"x-simulate-status": "500"},
            )

            assert receipt.status == StatusSubmissao.ERRO
            assert receipt.protocolo is None
            assert "500" in receipt.mensagem

            records = db_session.query(SubmissaoRessarcimento).all()
            assert len(records) == 1
            assert records[0].status == StatusSubmissao.ERRO

    asyncio.run(run())


def test_submit_reimbursement_updates_cycle_status(sample_files, db_session: Session):
    """When ciclo_id is provided, successful submission updates status to ENVIADO."""
    ciclo = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ressarcimento=Decimal("454.31"),
        boleto_pdf_path=sample_files["boleto_path"],
        comprovante_pix_path=sample_files["comprovante_path"],
        status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
    )
    db_session.add(ciclo)
    db_session.flush()

    async def run():
        async with httpx.AsyncClient(
            transport=ASGITransport(app=mock_bitrix_app),
            base_url="http://testserver",
        ) as client:
            payload = SubmissionPayload(
                ciclo_id=ciclo.id,
                nome="Luiz Soutes",
                email="luiz@example.com",
                telefone="55 48 99999-9999",
                contrato="09638.003.03",
                boleto_path=sample_files["boleto_path"],
                comprovante_path=sample_files["comprovante_path"],
            )

            receipt = await submit_reimbursement(
                payload=payload,
                db_session=db_session,
                target_url="http://testserver/condominioressarcimento/ressarcimento/",
                use_browser=False,
                client=client,
            )

            assert receipt.status == StatusSubmissao.SUCESSO
            updated_cycle = db_session.get(CicloCondominio, ciclo.id)
            assert updated_cycle.status_ciclo == StatusCiclo.ENVIADO

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 3. Submitter Service Playwright Browser Automation Tests
# ---------------------------------------------------------------------------

def test_submit_reimbursement_browser_success(sample_files, live_mock_server, db_session: Session):
    """submit_reimbursement using Playwright browser submits form and takes screenshot."""
    async def run():
        payload = SubmissionPayload(
            nome="Luiz Soutes",
            email="luiz@example.com",
            telefone="55 48 99999-9999",
            contrato="09638.003.03",
            observacoes="Submissao automatizada via Playwright",
            boleto_path=sample_files["boleto_path"],
            comprovante_path=sample_files["comprovante_path"],
        )

        target_url = f"{live_mock_server}/condominioressarcimento/ressarcimento/"
        receipt = await submit_reimbursement(
            payload=payload,
            db_session=db_session,
            target_url=target_url,
            use_browser=True,
        )

        assert receipt.status == StatusSubmissao.SUCESSO
        assert receipt.protocolo is not None
        assert receipt.protocolo.startswith("IBAGY-2026-")
        assert receipt.screenshot_path is not None
        assert os.path.exists(receipt.screenshot_path)

        rec = db_session.query(SubmissaoRessarcimento).first()
        assert rec is not None
        assert rec.screenshot_path == receipt.screenshot_path

    asyncio.run(run())


def test_submit_reimbursement_browser_detects_altered_selector(
    sample_files, live_mock_server, db_session: Session
):
    """Playwright submission handles altered selector gracefully, capturing screenshot of failure."""
    async def run():
        payload = SubmissionPayload(
            nome="Luiz Soutes",
            email="luiz@example.com",
            telefone="55 48 99999-9999",
            contrato="09638.003.03",
            boleto_path=sample_files["boleto_path"],
            comprovante_path=sample_files["comprovante_path"],
        )

        target_url = f"{live_mock_server}/condominioressarcimento/ressarcimento/"
        receipt = await submit_reimbursement(
            payload=payload,
            db_session=db_session,
            target_url=target_url,
            use_browser=True,
            extra_headers={"x-simulate-selector": "contrato_num"},
        )

        assert receipt.status == StatusSubmissao.ERRO
        assert receipt.protocolo is None
        assert receipt.screenshot_path is not None
        assert os.path.exists(receipt.screenshot_path)
        assert "contrato" in receipt.mensagem.lower()

    asyncio.run(run())


def test_submit_reimbursement_browser_fails_fast_on_missing_file(db_session: Session):
    """Playwright submission fails fast with ERRO when local file path does not exist."""
    async def run():
        payload = SubmissionPayload(
            nome="Luiz Soutes",
            email="luiz@example.com",
            telefone="55 48 99999-9999",
            contrato="09638.003.03",
            boleto_path="/nonexistent/path/to/missing_boleto.pdf",
            comprovante_bytes=b"%PDF-1.4 dummy",
        )

        receipt = await submit_reimbursement(
            payload=payload,
            db_session=db_session,
            target_url="http://localhost:8080/condominioressarcimento/ressarcimento/",
            use_browser=True,
        )

        assert receipt.status == StatusSubmissao.ERRO
        assert receipt.protocolo is None
        assert "arquivo nao encontrado" in receipt.mensagem.lower()
        assert receipt.screenshot_path is None

    asyncio.run(run())


def test_submit_reimbursement_http_fails_fast_on_missing_file(db_session: Session):
    """HTTP submission fails fast with ERRO when local file path does not exist."""
    async def run():
        payload = SubmissionPayload(
            nome="Luiz Soutes",
            email="luiz@example.com",
            telefone="55 48 99999-9999",
            contrato="09638.003.03",
            boleto_path="/nonexistent/path/to/missing_boleto.pdf",
            comprovante_bytes=b"%PDF-1.4 dummy",
        )

        receipt = await submit_reimbursement(
            payload=payload,
            db_session=db_session,
            target_url="http://testserver/condominioressarcimento/ressarcimento/",
            use_browser=False,
        )

        assert receipt.status == StatusSubmissao.ERRO
        assert receipt.protocolo is None
        assert "arquivo nao encontrado" in receipt.mensagem.lower()

    asyncio.run(run())


def test_resolve_target_url_normalizes_trailing_slashes(monkeypatch):
    """resolve_target_url correctly appends endpoint path even when base URL has trailing slash."""
    monkeypatch.setenv("MOCK_SUBMISSION", "true")
    monkeypatch.setenv("MOCK_BITRIX_URL", "http://mock-bitrix:8080/")
    url = resolve_target_url()
    assert url == "http://mock-bitrix:8080/condominioressarcimento/ressarcimento/"

    monkeypatch.setenv("MOCK_BITRIX_URL", "http://mock-bitrix:8080")
    url2 = resolve_target_url()
    assert url2 == "http://mock-bitrix:8080/condominioressarcimento/ressarcimento/"

