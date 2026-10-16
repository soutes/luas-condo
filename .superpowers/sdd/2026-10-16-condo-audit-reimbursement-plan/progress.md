# SDD ledger — plan: docs/superpowers/plans/2026-10-16-condo-audit-reimbursement-plan.md

Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo
Initial commit: c95f533737ad38c9d4ad59c70d25231d40ffdd22

## Pre-flight Conflict Scan
| Task A | Task B | Produces vs Consumes | Status / Ruling |
|---|---|---|---|
| Task 1 (Scaffolding) | Task 2 (DB Models) | Directory layout & requirements.txt | Clean. Task 1 sets requirements and compose, Task 2 builds models. |
| Task 2 (DB Models) | Task 3 (Parser) | ParsedCondoBill vs ItemRateio schemas | Clean. Pydantic schemas bridge parser and DB entities. |
| Task 3 (Parser) | Task 4 (Audit) | ParsedCondoBill consumption | Clean. Audit engine takes ParsedCondoBill and partitions items. |
| Task 4 (Audit) | Task 6 (Submitter) | AuditReport / SubmissionPayload | Clean. Submitter consumes formatted observations and amounts. |
| Task 5 (IMAP) | Task 3 (Parser) | PDF byte stream to parser | Clean. Worker feeds attachment buffer to parser. |
| Task 6 (Submitter) | Task 8 (On-Call) | Submitter failure triggers Alertmanager | Clean. Mock Bitrix simulates 500 / selector mismatch. |
| Task 7 (Telemetry) | Task 8 (On-Call) | Unified trace_id in logs and alerts | Clean. Alert payload carries trace_id for agent correlation. |

Ruling: All tasks agree with Global Constraints and course criteria. No emojis permitted anywhere.
