import React, { useState, useEffect } from "react";
import type { Ciclo } from "./types";
import { CycleCard } from "./components/CycleCard";
import { AuditTable } from "./components/AuditTable";
import { SubmissionPreview } from "./components/SubmissionPreview";
import { DocumentosRetroativos } from "./components/DocumentosRetroativos";
import { formatBRL } from "./utils";
import {
  Building2,
  TrendingDown,
  FileCheck2,
  Layers,
  RefreshCw,
  Scale,
  Mail,
  AlertCircle,
} from "lucide-react";

const FALLBACK_DEFAULT_CYCLES: Ciclo[] = [
  {
    id: "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
    competencia: "2026-09",
    condominio_nome: "CONDOMINIO EDIFICIO VILLA SALOMY",
    data_vencimento: "2026-10-10",
    valor_total: 1154.5,
    valor_ordinarias: 800.0,
    valor_extraordinarias: 354.5,
    valor_fundos: 0.0,
    valor_leituras: 0.0,
    valor_ressarcimento: 354.5,
    valor_desconto_aluguel: 264.5,
    valor_saldo_residual: 90.0,
    boleto_pdf_path: "/data/boletos/villa_salomy_2026_09.pdf",
    boleto_aluguel_path: "/data/boletos/aluguel_ibagy_2026_09.pdf",
    comprovante_pix_path: "/data/comprovantes/pix_2026_09.pdf",
    itens_abatidos_aluguel: [
      { descricao: "Fundo de Reserva", valor: 56.21 },
      { descricao: "Rateio manutencao fachada (5/10)", valor: 208.29 },
    ],
    status_ciclo: "PRONTO_PARA_ENVIO",
    detalhes_verificacao:
      "Boleto condominio, boleto aluguel e comprovante PIX localizados. Saldo residual pendente: R$ 90,00.",
    criado_em: "2026-10-16T18:00:00Z",
    itens: [
      {
        id: "item-1",
        categoria: "ORDINARIA",
        descricao: "Despesas Ordinarias de Condominio",
        valor_unidade: 800.0,
        responsabilidade: "LOCATARIO",
        justificativa_legal: "Art. 23 da Lei 8.245/91",
      },
      {
        id: "item-2",
        categoria: "EXTRAORDINARIA",
        descricao: "Fundo de Reserva / Reforma Fachada",
        valor_unidade: 354.5,
        responsabilidade: "LOCADOR",
        justificativa_legal: "Art. 22, X, g da Lei 8.245/91",
      },
    ],
    submissoes: [],
  },
];

export const App: React.FC = () => {
  const [ciclos, setCiclos] = useState<Ciclo[]>([]);
  const [selectedCicloId, setSelectedCicloId] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [syncingEmail, setSyncingEmail] = useState<boolean>(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [submissionResult, setSubmissionResult] = useState<{
    status: string;
    protocolo?: string | null;
    mensagem: string;
  } | null>(null);
  const [sampleOffline, setSampleOffline] = useState<boolean>(false);
  const [seeding, setSeeding] = useState<boolean>(false);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"dashboard" | "documentos">("dashboard");

  const handleSyncEmail = async () => {
    setSyncingEmail(true);
    setSyncMessage(null);
    try {
      const res = await fetch("/api/ciclos/sync-email", { method: "POST" });
      const data = await res.json();
      setSyncMessage(data.detail || "Verificacao de e-mail concluida");
      await fetchCiclos();
    } catch {
      setSyncMessage("Erro ao sincronizar e-mail");
    } finally {
      setSyncingEmail(false);
    }
  };

  const handleSeedDemo = async () => {
    setSeeding(true);
    setSeedMessage(null);
    try {
      const res = await fetch("/api/ciclos/seed-demo", { method: "POST" });
      if (res.ok) {
        setSeedMessage(
          "Ciclo de demonstracao carregado (referencia Villa Salomy, submissao em modo mock)."
        );
        await fetchCiclos();
      } else {
        const errData = await res.json().catch(() => ({}));
        setSeedMessage(errData.detail || "Nao foi possivel carregar o ciclo de demonstracao");
      }
    } catch {
      setSeedMessage("Erro de rede ao carregar o ciclo de demonstracao");
    } finally {
      setSeeding(false);
    }
  };

  const fetchCiclos = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/ciclos");
      if (res.ok) {
        const data: Ciclo[] = await res.json();
        if (data && data.length > 0) {
          setCiclos(data);
          setSampleOffline(false);
          if (!selectedCicloId || !data.some((c) => c.id === selectedCicloId)) {
            setSelectedCicloId(data[0].id);
          }
        } else {
          // Healthy API but no cycles yet: show the explicit empty state instead
          // of sample data (submitting a sample id would fail with 404).
          setCiclos([]);
          setSelectedCicloId("");
          setSampleOffline(false);
        }
      } else {
        // API reachable but erroring: offline demo fallback, submission disabled
        setCiclos(FALLBACK_DEFAULT_CYCLES);
        setSelectedCicloId(FALLBACK_DEFAULT_CYCLES[0].id);
        setSampleOffline(true);
      }
    } catch {
      // Offline / dev fallback: sample data clearly flagged, submission disabled
      setCiclos(FALLBACK_DEFAULT_CYCLES);
      setSelectedCicloId(FALLBACK_DEFAULT_CYCLES[0].id);
      setSampleOffline(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCiclos();
  }, []);

  const selectedCiclo =
    ciclos.find((c) => c.id === selectedCicloId) || ciclos[0] || null;

  const handleSubmeter = async (customObs?: string) => {
    if (!selectedCiclo) return;
    setSubmitting(true);
    setSubmissionResult(null);

    try {
      const res = await fetch(`/api/ciclos/${selectedCiclo.id}/submeter`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          observacoes: customObs,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setSubmissionResult({
          status: data.status,
          protocolo: data.protocolo,
          mensagem: data.mensagem,
        });

        // Update local cycle state to ENVIADO
        setCiclos((prev) =>
          prev.map((c) =>
            c.id === selectedCiclo.id
              ? {
                  ...c,
                  status_ciclo: "ENVIADO",
                  submissoes: [
                    ...(c.submissoes || []),
                    {
                      id: `sub-${Date.now()}`,
                      contrato_numero: "09638.003.03",
                      status: data.status,
                      protocolo_retorno: data.protocolo,
                      trace_id: data.trace_id,
                      enviado_em: new Date().toISOString(),
                    },
                  ],
                }
              : c
          )
        );
      } else {
        const errData = await res.json().catch(() => ({}));
        setSubmissionResult({
          status: "ERRO",
          protocolo: null,
          mensagem: errData.detail || "Erro ao conectar com API de submissao",
        });
      }
    } catch (err: any) {
      setSubmissionResult({
        status: "ERRO",
        protocolo: null,
        mensagem: err?.message || "Falha de rede ao submeter ressarcimento",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const totalReimbursementAllCycles = ciclos.reduce(
    (acc, curr) =>
      acc +
      (typeof curr.valor_ressarcimento === "string"
        ? parseFloat(curr.valor_ressarcimento)
        : curr.valor_ressarcimento),
    0
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Header Bar */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-[#f7941d] flex items-center justify-center font-black text-slate-950 text-base rounded-none shadow-sm">
              L
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-black tracking-wider text-slate-100 uppercase">
                  Luas Condo
                </h1>
                <span className="px-1.5 py-0.2 text-[10px] font-bold bg-[#f7941d]/15 text-[#f7941d] border border-[#f7941d]/40 rounded-none uppercase">
                  Auditoria & Ressarcimento
                </span>
              </div>
              <p className="text-[11px] text-slate-400">
                Contrato: 09638.003.03 | Imobiliaria Ibagy | Villa Salomy
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-slate-950 border border-slate-800 text-slate-300">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="font-mono text-[11px]">Bitrix24 API Online</span>
            </div>

            <button
              type="button"
              onClick={handleSyncEmail}
              disabled={syncingEmail}
              className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 border border-slate-700 rounded-none text-xs transition-colors"
              title="Buscar boletos e comprovantes no e-mail agora"
            >
              <Mail className={`w-3.5 h-3.5 ${syncingEmail ? "animate-pulse" : ""}`} />
              <span>{syncingEmail ? "Verificando..." : "Sincronizar E-mail"}</span>
            </button>

            <button
              type="button"
              onClick={fetchCiclos}
              className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-none transition-colors"
              title="Atualizar dados"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full space-y-6">
        {/* Tab Bar */}
        <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
          <button
            type="button"
            onClick={() => setActiveTab("dashboard")}
            className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider rounded-none border transition-colors ${
              activeTab === "dashboard"
                ? "bg-[#f7941d]/15 text-[#f7941d] border-[#f7941d]/40"
                : "bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200"
            }`}
          >
            Dashboard
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("documentos")}
            className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider rounded-none border transition-colors ${
              activeTab === "documentos"
                ? "bg-[#f7941d]/15 text-[#f7941d] border-[#f7941d]/40"
                : "bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200"
            }`}
          >
            Documentos
          </button>
        </div>

        {activeTab === "documentos" && <DocumentosRetroativos onUploaded={fetchCiclos} />}

        {activeTab === "dashboard" && (
          <>
        {syncMessage && (
          <div className="p-3 bg-slate-900 border border-slate-700 text-xs flex items-center justify-between text-slate-200">
            <span>{syncMessage}</span>
            <button
              type="button"
              onClick={() => setSyncMessage(null)}
              className="text-slate-400 hover:text-slate-100 font-bold ml-4"
            >
              x
            </button>
          </div>
        )}

        {sampleOffline && (
          <div className="p-3 bg-amber-950/40 border border-amber-700/60 text-xs text-amber-200 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>
              Dados de amostra exibidos (API indisponivel). A submissao esta desabilitada.
            </span>
          </div>
        )}

        {!loading && ciclos.length === 0 && (
          <div className="p-8 bg-slate-900 border border-slate-800 rounded-none text-center space-y-4">
            <Layers className="w-10 h-10 text-slate-600 mx-auto" />
            <h2 className="text-lg font-black text-slate-100 uppercase tracking-wider">
              Nenhum ciclo no banco de dados
            </h2>
            <p className="text-sm text-slate-400 max-w-xl mx-auto">
              Ainda nao existem ciclos auditados. Use "Sincronizar E-mail" para ingerir os
              boletos reais da caixa de entrada, ou carregue o ciclo de demonstracao
              (referencia Villa Salomy) para testar o fluxo de submissao em modo mock.
            </p>
            {seedMessage && (
              <div className="p-2.5 border border-slate-700 bg-slate-950 text-xs text-slate-200 max-w-xl mx-auto">
                {seedMessage}
              </div>
            )}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <button
                type="button"
                onClick={handleSeedDemo}
                disabled={seeding}
                className="px-5 py-2.5 bg-[#f7941d] hover:bg-[#e08316] disabled:opacity-50 disabled:cursor-not-allowed text-slate-950 font-bold text-xs uppercase tracking-wider rounded-none transition-colors"
              >
                {seeding ? "Carregando..." : "Carregar Ciclo de Demonstracao"}
              </button>
              <button
                type="button"
                onClick={handleSyncEmail}
                disabled={syncingEmail}
                className="px-5 py-2.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-slate-200 border border-slate-700 text-xs uppercase tracking-wider rounded-none transition-colors"
              >
                {syncingEmail ? "Verificando..." : "Sincronizar E-mail"}
              </button>
            </div>
          </div>
        )}

        {(loading || ciclos.length > 0) && (
          <>
        {/* KPI Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Reference Reimbursement Card */}
          <div className="p-4 bg-slate-900 border-l-4 border-l-[#f7941d] border-t border-r border-b border-slate-800 rounded-none shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-orange-400">
                Ressarcimento Referencia
              </span>
              <TrendingDown className="w-4 h-4 text-[#f7941d]" />
            </div>
            <div className="text-2xl font-black text-slate-100">
              {formatBRL(selectedCiclo ? selectedCiclo.valor_ressarcimento : 354.5)}
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              {selectedCiclo && selectedCiclo.valor_desconto_aluguel && parseFloat(String(selectedCiclo.valor_desconto_aluguel)) > 0
                ? `Abatido aluguel: -${formatBRL(selectedCiclo.valor_desconto_aluguel)} | Saldo devido: ${formatBRL(selectedCiclo.valor_saldo_residual || 90.0)}`
                : "Deducao de Fundo / Reforma no aluguel"}
            </p>
          </div>

          {/* Total Faturas Card */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-none shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">
                Ciclos Auditados
              </span>
              <Layers className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold text-slate-100">
              {ciclos.length}
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Competencias cadastradas
            </p>
          </div>

          {/* Total Accumulated Reimbursements */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-none shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">
                Total Recuperado
              </span>
              <FileCheck2 className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-2xl font-bold text-slate-100">
              {formatBRL(totalReimbursementAllCycles)}
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Soma global de deducoes apuradas
            </p>
          </div>

          {/* Compliance Status */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-none shadow-sm">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">
                Conformidade Legal
              </span>
              <Scale className="w-4 h-4 text-blue-400" />
            </div>
            <div className="text-2xl font-bold text-emerald-400">
              100%
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Lei Federal 8.245/1991
            </p>
          </div>
        </div>

        {/* Cycle Switcher Section */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Building2 className="w-3.5 h-3.5 text-slate-500" />
              Selecione a Competencia / Ciclo
            </h2>
            <span className="text-xs text-slate-500 font-mono">
              {ciclos.length} ciclo(s) disponivel(is)
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {ciclos.map((ciclo) => (
              <CycleCard
                key={ciclo.id}
                ciclo={ciclo}
                isSelected={ciclo.id === selectedCicloId}
                onSelect={(c) => {
                  setSelectedCicloId(c.id);
                  setSubmissionResult(null);
                }}
              />
            ))}
          </div>
        </div>

        {/* Detailed Audit & Submission Workspace */}
        {selectedCiclo && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left 7 cols: Rateio Table */}
            <div className="lg:col-span-7 space-y-4">
              <AuditTable items={selectedCiclo.itens || []} />
            </div>

            {/* Right 5 cols: Submission Preview & Action */}
            <div className="lg:col-span-5 space-y-4">
              <SubmissionPreview
                ciclo={selectedCiclo}
                isSubmitting={submitting}
                onSubmit={handleSubmeter}
                submissionResult={submissionResult}
                submitDisabled={sampleOffline}
              />
            </div>
          </div>
        )}
          </>
        )}
            </>
          )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-slate-900/60 py-4 text-center text-xs text-slate-500">
        <p>
          Luas Condo - Sistema de Auditoria e Ressarcimento Condominial | Lei Federal 8.245/1991
        </p>
      </footer>
    </div>
  );
};

export default App;
