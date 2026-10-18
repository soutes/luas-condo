"""
Unit tests for IMAP email ingestion worker and cycle synchronization.
Follows luas_finance read-only pattern (EXAMINE INBOX, incremental UID tracking).
No emojis used.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import email
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import Base
from app.models.entities import CicloCondominio, ItemRateio, StatusCiclo
from app.services.email_worker import (
    SYNDKOS_DEFAULT_SENDER,
    DocumentType,
    EmailAttachment,
    EmailWorker,
    IngestedDocument,
    IngestedEmail,
    classify_attachment,
    fetch_new_condo_emails,
    parse_email_message,
    parse_syndkos_email_subject,
    process_inbound_message,
    sync_condo_cycle,
)

try:
    from tests.fixtures.sample_syndkos_text import VILLA_SALOMY_TEXT_PAGE1
except (ImportError, ModuleNotFoundError):
    from fixtures.sample_syndkos_text import VILLA_SALOMY_TEXT_PAGE1


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
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


def test_process_inbound_condo_pdf():
    """Verify inbound message with condo boleto PDF is classified as CONDO_BILL."""
    mock_msg = {
        "uid": 105,
        "from": "condominio@syndkos.com.br",
        "subject": "Boleto Villa Salomy 09/2026",
        "attachments": [{"filename": "Boleto.pdf", "content": b"%PDF-1.4 sample content"}],
    }
    result = process_inbound_message(mock_msg)
    assert result.doc_type == "CONDO_BILL"
    assert result.doc_type == DocumentType.CONDO_BILL
    assert result.filename == "Boleto.pdf"
    assert result.email_uid == 105


def test_process_inbound_pix_receipt():
    """Verify inbound message with PIX receipt is classified as PIX_RECEIPT."""
    mock_msg_png = {
        "uid": 106,
        "from": "notificacoes@banco.com.br",
        "subject": "Comprovante PIX de Pagamento - R$ 1.154,31",
        "attachments": [{"filename": "comprovante_pix.png", "content": b"\x89PNG\r\n\x1a\nfake"}],
    }
    result_png = process_inbound_message(mock_msg_png)
    assert result_png.doc_type == DocumentType.PIX_RECEIPT
    assert result_png.filename == "comprovante_pix.png"

    mock_msg_pdf = {
        "uid": 107,
        "from": "contato@itau.com.br",
        "subject": "Comprovante de Transferencia PIX",
        "attachments": [{"filename": "comprovante_pix.pdf", "content": b"%PDF-1.4 receipt"}],
    }
    result_pdf = process_inbound_message(mock_msg_pdf)
    assert result_pdf.doc_type == DocumentType.PIX_RECEIPT


def test_process_inbound_unknown_attachment():
    """Verify non-condo, non-receipt attachments are marked as UNKNOWN."""
    mock_msg = {
        "uid": 108,
        "from": "amigo@gmail.com",
        "subject": "Fotos da viagem",
        "attachments": [{"filename": "foto_praia.jpg", "content": b"fake_jpeg"}],
    }
    result = process_inbound_message(mock_msg)
    assert result.doc_type == DocumentType.UNKNOWN


def test_classify_attachment_variations():
    """Verify classify_attachment handles various keywords and content types."""
    # Condo bill PDF by keyword in filename
    att_bill = EmailAttachment(filename="demonstrativo_condominio.pdf", content_type="application/pdf", content=b"fake")
    assert classify_attachment(att_bill, "Demonstrativo", "") == DocumentType.CONDO_BILL

    # PIX receipt image
    att_pix = EmailAttachment(filename="recibo_pix.png", content_type="image/png", content=b"fake")
    assert classify_attachment(att_pix, "Pagamento", "Valor 1.154,31") == DocumentType.PIX_RECEIPT

    # Unknown file
    att_txt = EmailAttachment(filename="notas.txt", content_type="text/plain", content=b"hello")
    assert classify_attachment(att_txt, "Notas", "") == DocumentType.UNKNOWN


def test_imap_readonly_mailbox_access_examine_mode():
    """Verify IMAP client enforces strictly read-only EXAMINE mode and no modification commands."""
    mock_client = MagicMock()
    mock_client.select.return_value = ("OK", [b"0"])
    mock_client.uid.return_value = ("OK", [b""])

    # Run fetch_new_condo_emails with mock client
    docs = fetch_new_condo_emails(imap_client=mock_client, last_uid=0)
    assert docs == []

    # Verify select was called strictly with readonly=True (EXAMINE mode in imaplib)
    mock_client.select.assert_called_once_with("INBOX", readonly=True)

    # Verify modifying commands were NOT called
    assert not mock_client.store.called
    assert not mock_client.expunge.called
    assert not mock_client.copy.called


def test_email_worker_examine_and_uid_validity():
    """Verify EmailWorker class tracks uid_validity and last_uid incrementally."""
    mock_client = MagicMock()
    mock_client.select.return_value = ("OK", [b"15"])
    mock_client.untagged_responses = {"UIDVALIDITY": [b"987654321"]}
    mock_client.response.return_value = ("OK", [b"987654321"])

    worker = EmailWorker(
        host="imap.gmail.com",
        port=993,
        user="test@example.com",
        password="secretpassword",
        imap_client=mock_client,
    )

    worker.examine("INBOX")
    assert worker.uid_validity == 987654321
    mock_client.select.assert_called_with("INBOX", readonly=True)


def test_incremental_uid_tracking_fetches_newer_messages_only():
    """Verify fetch queries only UIDs strictly greater than last_uid."""
    mock_client = MagicMock()
    mock_client.select.return_value = ("OK", [b"2"])
    # Return UIDs 105 and 110 when last_uid is 100
    mock_client.uid.side_effect = [
        ("OK", [b"105 110"]),  # search result
        ("OK", [(b"1 (RFC822 {20}", b"From: a@b.com\r\nSubject: Boleto\r\n\r\nBody"), b")"]),  # fetch 105
        ("OK", [(b"2 (RFC822 {20}", b"From: c@d.com\r\nSubject: Comprovante\r\n\r\nBody"), b")"]),  # fetch 110
    ]

    fetch_new_condo_emails(imap_client=mock_client, last_uid=100)

    # Check that search query checked UID > 100
    mock_client.uid.assert_any_call("search", None, "UID 101:*")


def test_parse_multipart_email_with_pdf_attachment():
    """Verify parsing RFC822 multipart email extracts headers, body, and PDF attachment."""
    msg = MIMEMultipart()
    msg["From"] = "condominio@syndkos.com.br"
    msg["To"] = "luizaugustosoutes@gmail.com"
    msg["Subject"] = "Boleto Villa Salomy 09/2026"
    msg["Date"] = "Wed, 01 Oct 2026 10:00:00 +0000"

    body_part = MIMEText("Segue anexo o boleto para pagamento do condominio.", "plain", "utf-8")
    msg.attach(body_part)

    pdf_content = b"%PDF-1.4 synthetic pdf data"
    pdf_attachment = MIMEApplication(pdf_content, _subtype="pdf")
    pdf_attachment.add_header("Content-Disposition", "attachment", filename="Boleto_09_2026.pdf")
    msg.attach(pdf_attachment)

    raw_email_bytes = msg.as_bytes()

    parsed = parse_email_message(raw_email_bytes, uid=201)
    assert parsed.uid == 201
    assert "condominio@syndkos.com.br" in parsed.sender
    assert parsed.subject == "Boleto Villa Salomy 09/2026"
    assert "boleto para pagamento" in parsed.body
    assert len(parsed.attachments) == 1
    assert parsed.attachments[0].filename == "Boleto_09_2026.pdf"
    assert parsed.attachments[0].content == pdf_content


def test_sync_condo_cycle_creates_cycle_and_items(db_session: Session, tmp_path: Path, monkeypatch):
    """Verify sync_condo_cycle saves files, runs parser and audit, and persists CicloCondominio."""
    # Mock pdfplumber inside parse_condo_pdf
    mock_page = MagicMock()
    mock_page.extract_text.return_value = VILLA_SALOMY_TEXT_PAGE1
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf
    mock_pdf.__exit__.return_value = False
    monkeypatch.setattr("pdfplumber.open", lambda *args, **kwargs: mock_pdf)

    condo_doc = IngestedDocument(
        doc_type=DocumentType.CONDO_BILL,
        filename="Boleto_Villa_Salomy_2026_09.pdf",
        content=b"%PDF-1.4 test boleto",
        content_type="application/pdf",
        email_uid=301,
        email_sender="condominio@syndkos.com.br",
        email_subject="Boleto Villa Salomy 09/2026",
    )

    storage_dir = str(tmp_path / "storage")
    cycles = sync_condo_cycle(db_session, [condo_doc], storage_dir=storage_dir)

    assert len(cycles) == 1
    ciclo = cycles[0]
    assert ciclo.competencia == "2026-09"
    assert ciclo.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert ciclo.valor_total == Decimal("1154.31")
    assert ciclo.valor_ressarcimento == Decimal("354.50")
    assert ciclo.status_ciclo == StatusCiclo.PENDENTE_COMPROVANTE
    assert os.path.exists(ciclo.boleto_pdf_path)

    # Verify items were saved in DB
    saved_items = db_session.query(ItemRateio).filter_by(ciclo_id=ciclo.id).all()
    assert len(saved_items) > 0


def test_sync_condo_cycle_promotes_status_on_matching_pix(db_session: Session, tmp_path: Path, monkeypatch):
    """Verify sync_condo_cycle transitions status from PENDENTE_COMPROVANTE to PRONTO_PARA_ENVIO on matching PIX."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = VILLA_SALOMY_TEXT_PAGE1
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf
    mock_pdf.__exit__.return_value = False
    monkeypatch.setattr("pdfplumber.open", lambda *args, **kwargs: mock_pdf)

    storage_dir = str(tmp_path / "storage")

    # 1. Ingest condo bill
    bill_doc = IngestedDocument(
        doc_type=DocumentType.CONDO_BILL,
        filename="Boleto_Villa_Salomy_2026_09.pdf",
        content=b"%PDF-1.4 bill",
        content_type="application/pdf",
        email_uid=401,
        email_sender="condominio@syndkos.com.br",
        email_subject="Boleto Villa Salomy 09/2026",
    )
    cycles = sync_condo_cycle(db_session, [bill_doc], storage_dir=storage_dir)
    assert cycles[0].status_ciclo == StatusCiclo.PENDENTE_COMPROVANTE
    assert cycles[0].comprovante_pix_path is None

    # 2. Ingest matching PIX receipt (mentioning 1.154,31 and 2026-09)
    pix_doc = IngestedDocument(
        doc_type=DocumentType.PIX_RECEIPT,
        filename="Comprovante_PIX_1154_31.png",
        content=b"\x89PNG\r\n\x1a\nfake pix image",
        content_type="image/png",
        email_uid=402,
        email_sender="notificacoes@banco.com.br",
        email_subject="Comprovante de pagamento PIX R$ 1.154,31 ref 09/2026",
    )
    updated_cycles = sync_condo_cycle(db_session, [pix_doc], storage_dir=storage_dir)

    assert len(updated_cycles) == 1
    cycle = updated_cycles[0]
    assert cycle.status_ciclo == StatusCiclo.PRONTO_PARA_ENVIO
    assert cycle.comprovante_pix_path is not None
    assert os.path.exists(cycle.comprovante_pix_path)


def test_sync_condo_cycle_unmatched_pix_remains_pending(db_session: Session, tmp_path: Path, monkeypatch):
    """Verify PIX receipt with non-matching amount/competence does not promote cycle status."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = VILLA_SALOMY_TEXT_PAGE1
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf
    mock_pdf.__exit__.return_value = False
    monkeypatch.setattr("pdfplumber.open", lambda *args, **kwargs: mock_pdf)

    storage_dir = str(tmp_path / "storage")

    bill_doc = IngestedDocument(
        doc_type=DocumentType.CONDO_BILL,
        filename="Boleto_Villa_Salomy_2026_09.pdf",
        content=b"%PDF-1.4 bill",
        content_type="application/pdf",
        email_uid=501,
        email_sender="condominio@syndkos.com.br",
        email_subject="Boleto Villa Salomy 09/2026",
    )
    sync_condo_cycle(db_session, [bill_doc], storage_dir=storage_dir)

    # PIX receipt for a different amount (e.g. R$ 50,00) with no competence match
    unmatched_pix = IngestedDocument(
        doc_type=DocumentType.PIX_RECEIPT,
        filename="Comprovante_Lanche_50.png",
        content=b"\x89PNG\r\n\x1a\nfake pix image",
        content_type="image/png",
        email_uid=502,
        email_sender="notificacoes@banco.com.br",
        email_subject="Comprovante de pagamento PIX R$ 50,00 ref lanchonete",
    )
    updated_cycles = sync_condo_cycle(db_session, [unmatched_pix], storage_dir=storage_dir)

    # The cycle must remain PENDENTE_COMPROVANTE
    ciclo = db_session.query(CicloCondominio).filter_by(competencia="2026-09").one()
    assert ciclo.status_ciclo == StatusCiclo.PENDENTE_COMPROVANTE
    assert ciclo.comprovante_pix_path is None


def test_sync_condo_cycle_disambiguation_multi_cycle(db_session: Session, tmp_path: Path):
    """Verify PIX receipt matches active pending cycle and avoids terminal cycles or matches exact competence."""
    storage_dir = str(tmp_path / "storage")

    # Cycle 1: terminal ENVIADO cycle with existing receipt
    c1 = CicloCondominio(
        competencia="2026-08",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 9, 10),
        valor_total=Decimal("1154.31"),
        valor_ordinarias=Decimal("596.27"),
        valor_extraordinarias=Decimal("294.87"),
        valor_fundos=Decimal("59.63"),
        valor_leituras=Decimal("203.54"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/data/storage/2026-08.pdf",
        comprovante_pix_path="/data/storage/old_pix_2026_08.png",
        status_ciclo=StatusCiclo.ENVIADO,
    )

    # Cycle 2: older pending cycle
    c2 = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ordinarias=Decimal("596.27"),
        valor_extraordinarias=Decimal("294.87"),
        valor_fundos=Decimal("59.63"),
        valor_leituras=Decimal("203.54"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/data/storage/2026-09.pdf",
        comprovante_pix_path=None,
        status_ciclo=StatusCiclo.PENDENTE_COMPROVANTE,
    )

    # Cycle 3: most recent pending cycle
    c3 = CicloCondominio(
        competencia="2026-10",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 11, 10),
        valor_total=Decimal("1154.31"),
        valor_ordinarias=Decimal("596.27"),
        valor_extraordinarias=Decimal("294.87"),
        valor_fundos=Decimal("59.63"),
        valor_leituras=Decimal("203.54"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/data/storage/2026-10.pdf",
        comprovante_pix_path=None,
        status_ciclo=StatusCiclo.PENDENTE_COMPROVANTE,
    )

    db_session.add_all([c1, c2, c3])
    db_session.commit()

    # Ingest receipt without explicit competence: should bind to most recent pending (2026-10), not ENVIADO (2026-08)
    pix_recent = IngestedDocument(
        doc_type=DocumentType.PIX_RECEIPT,
        filename="Comprovante_PIX_Nov.png",
        content=b"\x89PNG\r\n\x1a\nfake image",
        content_type="image/png",
        email_uid=601,
        email_sender="notificacoes@banco.com.br",
        email_subject="Comprovante de pagamento PIX R$ 1.154,31",
    )
    sync_condo_cycle(db_session, [pix_recent], storage_dir=storage_dir)

    c1_refreshed = db_session.get(CicloCondominio, c1.id)
    c2_refreshed = db_session.get(CicloCondominio, c2.id)
    c3_refreshed = db_session.get(CicloCondominio, c3.id)

    # ENVIADO cycle must not be overwritten
    assert c1_refreshed.status_ciclo == StatusCiclo.ENVIADO
    assert c1_refreshed.comprovante_pix_path == "/data/storage/old_pix_2026_08.png"

    # Most recent pending cycle (2026-10) should be promoted
    assert c3_refreshed.status_ciclo == StatusCiclo.PRONTO_PARA_ENVIO
    assert c3_refreshed.comprovante_pix_path is not None

    # Next receipt with explicit competence for 09/2026 binds specifically to 2026-09
    pix_comp = IngestedDocument(
        doc_type=DocumentType.PIX_RECEIPT,
        filename="Comprovante_PIX_Set.png",
        content=b"\x89PNG\r\n\x1a\nfake image",
        content_type="image/png",
        email_uid=602,
        email_sender="notificacoes@banco.com.br",
        email_subject="Comprovante de pagamento PIX R$ 1.154,31 ref 09/2026",
    )
    sync_condo_cycle(db_session, [pix_comp], storage_dir=storage_dir)

    c2_refreshed = db_session.get(CicloCondominio, c2.id)
    assert c2_refreshed.status_ciclo == StatusCiclo.PRONTO_PARA_ENVIO
    assert "Comprovante_PIX_Set.png" in c2_refreshed.comprovante_pix_path


def test_email_worker_handles_password_protected_condo_bill(db_session, tmp_path):
    """Verify email worker classifies and syncs password-protected condo bill (password: 04293)."""
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

    att = EmailAttachment(
        filename="Boleto_Edificio_Villa_Salomy.pdf",
        content_type="application/pdf",
        content=enc_bytes,
    )

    # 1. Classification works even though file is password-protected
    doc_type = classify_attachment(att, email_subject="Boleto Condomínio Villa Salomy", email_body="")
    assert doc_type == DocumentType.CONDO_BILL

    # 2. Syncing creates cycle, rateio items, and writes decrypted PDF to disk
    ingested_doc = IngestedDocument(
        doc_type=DocumentType.CONDO_BILL,
        filename="Boleto_Edificio_Villa_Salomy.pdf",
        content=enc_bytes,
        email_uid=777,
        email_sender="syndkos@syndkos.com.br",
        email_subject="Demonstrativo de Rateio 09/2026",
    )

    cycles = sync_condo_cycle(db_session, [ingested_doc], storage_dir=str(tmp_path))
    assert len(cycles) == 1
    ciclo = cycles[0]
    assert ciclo.competencia == "2026-09"
    assert ciclo.valor_total == Decimal("1154.31")
    assert ciclo.valor_ressarcimento == Decimal("354.50")
    assert ciclo.status_ciclo == StatusCiclo.PENDENTE_COMPROVANTE

    # 3. Verify saved PDF on disk is decrypted so external reviewers can open it without password
    saved_file = Path(ciclo.boleto_pdf_path)
    assert saved_file.exists()
    check_doc = fitz.open(saved_file)
    assert check_doc.is_encrypted is False
    check_doc.close()


def test_syndkos_email_subject_parser_and_sender_matching():
    """Verify parse_syndkos_email_subject extracts dates, competence, and recipient accurately."""
    subject = (
        "Prezado(a) condômino(a) LUIZ AUGUSTO SOUTES, "
        "Segue em anexo seu boleto com vencimento em 10/10/2026 referente a 09/2026"
    )
    parsed = parse_syndkos_email_subject(subject)
    assert parsed is not None
    assert parsed["condomino"] == "LUIZ AUGUSTO SOUTES"
    assert parsed["data_vencimento"] == date(2026, 10, 10)
    assert parsed["competencia"] == "2026-09"
    assert parsed["raw_vencimento"] == "10/10/2026"
    assert parsed["raw_competencia"] == "09/2026"


def test_classify_attachment_with_syndkos_sender_and_subject():
    """Verify inbound email from naoresponda@syndkos.com.br with standard subject is classified as CONDO_BILL."""
    subject = (
        "Prezado(a) condômino(a) LUIZ AUGUSTO SOUTES, "
        "Segue em anexo seu boleto com vencimento em 10/11/2026 referente a 10/2026"
    )
    sender = SYNDKOS_DEFAULT_SENDER
    assert sender == "naoresponda@syndkos.com.br"

    att = EmailAttachment(
        filename="Boleto_Novembro.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 raw binary without ocr",
    )
    doc_type = classify_attachment(att, email_subject=subject, email_sender=sender)
    assert doc_type == DocumentType.CONDO_BILL


def test_process_inbound_syndkos_email_full_flow():
    """Verify process_inbound_message with official Syndkos sender and subject pattern."""
    msg = {
        "uid": 888,
        "from": "naoresponda@syndkos.com.br",
        "subject": "Prezado(a) condômino(a) LUIZ AUGUSTO SOUTES, Segue em anexo seu boleto com vencimento em 10/10/2026 referente a 09/2026",
        "attachments": [
            {
                "filename": "boleto_villa_salomy.pdf",
                "content_type": "application/pdf",
                "content": b"%PDF-1.4 sample content",
            }
        ],
    }
    result = process_inbound_message(msg)
    assert isinstance(result, IngestedDocument)
    assert result.doc_type == DocumentType.CONDO_BILL
    assert result.email_sender == "naoresponda@syndkos.com.br"
    assert "09/2026" in result.email_subject


def test_classify_ibagy_rental_bill():
    """Verify classify_attachment classifies Ibagy rental bills."""
    att = EmailAttachment(
        filename="Boleto_Aluguel_Outubro.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 raw binary",
    )
    doc_type = classify_attachment(
        att,
        email_subject="Boleto de aluguel referente a 09/2026",
        email_sender="boleto@ibagyimobiliaria.com.br",
    )
    assert doc_type == DocumentType.RENTAL_BILL


def test_sync_condo_cycle_rental_bill_closes_submitted_cycle(db_session: Session, tmp_path: Path):
    """
    Monthly flow: the Ibagy rental bill of competence M+1 carries the discount
    applied to the previous month's condo bill. When the previous cycle was
    already submitted (ENVIADO) and the discount covers the full claimed amount,
    the cycle is closed as PROCESSADO_ALUGUEL.
    """
    storage_dir = str(tmp_path / "storage")

    ciclo = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ordinarias=Decimal("596.27"),
        valor_extraordinarias=Decimal("294.87"),
        valor_fundos=Decimal("59.63"),
        valor_leituras=Decimal("203.54"),
        valor_ressarcimento=Decimal("264.50"),
        valor_saldo_residual=Decimal("264.50"),
        boleto_pdf_path="/data/storage/condo.pdf",
        comprovante_pix_path="/data/storage/pix.pdf",
        status_ciclo=StatusCiclo.ENVIADO,
    )
    db_session.add(ciclo)
    db_session.commit()

    sample_rental_text = (
        "341-7 Recibo do Pagador\n"
        "Beneficiario Ibagy Imoveis Ltda\n"
        "Aluguel C(Prop) D(Inq) 2650,00+\n"
        "Fundo de Reserva . 56,21-\n"
        "Rateio manutencao fachada.( 5/10) 208,29-\n"
        "(=) Valor do Documento R$ 2.741,14\n"
        "Referencia 09638.003.03\n"
        "01/10/2026 a 31/10/2026\n"
        "Vencimento 05/11/2026\n"
    )

    rental_doc = IngestedDocument(
        doc_type=DocumentType.RENTAL_BILL,
        filename="Boleto_Aluguel_2026_10.pdf",
        content=sample_rental_text.encode("utf-8"),
        content_type="application/pdf",
        email_uid=991,
        email_sender="boleto@ibagyimobiliaria.com.br",
        email_subject="Boleto Aluguel 10/2026",
    )

    result = sync_condo_cycle(db_session, [rental_doc], storage_dir=storage_dir)

    c_refreshed = db_session.get(CicloCondominio, ciclo.id)
    assert c_refreshed.valor_desconto_aluguel == Decimal("264.50")
    assert c_refreshed.status_ciclo == StatusCiclo.PROCESSADO_ALUGUEL
    assert "encerrado" in c_refreshed.detalhes_verificacao.lower()
    assert len(c_refreshed.itens_abatidos_aluguel) == 2
    assert [c.competencia for c in result] == ["2026-09"]


def test_sync_condo_cycle_rental_bill_divergence_on_submitted_cycle(db_session: Session, tmp_path: Path):
    """
    Monthly flow: when the following-month rental discount comes SHORT of the
    submitted amount, the cycle stays ENVIADO and the divergence is recorded.
    """
    storage_dir = str(tmp_path / "storage")

    ciclo = CicloCondominio(
        competencia="2026-08",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 9, 10),
        valor_total=Decimal("1154.31"),
        valor_ressarcimento=Decimal("264.50"),
        valor_saldo_residual=Decimal("264.50"),
        boleto_pdf_path="/data/storage/condo_08.pdf",
        comprovante_pix_path="/data/storage/pix_08.pdf",
        status_ciclo=StatusCiclo.ENVIADO,
    )
    db_session.add(ciclo)
    db_session.commit()

    sample_rental_text = (
        "341-7 Recibo do Pagador\n"
        "Beneficiario Ibagy Imoveis Ltda\n"
        "Fundo de Reserva . 56,21-\n"
        "(=) Valor do Documento R$ 2.741,14\n"
        "Referencia 09638.003.03\n"
        "01/09/2026 a 30/09/2026\n"
        "Vencimento 05/10/2026\n"
    )

    rental_doc = IngestedDocument(
        doc_type=DocumentType.RENTAL_BILL,
        filename="Boleto_Aluguel_2026_09.pdf",
        content=sample_rental_text.encode("utf-8"),
        content_type="application/pdf",
        email_uid=993,
        email_sender="boleto@ibagyimobiliaria.com.br",
        email_subject="Boleto Aluguel 09/2026",
    )

    sync_condo_cycle(db_session, [rental_doc], storage_dir=storage_dir)

    c_refreshed = db_session.get(CicloCondominio, ciclo.id)
    assert c_refreshed.valor_desconto_aluguel == Decimal("56.21")
    assert c_refreshed.status_ciclo == StatusCiclo.ENVIADO
    assert "divergencia" in c_refreshed.detalhes_verificacao.lower()
    assert "208,29" in c_refreshed.detalhes_verificacao or "208.29" in c_refreshed.detalhes_verificacao


def test_sync_condo_cycle_rental_bill_does_not_touch_pending_cycle(db_session: Session, tmp_path: Path):
    """
    Monthly verification ignores the rental bill comparison: a rental bill
    arriving while the previous cycle is still pending must NOT reconcile it,
    block it, or create a separate cycle.
    """
    storage_dir = str(tmp_path / "storage")

    ciclo = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ressarcimento=Decimal("354.50"),
        valor_saldo_residual=Decimal("354.50"),
        boleto_pdf_path="/data/storage/condo.pdf",
        comprovante_pix_path="/data/storage/pix.pdf",
        status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
    )
    db_session.add(ciclo)
    db_session.commit()

    sample_rental_text = (
        "341-7 Recibo do Pagador\n"
        "Beneficiario Ibagy Imoveis Ltda\n"
        "Fundo de Reserva . 56,21-\n"
        "Rateio manutencao fachada.( 5/10) 208,29-\n"
        "(=) Valor do Documento R$ 2.741,14\n"
        "Referencia 09638.003.03\n"
        "01/10/2026 a 31/10/2026\n"
        "Vencimento 05/11/2026\n"
    )

    rental_doc = IngestedDocument(
        doc_type=DocumentType.RENTAL_BILL,
        filename="Boleto_Aluguel_2026_10.pdf",
        content=sample_rental_text.encode("utf-8"),
        content_type="application/pdf",
        email_uid=994,
        email_sender="boleto@ibagyimobiliaria.com.br",
        email_subject="Boleto Aluguel 10/2026",
    )

    sync_condo_cycle(db_session, [rental_doc], storage_dir=storage_dir)

    c_refreshed = db_session.get(CicloCondominio, ciclo.id)
    assert c_refreshed.status_ciclo == StatusCiclo.PRONTO_PARA_ENVIO
    assert c_refreshed.valor_desconto_aluguel == Decimal("0.00")
    assert c_refreshed.valor_saldo_residual == Decimal("354.50")
    assert c_refreshed.boleto_aluguel_path is None
    # No phantom cycle created for the rental bill's own competence
    assert db_session.query(CicloCondominio).count() == 1


def test_sync_condo_cycle_rental_bill_without_previous_cycle_creates_nothing(db_session: Session, tmp_path: Path):
    """
    Monthly flow: a rental bill with no previous-month cycle to verify must be
    archived without creating any cycle (no more orphan aluguel-only cycles).
    """
    storage_dir = str(tmp_path / "storage")

    sample_rental_text = (
        "341-7 Recibo do Pagador\n"
        "Beneficiario Ibagy Imoveis Ltda\n"
        "Fundo de Reserva . 56,21-\n"
        "(=) Valor do Documento R$ 2.741,14\n"
        "Referencia 09638.003.03\n"
        "01/10/2026 a 31/10/2026\n"
        "Vencimento 05/11/2026\n"
    )

    rental_doc = IngestedDocument(
        doc_type=DocumentType.RENTAL_BILL,
        filename="Boleto_Aluguel_2026_10.pdf",
        content=sample_rental_text.encode("utf-8"),
        content_type="application/pdf",
        email_uid=995,
        email_sender="boleto@ibagyimobiliaria.com.br",
        email_subject="Boleto Aluguel 10/2026",
    )

    result = sync_condo_cycle(db_session, [rental_doc], storage_dir=storage_dir)

    assert result == []
    assert db_session.query(CicloCondominio).count() == 0




