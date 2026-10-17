"""
Unit tests for deterministic PDF and text parser for Syndkos condo bills.
No emojis used.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import MagicMock
import pytest

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.models.entities import CategoriaItem
from app.services.parser_boleto import (
    ParsedCondoBill,
    ParsedItemRateio,
    decrypt_pdf_bytes,
    extract_pdf_text,
    parse_condo_pdf,
    parse_condo_text,
)

try:
    from tests.fixtures.sample_syndkos_text import (
        VILLA_SALOMY_INVALID_MATH_TEXT,
        VILLA_SALOMY_OCR_TEXT,
        VILLA_SALOMY_TEXT_PAGE1,
    )
except (ImportError, ModuleNotFoundError):
    from fixtures.sample_syndkos_text import (
        VILLA_SALOMY_INVALID_MATH_TEXT,
        VILLA_SALOMY_OCR_TEXT,
        VILLA_SALOMY_TEXT_PAGE1,
    )


def test_parse_syndkos_villa_salomy():
    """Verify deterministic extraction from standard Villa Salomy reference text."""
    result = parse_condo_text(VILLA_SALOMY_TEXT_PAGE1)

    assert isinstance(result, ParsedCondoBill)
    assert result.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert result.competencia == "2026-09"
    assert result.data_vencimento == date(2026, 10, 10)
    assert result.valor_total == Decimal("1154.31")
    assert result.valor_ordinarias == Decimal("596.27")
    assert result.valor_extraordinarias == Decimal("294.87")
    assert result.valor_fundos == Decimal("59.63")
    assert result.valor_leituras == Decimal("203.54")
    assert (
        result.linha_digitavel
        == "13691.10802 00102.557006 00000.514034 2 15950000115431"
    )

    # Key extraordinarias items
    fachada = next(
        i
        for i in result.itens
        if "Rateio Manutenção Fachada Parc 6/10" in i.descricao
    )
    assert fachada.valor_unidade == Decimal("208.29")
    assert fachada.valor_total_condominio == Decimal("4998.96")
    assert fachada.categoria == CategoriaItem.EXTRAORDINARIA

    seguro = next(
        i
        for i in result.itens
        if "Seguro Obrigatório Predial Parc 2/6" in i.descricao
    )
    assert seguro.valor_unidade == Decimal("18.44")
    assert seguro.valor_total_condominio == Decimal("442.56")
    assert seguro.categoria == CategoriaItem.EXTRAORDINARIA

    tarifa = next(i for i in result.itens if "Tarifa Bancária" in i.descricao)
    assert tarifa.valor_unidade == Decimal("2.29")
    assert tarifa.valor_total_condominio == Decimal("54.96")
    assert tarifa.categoria == CategoriaItem.EXTRAORDINARIA

    laudo = next(
        i for i in result.itens if "Laudo Bombeiro Parc 2/3" in i.descricao
    )
    assert laudo.valor_unidade == Decimal("10.96")
    assert laudo.categoria == CategoriaItem.EXTRAORDINARIA

    fiscalizacao = next(
        i
        for i in result.itens
        if "Rateio fiscalização obra da fachada" in i.descricao
    )
    assert fiscalizacao.valor_unidade == Decimal("54.89")
    assert fiscalizacao.categoria == CategoriaItem.EXTRAORDINARIA

    # Fundos item
    fundo = next(
        i for i in result.itens if "Fundo de Reserva" in i.descricao
    )
    assert fundo.valor_unidade == Decimal("59.63")
    assert fundo.categoria == CategoriaItem.FUNDOS

    # Leituras items
    gas = next(i for i in result.itens if "GÁS" in i.descricao.upper())
    assert gas.valor_unidade == Decimal("62.21")
    assert gas.categoria == CategoriaItem.LEITURA

    agua = next(i for i in result.itens if "ÁGUA" in i.descricao.upper())
    assert agua.valor_unidade == Decimal("141.33")
    assert agua.categoria == CategoriaItem.LEITURA


def test_parse_syndkos_ocr_text_variant():
    """Verify parser works with OCR text variant lacking accents or with slight whitespace differences."""
    result = parse_condo_text(VILLA_SALOMY_OCR_TEXT)

    assert result.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert result.competencia == "2026-09"
    assert result.data_vencimento == date(2026, 10, 10)
    assert result.valor_total == Decimal("1154.31")
    assert result.valor_ordinarias == Decimal("596.27")
    assert result.valor_extraordinarias == Decimal("294.87")
    assert result.valor_fundos == Decimal("59.63")
    assert result.valor_leituras == Decimal("203.54")
    assert (
        result.linha_digitavel
        == "13691.10802 00102.557006 00000.514034 2 15950000115431"
    )

    fachada = next(
        i for i in result.itens if "Rateio Manutencao Fachada" in i.descricao
    )
    assert fachada.valor_unidade == Decimal("208.29")
    assert fachada.categoria == CategoriaItem.EXTRAORDINARIA


def test_mathematical_integrity_failure_raises_value_error():
    """Verify that tampering with totals triggers a mathematical integrity ValueError."""
    with pytest.raises(ValueError, match="Mathematical integrity check failed"):
        parse_condo_text(VILLA_SALOMY_INVALID_MATH_TEXT)


def test_parse_condo_pdf_extracts_and_parses(monkeypatch):
    """Verify parse_condo_pdf extracts text pages via pdfplumber and delegates to parser."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = VILLA_SALOMY_TEXT_PAGE1

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf
    mock_pdf.__exit__.return_value = False

    monkeypatch.setattr("pdfplumber.open", lambda *args, **kwargs: mock_pdf)

    result = parse_condo_pdf("fake_path_to_bill.pdf")
    assert result.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert result.valor_total == Decimal("1154.31")
    assert len(result.itens) > 0


def test_parse_empty_text_raises_value_error():
    """Verify empty or non-rateio text raises descriptive ValueError."""
    with pytest.raises(ValueError, match="Unable to parse condo bill"):
        parse_condo_text("")


def test_parse_condo_pdf_with_bytes(monkeypatch):
    """Verify parse_condo_pdf handles raw bytes input via BytesIO."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = VILLA_SALOMY_TEXT_PAGE1

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf
    mock_pdf.__exit__.return_value = False

    monkeypatch.setattr("pdfplumber.open", lambda *args, **kwargs: mock_pdf)

    result = parse_condo_pdf(b"%PDF-1.4 fake content")
    assert result.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert result.valor_total == Decimal("1154.31")


def test_missing_data_vencimento_raises_value_error():
    """Verify missing due date raises ValueError."""
    text_without_venc = VILLA_SALOMY_TEXT_PAGE1.replace("VENCIMENTO: 10/10/2026", "")
    with pytest.raises(ValueError, match="data_vencimento not found"):
        parse_condo_text(text_without_venc)


def test_missing_valor_total_raises_value_error():
    """Verify missing total raises ValueError."""
    text_without_total = VILLA_SALOMY_TEXT_PAGE1.replace("VALOR TOTAL: 1.154,31", "")
    with pytest.raises(ValueError, match="valor_total not found"):
        parse_condo_text(text_without_total)


def test_parse_condo_pdf_with_password():
    """Verify parse_condo_pdf decrypts password-protected PDF with password 04293."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), VILLA_SALOMY_TEXT_PAGE1)
    enc_bytes = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="04293",
        owner_pw="04293",
    )
    doc.close()

    # Should succeed with default password fallback 04293
    result = parse_condo_pdf(enc_bytes)
    assert result.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert result.valor_total == Decimal("1154.31")

    # Should also succeed when explicitly passing password
    result_explicit = parse_condo_pdf(enc_bytes, password="04293")
    assert result_explicit.valor_total == Decimal("1154.31")


def test_parse_condo_pdf_wrong_password_raises():
    """Verify parse_condo_pdf raises when an invalid password is provided for encrypted PDF."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), VILLA_SALOMY_TEXT_PAGE1)
    enc_bytes = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="04293",
        owner_pw="04293",
    )
    doc.close()

    with pytest.raises(Exception):
        parse_condo_pdf(enc_bytes, password="wrong_password_99999")


def test_decrypt_pdf_bytes_helper():
    """Verify decrypt_pdf_bytes produces an unencrypted PDF stream from encrypted input."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Sample condo content")
    enc_bytes = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="04293",
        owner_pw="04293",
    )
    doc.close()

    decrypted = decrypt_pdf_bytes(enc_bytes, password="04293")
    check_doc = fitz.open(stream=decrypted, filetype="pdf")
    assert check_doc.is_encrypted is False
    assert "Sample condo content" in check_doc[0].get_text()
    check_doc.close()

