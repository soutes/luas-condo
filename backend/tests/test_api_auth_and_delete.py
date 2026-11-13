"""
Tests for write-route authentication and cycle deletion.
Follows TDD methodology.
No emojis used.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

backend_dir = Path(__file__).resolve().parent.parent
root_dir = backend_dir.parent
for path in (root_dir, backend_dir):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

WRITE_HEADERS = {"Authorization": "Bearer test-write-token-0123456789abcdef"}

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import (  # noqa: E402
    CategoriaItem,
    CicloCondominio,
    CompetenciaDescartada,
    ItemRateio,
    ResponsabilidadeItem,
    StatusCiclo,
    StatusSubmissao,
    SubmissaoRessarcimento,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session: Session):
    """Client WITHOUT default credentials: each test supplies its own headers."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_ciclo(db: Session, competencia: str, status: StatusCiclo) -> CicloCondominio:
    ciclo = CicloCondominio(
        competencia=competencia,
        condominio_nome="CONDOMINIO TESTE",
        data_vencimento=date(2026, 7, 10),
        valor_total=Decimal("1000.00"),
        valor_ressarcimento=Decimal("300.00"),
        valor_saldo_residual=Decimal("300.00"),
        status_ciclo=status,
    )
    db.add(ciclo)
    db.flush()
    db.add(
        ItemRateio(
            ciclo_id=ciclo.id,
            categoria=CategoriaItem.EXTRAORDINARIA,
            descricao="Fundo de Reserva",
            valor_unidade=Decimal("300.00"),
            responsabilidade=ResponsabilidadeItem.LOCADOR,
            justificativa_legal="Art. 22",
        )
    )
    db.commit()
    return ciclo


# ---------------------------------------------------------------------------
# Authentication on write routes
# ---------------------------------------------------------------------------

WRITE_ROUTES = [
    ("post", "/api/ciclos/sync-email"),
    ("post", "/api/ciclos/seed-demo"),
    ("post", "/api/ciclos/documentos"),
    ("post", f"/api/ciclos/{uuid.uuid4()}/submeter"),
    ("delete", f"/api/ciclos/{uuid.uuid4()}"),
]


@pytest.mark.parametrize("method,path", WRITE_ROUTES)
def test_write_routes_reject_missing_token(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401


@pytest.mark.parametrize("method,path", WRITE_ROUTES)
def test_write_routes_reject_wrong_token(client, method, path):
    response = getattr(client, method)(path, headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_write_routes_fail_closed_when_token_not_configured(client, monkeypatch):
    monkeypatch.delenv("API_WRITE_TOKEN", raising=False)
    response = client.delete(f"/api/ciclos/{uuid.uuid4()}", headers=WRITE_HEADERS)
    assert response.status_code == 503


def test_read_routes_stay_open(client):
    assert client.get("/api/ciclos").status_code == 200
    assert client.get("/api/health").status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/ciclos/{id}
# ---------------------------------------------------------------------------

def test_delete_pending_cycle_removes_it_with_items(client, db_session):
    ciclo = make_ciclo(db_session, "2026-06", StatusCiclo.PENDENTE_COMPROVANTE)
    ciclo_id = ciclo.id

    response = client.delete(f"/api/ciclos/{ciclo_id}", headers=WRITE_HEADERS)

    assert response.status_code == 204
    assert client.get(f"/api/ciclos/{ciclo_id}").status_code == 404
    assert db_session.query(ItemRateio).filter_by(ciclo_id=ciclo_id).count() == 0
    assert db_session.get(CompetenciaDescartada, "2026-06") is not None


def test_delete_ready_cycle_without_successful_submission_is_allowed(client, db_session):
    ciclo = make_ciclo(db_session, "2026-09", StatusCiclo.PRONTO_PARA_ENVIO)
    response = client.delete(f"/api/ciclos/{ciclo.id}", headers=WRITE_HEADERS)
    assert response.status_code == 204


@pytest.mark.parametrize("status", [StatusCiclo.ENVIADO, StatusCiclo.PROCESSADO_ALUGUEL])
def test_delete_submitted_cycle_is_refused(client, db_session, status):
    ciclo = make_ciclo(db_session, "2026-10", status)
    response = client.delete(f"/api/ciclos/{ciclo.id}", headers=WRITE_HEADERS)
    assert response.status_code == 409
    assert db_session.get(CicloCondominio, ciclo.id) is not None


def test_delete_cycle_with_successful_submission_is_refused(client, db_session):
    ciclo = make_ciclo(db_session, "2026-08", StatusCiclo.PRONTO_PARA_ENVIO)
    db_session.add(
        SubmissaoRessarcimento(
            ciclo_id=ciclo.id,
            contrato_numero="123",
            payload_enviado={},
            status=StatusSubmissao.SUCESSO,
            protocolo_retorno="IBAGY-2026-ABCD",
            trace_id="t",
        )
    )
    db_session.commit()
    response = client.delete(f"/api/ciclos/{ciclo.id}", headers=WRITE_HEADERS)
    assert response.status_code == 409


def test_delete_unknown_cycle_returns_404(client):
    response = client.delete(f"/api/ciclos/{uuid.uuid4()}", headers=WRITE_HEADERS)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Discarded competences are not recreated by e-mail sync
# ---------------------------------------------------------------------------

def test_sync_does_not_recreate_discarded_competencia(db_session, monkeypatch):
    from types import SimpleNamespace
    from app.services import email_worker

    db_session.add(CompetenciaDescartada(competencia="2026-06"))
    db_session.commit()

    parsed = SimpleNamespace(
        competencia="2026-06",
        condominio_nome="CONDOMINIO TESTE",
        data_vencimento=date(2026, 7, 10),
        valor_total=Decimal("1000.00"),
        valor_ordinarias=Decimal("600.00"),
        valor_extraordinarias=Decimal("300.00"),
        valor_fundos=Decimal("50.00"),
        valor_leituras=Decimal("50.00"),
        itens=[],
    )
    monkeypatch.setattr(email_worker, "decrypt_pdf_bytes", lambda b: b)
    monkeypatch.setattr(email_worker, "parse_condo_pdf", lambda b: parsed)
    monkeypatch.setattr(
        email_worker,
        "audit_condo_bill",
        lambda p: SimpleNamespace(total_reimbursement=Decimal("300.00"), itens_auditados=[]),
    )
    doc = email_worker.IngestedDocument(
        doc_type=email_worker.DocumentType.CONDO_BILL, filename="b.pdf", content=b"x"
    )

    cycles = email_worker.sync_condo_cycle(db_session, [doc], storage_dir=tempfile.mkdtemp())

    assert cycles == []
    assert db_session.query(CicloCondominio).count() == 0
