"""
Regression tests for the email sync poller (execute_email_sync).
Covers the empty-inbox path that touches ultima_verificacao timestamps.
Follows TDD methodology.
No emojis used.
"""

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

backend_dir = Path(__file__).resolve().parent.parent
root_dir = backend_dir.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import Base
from app.models.entities import CicloCondominio, StatusCiclo
from app.services import poller


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


def test_empty_inbox_sync_marks_pending_cycle_as_verified(db_session, monkeypatch):
    """With an empty inbox, pending cycles get their ultima_verificacao refreshed
    and the sync reports ok instead of an internal NameError."""
    ciclo = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/data/storage/villa_salomy_2026_09.pdf",
        comprovante_pix_path="/data/storage/comprovante_pix_2026_09.pdf",
        status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
    )
    db_session.add(ciclo)
    db_session.commit()

    monkeypatch.setattr(poller, "fetch_new_condo_emails", lambda **kwargs: [])

    res = asyncio.run(poller.execute_email_sync(db=db_session, imap_client=object()))

    assert res["status"] == "ok"
    assert res["synced_cycles"] == 0
    db_session.refresh(ciclo)
    assert ciclo.ultima_verificacao is not None


def test_sync_does_not_block_event_loop(db_session, monkeypatch):
    """A slow blocking IMAP fetch must not freeze the event loop (startup/API stay responsive)."""
    import time

    def slow_fetch(**kwargs):
        time.sleep(0.4)
        return []

    monkeypatch.setattr(poller, "fetch_new_condo_emails", slow_fetch)

    async def scenario():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.05)
                ticks += 1

        task = asyncio.create_task(ticker())
        await poller.execute_email_sync(db=db_session, imap_client=object())
        task.cancel()
        return ticks

    assert asyncio.run(scenario()) >= 4


def test_reprocessing_bill_keeps_enviado_status(db_session, monkeypatch):
    """Re-ingesting the boleto of an already submitted cycle must not reopen it."""
    from types import SimpleNamespace
    from app.services import email_worker

    ciclo = CicloCondominio(
        competencia="2026-10",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 11, 10),
        valor_total=Decimal("1219.23"),
        valor_ressarcimento=Decimal("358.09"),
        valor_saldo_residual=Decimal("358.09"),
        boleto_pdf_path="/data/storage/b.pdf",
        comprovante_pix_path="/data/storage/c.pdf",
        status_ciclo=StatusCiclo.ENVIADO,
        detalhes_verificacao="Enviado ao Ibagy.",
    )
    db_session.add(ciclo)
    db_session.commit()

    parsed = SimpleNamespace(
        competencia="2026-10",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 11, 10),
        valor_total=Decimal("1219.23"),
        valor_ordinarias=Decimal("632.13"),
        valor_extraordinarias=Decimal("294.88"),
        valor_fundos=Decimal("63.21"),
        valor_leituras=Decimal("229.01"),
        itens=[],
    )
    monkeypatch.setattr(email_worker, "decrypt_pdf_bytes", lambda b: b)
    monkeypatch.setattr(email_worker, "parse_condo_pdf", lambda b: parsed)
    monkeypatch.setattr(
        email_worker,
        "audit_condo_bill",
        lambda p: SimpleNamespace(total_reimbursement=Decimal("358.09"), itens_auditados=[]),
    )

    doc = email_worker.IngestedDocument(
        doc_type=email_worker.DocumentType.CONDO_BILL,
        filename="b.pdf",
        content=b"x",
    )
    import tempfile

    email_worker.sync_condo_cycle(db_session, [doc], storage_dir=tempfile.mkdtemp())
    db_session.refresh(ciclo)
    assert ciclo.status_ciclo == StatusCiclo.ENVIADO
    assert ciclo.detalhes_verificacao == "Enviado ao Ibagy."
