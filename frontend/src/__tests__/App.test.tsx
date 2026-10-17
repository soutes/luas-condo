import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { App } from "../App";

describe("App Dashboard Integration", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders header and reference reimbursement R$ 354,50", async () => {
    // Mock fetch for /api/ciclos returning empty to test fallback reference cycle
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url === "/api/ciclos") {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve([]),
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

  it("handles submission trigger successfully", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, options: any) => {
        if (url === "/api/ciclos") {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve([]),
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
});
