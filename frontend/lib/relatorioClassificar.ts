// Relatórios › Resultado › Classificar: o modelo da tela. PURO (só import de tipo) —
// testes em relatorioClassificar.test.ts. Os números e as pendências vêm do servidor
// (GET /financeiro/classificacao/pendencias); aqui só se agrupa, se filtra, se monta o
// lote de ações a partir da seleção e se escolhe a frase.
import type {
  AcaoClassificacao, FilaClassificacao, GrupoConta, LinhaPendencia, MotivoClassificacao, ResultadoLote, ResultadoReversao, TipoAcao,
  UltimoLote,
} from "@/lib/classificacaoApi";

export type Trecho = { t: string; b?: boolean };

/** Ordem de exibição (a mesma do servidor). */
export const MOTIVOS: MotivoClassificacao[] = [
  "conta_sem_linha_dre", "sem_codigo_conta", "item_sem_conta_automatica", "natureza_nao_informada",
];

/** Que ação resolve cada motivo (o controle que a tela mostra quando o motivo está aberto). */
export const ACAO_DO_MOTIVO: Record<MotivoClassificacao, TipoAcao> = {
  conta_sem_linha_dre: "linha_dre", sem_codigo_conta: "conta", item_sem_conta_automatica: "conta", natureza_nao_informada: "natureza",
};

/** Motivos em que a ação é da CONTA (vale para todos os lançamentos dela): a tabela agrupa por conta. */
export const MOTIVOS_POR_CONTA = new Set<MotivoClassificacao>(["conta_sem_linha_dre", "natureza_nao_informada"]);

export const ROTULO_MOTIVO: Record<MotivoClassificacao, string> = {
  conta_sem_linha_dre: "Conta sem linha da DRE",
  sem_codigo_conta: "Lançamento sem conta",
  item_sem_conta_automatica: "Folha e contratos sem conta",
  natureza_nao_informada: "Fora da DRE sem motivo",
};

/** As 9 linhas atribuíveis da DRE + a saída consciente (espelho de ESPECIFICACAO_LINHAS, backend/fazenda/rules/dre.py). */
export const LINHAS_DRE: { valor: string; rotulo: string }[] = [
  { valor: "RECEITA_VENDAS", rotulo: "Receita de vendas" },
  { valor: "DEDUCAO_IMPOSTOS", rotulo: "Deduções de impostos" },
  { valor: "CUSTO_VARIAVEL", rotulo: "Custo variável (CPV/CMV)" },
  { valor: "DESPESA_VARIAVEL", rotulo: "Despesas variáveis" },
  { valor: "GASTOS_PESSOAL", rotulo: "Gastos com pessoal" },
  { valor: "DESPESAS_OPERACIONAIS", rotulo: "Despesas operacionais" },
  { valor: "DEPRECIACAO_AMORT_EXAUSTAO", rotulo: "Depreciação, amortização e exaustão" },
  { valor: "OUTRAS_REC_DESP", rotulo: "Outras receitas e despesas" },
  { valor: "TRIBUTOS_IR_CSLL", rotulo: "Tributos (IRPJ e CSLL)" },
  { valor: "NAO_ENTRA_NA_DRE", rotulo: "Não entra na DRE (principal de financiamento, transferência, aporte)" },
];

const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;
const sem = (s: string | null | undefined) =>
  (s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();

// ── O que a linha aceita ──────────────────────────────────────────────────
/** A ação do motivo da linha está liberada? Se não, por quê (texto do servidor ou um padrão). */
export function podeAplicar(l: LinhaPendencia, tipo: TipoAcao = ACAO_DO_MOTIVO[l.motivo]): { ok: boolean; porque: string | null } {
  if (l.acoes[tipo]) return { ok: true, porque: null };
  const porque = l.travas[tipo]
    ?? (tipo === "linha_dre" ? "Esta conta não pode receber uma linha da DRE aqui." : "Esta ação não está liberada para este lançamento.");
  return { ok: false, porque };
}

// ── Agrupar e filtrar ─────────────────────────────────────────────────────
export type GrupoLinhas = {
  chave: string; codigo: string | null; nome: string | null; noPlano: boolean; linhas: LinhaPendencia[]; quantidade: number;
  totalReceita: number; totalDespesa: number; sugestao: LinhaPendencia["sugestao"];
};

const r2 = (v: number) => Math.round(v * 100) / 100;

/** Motivo da CONTA (linha da DRE, natureza): um bloco por conta, com o total dela. Os outros: um bloco só, sem cabeçalho. */
export function agruparLinhas(linhas: LinhaPendencia[], motivo: MotivoClassificacao): GrupoLinhas[] {
  const grupos = new Map<string, GrupoLinhas>();
  for (const l of linhas) {
    const chave = MOTIVOS_POR_CONTA.has(motivo) ? l.codigo_conta ?? "" : "";
    let g = grupos.get(chave);
    if (!g) {
      g = { chave, codigo: MOTIVOS_POR_CONTA.has(motivo) ? l.codigo_conta : null, nome: l.nome_conta, noPlano: l.conta_no_plano, linhas: [], quantidade: 0, totalReceita: 0, totalDespesa: 0, sugestao: null };
      grupos.set(chave, g);
    }
    g.linhas.push(l);
    g.quantidade++;
    if (l.tipo === "receita") g.totalReceita = r2(g.totalReceita + l.valor); else g.totalDespesa = r2(g.totalDespesa + l.valor);
    if (!g.sugestao && l.sugestao && l.sugestao.tipo !== "conta") g.sugestao = l.sugestao;
  }
  return [...grupos.values()];
}

/** Só as primeiras `max` linhas, na ordem dos grupos (o resto aparece em “Mostrar mais”); o total do grupo continua o inteiro. */
export function limitarGrupos(grupos: GrupoLinhas[], max: number): GrupoLinhas[] {
  const saida: GrupoLinhas[] = [];
  let usadas = 0;
  for (const g of grupos) {
    if (usadas >= max) break;
    const linhas = g.linhas.slice(0, max - usadas);
    usadas += linhas.length;
    saida.push({ ...g, linhas });
  }
  return saida;
}

export function filtrarLinhas(linhas: LinhaPendencia[], f: { q?: string; conta?: string }): LinhaPendencia[] {
  const q = sem(f.q);
  const conta = (f.conta ?? "").trim();
  return linhas.filter((l) => {
    if (conta && !(l.codigo_conta === conta || (l.codigo_conta ?? "").startsWith(`${conta}.`))) return false;
    if (!q) return true;
    return sem([l.fornecedor, l.descricao, l.produto, l.numero_lancamento, l.codigo_conta, l.nome_conta].filter(Boolean).join(" ")).includes(q);
  });
}

/** Receitas e despesas ficam separadas, nunca somadas (a regra da DRE). */
export function totais(linhas: LinhaPendencia[]): { receita: number; despesa: number } {
  let receita = 0, despesa = 0;
  for (const l of linhas) if (l.tipo === "receita") receita += l.valor; else despesa += l.valor;
  return { receita: r2(receita), despesa: r2(despesa) };
}

/** "receita" | "despesa" quando todas as linhas são do mesmo tipo; null se misturam (o seletor de conta precisa de um). */
export function tipoUniforme(linhas: LinhaPendencia[]): "receita" | "despesa" | null {
  if (!linhas.length) return null;
  const t = linhas[0].tipo;
  return linhas.every((l) => l.tipo === t) ? t : null;
}

// ── Montar o lote ─────────────────────────────────────────────────────────
export type Controle =
  | { tipo: "linha_dre"; valor: string }
  | { tipo: "conta"; valor: string }
  | { tipo: "natureza"; valor: string; escopo: "conta" | "lancamento" };

/** O alvo no formato do servidor: só o que existe (nota antiga sem número manda só `conta_id`). */
const alvoDoLancamento = (l: LinhaPendencia) => ({
  ...(l.numero_lancamento ? { numero_lancamento: l.numero_lancamento } : {}),
  ...(l.item_id != null ? { item_id: l.item_id } : {}),
  ...(l.conta_id != null ? { conta_id: l.conta_id } : {}),
});

export type PlanoDoLote = { acoes: AcaoClassificacao[]; contas: number; lancamentos: number; puladas: number };

/** As ações do lote para a seleção e o valor escolhido. Linha travada (mês fechado, conta fora do plano...) fica de fora e é contada em `puladas`. */
export function acoesDoControle(linhas: LinhaPendencia[], c: Controle): PlanoDoLote {
  const acoes: AcaoClassificacao[] = [];
  const codigos = new Set<string>();
  let puladas = 0;
  for (const l of linhas) {
    if (c.tipo === "linha_dre") {
      if (!l.acoes.linha_dre || !l.codigo_conta) { puladas++; continue; }
      if (!codigos.has(l.codigo_conta)) { codigos.add(l.codigo_conta); acoes.push({ tipo: "linha_dre", alvo: { codigo: l.codigo_conta }, valor: c.valor }); }
    } else if (c.tipo === "conta") {
      if (!l.acoes.conta) { puladas++; continue; }
      acoes.push({ tipo: "conta", alvo: alvoDoLancamento(l), valor: c.valor });
    } else if (c.escopo === "conta" && l.conta_no_plano && l.codigo_conta) {
      if (!codigos.has(l.codigo_conta)) { codigos.add(l.codigo_conta); acoes.push({ tipo: "natureza", alvo: { codigo: l.codigo_conta }, valor: c.valor }); }
    } else {
      // Só neste lançamento (ou conta fora do plano): o mês fechado trava.
      if (l.mes_fechado || !l.acoes.natureza) { puladas++; continue; }
      acoes.push({ tipo: "natureza", alvo: alvoDoLancamento(l), valor: c.valor });
    }
  }
  const contas = new Set(linhas.map((l) => l.codigo_conta ?? "")).size;
  return { acoes, contas: c.tipo === "linha_dre" ? codigos.size : contas, lancamentos: linhas.length - puladas, puladas };
}

/** A sugestão da linha pode ser aceita agora? (A ação dela está liberada para a linha.) */
export function sugestaoAplicavel(l: LinhaPendencia): boolean {
  const s = l.sugestao;
  if (!s || !l.acoes[s.tipo]) return false;
  if (s.tipo === "natureza" && !s.alvo.codigo && l.mes_fechado) return false;
  return true;
}

/** As sugestões das linhas, aceitas de uma vez (sem repetir a mesma ação — uma conta com 10 lançamentos vira 1 ação). */
export function acoesDasSugestoes(linhas: LinhaPendencia[]): AcaoClassificacao[] {
  const vistas = new Set<string>();
  const acoes: AcaoClassificacao[] = [];
  for (const l of linhas) {
    if (!sugestaoAplicavel(l)) continue;
    const s = l.sugestao!;
    const a: AcaoClassificacao = { tipo: s.tipo, alvo: s.alvo, valor: s.valor };
    const chave = JSON.stringify([a.tipo, a.alvo.codigo ?? "", a.alvo.numero_lancamento ?? "", a.alvo.item_id ?? 0, a.alvo.conta_id ?? 0, a.valor]);
    if (vistas.has(chave)) continue;
    vistas.add(chave);
    acoes.push(a);
  }
  return acoes;
}

/** Texto do botão de aplicar: diz exatamente o que vai ser gravado. */
export function textoDoLote(c: Controle, plano: PlanoDoLote): string {
  if (c.tipo === "linha_dre") return `Aplicar a ${plural(plano.acoes.length, "conta", "contas")} (vale para todos os lançamentos delas)`;
  if (c.tipo === "natureza" && c.escopo === "conta") return `Aplicar a ${plural(plano.acoes.length, "conta", "contas")}`;
  return `Aplicar a ${plural(plano.acoes.length, "lançamento", "lançamentos")}`;
}

// ── Frases e mensagens ────────────────────────────────────────────────────
export function fraseClassificar(f: FilaClassificacao, periodo: string, brl: (v: number) => string): Trecho[] {
  const n = f.resumo.total_pendencias;
  if (n === 0) return [{ t: `Nada a classificar em ${periodo}: todo lançamento tem conta, linha da DRE e, quando fica de fora, o motivo.` }];
  const maior = [...f.por_motivo].sort((a, b) => b.quantidade - a.quantidade)[0];
  const valores = [
    f.resumo.total_despesa ? `${brl(f.resumo.total_despesa)} de despesa` : null,
    f.resumo.total_receita ? `${brl(f.resumo.total_receita)} de receita` : null,
  ].filter(Boolean).join(" e ");
  return [
    { t: "Faltam classificar " }, { t: plural(n, "lançamento", "lançamentos"), b: true }, { t: ` em ${periodo}` },
    { t: valores ? ` — ${valores}${f.resumo.total_despesa && f.resumo.total_receita ? " (nunca somadas)" : ""}.` : "." },
    { t: ` Enquanto não forem classificados, ficam fora das linhas da DRE: ela prefere mostrar o buraco a fechar com um número errado.` },
    ...(maior && maior.quantidade ? [{ t: ` O que mais pesa: ` }, { t: ROTULO_MOTIVO[maior.motivo].toLowerCase(), b: true }, { t: ` (${maior.quantidade}).` }] : []),
  ];
}

export function mensagemAplicada(r: ResultadoLote): string {
  if (!r.lote) return "Nada mudou: tudo já estava classificado assim.";
  const base = `${plural(r.aplicadas, "classificação gravada", "classificações gravadas")} (${plural(r.alteracoes, "campo mudou", "campos mudaram")}).`;
  return `${base} A DRE já usa o novo valor; dá para desfazer.${r.sem_mudanca ? ` ${plural(r.sem_mudanca, "ação já estava assim", "ações já estavam assim")}.` : ""}`;
}

export function mensagemDesfeita(r: ResultadoReversao): string {
  const volta = `${plural(r.revertidas, "campo voltou", "campos voltaram")} ao que era`;
  if (!r.conflitos.length) return r.revertidas ? `Desfeito: ${volta}.` : "Esse lote já estava desfeito.";
  return `${volta}; ${plural(r.conflitos.length, "campo foi mudado à mão depois e ficou como está", "campos foram mudados à mão depois e ficaram como estão")}.`;
}

export function descreverLote(u: UltimoLote, dataHora: (iso: string) => string): string {
  return `${plural(u.alteracoes, "campo alterado", "campos alterados")} em ${dataHora(u.criado_em)}`;
}

// ── Drill ─────────────────────────────────────────────────────────────────
/** Para onde "ver o lançamento" leva: Consultas só lista o realizado; a prazo, o lugar é Contas a pagar/receber. */
export function destinoDaLinha(l: LinhaPendencia): { onde: "consultas" | "contas"; documento: string | null; relatorio: "a_pagar" | "a_receber" } {
  return { onde: l.pago ? "consultas" : "contas", documento: l.numero_lancamento, relatorio: l.tipo === "receita" ? "a_receber" : "a_pagar" };
}

// ── Exportar ──────────────────────────────────────────────────────────────
export function linhasParaExportar(linhas: LinhaPendencia[], dataBr: (iso: string) => string): (string | number | null)[][] {
  return linhas.map((l) => [
    ROTULO_MOTIVO[l.motivo], l.data ? dataBr(l.data) : "", l.fornecedor ?? "", [l.descricao, l.produto].filter(Boolean).join(" · "),
    l.numero_lancamento ?? "", l.codigo_conta ? `${l.codigo_conta}${l.nome_conta ? ` ${l.nome_conta}` : ""}` : "",
    l.tipo === "receita" ? "Receita" : "Despesa", l.valor, l.sugestao ? l.sugestao.rotulo : "",
  ]);
}

export type { GrupoConta };
