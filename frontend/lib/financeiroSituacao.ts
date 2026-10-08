import type { Lanc } from "@/lib/financeiroTipos";

/** Data de hoje no fuso LOCAL (AAAA-MM-DD). `toISOString()` usa UTC e, depois das 21h em Brasília, já devolve amanhã. */
export function hojeLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Soma `n` dias a uma data AAAA-MM-DD (fuso local). */
export function somaDias(iso: string, n: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const dt = new Date(a, m - 1, d + n);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
}

/** Diferença em dias entre `iso` e hoje (negativo = já passou). */
export function diasAte(iso: string, hoje = hojeLocal()): number {
  const [a, m, d] = iso.split("-").map(Number);
  const [a2, m2, d2] = hoje.split("-").map(Number);
  return Math.round((Date.UTC(a, m - 1, d) - Date.UTC(a2, m2 - 1, d2)) / 86400000);
}

export type SituacaoId = "vencida" | "hoje" | "logo" | "aberto" | "fatura" | "parcial" | "paga" | "agendada";
export type Situacao = { id: SituacaoId; classe: "venc" | "logo" | "aberto" | "fat" | "pago" | "parc"; rotulo: string };

const plural = (n: number, a: string, b: string) => `${n} ${n === 1 ? a : b}`;
const diaMes = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

/**
 * Pagamento com data futura (regras v2, Fase A PR 6): vira AGENDADO — não sai do
 * saldo de hoje, aparece no Caixa Real na data dele. Devolve a pergunta de
 * confirmação para a tela mostrar antes de enviar a baixa, ou null quando
 * nenhuma data é futura (ou a fazenda ainda usa as regras antigas).
 */
export function perguntaAgendamento(datas: (string | null | undefined)[], regrasV2: boolean, hoje = hojeLocal()): string | null {
  if (!regrasV2) return null;
  const futuras = [...new Set(datas.filter((d): d is string => !!d && d > hoje))].sort();
  if (!futuras.length) return null;
  const quando = futuras.length === 1 ? diaMes(futuras[0]) : `${diaMes(futuras[0])} a ${diaMes(futuras[futuras.length - 1])}`;
  return `Agendar pagamento para ${quando}? Ele só sai do saldo nessa data e aparece no Caixa Real como agendado.`;
}

/** Situação de um lançamento, sempre com texto (o ícone é escolhido pela tela a partir do `id`). */
export function situacaoDe(l: Lanc, hoje = hojeLocal()): Situacao {
  // Regras v2 (Fase A, PR 6): baixa com data FUTURA é agendada — ainda não saiu
  // do saldo de hoje. `data_caixa` só vem do servidor com as regras novas.
  if (l.data_pagamento && l.data_caixa && l.data_caixa > hoje) {
    return { id: "agendada", classe: "aberto", rotulo: `Agendada para ${diaMes(l.data_caixa)}` };
  }
  if (l.data_pagamento) {
    const dm = l.data_pagamento.slice(8, 10) + "/" + l.data_pagamento.slice(5, 7);
    const parcial = l.valor_pago != null && Math.round((l.valor - l.valor_pago) * 100) > 0 && (l.desconto_acrescimo ?? 0) === 0;
    return parcial
      ? { id: "parcial", classe: "parc", rotulo: `Parcial em ${dm}` }
      : { id: "paga", classe: "pago", rotulo: `${l.tipo === "receita" ? "Recebida" : "Paga"} em ${dm}` };
  }
  const venc = l.data_vencimento;
  if (l.fatura_id) return { id: "fatura", classe: "fat", rotulo: "Em fatura" };
  if (!venc) return { id: "aberto", classe: "aberto", rotulo: "Em aberto" };
  const d = diasAte(venc, hoje);
  if (d < 0) return { id: "vencida", classe: "venc", rotulo: `Vencida há ${plural(-d, "dia", "dias")}` };
  if (d === 0) return { id: "hoje", classe: "logo", rotulo: "Vence hoje" };
  if (d <= 7) return { id: "logo", classe: "logo", rotulo: `Vence em ${plural(d, "dia", "dias")}` };
  return { id: "aberto", classe: "aberto", rotulo: `Em aberto · ${d} dias` };
}

export type FaixaId = "venc" | "sem" | "m30" | "m60" | "mais";
export const FAIXAS: { id: FaixaId; nome: string; ok: (d: number) => boolean }[] = [
  { id: "venc", nome: "Vencidas", ok: (d) => d < 0 },
  { id: "sem", nome: "Até 7 dias", ok: (d) => d >= 0 && d <= 7 },
  { id: "m30", nome: "8 a 30 dias", ok: (d) => d > 7 && d <= 30 },
  { id: "m60", nome: "31 a 60 dias", ok: (d) => d > 30 && d <= 60 },
  { id: "mais", nome: "Mais de 60 dias", ok: (d) => d > 60 },
];

/** Faixa de vencimento de um lançamento em aberto (sem vencimento cai em "Mais de 60 dias"). */
export function faixaDe(l: Lanc, hoje = hojeLocal()): FaixaId {
  if (!l.data_vencimento) return "mais";
  const d = diasAte(l.data_vencimento, hoje);
  return (FAIXAS.find((f) => f.ok(d)) || FAIXAS[4]).id;
}

/** Soma em centavos exatos (evita 0,1 + 0,2). */
export function somaValores(xs: Lanc[]): number {
  return Math.round(xs.reduce((a, l) => a + l.valor, 0) * 100) / 100;
}

/**
 * Valor REALIZADO de um lançamento (regime de caixa): o que de fato saiu/entrou.
 * Em baixa parcial com reparcelamento a parcela mantém `valor` = valor original e o
 * restante vira OUTRA parcela; somar `valor` contaria o restante duas vezes.
 */
export function valorRealizado(l: Pick<Lanc, "valor" | "valor_pago">): number {
  return l.valor_pago ?? l.valor;
}

/** Baixa parcial: pagou menos que o valor e a diferença NÃO virou desconto (virou outra parcela). */
export function ehBaixaParcial(l: Pick<Lanc, "valor" | "valor_pago" | "desconto_acrescimo">): boolean {
  return l.valor_pago != null && Math.round((l.valor - l.valor_pago) * 100) > 0 && Math.round((l.desconto_acrescimo ?? 0) * 100) === 0;
}

/** Valor para o regime de COMPETÊNCIA: a parte paga numa baixa parcial (o restante já é outra parcela). */
export function valorCompetencia(l: Pick<Lanc, "valor" | "valor_pago" | "desconto_acrescimo">): number {
  return ehBaixaParcial(l) ? (l.valor_pago as number) : l.valor;
}
