// Chamadas do grupo Plano dos Relatórios (Fase C): orçado × realizado por linha
// da DRE e a planilha do orçamento. Arquivo próprio (não em api.ts) para não
// disputar o arquivo compartilhado com as outras telas da Fase C.
import { API, authFetch, mensagemErroApi } from "@/lib/api";
import type { CelulaGrade, ItemOrcamento, RespostaOrcamento } from "@/lib/relatorioOrcamento";

/** GET /planejamento/orcamento/relatorio — período de meses inteiros, competência. */
export async function fetchOrcamentoRelatorio(params: { data_inicio: string; data_fim: string; centro_custo?: string | null }): Promise<RespostaOrcamento> {
  const q = new URLSearchParams({ data_inicio: params.data_inicio, data_fim: params.data_fim });
  if (params.centro_custo) q.set("centro_custo", params.centro_custo);
  const res = await authFetch(`${API}/planejamento/orcamento/relatorio?${q}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Orçamento: ${res.status}`); }
  return res.json();
}

export async function fetchItensOrcamento(ano: number): Promise<ItemOrcamento[]> {
  const res = await authFetch(`${API}/planejamento/orcamento?ano=${ano}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Orçamento de ${ano}: ${res.status}`);
  return res.json();
}

/** PUT /planejamento/orcamento-grade — a planilha salva de uma vez (só as células que mudaram). */
export async function salvarGradeOrcamento(ano: number, celulas: CelulaGrade[]): Promise<{ criadas: number; atualizadas: number; excluidas: number; ignoradas: { codigo_conta_gerencial: string; centro_custo: string | null; mes: number; motivo: string }[] }> {
  const res = await authFetch(`${API}/planejamento/orcamento-grade`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ano, celulas }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Não foi possível salvar o orçamento (${res.status})`); }
  return res.json();
}
