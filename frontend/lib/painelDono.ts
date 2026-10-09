// Painel do dono (Relatórios › Painel) e "Apresentar o mês": as 4 perguntas do
// dono respondidas com os números DO SERVIDOR — DRE única (GET /financeiro/dre),
// Resultado por litro, Caixa real e orçado × realizado. Aqui só se escolhe o que
// mostrar e se escreve em palavras; nenhuma conta nova de resultado.
// PURO (só import de tipo; formatadores entram por parâmetro) — testes em painelDono.test.ts.
import type { IndicadoresLitro } from "./relatorioLitro";

export type Fmt = { brl: (v: number) => string; brl0: (v: number) => string; dia: (iso: string) => string };

// ── Caixa real (GET /financeiro/caixa-real) ──────────────────────────────
export type ItemCaixa = { descricao: string | null; valor: number; tipo: string; vencido: boolean; data_original: string };
export type CaixaLite = {
  saldo_inicial: number; fundo_reserva: number; primeiro_dia_negativo: string | null; primeiro_dia_abaixo_da_reserva: string | null;
  serie: { data: string; saldo: number; itens: ItemCaixa[] }[];
};
export type RespostaCaixa = {
  saldoHoje: number; reserva: number; menor: { saldo: number; data: string } | null;
  negativoEm: string | null; abaixoReservaEm: string | null;
  vence7: { itens: (ItemCaixa & { data: string })[]; total: number; temVencida: boolean };
};

/** O que o painel diz do caixa: o saldo de hoje, o ponto mais baixo e os marcos do próprio Caixa real. */
export function respostaCaixa(c: CaixaLite | null, hoje: string, dias = 60): RespostaCaixa | null {
  if (!c) return null;
  const limite = somaDias(hoje, dias), limite7 = somaDias(hoje, 7);
  const janela = c.serie.filter((p) => p.data <= limite);
  const menor = janela.reduce<{ saldo: number; data: string } | null>((m, p) => (!m || p.saldo < m.saldo ? { saldo: p.saldo, data: p.data } : m), null);
  const itens = c.serie.filter((p) => p.data <= limite7)
    .flatMap((p) => p.itens.filter((i) => i.tipo !== "receita").map((i) => ({ ...i, data: p.data })));
  const total = Math.round(itens.reduce((s, i) => s + i.valor, 0) * 100) / 100;
  const dentro = (d: string | null) => (d && d <= limite ? d : null);
  return {
    saldoHoje: c.saldo_inicial, reserva: c.fundo_reserva, menor,
    negativoEm: dentro(c.primeiro_dia_negativo), abaixoReservaEm: dentro(c.primeiro_dia_abaixo_da_reserva),
    vence7: { itens, total, temVencida: itens.some((i) => i.vencido) },
  };
}

export function somaDias(iso: string, k: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const t = new Date(Date.UTC(a, m - 1, d + k));
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}-${String(t.getUTCDate()).padStart(2, "0")}`;
}

// ── Orçado × realizado (GET /planejamento/orcamento/comparativo) ──────────
export type ComparativoLite = {
  regras_v2?: boolean; total_orcado: number; total_realizado: number;
  totais?: Record<string, { orcado: number; realizado: number; desvio: number | null; desvio_pct: number | null; situacao?: string }>;
};
export type RespostaOrcado =
  | { estado: "ok"; orcado: number; realizado: number; desvio: number; desvioPct: number | null; acima: boolean }
  | { estado: "sem_orcamento"; realizado: number }
  | { estado: "regras_antigas" }
  | { estado: "varios_anos" };

/** O orçamento é por ano e mês: o período precisa caber num ano só. */
export function mesesDoOrcamento(ini: string, fim: string): { ano: number; mes_inicio: number; mes_fim: number } | null {
  if (ini.slice(0, 4) !== fim.slice(0, 4)) return null;
  return { ano: Number(ini.slice(0, 4)), mes_inicio: Number(ini.slice(5, 7)), mes_fim: Number(fim.slice(5, 7)) };
}

/** Despesa operacional realizada × orçada, pelos totais SEPARADOS do servidor (regras v2).
 *  Com as regras antigas o total do servidor somava receita com despesa: a tela trava com o porquê. */
export function respostaOrcado(c: ComparativoLite | null, cabeNumAno: boolean): RespostaOrcado | null {
  if (!cabeNumAno) return { estado: "varios_anos" };
  if (!c) return null;
  const t = c.totais?.despesa_operacional;
  if (!c.regras_v2 || !t) return { estado: "regras_antigas" };
  if (!(t.orcado > 0)) return { estado: "sem_orcamento", realizado: t.realizado };
  const desvio = t.desvio ?? Math.round((t.realizado - t.orcado) * 100) / 100;
  return { estado: "ok", orcado: t.orcado, realizado: t.realizado, desvio, desvioPct: t.desvio_pct, acima: desvio > 0 };
}

// ── Frase-resumo e decisões do mês ────────────────────────────────────────
export type Trecho = { t: string; b?: boolean };

export function frasePainel(o: {
  periodoLabel: string; resultado: number | null; litro: IndicadoresLitro | null; caixa: RespostaCaixa | null; fmt: Fmt;
}): Trecho[] {
  const { fmt } = o;
  const out: Trecho[] = [];
  if (o.resultado != null) {
    out.push({ t: `Em ${o.periodoLabel} a fazenda ${o.resultado >= 0 ? "teve resultado de " : "teve prejuízo de "}` }, { t: fmt.brl0(Math.abs(o.resultado)), b: true }, { t: "." });
  }
  const l = o.litro;
  if (l && l.litros > 0 && l.preco_liquido_l != null && l.coe_l != null && l.margem_l != null) {
    out.push({ t: " Cada litro foi vendido por " }, { t: fmt.brl(l.preco_liquido_l), b: true }, { t: " e custou " }, { t: fmt.brl(l.coe_l), b: true },
      { t: ` de custeio: ${l.margem_l >= 0 ? "sobraram" : "faltaram"} ` }, { t: `${fmt.brl(Math.abs(l.margem_l))} por litro`, b: true }, { t: "." });
  }
  const c = o.caixa;
  if (c) {
    out.push({ t: " O caixa tem " }, { t: fmt.brl0(c.saldoHoje), b: true }, { t: " hoje" });
    if (c.negativoEm) out.push({ t: " e fica abaixo de zero em " }, { t: fmt.dia(c.negativoEm), b: true });
    else if (c.abaixoReservaEm) out.push({ t: " e fica abaixo da reserva em " }, { t: fmt.dia(c.abaixoReservaEm), b: true });
    else out.push({ t: " e não fica abaixo da reserva nos próximos 60 dias" });
    out.push({ t: "." });
  }
  return out;
}

export type Decisao = { chave: string; tipo: "alerta" | "prazo" | "contador" | "info"; titulo: string; texto: string; relatorio: string; rotulo: string };

/** "A decisão do mês": só pontos que pedem ação, cada um com o relatório que mostra o detalhe. */
export function decisoesDoMes(o: {
  caixa: RespostaCaixa | null; litro: IndicadoresLitro | null; naoClassificado: number; pendenciasNatureza: number;
  orcado: RespostaOrcado | null; fmt: Fmt;
}): Decisao[] {
  const { fmt, caixa: c } = o;
  const out: Decisao[] = [];
  if (c && (c.negativoEm || c.abaixoReservaEm)) {
    const partes = [c.abaixoReservaEm ? `fica abaixo da reserva em ${fmt.dia(c.abaixoReservaEm)}` : null,
      c.negativoEm ? `fica abaixo de zero em ${fmt.dia(c.negativoEm)}` : null].filter(Boolean).join(" e ");
    out.push({ chave: "caixa", tipo: "alerta", titulo: `Caixa: ${partes}${c.menor ? ` (menor saldo ${fmt.brl0(c.menor.saldo)} em ${fmt.dia(c.menor.data)})` : ""}.`,
      texto: "Decidir antes: renegociar uma data, antecipar um recebimento ou adiar uma compra.", relatorio: "rel_caixa", rotulo: "Abrir o Caixa real" });
  }
  if (c && c.vence7.itens.length) {
    out.push({ chave: "vence7", tipo: "prazo", titulo: `Vence nos próximos 7 dias: ${fmt.brl0(c.vence7.total)} em ${c.vence7.itens.length} ${c.vence7.itens.length === 1 ? "compromisso" : "compromissos"}.`,
      texto: c.vence7.temVencida ? "Há conta vencida: pagar ou renegociar hoje." : "Tudo dentro do prazo.", relatorio: "rel_caixa", rotulo: "Ver as contas" });
  }
  const l = o.litro;
  if (l && l.margem_l != null && l.margem_l < 0) {
    out.push({ chave: "litro", tipo: "alerta", titulo: `Cada litro custou ${fmt.brl(-l.margem_l)} a mais do que rendeu.`,
      texto: "Ver no Resultado por litro onde o custeio subiu (comida, gente ou outros custeios).", relatorio: "rel_litro", rotulo: "Abrir o Resultado por litro" });
  }
  if (o.orcado && o.orcado.estado === "ok" && o.orcado.acima) {
    out.push({ chave: "orcado", tipo: "alerta", titulo: `As despesas passaram ${fmt.brl0(o.orcado.desvio)} do orçado.`,
      texto: "Ver no Orçamento quais contas passaram do planejado.", relatorio: "rel_orcamento", rotulo: "Abrir o Orçamento" });
  }
  if (Math.abs(o.naoClassificado) >= 0.005 || o.pendenciasNatureza > 0) {
    const p = [Math.abs(o.naoClassificado) >= 0.005 ? `${fmt.brl(Math.abs(o.naoClassificado))} em contas sem linha na DRE` : null,
      o.pendenciasNatureza > 0 ? `${o.pendenciasNatureza} ${o.pendenciasNatureza === 1 ? "lançamento" : "lançamentos"} sem natureza` : null].filter(Boolean).join(" e ");
    out.push({ chave: "contador", tipo: "contador", titulo: `Para o contador: ${p}.`,
      texto: "Classificar antes de fechar o mês, para o número entrar na DRE.", relatorio: "classificar", rotulo: "Classificar" });
  }
  return out;
}
