import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DocumentosRetroativos } from "../components/DocumentosRetroativos";

describe("Documentos Retroativos Upload", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders month input, file picker, and upload action", () => {
    render(<DocumentosRetroativos />);

    expect(screen.getByText(/Documentos retroativos/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Competencia do lote/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Arquivos/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enviar e Auditar/i })).toBeDisabled();
  });

  it("uploads files with competencia hint and shows per-file result", async () => {
    const fakePdf = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "boleto_2026-07.pdf", {
      type: "application/pdf",
    });
    const onUploaded = vi.fn();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url === "/api/ciclos/documentos") {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                arquivos: [
                  { arquivo: "boleto_2026-07.pdf", tipo: "CONDO_BILL", arquivado: true },
                ],
                ciclos_afetados: [
                  { id: "abc", competencia: "2026-07", status_ciclo: "PENDENTE_COMPROVANTE" },
                ],
              }),
          });
        }
        return Promise.reject(new Error("Unknown route"));
      })
    );

    render(<DocumentosRetroativos onUploaded={onUploaded} />);

    const input = screen.getByLabelText(/Arquivos/i) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fakePdf] } });

    const monthInput = screen.getByLabelText(/Competencia do lote/i) as HTMLInputElement;
    fireEvent.change(monthInput, { target: { value: "2026-07" } });

    const btn = screen.getByRole("button", { name: /Enviar e Auditar/i });
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText(/Boleto de condominio/i)).toBeInTheDocument();
      expect(screen.getByText(/Competencia 2026-07/i)).toBeInTheDocument();
    });
    expect(onUploaded).toHaveBeenCalled();
  });

  it("flags files the classifier could not recognize", async () => {
    const fakeTxt = new File(["plain text"], "arquivo_qualquer.txt", { type: "text/plain" });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              arquivos: [
                { arquivo: "arquivo_qualquer.txt", tipo: "UNKNOWN", arquivado: false },
              ],
              ciclos_afetados: [],
            }),
        })
      )
    );

    render(<DocumentosRetroativos />);

    const input = screen.getByLabelText(/Arquivos/i) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fakeTxt] } });

    fireEvent.click(screen.getByRole("button", { name: /Enviar e Auditar/i }));

    await waitFor(() => {
      expect(screen.getByText(/Desconhecido/i)).toBeInTheDocument();
    });
  });

  it("shows network error when upload fails", async () => {
    const fakePdf = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "boleto.pdf", {
      type: "application/pdf",
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.reject(new Error("network down")))
    );

    render(<DocumentosRetroativos />);

    const input = screen.getByLabelText(/Arquivos/i) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fakePdf] } });

    fireEvent.click(screen.getByRole("button", { name: /Enviar e Auditar/i }));

    await waitFor(() => {
      expect(screen.getByText(/Erro de rede no upload/i)).toBeInTheDocument();
    });
  });
});
