"""
Deterministic parser for Ibagy rental bills.
Extracts contract number, competence, due date, and line items ending with '-'
denoting reimbursements/discounts already granted on the rental invoice.
No emojis used.
"""

from datetime import date
from decimal import Decimal
import io
import os
from pathlib import Path
import re
from typing import BinaryIO, Optional, Union
import pdfplumber

from app.schemas.condo import ItemDescontoAluguel, ParsedAluguelBill


def _parse_decimal(val_str: str) -> Decimal:
    """Convert Brazilian currency string to Decimal."""
    cleaned = val_str.replace("R$", "").replace(" ", "").strip()
    if "." in cleaned and "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def extract_aluguel_pdf_text(
    pdf_input: Union[str, Path, bytes, BinaryIO],
    password: Optional[str] = "04293",
) -> str:
    """
    Extract text content from an Ibagy rental bill PDF, decrypting with password if protected.
    """
    if isinstance(pdf_input, (str, Path)):
        p = Path(pdf_input)
        if not p.exists():
            raise FileNotFoundError(f"Arquivo de aluguel nao encontrado: {pdf_input}")
        pdf_bytes = p.read_bytes()
    elif isinstance(pdf_input, bytes):
        pdf_bytes = pdf_input
    else:
        pdf_bytes = pdf_input.read()

    # Attempt decryption with PyPDF2 / pdfplumber
    try:
        import PyPDF2

        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            writer = PyPDF2.PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            pdf_bytes = buf.getvalue()
    except Exception:
        pass

    pages_text = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes), password=password) as pdf:
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    pages_text.append(txt)
    except Exception:
        # Fallback without password parameter if already decrypted
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text()
                    if txt:
                        pages_text.append(txt)
        except Exception:
            pass

    if not pages_text:
        try:
            decoded = pdf_bytes.decode("utf-8", errors="ignore")
            if "Recibo" in decoded or "Ibagy" in decoded or "Aluguel" in decoded:
                return decoded
        except Exception:
            pass

    return "\n".join(pages_text)


def parse_aluguel_text(text: str) -> ParsedAluguelBill:
    """
    Parse extracted text from an Ibagy rental bill.
    Identifies contract, reference competence, and discount lines ending with '-'.
    """
    if not text or not text.strip():
        raise ValueError("Texto do boleto de aluguel esta vazio")

    # 1. Contrato (Referencia 09638.003.03)
    m_contrato = re.search(r"Refer[eê]ncia\s*(\d{5}\.\d{3}\.\d{2})", text, re.IGNORECASE)
    contrato = m_contrato.group(1).strip() if m_contrato else os.getenv("CONTRATO_PADRAO", "09638.003.03")

    # 2. Competencia (e.g. 01/09/2026 a 30/09/2026 -> 2026-09)
    m_comp = re.search(r"(\d{2})/(\d{2})/(\d{4})\s*a\s*(\d{2})/(\d{2})/(\d{4})", text)
    if m_comp:
        competencia = f"{m_comp.group(3)}-{m_comp.group(2)}"
    else:
        # Fallback pattern
        m_comp2 = re.search(r"(\d{2})/(\d{4})", text)
        competencia = f"{m_comp2.group(2)}-{m_comp2.group(1)}" if m_comp2 else date.today().strftime("%Y-%m")

    # 3. Data de Vencimento
    m_venc = re.search(r"Vencimento\s*(\d{2})/(\d{2})/(\d{4})", text, re.IGNORECASE)
    if m_venc:
        vencimento = date(int(m_venc.group(3)), int(m_venc.group(2)), int(m_venc.group(1)))
    else:
        vencimento = date.today()

    # 4. Valor total do boleto de aluguel
    m_total = re.search(
        r"(?:Valor\s+do\s+Documento|Valor\s+Cobrado)\s*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})",
        text,
        re.IGNORECASE,
    )
    valor_total = _parse_decimal(m_total.group(1)) if m_total else Decimal("0.00")

    # 5. Extract discount lines with '-' (e.g. Fundo de Reserva . 56,21- or Rateio manutencao fachada.( 5/10) 208,29-)
    discount_pattern = re.compile(
        r"([A-Za-zÀ-ÿ0-9\s\.\(\)\/]+?)\s+(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})-"
    )
    itens_desconto: list[ItemDescontoAluguel] = []
    total_descontos = Decimal("0.00")

    for m in discount_pattern.finditer(text):
        desc = m.group(1).strip()
        val = _parse_decimal(m.group(2))
        itens_desconto.append(ItemDescontoAluguel(descricao=desc, valor=val))
        total_descontos += val

    return ParsedAluguelBill(
        competencia=competencia,
        contrato=contrato,
        data_vencimento=vencimento,
        valor_total_aluguel=valor_total,
        valor_total_descontos=total_descontos,
        itens_desconto=itens_desconto,
    )


def parse_aluguel_pdf(
    pdf_input: Union[str, Path, bytes, BinaryIO],
    password: Optional[str] = "04293",
) -> ParsedAluguelBill:
    """Parse Ibagy rental bill directly from PDF bytes or path."""
    text = extract_aluguel_pdf_text(pdf_input, password=password)
    return parse_aluguel_text(text)
