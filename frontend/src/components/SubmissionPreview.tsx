import React, { useState, useEffect } from "react";
import type { Ciclo } from "../types";
import { formatBRL, formatDateBR } from "../utils";
import {
  Send,
  AlertCircle,
  CheckCircle,
  Loader2,
  Copy,
  Check,
  Clock,
  ShieldCheck,
} from "lucide-react";

export interface SubmissionPreviewProps {
  ciclo: Ciclo;
  isSubmitting: boolean;
  onSubmit: (customObs?: string) => Promise<void>;
  submissionResult: {
    status: string;
    protocolo?: string | null;
    mensagem: string;
  } | null;
  submitDisabled?: boolean;
}

export const SubmissionPreview: React.FC<SubmissionPreviewProps> = ({
  ciclo,
  isSubmitting,
  onSubmit,
  submissionResult,
  submitDisabled = false,
}) => {
  const [copied, setCopied] = useState(false);

  const despesasLocador =
    typeof ciclo.valor_ressarcimento === "string"
      ? parseFloat(ciclo.valor_ressarcimento)
      : ciclo.valor_ressarcimento;

  const descontoAluguel = ciclo.valor_desconto_aluguel
    ? typeof ciclo.valor_desconto_aluguel === "string"
      ? parseFloat(ciclo.valor_desconto_aluguel)
      : ciclo.valor_desconto_aluguel
    : 0;

  const saldoResidual =
    ciclo.valor_saldo_residual !== undefined && ciclo.valor_saldo_residual !== null
      ? typeof ciclo.valor_saldo_residual === "string"
        ? parseFloat(ciclo.valor_saldo_residual)
        : ciclo.valor_saldo_residual
      : Math.max(0, despesasLocador - descontoAluguel);

  const isConciliado =
    ciclo.status_ciclo === "CONCILIADO_SEM_PENDENCIA" || saldoResidual <= 0;

  // Generate dynamic formatted observations memo text
  const locadorItems = (ciclo.itens || []).filter(
    (i) => i.responsabilidade === "LOCADOR"
  );

  const defaultMemo = [
    "Solicitacao de ressarcimento de despesas condominiais de responsabilidade do locador (Art. 22 da Lei 8.245/91).",
    `Condominio: ${ciclo.condominio_nome}`,
    `Competencia: ${ciclo.competencia} | Vencimento: ${formatDateBR(ciclo.data_vencimento)}`,
    "",
    "Itens de responsabilidade do locador apurados no rateio condominial:",
    ...(locadorItems.length > 0
      ? locadorItems.map(
          (it) =>
            `- ${it.descricao}: ${formatBRL(it.valor_unidade)} (${it.justificativa_legal || "Art. 22 da Lei 8.245/91"})`
        )
      : ["- Sem despesas do locador apuradas"]),
    "",
    `Total despesas locador apuradas: ${formatBRL(despesasLocador)}`,
    ...(descontoAluguel > 0
      ? [
          `Descontos ja aplicados na fatura de aluguel: -${formatBRL(descontoAluguel)}`,
          `Saldo residual devido solicitado neste protocolo: ${formatBRL(saldoResidual)}`,
        ]
      : []),
    "",
    "Seguem em anexo o boleto condominial detalhado e o respectivo comprovante de pagamento.",
  ].join("\n");

  const [memo, setMemo] = useState(defaultMemo);

  useEffect(() => {
    setMemo(defaultMemo);
  }, [ciclo.id, ciclo.valor_saldo_residual, ciclo.valor_desconto_aluguel]);

  const handleCopy = () => {
    navigator.clipboard.writeText(memo);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const hasBoletoCondo = Boolean(ciclo.boleto_pdf_path);
  const hasBoletoAluguel = Boolean(ciclo.boleto_aluguel_path);
  const hasComprovante = Boolean(ciclo.comprovante_pix_path);
  const isEnviado = ciclo.status_ciclo === "ENVIADO";
  const latestSubmissao =
    ciclo.submissoes && ciclo.submissoes.length > 0
      ? ciclo.submissoes[ciclo.submissoes.length - 1]
      : null;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-none overflow-hidden space-y-0">
      {/* Header */}
      <div className="p-4 sm:p-5 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Send className="w-5 h-5 text-[#f7941d]" />
          <h3 className="text-lg font-bold text-slate-100 tracking-wide">
            Submissao Bitrix24 / Ibagy
          </h3>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-none transition-colors"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span>Copiado</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>Copiar Texto</span>
              </>
            )}
          </button>
        </div>
      </div>

      <div className="p-4 sm:p-5 space-y-5">
        {/* Verification Status / Log */}
        {ciclo.detalhes_verificacao && (
          <div className="p-3 bg-slate-950 border border-slate-800 text-xs text-slate-300 flex items-start gap-2.5">
            <Clock className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">
                Registro de Verificacao Mensal
              </span>
              <p className="text-slate-300 leading-relaxed">
                {ciclo.detalhes_verificacao}
              </p>
              {ciclo.ultima_verificacao && (
                <span className="text-[10px] text-slate-500 font-mono block">
                  Data: {formatDateBR(ciclo.ultima_verificacao)}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Document Verification Checklist */}
        <div>
          <span className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Checklist de Documentos Mensais
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {/* Boleto Condominio */}
            <div className="p-2.5 bg-slate-950 border border-slate-800 rounded-none">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-200 truncate block">
                  Boleto Condomínio
                </span>
                {hasBoletoCondo ? (
                  <span className="px-1.5 py-0.2 text-[9px] font-bold bg-emerald-950/60 text-emerald-400 border border-emerald-700/50">
                    OK
                  </span>
                ) : (
                  <span className="px-1.5 py-0.2 text-[9px] font-bold bg-amber-950/60 text-amber-400 border border-amber-700/50">
                    Pendente
                  </span>
                )}
              </div>
              <span className="text-[10px] text-slate-500 font-mono truncate block">
                {ciclo.boleto_pdf_path
                  ? ciclo.boleto_pdf_path.split(/[\\/]/).pop()
                  : "Nao localizado"}
              </span>
            </div>

            {/* Boleto Aluguel */}
            <div className="p-2.5 bg-slate-950 border border-slate-800 rounded-none">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-200 truncate block">
                  Boleto Aluguel Ibagy
                </span>
                {hasBoletoAluguel ? (
                  <span className="px-1.5 py-0.2 text-[9px] font-bold bg-emerald-950/60 text-emerald-400 border border-emerald-700/50">
                    OK
                  </span>
                ) : (
                  <span className="px-1.5 py-0.2 text-[9px] font-bold bg-amber-950/60 text-amber-400 border border-amber-700/50">
                    Pendente
                  </span>
                )}
              </div>
              <span className="text-[10px] text-slate-500 font-mono truncate block">
                {ciclo.boleto_aluguel_path
                  ? ciclo.boleto_aluguel_path.split(/[\\/]/).pop()
                  : "Nao localizado"}
              </span>
            </div>

            {/* Comprovante PIX */}
            <div className="p-2.5 bg-slate-950 border border-slate-800 rounded-none">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-200 truncate block">
                  Comprovante PIX
                </span>
                {hasComprovante ? (
                  <span className="px-1.5 py-0.2 text-[9px] font-bold bg-emerald-950/60 text-emerald-400 border border-emerald-700/50">
                    OK
                  </span>
                ) : (
                  <span className="px-1.5 py-0.2 text-[9px] font-bold bg-amber-950/60 text-amber-400 border border-amber-700/50">
                    Pendente
                  </span>
                )}
              </div>
              <span className="text-[10px] text-slate-500 font-mono truncate block">
                {ciclo.comprovante_pix_path
                  ? ciclo.comprovante_pix_path.split(/[\\/]/).pop()
                  : "Pendente"}
              </span>
            </div>
          </div>
        </div>

        {/* Differential Reconciliation Box */}
        <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-none space-y-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
            Auditoria Diferencial de Aluguel
          </span>
          <div className="grid grid-cols-3 gap-2 pt-1 border-t border-slate-800 text-center">
            <div>
              <span className="text-[10px] uppercase text-slate-400 block">
                Despesas Locador
              </span>
              <span className="text-xs font-bold text-slate-200">
                {formatBRL(despesasLocador)}
              </span>
            </div>
            <div>
              <span className="text-[10px] uppercase text-slate-400 block">
                Abatido no Aluguel
              </span>
              <span className="text-xs font-bold text-emerald-400">
                -{formatBRL(descontoAluguel)}
              </span>
            </div>
            <div>
              <span className="text-[10px] uppercase text-orange-400 block font-bold">
                Saldo Devido
              </span>
              <span className="text-sm font-black text-[#f7941d]">
                {formatBRL(saldoResidual)}
              </span>
            </div>
          </div>

          {/* List of items already discounted */}
          {ciclo.itens_abatidos_aluguel && ciclo.itens_abatidos_aluguel.length > 0 && (
            <div className="pt-2 border-t border-slate-800/80 text-[11px] text-slate-400 space-y-1">
              <span className="font-semibold text-slate-300 block">
                Itens abatidos na fatura de aluguel:
              </span>
              {ciclo.itens_abatidos_aluguel.map((item, idx) => (
                <div key={idx} className="flex justify-between font-mono text-[10px]">
                  <span>{item.descricao}</span>
                  <span className="text-emerald-400">-{formatBRL(item.valor)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Fully Reconciled Banner */}
        {isConciliado && (
          <div className="p-3 bg-emerald-950/20 border border-emerald-700/40 text-emerald-300 rounded-none flex items-start gap-2.5">
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div className="text-xs space-y-1">
              <span className="font-bold uppercase tracking-wider block">
                Ciclo Conciliado Sem Pendencia
              </span>
              <p className="text-slate-300">
                Todas as despesas de responsabilidade do locador ja foram compensadas
                automaticamente na fatura de aluguel. Nao ha saldo a ressarcir nem
                necessidade de abertura de protocolo na Ibagy.
              </p>
            </div>
          </div>
        )}

        {/* Submission Result Alerts */}
        {submissionResult && (
          <div
            className={`p-4 border rounded-none flex items-start gap-3 ${
              submissionResult.status === "SUCESSO"
                ? "bg-emerald-950/40 border-emerald-600/60 text-emerald-200"
                : "bg-red-950/40 border-red-600/60 text-red-200"
            }`}
          >
            {submissionResult.status === "SUCESSO" ? (
              <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            )}
            <div className="space-y-1">
              <h5 className="text-xs font-bold uppercase tracking-wider">
                {submissionResult.status === "SUCESSO"
                  ? "Submissao Protocolada com Sucesso"
                  : "Falha na Submissao"}
              </h5>
              <p className="text-xs">{submissionResult.mensagem}</p>
              {submissionResult.protocolo && (
                <div className="text-xs font-mono font-bold mt-2 inline-block bg-slate-950 px-2.5 py-1 border border-emerald-500/40">
                  Protocolo: {submissionResult.protocolo}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Existing Submission History if already sent */}
        {isEnviado && !submissionResult && latestSubmissao && (
          <div className="p-4 bg-emerald-950/20 border border-emerald-700/40 text-emerald-300 rounded-none flex items-start gap-3">
            <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <h5 className="text-xs font-bold uppercase tracking-wider">
                Solicitacao Ja Enviada
              </h5>
              <p className="text-xs text-slate-300 mt-0.5">
                Protocolo:{" "}
                <span className="font-mono font-bold text-emerald-400">
                  {latestSubmissao.protocolo_retorno || "Confirmado"}
                </span>{" "}
                em {formatDateBR(latestSubmissao.enviado_em)}
              </p>
            </div>
          </div>
        )}

        {/* Formatted Observations Memo Preview */}
        {!isConciliado && (
          <div>
            <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Texto do Memorando / Observacoes para Ibagy
            </label>
            <textarea
              value={memo}
              onChange={(e) => setMemo(e.target.value)}
              rows={6}
              className="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs font-mono p-3 rounded-none focus:outline-none focus:border-[#f7941d] leading-relaxed resize-y"
            />
          </div>
        )}

        {/* Action Button */}
        <div className="pt-2">
          {isConciliado ? (
            <button
              type="button"
              disabled
              className="w-full flex items-center justify-center gap-2 px-6 py-3.5 bg-slate-800 text-slate-400 font-bold text-sm uppercase tracking-wider rounded-none cursor-not-allowed border border-slate-700"
            >
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Conciliado (R$ 0,00 a ressarcir)</span>
            </button>
          ) : (
            <button
              type="button"
              disabled={isSubmitting || !hasComprovante || submitDisabled}
              onClick={() => onSubmit(memo)}
              className="w-full flex items-center justify-center gap-2 px-6 py-3.5 bg-[#f7941d] hover:bg-[#e08316] text-slate-950 font-bold text-sm uppercase tracking-wider rounded-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-[#f7941d]/10"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-slate-950" />
                  <span>Enviando para Bitrix24...</span>
                </>
              ) : !hasComprovante ? (
                <>
                  <Clock className="w-4 h-4" />
                  <span>Aguardando Comprovante PIX</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>
                    {isEnviado
                      ? `Reenviar para Bitrix24 (${formatBRL(saldoResidual)})`
                      : `Aprovar e Enviar para Ibagy (${formatBRL(saldoResidual)})`}
                  </span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
