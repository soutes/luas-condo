"""
Tests for the manual retroactive document upload endpoint (POST /api/ciclos/documentos).
The endpoint must reuse the email-flow classifier and cycle sync engine unchanged:
same classification, same dedupe by competencia, same PIX pairing. Uploaded files
are a backfill path, not new business logic.
Follows TDD methodology.
No emojis used.
"""

from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient
import httpx
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

backend_dir = Path(__file__).resolve().parent.parent
root_dir = backend_dir.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import Base, get_db
from app.main import app
from app.services import email_worker
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
    """In-memory async client targeting mock_bitrix app."""
    return httpx.AsyncClient(
        transport=ASGITransport(app=mock_bitrix_app),
        base_url="http://testserver",
    )


@pytest.fixture
def client(db_session: Session, mock_bitrix_client: httpx.AsyncClient):
    """FastAPI TestClient with overridden get_db and mock submitter client."""
    from app.routes.ciclos import set_default_http_client

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


def test_upload_condo_bill_reaches_sync_engine_with_hint(client, monkeypatch):
    """A classified CONDO_BILL upload flows into sync_condo_cycle carrying the
    competencia hint for later PIX pairing."""
    captured = {}

    def fake_sync(db_session_arg, docs, storage_dir="/data/storage"):
        captured["docs"] = docs
        return []

    monkeypatch.setattr(
        email_worker, "classify_attachment", lambda att, **kw: email_worker.DocumentType.CONDO_BILL
    )
    monkeypatch.setattr(email_worker, "sync_condo_cycle", fake_sync)

    response = client.post(
        "/api/ciclos/documentos",
        files={"files": ("boleto_julho.pdf", b"%PDF-1.4 synthetic bill", "application/pdf")},
        data={"competencia": "2026-07"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["arquivos"][0]["arquivo"] == "boleto_julho.pdf"
    assert body["arquivos"][0]["tipo"] == "CONDO_BILL"
    assert body["arquivos"][0]["arquivado"] is True

    assert len(captured["docs"]) == 1
    doc = captured["docs"][0]
    assert doc.doc_type == email_worker.DocumentType.CONDO_BILL
    assert doc.filename == "boleto_julho.pdf"
    # Competencia hint must travel in both YYYY-MM and MM/YYYY forms so the
    # PIX pairing corpus can match either representation.
    assert "2026-07" in doc.email_subject
    assert "07/2026" in doc.email_subject


def test_upload_pix_receipt_is_classified_and_hinted(client, monkeypatch):
    """Image comprovantes (PNG/JPG) are accepted and carry the month hint."""
    captured = {}

    def fake_sync(db_session_arg, docs, storage_dir="/data/storage"):
        captured["docs"] = docs
        return []

    monkeypatch.setattr(
        email_worker, "classify_attachment", lambda att, **kw: email_worker.DocumentType.PIX_RECEIPT
    )
    monkeypatch.setattr(email_worker, "sync_condo_cycle", fake_sync)

    response = client.post(
        "/api/ciclos/documentos",
        files={"files": ("comprovante_2026-07.png", b"\x89PNG fake receipt", "image/png")},
        data={"competencia": "2026-07"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["arquivos"][0]["tipo"] == "PIX_RECEIPT"
    assert len(captured["docs"]) == 1
    assert "07/2026" in captured["docs"][0].email_subject


def test_upload_multiple_files_single_sync_call(client, monkeypatch):
    """All valid files go to ONE sync_condo_cycle call. The engine itself orders
    bills before receipts when pairing (sync_condo_cycle separates docs by type),
    so the route only needs to deliver the full batch at once."""
    captured = {"docs": None, "calls": 0}

    def fake_sync(db_session_arg, docs, storage_dir="/data/storage"):
        captured["docs"] = docs
        captured["calls"] += 1
        return []

    monkeypatch.setattr(
        email_worker,
        "classify_attachment",
        lambda att, **kw: (
            email_worker.DocumentType.PIX_RECEIPT
            if "comprovante" in att.filename.lower()
            else email_worker.DocumentType.CONDO_BILL
        ),
    )
    monkeypatch.setattr(email_worker, "sync_condo_cycle", fake_sync)

    response = client.post(
        "/api/ciclos/documentos",
        files=[
            ("files", ("comprovante_2026-07.pdf", b"%PDF-1.4 receipt", "application/pdf")),
            ("files", ("boleto_2026-07.pdf", b"%PDF-1.4 bill", "application/pdf")),
        ],
        data={"competencia": "2026-07"},
    )

    assert response.status_code == 200
    assert captured["calls"] == 1
    doc_types = {d.doc_type for d in captured["docs"]}
    assert doc_types == {email_worker.DocumentType.CONDO_BILL, email_worker.DocumentType.PIX_RECEIPT}


def test_upload_unknown_file_reported_and_ignored(client, monkeypatch):
    """UNKNOWN files are reported as not archived and never reach the engine."""
    calls = {"n": 0}

    def fake_sync(*args, **kwargs):
        calls["n"] += 1
        return []

    monkeypatch.setattr(
        email_worker, "classify_attachment", lambda att, **kw: email_worker.DocumentType.UNKNOWN
    )
    monkeypatch.setattr(email_worker, "sync_condo_cycle", fake_sync)

    response = client.post(
        "/api/ciclos/documentos",
        files={"files": ("arquivo_qualquer.txt", b"plain text", "text/plain")},
        data={"competencia": "2026-07"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["arquivos"][0]["tipo"] == "UNKNOWN"
    assert body["arquivos"][0]["arquivado"] is False
    assert calls["n"] == 0  # nothing to sync, engine never invoked
