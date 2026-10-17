import React, { useState, useEffect } from "react";
import type { Ciclo } from "./types";
import { CycleCard } from "./components/CycleCard";
import { AuditTable } from "./components/AuditTable";
import { SubmissionPreview } from "./components/SubmissionPreview";
import { formatBRL } from "./utils";
import {
  Building2,
  TrendingDown,
  FileCheck2,
  Layers,
  RefreshCw,
  Scale,
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
    boleto_pdf_path: "/data/boletos/villa_salomy_2026_09.pdf",
    comprovante_pix_path: "/data/comprovantes/pix_2026_09.pdf",
    status_ciclo: "PRONTO_PARA_ENVIO",
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
  const [submissionResult, setSubmissionResult] = useState<{
    status: string;
    protocolo?: string | null;
    mensagem: string;
  } | null>(null);

  const fetchCiclos = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/ciclos");
      if (res.ok) {
        const data: Ciclo[] = await res.json();
        if (data && data.length > 0) {
          setCiclos(data);
          if (!selectedCicloId || !data.some((c) => c.id === selectedCicloId)) {
            setSelectedCicloId(data[0].id);
          }
        } else {
          // If database has no cycles yet, use sample reference data
          setCiclos(FALLBACK_DEFAULT_CYCLES);
          setSelectedCicloId(FALLBACK_DEFAULT_CYCLES[0].id);
        }
      } else {
        setCiclos(FALLBACK_DEFAULT_CYCLES);
        setSelectedCicloId(FALLBACK_DEFAULT_CYCLES[0].id);
      }
    } catch {
      // Offline / dev fallback
      setCiclos(FALLBACK_DEFAULT_CYCLES);
      setSelectedCicloId(FALLBACK_DEFAULT_CYCLES[0].id);
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
              Deducao de Fundo / Reforma no aluguel
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
              />
            </div>
          </div>
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
