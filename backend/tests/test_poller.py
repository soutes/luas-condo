"""
Tests for background email poller service and daily schedule window (07-12).
No emojis used.
"""

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient
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
from app.models.entities import CicloCondominio, StatusCiclo
from app.services.email_worker import DocumentType, IngestedDocument
from app.services.poller import (
    execute_email_sync,
    is_active_polling_window,
    start_poller,
    stop_poller,
)


@pytest.fixture
def db_session():
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


def test_is_active_polling_window():
    assert is_active_polling_window(date(2026, 10, 6)) is False
    assert is_active_polling_window(date(2026, 10, 7)) is True
    assert is_active_polling_window(date(2026, 10, 10)) is True
    assert is_active_polling_window(date(2026, 10, 12)) is True
    assert is_active_polling_window(date(2026, 10, 13)) is False


def test_execute_email_sync_skipped_when_credentials_missing(db_session: Session, monkeypatch):
    monkeypatch.delenv("IMAP_USER", raising=False)
    monkeypatch.delenv("IMAP_PASSWORD", raising=False)

    async def run():
        res = await execute_email_sync(db=db_session)
        assert res["status"] == "skipped"
        assert "not configured" in res["detail"]

    asyncio.run(run())


def test_api_trigger_email_sync(db_session: Session, monkeypatch):
    monkeypatch.delenv("IMAP_USER", raising=False)
    monkeypatch.delenv("IMAP_PASSWORD", raising=False)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        resp = client.post("/api/ciclos/sync-email")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "skipped"
    app.dependency_overrides.clear()


def test_start_and_stop_poller():
    async def run():
        task = start_poller(check_interval_seconds=3600)
        assert task is not None
        assert not task.done()
        stop_poller()
        await asyncio.sleep(0)
        assert task.cancelled() or task.done()

    asyncio.run(run())
