// "Resultado por litro" (Relatórios › Resultado, Fase B): modelo de tela da
// resposta de GET /financeiro/resultado-por-litro (que reparte por litro a
// DRE do servidor). PURO (só import de tipo) — testes em relatorioLitro.test.ts.
import type { Delta, Periodo, Regime } from "@/lib/relatorioContexto";

/** De onde vieram os litros (T4): a NOTA do laticínio lançada em Financeiro, a Venda mensal do leite (reserva, ESTIMADO)
 * ou nenhuma; "mista" só num período com meses de fontes diferentes. Só vem com as regras novas ligadas. */
export type FonteLitros = "nota" | "venda_mensal" | "mista" | "sem_dado";
export type MesLitros = { competencia: string; fonte: FonteLitros; litros: number; nota_incompleta?: boolean };

export type IndicadoresLitro = {
  litros: number; litros_mes: number | null; meses: number;
  fonte_litros?: FonteLitros; litros_por_fonte?: { nota: number; venda_mensal: number };
  pct_litros_estimados?: number | null; meses_litros?: MesLitros[];
  receita_leite_bruta: number; deducoes_leite: number; receita_leite_liquida: number;
  comida: number; pessoal: number; outros_custeio: number; custo_variavel: number; custo_fixo: number;
  coe: number; depreciacao: number; cot: number;
  preco_bruto_l: number | null; preco_liquido_l: number | null;
  comida_l: number | null; pessoal_l: number | null; outros_l: number | null;
  coe_l: number | null; depreciacao_l: number | null; cot_l: number | null;
  margem_l: number | null; margem_cot_l: number | null; margem_pct: number | null;
  ponto_equilibrio: { litros_periodo: number; litros_mes: number | null; receita_periodo: number; folga_pct: number | null; contribuicao_por_litro: number } | null;
  receita_liquida_dre: number; resultado_liquido_dre: number; nao_classificado: number;
};
export type RespostaLitro = {
  periodo: { inicio: string; fim: string }; regime: string; centro_custo: string | null; regras_v2: boolean;
  configuracao: { contas_leite: string[]; contas_alimentacao: string[]; tem_entrega: boolean; tem_nota_leite?: boolean };
  atual: IndicadoresLitro; serie: (IndicadoresLitro & { competencia: string })[]; avisos: string[];
  /** Avisos de fonte dos litros (estimado pela Venda mensal, nota sem unidade/quantidade…); só com as regras novas. */
  avisos_fonte_litros?: string[];
};

/** O que falta configurar para o número existir (cada item com o caminho de 1 clique). */
export type Pendencia = { chave: string; texto: string; pronto: boolean; acao: string; href: string; hrefReserva?: string; acaoReserva?: string };
export function pendenciasLitro(r: RespostaLitro | null): Pendencia[] {
  if (!r) return [];
  return [
    { chave: "leite", texto: "Contas da venda do leite marcadas", pronto: r.configuracao.contas_leite.length > 0,
      acao: "Marcar em Parâmetros financeiros › Conta gerencial", href: "/parametros?sub=financeiro&pf=gerenciais" },
    { chave: "comida", texto: "Contas de alimentação marcadas", pronto: r.configuracao.contas_alimentacao.length > 0,
      acao: "Marcar em Parâmetros financeiros › Conta gerencial", href: "/parametros?sub=financeiro&pf=gerenciais" },
    { chave: "litros", texto: "Litros do leite no período", pronto: r.atual.litros > 0,
      acao: "Lançar a nota do laticínio (item de leite) — ou a Venda mensal como reserva", href: "/financeiro?sub=a_receber",
      acaoReserva: "Venda mensal do leite (reserva)", hrefReserva: "/lancamentos?sub=entrega_leite" },
  ];
}

const pctPt = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 1 });

/** Parcela dos litros que veio da Venda mensal (reserva) em vez de uma nota do laticínio, e os meses estimados.
 * null quando nenhum mês do indicador é estimado (ou a resposta é das regras antigas, sem `meses_litros`). */
export function litrosEstimados(i: IndicadoresLitro | null | undefined): { pct: number; meses: string[] } | null {
  const meses = (i?.meses_litros ?? []).filter((m) => m.fonte === "venda_mensal").map((m) => m.competencia);
  if (!i || !meses.length) return null;
  const nota = i.litros_por_fonte?.nota ?? 0, reserva = i.litros_por_fonte?.venda_mensal ?? 0;
  const pct = i.pct_litros_estimados ?? (nota + reserva > 0 ? Math.round((1000 * reserva) / (nota + reserva)) / 10 : 100);
  return { pct, meses };
}

/** "55,6% estimados pela Venda mensal (sem nota)" — o aviso curto que acompanha o número de litros; "" sem mês estimado. */
export function avisoLitrosEstimados(i: IndicadoresLitro | null | undefined): string {
  const e = litrosEstimados(i);
  if (!e) return "";
  return e.pct >= 100 ? "litros estimados pela Venda mensal (sem nota do laticínio)" : `${pctPt(e.pct)}% dos litros estimados pela Venda mensal (sem nota do laticínio)`;
}

/** De onde saem os litros, em palavras, para as notas do relatório exportado. */
export function descricaoFonteLitros(i: IndicadoresLitro | null | undefined, regrasV2: boolean): string {
  if (!regrasV2 || !i?.fonte_litros) return "Venda mensal do leite";
  const est = avisoLitrosEstimados(i);
  if (i.fonte_litros === "nota") return "nota do laticínio lançada em Financeiro";
  if (i.fonte_litros === "venda_mensal") return `Venda mensal do leite — ${est}`;
  if (i.fonte_litros === "mista") return `nota do laticínio e, nos meses sem nota, a Venda mensal do leite — ${est}`;
  return "sem nota do laticínio nem Venda mensal";
}

/** Sem litros ou sem receita do leite no período, não há resultado por litro: a tela ensina em vez de mostrar zero. */
export const temResultadoPorLitro = (i: IndicadoresLitro | null | undefined) =>
  !!i && i.litros > 0 && i.preco_liquido_l != null && i.receita_leite_liquida > 0;

export type LinhaLitro = {
  chave: string; nome: string; sub?: string; a: number | null; b: number | null;
  /** Sentido do "melhor" para a variação. */
  bom: "sobe" | "desce"; tot?: boolean; ind?: boolean;
  /** Linha da DRE que explica este número (drill). */
  dre?: string;
};

/** "Resultado por litro, linha a linha" — do preço bruto à sobra depois de repor os bens. */
export function linhasLitro(a: IndicadoresLitro | null, b: IndicadoresLitro | null): LinhaLitro[] {
  const v = (i: IndicadoresLitro | null, k: keyof IndicadoresLitro) => (i && temResultadoPorLitro(i) ? (i[k] as number | null) : null);
  const ded = (i: IndicadoresLitro | null) => (i && temResultadoPorLitro(i) && i.litros > 0 ? i.deducoes_leite / i.litros : null);
  return [
    { chave: "preco_bruto", nome: "Preço bruto do leite", a: v(a, "preco_bruto_l"), b: v(b, "preco_bruto_l"), bom: "sobe", dre: "RECEITA_VENDAS" },
    { chave: "deducoes", nome: "Funrural, Senar e descontos", a: ded(a), b: ded(b), bom: "desce", ind: true, dre: "DEDUCAO_IMPOSTOS" },
    { chave: "preco_liquido", nome: "Preço líquido do leite", a: v(a, "preco_liquido_l"), b: v(b, "preco_liquido_l"), bom: "sobe", tot: true },
    { chave: "comida", nome: "Comida", sub: "contas de alimentação (as mesmas do RMCA)", a: v(a, "comida_l"), b: v(b, "comida_l"), bom: "desce", ind: true, dre: "CUSTO_VARIAVEL" },
    { chave: "gente", nome: "Gente", sub: "folha e encargos", a: v(a, "pessoal_l"), b: v(b, "pessoal_l"), bom: "desce", ind: true, dre: "GASTOS_PESSOAL" },
    { chave: "outros", nome: "Outros custeios", sub: "o resto do custeio: sanidade, reprodução, energia, manutenção…", a: v(a, "outros_l"), b: v(b, "outros_l"), bom: "desce", ind: true, dre: "DESPESAS_OPERACIONAIS" },
    { chave: "coe", nome: "Custo de custeio (COE)", a: v(a, "coe_l"), b: v(b, "coe_l"), bom: "desce", tot: true },
    { chave: "margem", nome: "Sobra do custeio", a: v(a, "margem_l"), b: v(b, "margem_l"), bom: "sobe", tot: true },
    { chave: "depreciacao", nome: "Desgaste dos bens", sub: "depreciação do período", a: v(a, "depreciacao_l"), b: v(b, "depreciacao_l"), bom: "desce", ind: true, dre: "DEPRECIACAO_AMORT_EXAUSTAO" },
    { chave: "cot", nome: "Custo total (COT)", a: v(a, "cot_l"), b: v(b, "cot_l"), bom: "desce", tot: true },
    { chave: "margem_cot", nome: "Sobra depois de repor os bens", a: v(a, "margem_cot_l"), b: v(b, "margem_cot_l"), bom: "sobe", tot: true },
  ];
}

/** Pontos do gráfico de 12 meses (mês sem leite fica vazio, sem inventar zero). */
export type PontoLitro = {
  comp: string; preco: number | null; custo: number | null; faixaPos: [number, number] | null; faixaNeg: [number, number] | null;
  /** Mês cujos litros vêm da Venda mensal (reserva), não de uma nota do laticínio. */
  estimado: boolean;
};
export function serieLitro(r: RespostaLitro | null): PontoLitro[] {
  return (r?.serie ?? []).map((m) => {
    const ok = temResultadoPorLitro(m);
    const preco = ok ? m.preco_liquido_l : null, custo = ok ? m.coe_l : null;
    const ambos = preco != null && custo != null;
    return {
      comp: m.competencia, preco, custo, estimado: ok && m.fonte_litros === "venda_mensal",
      // A faixa entre as linhas: sobra (preço acima do custo) ou falta (custo acima do preço).
      faixaPos: ambos && preco! >= custo! ? [custo!, preco!] : null,
      faixaNeg: ambos && custo! > preco! ? [preco!, custo!] : null,
    };
  });
}

export function fraseLitro(o: {
  periodo: Periodo; regime: Regime; a: IndicadoresLitro; b: IndicadoresLitro | null; rotuloCmp: string | null;
  brl: (v: number) => string; delta: (a: number, b: number, bom: "sobe" | "desce") => Delta | null;
}): { t: string; b?: boolean }[] {
  const { a } = o;
  if (!temResultadoPorLitro(a)) return [];
  const sobra = a.margem_l ?? 0;
  const out: { t: string; b?: boolean }[] = [
    { t: `Em ${o.periodo.label} cada litro foi vendido por ` }, { t: o.brl(a.preco_liquido_l!), b: true },
    { t: " líquido e custou " }, { t: o.brl(a.coe_l!), b: true }, { t: " de custeio — " },
    { t: sobra >= 0 ? "sobraram " : "faltaram " }, { t: `${o.brl(Math.abs(sobra))} por litro`, b: true },
  ];
  if (o.rotuloCmp && o.b && temResultadoPorLitro(o.b) && o.b.margem_l != null) {
    const d = o.delta(sobra, o.b.margem_l, "sobe");
    if (d && d.igual) out.push({ t: `, igual a ${o.rotuloCmp}` });
    else if (d) out.push({ t: `, ${o.brl(Math.abs(d.abs))} ${d.abs > 0 ? "a mais" : "a menos"} que em ${o.rotuloCmp}` });
    // A maior mudança entre comida, gente e outros custeios (por litro).
    const partes: [string, number | null, number | null][] = [
      ["comida", a.comida_l, o.b.comida_l], ["gente", a.pessoal_l, o.b.pessoal_l], ["outros custeios", a.outros_l, o.b.outros_l], ["preço do leite", a.preco_liquido_l, o.b.preco_liquido_l],
    ];
    const maior = partes.filter(([, x, y]) => x != null && y != null).map(([n, x, y]) => [n, (x as number) - (y as number)] as const)
      .sort((p, q) => Math.abs(q[1]) - Math.abs(p[1]))[0];
    if (maior && Math.abs(maior[1]) >= 0.005) {
      const n = maior[0], v = maior[1];
      out.push({ t: `. A maior mudança veio de ${n} (${v > 0 ? "+" : "−"}${o.brl(Math.abs(v))} por litro)` });
    }
  }
  out.push({ t: "." });
  return out;
}
