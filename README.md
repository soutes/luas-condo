# Luas Condo (Condo Audit & Reimbursement System)

Automated system for auditing condo expense statements (Edifício Villa Salomy / SCI Syndkos) and submitting legal reimbursement claims to real estate management (Ibagy / Bitrix24), built according to Brazilian Tenant-Landlord Law (Lei nº 8.245/1991).

## Problem Description

Tenants frequently receive monthly condominium bills containing mixed charges:
- **Ordinary Expenses**: Cleaning, routine maintenance, concierge, water, and gas (tenant's legal duty).
- **Extraordinary Expenses & Reserve Funds**: Structural repairs, facade maintenance, fire safety certifications, and reserve fund contributions (landlord's legal duty under Art. 22 of Brazilian Law 8.245/1991).

Tenants must manually audit bills, calculate the exact reimbursement, pay the bill, obtain payment receipts, and submit a formal dispute with attachments to the property manager's portal. Delayed or missed disputes cause direct financial loss.

## System Architecture

- **Ingestion**: Read-only IMAP worker listening for condo invoices and PIX payment receipts.
- **Audit Engine**: Deterministic extraction and legal segregation engine.
- **Web Submitter**: Automated submission to Ibagy Bitrix24 portal with Playwright and mock fallback.
- **Full-Stack Application**: FastAPI backend, PostgreSQL database, and modern React dashboard.
- **Observability**: OpenTelemetry distributed tracing, Prometheus metrics, user-impact alerting, and an on-call self-healing responder agent.

## Documentation, Specs & Task Tracker

- **Public Task Tracker**: [GitHub Issues / Acceptance Criteria](https://github.com/soutes/luas-condo/issues)
- **Design Specification**: [`docs/superpowers/specs/2026-10-16-condo-audit-reimbursement-design.md`](docs/superpowers/specs/2026-10-16-condo-audit-reimbursement-design.md)
- **Implementation Plan**: [`docs/superpowers/plans/2026-10-16-condo-audit-reimbursement-plan.md`](docs/superpowers/plans/2026-10-16-condo-audit-reimbursement-plan.md)
