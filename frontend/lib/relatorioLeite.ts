// Relatórios › Leite (Fase C): "Custos do leite" e "Sobra da comida por vaca
// (RMCA)". Modelos de tela das respostas de GET /financeiro/custos-leite,
// /financeiro/custo-vaca-lote, /financeiro/custo-hectare, /financeiro/custo-safra
// e /financeiro/rmca-vaca — os números vêm do servidor; aqui só se organiza
// (linhas, frase, série do gráfico) e se decide o que mostrar da régua de
// referência. PURO (só import de tipo) — testes em relatorioLeite.test.ts.
import type { Delta, Periodo } from "@/lib/relatorioContexto";
import type { IndicadoresLitro, PontoLitro, RespostaLitro } from "@/lib/relatorioLitro";

// ── Custos do leite ─────────────────────────────────────────────────────────
export type EstimativasCusto = {
  familia_informada: boolean; capital_informado: boolean;
  familia_mes: number; taxa_capital_aa: number; capital: { rebanho: number; maquinas: number; terra: number }; capital_total: number;
  familia_periodo: number; retorno_capital_periodo: number | null; cot: number; ct: number | null;
  familia_l: number | null; retorno_capital_l: number | null; cot_l: number | null; ct_l: number | null;
};
export type RespostaCustosLeite = {
  periodo: { inicio: string; fim: string }; regime: string; centro_custo: string | null; regras_v2: boolean;
  litro: RespostaLitro; estimativas: EstimativasCusto;
  /** Só com as regras antigas: a comida por litro da tela anterior (GET /financeiro/custo-litro-leite). */
  alimentacao_tela_anterior?: { custo_por_litro: number | null; custo_total: number; litros: number } | null;
  media_serie: { meses: number; coe_l: number | null; cot_l: number | null; preco_liquido_l: number | null };
};

/** Visões da tela Custos do leite (?visao=). Os ids antigos de Rel caem na visão certa. */
export type VisaoCusto = "litro" | "lote" | "ha" | "safra";
export const VISOES_CUSTO: { v: VisaoCusto; rotulo: string }[] = [
  { v: "litro", rotulo: "Por litro" }, { v: "lote", rotulo: "Por vaca e lote" }, { v: "ha", rotulo: "Por hectare" }, { v: "safra", rotulo: "Por safra" },
];
export const visaoCusto = (v: string | null | undefined): VisaoCusto => (VISOES_CUSTO.some((x) => x.v === v) ? (v as VisaoCusto) : "litro");

export type LinhaCusto = {
  chave: string; nome: string; sub?: string; a: number | null; b: number | null; tot?: boolean; ind?: boolean;
  /** Estimativa por parâmetro (selo "parâmetro"). */
  parametro?: boolean;
  /** Linha da DRE que explica o número (drill). */
  dre?: string;
};

const temLitros = (i: IndicadoresLitro | null | undefined) => !!i && i.litros > 0;

/** "Do custeio ao custo total, por litro" (CNA/Embrapa): comida + gente + outros = COE;
 *  + desgaste + família = COT; + retorno do capital = CT. Sem parâmetro, a linha fica vazia (nunca zero inventado). */
export function linhasCustoLitro(a: RespostaCustosLeite | null, b: RespostaCustosLeite | null): LinhaCusto[] {
  const ia = a?.litro.atual, ib = b?.litro.atual;
  const v = (i: IndicadoresLitro | undefined, k: keyof IndicadoresLitro) => (i && temLitros(i) ? (i[k] as number | null) : null);
  const e = (r: RespostaCustosLeite | null, k: keyof EstimativasCusto, so?: "familia" | "capital") => {
    if (!r || !temLitros(r.litro.atual)) return null;
    if (so === "familia" && !r.estimativas.familia_informada) return null;
    if (so === "capital" && !r.estimativas.capital_informado) return null;
    return r.estimativas[k] as number | null;
  };
  // Regras antigas: a comida é a da tela anterior (itens das contas de alimentação ÷ litros) e
  // "outros" (custeio − comida − gente) fica travado — não se inventa uma repartição que não fecha.
  const antiga = (r: RespostaCustosLeite | null) => !!r && !r.regras_v2 && r.alimentacao_tela_anterior != null;
  const comida = (r: RespostaCustosLeite | null, i: IndicadoresLitro | undefined) =>
    antiga(r) ? (temLitros(i) ? r!.alimentacao_tela_anterior!.custo_por_litro : null) : v(i, "comida_l");
  const outros = (r: RespostaCustosLeite | null, i: IndicadoresLitro | undefined) => (antiga(r) ? null : v(i, "outros_l"));
  return [
    { chave: "comida", nome: "Comida", sub: antiga(a) ? "regras antigas: itens das contas de alimentação ÷ litros (como a tela anterior)" : "contas de alimentação (as mesmas do RMCA)",
      a: comida(a, ia), b: comida(b, ib), ind: true, dre: "CUSTO_VARIAVEL" },
    { chave: "gente", nome: "Gente", sub: "folha e encargos", a: v(ia, "pessoal_l"), b: v(ib, "pessoal_l"), ind: true, dre: "GASTOS_PESSOAL" },
    { chave: "outros", nome: "Outros custeios", sub: antiga(a) ? "travado com as regras antigas: a comida da tela anterior não fecha com o custeio da DRE" : "sanidade, reprodução, energia, manutenção…",
      a: outros(a, ia), b: outros(b, ib), ind: true, dre: "DESPESAS_OPERACIONAIS" },
    { chave: "coe", nome: "Custo de custeio (COE)", sub: "o que saiu do bolso", a: v(ia, "coe_l"), b: v(ib, "coe_l"), tot: true },
    { chave: "depreciacao", nome: "Desgaste dos bens", sub: "depreciação do período", a: v(ia, "depreciacao_l"), b: v(ib, "depreciacao_l"), ind: true, dre: "DEPRECIACAO_AMORT_EXAUSTAO" },
    { chave: "familia", nome: "Remuneração da família", sub: "pró-labore (parâmetro)", a: e(a, "familia_l", "familia"), b: e(b, "familia_l", "familia"), ind: true, parametro: true },
    { chave: "cot", nome: "Custo operacional total (COT)", sub: "custeio + desgaste + família", a: e(a, "cot_l"), b: e(b, "cot_l"), tot: true },
    { chave: "capital", nome: "Retorno do capital", sub: "taxa ao ano sobre o capital empatado (parâmetro)", a: e(a, "retorno_capital_l", "capital"), b: e(b, "retorno_capital_l", "capital"), ind: true, parametro: true },
    { chave: "ct", nome: "Custo total (CT)", sub: "com o retorno do capital", a: e(a, "ct_l", "capital"), b: e(b, "ct_l", "capital"), tot: true },
  ];
}

export function fraseCustos(o: {
  periodo: Periodo; r: RespostaCustosLeite; rotuloCmp: string | null; b: RespostaCustosLeite | null;
  brl: (v: number) => string; delta: (a: number, b: number, bom: "sobe" | "desce") => Delta | null;
}): { t: string; b?: boolean }[] {
  const a = o.r.litro.atual, e = o.r.estimativas;
  if (!temLitros(a) || a.coe_l == null) return [];
  const out: { t: string; b?: boolean }[] = [
    { t: `Em ${o.periodo.label} o ` }, { t: "custo de custeio", b: true }, { t: " — o que saiu do bolso — foi " },
    { t: `${o.brl(a.coe_l)} por litro`, b: true },
  ];
  if (o.r.media_serie.coe_l != null && o.r.media_serie.meses > 1) out.push({ t: ` (média de ${o.r.media_serie.meses} meses: ${o.brl(o.r.media_serie.coe_l)})` });
  const bl = o.b?.litro.atual;
  if (o.rotuloCmp && bl && temLitros(bl) && bl.coe_l != null) {
    const d = o.delta(a.coe_l, bl.coe_l, "desce");
    if (d && d.igual) out.push({ t: `, igual a ${o.rotuloCmp}` });
    else if (d) out.push({ t: `, ${o.brl(Math.abs(d.abs))} ${d.abs > 0 ? "a mais" : "a menos"} que em ${o.rotuloCmp}` });
  }
  out.push({ t: ". " });
  if (e.cot_l != null) {
    out.push({ t: e.familia_informada ? "Somando o desgaste dos bens e a família, " : "Somando o desgaste dos bens, " }, { t: o.brl(e.cot_l), b: true });
    if (e.ct_l != null) out.push({ t: "; com o retorno do capital, " }, { t: o.brl(e.ct_l), b: true });
    out.push({ t: ". " });
  }
  if (a.preco_liquido_l != null) out.push({ t: `O leite foi vendido por ${o.brl(a.preco_liquido_l)} líquido.` });
  return out;
}

/** Pendências dos parâmetros das estimativas (cada uma com o caminho de 1 clique). */
export function pendenciasEstimativas(e: EstimativasCusto | null | undefined): { chave: string; texto: string; pronto: boolean }[] {
  if (!e) return [];
  return [
    { chave: "familia", texto: "Remuneração da família (pró-labore) informada", pronto: e.familia_informada },
    { chave: "capital", texto: "Capital empatado (rebanho, máquinas e benfeitorias) e taxa informados", pronto: e.capital_informado },
  ];
}

// ── Por vaca e lote / hectare / safra (endpoints da Fase A) ────────────────
export type RateioDepreciacaoCusto = {
  centro_custo: string; depreciacao_bens_do_centro: number; depreciacao_bens_sem_centro: number; depreciacao_rateada: number;
  participacao: number; aviso: string | null;
};
export type CamposCot = {
  regras_v2?: boolean; depreciacao_periodo?: number; cot?: number; depreciacao_rateio?: RateioDepreciacaoCusto | null;
  fora_por_natureza?: Record<string, number>;
};
export type RespostaCustoVacaLote = CamposCot & {
  periodo: { inicio: string; fim: string }; centro_custo: string | null; tem_vacas_no_periodo: boolean;
  num_vacas: number; despesas_total: number; custo_por_vaca: number | null; cot_por_vaca?: number | null;
  por_lote: { lote: string; num_vacas: number; custo_alocado: number; custo_por_vaca: number }[];
};
export type RespostaCustoHectare = CamposCot & {
  periodo: { inicio: string; fim: string }; centro_custo: string | null; area_configurada: boolean;
  area_hectares: number | null; despesas_total: number; custo_por_hectare: number | null; cot_por_hectare?: number | null;
};
export type SafraOpcao = { id: number; nome: string; centro_custo: string; hectares: number; toneladas_produzidas: number; ativo: boolean };
export type RespostaCustoSafra = CamposCot & {
  safra: SafraOpcao & { data_inicio: string; data_fim: string; observacao: string | null };
  por_categoria: { codigo: string; descricao: string; valor: number }[];
  despesas_total: number; hectares: number | null; toneladas_produzidas: number | null;
  custo_por_hectare: number | null; custo_por_tonelada: number | null;
};

export const ROTULO_NATUREZA: Record<string, string> = {
  OPERACIONAL: "Operacional", INVESTIMENTO: "Investimento (bens e animais do plantel)", FINANCIAMENTO: "Financiamento (principal)",
  CAPITAL: "Capital (aporte e retirada)", TRANSFERENCIA: "Transferência entre contas", ADIANTAMENTO: "Adiantamento (vale)",
  OBRIGACAO: "Obrigação já reconhecida", NAO_INFORMADA: "Fora da DRE, motivo não informado",
};

/** O que ficou FORA do numerador (natureza ≠ operacional), do maior para o menor — a tela mostra o investimento fora. */
export function foraDoCusto(c: CamposCot | null | undefined): { natureza: string; rotulo: string; valor: number }[] {
  return Object.entries(c?.fora_por_natureza ?? {})
    .filter(([, v]) => Math.abs(v) >= 0.005)
    .map(([n, v]) => ({ natureza: n, rotulo: ROTULO_NATUREZA[n] ?? n, valor: v }))
    .sort((x, y) => Math.abs(y.valor) - Math.abs(x.valor));
}

/** Barras por lote: o custo alocado de cada lote (a soma fecha com as despesas do período). */
export function barrasPorLote(r: RespostaCustoVacaLote | null): { chave: string; nome: string; valor: number; sub: string }[] {
  return (r?.por_lote ?? []).map((l) => ({ chave: l.lote, nome: l.lote, valor: l.custo_alocado, sub: `${l.num_vacas} vaca${l.num_vacas === 1 ? "" : "s"}` }))
    .sort((a, b) => b.valor - a.valor);
}

// ── Sobra da comida por vaca/dia (RMCA) ────────────────────────────────────
export type IndicadoresRmca = {
  receita_bruta: number; receita_liquida: number | null; comida: number; rmca: number; rmca_liquida: number | null;
  comida_receita_pct: number | null; comida_receita_liquida_pct: number | null;
  receita_vaca_dia: number | null; comida_vaca_dia: number | null; rmca_vaca_dia: number | null; rmca_liquida_vaca_dia: number | null;
  litros: number; litros_vaca_dia: number | null;
  vaca_dias: number; dias: number; vacas: number; vacas_media: number | null;
};
export type ItemFisico = {
  ingrediente: string; quantidade: number; valor_unitario: number; custo: number; estoque_id?: number | null; unidade?: string | null;
  quantidade_kg: number; preco_padrao_kg: number | null; preco_ultima_compra_kg: number | null;
};
export type LoteRmca = {
  lote: string; vacas: number; vacas_media: number | null; vaca_dias: number; leite_l_vaca_dia: number | null;
  receita_vaca_dia: number | null; comida_vaca_dia: number | null; rmca_vaca_dia: number | null; consumo_sem_preco_kg: number;
};
export type RespostaRmcaVaca = {
  periodo: { inicio: string; fim: string }; regras_v2: boolean; configurado: boolean;
  contas_receita: string[]; contas_custo: string[]; meta_rmca: number;
  contas_receita_codigos?: { codigo: string; nome: string }[]; contas_custo_codigos?: { codigo: string; nome: string }[];
  gerencial: { receita_leite: number; custo_alimentacao: number; rmca: number; receita_leite_liquida?: number; deducoes_receita_leite?: number; rmca_sobre_liquida?: number };
  atual: IndicadoresRmca;
  fisico: Omit<IndicadoresRmca, "vaca_dias" | "dias" | "vacas" | "vacas_media"> & { itens: ItemFisico[] };
  preco_medio_litro_leite: { competencia: string; preco_por_litro: number; receita: number; litros: number } | null;
  serie: (IndicadoresRmca & { competencia: string })[];
  por_lote: LoteRmca[]; preco_bruto_l: number | null; avisos: string[];
};

/** Há o que mostrar? Sem contas marcadas e sem receita nem comida, a tela ensina em vez de mostrar zero. */
export const temRmca = (r: RespostaRmcaVaca | null) =>
  !!r && (Math.abs(r.atual.receita_bruta) >= 0.005 || Math.abs(r.atual.comida) >= 0.005);
export const temPorVaca = (i: IndicadoresRmca | null | undefined) => !!i && i.vaca_dias > 0 && i.rmca_vaca_dia != null;

/** Pontos do gráfico de 12 meses receita × comida por vaca/dia — o MESMO formato do preço × custo por litro
 *  (o gráfico é o mesmo componente). Mês sem vaca controlada ou sem receita fica vazio. */
export function serieRmca(r: RespostaRmcaVaca | null): PontoLitro[] {
  return (r?.serie ?? []).map((m) => {
    const ok = temPorVaca(m) && m.receita_bruta > 0;
    const rec = ok ? m.receita_vaca_dia : null, com = ok ? m.comida_vaca_dia : null;
    const ambos = rec != null && com != null;
    return {
      comp: m.competencia, preco: rec, custo: com, estimado: false,
      faixaPos: ambos && rec! >= com! ? [com!, rec!] : null,
      faixaNeg: ambos && com! > rec! ? [rec!, com!] : null,
    };
  });
}

export function fraseRmca(o: {
  periodo: Periodo; r: RespostaRmcaVaca; rb: RespostaRmcaVaca | null; rotuloCmp: string | null; brl: (v: number) => string;
}): { t: string; b?: boolean }[] {
  const a = o.r.atual;
  if (!temRmca(o.r)) return [];
  if (!temPorVaca(a)) {
    return [
      { t: `Em ${o.periodo.label} a receita do leite foi ` }, { t: o.brl(a.receita_bruta), b: true }, { t: " e a comida custou " },
      { t: o.brl(a.comida), b: true }, { t: `: ${a.rmca >= 0 ? "sobraram" : "faltaram"} ` }, { t: o.brl(Math.abs(a.rmca)), b: true },
      { t: ". Sem Controle leiteiro no período, não dá para dividir por vaca." },
    ];
  }
  const out: { t: string; b?: boolean }[] = [
    { t: `Em ${o.periodo.label} cada vaca em lactação rendeu ` }, { t: o.brl(a.receita_vaca_dia!), b: true },
    { t: " de leite por dia e a comida custou " }, { t: o.brl(a.comida_vaca_dia!), b: true },
    { t: `: ${a.rmca_vaca_dia! >= 0 ? "sobraram" : "faltaram"} ` }, { t: `${o.brl(Math.abs(a.rmca_vaca_dia!))} por vaca/dia`, b: true },
    { t: a.rmca_vaca_dia! >= 0 ? " para pagar o resto" : "" },
  ];
  const b = o.rb?.atual;
  if (o.rotuloCmp && temPorVaca(b)) out.push({ t: ` (${o.brl(b!.rmca_vaca_dia!)} em ${o.rotuloCmp})` });
  out.push({ t: "." });
  if (o.r.fisico.rmca_vaca_dia != null && o.r.fisico.itens.length) out.push({ t: ` Pelo consumo registrado na Alimentação, a sobra seria ${o.brl(o.r.fisico.rmca_vaca_dia)}.` });
  return out;
}

// ── Régua de referência (GET /financeiro/reguas-referencia) ─────────────────
// Consumo DEFENSIVO (parecer jurídico, item 6.3): só se desenha faixa quando a
// régua está "publicada", com faixa numérica válida e sem validade vencida.
// Fora disso, nada (nem texto de faixa). Faixa cinza neutra, a palavra
// "referência", sem semáforo e sem linguagem de meta.
export type ReguaVisivel = { codigo: string; nome: string; min: number; max: number; unidade: string; fidedignidade: string | null; venceEm: string | null };

export function reguaVisivel(resp: unknown, codigo: string, hoje: string): ReguaVisivel | null {
  if (!resp || typeof resp !== "object") return null;
  const r = resp as Record<string, unknown>;
  if (r.vencida === true || r.aceite_pendente === true || r.faixas_ocultas_ate_aceite === true) return null;
  if (r.publicacao && typeof r.publicacao === "object" && (r.publicacao as Record<string, unknown>).liberada === false) return null;
  const lista = Array.isArray(r.reguas) ? r.reguas : [];
  const g = lista.find((x) => x && typeof x === "object" && (x as Record<string, unknown>).codigo === codigo) as Record<string, unknown> | undefined;
  if (!g || g.situacao !== "publicada" || g.exibir_faixa !== true) return null;
  const f = g.faixa as Record<string, unknown> | null | undefined;
  const min = typeof f?.min === "number" ? f.min : NaN, max = typeof f?.max === "number" ? f.max : NaN;
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return null;
  const vence = typeof g.vence_em === "string" ? g.vence_em : null;
  if (vence && vence < hoje) return null;
  return {
    codigo, nome: typeof g.nome === "string" ? g.nome : codigo, min, max, unidade: typeof g.unidade === "string" ? g.unidade : "",
    fidedignidade: typeof g.fidedignidade === "string" ? g.fidedignidade : null, venceEm: vence,
  };
}
