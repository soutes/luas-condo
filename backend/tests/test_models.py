import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import uuid
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import Base, get_db, init_db, parse_database_url
from app.models.entities import (
    CategoriaItem,
    CicloCondominio,
    IncidenteOnCall,
    ItemRateio,
    ResponsabilidadeItem,
    StatusCiclo,
    StatusIncidente,
    StatusSubmissao,
    SubmissaoRessarcimento,
)
from app.schemas.condo import (
    CicloCondominioCreate,
    CicloCondominioResponse,
    IncidenteOnCallCreate,
    IncidenteOnCallResponse,
    ItemRateioCreate,
    ItemRateioResponse,
    SubmissaoRessarcimentoCreate,
    SubmissaoRessarcimentoResponse,
)


@pytest.fixture
def db_session():
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


def test_create_ciclo_and_items(db_session: Session):
    ciclo = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ordinarias=Decimal("596.27"),
        valor_extraordinarias=Decimal("294.87"),
        valor_fundos=Decimal("59.63"),
        valor_leituras=Decimal("203.54"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/data/boletos/2026-09.pdf",
        comprovante_pix_path="/data/comprovantes/pix-2026-09.pdf",
        status_ciclo=StatusCiclo.PENDENTE_COMPROVANTE,
    )
    db_session.add(ciclo)
    db_session.flush()

    assert ciclo.id is not None
    assert isinstance(ciclo.id, uuid.UUID)

    item1 = ItemRateio(
        ciclo_id=ciclo.id,
        categoria=CategoriaItem.ORDINARIA,
        descricao="DESPESAS ORDINARIAS",
        valor_unidade=Decimal("596.27"),
        valor_total_condominio=Decimal("15000.00"),
        responsabilidade=ResponsabilidadeItem.LOCATARIO,
        justificativa_legal="Art. 23 da Lei do Inquilinato",
    )
    item2 = ItemRateio(
        ciclo_id=ciclo.id,
        categoria=CategoriaItem.EXTRAORDINARIA,
        descricao="FUNDO DE OBRAS",
        valor_unidade=Decimal("294.87"),
        valor_total_condominio=Decimal("7000.00"),
        responsabilidade=ResponsabilidadeItem.LOCADOR,
        justificativa_legal="Art. 22 da Lei do Inquilinato",
    )
    db_session.add_all([item1, item2])
    db_session.commit()

    saved_ciclo = db_session.get(CicloCondominio, ciclo.id)
    assert saved_ciclo is not None
    assert len(saved_ciclo.itens) == 2
    assert saved_ciclo.itens[0].descricao == "DESPESAS ORDINARIAS"


def test_cascade_delete_ciclo(db_session: Session):
    ciclo = CicloCondominio(
        competencia="2026-08",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 9, 10),
        valor_total=Decimal("1000.00"),
        valor_ordinarias=Decimal("600.00"),
        valor_extraordinarias=Decimal("400.00"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        valor_ressarcimento=Decimal("400.00"),
        boleto_pdf_path="/data/boletos/2026-08.pdf",
        status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
    )
    db_session.add(ciclo)
    db_session.flush()

    item = ItemRateio(
        ciclo_id=ciclo.id,
        categoria=CategoriaItem.EXTRAORDINARIA,
        descricao="REFORMA FACHADA",
        valor_unidade=Decimal("400.00"),
        valor_total_condominio=Decimal("10000.00"),
        responsabilidade=ResponsabilidadeItem.LOCADOR,
        justificativa_legal="Benfeitoria estrutural",
    )
    db_session.add(item)
    db_session.commit()

    item_id = item.id
    db_session.delete(ciclo)
    db_session.commit()

    deleted_item = db_session.get(ItemRateio, item_id)
    assert deleted_item is None


def test_cascade_delete_ciclo_with_submissao(db_session: Session):
    ciclo = CicloCondominio(
        competencia="2026-06",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 7, 10),
        valor_total=Decimal("800.00"),
        valor_ordinarias=Decimal("500.00"),
        valor_extraordinarias=Decimal("300.00"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        valor_ressarcimento=Decimal("300.00"),
        boleto_pdf_path="/data/boletos/2026-06.pdf",
        status_ciclo=StatusCiclo.ENVIADO,
    )
    db_session.add(ciclo)
    db_session.flush()

    submissao = SubmissaoRessarcimento(
        ciclo_id=ciclo.id,
        contrato_numero="09638.003.03",
        payload_enviado={"test": 123},
        status=StatusSubmissao.SUCESSO,
        protocolo_retorno="PROT-999",
        tentativas=1,
        trace_id="trace-cascade",
    )
    db_session.add(submissao)
    db_session.commit()

    submissao_id = submissao.id
    db_session.delete(ciclo)
    db_session.commit()

    deleted_submissao = db_session.get(SubmissaoRessarcimento, submissao_id)
    assert deleted_submissao is None


def test_submissao_ressarcimento_model(db_session: Session):
    ciclo = CicloCondominio(
        competencia="2026-07",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 8, 10),
        valor_total=Decimal("1200.00"),
        valor_ordinarias=Decimal("700.00"),
        valor_extraordinarias=Decimal("500.00"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        valor_ressarcimento=Decimal("500.00"),
        boleto_pdf_path="/data/boletos/2026-07.pdf",
        status_ciclo=StatusCiclo.ENVIADO,
    )
    db_session.add(ciclo)
    db_session.flush()

    payload = {
        "tenant_name": "Luiz Augusto Soutes",
        "contract": "09638.003.03",
        "items": [
            {"desc": "Fundo Reserva", "amount": 50.0},
            {"desc": "Reforma", "amount": 450.0},
        ],
    }

    submissao = SubmissaoRessarcimento(
        ciclo_id=ciclo.id,
        contrato_numero="09638.003.03",
        payload_enviado=payload,
        status=StatusSubmissao.SUCESSO,
        protocolo_retorno="PROT-2026-00123",
        screenshot_path="/data/screenshots/submissao-2026-07.png",
        tentativas=1,
        trace_id="trace-abc-123",
    )
    db_session.add(submissao)
    db_session.commit()

    saved = db_session.get(SubmissaoRessarcimento, submissao.id)
    assert saved is not None
    assert saved.contrato_numero == "09638.003.03"
    assert saved.status == StatusSubmissao.SUCESSO
    assert saved.payload_enviado["tenant_name"] == "Luiz Augusto Soutes"
    assert saved.tentativas == 1
    assert saved.protocolo_retorno == "PROT-2026-00123"


def test_incidente_on_call_model(db_session: Session):
    incidente = IncidenteOnCall(
        trace_id="trace-xyz-789",
        alerta_nome="CondoSubmissionFailed",
        diagnostico="Bitrix selector #submit-btn not found",
        acao_executada="Retried with fallback selector and dispatched notification",
        status=StatusIncidente.RESOLVIDO,
    )
    db_session.add(incidente)
    db_session.commit()

    saved = db_session.get(IncidenteOnCall, incidente.id)
    assert saved is not None
    assert saved.alerta_nome == "CondoSubmissionFailed"
    assert saved.status == StatusIncidente.RESOLVIDO
    assert saved.criado_em is not None


def test_pydantic_schemas_serialization():
    ciclo_id = uuid.uuid4()
    item_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    item_create = ItemRateioCreate(
        categoria=CategoriaItem.EXTRAORDINARIA,
        descricao="REFORMA ELEVADOR",
        valor_unidade=Decimal("250.00"),
        valor_total_condominio=Decimal("5000.00"),
        responsabilidade=ResponsabilidadeItem.LOCADOR,
        justificativa_legal="Art. 22 Lei 8245/91",
    )
    assert item_create.valor_unidade == Decimal("250.00")

    item_resp = ItemRateioResponse(
        id=item_id,
        ciclo_id=ciclo_id,
        categoria=CategoriaItem.EXTRAORDINARIA,
        descricao="REFORMA ELEVADOR",
        valor_unidade=Decimal("250.00"),
        valor_total_condominio=Decimal("5000.00"),
        responsabilidade=ResponsabilidadeItem.LOCADOR,
        justificativa_legal="Art. 22 Lei 8245/91",
    )
    assert item_resp.id == item_id

    ciclo_create = CicloCondominioCreate(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ordinarias=Decimal("596.27"),
        valor_extraordinarias=Decimal("294.87"),
        valor_fundos=Decimal("59.63"),
        valor_leituras=Decimal("203.54"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/data/boletos/2026-09.pdf",
    )
    assert ciclo_create.competencia == "2026-09"

    ciclo_resp = CicloCondominioResponse(
        id=ciclo_id,
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ordinarias=Decimal("596.27"),
        valor_extraordinarias=Decimal("294.87"),
        valor_fundos=Decimal("59.63"),
        valor_leituras=Decimal("203.54"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/data/boletos/2026-09.pdf",
        comprovante_pix_path=None,
        status_ciclo=StatusCiclo.PENDENTE_COMPROVANTE,
        criado_em=now,
        itens=[item_resp],
    )
    assert len(ciclo_resp.itens) == 1
    assert ciclo_resp.status_ciclo == StatusCiclo.PENDENTE_COMPROVANTE

    submissao_resp = SubmissaoRessarcimentoResponse(
        id=uuid.uuid4(),
        ciclo_id=ciclo_id,
        contrato_numero="09638.003.03",
        payload_enviado={"status": "ok"},
        status=StatusSubmissao.SUCESSO,
        protocolo_retorno="PROT-123",
        screenshot_path=None,
        tentativas=1,
        trace_id="trace-001",
        enviado_em=now,
    )
    assert submissao_resp.status == StatusSubmissao.SUCESSO

    incidente_resp = IncidenteOnCallResponse(
        id=uuid.uuid4(),
        trace_id="trace-999",
        alerta_nome="SlaWarning",
        diagnostico="SLA under 3 days",
        acao_executada="Sent alert",
        status=StatusIncidente.ESCALADO_HUMANO,
        criado_em=now,
    )
    assert incidente_resp.status == StatusIncidente.ESCALADO_HUMANO


def test_pydantic_from_orm_entity(db_session: Session):
    ciclo = CicloCondominio(
        competencia="2026-10",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 11, 10),
        valor_total=Decimal("1500.00"),
        valor_ordinarias=Decimal("900.00"),
        valor_extraordinarias=Decimal("600.00"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        valor_ressarcimento=Decimal("600.00"),
        boleto_pdf_path="/data/boletos/2026-10.pdf",
        status_ciclo=StatusCiclo.PENDENTE_COMPROVANTE,
    )
    db_session.add(ciclo)
    db_session.flush()

    item = ItemRateio(
        ciclo_id=ciclo.id,
        categoria=CategoriaItem.EXTRAORDINARIA,
        descricao="OBRA PORTARIA",
        valor_unidade=Decimal("600.00"),
        responsabilidade=ResponsabilidadeItem.LOCADOR,
    )
    db_session.add(item)
    db_session.commit()

    saved_ciclo = db_session.get(CicloCondominio, ciclo.id)
    resp = CicloCondominioResponse.model_validate(saved_ciclo)
    assert resp.id == ciclo.id
    assert resp.competencia == "2026-10"
    assert len(resp.itens) == 1
    assert resp.itens[0].descricao == "OBRA PORTARIA"
    assert resp.itens[0].valor_unidade == Decimal("600.00")


def test_schema_validation_error():
    with pytest.raises(ValidationError):
        ItemRateioCreate(
            categoria="INVALID_CATEGORY",
            descricao="TEST",
            valor_unidade=Decimal("100.00"),
            responsabilidade=ResponsabilidadeItem.LOCATARIO,
        )


def test_database_init_db_and_get_db():
    init_db()
    gen = get_db()
    db = next(gen)
    assert isinstance(db, Session)
    try:
        next(gen)
    except StopIteration:
        pass
    from app.core.database import engine
    engine.dispose()
    default_db = Path("condo.db")
    if default_db.exists():
        default_db.unlink()


def test_parse_database_url_scenarios(monkeypatch):
    from sqlalchemy import URL
    from sqlalchemy.engine import make_url

    # Case 1: default fallback to SQLite
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url_default = parse_database_url()
    assert str(url_default) == "sqlite:///./condo.db"

    # Case 2: password containing @ symbol in DATABASE_URL
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://postgres:@luascondo@db:5432/luas_condo")
    url_at = parse_database_url()
    assert isinstance(url_at, str)
    parsed = make_url(url_at)
    assert parsed.host == "db"
    assert parsed.username == "postgres"
    assert parsed.password == "@luascondo"

    # Case 3: discrete POSTGRES_HOST takes precedence and encodes special characters safely
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_USER", "luas_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "complex@pass#2026")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "luas_condo")
    url_discrete = parse_database_url()
    assert isinstance(url_discrete, URL)
    assert url_discrete.host == "db"
    assert url_discrete.username == "luas_user"
    assert url_discrete.password == "complex@pass#2026"
    assert url_discrete.database == "luas_condo"



