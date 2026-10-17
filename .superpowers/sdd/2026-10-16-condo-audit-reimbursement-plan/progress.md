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

Task 1: complete (commits c95f533..eb8f165, review clean)
Task 2: minor (deferred): use tmp_path fixture for condo.db test cleanup and dialect.name == "sqlite"
Task 2: complete (commits 0b6710a..98b260c, review clean)
Task 3: complete (commit 5af5673, parser unit tests passing, mathematical validation verified)
Task 3: minor (deferred): replace fallback condo name with ValueError, use Field(default_factory=list), add item sum vs subtotal cross-check
Task 3: complete (commits 98b260c..5af5673, review clean)
Task 4: complete (commit 3b667ab, audit unit tests passing, legal rule engine verified)
Task 4: complete (commits 5af5673..3b667ab, review clean)
Task 5: fix round 1/5 (1 addressed, 0 open — receipt matching disambiguation; commits 4d8de5d..3d381bd)
Task 5: complete (commits 3b667ab..3d381bd, review clean)
Task 6: fix round 1/5 (1 addressed, 0 open — browser file existence check; commits f871144..0f4c124)
Task 6: complete (commits 3d381bd..0f4c124, review clean)
Task 7: minor (deferred): apply sanitize_text to exception descriptions in trace_step
Task 7: complete (commits 0f4c124..b11a2bf, review clean)
Task 8: fix round 1/5 (1 addressed, 0 open — decouple http transport and ignore resolved alerts; commits 67ce4b6..81a435b)
Task 8: complete (commits b11a2bf..81a435b, review clean)
Task 9: minor (deferred): add optional chaining on boleto_pdf_path basename parsing in SubmissionPreview
Task 9: complete (commits 81a435b..beaa25f, review clean)
