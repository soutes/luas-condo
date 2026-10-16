# Sistema de Auditoria e Ressarcimento Condominial (luas_condo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir uma aplicação full-stack ponta a ponta pronta para produção (`luas_condo`) que ingere boletos condominiais por e-mail e comprovantes PIX, audita as despesas separando obrigações do inquilino e proprietário (Lei nº 8.245/1991), disponibiliza um painel de conferência e submete automaticamente a contestação com comprovantes no formulário Bitrix24 da imobiliária Ibagy, atendendo com nota máxima aos 12 critérios (24 pontos) do curso.

**Architecture:** O sistema opera em microsserviços integrados via Docker Compose: um backend em Python (FastAPI) com motor determinístico de extração PDF (`pdfplumber`) e regras jurídicas de rateio, um worker de ingestão IMAP (modo somente-leitura com UID incremental), um módulo de automação web com Playwright para submissão ao Bitrix24 (com container mock para testes), instrumentação completa com OpenTelemetry (spans, métricas e logs correlacionados com `trace_id`), alerta de impacto no usuário e um agente on-call autônomo para autorrecuperação de falhas em submissões. O frontend é uma SPA moderna em React + Vite + Tailwind (sem emojis, cantos retos).

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, PostgreSQL, pdfplumber, Playwright, React, Vite, Tailwind CSS, Lucide Icons, OpenTelemetry SDK, Prometheus, Grafana, Docker, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-16-condo-audit-reimbursement-design.md`

## Global Constraints

- **NO EMOJIS**: NUNCA utilize emojis em código, testes, arquivos de configuração, mensagens de commit, comentários, documentação ou interface de usuário (UI). Utilize ícones Lucide/SVG ou texto puro.
- **Single Command Execution**: A aplicação completa deve subir com um único comando: `docker compose up --build`.
- **Single Command Testing**: Toda a suíte de testes (unitários e integração) deve rodar com um único comando: `pytest` (ou script `run_tests.sh` / `test.bat`).
- **Ports Allocation**: Frontend (5173), Backend API (8000), Mock Bitrix24 (8080), PostgreSQL (5432), Prometheus (9090), Grafana (3001).
- **Data Protection & LGPD**: Nenhum dado sensível (CPF, senha de app de e-mail, credenciais) pode trafegar ou ser exibido em logs de telemetria pública ou traces OpenTelemetry.
- **Direct Real estate form**: `https://ibagy.bitrix24.site/condominioressarcimento/ressarcimento/` (usado somente com `MOCK_SUBMISSION=false`).
- **Contrato padrão**: `09638.003.03`.

## Review Focus

1. **Rubrica não categorizada no rateio**: Se o condomínio introduzir uma linha nova não prevista na tabela (ex: "Rateio Emergencial Portão"), o classificador deve marcar como `REVISAO_MANUAL` em vez de quebrar ou atribuir erroneamente.
2. **Falha transitória ou 5xx no Bitrix24**: O worker deve armazenar o estado em quarentena com `status=RETRY` e disparar o alerta de impacto no usuário se a janela de vencimento estiver comprometida.
3. **Comprovante PIX com valor inconsistente**: Se um comprovante com valor diferente de `R$ 1.154,31` for ingerido, o sistema deve registrar `status_ciclo=PENDENTE_COMPROVANTE` e emitir aviso no painel em vez de enviar dados errados para a Ibagy.
4. **Quebra de seletores HTML no Bitrix24**: Se a Ibagy alterar o nome de campos (ex: `input[name="contrato"]` para `input[name="num_contrato"]`), o agente on-call deve inspecionar o DOM, atualizar o arquivo de mapeamento de seletores e reexecutar a submissão com sucesso.
5. **Sanitização estrita em telemetria**: Validação de que nenhum trace span ou log estruturado emita CPFs, senhas de e-mail ou chaves PIX.

---

### Task 1: Scaffolding do Repositório, Estrutura de Pastas e Docker Compose

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\docker-compose.yml`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.env.example`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.gitignore`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\Dockerfile`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\requirements.txt`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\pyproject.toml`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\frontend\Dockerfile`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\mock_bitrix\Dockerfile`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\tests\test_scaffolding.py`

**Interfaces:**
- Produces: Ambiente reproduzível via Docker Compose com serviços `db` (Postgres 16), `backend` (FastAPI), `mock-bitrix` (FastAPI mock), `frontend` (Vite) e stack Prometheus/Grafana.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffolding.py
import os
import yaml

def test_docker_compose_structure():
    compose_path = os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")
    assert os.path.exists(compose_path), "docker-compose.yml must exist"
    with open(compose_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    services = data.get("services", {})
    assert "db" in services
    assert "backend" in services
    assert "mock-bitrix" in services
    assert "frontend" in services
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scaffolding.py`
Expected: FAIL (file not found)

- [ ] **Step 3: Implement minimal files**

Criar `.gitignore`, `.env.example`, `backend/requirements.txt`, `backend/Dockerfile`, `frontend/Dockerfile`, `mock_bitrix/Dockerfile` e `docker-compose.yml` configurando portas e variáveis padrão sem emojis.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scaffolding.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "chore: scaffold repo structure and docker compose services"
```

---

### Task 2: Modelos de Domínio e Camada de Persistência (PostgreSQL + SQLAlchemy)

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\core\database.py`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\models\entities.py`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\schemas\condo.py`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\tests\test_models.py`

**Interfaces:**
- Produces: Tabelas `ciclos_condominio`, `itens_rateio`, `submissoes_ressarcimento` e `incidentes_on_call`.
- Funções: `get_db()`, `create_tables()`, schemas Pydantic de entrada e saída.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models.py
from datetime import date
from decimal import Decimal
from app.models.entities import CicloCondominio, ItemRateio, StatusCiclo, CategoriaItem, ResponsabilidadeItem

def test_create_ciclo_and_items(db_session):
    ciclo = CicloCondominio(
        competencia="2026-09",
        condominio_nome="CONDOMINIO EDIFICIO VILLA SALOMY",
        data_vencimento=date(2026, 10, 10),
        valor_total=Decimal("1154.31"),
        valor_ordinarias=Decimal("596.27"),
        valor_extraordinarias=Decimal("294.87"),
        valor_fundos=Decimal("59.63"),
        valor_leituras=Decimal("203.54"),
        valor_ressarcimento=Decimal("354.50"),
        boleto_pdf_path="/data/boletos/2026-09.pdf",
        status_ciclo=StatusCiclo.PENDENTE_COMPROVANTE
    )
    db_session.add(ciclo)
    db_session.commit()
    assert ciclo.id is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_models.py`
Expected: FAIL (models not found)

- [ ] **Step 3: Implement database models and schemas**

Implementar SQLAlchemy 2.0 e Pydantic v2 em `backend/app/models/entities.py` com tipos decimais, enums de status e relacionamentos com cascata.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_models.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: implement database entities and schemas"
```

---

### Task 3: Parser Determinístico de Boletos Condominiais (SCI Syndkos Villa Salomy)

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\services\parser_boleto.py`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\tests\fixtures\sample_syndkos_text.py`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\tests\test_parser_boleto.py`

**Interfaces:**
- Produces: `parse_condo_pdf(file_path: str) -> ParsedCondoBill`
- Retorno: Competência, Vencimento, Total, Tabela itemizada com valores por unidade e categorias identificadas.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_parser_boleto.py
from decimal import Decimal
from app.services.parser_boleto import parse_condo_text
from tests.fixtures.sample_syndkos_text import VILLA_SALOMY_TEXT_PAGE1

def test_parse_syndkos_villa_salomy():
    result = parse_condo_text(VILLA_SALOMY_TEXT_PAGE1)
    assert result.condominio_nome == "CONDOMINIO EDIFICIO VILLA SALOMY"
    assert result.competencia == "2026-09"
    assert result.valor_total == Decimal("1154.31")
    assert result.valor_ordinarias == Decimal("596.27")
    assert result.valor_extraordinarias == Decimal("294.87")
    assert result.valor_fundos == Decimal("59.63")
    assert result.valor_leituras == Decimal("203.54")
    
    # Checar item chave da fachada
    fachada = next(i for i in result.itens if "Rateio Manutenção Fachada Parc 6/10" in i.descricao)
    assert fachada.valor_unidade == Decimal("208.29")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_parser_boleto.py`
Expected: FAIL (parse_condo_text not defined)

- [ ] **Step 3: Implement `parse_condo_text` and `parse_condo_pdf`**

Implementar parser robusto que varre as seções `Ordinárias`, `Extraordinárias`, `Leituras` e `Fundos`, extrai números decimais e faz conferência matemática garantindo que a soma dos blocos bata com o total `R$ 1.154,31`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_parser_boleto.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/parser_boleto.py backend/tests/
git commit -m "feat: implement deterministic parser for syndkos condo bills"
```

---

### Task 4: Motor de Auditoria e Regras Legais (Lei do Inquilinato)

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\services\audit_engine.py`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\tests\test_audit_engine.py`

**Interfaces:**
- Produces: `audit_condo_bill(parsed_bill: ParsedCondoBill) -> AuditReport`
- Retorno: Itens segregados (`LOCADOR` vs `LOCATARIO`), valor total a ressarcir (`R$ 354,50`), lista de justificativas por dispositivo legal e texto pronto para o campo `Observações`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_audit_engine.py
from decimal import Decimal
from app.services.parser_boleto import parse_condo_text
from app.services.audit_engine import audit_condo_bill
from tests.fixtures.sample_syndkos_text import VILLA_SALOMY_TEXT_PAGE1

def test_audit_reimbursement_calculation():
    bill = parse_condo_text(VILLA_SALOMY_TEXT_PAGE1)
    report = audit_condo_bill(bill)
    
    # Total a ressarcir deve ser exatamente Extraordinárias (294.87) + Fundos (59.63) = 354.50
    assert report.total_reimbursement == Decimal("354.50")
    assert "Fundo de Reserva: R$ 59,63" in report.formatted_observations
    assert "Rateio Manutenção Fachada (Parc 6/10): R$ 208,29" in report.formatted_observations
    assert "Art. 22 da Lei 8.245/91" in report.formatted_observations
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_audit_engine.py`
Expected: FAIL

- [ ] **Step 3: Implement `audit_condo_bill`**

Classificar itens por regras:
- `EXTRAORDINARIA` e `FUNDO_DE_RESERVA` -> `LOCADOR`
- `ORDINARIA` e `LEITURA` -> `LOCATARIO`
- Se houver item ambíguo ou desconhecido -> marcar flag `revisao_necessaria=True`.
- Montar a memória de cálculo textual para a imobiliária.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_audit_engine.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/audit_engine.py backend/tests/test_audit_engine.py
git commit -m "feat: implement legal audit engine for condo expenses segregation"
```

---

### Task 5: Worker de Ingestão IMAP (Padrão luas_finance em Python)

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\services\email_worker.py`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\tests\test_email_worker.py`

**Interfaces:**
- Produces: `fetch_new_condo_emails(imap_client, last_uid: int) -> List[IngestedDocument]`
- Características: Conexão IMAP SSL 993, trava `read-only`, extração de anexos PDF/imagens, casamento de comprovante PIX pelo valor `1154.31`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_email_worker.py
from unittest.mock import MagicMock
from app.services.email_worker import process_inbound_message

def test_process_inbound_condo_pdf():
    mock_msg = {
        "uid": 105,
        "from": "condominio@syndkos.com.br",
        "subject": "Boleto Villa Salomy 09/2026",
        "attachments": [{"filename": "Boleto.pdf", "content": b"%PDF-1.4..."}]
    }
    result = process_inbound_message(mock_msg)
    assert result.doc_type == "CONDO_BILL"
    assert result.filename == "Boleto.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_email_worker.py`
Expected: FAIL

- [ ] **Step 3: Implement `process_inbound_message` and IMAP read-only poller**

Implementar conexão IMAP com `imaplib` / `mailparser` em Python seguindo a mesma política do `luas_finance`: modo somente leitura (`EXAMINE INBOX`), sem exclusão e busca incremental por `UID`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_email_worker.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/email_worker.py backend/tests/test_email_worker.py
git commit -m "feat: implement imap read-only poller matching luas_finance architecture"
```

---

### Task 6: Mock Server do Bitrix24 e Submitter Web com Playwright

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\mock_bitrix\main.py`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\services\bitrix_submitter.py`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\tests\test_bitrix_submitter.py`

**Interfaces:**
- Consumes: Dados cadastrais, número de contrato `09638.003.03`, texto de observações e arquivos binários (boleto e comprovante).
- Produces: `submit_reimbursement(payload: SubmissionPayload) -> SubmissionReceipt` com protocolo e caminho do screenshot.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bitrix_submitter.py
import pytest
from app.services.bitrix_submitter import submit_reimbursement_direct
from app.schemas.condo import SubmissionPayload

@pytest.mark.asyncio
async def test_submit_to_mock_bitrix(mock_server_url):
    payload = SubmissionPayload(
        nome="Luiz Augusto Soutes",
        email="luizaugustosoutes@gmail.com",
        telefone="5548999999999",
        contrato="09638.003.03",
        observacoes="Ressarcimento de fachada e fundo de reserva: R$ 354,50",
        boleto_path="/tmp/fake_boleto.pdf",
        comprovante_path="/tmp/fake_pix.png"
    )
    receipt = await submit_reimbursement_direct(payload, target_url=f"{mock_server_url}/submit")
    assert receipt.status == "SUCESSO"
    assert receipt.protocolo is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_bitrix_submitter.py`
Expected: FAIL

- [ ] **Step 3: Implement mock-bitrix and submitter service**

1. Em `mock_bitrix/main.py`: Endpoint FastAPI que recebe `multipart/form-data`, valida presença dos 7 campos do formulário da Ibagy e retorna código de confirmação.
2. Em `backend/app/services/bitrix_submitter.py`: Implementação com fallback duplo (Playwright para captura de tela e chamada HTTP direta rápida).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_bitrix_submitter.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mock_bitrix/ backend/app/services/bitrix_submitter.py backend/tests/
git commit -m "feat: implement mock bitrix24 and robust submitter service"
```

---

### Task 7: Telemetria com OpenTelemetry (Métricas, Spans Correlacionados e Sanitização LGPD)

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\core\telemetry.py`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\tests\test_telemetry.py`

**Interfaces:**
- Produces: `tracer`, `get_current_trace_id()`, `sanitize_log_data(data: dict) -> dict`, métricas Prometheus:
  - `condo_submissions_total`
  - `condo_reimbursement_value_brl`
  - `condo_processing_duration_seconds`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_telemetry.py
from app.core.telemetry import sanitize_log_data, trace_cycle_step

def test_sanitization_removes_cpf_and_password():
    raw_data = {
        "cpf": "042.931.439-63",
        "email_pass": "secret123",
        "contrato": "09638.003.03",
        "valor": "354.50"
    }
    clean = sanitize_log_data(raw_data)
    assert clean["cpf"] == "[REDACTED]"
    assert clean["email_pass"] == "[REDACTED]"
    assert clean["contrato"] == "09638.003.03"
    assert clean["valor"] == "354.50"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_telemetry.py`
Expected: FAIL

- [ ] **Step 3: Implement OpenTelemetry tracer and sanitizers**

Configurar OTel Tracer com exportador OTLP/Prometheus e filtro de sanitização que expurga padrões de CPF, e-mail completo e senhas antes de injetar atributos nos spans.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_telemetry.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/telemetry.py backend/tests/test_telemetry.py
git commit -m "feat: instrument opentelemetry with trace propagation and lgpd sanitization"
```

---

### Task 8: Alertas de Impacto Real e Agente On-Call Autônomo (Self-Healing)

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\agents\on_call.py`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\app\routes\alert_webhook.py`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\backend\tests\test_on_call_agent.py`

**Interfaces:**
- Produces: `POST /api/alerts/webhook` recebendo payloads do Prometheus Alertmanager.
- Comportamento: O agente analisa o `trace_id` e a mensagem de erro. Se houver falha de submissão por seletor desatualizado, inspeciona o DOM, remapeia o campo, reprocessa a fila e encerra o alerta com `status=RESOLVIDO`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_on_call_agent.py
import pytest
from app.agents.on_call import handle_incident_alert

@pytest.mark.asyncio
async def test_on_call_agent_recovers_submission_failure(db_session):
    alert_payload = {
        "status": "firing",
        "labels": {"alertname": "CondoSubmissionFailed", "severity": "critical"},
        "annotations": {
            "trace_id": "test-trace-12345",
            "error_type": "SELECTOR_MISMATCH",
            "description": "Field contrato could not be located in Bitrix24 DOM"
        }
    }
    resolution = await handle_incident_alert(alert_payload, db_session)
    assert resolution.status == "RESOLVIDO"
    assert "reprocessamento" in resolution.acao_executada.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_on_call_agent.py`
Expected: FAIL

- [ ] **Step 3: Implement On-Call Responder Agent logic**

Construir o despachante de remediação que:
1. Registra o incidente na tabela `incidentes_on_call`;
2. Executa a ação de contingência (atualização de mapa de seletores / retry exponencial / chaveamento para modo direto multipart);
3. Testa o canal e confirma a resolução.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_on_call_agent.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/on_call.py backend/app/routes/alert_webhook.py backend/tests/
git commit -m "feat: implement on-call responder agent for automated incident resolution"
```

---

### Task 9: Painel Web Frontend (React + Vite + Tailwind, sem emojis)

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\frontend\src\App.tsx`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\frontend\src\components\CycleCard.tsx`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\frontend\src\components\AuditTable.tsx`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\frontend\src\components\SubmissionPreview.tsx`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\frontend\src\__tests__\AuditTable.test.tsx`

**Interfaces:**
- Produces: Dashboard responsivo exibindo status do ciclo (Recebido, Pago, Auditado, Enviado), tabela comparativa Ordinárias vs Extraordinárias (com destaque no valor a ressarcir `R$ 354,50`), modal de edição de observações e botão "Aprovar e Enviar para Ibagy".

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/AuditTable.test.tsx
import { render, screen } from '@testing-library/react'
import { AuditTable } from '../components/AuditTable'

test('renders reimbursement value prominently with no emojis', () => {
  const items = [
    { descricao: 'Rateio Manutenção Fachada Parc 6/10', valor: '208.29', responsabilidade: 'LOCADOR' },
    { descricao: 'Fundo de Reserva', valor: '59.63', responsabilidade: 'LOCADOR' },
    { descricao: 'Portaria Remota', valor: '106.78', responsabilidade: 'LOCATARIO' }
  ]
  render(<AuditTable items={items} totalReimbursement="267.92" />)
  expect(screen.getByText('R$ 267.92')).toBeInTheDocument()
  expect(screen.getByText('Rateio Manutenção Fachada Parc 6/10')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test` no frontend
Expected: FAIL

- [ ] **Step 3: Implement Frontend Components**

Implementar componentes em React com Tailwind CSS, tipografia JetBrains Mono / Inter, cantos retos (`rounded-none`), cores sóbrias (laranja e cinzas escuros no estilo Luas.Ai) e ícones SVG Lucide, garantindo zero emojis.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test` no frontend
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: implement responsive condo audit dashboard frontend"
```

---

### Task 10: Documentação Oficial do Curso, AGENTS.md e Pipeline CI/CD com Rollback

**Files:**
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\README.md`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\AGENTS.md`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\docs\team.md`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\docs\process.md`
- Create: `C:\Users\luiz_\_DS\luas_projects\luas_condo\.github\workflows\ci.yml`
- Test: `C:\Users\luiz_\_DS\luas_projects\luas_condo\tests\test_ci_cd_docs.py`

**Interfaces:**
- Produces: Documentação em inglês (conforme exigência do curso) detalhando o problema, arquitetura, time de agentes e instruções para peer review. Pipeline GitHub Actions com testes automatizados em PRs, deploy contínuo em ambiente dev e aprovação manual para produção.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ci_cd_docs.py
import os

def test_course_documentation_presence():
    base = os.path.join(os.path.dirname(__file__), "..")
    assert os.path.exists(os.path.join(base, "README.md"))
    assert os.path.exists(os.path.join(base, "AGENTS.md"))
    assert os.path.exists(os.path.join(base, ".github", "workflows", "ci.yml"))
    
    with open(os.path.join(base, "README.md"), "r", encoding="utf-8") as f:
        readme = f.read()
    assert "Villa Salomy" in readme
    assert "docker compose up" in readme
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ci_cd_docs.py`
Expected: FAIL

- [ ] **Step 3: Implement Documentation and GitHub Actions Workflow**

1. Escrever `README.md` em inglês completo abordando a especificação do problema, o fluxo de aceitação e o guia passo a passo para os avaliadores do curso.
2. Criar `AGENTS.md` referenciando `docs/team.md` e `docs/process.md`.
3. Criar `.github/workflows/ci.yml` cobrindo PR test, dev deploy e manual prod deploy com rollback.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ci_cd_docs.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md docs/ .github/ tests/
git commit -m "docs: finalize course documentation, agents definition and ci/cd pipeline"
```
