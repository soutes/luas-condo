import React, { useState } from "react";
import type { RateioItem, Responsabilidade } from "../types";
import { formatBRL } from "../utils";
import { ShieldCheck, UserCheck, Scale, FileText } from "lucide-react";

export interface AuditTableProps {
  items: RateioItem[];
}

export const AuditTable: React.FC<AuditTableProps> = ({ items }) => {
  const [filter, setFilter] = useState<"ALL" | Responsabilidade>("ALL");

  const filteredItems = items.filter((item) => {
    if (filter === "ALL") return true;
    return item.responsabilidade === filter;
  });

  const totalLocatario = items
    .filter((i) => i.responsabilidade === "LOCATARIO")
    .reduce((acc, curr) => acc + (typeof curr.valor_unidade === "string" ? parseFloat(curr.valor_unidade) : curr.valor_unidade), 0);

  const totalLocador = items
    .filter((i) => i.responsabilidade === "LOCADOR")
    .reduce((acc, curr) => acc + (typeof curr.valor_unidade === "string" ? parseFloat(curr.valor_unidade) : curr.valor_unidade), 0);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-none overflow-hidden">
      {/* Header and Filter Controls */}
      <div className="p-4 sm:p-5 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Scale className="w-5 h-5 text-[#f7941d]" />
            <h3 className="text-lg font-bold text-slate-100 tracking-wide">
              Rateio Detalhado & Segregação Legal
            </h3>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Classificação automatizada pela Lei do Inquilinato (Lei Federal 8.245/1991, Arts. 22 e 23)
          </p>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1 bg-slate-950 p-1 border border-slate-800 rounded-none self-start md:self-auto">
          <button
            type="button"
            onClick={() => setFilter("ALL")}
            className={`px-3 py-1.5 text-xs font-semibold rounded-none transition-colors ${
              filter === "ALL"
                ? "bg-[#f7941d] text-slate-950"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Todos ({items.length})
          </button>
          <button
            type="button"
            onClick={() => setFilter("LOCADOR")}
            className={`px-3 py-1.5 text-xs font-semibold rounded-none transition-colors ${
              filter === "LOCADOR"
                ? "bg-[#f7941d] text-slate-950"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Somente Locador
          </button>
          <button
            type="button"
            onClick={() => setFilter("LOCATARIO")}
            className={`px-3 py-1.5 text-xs font-semibold rounded-none transition-colors ${
              filter === "LOCATARIO"
                ? "bg-[#f7941d] text-slate-950"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Somente Locatario
          </button>
        </div>
      </div>

      {/* Summary Highlights */}
      <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-slate-800 bg-slate-950/60 border-b border-slate-800">
        <div className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <UserCheck className="w-4 h-4 text-slate-400" />
            <div>
              <span className="text-xs font-medium text-slate-400 block">Total Responsabilidade Locatario</span>
              <span className="text-sm font-semibold text-slate-200">
                Ordinarias & Leituras
              </span>
            </div>
          </div>
          <span className="text-base font-bold text-slate-200">
            {formatBRL(totalLocatario)}
          </span>
        </div>

        <div className="p-4 flex items-center justify-between bg-orange-950/20 border-l-2 border-l-[#f7941d]">
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="w-4 h-4 text-[#f7941d]" />
            <div>
              <span className="text-xs font-medium text-orange-400 block">Total a Ressarcir (Locador)</span>
              <span className="text-sm font-semibold text-slate-200">
                Fundos & Extraordinarias
              </span>
            </div>
          </div>
          <span className="text-lg font-extrabold text-[#f7941d]">
            {formatBRL(totalLocador)}
          </span>
        </div>
      </div>

      {/* Table Content */}
      {filteredItems.length === 0 ? (
        <div className="p-10 text-center text-slate-500 text-sm">
          <FileText className="w-8 h-8 mx-auto mb-2 opacity-40 text-slate-500" />
          Nenhum item de rateio encontrado.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase tracking-wider text-[11px]">
              <tr>
                <th className="py-3 px-4">Categoria</th>
                <th className="py-3 px-4">Descricao</th>
                <th className="py-3 px-4">Responsabilidade</th>
                <th className="py-3 px-4">Fundamentacao Legal</th>
                <th className="py-3 px-4 text-right">Valor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {filteredItems.map((item, idx) => {
                const isLocador = item.responsabilidade === "LOCADOR";
                return (
                  <tr
                    key={item.id || idx}
                    className={`hover:bg-slate-800/50 transition-colors ${
                      isLocador ? "bg-orange-950/10" : ""
                    }`}
                  >
                    <td className="py-3.5 px-4 font-mono text-[11px] text-slate-400">
                      {item.categoria}
                    </td>
                    <td className="py-3.5 px-4 font-medium text-slate-100">
                      {item.descricao}
                    </td>
                    <td className="py-3.5 px-4">
                      {isLocador ? (
                        <span className="inline-flex items-center px-2 py-0.5 text-[11px] font-bold bg-[#f7941d]/15 text-[#f7941d] border border-[#f7941d]/40 rounded-none">
                          LOCADOR
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700 rounded-none">
                          LOCATARIO
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-slate-400 font-mono text-[11px]">
                      {item.justificativa_legal || "-"}
                    </td>
                    <td className={`py-3.5 px-4 text-right font-semibold ${
                      isLocador ? "text-[#f7941d]" : "text-slate-200"
                    }`}>
                      {formatBRL(item.valor_unidade)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
