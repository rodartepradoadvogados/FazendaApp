// Cálculos PUROS da tela Resumo do Financeiro (janelas de dias, barras do
// gráfico, Posição, drill para Contas a pagar, fila do que pede ação).
//
// Sem import de runtime de propósito: só tipos (apagados na execução), para o
// arquivo rodar direto no runner nativo do Node (`node --experimental-strip-types
// --test`, ver resumoCalculo.test.ts) sem depender do alias "@/". Por isso as
// duas contas de data abaixo (somaDias/diasAte) são cópias fiéis das de
// lib/financeiroSituacao.ts — o teste confere que as duas dão o mesmo resultado.
// "Hoje" SEMPRE entra por parâmetro (a tela usa hojeLocal(), fuso local).
//
// CONVENÇÃO DE JANELA (a mesma de FAIXAS/situacaoDe): "vence em até 7 dias" é
// de hoje até hoje+7, inclusive. O período de N dias do Resumo é de hoje até
// hoje+N; "Vence do 8º ao Nº dia" é de hoje+8 até hoje+N; "Depois do período"
// começa em hoje+N+1. Vencido é tudo com vencimento até ontem.
import type { Lanc } from "@/lib/financeiroTipos";

export type DrillContas = { tipo: "venc" | "sem" | "meio" | "alem" | "todas" | "ate"; de?: string; ate?: string; rotulo: string };

/** Atalhos do seletor do gráfico; "Outro" aceita de 1 a 180. */
export const PERIODOS = [7, 14, 30, 60, 90] as const;
export const DIAS_MIN = 1;
export const DIAS_MAX = 180;
/** A partir daqui o gráfico mostra uma barra por semana, não por dia. */
export const LIMITE_DIARIO = 21;

const pad = (n: number) => String(n).padStart(2, "0");

/** Soma `n` dias a AAAA-MM-DD (fuso local). Igual a somaDias de lib/financeiroSituacao.ts. */
export function somaDias(iso: string, n: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const dt = new Date(a, m - 1, d + n);
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
}

/** Dias de `hoje` até `iso` (negativo = já passou). Igual a diasAte de lib/financeiroSituacao.ts. */
export function diasAte(iso: string, hoje: string): number {
  const [a, m, d] = iso.split("-").map(Number);
  const [a2, m2, d2] = hoje.split("-").map(Number);
  return Math.round((Date.UTC(a, m - 1, d) - Date.UTC(a2, m2 - 1, d2)) / 86400000);
}

/** Arredonda em centavos (evita 0,1 + 0,2). */
export const r2 = (v: number) => Math.round(v * 100) / 100;

/** Soma em centavos exatos. Igual a somaValores de lib/financeiroSituacao.ts. */
export function soma(xs: Lanc[]): number {
  return r2(xs.reduce((a, l) => a + l.valor, 0));
}

/** Número digitado em "Outro": inteiro de 1 a 180, ou null se inválido. */
export function diasValidos(txt: string | number): number | null {
  const s = String(txt).trim();
  if (!/^\d+$/.test(s)) return null;
  const n = Number(s);
  return n >= DIAS_MIN && n <= DIAS_MAX ? n : null;
}

/** Contas a pagar em aberto (mesma regra de Contas a pagar: despesa sem data de pagamento; notas de fatura incluídas). */
export const abertasPagar = (regs: Lanc[]) => regs.filter((l) => l.tipo === "despesa" && !l.data_pagamento);
/** Contas a receber em aberto. */
export const abertasReceber = (regs: Lanc[]) => regs.filter((l) => l.tipo === "receita" && !l.data_pagamento);

const naJanela = (xs: Lanc[], hoje: string, de: number, ate: number) =>
  xs.filter((l) => {
    if (!l.data_vencimento) return false;
    const d = diasAte(l.data_vencimento, hoje);
    return d >= de && d <= ate;
  });

// ── Gráfico ───────────────────────────────────────────────────────────────
export type EstadoBarra = "venc" | "logo" | "aberto";
export type Coluna = {
  chave: string;
  rotulo: string;      // "Vencidas", "07", "07/10"
  sub: string;         // "hoje", "qui", "sem. 2"
  dica: string;        // texto completo para <title> e tabela oculta
  de?: string; ate?: string;
  valor: number; n: number;
  st: EstadoBarra;
  hoje: boolean;
};

const DOW = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const dm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const dowDe = (iso: string) => { const [a, m, d] = iso.split("-").map(Number); return DOW[new Date(a, m - 1, d).getDay()]; };

/**
 * Barras do gráfico: "Vencidas" (acumulado até ontem) + uma por dia de hoje a
 * hoje+N; acima de 21 dias, uma por semana (a última pode ser mais curta).
 * Até o 7º dia a barra é "logo"; a partir do 8º, "aberto".
 */
export function colunasGrafico(abertas: Lanc[], hoje: string, dias: number): Coluna[] {
  const venc = abertas.filter((l) => l.data_vencimento && diasAte(l.data_vencimento, hoje) < 0);
  const ontem = somaDias(hoje, -1);
  const cols: Coluna[] = [{
    chave: "venc", rotulo: "Vencidas", sub: "", dica: `Vencidas até ${dm(ontem)}`, ate: ontem,
    valor: soma(venc), n: venc.length, st: "venc", hoje: false,
  }];
  if (dias <= LIMITE_DIARIO) {
    for (let i = 0; i <= dias; i++) {
      const iso = somaDias(hoje, i);
      const xs = naJanela(abertas, hoje, i, i);
      cols.push({
        chave: iso, rotulo: iso.slice(8, 10), sub: i === 0 ? "hoje" : dowDe(iso),
        dica: `${i === 0 ? "Hoje, " : `${dowDe(iso)}, `}${dm(iso)}`, de: iso, ate: iso,
        valor: soma(xs), n: xs.length, st: i <= 7 ? "logo" : "aberto", hoje: i === 0,
      });
    }
  } else {
    for (let k = 0; k * 7 <= dias; k++) {
      const a = k * 7, z = Math.min(a + 6, dias);
      const de = somaDias(hoje, a), ate = somaDias(hoje, z);
      const xs = naJanela(abertas, hoje, a, z);
      cols.push({
        chave: de, rotulo: dm(de), sub: `sem. ${k + 1}`, dica: `${dm(de)} a ${dm(ate)}`, de, ate,
        valor: soma(xs), n: xs.length, st: a <= 7 ? "logo" : "aberto", hoje: k === 0,
      });
    }
  }
  return cols;
}

/** Topo "redondo" do eixo Y (1, 2, 2,5 ou 5 × 10^k), nunca abaixo de 1.000. */
export function topoEixo(max: number): number {
  if (!(max > 1000)) return 1000;
  const e = Math.pow(10, Math.floor(Math.log10(max)));
  for (const f of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (f * e >= max) return f * e;
  return 10 * e;
}

/** "5,2k" / "1,3 mi" para o rótulo em cima da barra. */
export function abreviar(v: number): string {
  if (v >= 1e6) return `${(v / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi`;
  if (v >= 1e3) return `${(v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}k`;
  return Math.round(v).toLocaleString("pt-BR");
}

// ── Posição ───────────────────────────────────────────────────────────────
export type Faixa = { valor: number; n: number };
export type Posicao = {
  dias: number;
  vencido: Faixa;        // até ontem
  sem: Faixa;            // hoje a hoje+min(7, N)
  meio: Faixa | null;    // hoje+8 a hoje+N (só quando N > 7)
  periodo: Faixa;        // hoje a hoje+N
  alem: Faixa;           // depois de hoje+N
  semVencimento: Faixa;  // em aberto sem data de vencimento (só no total)
  aPagar: Faixa;
  aReceber: Faixa;
  saldoContas: number | null;       // null = saldos ainda não carregados
  saldoAposPagar: number | null;    // saldo − vencido − período
};

const fx = (xs: Lanc[]): Faixa => ({ valor: soma(xs), n: xs.length });

export function posicao(regs: Lanc[], hoje: string, dias: number, saldoContas: number | null): Posicao {
  const pg = abertasPagar(regs);
  const venc = pg.filter((l) => l.data_vencimento && diasAte(l.data_vencimento, hoje) < 0);
  const periodo = naJanela(pg, hoje, 0, dias);
  const fimSem = Math.min(7, dias);
  return {
    dias,
    vencido: fx(venc),
    sem: fx(naJanela(pg, hoje, 0, fimSem)),
    meio: dias > 7 ? fx(naJanela(pg, hoje, 8, dias)) : null,
    periodo: fx(periodo),
    alem: fx(pg.filter((l) => l.data_vencimento && diasAte(l.data_vencimento, hoje) > dias)),
    semVencimento: fx(pg.filter((l) => !l.data_vencimento)),
    aPagar: fx(pg),
    aReceber: fx(abertasReceber(regs)),
    saldoContas,
    saldoAposPagar: saldoContas == null ? null : r2(saldoContas - soma(venc) - soma(periodo)),
  };
}

/** Filtro de Contas a pagar aberto por cada linha da Posição (vencimento de/até, sempre não pago). */
export function drill(tipo: DrillContas["tipo"], hoje: string, dias: number): DrillContas {
  const fimSem = Math.min(7, dias);
  switch (tipo) {
    case "venc": return { tipo, ate: somaDias(hoje, -1), rotulo: "Vencido, até ontem" };
    case "sem": return { tipo, de: hoje, ate: somaDias(hoje, fimSem), rotulo: `Vence em até ${fimSem} ${fimSem === 1 ? "dia" : "dias"}` };
    case "meio": return { tipo, de: somaDias(hoje, 8), ate: somaDias(hoje, dias), rotulo: `Vence do 8º ao ${dias}º dia` };
    case "ate": return { tipo, de: hoje, ate: somaDias(hoje, dias), rotulo: `Vence em até ${dias} ${dias === 1 ? "dia" : "dias"}` };
    case "alem": return { tipo, de: somaDias(hoje, dias + 1), rotulo: `Vence depois de ${dm(somaDias(hoje, dias))}` };
    case "todas": return { tipo, rotulo: "Todas em aberto" };
  }
}

// ── Textos ────────────────────────────────────────────────────────────────
export const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;

/** "Quarta-feira, 7 de outubro" (fuso local, sem passar por UTC). */
export function dataPorExtenso(hoje: string, comDiaSemana = true): string {
  const [a, m, d] = hoje.split("-").map(Number);
  const s = new Date(a, m - 1, d).toLocaleDateString("pt-BR", comDiaSemana ? { weekday: "long", day: "numeric", month: "long" } : { day: "numeric", month: "long" });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ── O que pede ação ───────────────────────────────────────────────────────
/** A conta vencida mais antiga (empate: a de maior valor). */
export function vencidaMaisAntiga(abertas: Lanc[], hoje: string): Lanc | null {
  const xs = abertas.filter((l) => l.data_vencimento && diasAte(l.data_vencimento, hoje) < 0);
  xs.sort((a, b) => a.data_vencimento!.localeCompare(b.data_vencimento!) || b.valor - a.valor);
  return xs[0] ?? null;
}

/** Tipos de documento de contrato/empreita (pagamento a quem não é CLT; aceita retenção do caixa). */
export const DOCS_CONTRATO = ["Contrato", "Empreitada"];

/** A próxima parcela (de hoje em diante) de contrato ou empreita em aberto. */
export function proximaParcelaContrato(abertas: Lanc[], hoje: string): Lanc | null {
  const xs = abertas.filter((l) => DOCS_CONTRATO.includes(l.tipo_documento || "") && l.data_vencimento && diasAte(l.data_vencimento, hoje) >= 0);
  xs.sort((a, b) => a.data_vencimento!.localeCompare(b.data_vencimento!) || b.valor - a.valor);
  return xs[0] ?? null;
}

/** "Vence hoje" / "Vence em 3 dias" / "Venceu há 2 dias". */
export function quandoVence(iso: string, hoje: string): string {
  const d = diasAte(iso, hoje);
  if (d === 0) return "Vence hoje";
  if (d > 0) return `Vence em ${plural(d, "dia", "dias")}`;
  return `Venceu há ${plural(-d, "dia", "dias")}`;
}

/** Fatura de fornecedor mínima que a fila precisa (FaturaResumo de lib/api.ts). */
export type FaturaMin = {
  id: number; fornecedor: string; rotulo: string; status: "aberta" | "fechada" | "paga";
  data_fechamento_prevista: string | null; data_vencimento: string | null; valor_total: number; notas: number;
};

/** Fatura aberta que fecha em até `janela` dias (ou que já devia ter fechado): a mais próxima. */
export function faturaFechandoEmBreve<F extends FaturaMin>(faturas: F[], hoje: string, janela = 7): F | null {
  const xs = faturas.filter((f) => f.status === "aberta" && f.data_fechamento_prevista && diasAte(f.data_fechamento_prevista, hoje) <= janela);
  xs.sort((a, b) => a.data_fechamento_prevista!.localeCompare(b.data_fechamento_prevista!));
  return xs[0] ?? null;
}

/** Ordem da lista de faturas no painel: em curso primeiro (aberta, fechada), depois pagas; dentro, pela data mais próxima. */
export function ordenarFaturas<F extends FaturaMin>(faturas: F[]): F[] {
  const peso = { aberta: 0, fechada: 1, paga: 2 } as const;
  const data = (f: F) => (f.status === "aberta" ? f.data_fechamento_prevista : f.data_vencimento) || "9999-12-31";
  return [...faturas].sort((a, b) => peso[a.status] - peso[b.status] || (a.status === "paga" ? data(b).localeCompare(data(a)) : data(a).localeCompare(data(b))));
}
