import { useState } from "react";
import { KeyRound } from "lucide-react";
import { getAccessKey, setAccessKey } from "../auth";

export function AccessKey() {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState<boolean>(() => getAccessKey() !== "");

  const handleSave = () => {
    setAccessKey(draft.trim());
    setSaved(draft.trim() !== "");
    setDraft("");
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-none text-xs transition-colors"
        title="Chave usada para enviar, sincronizar e excluir"
      >
        <KeyRound className="w-3.5 h-3.5" />
        <span>Chave de acesso{saved ? "" : " (nao definida)"}</span>
      </button>
      {open && (
        <div className="absolute right-0 mt-1 z-20 w-72 p-3 bg-slate-900 border border-slate-700 space-y-2">
          <label htmlFor="access-key-input" className="block text-xs text-slate-300">
            Chave de acesso
          </label>
          <input
            id="access-key-input"
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 text-slate-200 text-xs font-mono p-2 rounded-none focus:outline-none focus:border-[#f7941d]"
          />
          <p className="text-[11px] text-slate-500">
            Fica salva so neste navegador. Deixe vazio e salve para remover.
          </p>
          <button
            type="button"
            onClick={handleSave}
            className="px-3 py-1.5 bg-[#f7941d] hover:bg-[#e08316] text-slate-950 text-xs font-bold uppercase tracking-wider rounded-none"
          >
            Salvar chave
          </button>
        </div>
      )}
    </div>
  );
}
