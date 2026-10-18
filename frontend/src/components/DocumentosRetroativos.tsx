import React, { useRef, useState } from "react";
import { Upload, FileText, CheckCircle, AlertCircle, Loader2 } from "lucide-react";

export interface DocumentosRetroativosProps {
  onUploaded?: () => void;
}

interface ArquivoResultado {
  arquivo: string;
  tipo: string;
  arquivado: boolean;
}

interface CicloAfetado {
  id: string;
  competencia: string;
  status_ciclo: string;
}

interface UploadResultado {
  arquivos: ArquivoResultado[];
  ciclos_afetados: CicloAfetado[];
}

const tipoLabel = (tipo: string): string => {
  switch (tipo) {
    case "CONDO_BILL":
      return "Boleto de condominio";
    case "RENTAL_BILL":
      return "Boleto de aluguel (Ibagy)";
    case "PIX_RECEIPT":
      return "Comprovante PIX";
    case "MUITO_GRANDE":
      return "Arquivo muito grande (max 20MB)";
    default:
      return "Desconhecido (ignorado)";
  }
};

export const DocumentosRetroativos: React.FC<DocumentosRetroativosProps> = ({
  onUploaded,
}) => {
  const [competencia, setCompetencia] = useState<string>("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState<boolean>(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<UploadResultado | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setErro(null);
    setResultado(null);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      if (competencia) {
        fd.append("competencia", competencia);
      }
      const res = await fetch("/api/ciclos/documentos", { method: "POST", body: fd });
      if (res.ok) {
        const data: UploadResultado = await res.json();
        setResultado(data);
        setFiles([]);
        if (inputRef.current) {
          inputRef.current.value = "";
        }
        onUploaded?.();
      } else {
        const errData = await res.json().catch(() => ({}));
        setErro(errData.detail || "Falha no upload dos documentos");
      }
    } catch {
      setErro("Erro de rede no upload dos documentos");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-5 bg-slate-900 border border-slate-800 rounded-none space-y-4">
      <div>
        <h2 className="text-sm font-black uppercase tracking-wider text-slate-100">
          Documentos retroativos
        </h2>
        <p className="text-xs text-slate-400 mt-1 max-w-3xl">
          Envie boletos de condominio, boletos de aluguel e comprovantes PIX de meses ja
          fechados (PDF, PNG ou JPG, ate 30 arquivos de 20MB). Indique a competencia do
          lote para vincular cada comprovante ao mes correto. A auditoria legal usa a
          mesma engine do fluxo de e-mail. Depois de enviar, revise e submeta mes a mes
          na aba Dashboard.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Competencia do lote
          </span>
          <input
            type="month"
            value={competencia}
            onChange={(e) => setCompetencia(e.target.value)}
            className="mt-1 w-full px-3 py-2 bg-slate-950 border border-slate-700 text-slate-100 text-sm rounded-none focus:border-[#f7941d] focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Arquivos
          </span>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg"
            onChange={(e) => setFiles(Array.from(e.target.files || []))}
            className="mt-1 w-full text-xs text-slate-300 bg-slate-950 border border-slate-700 rounded-none py-1.5 px-2 file:mr-3 file:px-3 file:py-1.5 file:bg-slate-800 file:border file:border-slate-700 file:text-slate-200 file:rounded-none file:cursor-pointer focus:border-[#f7941d] focus:outline-none"
          />
        </label>
      </div>

      {files.length > 0 && (
        <ul className="text-xs text-slate-300 space-y-1">
          {files.map((f) => (
            <li key={f.name} className="flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
              <span className="font-mono">{f.name}</span>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={handleUpload}
        disabled={uploading || files.length === 0}
        className="px-5 py-2.5 bg-[#f7941d] hover:bg-[#e08316] disabled:opacity-50 disabled:cursor-not-allowed text-slate-950 font-bold text-xs uppercase tracking-wider rounded-none transition-colors flex items-center gap-2"
      >
        {uploading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Upload className="w-4 h-4" />
        )}
        {uploading ? "Enviando..." : "Enviar e Auditar"}
      </button>

      {erro && (
        <div className="p-3 border border-red-800 bg-red-950/40 text-xs text-red-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{erro}</span>
        </div>
      )}

      {resultado && (
        <div className="space-y-3 border border-slate-700 bg-slate-950 p-3">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Resultado do upload
          </div>
          <ul className="text-xs space-y-1">
            {resultado.arquivos.map((a) => (
              <li key={a.arquivo} className="flex items-center gap-1.5 text-slate-300">
                {a.arquivado ? (
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                ) : (
                  <AlertCircle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                )}
                <span className="font-mono">{a.arquivo}</span>
                <span>- {tipoLabel(a.tipo)}</span>
              </li>
            ))}
          </ul>
          {resultado.ciclos_afetados.length > 0 && (
            <div className="text-xs text-slate-300 border-t border-slate-800 pt-2">
              <span className="font-bold uppercase tracking-wider text-slate-400">
                Ciclos atualizados:
              </span>
              <ul className="mt-1 space-y-1">
                {resultado.ciclos_afetados.map((c) => (
                  <li key={c.id}>
                    Competencia {c.competencia} - status {c.status_ciclo}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-slate-400">
                Revise cada ciclo na aba Dashboard e envie mes a mes.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
