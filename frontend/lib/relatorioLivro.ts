// "Livro caixa da atividade rural" (Relatórios › Caixa, Fase C1): modelo de tela
// da resposta de GET /financeiro/livro-caixa-rural — o livro no formato do
// contador (data, histórico, documento, receita, despesa, saldo). O servidor
// decide cada valor (com as regras v2, a separação fiscal); aqui só se agrupa
// por mês para a tabela e a exportação, e se monta a frase.
// PURO (só import de tipo) — testes em relatorioLivro.test.ts.
import type { Periodo } from "@/lib/relatorioContexto";

export type LinhaLivro = {
  data: string; id: number | null; numero_lancamento: string | null; documento: string | null;
  historico: string; fornecedor: string; conta: string | null;
  receita: number; despesa: number; custeio: number; investimento: number;
  categoria: "receita" | "custeio" | "investimento" | "misto" | null; saldo: number;
};
export type MesLivro = { competencia: string; receitas: number; custeio: number; investimentos: number; despesas: number; resultado: number; quantidade: number };
export type GrupoFora = { natureza: string; rotulo: string; entradas: number; saidas: number; quantidade: number };
export type RespostaLivro = {
  periodo: { inicio: string; fim: string }; regras_v2: boolean; separacao_fiscal: boolean;
  linhas: LinhaLivro[]; meses: MesLivro[];
  totais: { receitas: number; custeio: number; investimentos: number; despesas: number; resultado: number; quantidade: number };
  presumido_20: number | null;
  fora_do_livro: { entradas: number; saidas: number; grupos: GrupoFora[] } | null;
  ponte_dre: {
    resultado_dre: number; depreciacao: number; resultado_baixas: number; deducoes: number;
    investimentos_liquidos: number; venda_de_bens: number; resultado_livro: number; reconstruido: number; fecha: boolean;
  } | null;
  avisos: string[];
};

export const temLivro = (r: RespostaLivro | null) => !!r && r.linhas.length > 0;

/** Histórico no formato do contador: "Fornecedor — descrição" (sem repetir o que for igual). */
export function historicoDe(l: Pick<LinhaLivro, "historico" | "fornecedor">): string {
  const f = (l.fornecedor || "").trim(), h = (l.historico || "").trim();
  if (!f) return h || "—";
  if (!h || h.toLocaleLowerCase("pt-BR") === f.toLocaleLowerCase("pt-BR")) return f;
  return `${f} — ${h}`;
}
/** Documento: a nota; sem nota, o nº do lançamento. */
export const documentoDe = (l: Pick<LinhaLivro, "documento" | "numero_lancamento">) => l.documento || l.numero_lancamento || "—";

export type SecaoLivro = { mes: MesLivro; linhas: LinhaLivro[] };
/** As linhas agrupadas por mês (só os meses com lançamento), cada uma com o subtotal do mês. */
export function secoesLivro(r: RespostaLivro | null, soMes?: string): SecaoLivro[] {
  if (!r) return [];
  const porMes = new Map<string, LinhaLivro[]>();
  for (const l of r.linhas) {
    const ym = l.data.slice(0, 7);
    if (soMes && ym !== soMes) continue;
    porMes.set(ym, [...(porMes.get(ym) ?? []), l]);
  }
  return r.meses.filter((m) => porMes.has(m.competencia)).map((m) => ({ mes: m, linhas: porMes.get(m.competencia)! }));
}

export type Trecho = { t: string; b?: boolean };
export function fraseLivro(periodo: Periodo, r: RespostaLivro, brl: (v: number) => string): Trecho[] {
  const t = r.totais;
  if (!r.separacao_fiscal) {
    return [
      { t: `Em ${periodo.label} o livro caixa registra ` }, { t: brl(t.receitas), b: true }, { t: " recebidos e " },
      { t: brl(t.despesas), b: true }, { t: " pagos — " }, { t: t.resultado >= 0 ? "sobraram " : "faltaram " },
      { t: brl(Math.abs(t.resultado)), b: true }, { t: ". Todo pagamento entra: a separação fiscal chega com as regras novas." },
    ];
  }
  const out: Trecho[] = [
    { t: `Em ${periodo.label}, pela regra do livro caixa, a atividade rural teve ` }, { t: brl(t.receitas), b: true },
    { t: " de receitas recebidas e " }, { t: brl(t.despesas), b: true }, { t: " de despesas pagas — resultado de " },
    { t: brl(t.resultado), b: true }, { t: "." },
  ];
  if (r.presumido_20 != null) out.push({ t: " Pela opção de 20% da receita bruta, a base seria " }, { t: brl(r.presumido_20), b: true }, { t: "." });
  return out;
}
