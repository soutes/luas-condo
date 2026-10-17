# Task 2 Brief: Domain Models & Database Persistence Layer

## Project Context
Project: Luas Condo (Condo Audit & Reimbursement System)
Workspace: C:\Users\luiz_\_DS\luas_projects\luas_condo
Repo: https://github.com/soutes/luas-condo

## Global Constraints
- NO EMOJIS anywhere (code, tests, comments, commit messages, config).
- Python 3.12+ with SQLAlchemy 2.0+ and Pydantic v2+.
- Single command test execution: `pytest` passes cleanly.
- Database layer must support both SQLite (`sqlite:///:memory:` or local file for fast unit tests) and PostgreSQL (for docker/production) via `DATABASE_URL` environment variable.

## Task Scope & Files
- Create: `backend/app/core/database.py` (engine, sessionmaker, Base, get_db, init_db)
- Create: `backend/app/models/entities.py` (SQLAlchemy 2.0 mapped models: CicloCondominio, ItemRateio, SubmissaoRessarcimento, IncidenteOnCall, plus all Enums)
- Create: `backend/app/schemas/condo.py` (Pydantic v2 schemas for request/response serialization)
- Test: `backend/tests/test_models.py`

## Domain Specification (Verbatim from Spec)
1. `CicloCondominio`:
   - id: UUID (primary key)
   - competencia: str (e.g. "2026-09")
   - condominio_nome: str (e.g. "CONDOMINIO EDIFICIO VILLA SALOMY")
   - data_vencimento: date
   - valor_total: Decimal(10, 2)
   - valor_ordinarias: Decimal(10, 2)
   - valor_extraordinarias: Decimal(10, 2)
   - valor_fundos: Decimal(10, 2)
   - valor_leituras: Decimal(10, 2)
   - valor_ressarcimento: Decimal(10, 2)
   - boleto_pdf_path: str
   - comprovante_pix_path: Optional[str]
   - status_ciclo: StatusCiclo (PENDENTE_COMPROVANTE, PRONTO_PARA_ENVIO, ENVIADO, PROCESSADO_ALUGUEL)
   - criado_em: datetime
   - Relationship: itens (cascade delete)

2. `ItemRateio`:
   - id: UUID
   - ciclo_id: UUID (ForeignKey to CicloCondominio)
   - categoria: CategoriaItem (ORDINARIA, EXTRAORDINARIA, FUNDOS, LEITURA)
   - descricao: str
   - valor_unidade: Decimal(10, 2)
   - valor_total_condominio: Optional[Decimal(10, 2)]
   - responsabilidade: ResponsabilidadeItem (LOCATARIO, LOCADOR)
   - justificativa_legal: Optional[str]

3. `SubmissaoRessarcimento`:
   - id: UUID
   - ciclo_id: UUID
   - contrato_numero: str (e.g. "09638.003.03")
   - payload_enviado: dict / JSON
   - status: StatusSubmissao (SUCESSO, ERRO, RETRY)
   - protocolo_retorno: Optional[str]
   - screenshot_path: Optional[str]
   - tentativas: int
   - trace_id: str
   - enviado_em: datetime

4. `IncidenteOnCall`:
   - id: UUID
   - trace_id: str
   - alerta_nome: str
   - diagnostico: str
   - acao_executada: str
   - status: StatusIncidente (RESOLVIDO, ESCALADO_HUMANO)
   - criado_em: datetime

## Acceptance Criteria
- [ ] TDD followed: `backend/tests/test_models.py` written first and tested to fail, then implemented and verified to pass.
- [ ] All 4 models and relationships correctly defined with SQLAlchemy 2.0 typing (`Mapped`, `mapped_column`).
- [ ] Pydantic v2 schemas defined in `backend/app/schemas/condo.py`.
- [ ] Cascade delete works (deleting a `CicloCondominio` deletes associated `ItemRateio` rows).
- [ ] Commit message: `feat: implement domain models and database persistence layer` (NO EMOJIS).

## Report Contract
Write report to: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.superpowers\sdd\2026-10-16-condo-audit-reimbursement-plan\task-2-report.md`
Report must include:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED
- Commits created
- Test execution output
- Any concerns or observations
