# Task 6 Report: Mock Server Bitrix24 & Submitter Service

## Summary
- Task: Task 6 - Mock Server Bitrix24 & Submitter Service
- Status: DONE
- Commit Hash: f87114478181a2b88207c512fce80b0aeabb856e
- Single-command test execution: 51 passed in 14.42s (all 41 existing + 10 new submitter & mock server tests)

## Created & Modified Files
- `mock_bitrix/main.py`: Created FastAPI mock server replicating the Bitrix24 reimbursement form:
  - Mandatory fields validation: `nome`, `email`, `telefone`, `contrato`, `boleto`, `comprovante` (and optional `observacoes`).
  - Protocol generation matching `IBAGY-2026-XXXX` format.
  - Dual response support: renders HTML with `#protocolo` for browser navigation or returns JSON with protocol details for HTTP client.
  - Error simulation for On-Call drills:
    - `x-simulate-status` (or `simulate_status` query param): injects HTTP status codes (e.g. 500, 503, 400).
    - `x-simulate-selector` (or `simulate_selector` query param): alters input names (e.g. `contrato_num` instead of `contrato`) to trigger DOM inspection and test automated recovery.
- `backend/app/services/bitrix_submitter.py`: Created robust submitter service supporting dual execution modes:
  - `SubmissionPayload`: validates inputs and supports aliases (`boleto_pdf_path`, `comprovante_pix_path`) directly from `CicloCondominio`.
  - `SubmissionReceipt`: structured receipt with `status` (`SUCESSO` or `ERRO`), `protocolo`, `mensagem`, `screenshot_path`, and `trace_id`.
  - HTTP multipart/form-data upload (`_submit_via_http`): async uploads boleto PDF and comprovante PIX files, extracts protocol from JSON or HTML regex.
  - Playwright browser automation (`_submit_via_browser`): launches headless chromium, validates form field presence, uploads files, clicks `#submit-btn`, captures full screenshots (`screenshot_path`), extracts protocol, and catches altered selector anomalies.
  - OpenTelemetry correlation (`get_or_create_trace_id`): correlates trace context or generates traceable IDs.
  - Database persistence: persists submission record in `SubmissaoRessarcimento` table and updates `CicloCondominio.status_ciclo` to `ENVIADO` upon success.
- `backend/app/models/entities.py`: Made `SubmissaoRessarcimento.ciclo_id` optional (`nullable=True`) to allow standalone/drill submissions while retaining foreign key relationship with `CicloCondominio`.
- `backend/app/schemas/condo.py`: Updated `SubmissaoRessarcimentoCreate` and `SubmissaoRessarcimentoResponse` to allow optional `ciclo_id`.
- `backend/app/services/__init__.py`: Exported `SubmissionPayload`, `SubmissionReceipt`, `get_or_create_trace_id`, `resolve_target_url`, and `submit_reimbursement`.
- `backend/tests/test_bitrix_submitter.py`: Full test suite covering mock server rendering, altered selector injection, error simulation (500/503), field validation, HTTP multipart submission, database persistence, cycle status promotion to `ENVIADO`, Playwright browser automation, and browser screenshot capture on altered selector.

## TDD Lifecycle
1. Red Phase:
   - Authored test suite `backend/tests/test_bitrix_submitter.py` referencing `bitrix_submitter` and `mock_bitrix` components.
   - Executed `pytest backend/tests/test_bitrix_submitter.py`.
   - Result: Failed with `ModuleNotFoundError: No module named 'app.services.bitrix_submitter'` as expected.
2. Green Phase:
   - Implemented `mock_bitrix/main.py`.
   - Implemented `backend/app/services/bitrix_submitter.py`.
   - Updated `entities.py`, `condo.py`, and `__init__.py`.
   - Executed `pytest backend/tests/test_bitrix_submitter.py`.
   - Result: All 10 tests passed.
3. Regression & Full Verification:
   - Executed full test suite `pytest`.
   - Result: All 51 tests passed in 14.42s (scaffolding, models, parser, audit engine, email worker, and submitter).
   - Executed emoji verification across modified codebase and commit diff: 0 emojis found.

## Test Execution Output
```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\luiz_\_DS\luas_projects\luas_condo
plugins: anyio-4.13.0
collected 51 items

backend\tests\test_audit_engine.py ........                              [ 15%]
backend\tests\test_bitrix_submitter.py ..........                        [ 35%]
backend\tests\test_email_worker.py ............                          [ 58%]
backend\tests\test_models.py .........                                   [ 76%]
backend\tests\test_parser_boleto.py ........                             [ 92%]
tests\test_scaffolding.py ....                                           [100%]

============================== warnings summary ===============================
backend/tests/test_bitrix_submitter.py::test_submit_reimbursement_browser_success
  websockets.legacy is deprecated; see https://websockets.readthedocs.io/en/stable/howto/upgrade.html for upgrade instructions
backend/tests/test_bitrix_submitter.py::test_submit_reimbursement_browser_success
  websockets.server.WebSocketServerProtocol is deprecated

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 51 passed, 2 warnings in 14.42s =======================
```

## Observations and Notes
- Target URL Resolution: By default in test and CI environments (`MOCK_SUBMISSION=true`), the submitter routes submissions to `MOCK_BITRIX_URL` (`http://mock-bitrix:8080` or `http://localhost:8080`), ensuring no mock tickets are ever submitted to the real Ibagy CRM.
- Playwright Headless Verification: Playwright browser automation works reliably in headless mode on Windows, validating both successful submissions and error handling with full screenshots stored in the designated screenshot path.
- Zero Emojis: Strictly verified and enforced across all files, tests, commit messages, and documentation.

---

## Review Finding Fix: Fast Failure on Missing Local Files in Browser Submission
- Status: DONE
- Commit Hash: 0f4c124af7e3ecc0234f5b7c0b81d955941d584e
- Single-command test execution: 54 passed in 7.81s (all 41 existing + 13 submitter tests)

### Root Cause
In `backend/app/services/bitrix_submitter.py` (`_submit_via_browser`), if `boleto_path` or `comprovante_path` pointed to a non-existent local file and raw byte buffers were not supplied, the method previously created empty temporary files (`payload.boleto_bytes or b""`) and uploaded 0-byte files instead of failing fast before launching the browser.

### Solution Implemented
1. Validated and prepared files using `_prepare_file_content` before opening or launching Playwright. If any file path does not exist on disk, it fails fast by raising `FileNotFoundError` and immediately returning an `ERRO` receipt matching `_submit_via_http`.
2. Normalized trailing slash handling in `resolve_target_url` by stripping trailing slashes on base URLs before appending `/condominioressarcimento/ressarcimento/`.
3. Added `filterwarnings` in `backend/pyproject.toml` to ignore websockets deprecation warnings during test runs.
4. Added new test cases in `backend/tests/test_bitrix_submitter.py`:
   - `test_submit_reimbursement_browser_fails_fast_on_missing_file`: verifies fast ERRO receipt with "arquivo nao encontrado" when file path does not exist.
   - `test_submit_reimbursement_http_fails_fast_on_missing_file`: verifies matching HTTP fast failure behavior.
   - `test_resolve_target_url_normalizes_trailing_slashes`: verifies trailing slash normalization across base URL configurations.

### Test Execution Output
```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\luiz_\_DS\luas_projects\luas_condo
plugins: anyio-4.13.0
collected 54 items

backend\tests\test_audit_engine.py ........                              [ 14%]
backend\tests\test_bitrix_submitter.py .............                     [ 38%]
backend\tests\test_email_worker.py ............                          [ 61%]
backend\tests\test_models.py .........                                   [ 77%]
backend\tests\test_parser_boleto.py ........                             [ 92%]
tests\test_scaffolding.py ....                                           [100%]

============================== warnings summary ===============================
backend/tests/test_bitrix_submitter.py::test_submit_reimbursement_browser_success
  websockets.legacy is deprecated; see https://websockets.readthedocs.io/en/stable/howto/upgrade.html for upgrade instructions
backend/tests/test_bitrix_submitter.py::test_submit_reimbursement_browser_success
  websockets.server.WebSocketServerProtocol is deprecated

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 54 passed, 2 warnings in 7.81s ========================
```

