# Task 4 Brief: Legal & Audit Rule Engine (Lei do Inquilinato)

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (code, tests, comments, commit messages, config).
- Precision: All financial amounts represented with Python `Decimal`.
- Brazilian Tenant Law (Lei nº 8.245/1991, Art. 22):
  - Locador (Landlord): Despesas Extraordinárias (obras de reforma, fachada, laudos estruturais, seguros prediais) and Fundo de Reserva.
  - Locatário (Tenant): Despesas Ordinárias (limpeza, portaria, manutenção preventiva rotineira, consumos de gás/água).

## Task Scope & Files
- Create: `backend/app/services/audit_engine.py`
- Test: `backend/tests/test_audit_engine.py`

## Domain Rules & Expected Values (Villa Salomy 09/2026 Reference Bill)
Input: `ParsedCondoBill` produced by `backend.app.services.parser_boleto`.
Expected calculations:
- `valor_total_boleto`: Decimal("1154.31")
- `valor_locatario`: Decimal("799.81") (Ordinárias 596.27 + Leituras 203.54)
- `valor_locador`: Decimal("354.50") (Extraordinárias 294.87 + Fundos 59.63)
- `total_reimbursement`: Decimal("354.50")
- Items attributed to `LOCADOR`:
  - "Fundo de Reserva 10,00%": Decimal("59.63") (Art. 22, X, g)
  - "Rateio Manutenção Fachada Parc 6/10": Decimal("208.29") (Art. 22, X, a)
  - "Rateio fiscalização obra da fachada": Decimal("54.89") (Art. 22, X, a)
  - "Laudo Bombeiro Parc 2/3": Decimal("10.96") (Art. 22, X)
  - "Seguro Obrigatório Predial Parc 2/6": Decimal("18.44") (Art. 22, X)
  - "Tarifa Bancária": Decimal("2.29")
- Generated `formatted_observations` for Ibagy:
  A clear, professional Brazilian Portuguese text listing each landlord item and amount, referencing "Art. 22 da Lei 8.245/91", stating the total reimbursement of "R$ 354,50" for rent deduction, and mentioning attached condo bill and payment receipt.
- Edge case handling:
  - If an item does not clearly belong to known categories, mark `revisao_necessaria = True`.

## Schema Interfaces
`AuditReport`:
- `competencia: str`
- `condominio_nome: str`
- `data_vencimento: date`
- `valor_total_boleto: Decimal`
- `valor_locatario: Decimal`
- `valor_locador: Decimal`
- `total_reimbursement: Decimal`
- `itens_auditados: list[ItemAuditado]` (with `descricao`, `valor`, `categoria`, `responsabilidade`, `justificativa_legal`)
- `formatted_observations: str`
- `revisao_necessaria: bool`

Function:
`audit_condo_bill(parsed_bill: ParsedCondoBill) -> AuditReport`

## Acceptance Criteria
- [ ] TDD followed: `backend/tests/test_audit_engine.py` written first and tested to fail, then implemented and verified to pass.
- [ ] Correctly calculates `total_reimbursement = Decimal("354.50")` on reference bill.
- [ ] Correctly calculates `valor_locatario = Decimal("799.81")`.
- [ ] Produces clean, formal `formatted_observations` text mentioning Art. 22 and R$ 354,50.
- [ ] Flags unknown items with `revisao_necessaria = True`.
- [ ] All test suites pass: `pytest` passes all scaffolding, model, parser, and audit tests.
- [ ] Commit message: `feat: implement legal audit engine for condo expenses segregation` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-4-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
