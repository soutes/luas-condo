"""
Legal and audit rule engine for condominium expenses segregation (Lei do Inquilinato).
Segregates parsed condominium charges between tenant (locatario) and landlord (locador)
in compliance with Brazilian Federal Law 8.245/1991 (Articles 22 and 23).
No emojis used.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from app.models.entities import CategoriaItem, ResponsabilidadeItem
from app.schemas.condo import AuditReport, ItemAuditado, ParsedCondoBill, ParsedItemRateio

__all__ = [
    "AuditReport",
    "ItemAuditado",
    "audit_condo_bill",
    "classify_rateio_item",
    "format_currency_brl",
    "generate_formatted_observations",
]

# Keywords indicating ambiguous or unidentified charges requiring manual review
AMBIGUOUS_KEYWORDS = [
    "indeterminado",
    "diversas",
    "diversos",
    "a identificar",
    "desconhecido",
    "outros",
    "sem identificação",
    "sem identificacao",
    "duvidoso",
    "a classificar",
    "pendente",
]

# Keywords that indicate structural or extraordinary expenses mistakenly listed under ordinary
EXTRAORDINARY_WORK_KEYWORDS = [
    "reforma estrutural",
    "reforma da fachada",
    "obra de fachada",
    "obra estrutural",
    "reforma fachada",
    "fundo de reserva",
    "laudo estrutural",
    "indenização trabalhista",
    "indenizacao trabalhista",
]


def format_currency_brl(val: Decimal) -> str:
    """Format Decimal value as Brazilian Real currency (e.g. 354.50 -> 'R$ 354,50')."""
    formatted = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def classify_rateio_item(item: ParsedItemRateio) -> tuple[ResponsabilidadeItem, str, bool]:
    """
    Classify a rateio item by responsibility, legal justification, and review flag.

    Returns:
        tuple[ResponsabilidadeItem, str, bool]: (responsibility, legal justification, review needed)
    """
    desc = item.descricao.lower().strip()
    precisa_revisao = False

    # Check for ambiguous or unidentified descriptions
    for kw in AMBIGUOUS_KEYWORDS:
        if kw in desc:
            precisa_revisao = True
            break

    # 1. Fundos
    if item.categoria == CategoriaItem.FUNDOS:
        responsabilidade = ResponsabilidadeItem.LOCADOR
        if "reserva" in desc:
            justificativa = "Art. 22, X, g da Lei 8.245/91"
        else:
            justificativa = "Art. 22, X da Lei 8.245/91"

    # 2. Despesas Extraordinárias
    elif item.categoria == CategoriaItem.EXTRAORDINARIA:
        responsabilidade = ResponsabilidadeItem.LOCADOR
        # Sub-rules based on Art. 22, X and single paragraph
        if any(w in desc for w in ["fachada", "obra", "reforma", "acréscimo", "acrescimo", "estrutura", "fiscalização", "fiscalizacao"]):
            justificativa = "Art. 22, X, a da Lei 8.245/91"
        elif any(w in desc for w in ["pintura", "empena", "poço", "poco", "esquadria"]):
            justificativa = "Art. 22, X, b da Lei 8.245/91"
        elif "reserva" in desc:
            justificativa = "Art. 22, X, g da Lei 8.245/91"
        elif any(w in desc for w in ["laudo", "bombeiro", "incêndio", "incendio", "avcb", "segurança", "seguranca"]):
            justificativa = "Art. 22, X da Lei 8.245/91"
        elif any(w in desc for w in ["seguro", "sinistro"]):
            justificativa = "Art. 22, X da Lei 8.245/91"
        elif any(w in desc for w in ["tarifa", "bancária", "bancaria", "banco"]):
            justificativa = "Art. 22, X da Lei 8.245/91"
        else:
            justificativa = "Art. 22, X da Lei 8.245/91"

    # 3. Despesas Ordinárias
    elif item.categoria == CategoriaItem.ORDINARIA:
        responsabilidade = ResponsabilidadeItem.LOCATARIO
        justificativa = "Art. 23, § 1º da Lei 8.245/91"
        # Check if an extraordinary expense is mistakenly categorized as ordinary
        for kw in EXTRAORDINARY_WORK_KEYWORDS:
            if kw in desc:
                precisa_revisao = True
                break

    # 4. Leituras / Consumos Individualizados
    elif item.categoria == CategoriaItem.LEITURA:
        responsabilidade = ResponsabilidadeItem.LOCATARIO
        justificativa = "Art. 23, VIII da Lei 8.245/91"

    # 5. Unknown or Unrecognized Category
    else:
        responsabilidade = ResponsabilidadeItem.LOCATARIO
        justificativa = "Art. 23 da Lei 8.245/91"
        precisa_revisao = True

    return responsabilidade, justificativa, precisa_revisao


def generate_formatted_observations(
    condominio_nome: str,
    competencia: str,
    data_vencimento: date,
    itens_locador: list[ItemAuditado],
    total_reimbursement: Decimal,
    revisao_necessaria: bool,
) -> str:
    """
    Generate professional, structured Brazilian Portuguese text for Ibagy reimbursement request.
    References Art. 22 of Federal Law 8.245/1991, lists landlord items and amounts,
    specifies the total rent deduction amount, and mentions attached bill and receipt.
    """
    venc_str = data_vencimento.strftime("%d/%m/%Y")
    total_str = format_currency_brl(total_reimbursement)

    lines = [
        "Solicitação de ressarcimento de despesas condominiais de responsabilidade do locador (Art. 22 da Lei 8.245/91).",
        f"Condomínio: {condominio_nome}",
        f"Competência: {competencia} | Vencimento: {venc_str}",
        "",
    ]

    if itens_locador:
        lines.append("Itens de responsabilidade do locador para dedução no próximo aluguel:")
        for it in itens_locador:
            item_val_str = format_currency_brl(it.valor)
            lines.append(f"- {it.descricao}: {item_val_str} ({it.justificativa_legal})")
        lines.append("")
        lines.append(f"Valor total a ser ressarcido / deduzido: {total_str}")
    else:
        lines.append("Não foram identificadas despesas extraordinárias ou fundos de responsabilidade do locador para ressarcimento nesta fatura.")
        lines.append(f"Valor total a ser ressarcido / deduzido: {total_str}")

    lines.append("")
    lines.append("Seguem em anexo o boleto condominial detalhado e o respectivo comprovante de pagamento.")

    if revisao_necessaria:
        lines.append("")
        lines.append("Observação: Identificada pendência de conferência manual de itens ou divergência de valores.")

    return "\n".join(lines).strip()


def audit_condo_bill(parsed_bill: ParsedCondoBill) -> AuditReport:
    """
    Audit and segregate parsed condominium bill charges between tenant and landlord.
    Performs legal classification, sum reconciliation, and produces formatted observations.
    """
    itens_auditados: list[ItemAuditado] = []
    revisao_necessaria = False

    for item in parsed_bill.itens:
        responsabilidade, justificativa, precisa_revisao = classify_rateio_item(item)
        if precisa_revisao:
            revisao_necessaria = True

        itens_auditados.append(
            ItemAuditado(
                descricao=item.descricao,
                valor=item.valor_unidade,
                categoria=item.categoria,
                responsabilidade=responsabilidade,
                justificativa_legal=justificativa,
            )
        )

    # Calculate financial aggregations
    valor_locatario = sum(
        (it.valor for it in itens_auditados if it.responsabilidade == ResponsabilidadeItem.LOCATARIO),
        Decimal("0.00"),
    )
    valor_locador = sum(
        (it.valor for it in itens_auditados if it.responsabilidade == ResponsabilidadeItem.LOCADOR),
        Decimal("0.00"),
    )
    total_reimbursement = valor_locador

    # Cross-check item sums against parsed bill totals
    soma_itens = valor_locatario + valor_locador
    if abs(soma_itens - parsed_bill.valor_total) > Decimal("0.01"):
        revisao_necessaria = True

    # Filter landlord items for observations
    itens_locador = [
        it for it in itens_auditados if it.responsabilidade == ResponsabilidadeItem.LOCADOR
    ]

    formatted_obs = generate_formatted_observations(
        condominio_nome=parsed_bill.condominio_nome,
        competencia=parsed_bill.competencia,
        data_vencimento=parsed_bill.data_vencimento,
        itens_locador=itens_locador,
        total_reimbursement=total_reimbursement,
        revisao_necessaria=revisao_necessaria,
    )

    return AuditReport(
        competencia=parsed_bill.competencia,
        condominio_nome=parsed_bill.condominio_nome,
        data_vencimento=parsed_bill.data_vencimento,
        valor_total_boleto=parsed_bill.valor_total,
        valor_locatario=valor_locatario,
        valor_locador=valor_locador,
        total_reimbursement=total_reimbursement,
        itens_auditados=itens_auditados,
        formatted_observations=formatted_obs,
        revisao_necessaria=revisao_necessaria,
    )
