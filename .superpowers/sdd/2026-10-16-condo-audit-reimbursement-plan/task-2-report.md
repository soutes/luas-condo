# Task 2 Report: Domain Models & Database Persistence Layer

## Summary
- Task: Task 2 - Domain Models & Database Persistence Layer
- Status: DONE
- Commit Hash: 98b260c0e74eba8b63ca97e3b0f2bb9287dd63d9
- Single-command test execution: 13 passed in 1.11s

## Created & Modified Files
- `backend/app/core/database.py`: Database engine, SessionLocal, Base DeclarativeBase, get_db generator, init_db, and SQLite/PostgreSQL URL adaptation with SQLite foreign keys pragma.
- `backend/app/models/entities.py`: SQLAlchemy 2.0 mapped models (CicloCondominio, ItemRateio, SubmissaoRessarcimento, IncidenteOnCall) with Enums (StatusCiclo, CategoriaItem, ResponsabilidadeItem, StatusSubmissao, StatusIncidente), UUID primary keys, and cascade deletion.
- `backend/app/schemas/condo.py`: Pydantic v2 schemas for request validation and response serialization with ORM mode enabled (`from_attributes=True`).
- `backend/app/__init__.py`: Application root package init.
- `backend/app/core/__init__.py`: Core module package init.
- `backend/app/models/__init__.py`: Models module package init re-exporting entities and enums.
- `backend/app/schemas/__init__.py`: Schemas module package init re-exporting Pydantic models.
- `backend/tests/test_models.py`: Comprehensive test suite covering model creation, UUID primary keys, cascade deletion, submissao JSON persistence, incidente logs, Pydantic serialization/validation, and database helper methods.

## TDD Lifecycle
1. Red Phase:
   - Created `backend/tests/test_models.py`.
   - Executed `python -m pytest backend/tests/test_models.py`.
   - Result: Failed with `ModuleNotFoundError: No module named 'app'` as expected.
2. Green Phase:
   - Implemented database engine, models, enums, schemas, and package initializers.
   - Executed `python -m pytest backend/tests/test_models.py`.
   - Result: 9 passed.
3. Verification & Regressions:
   - Executed `python -m pytest tests/test_scaffolding.py`.
   - Result: 4 passed (including `test_no_emojis_in_scaffolding`).
   - Executed root `pytest`.
   - Result: 13 passed cleanly.

## Test Execution Output
```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\luiz_\_DS\luas_projects\luas_condo
plugins: anyio-4.13.0
collected 13 items

backend\tests\test_models.py .........                                   [ 69%]
tests\test_scaffolding.py ....                                           [100%]

============================= 13 passed in 1.11s ==============================
```

## Observations and Notes
- SQLite PRAGMA foreign_keys=ON was configured on connection to guarantee cascade deletion during unit testing.
- Database engine URI automatically normalizes legacy `postgres://` to `postgresql://`.
- No emojis present in code, schemas, docstrings, tests, or commit messages.
