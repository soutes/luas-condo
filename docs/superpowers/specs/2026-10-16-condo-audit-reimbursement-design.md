# Documento de Design: Sistema Automatizado de Conferência e Ressarcimento Condominial

**Data:** 16 de Outubro de 2026  
**Status:** Proposto (Aguardando Aprovação)  
**Projeto de Referência:** Final Project (AI Dev Tools - 24 Pontos) / Solução Catálogo Luas.Ai (`[CF]` Conferência + `[PL]` Leitura de Documentos + `[FO]` Formulário)

---

## 1. Intenção e Motivação

### 1.1 O Problema Real
Inquilinos de imóveis alugados recebem mensalmente o boleto de condomínio contendo cobranças de responsabilidade mista:
- **Despesas Ordinárias**: Manutenção rotineira, limpeza, água e gás (dever do locatário).
- **Despesas Extraordinárias e Fundo de Reserva**: Obras de fachada, reformas prediais estruturais, laudos de bombeiro e fundo de reserva (dever do locador/proprietário, conforme Art. 22 da Lei nº 8.245/1991 - Lei do Inquilinato).

Hoje, o inquilino precisa:
1. Abrir o demonstrativo do condomínio (Edifício Villa Salomy / SCI Syndkos);
2. Ler manualmente cada linha para identificar o que cabe ao proprietário (ex: R$ 354,50 neste mês);
3. Pagar o boleto total via PIX;
4. Baixar o comprovante bancário do PIX;
5. Acessar o formulário público da imobiliária (Ibagy via Bitrix24);
6. Preencher dados cadastrais, contrato (`09638.003.03`), texto justificando os valores contestados;
7. Anexar o boleto de condomínio e o comprovante de pagamento;
8. Torcer para a imobiliária processar a tempo do abatimento no boleto de aluguel do mês subsequente.

O esquecimento ou atraso nesse processo gera prejuízo financeiro direto todo mês.

### 1.2 O Objetivo do Projeto
Desenvolver uma aplicação full-stack ponta a ponta, pronta para produção, que automatiza o ciclo completo de auditoria condominial e submissão de ressarcimento, cumprindo os 12 critérios de excelência do curso (24 pontos).

---

## 2. Requisitos do Curso & Mapeamento de Pontuação (24/24)

1. **Problem Description (2 pts)**: README detalhado com descrição da dor, arquitetura, legislação aplicável (Lei 8.245/91) e comportamento esperado.
2. **Product Specification (2 pts)**: Especificação formal com critérios de aceite vinculados a um rastreador público de tarefas (GitHub Projects / Issues), com evidências de execução via agentes.
3. **Agent Team Specification (2 pts)**: Time de agentes com responsabilidades e papéis delimitados:
   - *Extractor Agent*: Parsing do boleto PDF e do comprovante PIX.
   - *Auditor/Legal Agent*: Regras contábeis e segregação Locador vs Locatário.
   - *Submitter Agent*: Automação web e submissão multipart no portal Bitrix24.
   - *On-Call Responder Agent*: Diagnóstico e autorrecuperação reativa em caso de incidentes operacionais.
4. **Context Management (2 pts)**: `AGENTS.md` modular referenciando guias de processos, convenções de testes e decisões de arquitetura.
5. **Application (2 pts)**: Frontend moderno + Backend API + Banco de dados relacional persistente. Início local com um único comando (`docker compose up`).
6. **Testing (2 pts)**: Testes unitários (regras de cálculo, parsers, validadores) e de integração (rotas de API, persistência e pipeline de ingestão) rodando com comando único.
7. **Containerization (2 pts)**: Sistema completo em contêineres Docker orquestrados por Docker Compose (App, Worker, DB e Stack de Observabilidade).
8. **Deployment (2 pts)**: Deploy em ambiente público acessível (ou demonstração gravada e reprodutível de ponta a ponta).
9. **CI/CD (3 pts)**: Pipeline GitHub Actions que roda testes em Pull Requests, deploy automatizado no ambiente de desenvolvimento e deploy com aprovação manual para produção.
10. **Observability (2 pts)**: Instrumentação com OpenTelemetry correlacionando métricas, traces distribuídos e logs estruturados sob o mesmo `trace_id`. Sanitização rígida de dados pessoais e credenciais (LGPD). Painel visualizável (Grafana / Jaeger).
11. **Alerting on Real User Impact (1 pt)**: Alerta disparado por impacto real de negócio:
    - *Alerta de Prazo Crítico*: Boleto emitido com vencimento próximo (< 3 dias) sem submissão de ressarcimento efetuada.
    - *Alerta de Falha de Submissão*: Taxa de erro na submissão ao formulário da Ibagy > 0% no período crítico.
12. **On-Call Agent (2 pts)**: Agente autônomo conectado via webhook do Alertmanager. Ao ser acionado por falha de submissão (ex: quebra de layout no Bitrix24 ou timeout de upload), o agente analisa o trace, diagnostica a causa, executa o failover/reparo de seletor ou reprocessa a fila em quarentena e emite relatório pós-incidente.

---

## 3. Arquitetura do Sistema

### 3.1 Camada de Ingestão (Baseada na Arquitetura do `luas_finance`)
- **Protocolo & Conexão**:
  - Utiliza `imapflow` e `mailparser` conectando em `imap.gmail.com:993` (TLS) com Senha de App do Google (`senhaApp`).
  - **Modo Estritamente Somente-Leitura (`readOnly: true`)**: Abre a caixa `INBOX` com trava de leitura (`getMailboxLock('INBOX', { readOnly: true })`), garantindo que nenhum e-mail seja apagado, marcado como lido ou alterado indevidamente no servidor.
  - **Coleta Incremental Segura**: Controle de estado baseado em `uid` e `uidValidity`. O worker busca apenas mensagens com `UID > ultimoUidProcessado`, evitando reprocessamento redundante.
- **Detecção e Separação de Documentos do Ciclo**:
  1. **Boleto do Condomínio (PDF)**:
     - Identificado por remetente/assunto (ex: SCI Syndkos, Condomínio Villa Salomy, ZC Contabilidade).
     - Extração do anexo em memória (`application/pdf`) para parsing das rubricas.
  2. **Comprovante de Pagamento PIX (PDF ou Imagem)**:
     - Identificado quando enviado pelo próprio Luiz (`de: luizaugustosoutes@gmail.com` ou assunto com comprovante/PIX/Villa Salomy).
     - Extração do anexo (`pdf`, `png`, `jpeg`).
- **Canal de Contingência (Manual)**:
  - Upload direto via drag-and-drop no painel web para permitir testes manuais imediatos ou resolução rápida caso o e-mail atrase.

### 3.2 Motor de Extração e Pareamento (Extraction Engine)
- **Parser de Boletos Condominiais**:
  - Extrai competência (`01/09/2026 até 30/09/2026`), data de vencimento (`10/10/2026`), valor total (`R$ 1.154,31`) e código de barras/PIX.
  - Extrai tabela detalhada de despesas categorizadas em:
    - `Ordinárias` (Portaria, Limpeza, Seguro elevador, etc.)
    - `Extraordinárias` (Obras, Fachada, Laudos, Seguro predial)
    - `Leituras` (Água, Gás)
    - `Fundos` (Fundo de Reserva)
- **Parser de Comprovantes PIX**:
  - Extrai valor pago, data/hora da transação, chave PIX e autenticação bancária.
- **Pareador de Ciclos**:
  - Cruza o comprovante com o boleto através do valor (`R$ 1.154,31`), competência ou proximidade de data de pagamento.

### 3.3 Motor de Auditoria e Regras Legais (Legal & Audit Engine)
- **Matriz de Responsabilidade (Lei 8.245/91)**:
  - Itens categorizados como `EXTRAORDINARIA` ou `FUNDO_DE_RESERVA` são automaticamente atribuídos ao locador (proprietário).
  - Itens categorizados como `ORDINARIA` ou `CONSUMO_INDIVIDUAL` são atribuídos ao locatário (inquilino).
- **Geração da Memória de Cálculo**:
  - Soma dos valores a ressarcir:
    - Fundo de Reserva: R$ 59,63
    - Rateio Manutenção Fachada (Parc 6/10): R$ 208,29
    - Rateio Fiscalização Obra Fachada: R$ 54,89
    - Laudo Bombeiro (Parc 2/3): R$ 10,96
    - Seguro Obrigatório Predial (Parc 2/6): R$ 18,44
    - Tarifa Bancária: R$ 2,29
    - **Total a Ressarcir:** R$ 354,50
- **Redação Automática das Observações**:
  - Gera texto padronizado, claro e formal para preenchimento no formulário:
    ```text
    Solicito ressarcimento de despesas condominiais de responsabilidade do proprietário (Art. 22 da Lei 8.245/91), referentes à competência 09/2026 (Condomínio Edifício Villa Salomy, Apto 802):
    - Fundo de Reserva: R$ 59,63
    - Rateio Manutenção Fachada (Parc 6/10): R$ 208,29
    - Rateio Fiscalização Obra Fachada: R$ 54,89
    - Laudo Bombeiro (Parc 2/3): R$ 10,96
    - Seguro Obrigatório Predial (Parc 2/6): R$ 18,44
    - Tarifa Bancária: R$ 2,29
    Valor total para desconto no próximo aluguel: R$ 354,50.
    Boleto e comprovante de pagamento anexados.
    ```

### 3.4 Interface do Usuário (Frontend)
- **Dashboard de Ciclos**:
  - Cards mensais indicando o estágio do ciclo:
    1. *Boleto recebido* (PDF importado e analisado)
    2. *Pagamento detectado* (Comprovante PIX casado)
    3. *Conferência pronta* (Valores segregados com memória de cálculo)
    4. *Submissão efetuada* (Protocolo gerado e comprovante de envio)
- **Visão Detalhada de Conferência**:
  - Exibição visual lado a lado dos itens Ordinários (verde/neutro) vs Extraordinários a abater (laranja de destaque).
  - Preview editável do texto de observações e campos do formulário.
  - Botão de ação: "Aprovar e Enviar para Ibagy" (com opção de modo 100% automático habilitável nas configurações).
- **Histórico e Conciliação com o Boleto de Aluguel**:
  - Registro de conferência para checar se o boleto do aluguel do mês seguinte de fato aplicou o desconto com sinal negativo (`-`).

### 3.5 Automação de Envio (Bitrix24 Submitter)
- **Destino**: `https://ibagy.bitrix24.site/condominioressarcimento/ressarcimento/` (ou mock local em ambiente de teste/CI).
- **Ambiente de Teste & Mock**:
  - Para testes de CI/CD, testes de integração e simulações do agente on-call sem poluir o CRM real da Ibagy com tickets falsos, o Docker Compose inclui um container `mock-bitrix24` leve (FastAPI) que replica os campos, validações e simula cenários de erro (ex: 500, timeout, seletor renomeado).
  - Em modo de produção (`MOCK_SUBMISSION=false`), o worker submete diretamente ao formulário oficial da Ibagy.
- **Mecanismo de Execução**:
  - Playwright Headless no container do worker (garante captura de screenshot comprobatório para auditoria do inquilino e viabiliza a auto-remediação do agente on-call por inspeção de DOM).
- **Mapeamento de Campos**:
  - `Nome do inquilino`: Luiz Augusto Soutes
  - `E-mail`: luizaugustosoutes@gmail.com
  - `Telefone`: 55 48 9XXXX-XXXX (configurado em variáveis de ambiente)
  - `Número do contrato`: `09638.003.03`
  - `Observações`: Texto com a discriminação dos itens e fundamentação legal.
  - `Boleto condomínio`: Arquivo PDF do boleto.
  - `Comprovante de pagamento`: Arquivo PDF ou imagem do comprovante PIX.

### 3.6 Motor Híbrido de Agentes & IA
- **Extractor & Auditor**:
  - Motor primário determinístico via `pdfplumber` e tabelas de regex/regras (garantindo precisão contábil de 100%, velocidade milimétrica, zero custo de API e testes unitários 100% reproduzíveis sem dependência de rede).
  - LLM opcional para redação da fundamentação legal no campo `Observações`.
- **On-Call Responder Agent**:
  - Acionado exclusivamente em caso de incidentes operacionais via webhook do Prometheus Alertmanager.
  - Utiliza LLM (Groq / OpenAI / Anthropic) para analisar o diff do DOM e traces de erro, propondo a correção do seletor quebrado ou ajustando a fila de reenvio.

### 3.6 Observabilidade, Alertas & Agente On-Call
- **OpenTelemetry Tracer**:
  - Span raiz do ciclo mensal: `trace_id` propagado por todas as etapas (`email.received` -> `pdf.extracted` -> `audit.calculated` -> `form.submitted`).
  - Métricas Prometheus:
    - `condo_bill_processing_seconds` (histogram)
    - `condo_reimbursement_amount_brl` (gauge)
    - `condo_submission_status_total` (counter, labels: `status=success|failed`)
    - `condo_cycle_sla_days_remaining` (gauge)
- **Regras de Alerta (Prometheus Alertmanager)**:
  - `CondoSubmissionFailed`: Dispara imediatamente quando uma tentativa de submissão do formulário falha.
  - `CondoSlaBreachWarning`: Dispara se faltarem menos de 3 dias para o vencimento do condomínio e a submissão ainda não tiver ocorrido por falta de comprovante ou erro de parsing.
- **Agente On-Call (Self-Healing)**:
  - Servidor webhook recebe o alerta do Alertmanager.
  - Agente lê o `trace_id` e os últimos logs estruturados.
  - Cenários de remediação automática:
    - Se falha por instabilidade/timeout no Bitrix24: aplica retry exponencial com backoff e notifica o status.
    - Se falha por mudança de campo/seletor no formulário: aciona módulo com LLM para inspecionar o novo DOM da página Bitrix24, atualizar o mapa de seletores e reenviar a requisição.
    - Se faltar o comprovante: envia lembrete proativo via e-mail ou WhatsApp alertando que o prazo está se esgotando.

---

## 4. Banco de Dados & Modelos de Dados (PostgreSQL / SQLite)

```sql
CREATE TABLE ciclos_condominio (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competencia VARCHAR(7) NOT NULL, -- Formato: YYYY-MM
    condominio_nome VARCHAR(255) NOT NULL,
    data_vencimento DATE NOT NULL,
    valor_total NUMERIC(10, 2) NOT NULL,
    valor_ordinarias NUMERIC(10, 2) NOT NULL,
    valor_extraordinarias NUMERIC(10, 2) NOT NULL,
    valor_fundos NUMERIC(10, 2) NOT NULL,
    valor_leituras NUMERIC(10, 2) NOT NULL,
    valor_ressarcimento NUMERIC(10, 2) NOT NULL,
    boleto_pdf_path TEXT NOT NULL,
    comprovante_pix_path TEXT,
    status_ciclo VARCHAR(50) NOT NULL, -- PENDENTE_COMPROVANTE, PRONTO_PARA_ENVIO, ENVIADO, PROCESSADO_ALUGUEL
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE itens_rateio (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ciclo_id UUID REFERENCES ciclos_condominio(id) ON DELETE CASCADE,
    categoria VARCHAR(50) NOT NULL, -- ORDINARIA, EXTRAORDINARIA, FUNDOS, LEITURA
    descricao VARCHAR(255) NOT NULL,
    valor_unidade NUMERIC(10, 2) NOT NULL,
    valor_total_condominio NUMERIC(10, 2),
    responsabilidade VARCHAR(20) NOT NULL, -- LOCATARIO, LOCADOR
    justificativa_legal TEXT
);

CREATE TABLE submissoes_ressarcimento (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ciclo_id UUID REFERENCES ciclos_condominio(id),
    contrato_numero VARCHAR(50) NOT NULL,
    payload_enviado JSONB NOT NULL,
    status VARCHAR(50) NOT NULL, -- SUCESSO, ERRO, RETRY
    protocolo_retorno TEXT,
    screenshot_path TEXT,
    tentativas INT DEFAULT 1,
    trace_id VARCHAR(64) NOT NULL,
    enviado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE incidentes_on_call (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id VARCHAR(64) NOT NULL,
    alerta_nome VARCHAR(100) NOT NULL,
    diagnostico TEXT NOT NULL,
    acao_executada TEXT NOT NULL,
    status VARCHAR(50) NOT NULL, -- RESOLVIDO, ESCALADO_HUMANO
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. Não-Objetivos e Anti-Objetivos (Non-Goals & Anti-Goals)

- **Anti-Objetivo 1**: Nunca enviar submissões duplicadas no Bitrix24 para o mesmo ciclo/mês sem confirmação humana ou idempotência garantida no banco.
- **Anti-Objetivo 2**: Nunca trafegar ou registrar credenciais de e-mail, senhas bancárias ou dados pessoais sensíveis desnecessários nos logs de telemetria pública.
- **Non-Goal 1**: Não é escopo criar uma plataforma genérica para milhares de condomínios diferentes no primeiro momento; o foco de extração inicial é o formato SCI Syndkos (Edifício Villa Salomy) e envio para Ibagy.
- **Non-Goal 2**: Não automatiza o pagamento da conta bancária; o pagamento do PIX continua sendo feito pelo usuário em seu aplicativo bancário pessoal.

---

## 6. Stack Tecnológica Recomendada

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy + Uvicorn + Pydantic.
- **Extração & Automação**: PyPDF / pdfplumber + Playwright (ou httpx multipart).
- **Frontend**: React (Vite) + Tailwind CSS + Lucide Icons (sem emojis).
- **Banco de Dados**: PostgreSQL 16 (ou SQLite em testes locais).
- **Observabilidade**: OpenTelemetry Python SDK + Prometheus + Grafana + Loki (ou Jaeger).
- **DevOps & CI/CD**: Docker, Docker Compose, GitHub Actions (testes automatizados, lint e deploy).
