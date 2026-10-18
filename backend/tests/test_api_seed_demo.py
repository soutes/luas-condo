"""
Tests for the demo cycle seed endpoint (POST /api/ciclos/seed-demo).
The demo seed must only be available while submissions are mocked
(MOCK_SUBMISSION=true) so sample data can never reach a production database.
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
from app.models.entities import CicloCondominio
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
    """In-memory async client targeting mock_bitrix app."""
    return httpx.AsyncClient(
        transport=ASGITransport(app=mock_bitrix_app),
        base_url="http://testserver",
    )


@pytest.fixture
def client(
    db_session: Session,
    mock_bitrix_client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """FastAPI TestClient with mocked DB, storage dir, and MOCK_SUBMISSION=true."""
    from app.routes.ciclos import set_default_http_client

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MOCK_SUBMISSION", "true")

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


def test_seed_demo_creates_reference_cycle(client: TestClient):
    """POST /api/ciclos/seed-demo creates the audited Villa Salomy reference cycle."""
    response = client.post("/api/ciclos/seed-demo")
    assert response.status_code == 200
    body = response.json()
    assert body["condominio_nome"] == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert body["competencia"] == "2026-09"
    assert body["status_ciclo"] == "PRONTO_PARA_ENVIO"
    assert float(body["valor_ressarcimento"]) == 354.5
    assert len(body["itens"]) > 0
    # Deterministic legal audit: landlord items carry the Art. 22 justification
    itens_locador = [i for i in body["itens"] if i["responsabilidade"] == "LOCADOR"]
    assert len(itens_locador) > 0
    assert all("8.245" in (i["justificativa_legal"] or "") for i in itens_locador)


def test_seed_demo_is_idempotent(client: TestClient):
    """Calling seed-demo twice keeps a single reference cycle with the same id."""
    first = client.post("/api/ciclos/seed-demo")
    second = client.post("/api/ciclos/seed-demo")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_seed_demo_blocked_when_submission_is_real(
    db_session: Session,
    mock_bitrix_client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """With MOCK_SUBMISSION=false the endpoint refuses to insert sample data."""
    from app.routes.ciclos import set_default_http_client

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MOCK_SUBMISSION", "false")

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    set_default_http_client(mock_bitrix_client)
    try:
        with TestClient(app) as test_client:
            response = test_client.post("/api/ciclos/seed-demo")
            assert response.status_code == 403
            assert "MOCK_SUBMISSION" in response.json()["detail"]
        assert db_session.query(CicloCondominio).count() == 0
    finally:
        app.dependency_overrides.clear()
        set_default_http_client(None)
