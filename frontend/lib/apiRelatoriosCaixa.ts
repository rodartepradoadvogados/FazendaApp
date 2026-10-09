// Leituras dos Relatórios › Caixa (Fase C1). Arquivo próprio para não mexer em
// lib/api.ts (compartilhado): usa o mesmo authFetch/API de lá. O Caixa real
// continua lendo GET /financeiro/caixa-real e o fundo de reserva sugerido
// (fetchCaixaReal/fetchFundoReservaSugerido, em lib/api.ts).
import { API, authFetch, mensagemErroApi } from "@/lib/api";
import type { RespostaFluxo } from "@/lib/relatorioFluxo";
import type { RespostaLivro } from "@/lib/relatorioLivro";

async function ler<T>(caminho: string, q: URLSearchParams, nome: string): Promise<T> {
  const res = await authFetch(`${API}${caminho}?${q}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `${nome}: ${res.status}`); }
  return res.json();
}

export type Folego = {
  saldo_hoje: number; saidas_janela: number; dias_janela: number; saida_media_diaria: number | null; folego_dias: number | null;
  hoje: string; inicio_janela: string; regras_v2: boolean;
};

/** Fôlego do Caixa real: saldo de hoje ÷ saída média diária dos últimos 90 dias. */
export function fetchFolegoCaixa(hoje: string): Promise<Folego> {
  return ler<Folego>("/financeiro/caixa-real/folego", new URLSearchParams({ hoje }), "Fôlego do caixa");
}

/** Fluxo de caixa mês a mês (e dia a dia com `por_dia`), realizado × previsto. */
export function fetchFluxoCaixaMensal(p: { data_inicio: string; data_fim: string; centro_custo?: string | null; hoje: string; por_dia?: boolean }): Promise<RespostaFluxo> {
  const q = new URLSearchParams({ data_inicio: p.data_inicio, data_fim: p.data_fim, hoje: p.hoje });
  if (p.centro_custo) q.set("centro_custo", p.centro_custo);
  if (p.por_dia) q.set("por_dia", "true");
  return ler<RespostaFluxo>("/financeiro/fluxo-caixa-mensal", q, "Fluxo de caixa");
}

/** Livro caixa da atividade rural (formato do contador). */
export function fetchLivroCaixaRural(p: { data_inicio: string; data_fim: string }): Promise<RespostaLivro> {
  return ler<RespostaLivro>("/financeiro/livro-caixa-rural", new URLSearchParams({ data_inicio: p.data_inicio, data_fim: p.data_fim }), "Livro caixa");
}
