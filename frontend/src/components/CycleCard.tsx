import React from "react";
import type { Ciclo, StatusCiclo } from "../types";
import { formatBRL, formatDateBR } from "../utils";
import { Calendar, ArrowUpRight, Clock, Send, FileCheck } from "lucide-react";

export interface CycleCardProps {
  ciclo: Ciclo;
  isSelected: boolean;
  onSelect: (ciclo: Ciclo) => void;
}

const statusConfig: Record<
  StatusCiclo,
  { label: string; bg: string; text: string; border: string; icon: React.FC<{ className?: string }> }
> = {
  PENDENTE_COMPROVANTE: {
    label: "Pendente Comprovante",
    bg: "bg-amber-950/30",
    text: "text-amber-400",
    border: "border-amber-700/50",
    icon: Clock,
  },
  PRONTO_PARA_ENVIO: {
    label: "Pronto para Envio",
    bg: "bg-blue-950/30",
    text: "text-blue-400",
    border: "border-blue-700/50",
    icon: ArrowUpRight,
  },
  ENVIADO: {
    label: "Enviado Bitrix24",
    bg: "bg-emerald-950/30",
    text: "text-emerald-400",
    border: "border-emerald-700/50",
    icon: Send,
  },
  PROCESSADO_ALUGUEL: {
    label: "Deducao Aplicada",
    bg: "bg-purple-950/30",
    text: "text-purple-400",
    border: "border-purple-700/50",
    icon: FileCheck,
  },
};

export const CycleCard: React.FC<CycleCardProps> = ({
  ciclo,
  isSelected,
  onSelect,
}) => {
  const statusInfo = statusConfig[ciclo.status_ciclo] || statusConfig.PENDENTE_COMPROVANTE;
  const StatusIcon = statusInfo.icon;

  return (
    <div
      onClick={() => onSelect(ciclo)}
      className={`p-4 cursor-pointer transition-all border rounded-none text-left bg-slate-900 ${
        isSelected
          ? "border-[#f7941d] bg-slate-900 ring-1 ring-[#f7941d]"
          : "border-slate-800 hover:border-slate-700 hover:bg-slate-800/40"
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <span className="text-[11px] font-mono uppercase text-slate-400 tracking-wider">
            Competencia {ciclo.competencia}
          </span>
          <h4 className="text-sm font-bold text-slate-100 truncate max-w-[200px]">
            {ciclo.condominio_nome}
          </h4>
        </div>

        <div
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-none border ${statusInfo.bg} ${statusInfo.text} ${statusInfo.border}`}
        >
          <StatusIcon className="w-3 h-3" />
          <span>{statusInfo.label}</span>
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs text-slate-400 mb-4">
        <Calendar className="w-3.5 h-3.5 text-slate-500" />
        <span>Vencimento: {formatDateBR(ciclo.data_vencimento)}</span>
      </div>

      <div className="grid grid-cols-2 gap-2 pt-3 border-t border-slate-800/80">
        <div>
          <span className="text-[10px] uppercase font-medium text-slate-400 block">
            Total Boleto
          </span>
          <span className="text-xs font-semibold text-slate-300">
            {formatBRL(ciclo.valor_total)}
          </span>
        </div>

        <div className="text-right">
          <span className="text-[10px] uppercase font-medium text-orange-400 block">
            Ressarcimento
          </span>
          <span className="text-sm font-bold text-[#f7941d]">
            {formatBRL(ciclo.valor_ressarcimento)}
          </span>
        </div>
      </div>
    </div>
  );
};
