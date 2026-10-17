# Task 6 Brief: Mock Server Bitrix24 & Submitter Service

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (code, tests, comments, commit messages, config).
- Default target for tests & CI: `mock-bitrix` (never submit fake test tickets to real Ibagy CRM).
- Real Ibagy form URL: `https://ibagy.bitrix24.site/condominioressarcimento/ressarcimento/` (used only when `MOCK_SUBMISSION=false`).
- Tenant contract number: `09638.003.03`.

## Task Scope & Files
- Create: `mock_bitrix/main.py` (FastAPI app replicating Bitrix24 form, validation, and error injection)
- Create: `backend/app/services/bitrix_submitter.py` (Submitter client supporting HTTP multipart and Playwright)
- Test: `backend/tests/test_bitrix_submitter.py`

## Bitrix24 Form Specification (from User Uploaded Reference)
Fields:
1. `nome`: "Nome do inquilino *"
2. `email`: "E-mail *"
3. `telefone`: "Telefone *" (format: `55 XX 9XXXX-XXXX`)
4. `contrato`: "Número do contrato *" (format: `XXXXX.XXX.XX`, e.g. `09638.003.03`)
5. `observacoes`: "Observações" (string with memo)
6. `boleto`: "Boleto condomínio *" (file upload)
7. `comprovante`: "Comprovante de pagamento *" (file upload)

## Error Simulation for On-Call Drills (in mock_bitrix)
Mock server must support headers or query parameters for controlled failure scenarios:
- `x-simulate-status`: Return specific HTTP status (e.g. 500, 503, 400).
- `x-simulate-selector`: Render altered input names (e.g. `contrato_num` instead of `contrato`) to trigger and test DOM inspection by the On-Call agent.

## Submitter Client Interface (`backend/app/services/bitrix_submitter.py`)
```python
class SubmissionReceipt(BaseModel):
    status: StatusSubmissao  # SUCESSO or ERRO
    protocolo: Optional[str] = None
    mensagem: str
    screenshot_path: Optional[str] = None
    trace_id: str

async def submit_reimbursement(
    payload: SubmissionPayload,
    db_session: Optional[Session] = None,
    trace_id: Optional[str] = None,
    target_url: Optional[str] = None,
    use_browser: bool = False
) -> SubmissionReceipt
```
- Persists record in `SubmissaoRessarcimento` table if `db_session` is provided.
- Records `trace_id` for OpenTelemetry correlation.

## Acceptance Criteria
- [ ] TDD followed: `backend/tests/test_bitrix_submitter.py` written first and tested to fail, then implemented and verified to pass.
- [ ] Mock Bitrix server validates mandatory fields and produces protocol format (e.g. `IBAGY-2026-XXXX`).
- [ ] Submitter client uploads boleto PDF and comprovante PIX via multipart/form-data.
- [ ] Handles simulated error (500) and records `status = ERRO` with error description.
- [ ] Persists submission record in `SubmissaoRessarcimento` table with trace_id.
- [ ] All test suites pass: `pytest` passes all scaffolding, model, parser, audit, worker, and submitter tests.
- [ ] Commit message: `feat: implement mock bitrix24 and robust submitter service` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-6-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
