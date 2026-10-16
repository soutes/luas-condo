"""
Deterministic parser for Syndkos condominium bills (Villa Salomy format).
Extracts rateio entries, subtotals, barcode line, and validates mathematical integrity.
No emojis used.
"""

from datetime import date
from decimal import Decimal
import io
from pathlib import Path
import re
from typing import BinaryIO, Optional, Union

import pdfplumber

from app.models.entities import CategoriaItem
from app.schemas.condo import ParsedCondoBill, ParsedItemRateio

__all__ = [
    "ParsedCondoBill",
    "ParsedItemRateio",
    "parse_condo_pdf",
    "parse_condo_text",
]

NUMBER_PATTERN = r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})"


def _parse_decimal(val_str: str) -> Decimal:
    """Convert Brazilian formatted currency or decimal string to Decimal."""
    cleaned = val_str.replace("R$", "").replace(" ", "").strip()
    if not cleaned:
        raise ValueError("Empty string cannot be converted to Decimal")
    if "." in cleaned and "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def parse_condo_text(text: str) -> ParsedCondoBill:
    """
    Parse text extracted from a Syndkos condo bill.
    Performs deterministic parsing of metadata, items, and validates mathematical integrity.
    """
    if not text or not text.strip():
        raise ValueError("Unable to parse condo bill: text is empty")

    # 1. Condominium Name
    m_condo = re.search(
        r"^\s*(CONDOM[IÍ]NIO\s+[^\r\n]+)", text, re.IGNORECASE | re.MULTILINE
    )
    if m_condo:
        condominio_nome = m_condo.group(1).strip()
    else:
        condominio_nome = "CONDOMINIO EDIFICIO VILLA SALOMY"

    # 2. Competence (e.g. 2026-09)
    m_comp = re.search(
        r"DEMONSTRATIVO\s+DE\s+RATEIO\s+DE\s+\d{2}/(\d{2})/(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m_comp:
        month, year = m_comp.group(1), m_comp.group(2)
        competencia = f"{year}-{month}"
    else:
        m_comp_generic = re.search(
            r"(?:COMPET[EÊ]NCIA|REF\.?|M[EÊ]S/ANO)[:\s]+(\d{2})[/.-](\d{4})",
            text,
            re.IGNORECASE,
        )
        if m_comp_generic:
            competencia = f"{m_comp_generic.group(2)}-{m_comp_generic.group(1)}"
        else:
            m_comp_iso = re.search(r"\b(\d{4})-(\d{2})\b", text)
            if m_comp_iso:
                competencia = f"{m_comp_iso.group(1)}-{m_comp_iso.group(2)}"
            else:
                raise ValueError("Unable to parse condo bill: competencia not found")

    # 3. Due Date
    m_venc = re.search(
        r"(?:VENCIMENTO|Vencimento)[:\s]+(\d{2})[/.-](\d{2})[/.-](\d{4})",
        text,
        re.IGNORECASE,
    )
    if m_venc:
        day, month, year = (
            int(m_venc.group(1)),
            int(m_venc.group(2)),
            int(m_venc.group(3)),
        )
        data_vencimento = date(year, month, day)
    else:
        raise ValueError("Unable to parse condo bill: data_vencimento not found")

    # 4. Total Amount
    m_total = re.search(
        r"(?:VALOR\s+TOTAL(?:\s+DO\s+BOLETO)?|TOTAL\s+A\s+PAGAR)[:\s]+(?:R\$\s*)?([\d.,]+)",
        text,
        re.IGNORECASE,
    )
    if m_total:
        valor_total = _parse_decimal(m_total.group(1))
    else:
        raise ValueError("Unable to parse condo bill: valor_total not found")

    # 5. Barcode Line (Linha Digitavel)
    m_linha = re.search(
        r"(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14})",
        text,
    )
    linha_digitavel = m_linha.group(1).strip() if m_linha else None

    # 6. Parse Sections and Items
    current_category: Optional[CategoriaItem] = None
    parsed_items: list[ParsedItemRateio] = []
    category_subtotals: dict[CategoriaItem, Decimal] = {}

    skip_keywords = [
        "SUBTOTAL",
        "TOTAL",
        "DESCRICAO",
        "DESCRIÇÃO",
        "RESUMO",
        "VALOR TOTAL",
        "LINHA DIGITAVEL",
        "LINHA DIGITÁVEL",
        "VENCIMENTO",
        "CNPJ",
        "UNIDADE",
        "FRAÇÃO",
        "FRACAO",
        "DEMONSTRATIVO",
        "COMPETENCIA",
        "COMPETÊNCIA",
    ]

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Check section boundaries
        if re.search(
            r"^\s*(?:DESPESAS\s+)?EXTRAORDIN[AÁ]RIAS\s*$", line, re.IGNORECASE
        ):
            current_category = CategoriaItem.EXTRAORDINARIA
            continue
        if re.search(r"^\s*(?:DESPESAS\s+)?ORDIN[AÁ]RIAS\s*$", line, re.IGNORECASE):
            current_category = CategoriaItem.ORDINARIA
            continue
        if re.search(
            r"^\s*(?:LEITURAS|CONSUMO(?:\s+INDIVIDUAL)?)\s*$", line, re.IGNORECASE
        ):
            current_category = CategoriaItem.LEITURA
            continue
        if re.search(
            r"^\s*FUNDOS\s*$", line, re.IGNORECASE
        ) or re.search(
            r"^\s*FUNDO\s+DE\s+RESERVA\s*$", line, re.IGNORECASE
        ):
            current_category = CategoriaItem.FUNDOS
            continue
        if re.search(r"^\s*(?:RESUMO|TOTAL\s+GERAL)\b", line, re.IGNORECASE):
            current_category = None

        # Check explicit subtotal / total lines
        m_sub = re.search(
            r"^\s*(?:SUBTOTAL|TOTAL)\s+(?:DESPESAS\s+)?(ORDIN[AÁ]RIAS|EXTRAORDIN[AÁ]RIAS|LEITURAS|FUNDOS)[:\s]+(?:R\$\s*)?([\d.,]+)",
            line,
            re.IGNORECASE,
        )
        if m_sub:
            cat_name = m_sub.group(1).upper()
            val = _parse_decimal(m_sub.group(2))
            if "EXTRAORDIN" in cat_name:
                category_subtotals[CategoriaItem.EXTRAORDINARIA] = val
            elif "ORDIN" in cat_name:
                category_subtotals[CategoriaItem.ORDINARIA] = val
            elif "LEITURA" in cat_name:
                category_subtotals[CategoriaItem.LEITURA] = val
            elif "FUNDO" in cat_name:
                category_subtotals[CategoriaItem.FUNDOS] = val
            continue

        if current_category is None:
            continue

        # Try matching two numbers at end of line (condo total + unit value)
        two_nums = re.search(
            r"^(.*?)\s+" + NUMBER_PATTERN + r"\s+" + NUMBER_PATTERN + r"\s*$",
            line,
        )
        if two_nums:
            desc = two_nums.group(1).strip()
            if any(kw in desc.upper() for kw in skip_keywords):
                continue
            total_condo = _parse_decimal(two_nums.group(2))
            unit_val = _parse_decimal(two_nums.group(3))
            parsed_items.append(
                ParsedItemRateio(
                    descricao=desc,
                    valor_unidade=unit_val,
                    valor_total_condominio=total_condo,
                    categoria=current_category,
                )
            )
            continue

        # Try matching single number at end of line (unit value)
        one_num = re.search(
            r"^(.*?)\s+" + NUMBER_PATTERN + r"\s*$",
            line,
        )
        if one_num:
            desc = one_num.group(1).strip()
            if any(kw in desc.upper() for kw in skip_keywords):
                continue
            unit_val = _parse_decimal(one_num.group(2))
            parsed_items.append(
                ParsedItemRateio(
                    descricao=desc,
                    valor_unidade=unit_val,
                    valor_total_condominio=None,
                    categoria=current_category,
                )
            )
            continue

    # 7. Category Totals Resolution
    sum_ordinarias = sum(
        (i.valor_unidade for i in parsed_items if i.categoria == CategoriaItem.ORDINARIA),
        Decimal("0.00"),
    )
    sum_extraordinarias = sum(
        (i.valor_unidade for i in parsed_items if i.categoria == CategoriaItem.EXTRAORDINARIA),
        Decimal("0.00"),
    )
    sum_fundos = sum(
        (i.valor_unidade for i in parsed_items if i.categoria == CategoriaItem.FUNDOS),
        Decimal("0.00"),
    )
    sum_leituras = sum(
        (i.valor_unidade for i in parsed_items if i.categoria == CategoriaItem.LEITURA),
        Decimal("0.00"),
    )

    valor_ordinarias = category_subtotals.get(CategoriaItem.ORDINARIA, sum_ordinarias)
    valor_extraordinarias = category_subtotals.get(CategoriaItem.EXTRAORDINARIA, sum_extraordinarias)
    valor_fundos = category_subtotals.get(CategoriaItem.FUNDOS, sum_fundos)
    valor_leituras = category_subtotals.get(CategoriaItem.LEITURA, sum_leituras)

    # 8. Mathematical Integrity Validation
    category_sum = valor_ordinarias + valor_extraordinarias + valor_fundos + valor_leituras
    if abs(category_sum - valor_total) > Decimal("0.01"):
        raise ValueError(
            f"Mathematical integrity check failed: category sum ({category_sum}) "
            f"does not match valor_total ({valor_total}) within 0.01 tolerance"
        )

    return ParsedCondoBill(
        condominio_nome=condominio_nome,
        competencia=competencia,
        data_vencimento=data_vencimento,
        valor_total=valor_total,
        valor_ordinarias=valor_ordinarias,
        valor_extraordinarias=valor_extraordinarias,
        valor_fundos=valor_fundos,
        valor_leituras=valor_leituras,
        linha_digitavel=linha_digitavel,
        itens=parsed_items,
    )


def parse_condo_pdf(
    pdf_source: Union[str, Path, bytes, BinaryIO],
) -> ParsedCondoBill:
    """
    Extract text from a PDF condo bill and parse it deterministically.
    Supports file path (str/Path), raw bytes, or stream.
    """
    if isinstance(pdf_source, (str, Path)):
        with pdfplumber.open(str(pdf_source)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
            full_text = "\n".join(pages_text)
    elif isinstance(pdf_source, bytes):
        with pdfplumber.open(io.BytesIO(pdf_source)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
            full_text = "\n".join(pages_text)
    else:
        with pdfplumber.open(pdf_source) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
            full_text = "\n".join(pages_text)

    return parse_condo_text(full_text)
