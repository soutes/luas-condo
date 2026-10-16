"""
Unit tests for legal audit engine for condo expenses segregation (Lei do Inquilinato).
No emojis used.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import pytest

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.models.entities import CategoriaItem, ResponsabilidadeItem
from app.schemas.condo import ParsedCondoBill, ParsedItemRateio
from app.services.parser_boleto import parse_condo_text

try:
    from tests.fixtures.sample_syndkos_text import VILLA_SALOMY_TEXT_PAGE1
except (ImportError, ModuleNotFoundError):
    from fixtures.sample_syndkos_text import VILLA_SALOMY_TEXT_PAGE1

# Import the engine to test
from app.services.audit_engine import (
    AuditReport,
    ItemAuditado,
    audit_condo_bill,
)


def test_audit_reference_bill_villa_salomy():
    """
    Verify complete legal audit on the standard Villa Salomy reference bill (09/2026).
    Total: 1154.31
    Locatario: 799.81 (Ordinarias 596.27 + Leituras 203.54)
    Locador / Reimbursement: 354.50 (Extraordinarias 294.87 + Fundos 59.63)
    """
    parsed_bill = parse_condo_text(VILLA_SALOMY_TEXT_PAGE1)
    report = audit_condo_bill(parsed_bill)

    assert isinstance(report, AuditReport)
    assert report.competencia == "2026-09"
    assert report.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert report.data_vencimento == date(2026, 10, 10)
    assert report.valor_total_boleto == Decimal("1154.31")
    assert report.valor_locatario == Decimal("799.81")
    assert report.valor_locador == Decimal("354.50")
    assert report.total_reimbursement == Decimal("354.50")
    assert report.revisao_necessaria is False

    # Check landlord items
    itens_locador = [
        item for item in report.itens_auditados
        if item.responsabilidade == ResponsabilidadeItem.LOCADOR
    ]
    assert len(itens_locador) == 6

    # Verify each specific landlord item
    locador_by_desc = {item.descricao: item for item in itens_locador}

    assert "Fundo de Reserva 10,00%" in locador_by_desc
    item_fr = locador_by_desc["Fundo de Reserva 10,00%"]
    assert item_fr.valor == Decimal("59.63")
    assert item_fr.categoria == CategoriaItem.FUNDOS
    assert "Art. 22, X, g" in item_fr.justificativa_legal

    assert "Rateio Manutenção Fachada Parc 6/10" in locador_by_desc
    item_fachada = locador_by_desc["Rateio Manutenção Fachada Parc 6/10"]
    assert item_fachada.valor == Decimal("208.29")
    assert item_fachada.categoria == CategoriaItem.EXTRAORDINARIA
    assert "Art. 22, X, a" in item_fachada.justificativa_legal

    assert "Rateio fiscalização obra da fachada" in locador_by_desc
    item_fisc = locador_by_desc["Rateio fiscalização obra da fachada"]
    assert item_fisc.valor == Decimal("54.89")
    assert item_fisc.categoria == CategoriaItem.EXTRAORDINARIA
    assert "Art. 22, X, a" in item_fisc.justificativa_legal

    assert "Laudo Bombeiro Parc 2/3" in locador_by_desc
    item_bombeiro = locador_by_desc["Laudo Bombeiro Parc 2/3"]
    assert item_bombeiro.valor == Decimal("10.96")
    assert item_bombeiro.categoria == CategoriaItem.EXTRAORDINARIA
    assert "Art. 22, X" in item_bombeiro.justificativa_legal

    assert "Seguro Obrigatório Predial Parc 2/6" in locador_by_desc
    item_seguro = locador_by_desc["Seguro Obrigatório Predial Parc 2/6"]
    assert item_seguro.valor == Decimal("18.44")
    assert item_seguro.categoria == CategoriaItem.EXTRAORDINARIA
    assert "Art. 22, X" in item_seguro.justificativa_legal

    assert "Tarifa Bancária" in locador_by_desc
    item_tarifa = locador_by_desc["Tarifa Bancária"]
    assert item_tarifa.valor == Decimal("2.29")
    assert item_tarifa.categoria == CategoriaItem.EXTRAORDINARIA
    assert "Art. 22, X" in item_tarifa.justificativa_legal

    # Check tenant items
    itens_locatario = [
        item for item in report.itens_auditados
        if item.responsabilidade == ResponsabilidadeItem.LOCATARIO
    ]
    assert len(itens_locatario) == 6
    soma_locatario = sum(item.valor for item in itens_locatario)
    assert soma_locatario == Decimal("799.81")

    # Check formatted observations for Ibagy
    obs = report.formatted_observations
    assert "Art. 22 da Lei 8.245/91" in obs
    assert "R$ 354,50" in obs
    assert "Fundo de Reserva 10,00%" in obs
    assert "Rateio Manutenção Fachada Parc 6/10" in obs
    assert "anexo" in obs.lower()
    assert "boleto" in obs.lower()
    assert "comprovante" in obs.lower()


def test_audit_flags_unknown_or_ambiguous_item():
    """Verify revisao_necessaria flag when bill contains unknown / ambiguous item."""
    bill = ParsedCondoBill(
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        competencia="2026-09",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("200.00"),
        valor_ordinarias=Decimal("100.00"),
        valor_extraordinarias=Decimal("100.00"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        itens=[
            ParsedItemRateio(
                descricao="Limpeza",
                valor_unidade=Decimal("100.00"),
                categoria=CategoriaItem.ORDINARIA,
            ),
            ParsedItemRateio(
                descricao="Despesas Diversas Indeterminadas",
                valor_unidade=Decimal("100.00"),
                categoria=CategoriaItem.EXTRAORDINARIA,
            ),
        ],
    )
    report = audit_condo_bill(bill)
    assert report.revisao_necessaria is True


def test_audit_flags_category_mismatch():
    """Verify revisao_necessaria flag when an ordinary item mentions extraordinary work."""
    bill = ParsedCondoBill(
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        competencia="2026-09",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("500.00"),
        valor_ordinarias=Decimal("500.00"),
        valor_extraordinarias=Decimal("0.00"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        itens=[
            ParsedItemRateio(
                descricao="Reforma Estrutural da Fachada",
                valor_unidade=Decimal("500.00"),
                categoria=CategoriaItem.ORDINARIA,
            ),
        ],
    )
    report = audit_condo_bill(bill)
    assert report.revisao_necessaria is True


def test_audit_flags_math_discrepancy():
    """Verify revisao_necessaria flag when sum of items doesn't match total."""
    bill = ParsedCondoBill(
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        competencia="2026-09",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("300.00"),
        valor_ordinarias=Decimal("100.00"),
        valor_extraordinarias=Decimal("0.00"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        itens=[
            ParsedItemRateio(
                descricao="Limpeza e Portaria",
                valor_unidade=Decimal("100.00"),
                categoria=CategoriaItem.ORDINARIA,
            ),
        ],
    )
    report = audit_condo_bill(bill)
    assert report.revisao_necessaria is True


def test_audit_zero_reimbursement():
    """Verify report when there are only ordinary expenses."""
    bill = ParsedCondoBill(
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        competencia="2026-09",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("100.00"),
        valor_ordinarias=Decimal("100.00"),
        valor_extraordinarias=Decimal("0.00"),
        valor_fundos=Decimal("0.00"),
        valor_leituras=Decimal("0.00"),
        itens=[
            ParsedItemRateio(
                descricao="Limpeza e Portaria",
                valor_unidade=Decimal("100.00"),
                categoria=CategoriaItem.ORDINARIA,
            ),
        ],
    )
    report = audit_condo_bill(bill)
    assert report.total_reimbursement == Decimal("0.00")
    assert report.valor_locador == Decimal("0.00")
    assert report.valor_locatario == Decimal("100.00")
    assert report.revisao_necessaria is False
    assert "Não foram identificadas despesas" in report.formatted_observations


def test_format_currency_brl():
    """Verify Brazilian Real currency formatting."""
    from app.services.audit_engine import format_currency_brl

    assert format_currency_brl(Decimal("0.00")) == "R$ 0,00"
    assert format_currency_brl(Decimal("2.29")) == "R$ 2,29"
    assert format_currency_brl(Decimal("354.50")) == "R$ 354,50"
    assert format_currency_brl(Decimal("1154.31")) == "R$ 1.154,31"
    assert format_currency_brl(Decimal("10450.90")) == "R$ 10.450,90"


def test_classify_rateio_item_subrules():
    """Verify classification subrules for different categories and descriptions."""
    from app.services.audit_engine import classify_rateio_item

    # Pintura de fachada
    resp, just, rev = classify_rateio_item(
        ParsedItemRateio(
            descricao="Pintura externa e empenas",
            valor_unidade=Decimal("100.00"),
            categoria=CategoriaItem.EXTRAORDINARIA,
        )
    )
    assert resp == ResponsabilidadeItem.LOCADOR
    assert "Art. 22, X, b" in just
    assert rev is False

    # AVCB / Incendio
    resp, just, rev = classify_rateio_item(
        ParsedItemRateio(
            descricao="Renovação AVCB e Extintores",
            valor_unidade=Decimal("50.00"),
            categoria=CategoriaItem.EXTRAORDINARIA,
        )
    )
    assert resp == ResponsabilidadeItem.LOCADOR
    assert "Art. 22, X" in just
    assert rev is False

    # Leitura individual de gas
    resp, just, rev = classify_rateio_item(
        ParsedItemRateio(
            descricao="Consumo individual de gas",
            valor_unidade=Decimal("45.00"),
            categoria=CategoriaItem.LEITURA,
        )
    )
    assert resp == ResponsabilidadeItem.LOCATARIO
    assert "Art. 23, VIII" in just
    assert rev is False


def test_item_auditado_property():
    """Verify ItemAuditado valor_unidade property matches valor."""
    item = ItemAuditado(
        descricao="Teste",
        valor=Decimal("123.45"),
        categoria=CategoriaItem.ORDINARIA,
        responsabilidade=ResponsabilidadeItem.LOCATARIO,
        justificativa_legal="Art. 23",
    )
    assert item.valor == Decimal("123.45")
    assert item.valor_unidade == Decimal("123.45")
