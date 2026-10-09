// "Caixa real" (Relatórios › Caixa, Fase C1): modelo de tela da resposta de
// GET /financeiro/caixa-real (a projeção do SERVIDOR: saldo de hoje, compromissos
// em aberto pelo vencimento, faturas de cartão abertas e pagamentos agendados),
// do fundo de reserva e do fôlego. Aqui só se reorganiza: resumo da projeção,
// linha do tempo por dia/semana, itens agrupados (fatura numa linha) e a
// simulação "Posso comprar?" — que é uma hipótese da pessoa, não um número do
// relatório. PURO (só import de tipo) — testes em relatorioCaixa.test.ts.
import type { CaixaReal } from "@/lib/api";

export type DiaCaixa = CaixaReal["serie"][number];
export type ItemCaixa = DiaCaixa["itens"][number];

const p2 = (n: number) => String(n).padStart(2, "0");
const r2 = (v: number) => Math.round(v * 100) / 100 + 0;

/** AAAA-MM-DD + k dias (fuso local, sem UTC). */
export function somaDias(iso: string, k: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const x = new Date(a, m - 1, d + k);
  return `${x.getFullYear()}-${p2(x.getMonth() + 1)}-${p2(x.getDate())}`;
}
/** Dias de `a` até `b` (b − a). */
export function diasEntre(a: string, b: string): number {
  const [y1, m1, d1] = a.split("-").map(Number), [y2, m2, d2] = b.split("-").map(Number);
  return Math.round((new Date(y2, m2 - 1, d2).getTime() - new Date(y1, m1 - 1, d1).getTime()) / 864e5);
}
/** Mesma data `k` meses depois (dia limitado ao fim do mês: 31/01 + 1 mês = 28/02). */
export function somaMesesDia(iso: string, k: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const idx = a * 12 + (m - 1) + k, ano = Math.floor(idx / 12), mes = (idx % 12) + 1;
  const ultimo = new Date(ano, mes, 0).getDate();
  return `${ano}-${p2(mes)}-${p2(Math.min(d, ultimo))}`;
}
export const dm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
export const dmy = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
const SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
export function diaSemana(iso: string): string {
  const [a, m, d] = iso.split("-").map(Number);
  return SEMANA[new Date(a, m - 1, d).getDay()];
}

/** Valor digitado em reais ("24.000,50", "24000.5", "R$ 1.200") → número; NaN se não der. */
export function lerValorBR(s: string): number {
  let t = String(s ?? "").trim().replace(/[^\d,.-]/g, "");
  if (!t) return NaN;
  if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  else if (/^-?\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, "");
  return parseFloat(t);
}

// ── Reserva ──────────────────────────────────────────────────────────────
export type Reserva = {
  valor: number;
  /** "parametro" = definida em Parâmetros; "sugerida" = meses de custeio do histórico (só para o gráfico, com aviso); "nenhuma". */
  origem: "parametro" | "sugerida" | "nenhuma";
  /** Quantos meses de saída média a reserva cobre (null sem histórico). */
  meses: number | null;
};
export function reservaDe(fundoReserva: number, sugestao: { sugerido: number; meses_folga: number } | null): Reserva {
  const media = sugestao && sugestao.meses_folga > 0 && sugestao.sugerido > 0 ? sugestao.sugerido / sugestao.meses_folga : null;
  if (fundoReserva > 0) return { valor: fundoReserva, origem: "parametro", meses: media ? Math.round((fundoReserva / media) * 10) / 10 : null };
  if (sugestao && sugestao.sugerido > 0) return { valor: sugestao.sugerido, origem: "sugerida", meses: sugestao.meses_folga };
  return { valor: 0, origem: "nenhuma", meses: null };
}

// ── Resumo da projeção ───────────────────────────────────────────────────
export type ResumoCaixa = {
  saldoHoje: number; saldoFim: number; entradas: number; saidas: number;
  menor: { saldo: number; data: string };
  primeiroNegativo: string | null;
  /** Último dia negativo da sequência que começa no 1º negativo (null se continua negativo até o fim). */
  voltaPositivo: string | null;
  primeiroAbaixoReserva: string | null;
  dias: number;
};
export function resumoCaixa(d: CaixaReal, reserva: Reserva): ResumoCaixa {
  const serie = d.serie ?? [];
  const menor = serie.reduce((m, p) => (p.saldo < m.saldo ? { saldo: p.saldo, data: p.data } : m),
    { saldo: serie[0]?.saldo ?? d.saldo_inicial, data: serie[0]?.data ?? "" });
  const iNeg = serie.findIndex((p) => p.saldo < 0);
  let volta: string | null = null;
  if (iNeg >= 0) { const k = serie.slice(iNeg).findIndex((p) => p.saldo >= 0); volta = k > 0 ? serie[iNeg + k].data : null; }
  // A reserva do parâmetro: o servidor marca; a sugerida: o mesmo critério sobre a mesma série.
  const abaixo = reserva.origem === "parametro" ? d.primeiro_dia_abaixo_da_reserva
    : reserva.valor > 0 ? serie.find((p) => p.saldo < reserva.valor)?.data ?? null : null;
  return {
    saldoHoje: d.saldo_inicial, saldoFim: d.saldo_final, entradas: d.total_entradas, saidas: d.total_saidas,
    menor, primeiroNegativo: d.primeiro_dia_negativo ?? (iNeg >= 0 ? serie[iNeg].data : null), voltaPositivo: volta,
    primeiroAbaixoReserva: abaixo, dias: d.dias,
  };
}

// ── Itens agrupados (fatura do cartão numa linha) ────────────────────────
export type ItemVis = { chave: string; nome: string; valor: number; entra: boolean; tags: string[]; quantidade: number; vencido: boolean; agendado: boolean; cartao: boolean };
export function agruparItens(itens: ItemCaixa[]): ItemVis[] {
  const out: ItemVis[] = [];
  const cartao = itens.filter((i) => i.fatura_cartao && i.tipo !== "receita");
  if (cartao.length) {
    const total = r2(cartao.reduce((s, i) => s + i.valor, 0));
    out.push({ chave: "cartao", nome: cartao.length === 1 ? `Fatura do cartão (${cartao[0].descricao || "1 compra"})` : `Fatura do cartão (${cartao.length} compras)`,
      valor: total, entra: false, tags: ["fatura aberta do cartão"], quantidade: cartao.length, vencido: false, agendado: false, cartao: true });
  }
  itens.filter((i) => !(i.fatura_cartao && i.tipo !== "receita")).forEach((i, k) => {
    const tags: string[] = [];
    if (i.vencido) tags.push(`vencido em ${dm(i.data_original)}`);
    if (i.agendado) tags.push("pagamento agendado");
    out.push({ chave: `i${k}`, nome: i.descricao || "(sem descrição)", valor: i.valor, entra: i.tipo === "receita", tags, quantidade: 1,
      vencido: !!i.vencido, agendado: !!i.agendado, cartao: false });
  });
  return out.sort((a, b) => Number(b.entra) - Number(a.entra) || b.valor - a.valor);
}

// ── Linha do tempo: por dia (só dias com movimento) ou por semana ─────────
export type Periodo = { chave: string; ini: string; fim: string; entradas: number; saidas: number; saldoFim: number; menorSaldo: number; itens: number };
export function linhaDoTempo(serie: DiaCaixa[], modo: "dia" | "semana"): Periodo[] {
  if (!serie.length) return [];
  if (modo === "dia") {
    return serie.filter((p) => p.entradas || p.saidas).map((p) => ({
      chave: p.data, ini: p.data, fim: p.data, entradas: p.entradas, saidas: p.saidas, saldoFim: p.saldo, menorSaldo: p.saldo, itens: p.itens.length,
    }));
  }
  const out: Periodo[] = [];
  for (let i = 0; i < serie.length; i += 7) {
    const fatia = serie.slice(i, i + 7);
    out.push({
      chave: fatia[0].data, ini: fatia[0].data, fim: fatia[fatia.length - 1].data,
      entradas: r2(fatia.reduce((s, p) => s + p.entradas, 0)), saidas: r2(fatia.reduce((s, p) => s + p.saidas, 0)),
      saldoFim: fatia[fatia.length - 1].saldo, menorSaldo: Math.min(...fatia.map((p) => p.saldo)),
      itens: fatia.reduce((s, p) => s + p.itens.length, 0),
    });
  }
  return out;
}

// ── "Posso comprar?" ─────────────────────────────────────────────────────
export type Compra = { valor: number; data: string; parcelas: number };
export type Parcela = { data: string; valor: number };
export function parcelasDa(c: Compra): Parcela[] {
  const n = Math.max(1, Math.min(24, Math.floor(c.parcelas) || 1)), base = r2(c.valor / n);
  return Array.from({ length: n }, (_, i) => ({ data: somaMesesDia(c.data, i), valor: i === n - 1 ? r2(c.valor - base * (n - 1)) : base }));
}
/** A série com a compra descontada: cada parcela sai do saldo a partir do seu dia. */
export function serieComCompra(serie: DiaCaixa[], parcelas: Parcela[]): number[] {
  return serie.map((p) => r2(p.saldo - parcelas.filter((x) => x.data <= p.data).reduce((s, x) => s + x.valor, 0)));
}
const menorDe = (serie: DiaCaixa[], saldos: number[]) =>
  saldos.reduce((m, v, i) => (v < m.saldo ? { saldo: v, data: serie[i].data } : m), { saldo: saldos[0] ?? 0, data: serie[0]?.data ?? "" });

export type Simulacao =
  | { ok: false; erro: string }
  | {
    ok: true; parcelas: Parcela[]; foraDaJanela: number; saldos: number[];
    menorSem: { saldo: number; data: string }; menorCom: { saldo: number; data: string };
    primeiroNegativoCom: string | null; furaReserva: boolean;
    veredito: "pode" | "reserva" | "negativo" | "jaAperta";
    /** Primeira data (com todas as parcelas dentro da janela) em que a compra não aprofunda o aperto. */
    sugestao: string | null;
  };
export function simularCompra(serie: DiaCaixa[], c: Compra, hoje: string, reserva: number): Simulacao {
  if (!(c.valor > 0)) return { ok: false, erro: "Informe o valor da compra." };
  if (!c.data || c.data < hoje) return { ok: false, erro: "A 1ª parcela precisa ser de hoje em diante." };
  if (!(c.parcelas >= 1 && c.parcelas <= 24)) return { ok: false, erro: "Parcelas: de 1 a 24." };
  if (!serie.length) return { ok: false, erro: "Sem projeção para simular." };
  const fim = serie[serie.length - 1].data;
  const parcelas = parcelasDa(c);
  const saldos = serieComCompra(serie, parcelas);
  const menorSem = menorDe(serie, serie.map((p) => p.saldo)), menorCom = menorDe(serie, saldos);
  const iNeg = saldos.findIndex((v) => v < 0);
  const limite = Math.min(menorSem.saldo, reserva > 0 ? reserva : 0);
  let veredito: "pode" | "reserva" | "negativo" | "jaAperta";
  if (menorSem.saldo < 0) veredito = "jaAperta";
  else if (menorCom.saldo < 0) veredito = "negativo";
  else if (reserva > 0 && menorCom.saldo < reserva) veredito = "reserva";
  else veredito = "pode";
  let sugestao: string | null = null;
  if (menorCom.saldo < limite - 0.5) {
    for (let k = 1; k <= diasEntre(c.data, fim); k++) {
      const d = somaDias(c.data, k);
      const ps = parcelasDa({ ...c, data: d });
      if (ps[ps.length - 1].data > fim) break;
      const m = menorDe(serie, serieComCompra(serie, ps));
      if (m.saldo >= limite - 0.5) { sugestao = d; break; }
    }
  }
  return {
    ok: true, parcelas, foraDaJanela: parcelas.filter((x) => x.data > fim).length, saldos, menorSem, menorCom,
    primeiroNegativoCom: iNeg >= 0 ? serie[iNeg].data : null, furaReserva: reserva > 0 && menorCom.saldo < reserva, veredito, sugestao,
  };
}

// ── Frase-resumo ─────────────────────────────────────────────────────────
export type Trecho = { t: string; b?: boolean };
export function fraseCaixa(r: ResumoCaixa, reserva: Reserva, brl: (v: number) => string, pendente: boolean): Trecho[] {
  const out: Trecho[] = pendente
    ? [{ t: "Pela soma dos lançamentos, o caixa tem " }, { t: brl(r.saldoHoje), b: true }, { t: " hoje (falta o saldo de abertura de alguma conta)" }]
    : [{ t: "O caixa tem " }, { t: brl(r.saldoHoje), b: true }, { t: " hoje" }];
  out.push({ t: `. Nos próximos ${r.dias} dias entram ` }, { t: brl(r.entradas), b: true }, { t: " e saem " }, { t: brl(r.saidas), b: true }, { t: "." });
  if (r.primeiroNegativo) {
    out.push({ t: " O saldo fica abaixo de zero a partir de " }, { t: dm(r.primeiroNegativo), b: true },
      { t: r.voltaPositivo ? ` e volta em ${dm(r.voltaPositivo)}` : " e não volta dentro da janela" },
      { t: "; o ponto mais baixo é " }, { t: brl(r.menor.saldo), b: true }, { t: ` em ${dm(r.menor.data)}.` });
  } else {
    out.push({ t: " O ponto mais baixo é " }, { t: brl(r.menor.saldo), b: true }, { t: ` em ${dm(r.menor.data)}` });
    if (reserva.valor > 0 && r.primeiroAbaixoReserva) out.push({ t: `, abaixo da reserva${reserva.origem === "sugerida" ? " sugerida" : ""} a partir de ${dm(r.primeiroAbaixoReserva)}.` });
    else out.push({ t: reserva.valor > 0 ? ", sem tocar na reserva." : ", sem ficar negativo." });
  }
  return out;
}
