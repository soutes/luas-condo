# Agent Team Specification

This document specifies the autonomous agent team powering the Luas Condo audit and reimbursement system. The architecture organizes specialized agents with distinct responsibilities, deterministic tooling, clear input/output contracts, and structured communication patterns.

## Agent Team Overview

The multi-agent system comprises four primary agents:

1. **Extractor Agent**: Ingestion, OCR/text extraction, and document normalization.
2. **Legal Auditor Agent**: Statutory segregation and financial obligation calculation.
3. **Submitter Agent**: External portal automation, dispute package compilation, and submission.
4. **On-Call Responder Agent**: Telemetry monitoring, automated self-healing, and incident escalation.

---

## 1. Extractor Agent

### Role
Automates the retrieval and parsing of condominium fee statements (boletos), itemized breakdown sheets (rateio), and bank transaction receipts (comprovantes de pagamento PIX).

### Core Responsibilities
- Polls or listens via IMAP on a dedicated incoming mailbox for monthly condominium communications from property administrators (e.g., SCI Syndkos for Edifício Villa Salomy).
- Extracts and validates attached PDF documents and embedded metadata.
- Implements idempotent message processing to prevent duplicate cycle creation.
- Normalizes parsed text, line items, monetary figures, barcode/digitable lines, due dates, and reference periods into structured database entities.

### Tools and Technologies
- **Email Worker**: Python `imaplib`, `email` package with read-only IMAP access and UID tracking.
- **PDF Parser**: `pypdf` and `pdfplumber` layout-aware extraction routines tailored to Brazilian condominium statement layouts.
- **Validation Suite**: Checksum validation for Brazilian bank boleto digitable lines (linha digitavel) and PIX end-to-end identifiers.

### Inputs and Outputs
- **Input**: Raw RFC 822 email messages with PDF attachments.
- **Output**: Persisted `CicloCondominio` record with associated `ItemRateio` line items in initial status `RASCUNHO` (Draft).

### Communication Pattern
- Asynchronous polling or webhook trigger.
- Emits domain event `CondoBillIngested` with cycle identifier and trace context to notify the Legal Auditor Agent.

---

## 2. Legal Auditor Agent

### Role
Executes statutory analysis on itemized condominium expenses according to the Brazilian Tenant-Landlord Law (Lei Federal nº 8.245/1991).

### Core Responsibilities
- Segregates ordinary expenses (despesas ordinarias) governed by Article 23 from extraordinary expenses (despesas extraordinarias) governed by Article 22.
- Identifies reserve fund provisions (fundo de reserva), capital improvement funds (fundo de melhorias), facade painting, structural engineering assessments, and fire insurance quotas.
- Applies statutory legal justification tags to every line item, citing exact legal articles, paragraphs, and precedent rulings.
- Computes the precise reimbursement credit (`total_reembolso`) due to the tenant (targeting the reference benchmark of R$ 354,50 for standard Villa Salomy cycles).
- Calculates landlord vs tenant liabilities and compiles an audit summary for human review.

### Tools and Technologies
- **Deterministic Audit Engine**: Python rule-based classifier with regex matching, keyword heuristics, and normalization dictionaries.
- **Statutory Ruleset**: Encoded mapping of Brazilian Law 8.245/1991 (Articles 22 and 23).
- **Financial Precision Engine**: Python `Decimal` arithmetic avoiding floating-point rounding inaccuracies.

### Inputs and Outputs
- **Input**: `CicloCondominio` record with unclassified `ItemRateio` entries.
- **Output**: Updated `CicloCondominio` in status `AUDITADO` (Audited), with each item assigned a `responsabilidade` (`LOCATARIO` or `LOCADOR`), statutory justification text, and calculated `total_reembolso`.

### Communication Pattern
- Consumes `CondoBillIngested` events or processes cycles in status `RASCUNHO`.
- Produces an audit report and publishes notification to the frontend dashboard for human-in-the-loop validation.

---

## 3. Submitter Agent

### Role
Executes automated filing of reimbursement disputes and supporting documentation with the property manager's portal (Ibagy via Bitrix24).

### Core Responsibilities
- Assembles the complete formal reimbursement claim package:
  - Formatted dispute memorandum citing lease contract number, unit details, reference month, and itemized amounts.
  - Original condominium boleto PDF.
  - Payment receipt (comprovante PIX) confirming tenant settlement of the full condominium bill.
- Authenticates and navigates the property manager's Bitrix24 dispute portal.
- Handles automated form population, document upload, and submission triggering.
- Extracts external confirmation protocols, timestamps, and receipt tokens.
- Supports transparent fallback to REST API endpoints or mock environments for local development and offline testing.

### Tools and Technologies
- **Headless Browser Engine**: Playwright (Chromium) with dynamic selector resilience and screenshot logging.
- **HTTP Client**: `httpx` with timeout management and exponential backoff retry.
- **Mock Service**: Isolated FastAPI mock server emulating Bitrix24 form interactions and protocol issuance.

### Inputs and Outputs
- **Input**: User-approved `CicloCondominio` (status `APROVADO`), confirmed dispute memorandum, and validated file paths.
- **Output**: Persisted `SubmissaoRessarcimento` record containing external protocol ID, submission timestamp, HTTP status, and lifecycle transition to `ENVIADO`.

### Communication Pattern
- Synchronous or queued trigger from the Web Frontend upon human user approval (`POST /api/ciclos/{id}/submeter`).
- Emits telemetry spans and Prometheus counter increments (`condo_submissions_total{status="success|failed"}`).

---

## 4. On-Call Responder Agent

### Role
Provides 24/7 autonomous monitoring, incident triage, self-healing remediation, and human escalation for operational disruptions.

### Core Responsibilities
- Listens to Prometheus Alertmanager alert webhooks for user-impacting conditions:
  - `CondoSubmissionFailed`: Fired when a reimbursement submission to Bitrix24 fails.
  - `CondoSlaBreachWarning`: Fired when a monthly cycle has fewer than 3 days remaining before the reimbursement deadline without submission.
- Triages alerts by correlating incoming events with database state, incident logs, and OpenTelemetry trace identifiers (`trace_id`).
- Executes automated self-healing remediation runbooks:
  - **Selector Drift Repair**: Detects UI element changes on Bitrix24 and applies alternative fallback selectors.
  - **HTTP 5xx / Timeout Replay**: Retries transient gateway failures using dead-letter queue replay with jitter.
- Escalates unrecoverable failures (e.g., expired credentials, portal authentication changes, rejected disputes) to human operators with diagnostic reports and suggested remediation steps.

### Tools and Technologies
- **Incident Engine**: `app.agents.on_call` incident state machine managing `IncidenteOnCall` lifecycle (`ABERTO` -> `EM_ANDAMENTO` -> `RESOLVIDO` / `ESCALADO`).
- **Telemetry Ingestion**: OpenTelemetry trace context propagation and Prometheus Alertmanager webhook receiver (`POST /api/alerts/webhook`).
- **Notification Client**: Outbound webhook dispatcher alerting engineering and tenant operations.

### Inputs and Outputs
- **Input**: Alertmanager JSON webhook payloads containing alert name, severity, labels, annotations, and trace correlation ID.
- **Output**: Persisted `IncidenteOnCall` entity, automated remediation action execution, and diagnostic incident timeline.

### Communication Pattern
- Inbound HTTP webhook from Alertmanager.
- Outbound remediation actions directly to backend execution services or database state.
- Outbound alert dispatches to human operations channels when escalation is required.

---

## Team Collaboration Matrix

| Agent | Trigger | Upstream Dependency | Downstream Hand-off | Primary Failure Mode |
|---|---|---|---|---|
| Extractor Agent | Email received / Cron | Property management email | Legal Auditor Agent | Statement layout drift |
| Legal Auditor Agent | Cycle extracted | Extractor Agent | Human Reviewer (UI) | Unrecognized line item |
| Submitter Agent | Human user approval | Legal Auditor Agent + User | External Bitrix24 Portal | Portal downtime / selector change |
| On-Call Agent | Alertmanager webhook | Submitter Agent / Prometheus | Engineering Team / Self | Repeated external service failure |

---

## Design Principles

1. **No Emojis**: All documentation, logs, code, and user interface elements adhere strictly to plain text and SVG/Lucide iconography.
2. **Deterministic Rules Over Generative Hallucinations**: Financial and statutory classifications rely on deterministic rulesets verified against Brazilian Law 8.245/1991.
3. **Trace Context Propagation**: Every agent action carries a unified OpenTelemetry `trace_id` for end-to-end request tracing.
4. **Human-in-the-Loop Safeguard**: External filings with legal consequences require explicit human confirmation via the web dashboard.
