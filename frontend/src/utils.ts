/**
 * Utility functions for currency and date formatting.
 * No emojis used.
 */

export function formatBRL(val: number | string): string {
  const num = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(num)) return "R$ 0,00";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(num);
}

export function formatDateBR(dateStr?: string): string {
  if (!dateStr) return "-";
  const [year, month, day] = dateStr.split("T")[0].split("-");
  if (!year || !month || !day) return dateStr;
  return `${day}/${month}/${year}`;
}
