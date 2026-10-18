"""
Tests for the retroactive batch sync (sync_retroativo_lote) and the
Documentos Retroativos upload semantics.

Business rules (Ibagy already deducts retroactive landlord expenses on the
following month's rental invoice):
- The condo bill defines the cycle; its own extracted competencia is the cycle
  competence.
- The following-month rental invoice is conferencia evidence only and is never
  submitted: compare discount already applied vs audited landlord amount.
  difference <= 0 -> TUDO OK (CONCILIADO_SEM_PENDENCIA, nothing to submit).
  difference > 0  -> PRONTO_PARA_ENVIO (suggest submitting the difference).
- PIX receipts pair with the batch's condo cycle.
No emojis used.
"""

from datetime import date
from decimal import Decimal
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
from app.models.entities import CategoriaItem, CicloCondominio, StatusCiclo
from app.main import app
from app.services import email_worker
from app.services.email_worker import IngestedDocument, DocumentType, previous_month
from app.schemas.condo import ParsedAluguelBill, ParsedCondoBill, ParsedItemRateio
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


def _fake_parsed_bill(competencia: str = "2026-05", ressarcimento: str = "264.50") -> ParsedCondoBill:
    return ParsedCondoBill(
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        competencia=competencia,
        data_vencimento=date(2026, 6, 10),
        valor_total=Decimal("1154.31"),
        valor_ordinarias=Decimal("889.81"),
        valor_extraordinarias=Decimal("264.50"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        itens=[
            ParsedItemRateio(
                descricao="Rateio manutencao fachada (2/10)",
                valor_unidade=Decimal("208.29"),
                valor_total_condominio=None,
                categoria=CategoriaItem.EXTRAORDINARIA,
            ),
            ParsedItemRateio(
                descricao="Fundo de Reserva 10,00%",
                valor_unidade=Decimal("56.21"),
                valor_total_condominio=None,
                categoria=CategoriaItem.FUNDOS,
            ),
        ],
        linha_digitavel=None,
    )


def _rental_doc(competencia_fatura: str = "2026-06", descontos: str = "264.50") -> IngestedDocument:
    """Rental bill doc - parse_aluguel_pdf is monkeypatched so content is irrelevant."""
    return IngestedDocument(
        doc_type=DocumentType.RENTAL_BILL,
        filename=f"Boleto_Aluguel_{competencia_fatura.replace('-', '_')}.pdf",
        content=b"%PDF-1.4 rental",
        content_type="application/pdf",
        email_uid=990,
        email_sender="boleto@ibagyimobiliaria.com.br",
        email_subject="Boleto Aluguel",
    )


def _pix_doc() -> IngestedDocument:
    return IngestedDocument(
        doc_type=DocumentType.PIX_RECEIPT,
        filename="Comprovante_PIX.png",
        content=b"\x89PNG\r\n\x1a\nfake",
        content_type="image/png",
        email_uid=991,
        email_sender="luizsoutes@gmail.com",
        email_subject="Comprovante PIX",
    )


def test_previous_month_rollover():
    assert previous_month("2026-06") == "2026-05"
    assert previous_month("2026-01") == "2025-12"
    assert previous_month("2025-03") == "2025-02"


def test_lote_retroativo_tudo_ok(db_session: Session, tmp_path: Path, monkeypatch):
    """Retroactive batch where the following-month invoice already discounted the
    full landlord amount: cycle becomes CONCILIADO_SEM_PENDENCIA (nothing to submit)."""
    monkeypatch.setattr(
        email_worker, "parse_condo_pdf", lambda content: _fake_parsed_bill()
    )
    monkeypatch.setattr(
        email_worker,
        "parse_aluguel_pdf",
        lambda content, password="04293": ParsedAluguelBill(
            competencia="2026-06",
            contrato="09638.003.03",
            data_vencimento=date(2026, 6, 10),
            valor_total_aluguel=Decimal("2741.14"),
            valor_total_descontos=Decimal("264.50"),
            itens_desconto=[],
        ),
    )

    result, falhas = email_worker.sync_retroativo_lote(
        db_session,
        [_rental_doc(), _pix_doc(), IngestedDocument(
            doc_type=DocumentType.CONDO_BILL,
            filename="Boleto_Ref_052026.pdf",
            content=b"%PDF-1.4 condo",
            content_type="application/pdf",
            email_subject="upload manual competencia 2026-05 05/2026",
        )],
        storage_dir=str(tmp_path / "storage"),
    )

    assert falhas == []
    assert len(result) == 1
    ciclo = result[0]
    assert ciclo.competencia == "2026-05"
    assert ciclo.status_ciclo == StatusCiclo.CONCILIADO_SEM_PENDENCIA
    assert ciclo.valor_saldo_residual == Decimal("0.00")
    assert "tudo ok" in ciclo.detalhes_verificacao.lower()
    assert ciclo.boleto_pdf_path
    assert ciclo.boleto_aluguel_path
    assert ciclo.comprovante_pix_path


def test_lote_retroativo_diferenca_sugere_envio(db_session: Session, tmp_path: Path, monkeypatch):
    """Retroactive batch where the following-month invoice discounted LESS than
    the audited landlord amount: cycle becomes PRONTO_PARA_ENVIO with the
    difference as the residual balance (suggest submitting to Ibagy)."""
    monkeypatch.setattr(
        email_worker, "parse_condo_pdf", lambda content: _fake_parsed_bill()
    )
    monkeypatch.setattr(
        email_worker,
        "parse_aluguel_pdf",
        lambda content, password="04293": ParsedAluguelBill(
            competencia="2026-06",
            contrato="09638.003.03",
            data_vencimento=date(2026, 6, 10),
            valor_total_aluguel=Decimal("2741.14"),
            valor_total_descontos=Decimal("100.00"),
            itens_desconto=[],
        ),
    )

    result, falhas = email_worker.sync_retroativo_lote(
        db_session,
        [IngestedDocument(
            doc_type=DocumentType.CONDO_BILL,
            filename="Boleto_Ref_052026.pdf",
            content=b"%PDF-1.4 condo",
            content_type="application/pdf",
            email_subject="upload manual competencia 2026-05 05/2026",
        ), _rental_doc(), _pix_doc()],
        storage_dir=str(tmp_path / "storage"),
    )

    assert falhas == []
    ciclo = result[0]
    assert ciclo.status_ciclo == StatusCiclo.PRONTO_PARA_ENVIO
    assert ciclo.valor_saldo_residual == Decimal("164.50")
    assert "diferenca apurada" in ciclo.detalhes_verificacao.lower()
    assert "sugerido: enviar" in ciclo.detalhes_verificacao.lower()


def test_lote_retroativo_pix_casa_com_ciclo_do_boleto(db_session: Session, tmp_path: Path, monkeypatch):
    """PIX pairs with the batch's condo cycle even when the batch hint points to
    a different month (cycle competence comes from the condo bill, not the hint)."""
    monkeypatch.setattr(
        email_worker, "parse_condo_pdf", lambda content: _fake_parsed_bill()
    )

    result, falhas = email_worker.sync_retroativo_lote(
        db_session,
        [IngestedDocument(
            doc_type=DocumentType.CONDO_BILL,
            filename="Boleto_Ref_052026.pdf",
            content=b"%PDF-1.4 condo",
            content_type="application/pdf",
            email_subject="upload manual competencia 2026-06 06/2026",
        ), _pix_doc()],
        storage_dir=str(tmp_path / "storage"),
        hint_competencia="2026-06",
    )

    assert falhas == []
    ciclo = result[0]
    assert ciclo.competencia == "2026-05"
    assert ciclo.comprovante_pix_path is not None
    assert ciclo.status_ciclo == StatusCiclo.PRONTO_PARA_ENVIO
    assert ciclo.valor_saldo_residual == Decimal("264.50")
    # No phantom cycle created for the hint month
    assert db_session.query(CicloCondominio).count() == 1


def test_lote_fatura_sem_ciclo_anterior_reporta_falha(db_session: Session, tmp_path: Path, monkeypatch):
    """A rental bill uploaded with no condo bill (in batch or previous month) is
    reported as a failure and creates NO cycle."""
    monkeypatch.setattr(
        email_worker,
        "parse_aluguel_pdf",
        lambda content, password="04293": ParsedAluguelBill(
            competencia="2026-06",
            contrato="09638.003.03",
            data_vencimento=date(2026, 6, 10),
            valor_total_aluguel=Decimal("2741.14"),
            valor_total_descontos=Decimal("264.50"),
            itens_desconto=[],
        ),
    )

    result, falhas = email_worker.sync_retroativo_lote(
        db_session, [_rental_doc()], storage_dir=str(tmp_path / "storage")
    )

    assert result == []
    assert len(falhas) == 1
    assert "sem ciclo" in falhas[0]["erro"]
    assert db_session.query(CicloCondominio).count() == 0


def test_lote_boleto_quebrado_nao_derruba_lote(db_session: Session, tmp_path: Path, monkeypatch):
    """A condo bill that fails to parse is reported in falhas; the rental bill
    and PIX of the same batch are still processed against a previous cycle."""
    monkeypatch.setattr(
        email_worker,
        "parse_condo_pdf",
        lambda content: (_ for _ in ()).throw(ValueError("Unable to parse condo bill: data_vencimento not found")),
    )
    ciclo_existente = CicloCondominio(
        competencia="2026-05",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 6, 10),
        valor_total=Decimal("1154.31"),
        valor_ressarcimento=Decimal("264.50"),
        valor_saldo_residual=Decimal("264.50"),
        boleto_pdf_path="/data/storage/condo_mai.pdf",
        comprovante_pix_path="/data/storage/pix_mai.pdf",
        status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
    )
    db_session.add(ciclo_existente)
    db_session.commit()

    monkeypatch.setattr(
        email_worker,
        "parse_aluguel_pdf",
        lambda content, password="04293": ParsedAluguelBill(
            competencia="2026-06",
            contrato="09638.003.03",
            data_vencimento=date(2026, 6, 10),
            valor_total_aluguel=Decimal("2741.14"),
            valor_total_descontos=Decimal("264.50"),
            itens_desconto=[],
        ),
    )

    result, falhas = email_worker.sync_retroativo_lote(
        db_session,
        [IngestedDocument(
            doc_type=DocumentType.CONDO_BILL,
            filename="Boleto_quebrado.pdf",
            content=b"%PDF-1.4 broken",
            content_type="application/pdf",
        ), _rental_doc()],
        storage_dir=str(tmp_path / "storage"),
    )

    assert len(falhas) == 1
    assert falhas[0]["arquivo"] == "Boleto_quebrado.pdf"
    # The existing previous-month cycle still got the conferencia applied
    ciclo = result[0]
    assert ciclo.competencia == "2026-05"
    assert ciclo.status_ciclo == StatusCiclo.CONCILIADO_SEM_PENDENCIA


def _fake_classify_por_nome(att, **kw):
    """Route-level helper: force classification by filename since synthetic
    bytes carry no parseable text (classification itself is covered by the
    dedicated classifier tests)."""
    name = (att.filename or "").lower()
    if "aluguel" in name or "ibagy" in name:
        return email_worker.DocumentType.RENTAL_BILL
    if "comprovante" in name or name.endswith((".png", ".jpg", ".jpeg")):
        return email_worker.DocumentType.PIX_RECEIPT
    return email_worker.DocumentType.CONDO_BILL


def test_rota_documentos_retroativo_tudo_ok(client: TestClient, db_session: Session, monkeypatch):
    """Route-level: upload of the full retro batch returns the comparison and
    the TUDO_OK verdict."""
    monkeypatch.setattr(email_worker, "classify_attachment", _fake_classify_por_nome)
    monkeypatch.setattr(
        email_worker, "parse_condo_pdf", lambda content: _fake_parsed_bill()
    )
    monkeypatch.setattr(
        email_worker,
        "parse_aluguel_pdf",
        lambda content, password="04293": ParsedAluguelBill(
            competencia="2026-06",
            contrato="09638.003.03",
            data_vencimento=date(2026, 6, 10),
            valor_total_aluguel=Decimal("2741.14"),
            valor_total_descontos=Decimal("264.50"),
            itens_desconto=[],
        ),
    )

    response = client.post(
        "/api/ciclos/documentos",
        files=[
            ("files", ("Boleto_Ref_052026.pdf", b"%PDF-1.4 condo", "application/pdf")),
            ("files", ("Boleto_Aluguel_2026_06.pdf", b"%PDF-1.4 rental", "application/pdf")),
            ("files", ("Comprovante_PIX.png", b"\x89PNG fake", "image/png")),
        ],
        data={"competencia": "2026-05"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["falhas"] == []
    assert len(body["ciclos_afetados"]) == 1
    ciclo = body["ciclos_afetados"][0]
    assert ciclo["competencia"] == "2026-05"
    assert ciclo["veredito"] == "TUDO_OK"
    assert ciclo["status_ciclo"] == "CONCILIADO_SEM_PENDENCIA"
    assert Decimal(ciclo["diferenca"]) == Decimal("0.00")


def test_rota_documentos_retroativo_diferenca(client: TestClient, db_session: Session, monkeypatch):
    """Route-level: partial discount returns SUGERIR_ENVIO with the difference."""
    monkeypatch.setattr(email_worker, "classify_attachment", _fake_classify_por_nome)
    monkeypatch.setattr(
        email_worker, "parse_condo_pdf", lambda content: _fake_parsed_bill()
    )
    monkeypatch.setattr(
        email_worker,
        "parse_aluguel_pdf",
        lambda content, password="04293": ParsedAluguelBill(
            competencia="2026-06",
            contrato="09638.003.03",
            data_vencimento=date(2026, 6, 10),
            valor_total_aluguel=Decimal("2741.14"),
            valor_total_descontos=Decimal("100.00"),
            itens_desconto=[],
        ),
    )

    response = client.post(
        "/api/ciclos/documentos",
        files=[
            ("files", ("Boleto_Ref_052026.pdf", b"%PDF-1.4 condo", "application/pdf")),
            ("files", ("Boleto_Aluguel_2026_06.pdf", b"%PDF-1.4 rental", "application/pdf")),
            ("files", ("Comprovante_PIX.png", b"\x89PNG fake", "image/png")),
        ],
        data={"competencia": "2026-05"},
    )

    assert response.status_code == 200
    body = response.json()
    ciclo = body["ciclos_afetados"][0]
    assert ciclo["veredito"] == "SUGERIR_ENVIO"
    assert ciclo["status_ciclo"] == "PRONTO_PARA_ENVIO"
    assert Decimal(ciclo["valor_ressarcimento"]) == Decimal("264.50")
    assert Decimal(ciclo["valor_desconto_aluguel"]) == Decimal("100.00")
    assert Decimal(ciclo["diferenca"]) == Decimal("164.50")
