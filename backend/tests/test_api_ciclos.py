"""
Tests for Condominium Cycles and Reimbursement Submission API Endpoints.
Covers GET /api/ciclos, GET /api/ciclos/{id}, and POST /api/ciclos/{id}/submeter.
Follows TDD methodology.
No emojis used.
"""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import sys
import uuid
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
from app.models.entities import (
    CategoriaItem,
    CicloCondominio,
    ItemRateio,
    ResponsabilidadeItem,
    StatusCiclo,
    StatusSubmissao,
    SubmissaoRessarcimento,
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


def test_get_ciclos_empty(client: TestClient):
    """GET /api/ciclos returns empty list when no cycles exist."""
    response = client.get("/api/ciclos")
    assert response.status_code == 200
    assert response.json() == []


def test_get_ciclos_list_with_reference_reimbursement(client: TestClient, db_session: Session):
    """GET /api/ciclos lists cycles including reference reimbursement R$ 354,50."""
    ciclo = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.50"),
        valor_ordinarias=Decimal("800.00"),
        valor_extraordinarias=Decimal("354.50"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/data/boletos/villa_salomy_2026_09.pdf",
        comprovante_pix_path="/data/comprovantes/pix_2026_09.pdf",
        status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
    )
    db_session.add(ciclo)
    db_session.flush()

    item_locatario = ItemRateio(
        ciclo_id=ciclo.id,
        categoria=CategoriaItem.ORDINARIA,
        descricao="Despesas Ordinarias de Condominio",
        valor_unidade=Decimal("800.00"),
        responsabilidade=ResponsabilidadeItem.LOCATARIO,
        justificativa_legal="Art. 23 da Lei 8.245/91",
    )
    item_locador = ItemRateio(
        ciclo_id=ciclo.id,
        categoria=CategoriaItem.EXTRAORDINARIA,
        descricao="Fundo de Reserva / Reforma Fachada",
        valor_unidade=Decimal("354.50"),
        responsabilidade=ResponsabilidadeItem.LOCADOR,
        justificativa_legal="Art. 22, X da Lei 8.245/91",
    )
    db_session.add_all([item_locatario, item_locador])
    db_session.commit()

    response = client.get("/api/ciclos")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    cycle_data = data[0]
    assert cycle_data["id"] == str(ciclo.id)
    assert cycle_data["competencia"] == "2026-09"
    assert cycle_data["condominio_nome"] == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert float(cycle_data["valor_ressarcimento"]) == 354.50
    assert float(cycle_data["valor_total"]) == 1154.50
    assert len(cycle_data["itens"]) == 2


def test_get_ciclo_by_id_success(client: TestClient, db_session: Session):
    """GET /api/ciclos/{id} returns detailed cycle with items and submissions."""
    ciclo = CicloCondominio(
        competencia="2026-08",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 9, 10),
        valor_total=Decimal("1000.00"),
        valor_ordinarias=Decimal("700.00"),
        valor_extraordinarias=Decimal("300.00"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        valor_ressarcimento=Decimal("300.00"),
        boleto_pdf_path="/data/boletos/2026_08.pdf",
        status_ciclo=StatusCiclo.PENDENTE_COMPROVANTE,
    )
    db_session.add(ciclo)
    db_session.commit()

    response = client.get(f"/api/ciclos/{ciclo.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(ciclo.id)
    assert data["competencia"] == "2026-08"
    assert float(data["valor_ressarcimento"]) == 300.00


def test_get_ciclo_by_id_not_found(client: TestClient):
    """GET /api/ciclos/{random_id} returns 404 Not Found."""
    random_id = uuid.uuid4()
    response = client.get(f"/api/ciclos/{random_id}")
    assert response.status_code == 404
    assert "nao encontrado" in response.json()["detail"].lower()


def test_submeter_ciclo_success(client: TestClient, db_session: Session, tmp_path: Path):
    """POST /api/ciclos/{id}/submeter triggers Bitrix24 reimbursement submission."""
    boleto_file = tmp_path / "boleto.pdf"
    comprovante_file = tmp_path / "comprovante.pdf"
    boleto_file.write_bytes(b"%PDF-1.4 Mock Boleto Content")
    comprovante_file.write_bytes(b"%PDF-1.4 Mock Comprovante PIX Content")

    ciclo = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.50"),
        valor_ordinarias=Decimal("800.00"),
        valor_extraordinarias=Decimal("354.50"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path=str(boleto_file),
        comprovante_pix_path=str(comprovante_file),
        status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
    )
    db_session.add(ciclo)
    db_session.flush()

    item_locador = ItemRateio(
        ciclo_id=ciclo.id,
        categoria=CategoriaItem.EXTRAORDINARIA,
        descricao="Fundo de Reserva / Reforma",
        valor_unidade=Decimal("354.50"),
        responsabilidade=ResponsabilidadeItem.LOCADOR,
        justificativa_legal="Art. 22, X, g da Lei 8.245/91",
    )
    db_session.add(item_locador)
    db_session.commit()

    response = client.post(
        f"/api/ciclos/{ciclo.id}/submeter",
        json={
            "contrato": "09638.003.03",
            "nome": "Luiz Augusto Soutes",
            "email": "luizsoutes@gmail.com",
            "telefone": "48999999999",
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "SUCESSO"
    assert res_data["protocolo"].startswith("IBAGY-2026-")

    # Verify database state was updated
    updated_ciclo = db_session.get(CicloCondominio, ciclo.id)
    assert updated_ciclo.status_ciclo == StatusCiclo.ENVIADO

    submissoes = db_session.query(SubmissaoRessarcimento).filter_by(ciclo_id=ciclo.id).all()
    assert len(submissoes) == 1
    assert submissoes[0].status == StatusSubmissao.SUCESSO
    assert submissoes[0].protocolo_retorno == res_data["protocolo"]


def test_submeter_ciclo_not_found(client: TestClient):
    """POST /api/ciclos/{random_id}/submeter returns 404 Not Found."""
    random_id = uuid.uuid4()
    response = client.post(f"/api/ciclos/{random_id}/submeter", json={})
    assert response.status_code == 404
