# Task 1 Brief: Project Scaffolding, Folder Structure & Docker Compose

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (code, comments, configs, commits, documentation). Use SVG/Lucide icons or plain text.
- Single command execution: `docker compose up --build`.
- Ports allocation:
  - Frontend: 5173
  - Backend API: 8000
  - Mock Bitrix24: 8080
  - PostgreSQL: 5432
  - Prometheus: 9090
  - Grafana: 3001

## Task Scope & Files
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `backend/Dockerfile`
- Create: `backend/requirements.txt`
- Create: `backend/pyproject.toml`
- Create: `frontend/Dockerfile`
- Create: `frontend/package.json` (basic skeleton for container build)
- Create: `mock_bitrix/Dockerfile`
- Create: `mock_bitrix/requirements.txt`
- Test: `tests/test_scaffolding.py`

## Acceptance Criteria
- [ ] `tests/test_scaffolding.py` checks that `docker-compose.yml` defines `db`, `backend`, `mock-bitrix`, `frontend`, `prometheus`, `grafana`.
- [ ] Test runs with `pytest tests/test_scaffolding.py` and passes.
- [ ] Minimal Dockerfiles and configuration files exist and are syntactically valid.
- [ ] Commit message: `chore: scaffold repo structure and docker compose services` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-1-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
