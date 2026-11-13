import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { App } from "../App";

const REAL_API_CICLO = {
  id: "9f1d2c3a-1111-4111-8111-000000000001",
  competencia: "2026-09",
  condominio_nome: "CONDOMINIO EDIFICIO VILLA SALOMY",
  data_vencimento: "2026-10-10",
  valor_total: 1154.31,
  valor_ordinarias: 596.27,
  valor_extraordinarias: 294.87,
  valor_fundos: 59.63,
  valor_leituras: 203.54,
  valor_ressarcimento: 354.5,
  valor_desconto_aluguel: 264.5,
  valor_saldo_residual: 90.0,
  boleto_pdf_path: "/data/storage/villa_salomy_2026_09.pdf",
  boleto_aluguel_path: "/data/boletos/aluguel_ibagy_2026_09.pdf",
  comprovante_pix_path: "/data/storage/comprovante_pix_2026_09.pdf",
  itens_abatidos_aluguel: [],
  status_ciclo: "PRONTO_PARA_ENVIO",
  detalhes_verificacao: "Documentos localizados.",
  criado_em: "2026-10-16T18:00:00Z",
  itens: [
    {
      id: "item-1",
      categoria: "ORDINARIA",
      descricao: "Despesas Ordinarias de Condominio",
      valor_unidade: 596.27,
      responsabilidade: "LOCATARIO",
      justificativa_legal: "Art. 23 da Lei 8.245/91",
    },
    {
      id: "item-2",
      categoria: "EXTRAORDINARIA",
      descricao: "Fundo de Reserva",
      valor_unidade: 354.5,
      responsabilidade: "LOCADOR",
      justificativa_legal: "Art. 22, X, g da Lei 8.245/91",
    },
  ],
  submissoes: [],
};

describe("App Dashboard Integration", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders header and reference reimbursement from API data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url === "/api/ciclos") {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve([REAL_API_CICLO]),
          });
        }
        return Promise.reject(new Error("Unknown route"));
      })
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: /Luas Condo/i })).toBeInTheDocument();
    expect(screen.getAllByText(/354,50/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/VILLA SALOMY/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows an explicit empty state with demo seed action when database has no cycles", async () => {
    let ciclosCallCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, options: any) => {
        if (url === "/api/ciclos" && (!options?.method || options.method === "GET")) {
          ciclosCallCount += 1;
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(ciclosCallCount > 1 ? [REAL_API_CICLO] : []),
          });
        }
        if (url === "/api/ciclos/seed-demo" && options?.method === "POST") {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(REAL_API_CICLO),
          });
        }
        return Promise.reject(new Error("Unknown route"));
      })
    );

    render(<App />);

    expect(await screen.findByText(/Nenhum ciclo no banco de dados/i)).toBeInTheDocument();
    // The trap that motivated this regression: sample data must never appear
    // as if it were real database content (the full condo name only renders
    // inside cycle cards; the header subtitle also mentions "Villa Salomy").
    expect(screen.queryByText(/354,50/)).toBeNull();

    const seedBtn = screen.getByRole("button", { name: /Carregar Ciclo de Demonstracao/i });
    fireEvent.click(seedBtn);

    await waitFor(() => {
      expect(
        screen.getAllByText(/CONDOMINIO EDIFICIO VILLA SALOMY/i).length
      ).toBeGreaterThanOrEqual(1);
    });
  });

  it("handles submission trigger successfully from API data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, options: any) => {
        if (url === "/api/ciclos") {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve([REAL_API_CICLO]),
          });
        }
        if (url.includes("/submeter") && options?.method === "POST") {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                status: "SUCESSO",
                protocolo: "IBAGY-2026-TEST999",
                mensagem: "Submissao realizada com sucesso",
                trace_id: "trace-test-123",
              }),
          });
        }
        return Promise.reject(new Error("Unknown route"));
      })
    );

    render(<App />);

    const submitBtn = await screen.findByRole("button", {
      name: /Aprovar e Enviar para Ibagy/i,
    });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Submissao Protocolada com Sucesso/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/IBAGY-2026-TEST999/i)).toBeInTheDocument();
    });
  });

  it("switches to the Documentos tab and back to the Dashboard", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url === "/api/ciclos") {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve([REAL_API_CICLO]),
          });
        }
        return Promise.reject(new Error("Unknown route"));
      })
    );

    render(<App />);

    await screen.findByRole("heading", { name: /Luas Condo/i });

    fireEvent.click(screen.getByRole("button", { name: /^Documentos$/i }));
    expect(await screen.findByText(/Documentos retroativos/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Aprovar e Enviar para Ibagy/i })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /^Dashboard$/i }));
    expect(
      await screen.findByRole("button", { name: /Aprovar e Enviar para Ibagy/i })
    ).toBeInTheDocument();
  });

  it("disables submission and flags sample data when API is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.reject(new Error("network down")))
    );

    render(<App />);

    // Offline fallback keeps the reference cycle visible for demo purposes,
    // but submission must be clearly disabled.
    await waitFor(() => {
      expect(
        screen.getAllByText(/CONDOMINIO EDIFICIO VILLA SALOMY/i).length
      ).toBeGreaterThanOrEqual(1);
    });
    expect(await screen.findByText(/Dados de amostra/i)).toBeInTheDocument();

    const submitBtn = await screen.findByRole("button", {
      name: /Aprovar e Enviar para Ibagy/i,
    });
    expect(submitBtn).toBeDisabled();
  });
});

describe("Access key and cycle deletion", () => {
  const PENDING = { ...REAL_API_CICLO, id: "9f1d2c3a-2222-4222-8222-000000000002", status_ciclo: "PENDENTE_COMPROVANTE", comprovante_pix_path: null };
  const SENT = { ...REAL_API_CICLO, id: "9f1d2c3a-3333-4333-8333-000000000003", status_ciclo: "ENVIADO" };

  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("sends the saved access key as bearer token on write calls", async () => {
    const calls: Array<{ url: string; options: any }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, options: any) => {
        calls.push({ url, options });
        if (url === "/api/ciclos" && (!options?.method || options.method === "GET")) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([REAL_API_CICLO]) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ detail: "ok" }) });
      })
    );

    render(<App />);
    await screen.findByRole("heading", { name: /Luas Condo/i });

    fireEvent.click(screen.getByRole("button", { name: /Chave de acesso/i }));
    fireEvent.change(screen.getByLabelText(/Chave de acesso/i), { target: { value: "minha-chave" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar chave/i }));

    fireEvent.click(screen.getByRole("button", { name: /Sincronizar E-mail/i }));
    await waitFor(() => {
      const sync = calls.find((c) => c.url === "/api/ciclos/sync-email");
      expect(sync?.options.headers.Authorization).toBe("Bearer minha-chave");
    });
  });

  it("explains a missing or wrong access key when the API answers 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, options: any) => {
        if (url === "/api/ciclos" && (!options?.method || options.method === "GET")) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([REAL_API_CICLO]) });
        }
        return Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({ detail: "Token invalido" }) });
      })
    );

    render(<App />);
    await screen.findByRole("heading", { name: /Luas Condo/i });
    fireEvent.click(screen.getByRole("button", { name: /Sincronizar E-mail/i }));

    expect(await screen.findByText(/chave de acesso/i, { selector: "span" })).toBeInTheDocument();
  });

  it("offers deletion only for cycles that were not sent and calls DELETE after confirmation", async () => {
    window.localStorage.setItem("luas_condo_access_key", "minha-chave");
    const calls: Array<{ url: string; options: any }> = [];
    let ciclos = [PENDING];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, options: any) => {
        calls.push({ url, options });
        if (options?.method === "DELETE") {
          ciclos = [];
          return Promise.resolve({ ok: true, status: 204, json: () => Promise.reject(new Error("no body")) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve(ciclos) });
      })
    );
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));

    render(<App />);
    const btn = await screen.findByRole("button", { name: /Excluir ciclo/i });
    fireEvent.click(btn);

    await waitFor(() => {
      const del = calls.find((c) => c.options?.method === "DELETE");
      expect(del?.url).toBe(`/api/ciclos/${PENDING.id}`);
      expect(del?.options.headers.Authorization).toBe("Bearer minha-chave");
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: /Excluir ciclo/i })).toBeNull());
  });

  it("does not call DELETE when the user declines the confirmation", async () => {
    window.localStorage.setItem("luas_condo_access_key", "minha-chave");
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([PENDING]) })
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Excluir ciclo/i }));

    expect(fetchMock.mock.calls.some((c) => c[1]?.method === "DELETE")).toBe(false);
  });

  it("hides the delete button for cycles already sent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.resolve({ ok: true, json: () => Promise.resolve([SENT]) }))
    );
    render(<App />);
    await screen.findByRole("heading", { name: /Luas Condo/i });
    await screen.findAllByText(/VILLA SALOMY/i);
    expect(screen.queryByRole("button", { name: /Excluir ciclo/i })).toBeNull();
  });
});
