"""
Tests for production cycle seed script.
No emojis used.
"""

import sys
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import Base
from app.models.entities import CicloCondominio, ResponsabilidadeItem, StatusCiclo
from app.seed import seed_production_cycle


@pytest.fixture
def test_db_session(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session, tmp_path
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_seed_production_cycle(test_db_session):
    session, storage_dir = test_db_session
    ciclo = seed_production_cycle(db=session, storage_dir=str(storage_dir), reset_existing=True)

    assert ciclo is not None
    assert ciclo.competencia == "2026-09"
    assert ciclo.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert ciclo.valor_total == Decimal("1154.31")
    assert ciclo.valor_ressarcimento == Decimal("354.50")
    assert ciclo.status_ciclo == StatusCiclo.PRONTO_PARA_ENVIO
    assert len(ciclo.itens) == 12

    # Verify breakdown
    locador_itens = [it for it in ciclo.itens if it.responsabilidade == ResponsabilidadeItem.LOCADOR]
    locatario_itens = [it for it in ciclo.itens if it.responsabilidade == ResponsabilidadeItem.LOCATARIO]

    locador_sum = sum(it.valor_unidade for it in locador_itens)
    locatario_sum = sum(it.valor_unidade for it in locatario_itens)

    assert locador_sum == Decimal("354.50")
    assert locatario_sum == Decimal("799.81")
    assert locador_sum + locatario_sum == Decimal("1154.31")
