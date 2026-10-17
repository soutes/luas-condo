# Task 9 Brief: Web Frontend Dashboard (React + Vite + Tailwind)

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (UI, components, code, tests, commit messages). Use SVG / Lucide icons.
- Visual style: Clean, dark slate theme with Luas.Ai orange accents (`#f7941d`), straight corners (`rounded-none`).
- End-to-end connectivity: Frontend talks to FastAPI backend (`/api/ciclos`, `/api/ciclos/{id}/submeter`).

## Task Scope & Files
1. **Frontend Application**:
   - `frontend/package.json` (React 18+, Vite, Tailwind, Lucide React, Vitest, Testing Library)
   - `frontend/vite.config.ts` (API proxy `/api` -> `http://localhost:8000` or env `VITE_API_URL`)
   - `frontend/tailwind.config.js` and `frontend/postcss.config.js`
   - `frontend/index.html`
   - `frontend/src/main.tsx`
   - `frontend/src/index.css`
   - `frontend/src/App.tsx` (Dashboard layout, header, summary cards, cycle switcher)
   - `frontend/src/components/CycleCard.tsx` (Monthly cycle summary, due date, status badge)
   - `frontend/src/components/AuditTable.tsx` (Itemized rateio table with Locatário vs Locador segregation)
   - `frontend/src/components/SubmissionPreview.tsx` (Observations memo preview, attachments status, "Aprovar e Enviar" button)
   - `frontend/src/__tests__/AuditTable.test.tsx` (Unit/component tests)

2. **Backend API Endpoints (in `backend/app/routes/ciclos.py` and registered in `backend/app/main.py`)**:
   - `GET /api/ciclos`: List all cycles with rateio items and submission status.
   - `GET /api/ciclos/{id}`: Detailed cycle view.
   - `POST /api/ciclos/{id}/submeter`: Trigger Ibagy Bitrix24 submission.

## Acceptance Criteria
- [ ] TDD followed: Component tests in `frontend/src/__tests__/AuditTable.test.tsx` and API tests for `/api/ciclos` written first and tested to fail, then implemented and verified to pass.
- [ ] Full-stack connected: Backend exposes `/api/ciclos` and `/api/ciclos/{id}/submeter`.
- [ ] Prominently displays reference reimbursement: `R$ 354,50`.
- [ ] Zero emojis across all UI, templates, SVGs, and test fixtures.
- [ ] Frontend tests pass with `npm test` (or `npx vitest run`) and root `pytest` passes 100% of backend tests.
- [ ] Commit message: `feat: implement responsive condo audit dashboard frontend` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-9-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
