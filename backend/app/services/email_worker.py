"""
IMAP email ingestion worker following the luas_finance read-only architecture.
Connects via IMAP SSL (port 993), accesses mailbox in strictly read-only EXAMINE mode,
tracks incremental UIDs, classifies condo bills vs PIX receipts, and syncs cycles.
No emojis used.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import email
from email.header import decode_header
import email.utils
from enum import Enum
import io
import os
from pathlib import Path
import re
from typing import Any, Optional, Union
from sqlalchemy.orm import Session

from app.models.entities import CicloCondominio, ItemRateio, StatusCiclo
from app.services.audit_engine import audit_condo_bill
from app.services.parser_boleto import (
    decrypt_pdf_bytes,
    extract_pdf_text,
    parse_condo_pdf,
)

__all__ = [
    "DocumentType",
    "EmailAttachment",
    "EmailWorker",
    "IngestedDocument",
    "IngestedEmail",
    "SYNDKOS_DEFAULT_SENDER",
    "classify_attachment",
    "extract_documents_from_message",
    "fetch_new_condo_emails",
    "parse_email_message",
    "parse_syndkos_email_subject",
    "process_inbound_message",
    "sync_condo_cycle",
]


class DocumentType(str, Enum):
    CONDO_BILL = "CONDO_BILL"
    PIX_RECEIPT = "PIX_RECEIPT"
    UNKNOWN = "UNKNOWN"


@dataclass
class EmailAttachment:
    filename: str
    content_type: str = "application/octet-stream"
    content: bytes = b""

    def __init__(
        self,
        filename: str,
        content_type: str = "application/octet-stream",
        content: bytes = b"",
    ):
        if isinstance(content_type, bytes) and not content:
            content = content_type
            content_type = "application/octet-stream"
        self.filename = filename
        self.content_type = content_type
        self.content = content


@dataclass
class IngestedEmail:
    uid: int
    sender: str
    subject: str
    date: datetime
    attachments: list[EmailAttachment] = field(default_factory=list)
    body: str = ""


@dataclass
class IngestedDocument:
    doc_type: DocumentType
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    email_uid: int = 0
    email_sender: str = ""
    email_subject: str = ""
    email_date: Optional[datetime] = None
    attachment: Optional[EmailAttachment] = None


def _decode_header_str(header_val: Optional[str]) -> str:
    """Decode RFC 2047 encoded email header to plain string."""
    if not header_val:
        return ""
    parts = decode_header(header_val)
    decoded: list[str] = []
    for content, enc in parts:
        if isinstance(content, bytes):
            decoded.append(content.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(str(content))
    return "".join(decoded)


def _extract_pdf_text_safe(content: bytes, password: Optional[str] = None) -> str:
    """Safely attempt to extract text from PDF bytes via parser_boleto extract_pdf_text."""
    try:
        return extract_pdf_text(content, password=password)
    except Exception:
        return ""


SYNDKOS_DEFAULT_SENDER = os.getenv(
    "SYNDKOS_EMAIL_SENDER", "naoresponda@syndkos.com.br"
)


def parse_syndkos_email_subject(subject: str) -> Optional[dict[str, Any]]:
    """
    Parse Syndkos condo bill email subject pattern:
    'Prezado(a) condômino(a) LUIZ AUGUSTO SOUTES, Segue em anexo seu boleto com vencimento em 10/10/2026 referente a 09/2026'
    Returns dict containing 'condomino', 'data_vencimento' (date), 'competencia' ('YYYY-MM'),
    'raw_vencimento', 'raw_competencia', or None if pattern does not match.
    """
    if not subject:
        return None

    pattern = re.compile(
        r"Prezado\(a\)\s+cond[oô]mino\(a\)\s+([^,]+),\s*"
        r"Segue\s+em\s+anexo\s+seu\s+boleto\s+com\s+vencimento\s+em\s+(\d{2}/\d{2}/\d{4})\s+"
        r"referente\s+a\s+(\d{2}/\d{4})",
        re.IGNORECASE,
    )
    m = pattern.search(subject)
    if not m:
        pattern_relaxed = re.compile(
            r"vencimento\s+em\s+(\d{2}/\d{2}/\d{4})\s+referente\s+a\s+(\d{2}/\d{4})",
            re.IGNORECASE,
        )
        m_rel = pattern_relaxed.search(subject)
        if not m_rel:
            return None
        venc_str, comp_str = m_rel.group(1), m_rel.group(2)
        condomino = "LUIZ AUGUSTO SOUTES"
    else:
        condomino = m.group(1).strip()
        venc_str, comp_str = m.group(2), m.group(3)

    try:
        d, m_int, y = [int(p) for p in venc_str.split("/")]
        data_vencimento = date(y, m_int, d)
    except Exception:
        data_vencimento = None

    try:
        cm, cy = comp_str.split("/")
        competencia = f"{cy}-{cm}"
    except Exception:
        competencia = comp_str

    return {
        "condomino": condomino,
        "data_vencimento": data_vencimento,
        "competencia": competencia,
        "raw_vencimento": venc_str,
        "raw_competencia": comp_str,
    }


def classify_attachment(
    attachment: EmailAttachment,
    email_subject: str = "",
    email_body: str = "",
    email_sender: str = "",
) -> DocumentType:
    """
    Classify an email attachment as CONDO_BILL, PIX_RECEIPT, or UNKNOWN.

    CONDO_BILL: PDF containing keywords like DEMONSTRATIVO, SYNDKOS, VILLA SALOMY,
    CONDOMINIO, or matching the official Syndkos sender (naoresponda@syndkos.com.br)
    or standard subject pattern 'Prezado(a) condômino(a) LUIZ AUGUSTO SOUTES...'.
    PIX_RECEIPT: PDF or image (PNG/JPEG) containing keywords like COMPROVANTE, PIX,
    TRANSFERENCIA, PAGAMENTO, or matching condo bill amounts (e.g. 1.154,31).
    """
    filename_lower = attachment.filename.lower()
    content_type_lower = attachment.content_type.lower()
    is_pdf = (
        filename_lower.endswith(".pdf")
        or "pdf" in content_type_lower
        or attachment.content.startswith(b"%PDF")
    )
    is_image = (
        filename_lower.endswith((".png", ".jpg", ".jpeg"))
        or content_type_lower.startswith("image/")
        or attachment.content.startswith(b"\x89PNG")
        or attachment.content.startswith(b"\xff\xd8")
    )

    # Fast path: official Syndkos sender or matching subject pattern
    syndkos_meta = parse_syndkos_email_subject(email_subject)
    is_syndkos_sender = (
        "SYNDKOS" in email_sender.upper()
        or SYNDKOS_DEFAULT_SENDER.upper() in email_sender.upper()
    )
    if is_pdf and (is_syndkos_sender or syndkos_meta is not None):
        return DocumentType.CONDO_BILL

    extracted_pdf_text = ""
    if is_pdf:
        extracted_pdf_text = _extract_pdf_text_safe(attachment.content)

    meta_text = f"{attachment.filename} {email_subject} {email_body}".upper()
    pdf_text_upper = extracted_pdf_text.upper()
    combined_upper = f"{meta_text} {pdf_text_upper}"

    pix_keywords = [
        "COMPROVANTE",
        "PIX",
        "TRANSFERENCIA",
        "TRANSFERÊNCIA",
        "PAGAMENTO",
        "1.154,31",
        "1154.31",
        "1154,31",
        "AUTENTICACAO",
        "AUTENTICAÇÃO",
    ]

    condo_keywords = [
        "DEMONSTRATIVO",
        "SYNDKOS",
        "VILLA SALOMY",
        "CONDOMINIO",
        "CONDOMÍNIO",
        "RATEIO",
        "BOLETO",
        "DESPESAS ORDINARIAS",
        "DESPESAS ORDINÁRIAS",
        "DESPESAS EXTRAORDINARIAS",
        "DESPESAS EXTRAORDINÁRIAS",
    ]

    # 1. Images can only be PIX receipts or UNKNOWN
    if is_image:
        if any(kw in meta_text for kw in pix_keywords):
            return DocumentType.PIX_RECEIPT
        return DocumentType.UNKNOWN

    # 2. PDFs
    if is_pdf:
        # Check explicit condo indicators inside PDF or in filename
        has_condo_in_pdf = any(kw in pdf_text_upper for kw in condo_keywords)
        has_condo_in_meta = any(kw in meta_text for kw in ["BOLETO", "DEMONSTRATIVO", "SYNDKOS", "VILLA SALOMY", "RATEIO"])
        has_pix_in_meta = any(kw in meta_text for kw in ["COMPROVANTE", "PIX", "TRANSFERENCIA", "TRANSFERÊNCIA"])
        has_pix_in_pdf = any(kw in pdf_text_upper for kw in ["COMPROVANTE", "PIX", "TRANSFERENCIA", "TRANSFERÊNCIA"])

        if has_condo_in_pdf:
            return DocumentType.CONDO_BILL

        if has_pix_in_pdf and not has_condo_in_pdf:
            return DocumentType.PIX_RECEIPT

        if "BOLETO" in attachment.filename.upper() or "DEMONSTRATIVO" in attachment.filename.upper():
            return DocumentType.CONDO_BILL

        if "COMPROVANTE" in attachment.filename.upper() or "PIX" in attachment.filename.upper():
            return DocumentType.PIX_RECEIPT

        if has_condo_in_meta and not has_pix_in_meta:
            return DocumentType.CONDO_BILL

        if has_pix_in_meta:
            return DocumentType.PIX_RECEIPT

        if any(kw in combined_upper for kw in condo_keywords):
            return DocumentType.CONDO_BILL

        if any(kw in combined_upper for kw in pix_keywords):
            return DocumentType.PIX_RECEIPT

    return DocumentType.UNKNOWN


def extract_documents_from_message(
    msg: Union[dict, IngestedEmail],
) -> list[IngestedDocument]:
    """Extract and classify all attachments from an inbound message as IngestedDocument list."""
    if isinstance(msg, dict):
        uid = msg.get("uid", 0)
        sender = msg.get("from") or msg.get("sender", "")
        subject = msg.get("subject", "")
        body = msg.get("body", "")
        date_val = msg.get("date")
        raw_attachments = msg.get("attachments", [])
        attachments: list[EmailAttachment] = []
        for att in raw_attachments:
            if isinstance(att, dict):
                attachments.append(
                    EmailAttachment(
                        filename=att.get("filename", "attachment.bin"),
                        content_type=att.get(
                            "content_type", "application/octet-stream"
                        ),
                        content=att.get("content", b""),
                    )
                )
            elif isinstance(att, EmailAttachment):
                attachments.append(att)
    elif isinstance(msg, IngestedEmail):
        uid = msg.uid
        sender = msg.sender
        subject = msg.subject
        body = msg.body
        date_val = msg.date
        attachments = msg.attachments
    else:
        raise ValueError(f"Unsupported message type: {type(msg)}")

    docs: list[IngestedDocument] = []
    for att in attachments:
        doc_type = classify_attachment(
            att,
            email_subject=subject,
            email_body=body,
            email_sender=sender,
        )
        docs.append(
            IngestedDocument(
                doc_type=doc_type,
                filename=att.filename,
                content=att.content,
                content_type=att.content_type,
                email_uid=uid,
                email_sender=sender,
                email_subject=subject,
                email_date=date_val,
                attachment=att,
            )
        )
    return docs


def process_inbound_message(
    msg: Union[dict, IngestedEmail],
) -> Union[IngestedDocument, list[IngestedDocument]]:
    """
    Process an inbound message and return classified document(s).
    If exactly one attachment is present, returns the IngestedDocument directly.
    """
    docs = extract_documents_from_message(msg)
    if len(docs) == 1:
        return docs[0]
    return docs


def parse_email_message(raw_email_bytes: bytes, uid: int = 0) -> IngestedEmail:
    """Parse raw RFC822 bytes into structured IngestedEmail representation."""
    msg = email.message_from_bytes(raw_email_bytes)
    sender = _decode_header_str(msg.get("From", ""))
    subject = _decode_header_str(msg.get("Subject", ""))

    date_str = msg.get("Date")
    date_dt = None
    if date_str:
        try:
            date_dt = email.utils.parsedate_to_datetime(date_str)
        except Exception:
            date_dt = datetime.now(timezone.utc)
    if date_dt is None:
        date_dt = datetime.now(timezone.utc)

    attachments: list[EmailAttachment] = []
    body_parts: list[str] = []

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        content_type = part.get_content_type()
        filename = part.get_filename()
        if filename:
            filename = _decode_header_str(filename)

        if "attachment" in content_disposition.lower() or filename:
            payload = part.get_payload(decode=True)
            if payload is not None:
                attachments.append(
                    EmailAttachment(
                        filename=filename or "attachment.bin",
                        content_type=content_type,
                        content=payload,
                    )
                )
        elif content_type in ("text/plain", "text/html"):
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_parts.append(payload.decode(charset, errors="replace"))
                except Exception:
                    pass

    return IngestedEmail(
        uid=uid,
        sender=sender,
        subject=subject,
        date=date_dt,
        attachments=attachments,
        body="\n".join(body_parts).strip(),
    )


def fetch_new_condo_emails(
    imap_client: Optional[Any] = None,
    last_uid: int = 0,
    host: str = "imap.gmail.com",
    port: int = 993,
    user: str = "",
    password: str = "",
) -> list[IngestedDocument]:
    """
    Fetch new messages from IMAP server using strictly read-only mode (EXAMINE INBOX).
    Never marks messages as read, moves, deletes, or alters server state.
    Filters incrementally by UID > last_uid.
    """
    client = imap_client
    created_client = False
    if client is None:
        import imaplib

        client = imaplib.IMAP4_SSL(host, port)
        client.login(user, password)
        created_client = True

    try:
        # Strictly read-only EXAMINE INBOX mode
        if hasattr(client, "examine") and not hasattr(client, "select"):
            status, _ = client.examine("INBOX")
        else:
            status, _ = client.select("INBOX", readonly=True)

        if status != "OK":
            return []

        # Incremental search by UID
        if last_uid > 0:
            status, search_data = client.uid("search", None, f"UID {last_uid + 1}:*")
        else:
            status, search_data = client.uid("search", None, "ALL")

        if status != "OK" or not search_data or not search_data[0]:
            return []

        uid_list: list[int] = []
        for raw_u in search_data[0].split():
            try:
                val = int(raw_u)
                if val > last_uid:
                    uid_list.append(val)
            except (ValueError, TypeError):
                continue

        results: list[IngestedDocument] = []
        for u in sorted(uid_list)[-50:]:
            # Fetch message bytes using non-destructive PEEK mode
            status, fetch_data = client.uid("fetch", str(u), "(BODY.PEEK[])")
            raw_bytes = None
            if status == "OK" and fetch_data and fetch_data[0]:
                if isinstance(fetch_data[0], tuple) and len(fetch_data[0]) > 1:
                    raw_bytes = fetch_data[0][1]

            if not raw_bytes:
                # Fallback to RFC822 if PEEK was not supported by server
                status, fetch_data = client.uid("fetch", str(u), "(RFC822)")
                if status == "OK" and fetch_data and fetch_data[0]:
                    if isinstance(fetch_data[0], tuple) and len(fetch_data[0]) > 1:
                        raw_bytes = fetch_data[0][1]

            if not raw_bytes or not isinstance(raw_bytes, bytes):
                continue

            parsed_email = parse_email_message(raw_bytes, uid=u)
            docs = extract_documents_from_message(parsed_email)
            results.extend(docs)

        return results
    finally:
        if created_client:
            try:
                client.close()
            except Exception:
                pass
            try:
                client.logout()
            except Exception:
                pass


class EmailWorker:
    """Worker managing IMAP connection, incremental UID tracking, and message collection."""

    def __init__(
        self,
        host: str = "imap.gmail.com",
        port: int = 993,
        user: str = "",
        password: str = "",
        imap_client: Optional[Any] = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.client = imap_client
        self.last_uid: int = 0
        self.uid_validity: Optional[int] = None

    def connect(self) -> Any:
        if self.client is None:
            import imaplib

            self.client = imaplib.IMAP4_SSL(self.host, self.port)
            self.client.login(self.user, self.password)
        return self.client

    def examine(self, mailbox: str = "INBOX") -> tuple[str, list[bytes]]:
        """Open mailbox in strictly read-only mode using EXAMINE."""
        if self.client is None:
            self.connect()

        status, data = self.client.select(mailbox, readonly=True)

        # Extract UIDVALIDITY
        if hasattr(self.client, "response"):
            resp = self.client.response("UIDVALIDITY")
            if resp and len(resp) > 1 and resp[1]:
                try:
                    self.uid_validity = int(resp[1][0])
                except (ValueError, TypeError):
                    pass
        if self.uid_validity is None and hasattr(self.client, "untagged_responses"):
            ur = getattr(self.client, "untagged_responses", {})
            if "UIDVALIDITY" in ur and ur["UIDVALIDITY"]:
                try:
                    self.uid_validity = int(ur["UIDVALIDITY"][0])
                except (ValueError, TypeError):
                    pass

        return status, data

    def fetch_new_messages(
        self, last_uid: Optional[int] = None
    ) -> list[IngestedDocument]:
        """Fetch new messages starting from last_uid, updating incremental counter."""
        if last_uid is not None:
            self.last_uid = last_uid
        docs = fetch_new_condo_emails(self.client, last_uid=self.last_uid)
        for doc in docs:
            if doc.email_uid > self.last_uid:
                self.last_uid = doc.email_uid
        return docs


def sync_condo_cycle(
    db_session: Session,
    ingested_docs: list[IngestedDocument],
    storage_dir: str = "/data/storage",
) -> list[CicloCondominio]:
    """
    Synchronize ingested documents into database condo cycles:
    - Saves files to disk/storage.
    - Parses new condo bills via parse_condo_pdf and audits via audit_condo_bill.
    - Creates or updates CicloCondominio and child ItemRateio records.
    - Matches PIX receipts against cycles by amount/competence and promotes status
      from PENDENTE_COMPROVANTE to PRONTO_PARA_ENVIO.
    """
    storage_path = Path(storage_dir)
    storage_path.mkdir(parents=True, exist_ok=True)

    affected_cycles: dict[str, CicloCondominio] = {}

    # Separate into bills and receipts
    bills = [d for d in ingested_docs if d.doc_type == DocumentType.CONDO_BILL]
    receipts = [d for d in ingested_docs if d.doc_type == DocumentType.PIX_RECEIPT]

    # 1. Process Condo Bills first
    for bill_doc in bills:
        # Decrypt PDF if password protected before writing to disk,
        # ensuring the archived boleto and subsequent portal submission attachment are accessible
        decrypted_content = decrypt_pdf_bytes(bill_doc.content)
        file_path = storage_path / bill_doc.filename
        file_path.write_bytes(decrypted_content)

        parsed_bill = parse_condo_pdf(bill_doc.content)
        audit_report = audit_condo_bill(parsed_bill)

        ciclo = (
            db_session.query(CicloCondominio)
            .filter_by(competencia=parsed_bill.competencia)
            .first()
        )

        if ciclo is None:
            ciclo = CicloCondominio(
                competencia=parsed_bill.competencia,
                condominio_nome=parsed_bill.condominio_nome,
                data_vencimento=parsed_bill.data_vencimento,
                valor_total=parsed_bill.valor_total,
                valor_ordinarias=parsed_bill.valor_ordinarias,
                valor_extraordinarias=parsed_bill.valor_extraordinarias,
                valor_fundos=parsed_bill.valor_fundos,
                valor_leituras=parsed_bill.valor_leituras,
                valor_ressarcimento=audit_report.total_reimbursement,
                boleto_pdf_path=str(file_path),
                status_ciclo=StatusCiclo.PENDENTE_COMPROVANTE,
            )
            db_session.add(ciclo)
            db_session.flush()

            for item in audit_report.itens_auditados:
                # Find matching original rateio item for valor_total_condominio if available
                orig_item = next(
                    (
                        i
                        for i in parsed_bill.itens
                        if i.descricao == item.descricao
                    ),
                    None,
                )
                total_condo = (
                    orig_item.valor_total_condominio if orig_item else None
                )

                item_record = ItemRateio(
                    ciclo_id=ciclo.id,
                    categoria=item.categoria,
                    descricao=item.descricao,
                    valor_unidade=item.valor,
                    valor_total_condominio=total_condo,
                    responsabilidade=item.responsabilidade,
                    justificativa_legal=item.justificativa_legal,
                )
                db_session.add(item_record)
            db_session.flush()
        else:
            ciclo.boleto_pdf_path = str(file_path)
            ciclo.valor_total = parsed_bill.valor_total
            ciclo.valor_ressarcimento = audit_report.total_reimbursement
            db_session.flush()

        affected_cycles[ciclo.competencia] = ciclo

    # 2. Process PIX Receipts
    if receipts:
        all_cycles = db_session.query(CicloCondominio).all()
        for pix_doc in receipts:
            file_path = storage_path / pix_doc.filename
            file_path.write_bytes(pix_doc.content)

            # Build text corpus for matching
            extracted_pdf_text = ""
            if (
                pix_doc.filename.lower().endswith(".pdf")
                or "pdf" in pix_doc.content_type.lower()
            ):
                extracted_pdf_text = _extract_pdf_text_safe(pix_doc.content)

            corpus = (
                f"{pix_doc.filename} {pix_doc.email_subject} {extracted_pdf_text}"
            ).upper()

            # Filter candidate cycles: prioritize active PENDENTE_COMPROVANTE,
            # strictly excluding completed/terminal cycles (ENVIADO, PROCESSADO_ALUGUEL)
            pending_candidates = [
                c
                for c in all_cycles
                if c.status_ciclo == StatusCiclo.PENDENTE_COMPROVANTE
            ]
            candidates = (
                pending_candidates
                if pending_candidates
                else [
                    c
                    for c in all_cycles
                    if c.status_ciclo
                    not in (StatusCiclo.ENVIADO, StatusCiclo.PROCESSADO_ALUGUEL)
                ]
            )

            # Sort candidates by data_vencimento descending, then competencia descending
            # to match the most recent active cycle when competence is unspecified
            candidates.sort(
                key=lambda c: (
                    c.data_vencimento or date.min,
                    c.competencia or "",
                ),
                reverse=True,
            )

            best_match: Optional[CicloCondominio] = None

            # Pass 1: exact match on both competence and amount
            for cycle in candidates:
                comp_parts = cycle.competencia.split("-")
                comp_slash = (
                    f"{comp_parts[1]}/{comp_parts[0]}"
                    if len(comp_parts) == 2
                    else cycle.competencia
                )
                amt_dot = f"{cycle.valor_total:.2f}"
                amt_comma = amt_dot.replace(".", ",")
                amt_br = (
                    f"{cycle.valor_total:,.2f}"
                    .replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                amount_matches = (
                    amt_dot in corpus or amt_comma in corpus or amt_br in corpus
                )
                comp_matches = (
                    cycle.competencia in corpus
                    or comp_slash in corpus
                    or f"{comp_parts[1]}-{comp_parts[0]}" in corpus
                )

                if comp_matches and amount_matches:
                    best_match = cycle
                    break

            # Pass 2: fallback to competence with payment keywords or amount match on most recent pending
            if best_match is None:
                for cycle in candidates:
                    comp_parts = cycle.competencia.split("-")
                    comp_slash = (
                        f"{comp_parts[1]}/{comp_parts[0]}"
                        if len(comp_parts) == 2
                        else cycle.competencia
                    )
                    amt_dot = f"{cycle.valor_total:.2f}"
                    amt_comma = amt_dot.replace(".", ",")
                    amt_br = (
                        f"{cycle.valor_total:,.2f}"
                        .replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )

                    amount_matches = (
                        amt_dot in corpus or amt_comma in corpus or amt_br in corpus
                    )
                    comp_matches = (
                        cycle.competencia in corpus
                        or comp_slash in corpus
                        or f"{comp_parts[1]}-{comp_parts[0]}" in corpus
                    )

                    if comp_matches and any(
                        k in corpus for k in ["PIX", "COMPROVANTE", "PAGAMENTO"]
                    ):
                        best_match = cycle
                        break
                    elif amount_matches:
                        best_match = cycle
                        break

            if best_match is not None:
                best_match.comprovante_pix_path = str(file_path)
                best_match.status_ciclo = StatusCiclo.PRONTO_PARA_ENVIO
                affected_cycles[best_match.competencia] = best_match
                db_session.flush()

    db_session.commit()
    return list(affected_cycles.values())
