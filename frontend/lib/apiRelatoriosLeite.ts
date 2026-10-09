// Leituras dos Relatórios › Leite e Registros (Fase C2). Arquivo próprio para
// não mexer em lib/api.ts (outras telas da Fase C mexem lá em paralelo); usa o
// mesmo authFetch/API.
import { API, authFetch, mensagemErroApi } from "@/lib/api";
import type { RespostaCustosLeite, RespostaCustoHectare, RespostaCustoSafra, RespostaCustoVacaLote, RespostaRmcaVaca, SafraOpcao } from "@/lib/relatorioLeite";
import type { RespostaAnimais, RespostaSemen } from "@/lib/relatorioRegistros";

async function ler<T>(caminho: string, q: Record<string, string | number | null | undefined>, rotulo: string): Promise<T> {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v != null && v !== "") p.set(k, String(v));
  const res = await authFetch(`${API}${caminho}?${p.toString()}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `${rotulo}: ${res.status}`); }
  return res.json() as Promise<T>;
}

type Base = { data_inicio: string; data_fim: string; centro_custo?: string | null };

export const fetchCustosLeite = (q: Base & { regime: "competencia" | "caixa"; serie_meses?: number }) =>
  ler<RespostaCustosLeite>("/financeiro/custos-leite", q, "Custos do leite");
export const fetchCustoVacaLoteMolde = (q: Base) => ler<RespostaCustoVacaLote>("/financeiro/custo-vaca-lote", q, "Custo por vaca e lote");
export const fetchCustoHectareMolde = (q: Base) => ler<RespostaCustoHectare>("/financeiro/custo-hectare", q, "Custo por hectare");
export const fetchCustoSafraMolde = (safraId: number) => ler<RespostaCustoSafra>("/financeiro/custo-safra", { safra_id: safraId }, "Custo por safra");
export const fetchSafrasMolde = () => ler<SafraOpcao[]>("/safras/", {}, "Safras");
export const fetchRmcaVaca = (q: { data_inicio: string; data_fim: string; serie_meses?: number }) =>
  ler<RespostaRmcaVaca>("/financeiro/rmca-vaca", q, "Sobra da comida");

/** Réguas de referência (outro agente entrega o endpoint): falha ou ausência vira `null` — a tela segue sem régua. */
export async function fetchReguasReferenciaOpcional(): Promise<unknown> {
  try {
    const res = await authFetch(`${API}/financeiro/reguas-referencia`, { cache: "no-store" });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

export const fetchResumoAnimais = (q: { data_de?: string; data_ate?: string; centro_custo?: string | null; numero?: string; numero_documento?: string; gta?: string }) =>
  ler<RespostaAnimais>("/relatorio-compra-venda-animais/resumo", q, "Compra e venda de animais");
export const fetchResumoSemen = (q: { data_de: string; data_ate: string; centro_custo?: string | null; touro?: string; vendedor?: string; numero_documento?: string; serie_meses?: number }) =>
  ler<RespostaSemen>("/relatorio-compra-semen/resumo", q, "Compra de sêmen");
