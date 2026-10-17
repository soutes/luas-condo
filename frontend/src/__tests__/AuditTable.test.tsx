import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AuditTable } from "../components/AuditTable";
import type { RateioItem } from "../types";

describe("AuditTable Component", () => {
  const sampleItems: RateioItem[] = [
    {
      id: "item-1",
      descricao: "Despesas Ordinarias de Condominio",
      categoria: "ORDINARIA",
      valor_unidade: 800.0,
      responsabilidade: "LOCATARIO",
      justificativa_legal: "Art. 23 da Lei 8.245/91",
    },
    {
      id: "item-2",
      descricao: "Fundo de Reserva / Reforma Fachada",
      categoria: "EXTRAORDINARIA",
      valor_unidade: 354.5,
      responsabilidade: "LOCADOR",
      justificativa_legal: "Art. 22, X, g da Lei 8.245/91",
    },
  ];

  it("renders table with all rateio items and amounts", () => {
    render(<AuditTable items={sampleItems} />);

    expect(screen.getByText("Despesas Ordinarias de Condominio")).toBeInTheDocument();
    expect(screen.getByText("Fundo de Reserva / Reforma Fachada")).toBeInTheDocument();
    expect(screen.getAllByText(/800,00/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/354,50/).length).toBeGreaterThanOrEqual(1);
  });

  it("prominently displays reference reimbursement R$ 354,50 for locador", () => {
    render(<AuditTable items={sampleItems} />);

    const locadorBadges = screen.getAllByText("LOCADOR");
    expect(locadorBadges.length).toBeGreaterThanOrEqual(1);

    const locatarioBadges = screen.getAllByText("LOCATARIO");
    expect(locatarioBadges.length).toBeGreaterThanOrEqual(1);

    expect(screen.getByText("Art. 22, X, g da Lei 8.245/91")).toBeInTheDocument();
  });

  it("filters items when clicking filter tabs", () => {
    render(<AuditTable items={sampleItems} />);

    // Click Locador filter button
    const locadorFilterBtn = screen.getByRole("button", { name: /Somente Locador/i });
    fireEvent.click(locadorFilterBtn);

    // Locatario item should not be in document
    expect(screen.queryByText("Despesas Ordinarias de Condominio")).not.toBeInTheDocument();
    expect(screen.getByText("Fundo de Reserva / Reforma Fachada")).toBeInTheDocument();

    // Click Todos filter button
    const todosBtn = screen.getByRole("button", { name: /Todos/i });
    fireEvent.click(todosBtn);

    expect(screen.getByText("Despesas Ordinarias de Condominio")).toBeInTheDocument();
    expect(screen.getByText("Fundo de Reserva / Reforma Fachada")).toBeInTheDocument();
  });

  it("displays empty state when no items provided", () => {
    render(<AuditTable items={[]} />);
    expect(screen.getByText(/Nenhum item de rateio encontrado/i)).toBeInTheDocument();
  });
});
