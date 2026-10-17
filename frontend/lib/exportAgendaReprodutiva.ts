// Monta o que a exportação da Agenda Reprodutiva entrega — PDF (A4 paisagem, colunas enxutas) e Excel (todas as colunas,
// uma aba por lista) — a partir dos cards configurados e das listas de "Outras pendências". Função pura: só dados em
// entrada e seções em saída; quem desenha o arquivo é lib/export.ts (gerarFichaPDFBlob / gerarMultiExcelBlob).
import type { ColunaExport, OpcoesFichaPDF, OpcoesMultiExcel, SecaoFicha } from "./export.ts";
import type { ItemCardAgendaReprodutiva, SituacaoCard } from "./api.ts";
import { ROTULO_FASE, ROTULO_FASE_PLURAL, contarPorFase, filtrarPorFases, ordenarNoPrazoPrimeiro, regraDoPrazo, textoFaltam, type FaseToque } from "./fasesToque.ts";

export type ParametrosPrazo = { dias_toque: number; dias_reconfirmacao: number };

export type ListaCard = { id: string; titulo: string; situacao: SituacaoCard; itens: ItemCardAgendaReprodutiva[] };
/** Lista de "Outras pendências" (vazias por diagnóstico, pendentes…): já vem montada, em duas versões de colunas. */
export type ListaOutra = { id: string; titulo: string; total: number; pdf: SecaoFicha; excel: SecaoFicha };

export type EntradaExportacao = {
  cards: ListaCard[];
  outras: ListaOutra[];
  /** ids das listas marcadas no pop-up (cards e outras). */
  selecionadas: ReadonlySet<string>;
  /** Filtro de situação que está na tela e se o arquivo deve respeitá-lo. */
  fases: ReadonlySet<FaseToque>;
  aplicarFiltro: boolean;
  parametros: ParametrosPrazo | null;
  dataReferencia: string;
  projetado: boolean;
  proximaVisita: string | null;
  geradoEm: string;
};

export type LinhaDoModal = { id: string; titulo: string; grupo: "card" | "outra"; total: number; n: number; semAnimais: boolean; nota: string };

const comExames = (s: SituacaoCard) => s === "inseminada" || s === "gestante";

export function fmtData(iso: string | null | undefined): string {
  if (!iso) return "";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return d && m && a ? `${d}/${m}/${a}` : iso;
}

function letra(diag: string | null | undefined): string {
  const d = (diag ?? "").trim().toUpperCase();
  return d === "POSITIVO" ? "P" : d === "NEGATIVO" ? "V" : d === "INDEFINIDO" ? "I" : "";
}

/** "15/10/2026 · I", ou "–" quando ainda não houve exame. */
export function fmtExame(data: string | null | undefined, diag: string | null | undefined): string {
  const l = letra(diag);
  if (!data && !l) return "–";
  return [data ? fmtData(data) : "", l].filter(Boolean).join(" · ");
}

const filtroValeParaCards = (e: Pick<EntradaExportacao, "fases" | "aplicarFiltro">) => e.aplicarFiltro && e.fases.size > 0;

/** Itens de um card como saem no arquivo: com o filtro (se for para aplicar) e os que estão no prazo primeiro. */
export function itensDoCard(lista: ListaCard, e: Pick<EntradaExportacao, "fases" | "aplicarFiltro">): ItemCardAgendaReprodutiva[] {
  const base = filtroValeParaCards(e) ? filtrarPorFases(lista.itens, e.fases) : lista.itens;
  return ordenarNoPrazoPrimeiro(base);
}

/** O que o pop-up mostra por lista: total, quantos entram no arquivo com a escolha atual e se dá para marcar. */
export function linhasDoModal(e: Pick<EntradaExportacao, "cards" | "outras" | "fases" | "aplicarFiltro">): LinhaDoModal[] {
  const filtrando = filtroValeParaCards(e);
  const cards = e.cards.map((c) => {
    const n = itensDoCard(c, e).length;
    return { id: c.id, titulo: c.titulo, grupo: "card" as const, total: c.itens.length, n, semAnimais: n === 0,
      nota: n === 0 ? (filtrando ? "sem animais nesta situação" : "lista vazia") : (filtrando ? `de ${c.itens.length} na lista` : "todos os animais") };
  });
  const outras = e.outras.map((o) => {
    const n = filtrando ? 0 : o.total;
    return { id: o.id, titulo: o.titulo, grupo: "outra" as const, total: o.total, n, semAnimais: n === 0,
      nota: n === 0 ? (filtrando ? "não tem a tocar nem reconfirmar" : "lista vazia") : "todos os animais" };
  });
  return [...cards, ...outras];
}

const NOME_FASE = (f: FaseToque | null | undefined) => (f ? ROTULO_FASE[f] : "");

function situacaoTexto(it: ItemCardAgendaReprodutiva): string {
  const base = NOME_FASE(it.fase);
  if (!it.ainda_nao) return base;
  const faltam = textoFaltam(it.dias_para_prazo);
  return `${base} · AINDA NÃO${faltam ? `, ${faltam}` : ""}`;
}

function linhaDoCard(it: ItemCardAgendaReprodutiva): Record<string, unknown> {
  const reconfirmado = !!it.data_reconfirmacao || !!it.diagnostico_reconfirmacao;
  return {
    numero_matriz: it.numero_matriz, categoria: it.categoria ?? "", lote_atual: it.lote_atual ?? "", estado: it.estado ?? "",
    del_dias: it.del_dias ?? "", dias_desde_servico: it.dias_desde_servico ?? "", dias_gestacao: it.dias_gestacao ?? "",
    parto_previsto: fmtData(it.parto_previsto), data_servico: fmtData(it.data_servico),
    toque_fmt: fmtExame(it.data_diagnostico, it.diagnostico), retoque_fmt: reconfirmado ? fmtExame(it.data_reconfirmacao, it.diagnostico_reconfirmacao) : "–",
    situacao_fmt: situacaoTexto(it),
    diagnostico: it.diagnostico ?? "", data_diagnostico: fmtData(it.data_diagnostico),
    diagnostico_reconfirmacao: it.diagnostico_reconfirmacao ?? "", data_reconfirmacao: fmtData(it.data_reconfirmacao),
    retoque_marcado: it.retoque == null ? "" : it.retoque, fase: NOME_FASE(it.fase), ainda_nao: !!it.ainda_nao,
    dias_para_prazo: it.dias_para_prazo ?? "", prazo_tipo: it.prazo_tipo === "reconfirmacao" ? "Reconfirmação" : it.prazo_tipo === "toque" ? "Toque" : "",
    __ainda: !!it.ainda_nao,
  };
}

/** PDF: poucas colunas, com largura em mm — cabe em A4 paisagem sem espremer ninguém. */
export function colunasPdfDoCard(situacao: SituacaoCard): ColunaExport[] {
  const base: ColunaExport[] = [
    { header: "Matriz", key: "numero_matriz", larguraPdf: 16 }, { header: "Categoria", key: "categoria", larguraPdf: 22 },
    { header: "Lote", key: "lote_atual" }, { header: "DEL", key: "del_dias", larguraPdf: 13 },
  ];
  if (!comExames(situacao)) return base;
  const exames: ColunaExport[] = [
    { header: "Toque / confirmação", key: "toque_fmt", larguraPdf: 34 },
    { header: "Retoque / reconfirmação", key: "retoque_fmt", larguraPdf: 38 },
    { header: "Situação", key: "situacao_fmt", larguraPdf: 60 },
  ];
  return [...base, { header: "Dias da IA", key: "dias_desde_servico", larguraPdf: 17 },
    ...(situacao === "gestante" ? [{ header: "D. gest.", key: "dias_gestacao", larguraPdf: 16 }, { header: "Parto prev.", key: "parto_previsto", larguraPdf: 24 }] : []),
    ...exames];
}

/** Excel: todas as colunas, números como número (ordenam e somam). */
export function colunasExcelDoCard(): ColunaExport[] {
  return [
    { header: "Matriz", key: "numero_matriz", width: 10 }, { header: "Categoria", key: "categoria", width: 12 },
    { header: "Lote", key: "lote_atual", width: 24 }, { header: "Estado", key: "estado", width: 13 },
    { header: "DEL", key: "del_dias", width: 8, numerico: true }, { header: "Dias da IA", key: "dias_desde_servico", width: 11, numerico: true },
    { header: "Dias de gestação", key: "dias_gestacao", width: 15, numerico: true }, { header: "Parto previsto", key: "parto_previsto", width: 14 },
    { header: "Data do serviço", key: "data_servico", width: 15 },
    { header: "Resultado do toque", key: "diagnostico", width: 18 }, { header: "Data do toque", key: "data_diagnostico", width: 14 },
    { header: "Resultado da reconfirmação", key: "diagnostico_reconfirmacao", width: 24 }, { header: "Data da reconfirmação", key: "data_reconfirmacao", width: 20 },
    { header: "Marcado para retoque", key: "retoque_marcado", width: 19 },
    { header: "Situação", key: "fase", width: 15 }, { header: "AINDA NÃO", key: "ainda_nao", width: 11 },
    { header: "Dias que faltam", key: "dias_para_prazo", width: 14, numerico: true }, { header: "Prazo de", key: "prazo_tipo", width: 14 },
  ];
}


export function descreverFiltro(fases: ReadonlySet<FaseToque>, aplicar: boolean): string {
  if (!aplicar || fases.size === 0) return "sem filtro (todos os animais das listas)";
  return [...fases].map((f) => ROTULO_FASE_PLURAL[f]).join(" + ");
}

export type SaidaExportacao = {
  pdf: { titulo: string; subtitulo: string; secoes: SecaoFicha[]; opcoes: OpcoesFichaPDF };
  excel: { titulo: string; secoes: SecaoFicha[]; opcoes: OpcoesMultiExcel };
  totais: { listas: number; animais: number; porFase: Record<FaseToque, number>; aindaNao: number };
};

export function montarExportacao(e: EntradaExportacao): SaidaExportacao {
  const secoesPdf: SecaoFicha[] = [];
  const secoesExcel: SecaoFicha[] = [];
  const itensIncluidos: Record<string, ItemCardAgendaReprodutiva[]> = {};
  let animais = 0;
  let listas = 0;
  const unicos = new Set<string>();

  for (const c of e.cards) {
    if (!e.selecionadas.has(c.id)) continue;
    const itens = itensDoCard(c, e);
    if (itens.length === 0) continue;
    listas += 1;
    itensIncluidos[c.id] = itens;
    itens.forEach((it) => unicos.add(it.numero_matriz));
    animais += itens.length;
    const linhas = itens.map(linhaDoCard);
    const destacar = (l: Record<string, unknown>) => l.__ainda === true;
    secoesPdf.push({ titulo: `${c.titulo} — ${itens.length} ${itens.length === 1 ? "animal" : "animais"}`, colunas: colunasPdfDoCard(c.situacao), linhas, destacar });
    secoesExcel.push({ titulo: c.titulo, colunas: colunasExcelDoCard(), linhas, destacar });
  }
  if (!filtroValeParaCards(e)) {
    for (const o of e.outras) {
      if (!e.selecionadas.has(o.id) || o.total === 0) continue;
      listas += 1;
      animais += o.total;
      secoesPdf.push(o.pdf);
      secoesExcel.push(o.excel);
    }
  }

  const porFase = contarPorFase(itensIncluidos);
  const aindaNao = Object.values(itensIncluidos).flat().filter((it) => it.ainda_nao).reduce((s, it) => s.add(it.numero_matriz), new Set<string>()).size;
  const filtro = descreverFiltro(e.fases, e.aplicarFiltro);
  const subtitulo = [
    `Data de referência: ${fmtData(e.dataReferencia)} (${e.projetado ? "cenário projetado" : "data atual"})`,
    `Filtro: ${filtro}`,
    e.proximaVisita ? `Próxima visita reprodutiva: ${fmtData(e.proximaVisita)}` : null,
  ].filter(Boolean).join(" · ");

  const legenda = [
    "P = prenha · V = vazia · I = indefinida · – = ainda não houve. Linha em dourado = AINDA NÃO: o animal ainda está dentro do prazo.",
    `Prazo: ${regraDoPrazo(e.parametros)}. O AINDA NÃO só informa; não impede o lançamento.`,
  ];
  const noPrazo = (n: number) => `${n} ainda no prazo de espera`;
  return {
    pdf: {
      titulo: "Agenda Reprodutiva", subtitulo, secoes: secoesPdf,
      opcoes: {
        orientacao: "landscape",
        resumo: [
          { rotulo: "A tocar", valor: String(porFase.a_tocar), detalhe: porFase.a_tocar ? noPrazo(Object.values(itensIncluidos).flat().filter((i) => i.fase === "a_tocar" && i.ainda_nao).reduce((s, i) => s.add(i.numero_matriz), new Set<string>()).size) : undefined },
          { rotulo: "A reconfirmar", valor: String(porFase.a_reconfirmar) },
          { rotulo: "Reconfirmadas", valor: String(porFase.reconfirmada) },
          { rotulo: "Neste arquivo", valor: `${listas} ${listas === 1 ? "lista" : "listas"}`, detalhe: `${animais} ${animais === 1 ? "animal" : "animais"}` },
        ],
        legenda,
        rodape: `CowData · Agenda Reprodutiva · gerado em ${e.geradoEm}`,
      },
    },
    excel: { titulo: "Agenda Reprodutiva", secoes: secoesExcel, opcoes: { subtitulo: `Filtro: ${filtro} · Referência ${fmtData(e.dataReferencia)}`, congelarCabecalho: true, autofiltro: true, legenda } },
    totais: { listas, animais, porFase, aindaNao },
  };
}
