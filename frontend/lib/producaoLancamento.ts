// Regras de tela de Lançamentos › Produção (Controle leiteiro, Pesagem corporal, Secagem). Funções puras, sem React nem
// chamadas à API — quem grava continua sendo cada formulário (e as props de injeção do app de campo).
// Datas são sempre "AAAA-MM-DD" (calendário local da fazenda, nunca UTC: 22h no curral não pode virar "amanhã").

// ───────────────────────── datas e números ─────────────────────────
export function hojeLocalIso(agora: Date = new Date()): string {
  return `${agora.getFullYear()}-${String(agora.getMonth() + 1).padStart(2, "0")}-${String(agora.getDate()).padStart(2, "0")}`;
}
const utc = (iso: string) => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)));
export function diasEntre(deIso: string, ateIso: string): number {
  return Math.round((utc(ateIso) - utc(deIso)) / 86400000);
}
export function somarDiasIso(iso: string, dias: number): string {
  return new Date(utc(iso) + dias * 86400000).toISOString().slice(0, 10);
}
/** Campo em branco (ou ilegível) = null — nunca 0. */
export function numOuNull(v: string | number | null | undefined): number | null {
  if (v == null) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (v.trim() === "") return null;
  const n = Number(v.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}
/** Texto do erro capturado (`catch (e)` é `unknown`); `padrao` quando não há mensagem. */
export function mensagemDoErro(e: unknown, padrao: string): string {
  return e instanceof Error && e.message ? e.message : padrao;
}
const porNumero = (a: string, b: string) => a.localeCompare(b, "pt-BR", { numeric: true });
/** Agrupa mantendo a ordem dos grupos por nome (numérico: "02 - ..." antes de "10 - ..."). */
export function agruparPorLote<T>(itens: T[], lote: (i: T) => string | null | undefined, semLote = "Sem lote"): [string, T[]][] {
  const m = new Map<string, T[]>();
  for (const i of itens) {
    const k = lote(i) || semLote;
    m.set(k, [...(m.get(k) ?? []), i]);
  }
  return [...m.entries()].sort(([a], [b]) => porNumero(a, b));
}

// ───────────────────────── Controle leiteiro ─────────────────────────
export type AnimalControle = {
  numero: string; grupo_primario?: string | null; del_dias?: number | null; em_lactacao?: boolean;
  producao_kg?: number | null; producao_data?: string | null; producao_origem?: "controle" | "congelado" | null;
};

/**
 * Quem está em lactação — FONTE ÚNICA: a flag `em_lactacao` da API de animais (Lactacao aberta hoje), a mesma que o
 * servidor usa para aceitar ou recusar o lançamento. `undefined` (front novo contra backend antigo, ou cache do app
 * de campo) cai no critério antigo: lote de lactação OU DEL > 0.
 */
export function vacaEmLactacao(a: AnimalControle, lotesLact: string[]): boolean {
  if (a.em_lactacao !== undefined) return a.em_lactacao;
  return (!!a.grupo_primario && lotesLact.includes(a.grupo_primario)) || ((a.del_dias ?? 0) > 0);
}
/** Por lote entram só as `em_lactacao !== false`: o servidor recusa o lote INTEIRO se uma entrada não tiver lactação aberta. */
export function vacasDoLoteParaControle<T extends AnimalControle>(animais: T[], lotes: string[]): { vacas: T[]; foraDaLactacao: number } {
  const doLote = animais.filter((a) => !!a.grupo_primario && lotes.includes(a.grupo_primario));
  const vacas = doLote.filter((a) => a.em_lactacao !== false);
  return { vacas, foraDaLactacao: doLote.length - vacas.length };
}

/** Ordenha em branco vira `null` (não lançada), nunca `0`: um 0 gravado puxaria a média da ordenha para baixo. */
export function ordenhasParaEnvio(valores: string[] | undefined, nOrd: number): (number | null)[] {
  return Array.from({ length: nOrd }, (_, i) => numOuNull((valores ?? [])[i]));
}
/** Total do dia da vaca; `null` quando nenhuma ordenha foi preenchida. */
export function totalDaVaca(valores: string[] | undefined, nOrd: number): number | null {
  const vs = ordenhasParaEnvio(valores, nOrd).filter((x): x is number => x !== null);
  return vs.length ? vs.reduce((s, x) => s + x, 0) : null;
}
/** Só vai a vaca com pelo menos 1 ordenha preenchida. */
export function montarEntradasControle(numeros: string[], valores: Record<string, string[]>, nOrd: number) {
  return numeros
    .map((numero) => ({ numero_matriz: numero, ordenhas: ordenhasParaEnvio(valores[numero], nOrd) }))
    .filter((e) => e.ordenhas.some((v) => v !== null));
}

export const LIMITE_VARIACAO_CONFERIR_PCT = 25;
/**
 * Variação do total do dia sobre o último controle da vaca. `conferir` (≥ 25%) pega erro de digitação (112 em vez de 11,2;
 * ordenha esquecida). `null` quando não há base de comparação confiável: sem último controle, ou o dado é o campo
 * congelado do Ideagri (não anda mais), ou o "último" já é desta data ou posterior (o servidor substituiria esse registro).
 */
export function variacaoControle(
  total: number | null, a: Pick<AnimalControle, "producao_kg" | "producao_data" | "producao_origem">, dataControle: string,
): { pct: number; conferir: boolean } | null {
  if (total === null || !a.producao_kg || a.producao_kg <= 0) return null;
  if (a.producao_origem === "congelado") return null;
  if (a.producao_data && a.producao_data >= dataControle) return null;
  const pct = ((total - a.producao_kg) / a.producao_kg) * 100;
  return { pct, conferir: Math.abs(pct) >= LIMITE_VARIACAO_CONFERIR_PCT };
}
/** A vaca já tem controle nesta data (ou depois): lançar de novo SUBSTITUI o registro do dia (upsert no servidor). */
export function jaTemControleNaData(a: Pick<AnimalControle, "producao_data" | "producao_origem">, dataControle: string): boolean {
  return a.producao_origem === "controle" && !!a.producao_data && a.producao_data === dataControle;
}

export type FaixaControle = { vacas: number; ultimoControle: string | null; mediaUltimo: number | null; semControle: number };
/** Faixa do topo: o estado do rebanho antes de lançar. "Sem controle" = nunca teve, é dado do Ideagri ou tem mais de 30 dias. */
export function faixaControle(vacas: AnimalControle[], hoje: string, limiteDias = 30): FaixaControle {
  const datas = vacas.filter((v) => v.producao_origem === "controle" && v.producao_data).map((v) => v.producao_data as string);
  const ultimo = datas.length ? datas.reduce((a, b) => (a > b ? a : b)) : null;
  const doUltimo = ultimo ? vacas.filter((v) => v.producao_origem === "controle" && v.producao_data === ultimo && (v.producao_kg ?? 0) > 0) : [];
  const media = doUltimo.length ? doUltimo.reduce((s, v) => s + (v.producao_kg ?? 0), 0) / doUltimo.length : null;
  const semControle = vacas.filter((v) => {
    if (v.producao_origem !== "controle" || !v.producao_data) return true;
    return diasEntre(v.producao_data, hoje) > limiteDias;
  }).length;
  return { vacas: vacas.length, ultimoControle: ultimo, mediaUltimo: media, semControle };
}

/** Linhas de planilha que o servidor devolveu com erro: contagem + as primeiras `mostrar` mensagens + "e mais N". */
export function resumoErros(erros: string[], mostrar: number): { primeiras: string[]; resto: number } {
  return { primeiras: erros.slice(0, mostrar), resto: Math.max(0, erros.length - mostrar) };
}

// ───────────────────────── Pesagem corporal ─────────────────────────
/** Só vai peso maior que 0; em branco ou 0 não é lançado. */
export function pesoValido(v: string | undefined): number | null {
  const n = numOuNull(v);
  return n !== null && n > 0 ? n : null;
}
export type UltimaPesagem = { ultima_data: string; ultima_peso: number };
export type SobreAnterior = {
  novo: number | null; ganho: number | null; gmd: number | null; dias: number | null;
  /** O "último peso" é desta data ou posterior: lançar SUBSTITUI o do dia (ou é retroativo) — não dá ganho nem GMD. */
  jaPesada: boolean; primeira: boolean;
};
/** Ganho e GMD (kg/dia) sobre a pesagem anterior do próprio animal, na hora em que o peso é digitado. */
export function sobreAnterior(novo: number | null, ant: UltimaPesagem | null | undefined, dataPesagem: string): SobreAnterior {
  if (!ant) return { novo, ganho: null, gmd: null, dias: null, jaPesada: false, primeira: novo !== null };
  const dias = diasEntre(ant.ultima_data, dataPesagem);
  if (dias <= 0) return { novo, ganho: null, gmd: null, dias, jaPesada: true, primeira: false };
  if (novo === null) return { novo, ganho: null, gmd: null, dias, jaPesada: false, primeira: false };
  const ganho = novo - ant.ultima_peso;
  return { novo, ganho, gmd: ganho / dias, dias, jaPesada: false, primeira: false };
}
export function montarEntradasPesagem(numeros: string[], pesos: Record<string, string>) {
  return numeros
    .map((numero_matriz) => ({ numero_matriz, peso_kg: pesoValido(pesos[numero_matriz]) }))
    .filter((e): e is { numero_matriz: string; peso_kg: number } => e.peso_kg !== null);
}
export type LinhaGmd = { numero_matriz: string; ultima_data: string; gmd_kg_dia: number | null };
export type FaixaPesagem = { animais: number; ultimaPesagem: string | null; gmdMedio: number | null; semPesar: number };
/** `semPesar` conta quem JÁ tem pesagem e está há mais de `limiteDias` sem pesar (quem nunca foi pesado não entra: seria o rebanho todo). */
export function faixaPesagem(totalAnimais: number, linhas: LinhaGmd[], hoje: string, limiteDias = 60): FaixaPesagem {
  const ultima = linhas.length ? linhas.map((l) => l.ultima_data).reduce((a, b) => (a > b ? a : b)) : null;
  const gmds = linhas.map((l) => l.gmd_kg_dia).filter((x): x is number => x !== null);
  return {
    animais: totalAnimais, ultimaPesagem: ultima,
    gmdMedio: gmds.length ? gmds.reduce((s, x) => s + x, 0) / gmds.length : null,
    semPesar: linhas.filter((l) => diasEntre(l.ultima_data, hoje) > limiteDias).length,
  };
}

// ───────────────────────── Secagem ─────────────────────────
export type SituacaoSecagem = { tom: "ok" | "atencao" | "info" | "neutro"; texto: string; titulo?: string };
/** Selo da coluna "Situação": quanto falta para a data prevista. "Atrasada" e "sem prenhez" informam, não impedem. */
export function situacaoSecagem(diasParaSecagem: number | null | undefined, deveSecar?: boolean | null): SituacaoSecagem {
  if (diasParaSecagem == null) return { tom: "info", texto: "Sem prenhez confirmada", titulo: "Sem data de parto não dá para calcular a secagem" };
  if (deveSecar === false) return { tom: "neutro", texto: "Não precisa secar" };
  if (diasParaSecagem < 0) return { tom: "atencao", texto: `Atrasada ${-diasParaSecagem} d` };
  if (diasParaSecagem === 0) return { tom: "ok", texto: "Hoje" };
  if (diasParaSecagem <= 7) return { tom: "ok", texto: `Em ${diasParaSecagem} d` };
  return { tom: "neutro", texto: `Em ${diasParaSecagem} d` };
}
export type FiltroSecagem = "proximas" | "atrasadas" | "todas";
export const LIMITE_PROXIMAS_DIAS = 30;
export function passaFiltroSecagem(f: FiltroSecagem, diasParaSecagem: number | null | undefined): boolean {
  if (f === "todas") return true;
  if (diasParaSecagem == null) return false;
  return f === "atrasadas" ? diasParaSecagem < 0 : diasParaSecagem <= LIMITE_PROXIMAS_DIAS;
}

export type ItemProdutoSecagem = { produto: string; via: string; quantidade: string; unidade: string };
export type ModoDosagem = "por_vaca" | "total";
/**
 * Produtos que vão no payload. `modoDosagem[idx]` usa o ÍNDICE ORIGINAL (não o do array filtrado). "Total" divide pelo nº
 * de vacas antes de enviar (só faz diferença com mais de uma vaca marcada).
 */
export function produtosParaEnvio(itens: ItemProdutoSecagem[], modoDosagem: Record<number, ModoDosagem>, nVacas: number) {
  return itens
    .map((i, idx) => ({ ...i, idx }))
    .filter((i) => i.produto && Number(i.quantidade) > 0 && i.unidade)
    .map((i) => ({
      produto: i.produto, via: i.via || undefined,
      quantidade: modoDosagem[i.idx] === "total" && nVacas > 1 ? Number(i.quantidade) / nVacas : Number(i.quantidade),
      unidade: i.unidade,
    }));
}
/** Total que sai do estoque na aplicação inteira (todas as vacas). */
export function totalAplicado(quantidade: number, modo: ModoDosagem | undefined, nVacas: number): number {
  return modo === "total" && nVacas > 1 ? quantidade : quantidade * Math.max(1, nVacas);
}
/** Data futura nunca baixa estoque: o produto é programado na Agenda. */
export function aplicadoEfetivo(aplicado: boolean, dataSecagem: string, hoje: string): boolean {
  return aplicado && dataSecagem <= hoje;
}
/** Mensagem do que falta para salvar (null = pode salvar). Mesmas travas do formulário antigo. */
export function erroDeSecagem(d: { nVacas: number; motivo: string; vacinaSim: boolean; vacinas: string[]; ecc?: string }): string | null {
  if (d.nVacas === 0) return "Selecione ao menos uma vaca (ou lote).";
  if (!d.motivo) return "Selecione o motivo da secagem.";
  const ecc = numOuNull(d.ecc);
  if (ecc !== null && (ecc < 1 || ecc > 5)) return "O escore de condição corporal vai de 1 a 5 (ou deixe em branco).";
  if (d.vacinaSim && d.vacinas.length === 0) return 'Marque ao menos uma vacina pré-parto, ou volte para "Não".';
  return null;
}
