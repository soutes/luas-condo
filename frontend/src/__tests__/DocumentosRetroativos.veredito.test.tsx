import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DocumentosRetroativos } from "../components/DocumentosRetroativos";

const criarArquivo = (nome: string) =>
  new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], nome, { type: "application/pdf" });

describe("DocumentosRetroativos - comparativo retroativo", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra comparativo locador apurado x desconto aplicado com veredito SUGERIR_ENVIO", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url === "/api/ciclos/documentos") {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                arquivos: [
                  { arquivo: "Boleto_Ref_052026.pdf", tipo: "CONDO_BILL", arquivado: true },
                  { arquivo: "Ibagy_06.pdf", tipo: "RENTAL_BILL", arquivado: true },
                ],
                ciclos_afetados: [
                  {
                    id: "11111111-1111-1111-1111-111111111111",
                    competencia: "2026-05",
                    status_ciclo: "PRONTO_PARA_ENVIO",
                    veredito: "SUGERIR_ENVIO",
                    valor_ressarcimento: "264.50",
                    valor_desconto_aluguel: "100.00",
                    diferenca: "164.50",
                  },
                ],
                falhas: [],
              }),
          });
        }
        return Promise.reject(new Error("Unknown route"));
      })
    );

    render(<DocumentosRetroativos />);

    const input = screen.getByLabelText(/Arquivos/i) as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [criarArquivo("Boleto_Ref_052026.pdf"), criarArquivo("Ibagy_06.pdf")] },
    });

    fireEvent.click(screen.getByRole("button", { name: /Enviar e Auditar/i }));

    await waitFor(() => {
      expect(screen.getByText(/Sugestao: enviar pedido a Ibagy/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Locador apurado/i)).toBeInTheDocument();
    expect(screen.getByText(/Desconto ja aplicado/i)).toBeInTheDocument();
    expect(screen.getByText(/Diferenca:/i)).toBeInTheDocument();
    expect(screen.queryByText(/Ciclos atualizados/i)).not.toBeInTheDocument();
  });

  it("mostra TUDO_OK quando o desconto da fatura seguinte cobre o valor apurado", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url === "/api/ciclos/documentos") {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                arquivos: [
                  { arquivo: "Boleto_Ref_052026.pdf", tipo: "CONDO_BILL", arquivado: true },
                  { arquivo: "Ibagy_06.pdf", tipo: "RENTAL_BILL", arquivado: true },
                ],
                ciclos_afetados: [
                  {
                    id: "22222222-2222-2222-2222-222222222222",
                    competencia: "2026-05",
                    status_ciclo: "CONCILIADO_SEM_PENDENCIA",
                    veredito: "TUDO_OK",
                    valor_ressarcimento: "264.50",
                    valor_desconto_aluguel: "264.50",
                    diferenca: "0.00",
                  },
                ],
                falhas: [],
              }),
          });
        }
        return Promise.reject(new Error("Unknown route"));
      })
    );

    render(<DocumentosRetroativos />);

    const input = screen.getByLabelText(/Arquivos/i) as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [criarArquivo("Boleto_Ref_052026.pdf"), criarArquivo("Ibagy_06.pdf")] },
    });

    fireEvent.click(screen.getByRole("button", { name: /Enviar e Auditar/i }));

    await waitFor(() => {
      expect(screen.getByText(/Tudo ok - nenhuma acao necessaria/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Sugestao: enviar pedido/i)).not.toBeInTheDocument();
  });
});
