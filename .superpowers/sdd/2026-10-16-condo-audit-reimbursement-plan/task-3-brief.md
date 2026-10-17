# Task 3 Brief: Deterministic PDF Parser for Syndkos Condo Bills

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (code, tests, comments, commit messages, config).
- Deterministic extraction: No LLM calls for standard rateio parsing (fast, 100% exact, zero API cost).
- Mathematical validation: The sum of category totals (`valor_ordinarias + valor_extraordinarias + valor_leituras + valor_fundos`) must match `valor_total` within 0.01 tolerance.

## Task Scope & Files
- Create: `backend/tests/fixtures/sample_syndkos_text.py` (containing the exact text of Villa Salomy reference bill)
- Create: `backend/app/services/parser_boleto.py` (implementing `parse_condo_text` and `parse_condo_pdf`)
- Test: `backend/tests/test_parser_boleto.py`

## Exact Values & Data Structures (Verbatim from Reference Bill)
Reference text fixture in `sample_syndkos_text.py`:
- Condomínio: "CONDOMINIO EDIFICIO VILLA SALOMY"
- Competência: "2026-09" (from "DEMONSTRATIVO DE RATEIO DE 01/09/2026 ATÉ 30/09/2026")
- Vencimento: date(2026, 10, 10)
- Valor Total: Decimal("1154.31")
- Linha Digitável: "13691.10802 00102.557006 00000.514034 2 15950000115431"
- Category Totals:
  - Ordinárias: Decimal("596.27")
  - Extraordinárias: Decimal("294.87")
  - Leituras: Decimal("203.54")
  - Fundos: Decimal("59.63")
- Key Individual Items:
  - Extraordinárias:
    - "Seguro Obrigatório Predial Parc 2/6": Decimal("18.44")
    - "Tarifa Bancária": Decimal("2.29")
    - "Laudo Bombeiro Parc 2/3": Decimal("10.96")
    - "Rateio Manutenção Fachada Parc 6/10": Decimal("208.29")
    - "Rateio fiscalização obra da fachada": Decimal("54.89")
  - Fundos:
    - "Fundo de Reserva 10,00%": Decimal("59.63")
  - Leituras:
    - "GÁS": Decimal("62.21")
    - "ÁGUA": Decimal("141.33")

## Schema Interfaces
`ParsedCondoBill` (in `backend/app/schemas/condo.py` or `parser_boleto.py`):
- `condominio_nome: str`
- `competencia: str`
- `data_vencimento: date`
- `valor_total: Decimal`
- `valor_ordinarias: Decimal`
- `valor_extraordinarias: Decimal`
- `valor_fundos: Decimal`
- `valor_leituras: Decimal`
- `linha_digitavel: Optional[str]`
- `itens: List[ParsedItemRateio]` (with `descricao`, `valor_unidade`, `valor_total_condominio`, `categoria`)

## Acceptance Criteria
- [ ] TDD followed: `backend/tests/test_parser_boleto.py` written first and tested to fail, then implemented and verified to pass.
- [ ] Parser correctly extracts header data (condo name, competence, due date, total, barcode).
- [ ] Parser parses all 4 item blocks (Ordinárias, Extraordinárias, Leituras, Fundos).
- [ ] Mathematical integrity check: raises `ValueError` or marks invalid if category sum does not equal total.
- [ ] All test suites pass: `pytest` passes all scaffolding, model, and parser tests.
- [ ] Commit message: `feat: implement deterministic parser for syndkos condo bills` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-3-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
