# Agent Process Specification

This document details the operational lifecycle, human-in-the-loop governance, error escalation hierarchies, and autonomous self-healing mechanisms implemented in the Luas Condo platform.

---

## 1. End-to-End Lifecycle

The condominium expense audit and reimbursement workflow follows a five-stage progressive lifecycle:

```
[ Ingestion & OCR ] 
         | (Extractor Agent)
         v
 [ Legal Audit ]
         | (Legal Auditor Agent)
         v
[ Human Review ]
         | (Web Dashboard Approval)
         v
  [ Submission ]
         | (Submitter Agent)
         v
 [ Monitoring ]
           (On-Call Responder Agent)
```

### Stage 1: Ingestion and Normalization (Extractor Agent)
1. **Detection**: The Extractor Agent monitors the configured inbox for inbound emails from condominium administrators (e.g., SCI Syndkos, Edifício Villa Salomy).
2. **De-duplication**: Email headers and UID checksums are evaluated against the database. Duplicate messages are silently skipped to preserve idempotency.
3. **Extraction**: Attached PDF files are parsed to extract header metadata (contract number `09638.003.03`, due date, reference month, total condominium fee) and individual rateio line items.
4. **State Transition**: A new cycle is created in the database with status `RASCUNHO` (Draft).

### Stage 2: Statutory Audit and Segregation (Legal Auditor Agent)
1. **Expense Classification**: Each line item in the breakdown is evaluated against deterministic classification rules based on Brazilian Tenant-Landlord Law (Lei Federal nº 8.245/1991).
2. **Segregation**:
   - Items under Article 23 (ordinary operational expenses: cleaning, routine maintenance, concierge, basic utilities) are designated as `LOCATARIO` (tenant responsibility).
   - Items under Article 22, Inciso X, alíneas 'a' through 'g' (extraordinary expenses: reserve fund additions, structural maintenance, facade restoration, capital improvement quotas, fire safety equipment) are designated as `LOCADOR` (landlord responsibility).
3. **Calculation**:
   - `total_ordinario`: Total tenant liability.
   - `total_extraordinario`: Total landlord liability.
   - `total_reembolso`: Amount to be credited back to the tenant (targeting R$ 354,50 on the reference cycle).
4. **State Transition**: The cycle transitions to status `AUDITADO` (Audited).

### Stage 3: Human-in-the-Loop Review and Verification (Web Frontend)
1. **Presentation**: The tenant accesses the React dashboard (`http://localhost:5173`).
2. **Inspection**: The tenant inspects the itemized audit table, reviews statutory justifications, checks the computed reimbursement figure, and verifies required attachments (boleto and comprovante PIX).
3. **Memo Customization**: The tenant reviews and optionally edits the dispute memorandum text.
4. **Explicit Authorization**: The tenant clicks "Aprovar e Enviar para Ibagy" (`POST /api/ciclos/{id}/submeter`). This human confirmation prevents unintended or contested dispute filings.
5. **State Transition**: Cycle status updates to `APROVADO` (Approved).

### Stage 4: Portal Submission and Protocol Capture (Submitter Agent)
1. **Package Assembly**: The agent builds the dispatch bundle, combining the tenant memorandum, the parsed boleto PDF, and the payment receipt.
2. **Browser Automation**: Playwright navigates to the Ibagy Bitrix24 portal, fills in contract fields, attaches documents, and submits the dispute ticket.
3. **Fallback Execution**: If browser automation fails or if running in mock mode, the agent uses the direct API client or local mock service.
4. **Receipting**: An external protocol identifier is captured, stored in `SubmissaoRessarcimento`, and linked to the cycle.
5. **State Transition**: Cycle status moves to `ENVIADO` (Submitted).

### Stage 5: Continuous Monitoring and SLA Tracking (On-Call Agent)
1. **Metric Scraping**: Prometheus periodically queries application metrics (`condo_submissions_total`, `condo_cycle_sla_days_remaining`).
2. **Rule Evaluation**: Alertmanager monitors alert thresholds (`CondoSubmissionFailed`, `CondoSlaBreachWarning`).
3. **Self-Healing**: If a failure alert triggers, the On-Call Agent executes autonomous remediation runbooks.
4. **Resolution or Escalation**: If auto-healing succeeds, the incident is closed; otherwise, it is escalated to human on-call personnel.

---

## 2. Human-in-the-Loop Architecture

While routine data extraction and legal categorization are fully automated, external legal submissions require human sign-off for the following reasons:

- **Legal Bindingness**: A reimbursement claim submitted to a property manager is a formal commercial notice under Brazilian civil contract law.
- **Proof of Payment Precondition**: Landlord reimbursement claims are only valid after the tenant has paid the master condominium boleto. Human review confirms that the corresponding bank receipt (comprovante PIX) is verified and attached.
- **Tone and Context Flexibility**: Tenants may add special observations or contextual notes to the submission memo before filing.
- **Override Capability**: In edge cases where unusual condo line items require specialized agreement between tenant and owner, the tenant retains manual override control over item segregation.

---

## 3. Error Escalation Framework

Operational failures are categorized into two tiers to optimize recovery speed while preserving safety:

### Tier 1: Transient and Recoverable Errors
- **Network Timeouts**: Intermittent connection latency between the backend and external portals.
- **Rate Limits / 429 Responses**: Temporary throttling from the external portal or email server.
- **Frontend Selector Drift**: Minor DOM tree rearrangements in Bitrix24 form elements.
- **Resolution Path**: Handled autonomously by the On-Call Agent via retry queues, exponential backoff with jitter, and alternative CSS/XPath selector mappings.

### Tier 2: Unrecoverable and Semantic Errors
- **Authentication Failure**: Expired credentials, multi-factor authentication locks, or deactivated API keys.
- **Contract Mismatch**: Condominium statement does not match active lease contract `09638.003.03`.
- **Portal Dispute Rejection**: External property manager explicitly rejects or closes the dispute ticket.
- **Resolution Path**: Handled by escalating immediately to human engineering and tenant operations. The On-Call Agent creates an `IncidenteOnCall` in status `ESCALADO` with a detailed diagnostic payload, trace identifier, and screenshot capture.

---

## 4. Self-Healing Runbooks

The On-Call Responder Agent implements automated runbooks for common production failure modes:

### Runbook A: Selector Drift Repair
- **Trigger**: `CondoSubmissionFailed` alert with error context matching `ElementNotFound` or `TimeoutError` during Playwright navigation.
- **Mechanism**:
  1. The agent fetches alternative selector definitions from the configuration catalog.
  2. Applies updated selectors to the submission context.
  3. Re-executes the submission with fallback selectors.
  4. Records the working selector for subsequent runs and updates the incident to `RESOLVIDO`.

### Runbook B: HTTP 5xx Gateway Retry & Dead-Letter Replay
- **Trigger**: Submitter encounters HTTP 500, 502, 503, or 504 status codes during Bitrix24 API interaction.
- **Mechanism**:
  1. Failed payloads are pushed to a dead-letter retry queue.
  2. The agent schedules re-execution with randomized exponential backoff (e.g., base 2s, factor 1.5, jitter +/- 500ms).
  3. Replays up to 3 automated attempts.
  4. If successful, records confirmation protocol and closes the incident.
  5. If retries expire, escalates to human on-call with the full dead-letter payload.

### Runbook C: SLA Breach Warning Response
- **Trigger**: `CondoSlaBreachWarning` alert (fewer than 3 business days remaining before monthly dispute window closes).
- **Mechanism**:
  1. Queries all cycles with status `RASCUNHO` or `AUDITADO` where submission has not occurred.
  2. Sends urgent reminder notification to the tenant dashboard and messaging channel.
  3. Highlights pending action required to safeguard tenant reimbursement rights.
