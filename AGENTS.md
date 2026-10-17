# AGENTS.md: Autonomous Agent System Guide

Welcome to the Luas Condo multi-agent platform. This document serves as the top-level architectural context and entrypoint for AI coding agents and human reviewers navigating this repository.

---

## Mission Statement

Luas Condo automates the statutory audit of Brazilian condominium fee statements (boletos and rateio) and the filing of reimbursement claims with real estate property management portals (Ibagy via Bitrix24), strictly abiding by Brazilian Tenant-Landlord Law (Lei Federal nº 8.245/1991).

---

## Modular Documentation Structure

To ensure efficient context management and avoid context-window bloat, detailed specifications are modularized across dedicated documents:

1. **Agent Team Specification**: [`docs/team.md`](docs/team.md)
   - Detailed roles, responsibilities, deterministic tools, and communication patterns for all four autonomous agents.
2. **Agent Process Specification**: [`docs/process.md`](docs/process.md)
   - Operational lifecycle (Ingestion -> Legal Audit -> Human Review -> Submission -> Monitoring), human-in-the-loop safeguards, error escalation paths, and self-healing runbooks.
3. **System Architecture Specification**: [`docs/architecture.md`](docs/architecture.md)
   - Full-stack service topology (FastAPI, React, PostgreSQL, Mock Bitrix), distributed tracing with OpenTelemetry, Prometheus alerting, Grafana dashboards, and Docker Compose containerization.

---

## Agent Team at a Glance

The system orchestrates four specialized agents:

1. **Extractor Agent**:
   - **Responsibility**: Ingests condominium statements and PIX payment receipts from email, extracts text and layout data, and creates draft cycles (`CicloCondominio`).
   - **Tools**: IMAP email worker, `pdfplumber`, `pypdf`, banking barcode validators.
   - **Reference Spec**: See [`docs/team.md#1-extractor-agent`](docs/team.md).

2. **Legal Auditor Agent**:
   - **Responsibility**: Deterministically segregates ordinary tenant expenses (Art. 23) from extraordinary landlord expenses (Art. 22), attaches statutory legal justifications, and calculates reimbursement balances (e.g., target R$ 354,50).
   - **Tools**: Deterministic audit engine, statutory classification ruleset, `Decimal` arithmetic.
   - **Reference Spec**: See [`docs/team.md#2-legal-auditor-agent`](docs/team.md).

3. **Submitter Agent**:
   - **Responsibility**: Compiles the formal dispute package, generates the submission memorandum, and dispatches the claim to the Ibagy Bitrix24 portal.
   - **Tools**: Playwright headless browser automation, HTTP fallback client, mock Bitrix service.
   - **Reference Spec**: See [`docs/team.md#3-submitter-agent`](docs/team.md).

4. **On-Call Responder Agent**:
   - **Responsibility**: Wakes up on Prometheus Alertmanager alerts (`CondoSubmissionFailed`, `CondoSlaBreachWarning`), triages operational incidents, executes automated self-healing runbooks (selector drift repair, HTTP 5xx retry), and escalates unrecoverable faults.
   - **Tools**: Autonomous incident manager (`app.agents.on_call`), OpenTelemetry context injector, alert webhook endpoint (`POST /api/alerts/webhook`).
   - **Reference Spec**: See [`docs/team.md#4-on-call-responder-agent`](docs/team.md).

---

## Operating Guidelines for AI Agents

When interacting with or extending this codebase, all autonomous agents must adhere to these inviolable guidelines:

1. **Global Zero-Emoji Constraint**:
   - Never use emojis anywhere in the repository, including code, comments, commit messages, documentation, user interfaces, or test fixtures. Use plain text or SVG/Lucide icons.

2. **Documentation Language**:
   - All architecture, design documentation, code comments, and commit messages must be written in English.

3. **Deterministic Financial Rules**:
   - All legal classifications and currency calculations must follow deterministic rules based on Lei nº 8.245/1991. Do not use generative approximations or floating-point math for money values.

4. **Trace Context Propagation**:
   - Always propagate OpenTelemetry trace identifiers (`trace_id`) across asynchronous events, database records, and external dispatch routines.

5. **Human-in-the-Loop Verification**:
   - The final submission of legal dispute claims requires explicit user confirmation via the frontend dashboard.
