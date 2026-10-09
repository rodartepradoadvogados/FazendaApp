// "DRE da fazenda" (Relatórios › Resultado, Fase B): o modelo de tela tirado da
// resposta de GET /financeiro/dre — a cascata do SERVIDOR é a única fonte do
// número (o mesmo resultado da Capa, do e-mail do Portal e da aba antiga).
// Aqui só se reorganiza: sinal de cada linha, comparação, KPIs, frase-resumo,
// degraus da cascata, detalhe por conta (que sempre fecha com o total) e as
// linhas para exportar. PURO (só import de tipo) — testes em relatorioDre.test.ts.
import type { DreResposta } from "@/lib/api";
import type { Delta, Periodo, Regime } from "@/lib/relatorioContexto";

export type ContaVis = { chave: string; codigo: string | null; nome: string; a: number; b: number | null };
export type LinhaVis = {
  chave: string;
  nome: string;
  /** Rótulo técnico do servidor, quando o nome é a versão em português simples. */
  tecnico: string | null;
  operador: string;
  subtotal: boolean;
  /** Valor COM sinal na cascata (custo negativo). */
  a: number;
  b: number | null;
  contas: ContaVis[];
  /** Fração da receita líquida (null sem receita). */
  pctReceita: number | null;
};

// Nome em português de dono de fazenda + o rótulo técnico ao lado (o contador acha o dele).
const NOMES: Record<string, [string, string | null]> = {
  RECEITA_VENDAS: ["Receita de vendas", null],
  DEDUCAO_IMPOSTOS: ["Funrural, Senar e descontos", "deduções da receita"],
  RECEITA_LIQUIDA: ["Receita líquida", null],
  CUSTO_VARIAVEL: ["Custo variável", "alimentação e insumos (CPV/CMV)"],
  MARGEM_BRUTA: ["Margem bruta", null],
  DESPESA_VARIAVEL: ["Despesas variáveis", null],
  MARGEM_CONTRIBUICAO: ["Margem de contribuição", null],
  GASTOS_PESSOAL: ["Pessoal", "folha e encargos"],
  DESPESAS_OPERACIONAIS: ["Despesas operacionais", null],
  EBITDA: ["Geração de caixa da atividade", "EBITDA"],
  DEPRECIACAO_AMORT_EXAUSTAO: ["Desgaste e reserva para repor", "depreciação, amortização e exaustão"],
  OUTRAS_REC_DESP: ["Resultado financeiro e outras", "juros, descontos e outras receitas e despesas"],
  RESULTADO_OPERACIONAL: ["Resultado operacional", "EBIT"],
  TRIBUTOS_IR_CSLL: ["Tributos sobre o lucro", "IRPJ e CSLL"],
  RESULTADO_LIQUIDO: ["Resultado", "resultado líquido"],
};

/** Valor com sinal: o servidor guarda custo em magnitude positiva e o operador diz que subtrai. */
export function valorComSinal(operador: string, valor: number): number {
  return (operador === "-" ? -valor : valor) + 0; // + 0: nunca "−0"
}

const chaveConta = (c: { codigo: string | null; nome: string | null }) => c.codigo || c.nome || "(sem conta)";
const r2 = (v: number) => Math.round(v * 100) / 100;

/** As linhas da tela, com a comparação casada por chave de linha e por conta. */
export function linhasDre(atual: DreResposta | null, cmp: DreResposta | null): LinhaVis[] {
  const cascata = atual?.cascata ?? [];
  if (!cascata.length) return [];
  const doCmp = new Map((cmp?.cascata ?? []).map((l) => [l.chave, l]));
  const receita = cascata.find((l) => l.chave === "RECEITA_LIQUIDA")?.valor ?? 0;
  return cascata.map((l) => {
    const lb = doCmp.get(l.chave);
    const contasB = new Map((lb?.contas ?? []).map((c) => [chaveConta(c), c.valor]));
    const contasA = new Map((l.contas ?? []).map((c) => [chaveConta(c), c]));
    const contas: ContaVis[] = (l.contas ?? []).map((c) => ({
      chave: chaveConta(c), codigo: c.codigo, nome: c.nome || c.codigo || "(sem conta)",
      a: valorComSinal(l.operador, c.valor),
      b: cmp ? valorComSinal(l.operador, contasB.get(chaveConta(c)) ?? 0) : null,
    }));
    // Conta que só existe na comparação (ex.: teve gasto no ano passado e não neste): aparece com zero.
    for (const c of lb?.contas ?? []) {
      if (!contasA.has(chaveConta(c))) contas.push({ chave: chaveConta(c), codigo: c.codigo, nome: c.nome || c.codigo || "(sem conta)", a: 0, b: valorComSinal(l.operador, c.valor) });
    }
    contas.sort((x, y) => Math.abs(y.a) - Math.abs(x.a) || x.nome.localeCompare(y.nome, "pt-BR"));
    const [nome, tecnico] = NOMES[l.chave] ?? [l.rotulo, null];
    const a = valorComSinal(l.operador, l.valor);
    return {
      chave: l.chave, nome, tecnico, operador: l.operador, subtotal: l.eh_subtotal, a,
      b: lb ? valorComSinal(lb.operador, lb.valor) : cmp ? 0 : null,
      contas, pctReceita: receita > 0 ? Math.abs(a) / receita : null,
    };
  });
}

export const valorLinha = (linhas: LinhaVis[], chave: string) => linhas.find((l) => l.chave === chave) ?? null;

/** Degraus da cascata: linhas com valor (ou subtotal) — a de valor zero sai do gráfico, não da tabela. */
export type Degrau = { chave: string; nome: string; v: number; subtotal: boolean; resultado: boolean; ini: number; fim: number };
export function degrausCascata(linhas: LinhaVis[]): Degrau[] {
  let corrente = 0;
  const out: Degrau[] = [];
  for (const l of linhas) {
    if (l.subtotal) {
      out.push({ chave: l.chave, nome: l.nome, v: l.a, subtotal: true, resultado: l.chave === "RESULTADO_LIQUIDO", ini: 0, fim: l.a });
      corrente = l.a;
      continue;
    }
    if (Math.abs(l.a) < 0.005) continue;
    out.push({ chave: l.chave, nome: l.nome, v: l.a, subtotal: false, resultado: false, ini: corrente, fim: corrente + l.a });
    corrente += l.a;
  }
  return out;
}

/** Conferência: cada subtotal é a soma das linhas acima dele (o servidor monta; a tela confere). */
export function conferirCascata(linhas: LinhaVis[]): { fecha: boolean; diferenca: number } {
  let corrente = 0, pior = 0;
  for (const l of linhas) {
    if (l.subtotal) { pior = Math.max(pior, Math.abs(r2(corrente - l.a))); corrente = l.a; }
    else corrente += l.a;
  }
  return { fecha: pior < 0.02, diferenca: r2(pior) };
}

/** O que forma um subtotal: as linhas entre o subtotal anterior (incluso, como ponto de partida) e ele. */
export function composicaoSubtotal(linhas: LinhaVis[], chave: string): LinhaVis[] {
  const i = linhas.findIndex((l) => l.chave === chave);
  if (i < 0) return [];
  let j = i - 1;
  while (j >= 0 && !linhas[j].subtotal) j--;
  return linhas.slice(Math.max(0, j), i).filter((l) => l.subtotal || Math.abs(l.a) >= 0.005 || (l.b != null && Math.abs(l.b) >= 0.005));
}

// ── Frase-resumo ──────────────────────────────────────────────────────────

/** Pedaços de texto; `b` = negrito. A tela junta e põe <strong> onde for o caso. */
export type Trecho = { t: string; b?: boolean };

export function fraseDre(o: {
  periodo: Periodo; regime: Regime; linhas: LinhaVis[]; rotuloCmp: string | null; brl: (v: number) => string;
  naoClassificadoContas: number; delta: (a: number, b: number) => Delta | null;
}): Trecho[] {
  const res = valorLinha(o.linhas, "RESULTADO_LIQUIDO"), ebitda = valorLinha(o.linhas, "EBITDA");
  if (!res) return [];
  const quando = `Em ${o.periodo.label}, ${o.regime === "caixa" ? "pelo dia do pagamento" : "pelo mês do gasto"}`;
  const ganhou = res.a >= 0;
  const out: Trecho[] = [{ t: `${quando}, a fazenda ${ganhou ? "ganhou" : "perdeu"} ` }, { t: o.brl(Math.abs(res.a)), b: true }];
  if (o.rotuloCmp && res.b != null) {
    const d = o.delta(res.a, res.b);
    if (d && d.igual) out.push({ t: ` (igual a ${o.rotuloCmp})` });
    else if (d) out.push({ t: ` (${d.melhor ? "melhor" : "pior"} que ${o.rotuloCmp}, quando ${res.b >= 0 ? "ganhou" : "perdeu"} ${o.brl(Math.abs(res.b))})` });
  }
  out.push({ t: "." });
  if (ebitda) {
    out.push({ t: ` A atividade ${ebitda.a >= 0 ? "gerou" : "consumiu"} ` }, { t: o.brl(Math.abs(ebitda.a)), b: true }, { t: " de caixa antes do desgaste dos bens e dos juros." });
  }
  if (o.naoClassificadoContas > 0) {
    out.push({ t: " " }, { t: `${o.naoClassificadoContas} ${o.naoClassificadoContas === 1 ? "conta sem classificação ficou" : "contas sem classificação ficaram"}`, b: true }, { t: " fora até serem classificadas." });
  }
  return out;
}

// ── Drill para Consultas ──────────────────────────────────────────────────

export type FiltroConsultasDrill = {
  de: string; ate: string; periodoPor: "competencia" | "pagamento"; conta?: string; contaNome?: string; centro?: string; origem: string;
  /** Um lançamento só (nº do documento ou do lançamento): Consultas abre o período inteiro para achá-lo. */
  documento?: string;
};

/** Consultas já filtrada no mesmo período, regime, centro e conta da linha clicada. */
export function filtroConsultasDe(o: { periodo: Periodo; regime: Regime; cc: string; conta?: { codigo: string | null; nome: string } | null; origem: string }): FiltroConsultasDrill {
  const f: FiltroConsultasDrill = {
    de: o.periodo.ini, ate: o.periodo.fim, periodoPor: o.regime === "caixa" ? "pagamento" : "competencia", origem: o.origem,
  };
  if (o.cc && o.cc !== "todos") f.centro = o.cc;
  if (o.conta?.codigo && !o.conta.codigo.startsWith("(")) { f.conta = o.conta.codigo; f.contaNome = o.conta.nome; }
  return f;
}
