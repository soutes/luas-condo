# Task 7 Brief: OpenTelemetry Instrumentation, Correlated Tracing & LGPD Sanitization

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (code, tests, comments, commit messages, config).
- Zero PII in Telemetry: No CPFs, passwords, app secrets, or tenant credentials allowed in span attributes, Prometheus labels, or log records.
- OpenTelemetry compliant: Trace IDs must be 32-character hex strings or valid OTel TraceIDs shared across Ingestion, Parsing, Audit, and Submission.

## Task Scope & Files
- Create: `backend/app/core/telemetry.py` (Tracer, span context management, metrics, sanitizer)
- Update: `backend/app/main.py` (Expose `/metrics` Prometheus endpoint and OTel middleware)
- Test: `backend/tests/test_telemetry.py`

## Detailed Requirements
1. **Trace Propagation & Context**:
   - `get_tracer()`: Returns configured OpenTelemetry Tracer.
   - `trace_step(name: str, attributes: Optional[dict] = None)`: Context manager creating spans, recording errors, and propagating `trace_id`.
   - `get_current_trace_id() -> str`: Returns active trace ID or generates a valid 32-char hex trace ID.

2. **Metrics Collection (Prometheus)**:
   - Counter: `condo_submissions_total` (labels: `status`, `target`)
   - Histogram: `condo_reimbursement_amount_brl`
   - Histogram: `condo_processing_duration_seconds`
   - Gauge: `condo_cycle_sla_days_remaining`
   - Function: `get_prometheus_metrics() -> str` (returning Prometheus exposition format for `/metrics`).

3. **LGPD & Credential Sanitizer**:
   - `sanitize_log_data(data: dict) -> dict`: Recursively scrubs:
     - CPFs (regex `\d{3}\.\d{3}\.\d{3}-\d{2}`) -> `[REDACTED_CPF]`
     - Sensitive keys (`password`, `email_pass`, `secret`, `token`, `chave_pix`) -> `[REDACTED_SECRET]`
   - `sanitize_text(text: str) -> str`: Scrubs inline CPFs and sensitive tokens.

4. **FastAPI Application Integration**:
   - Create `backend/app/main.py` (if not present) with `/metrics` and `/api/health` endpoints and OTel trace injection.

## Acceptance Criteria
- [ ] TDD followed: `backend/tests/test_telemetry.py` written first and tested to fail, then implemented and verified to pass.
- [ ] Sanitizer completely masks CPFs and passwords.
- [ ] Trace IDs are correctly propagated across steps and attached to span events.
- [ ] Prometheus metrics increment correctly on events.
- [ ] `/metrics` endpoint returns valid Prometheus plain text.
- [ ] All test suites pass: `pytest` passes all scaffolding, model, parser, audit, worker, submitter, and telemetry tests.
- [ ] Commit message: `feat: instrument opentelemetry with trace propagation and lgpd sanitization` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-7-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
