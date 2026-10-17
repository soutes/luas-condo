# Task 5 Brief: IMAP Ingestion Worker (luas_finance Read-Only Pattern)

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (code, tests, comments, commit messages, config).
- Mode: Strictly READ-ONLY (`EXAMINE INBOX`). Under NO circumstance should any email be marked as read, moved, deleted, or altered on the mail server.
- Incremental Tracking: Track `last_uid` and `uid_validity` to fetch only new incoming messages (`UID > last_uid`).

## Task Scope & Files
- Create: `backend/app/services/email_worker.py`
- Test: `backend/tests/test_email_worker.py`

## Architecture & Interfaces (Matching luas_finance)
1. Connection config:
   - `host: str = "imap.gmail.com"`
   - `port: int = 993`
   - `user: str` (e.g. `luizaugustosoutes@gmail.com`)
   - `password: str` (Google App Password)

2. Core Components:
   - `EmailAttachment`: `filename: str`, `content_type: str`, `content: bytes`
   - `IngestedEmail`: `uid: int`, `sender: str`, `subject: str`, `date: datetime`, `attachments: list[EmailAttachment]`
   - `DocumentType`: Enum `CONDO_BILL`, `PIX_RECEIPT`, `UNKNOWN`
   - `classify_attachment(attachment: EmailAttachment, email_subject: str, email_body: str) -> DocumentType`:
     - `CONDO_BILL`: PDF containing keywords like "DEMONSTRATIVO", "SYNDKOS", "VILLA SALOMY", "CONDOMINIO", or matching rateio patterns.
     - `PIX_RECEIPT`: PDF or image (PNG/JPEG) containing keywords like "COMPROVANTE", "PIX", "TRANSFERENCIA", "PAGAMENTO", or amount matching condo bill (e.g. "1.154,31").
   - `sync_condo_cycle(db_session, ingested_docs: list[IngestedDocument], storage_dir: str) -> list[CicloCondominio]`:
     - Saves files to disk/storage.
     - Automatically parses new condo bills using `parse_condo_pdf` and `audit_condo_bill` from earlier tasks.
     - Creates or updates `CicloCondominio` and child `ItemRateio` records.
     - If PIX receipt is found matching the cycle amount/competence, attaches `comprovante_pix_path` and promotes status from `PENDENTE_COMPROVANTE` to `PRONTO_PARA_ENVIO`.

## Acceptance Criteria
- [ ] TDD followed: `backend/tests/test_email_worker.py` written first and tested to fail, then implemented and verified to pass.
- [ ] Unit tests with mock IMAP client verifying:
  - Read-only mailbox access (`EXAMINE` mode).
  - Correct parsing of multipart email with PDF attachments.
  - Accurate classification of condo bills vs PIX receipts.
  - Cycle state transition: `PENDENTE_COMPROVANTE` -> `PRONTO_PARA_ENVIO` when receipt matches.
- [ ] All test suites pass: `pytest` passes all scaffolding, model, parser, audit, and worker tests.
- [ ] Commit message: `feat: implement imap read-only poller matching luas_finance architecture` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-5-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
