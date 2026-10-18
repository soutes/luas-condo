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
