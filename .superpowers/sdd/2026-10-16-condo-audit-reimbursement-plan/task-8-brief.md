# Task 8 Brief: User Impact Alerting & Autonomous On-Call Responder Agent (Self-Healing)

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (code, tests, comments, commit messages, config).
- Alerts must be triggered on real user impact (failed submission, SLA breach risking refund), not simple CPU/memory spikes.
- The On-Call Agent must be autonomous: triggered via Alertmanager webhook, inspect the incident's trace/database context, execute an automated fix (self-healing), and record resolution.

## Task Scope & Files
- Create: `monitoring/alert_rules.yml` (Prometheus Alertmanager rules for CondoSubmissionFailed & CondoSlaBreachWarning)
- Create: `backend/app/agents/on_call.py` (Autonomous on-call responder agent)
- Create: `backend/app/routes/alert_webhook.py` (FastAPI route `POST /api/alerts/webhook`)
- Update: `backend/app/main.py` (Register alert webhook router)
- Test: `backend/tests/test_on_call_agent.py`

## Detailed Requirements
1. **Prometheus Alert Rules (`monitoring/alert_rules.yml`)**:
   - `CondoSubmissionFailed`: Alert on `increase(condo_submissions_total{status="failed"}[5m]) > 0` (user impact: dispute not filed).
   - `CondoSlaBreachWarning`: Alert on `condo_cycle_sla_days_remaining < 3` (user impact: imminent loss of monthly reimbursement window).

2. **Alertmanager Webhook Contract**:
   `POST /api/alerts/webhook` receiving Alertmanager payload:
   ```json
   {
     "status": "firing",
     "alerts": [
       {
         "status": "firing",
         "labels": {
           "alertname": "CondoSubmissionFailed",
           "severity": "critical"
         },
         "annotations": {
           "trace_id": "32_hex_chars",
           "error_type": "SELECTOR_MISMATCH",
           "description": "Field contrato could not be located in Bitrix24 DOM"
         }
       }
     ]
   }
   ```

3. **On-Call Agent Self-Healing Capabilities (`backend/app/agents/on_call.py`)**:
   - Core function: `handle_incident_alert(alert_data: dict, db_session: Session) -> IncidenteOnCall`
   - Self-healing actions:
     - **Selector Mismatch / Form Schema Drift**: Detects `SELECTOR_MISMATCH`, inspects available alternative field mappings, applies dynamic selector repair, and re-executes the pending submission.
     - **Transient HTTP 5xx / Network Timeout**: Detects `HTTP_5XX_TIMEOUT`, switches to resilient direct HTTP multipart fallback, replays dead-letter submission queue.
     - **Unrecoverable Issue**: If data cannot be repaired automatically, sets status to `ESCALADO_HUMANO` with clear diagnostic reason.
   - Persistence:
     - Creates `IncidenteOnCall` entity in database (`trace_id`, `alerta_nome`, `diagnostico`, `acao_executada`, `status`).
     - Updates corresponding `SubmissaoRessarcimento` to `SUCESSO` upon successful remediation.

## Acceptance Criteria
- [ ] TDD followed: `backend/tests/test_on_call_agent.py` written first and tested to fail, then implemented and verified to pass.
- [ ] `POST /api/alerts/webhook` successfully receives Alertmanager alerts.
- [ ] On-Call Agent fixes simulated selector mismatch, re-submits successfully, and marks incident `RESOLVIDO`.
- [ ] On-Call Agent fixes simulated 500 error via retry fallback, re-submits successfully, and marks incident `RESOLVIDO`.
- [ ] IncidenteOnCall record is saved in database with diagnostic and action taken.
- [ ] All test suites pass: `pytest` passes all scaffolding, model, parser, audit, worker, submitter, telemetry, and on-call tests.
- [ ] Commit message: `feat: implement on-call responder agent for automated incident resolution` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-8-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
