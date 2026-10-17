# Task 10 Brief: Course Documentation, AGENTS.md & CI/CD Pipeline

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (code, tests, comments, commit messages, documentation, workflow files).
- Documentation in ENGLISH (per course requirement: "Documentation in English, even if the interface is in another language. Reviewers cannot be assumed to read it.").
- Course rubric mapping: Must explicitly document how all 12 criteria (24 points) are met so peer reviewers can easily award full points.

## Task Scope & Files
- Create: `docs/team.md` (Agent team specification: roles, responsibilities, tools, and communication patterns)
- Create: `docs/process.md` (Agent process specification: lifecycle, human-in-the-loop, error escalation, self-healing)
- Create: `docs/architecture.md` (System components, data flow, telemetry, and containerization)
- Create: `AGENTS.md` (Entrypoint context document describing project and pointing to modular docs)
- Create: `.github/workflows/ci.yml` (GitHub Actions: PR test automation, CD to dev, manual deploy to prod with rollback)
- Update: `README.md` (Complete peer reviewer guide, problem description, acceptance criteria, quickstart `docker compose up`, architecture, rubric self-assessment)
- Create: `tests/test_ci_cd_docs.py` (Automated verification test ensuring all docs, workflows, and criteria references exist)

## Detailed Criteria Mappings (for README.md & AGENTS.md)
1. Problem Description (2 pts): Problem statement, Brazilian Tenant Law (Lei 8.245/91), Villa Salomy bill details, system functionality.
2. Product Specification (2 pts): Link to public task tracker (`https://github.com/soutes/luas-condo/issues`) with acceptance criteria and commit references.
3. Agent Team Specification (2 pts): Extractor, Legal Auditor, Submitter, and On-Call Responder agents defined in `docs/team.md`.
4. Context Management (2 pts): Modular `AGENTS.md` pointing to `docs/team.md`, `docs/process.md`, `docs/architecture.md`.
5. Application (2 pts): Full-stack FastAPI + PostgreSQL + React + Vite working end-to-end with single command (`docker compose up --build`).
6. Testing (2 pts): Unit and integration tests for backend (`pytest`) and frontend (`npm test`), all passing with single command.
7. Containerization (2 pts): Docker Compose multi-service setup (`backend`, `frontend`, `mock-bitrix`, `db`, `prometheus`, `grafana`).
8. Deployment (2 pts): Deployment runbook and demo guide for live operation.
9. CI/CD (3 pts): GitHub Actions workflow with PR test automation, automated CD to dev, and manual production deployment with rollback.
10. Observability (2 pts): OpenTelemetry traces with shared `trace_id`, Prometheus metrics, LGPD/PII sanitization, viewable in Prometheus/Grafana.
11. Alerting on User Impact (1 pt): Prometheus rules (`CondoSubmissionFailed`, `CondoSlaBreachWarning`) alerting on real user impact.
12. On-Call Agent (2 pts): Autonomous self-healing responder agent waking up on webhook alert and repairing issues.

## Acceptance Criteria
- [ ] TDD followed: `tests/test_ci_cd_docs.py` written first and tested to fail, then implemented and verified to pass.
- [ ] `AGENTS.md` exists, is modular, and links to `docs/team.md`, `docs/process.md`, `docs/architecture.md`.
- [ ] `README.md` provides complete documentation in English with quickstart and 12-criteria rubric matrix.
- [ ] `.github/workflows/ci.yml` contains `test`, `deploy-dev`, and `deploy-prod` (with rollback parameter/step).
- [ ] Zero emojis across all markdown, YAML, and Python files.
- [ ] All tests pass: `pytest` passes 100% of tests.
- [ ] Commit message: `docs: finalize course documentation, agents definition and ci/cd pipeline` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-10-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
