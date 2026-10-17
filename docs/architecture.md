# System Architecture Specification

This document details the architectural topology, service components, data models, telemetry, and containerization design of the Luas Condo platform.

---

## 1. High-Level Architecture Overview

Luas Condo is designed as a distributed, containerized micro-service application with decoupled ingestion, deterministic legal auditing, automated portal submission, and comprehensive observability.

```
+-------------------------------------------------------------------------------+
|                               Luas Condo Platform                             |
+-------------------------------------------------------------------------------+
|                                                                               |
|  [ Inbound Email ]                                                            |
|         |                                                                     |
|         v                                                                     |
|  +--------------------+                                                       |
|  |   Email Worker     | ---> [ Boleto Parser ]                                |
|  |   (IMAP Service)   |      (pypdf / pdfplumber)                             |
|  +--------------------+               |                                       |
|                                       v                                       |
|  +--------------------+       +--------------------+                          |
|  |   React Frontend   | <---> |   FastAPI Backend  | <---> [ PostgreSQL 16 ]  |
|  |   (Vite Dashboard) |       |   (REST API)       |       (Relational Store) |
|  +--------------------+       +--------------------+                          |
|                                       |                                       |
|                                       v                                       |
|  +--------------------+       +--------------------+                          |
|  |  On-Call Responder | <---  |  Bitrix Submitter  | ---> [ Bitrix24 / Mock ] |
|  |  (Self-Healing)    |       |  (Playwright HTTP) |       (External Portal)  |
|  +--------------------+       +--------------------+                          |
|           ^                                                                   |
|           | Webhook Alerts                                                    |
|  +--------------------+       +--------------------+                          |
|  |    Alertmanager    | <---  |     Prometheus     |                          |
|  |    & Prometheus    |       |     (Metrics)      |                          |
|  +--------------------+       +--------------------+                          |
|                                       |                                       |
|                                       v                                       |
|                               +--------------------+                          |
|                               |  Grafana Dashboard |                          |
|                               |  (Visualization)   |                          |
|                               +--------------------+                          |
|                                                                               |
+-------------------------------------------------------------------------------+
```

---

## 2. Core Components

### 2.1 Backend Service (`backend`)
- **Framework**: FastAPI (Python 3.12+), ASGI server powered by Uvicorn.
- **ORM & Data Layer**: SQLAlchemy 2.0 with PostgreSQL driver (`psycopg2-binary`).
- **Data Validation**: Pydantic v2 schemas providing strict type checking and JSON serialization.
- **Key Modules**:
  - `app.routes.ciclos`: REST API endpoints for condo cycle management and submission dispatch.
  - `app.routes.alerts`: Webhook receiver for Prometheus Alertmanager notifications.
  - `app.agents.audit_engine`: Deterministic segregation rules according to Brazilian Law 8.245/1991.
  - `app.agents.bitrix_submitter`: Browser automation with Playwright and fallback HTTP client.
  - `app.agents.on_call`: Self-healing remediation engine and incident manager.
  - `app.core.telemetry`: OpenTelemetry tracer and Prometheus metrics exporter setup.

### 2.2 Frontend Service (`frontend`)
- **Framework**: React 18 with TypeScript and Vite 5.
- **Styling**: Tailwind CSS configured with a dark slate palette (`#020617`, `#0f172a`, `#1e293b`), Luas.Ai accent colors (`#f7941d`), and clean straight corners (`rounded-none`).
- **Icons**: Lucide React SVG iconography (strictly adhering to the no-emoji mandate).
- **Testing**: Vitest with React Testing Library and JSDOM environment.
- **Key Components**:
  - `CycleCard`: Summary cards displaying month, due date, status badge, and amounts.
  - `AuditTable`: Line-by-line categorization table with tenant/landlord filter tabs and legal justification tooltips.
  - `SubmissionPreview`: Memo editor, attachment validator (boleto and comprovante PIX), and one-click submission trigger.

### 2.3 Relational Database (`db`)
- **Engine**: PostgreSQL 16 (Alpine-based Docker container).
- **Core Entities**:
  - `CicloCondominio`: Monthly statement lifecycle state, totals, due date, contract ID.
  - `ItemRateio`: Itemized rateio rows with description, amount, classification (`LOCATARIO` or `LOCADOR`), and legal citations.
  - `SubmissaoRessarcimento`: Portal submission attempts, external protocol IDs, timestamps, and receipt records.
  - `IncidenteOnCall`: Operational alerts, triage state (`ABERTO`, `EM_ANDAMENTO`, `RESOLVIDO`, `ESCALADO`), and runbook audit logs.

### 2.4 External Portal Emulation (`mock-bitrix`)
- **Service**: Lightweight FastAPI service mimicking the Ibagy Bitrix24 reimbursement form.
- **Purpose**: Enables robust offline development, integration tests, and reproducible demonstration without external network dependencies.
- **Endpoints**: Supports form submission, file upload handling, protocol generation, and configurable failure injection (HTTP 500, selector changes) for resilience verification.

### 2.5 Observability Stack (`prometheus` & `grafana`)
- **Metrics Collection**: Prometheus scrapes the backend `/metrics` endpoint.
- **Alert Rules**: Evaluates `monitoring/alert_rules.yml` for user-impact conditions (`CondoSubmissionFailed`, `CondoSlaBreachWarning`).
- **Visualization**: Grafana preconfigured with dashboard tiles for submission success rates, cycle SLA countdowns, and audit latency histograms.

---

## 3. Telemetry and LGPD / PII Compliance

### 3.1 Distributed Tracing
- OpenTelemetry SDK instrumentation across HTTP requests, internal agent calls, and external requests.
- Every incoming request and background workflow receives or propagates a standard `trace_id`.
- The `trace_id` is linked to submission records and incident reports, enabling complete root-cause tracing from the frontend UI to backend logs.

### 3.2 Metrics Specification
- `condo_submissions_total{status="success|failed"}`: Counter measuring reimbursement dispatch outcomes.
- `condo_cycle_sla_days_remaining`: Gauge tracking days remaining before the monthly reimbursement filing window closes.
- `condo_audit_duration_seconds`: Histogram measuring execution duration of the deterministic legal audit engine.
- `condo_oncall_incidents_total{status="..."}`: Counter tracking auto-remediated vs escalated incidents.

### 3.3 LGPD and PII Sanitization
- Under the Brazilian General Data Protection Law (Lei Geral de Proteção de Dados - LGPD, Lei nº 13.709/2018), tenant personal data must be safeguarded.
- **Sanitization Pipeline**: All logs, OpenTelemetry span attributes, and metric tags pass through an automated PII filter:
  - Brazilian Taxpayer IDs (CPF) are masked: `***.***.123-**`.
  - Banking identifiers, PIX keys, and account numbers are redacted before telemetry persistence.
  - Raw tenant names in logs are truncated or anonymized.

---

## 4. Containerization and Network Topology

The solution is orchestrated via Docker Compose:

| Service | Container Name | Internal Port | Host Port | Role |
|---|---|---|---|---|
| `db` | `luas_condo_db` | 5432 | 5432 | PostgreSQL 16 database |
| `backend` | `luas_condo_backend` | 8000 | 8000 | FastAPI REST API & Agents |
| `frontend` | `luas_condo_frontend` | 5173 | 5173 | React + Vite UI |
| `mock-bitrix` | `luas_condo_mock_bitrix` | 8080 | 8080 | Mock Bitrix24 portal |
| `prometheus` | `luas_condo_prometheus` | 9090 | 9090 | Metrics collection & Alerting |
| `grafana` | `luas_condo_grafana` | 3000 | 3001 | Observability dashboard |

All services communicate over an isolated Docker bridge network. Service dependencies ensure PostgreSQL is healthy before backend startup.
