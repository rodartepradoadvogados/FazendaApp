// Regras de tela do lançamento de INDUÇÃO DE CIO (PGF2α/Cloprostenol aplicado nos últimos dias do PEV para a vaca entrar em
// cio em 2 a 5 dias). Funções puras; quem grava é POST /reproducao/inducao-cio e a Agenda "Observar cio" nasce no servidor.
import { somaDias } from "./iatfCronograma.ts";

export const PRODUTO_PADRAO_INDUCAO = "Cloprostenol";
/** O cio esperado: de 2 a 5 dias depois da aplicação (a Agenda lembra de observar nesta janela). */
export const CIO_DIAS_MIN = 2;
export const CIO_DIAS_MAX = 5;

export type InducaoHistorico = { id: number; numero_matriz: string; data_aplicacao: string | null };

export function janelaCio(dataAplicacao: string): { de: string; ate: string } | null {
  if (!dataAplicacao) return null;
  return { de: somaDias(dataAplicacao, CIO_DIAS_MIN), ate: somaDias(dataAplicacao, CIO_DIAS_MAX) };
}

/** número da matriz -> data (AAAA-MM-DD) da indução mais recente. */
export function ultimaInducaoPorMatriz(historico: readonly InducaoHistorico[]): Map<string, string> {
  const m = new Map<string, string>();
  for (const h of historico) {
    if (!h.data_aplicacao) continue;
    const d = h.data_aplicacao.slice(0, 10);
    const atual = m.get(h.numero_matriz);
    if (!atual || d > atual) m.set(h.numero_matriz, d);
  }
  return m;
}

/** Quantas matrizes ainda estão na janela de observar o cio (induzidas há até 5 dias) e quantas foram induzidas em 30 dias. */
export function estatisticasInducao(historico: readonly InducaoHistorico[], hoje: string): { observando: number; ultimos30: number } {
  const corteObservar = somaDias(hoje, -CIO_DIAS_MAX);
  const corte30 = somaDias(hoje, -30);
  const observando = new Set<string>();
  const ultimos30 = new Set<string>();
  for (const h of historico) {
    const d = h.data_aplicacao?.slice(0, 10);
    if (!d) continue;
    if (d >= corteObservar && d <= hoje) observando.add(h.numero_matriz);
    if (d >= corte30 && d <= hoje) ultimos30.add(h.numero_matriz);
  }
  return { observando: observando.size, ultimos30: ultimos30.size };
}

export type CamposInducao = {
  numeros: readonly string[]; dataAplicacao: string; produto: string; dose: string; unidade: string; via: string;
  responsavel: string; observacao: string;
};
/** Valida e monta o corpo de registrarInducaoCio. Devolve a mensagem de erro (como a tela sempre disse) ou o payload. */
export function montarInducao(c: CamposInducao):
  | { erro: string }
  | { payload: { numeros_matriz: string[]; data_aplicacao: string; produto: string; dose?: number; unidade?: string; via?: string; responsavel?: string; observacao?: string } } {
  if (!c.numeros.length) return { erro: "Selecione ao menos uma matriz." };
  if (!c.dataAplicacao) return { erro: "Informe a data da aplicação." };
  if (!c.produto.trim()) return { erro: "Informe o produto (ex.: Cloprostenol / PGF2α)." };
  const dose = c.dose ? Number(c.dose) : undefined;
  if (dose !== undefined && !Number.isFinite(dose)) return { erro: "A dose precisa ser um número." };
  return {
    payload: {
      numeros_matriz: [...c.numeros], data_aplicacao: c.dataAplicacao, produto: c.produto,
      dose, unidade: dose !== undefined ? c.unidade : undefined,
      via: c.via || undefined, responsavel: c.responsavel || undefined, observacao: c.observacao || undefined,
    },
  };
}

/** Estoque do produto depois da baixa (dose × nº de matrizes); null se o item não está no estoque ou não há dose. */
export function estoqueDepois(
  estoque: readonly { nome: string; quantidade?: number | null; unidade?: string | null }[], produto: string, dose: string, n: number,
): { atual: number; depois: number; unidade: string; total: number } | null {
  const item = estoque.find((e) => e.nome === produto);
  const d = Number(dose);
  if (!item || !dose || !Number.isFinite(d) || d <= 0 || n <= 0) return null;
  const atual = item.quantidade ?? 0;
  const total = d * n;
  return { atual, depois: atual - total, unidade: item.unidade || "", total };
}
