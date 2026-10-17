// Regras de tela do lançamento de diagnóstico de gestação (site e app): que resultado cada situação aceita, quando o
// método "Cio de repasse" existe, como agrupar/ordenar/selecionar os animais. Funções puras; quem decide a fase e o
// prazo AINDA NÃO é o backend (rules/fase_toque.py) e quem grava é POST /reproducao/diagnostico.
import { ordenarNoPrazoPrimeiro, type FaseToque, type ItemComFase } from "./fasesToque.ts";

export type ResultadoDiagnostico = "retoque" | "reconfirmada" | "negativo" | "indefinido" | "aborto";
export type OrigemSelecao = "animais" | "lotes" | "agenda";

export type OpcaoResultado = { valor: ResultadoDiagnostico; nome: string; dica: string };

const ABORTO: OpcaoResultado = {
  valor: "aborto", nome: "Aborto", dica: "registra a perda; o motivo fica como pendência na Agenda",
};

/** O que cada situação pode receber — nada além disto aparece na tela. */
export const RESULTADOS_POR_SITUACAO: Record<FaseToque, OpcaoResultado[]> = {
  a_tocar: [
    { valor: "retoque", nome: "Positivo — para retoque", dica: "prenha; volta na agenda para reconfirmar" },
    { valor: "reconfirmada", nome: "Positivo — reconfirmada", dica: "prenhez confirmada, sem retoque" },
    { valor: "negativo", nome: "Negativo", dica: "vira vazia e segue para nova inseminação" },
    { valor: "indefinido", nome: "Indefinido", dica: "inconclusivo; continua em “a tocar”" },
  ],
  a_reconfirmar: [
    { valor: "reconfirmada", nome: "Positivo — reconfirmada", dica: "prenhez confirmada" },
    { valor: "negativo", nome: "Negativo", dica: "vira vazia e segue para nova inseminação" },
    { valor: "indefinido", nome: "Indefinido", dica: "inconclusivo; o animal volta para novo exame" },
    ABORTO,
  ],
  reconfirmada: [ABORTO],
};

export const NOTA_SITUACAO: Record<FaseToque, (p: { dias_toque: number; dias_reconfirmacao: number } | null) => string> = {
  a_tocar: (p) =>
    `Inseminadas ainda sem diagnóstico, inclusive as de toque indefinido. As que ainda não completaram os Dias para toque${p ? ` (${p.dias_toque}, em Parâmetros)` : ""} ficam no fim, com o selo dourado.`,
  a_reconfirmar: (p) =>
    `Toque positivo marcado “Positivo — para retoque”, ainda sem reconfirmação. O prazo vem de Dias para reconfirmação${p ? ` (${p.dias_reconfirmacao}, em Parâmetros)` : ""}.`,
  reconfirmada: () => "Prenhez já reconfirmada. Aqui só dá para lançar aborto.",
};

export const NOTA_RESULTADO: Record<ResultadoDiagnostico, string> = {
  retoque: "Os animais entram na agenda para retoque, no dia da próxima visita reprodutiva.",
  reconfirmada: "Prenhez confirmada; o animal sai das listas “a tocar” e “a reconfirmar”.",
  negativo: "Ao salvar, os animais ficam vazios e você poderá lançar a inseminação deles em seguida.",
  indefinido: "Resultado inconclusivo: o animal não vira vazio e segue para nova avaliação.",
  aborto: "Grava aborto/perda de prenhez na data do diagnóstico. O motivo (aborto, natimorto, outros) é pedido depois, na Agenda.",
};

/** Aborto não se examina (a data é a do diagnóstico), e a tela de reconfirmadas só aceita aborto: sem método. */
export function pedeMetodo(situacao: FaseToque, resultado: ResultadoDiagnostico | ""): boolean {
  return situacao !== "reconfirmada" && resultado !== "aborto";
}

/** "Cio de repasse" só existe em fazenda que usa adesivo (Parâmetros) e só para o resultado Negativo: a vaca voltou ao
 * cio com o adesivo pintado, ninguém a examinou. Nenhum outro critério. */
export function metodosDisponiveis(usaAdesivo: boolean, resultado: ResultadoDiagnostico | ""): string[] {
  return ["Palpação", "Ultrassom", ...(usaAdesivo && resultado === "negativo" ? ["Cio de repasse"] : [])];
}

export type ItemDiagnostico = ItemComFase & { lote_atual?: string | null };

export function loteDe(item: { lote_atual?: string | null }): string {
  return (item.lote_atual ?? "").trim() || "Sem lote";
}

/** Só os itens que casam com a origem: Animais = todos; Lotes = os lotes marcados; Agenda = quem está nos cards marcados. */
export function filtrarPorOrigem<T extends ItemDiagnostico>(
  itens: T[], origem: OrigemSelecao, lotes: ReadonlySet<string>, numerosDaAgenda: ReadonlySet<string>,
): T[] {
  if (origem === "lotes") return itens.filter((i) => lotes.has(loteDe(i)));
  if (origem === "agenda") return itens.filter((i) => numerosDaAgenda.has(i.numero_matriz));
  return itens;
}

/** Busca por número do animal ou nome do lote (sem acento, sem caixa). */
export function buscarItens<T extends ItemDiagnostico>(itens: T[], texto: string): T[] {
  const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  const q = norm(texto);
  if (!q) return itens;
  return itens.filter((i) => norm(i.numero_matriz).includes(q) || norm(loteDe(i)).includes(q));
}

/** Lotes em ordem do código ("01 - …" antes de "13 - …"); dentro do lote, no prazo primeiro e os AINDA NÃO do mais
 * perto para o mais longe, depois o número do animal. */
export function agruparPorLote<T extends ItemDiagnostico>(itens: T[]): { lote: string; itens: T[] }[] {
  const mapa = new Map<string, T[]>();
  for (const i of itens) {
    const l = loteDe(i);
    mapa.set(l, [...(mapa.get(l) ?? []), i]);
  }
  const numerico = (a: string, b: string) => a.localeCompare(b, "pt-BR", { numeric: true });
  return [...mapa.entries()]
    .sort(([a], [b]) => numerico(a, b))
    .map(([lote, lista]) => ({
      lote,
      itens: ordenarNoPrazoPrimeiro([...lista].sort((x, y) => numerico(x.numero_matriz, y.numero_matriz))),
    }));
}

/** Marcação inicial. Em Animais cada um se escolhe (nenhum marcado); em Lotes e Agenda vêm marcados os que estão no
 * prazo — os AINDA NÃO só entram marcando um a um. Em "reconfirmadas" só cabe aborto, exceção que nunca se marca em
 * bloco: nada vem marcado. */
export function selecaoPadrao(itens: ItemDiagnostico[], origem: OrigemSelecao, situacao: FaseToque): Set<string> {
  if (origem === "animais" || situacao === "reconfirmada") return new Set();
  return new Set(itens.filter((i) => !i.ainda_nao).map((i) => i.numero_matriz));
}

export function todasNoPrazoMarcadas(itens: ItemDiagnostico[], sel: ReadonlySet<string>): boolean {
  const noPrazo = itens.filter((i) => !i.ainda_nao);
  return noPrazo.length > 0 && noPrazo.every((i) => sel.has(i.numero_matriz));
}

/** "Selecionar todas" marca só as que estão no prazo; se já estão todas, desmarca essas (e só essas). */
export function alternarTodasNoPrazo(itens: ItemDiagnostico[], sel: ReadonlySet<string>): Set<string> {
  const novo = new Set(sel);
  const marcar = !todasNoPrazoMarcadas(itens, sel);
  for (const i of itens) {
    if (i.ainda_nao) continue;
    if (marcar) novo.add(i.numero_matriz); else novo.delete(i.numero_matriz);
  }
  return novo;
}

/** Quantos dos marcados estão em prazo de espera (AINDA NÃO) — só para avisar, nunca para bloquear. */
export function resumoSelecao(itens: ItemDiagnostico[], sel: ReadonlySet<string>): { marcados: ItemDiagnostico[]; ainda: number } {
  const marcados = itens.filter((i) => sel.has(i.numero_matriz));
  return { marcados, ainda: marcados.filter((i) => i.ainda_nao).length };
}

export function avisoAindaNao(n: number): string {
  if (n <= 0) return "";
  return `${n} ${n === 1 ? "animal marcado ainda está" : "animais marcados ainda estão"} dentro do prazo (AINDA NÃO). O lançamento é permitido; confira antes de salvar.`;
}

export type FalhaDeSalvamento = { numero: string; motivo: string };

/** Frase do resultado de um lote de lançamentos, com o que salvou e o que falhou. */
export function mensagemResultado(salvos: number, falhas: FalhaDeSalvamento[], rotulo: string): { ok: string | null; erro: string | null } {
  const ok = salvos ? `${rotulo} salvo para ${salvos} ${salvos === 1 ? "animal" : "animais"}.` : null;
  if (!falhas.length) return { ok, erro: null };
  const lista = falhas.map((f) => `${f.numero} (${f.motivo})`).join("; ");
  return { ok, erro: `Não salvou ${falhas.length === 1 ? "1 animal" : `${falhas.length} animais`}: ${lista}. Eles continuam marcados para tentar de novo.` };
}
