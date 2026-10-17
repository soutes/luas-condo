"""
Tests for Ibagy rental bill parser.
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

from app.services.parser_aluguel import parse_aluguel_text

SAMPLE_IBAGY_RENTAL_TEXT = """341-7 Recibo do Pagador
Beneficiario Ibagy Imoveis Ltda 75.290.122/0001-69. Rua Santos Saraiva, 1083 - CEP: 88070-100
Estreito - Florianopolis - SC
Data do Documento 02/10/2026 No do Documento 0002158786
Instrucoes de responsabilidade do Beneficiario
* * Valores Expressos em Reais * *
Aluguel C(Prop) D(Inq) 2650,00+
Seguro incendio mensal ( 2/12) 59,29+
IPTU C(Prop) D(Inq) (08/10) 48,45+
IPTU C(Prop) D(Inq) (08/10) 172,31+
Coleta Lixo C(Prop) D(Inq) (08/10) 75,59+
Fundo de Reserva . 56,21-
Rateio manutencao fachada.( 5/10) 208,29-
Vencimento 05/10/2026
Nome proprietario Swenson Schroeder
(=) Valor do Documento R$ 2.741,14
Pagador Luiz Augusto Soutes 042.931.439-63
ED. Villa Salomy, R Santos Saraiva, 144 APTO 802 GAR 13
Referencia 09638.003.03 Dia 30
01/09/2026 a 30/09/2026
"""


def test_parse_aluguel_text():
    parsed = parse_aluguel_text(SAMPLE_IBAGY_RENTAL_TEXT)

    assert parsed.competencia == "2026-09"
    assert parsed.contrato == "09638.003.03"
    assert parsed.data_vencimento == date(2026, 10, 5)
    assert parsed.valor_total_aluguel == Decimal("2741.14")
    assert parsed.valor_total_descontos == Decimal("264.50")
    assert len(parsed.itens_desconto) == 2

    assert parsed.itens_desconto[0].descricao == "Fundo de Reserva ."
    assert parsed.itens_desconto[0].valor == Decimal("56.21")

    assert "fachada" in parsed.itens_desconto[1].descricao.lower()
    assert parsed.itens_desconto[1].valor == Decimal("208.29")
