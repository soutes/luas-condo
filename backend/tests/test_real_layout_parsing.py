"""
Regression tests for the real-world Syndkos v26 bill layout (unit-first columns,
section headers sharing the line with column labels, summary grand total, bank
slip due date) and for bank payment receipt classification.

All fixtures use synthetic data in the real STRUCTURE - no real documents or
personal data are committed to the repository.
No emojis used.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import pytest

backend_dir = Path(__file__).resolve().parent.parent
root_dir = backend_dir.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.models.entities import CategoriaItem, ResponsabilidadeItem
from app.services import email_worker
from app.services.audit_engine import audit_condo_bill
from app.services.parser_boleto import parse_condo_text

# Synthetic fixture mirroring the real Syndkos v26 layout (unit-first columns,
# concatenated section headers, rateio summary, bank slip with due date).
# All values are fictional and mathematically consistent.
SYNDKOS_V26_TEXT = """CONDOMINIO EDIFICIO VILLA SALOMY
DEMONSTRATIVO DE RATEIO DE 01/03/2026 ATÉ 31/03/2026
Ordinárias Valor Unidade Total Comunicado: Prezados condôminos,
Portaria Remota ORSEGUPS 300,00 18.000,00
Honorários Contábeis 150,00 9.000,00
Material de Limpeza 50,00 3.000,00
Total: 500,00 30.000,00
Extraordinárias Valor Unidade Total
Seguro Obrigatório Predial Parc 5/12 200,00 12.000,00
Rateio Manutenção Fachada Parc 1/10 80,00 4.800,00
Tarifa Bancária 20,00 1.200,00
Total: 300,00 18.000,00
Anterior Atual Consumo Valor Taxa Total
LEITURA DE GAS m3 Data: 22/03/2026
850,100000 855,200000 5,100000 15,00 Mês 90,00
LEITURA DE AGUA m3 Data: 22/03/2026
1.200,000000 1.210,000000 10,000000 Mês 60,00
Fundos Valor Unidade
Fundo de Reserva 10,00% 49,99
Total: 49,99
Resumo de Rateio Valor Total
Ordinárias 500,00
Extraordinárias 300,00
Leituras 150,00
Fundos 49,99
Total: 999,99
136-8
Recibo do Pagador
Beneficiário CPF/CNPJ Beneficiário Agência/Código Beneficiário Vencimento
CONDOMINIO EDIFICIO VILLA SALOMY 08.957.162/0001-24 1108-8/000102557-0 10/04/2026
Rua Santos Saraiva, 144 Nosso Número N. do documento Data Documento
Capoeiras - Florianópolis - SC - 88070-101 0000004963-8 0000004963 24/03/2026
Pagador Valor Documento
LUIZ AUGUSTO SOUTES - CPF: 000.000.000-00 - Condominio - Apartamento 802 / G13 999,99
136-8
13691.10802 00102.557006 00000.496380 1 15030000099999
Local de pagamento Vencimento
Pagável preferencialmente nas agencias Unicred 10/04/2026
"""


def test_parse_real_layout_villa_salomy():
    """Real layout: due date from the bank slip, grand total from the summary,
    unit-first item columns, leitura rows with cleaned labels."""
    result = parse_condo_text(SYNDKOS_V26_TEXT)

    assert result.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert result.competencia == "2026-03"
    assert result.data_vencimento == date(2026, 4, 10)
    assert result.valor_total == Decimal("999.99")
    assert result.valor_ordinarias == Decimal("500.00")
    assert result.valor_extraordinarias == Decimal("300.00")
    assert result.valor_fundos == Decimal("49.99")
    assert result.valor_leituras == Decimal("150.00")
    assert result.linha_digitavel == "13691.10802 00102.557006 00000.496380 1 15030000099999"

    # Ordinary items: unit value first, condo total second (real column order)
    portaria = next(i for i in result.itens if "Portaria Remota" in i.descricao)
    assert portaria.valor_unidade == Decimal("300.00")
    assert portaria.valor_total_condominio == Decimal("18000.00")
    assert portaria.categoria == CategoriaItem.ORDINARIA

    # Extraordinary item with legal classification by the audit engine
    audit = audit_condo_bill(result)
    fachada = next(
        i for i in audit.itens_auditados if "Fachada" in i.descricao
    )
    assert fachada.responsabilidade == ResponsabilidadeItem.LOCADOR
    assert "Art. 22, X, a" in fachada.justificativa_legal

    # Leitura rows: clean labels instead of raw number rows
    gas = next(i for i in result.itens if "GAS" in i.descricao.upper())
    assert gas.valor_unidade == Decimal("90.00")
    assert gas.categoria == CategoriaItem.LEITURA
    agua = next(i for i in result.itens if "AGUA" in i.descricao.upper())
    assert agua.valor_unidade == Decimal("60.00")

    # Landlord reimbursement = extraordinary + fundos
    assert audit.total_reimbursement == Decimal("349.99")


def test_classify_bank_payment_receipt_by_text_signature(monkeypatch):
    """A bank payment receipt naming the condo as beneficiary must classify as
    PIX_RECEIPT (receipt signature checked before condo keywords)."""
    receipt_text = (
        "COMPROVANTE DE PAGAMENTO DE TITULOS\n"
        "VALOR PAGO\n"
        "R$ 999,99\n"
        "DATA DO PAGAMENTO\n"
        "10/04/2026\n"
        "AUTENTICACAO BANCARIA\n"
        "ABC123\n"
        "COND. EDIF. VILLA SALOMY"
    )
    monkeypatch.setattr(
        email_worker, "_extract_pdf_text_safe", lambda content, password=None: receipt_text
    )
    att = email_worker.EmailAttachment("recibo_bancario.pdf", "application/pdf", b"%PDF-1.4 x")
    assert email_worker.classify_attachment(att) == email_worker.DocumentType.PIX_RECEIPT


def test_classify_receipt_by_filename_even_naming_the_condo(monkeypatch):
    """A file named 'Comprovante...' whose PDF text mentions the condo stays a
    PIX receipt (condo name alone must not flip the classification)."""
    monkeypatch.setattr(
        email_worker, "_extract_pdf_text_safe", lambda content, password=None: "COND. EDIF. VILLA SALOMY"
    )
    att = email_worker.EmailAttachment(
        "ComprovanteSantander-17923384 Julho.pdf", "application/pdf", b"%PDF-1.4 x"
    )
    assert email_worker.classify_attachment(att) == email_worker.DocumentType.PIX_RECEIPT
