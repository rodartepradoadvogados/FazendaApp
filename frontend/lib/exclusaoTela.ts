// Regras PURAS da tela "Excluir lançamento" (3 passos): agrupar/filtrar os tipos, ordenar/paginar a lista de
// registros, montar o lote (itens[] ≤ 50, só admin) e o texto do retorno. Sem DOM nem fetch — testável com
// `npm test` (runner nativo do Node). O SERVIDOR continua sendo a fonte da verdade (risco, bloqueio, exigências).
import { normalizarBusca } from "./busca.ts";

export const LIMITE_LOTE = 50;

// ── Passo 1: tipos (GET /exclusoes/tipos) ───────────────────────────────────────────────────────────────────────
export type TipoApi = {
  id: string;
  label: string;
  sem_filtro_data: boolean;
  dominio?: string;
  plural?: string;
  dica?: string;
  cadastro?: boolean;
  contagem?: number | null;
};

export type DominioId = "reb" | "san" | "fin" | "est" | "pes" | "outros";

/** Grupos da grade principal, na ordem da tela. O que não tem `dominio` conhecido cai em "Outros". */
export const DOMINIOS_GRADE: { id: DominioId; nome: string; cor: string }[] = [
  { id: "reb", nome: "Rebanho e reprodução", cor: "var(--cat-reproducao)" },
  { id: "san", nome: "Sanidade", cor: "var(--cat-sanidade)" },
  { id: "fin", nome: "Financeiro", cor: "var(--cat-financeiro)" },
  { id: "est", nome: "Estoque", cor: "var(--cat-estoque)" },
  { id: "pes", nome: "Pessoal", cor: "var(--cat-gestao)" },
  { id: "outros", nome: "Outros", cor: "var(--text-muted)" },
];

/** Ordem de exibição dentro do grupo (os que o dono mais procura primeiro); o que não está aqui vai depois, por nome. */
const ORDEM_TIPOS = [
  "diagnostico", "servico", "parto", "controle", "animal", "movimento_lote", "secagem", "pesagem_corporal", "evento_manual",
  "sanidade", "protocolo_sanitario_lancamento", "protocolo_iatf_lancamento",
  "financeiro", "compra_animal", "compra_semen", "venda_animal", "entrega_leite",
  "estoque", "movimento_estoque",
  "diaria", "diaria_pagamento", "empreitada", "contrato",
];

/** Nome curto do bloco: o `plural` do servidor com a inicial maiúscula (cai no `label` se o tipo não tem META). */
export function nomeCurto(t: Pick<TipoApi, "label" | "plural">): string {
  const p = (t.plural || "").trim();
  return p ? p.charAt(0).toUpperCase() + p.slice(1) : t.label;
}

export function casaTipo(t: TipoApi, termo: string): boolean {
  const q = normalizarBusca(termo);
  if (!q) return true;
  return normalizarBusca(`${t.label} ${t.plural ?? ""} ${t.dica ?? ""}`).includes(q);
}

function posicao(id: string): number {
  const i = ORDEM_TIPOS.indexOf(id);
  return i < 0 ? ORDEM_TIPOS.length : i;
}

export type GrupoTipos = { id: DominioId; nome: string; cor: string; tipos: TipoApi[] };
export type TiposAgrupados = {
  /** O bloco largo "Todos os lançamentos" (sai da grade), se o servidor o devolveu e a busca o inclui. */
  todos: TipoApi | null;
  grupos: GrupoTipos[];
  /** Grupo recolhido: cadastros (lote, fornecedor, pessoa, doença, safra…). */
  cadastros: TipoApi[];
  /** Quantos tipos a busca deixou visíveis (inclui o bloco "Todos"). */
  visiveis: number;
  /** Total de tipos vindos do servidor. */
  total: number;
};

export function agruparTipos(tipos: TipoApi[], termo: string): TiposAgrupados {
  const filtrados = tipos.filter((t) => casaTipo(t, termo));
  const todos = filtrados.find((t) => t.id === "todos_lancamentos") ?? null;
  const resto = filtrados.filter((t) => t.id !== "todos_lancamentos");
  const porNome = (a: TipoApi, b: TipoApi) => posicao(a.id) - posicao(b.id) || nomeCurto(a).localeCompare(nomeCurto(b), "pt-BR");
  const cadastros = resto.filter((t) => t.cadastro).sort(porNome);
  const grade = resto.filter((t) => !t.cadastro);
  const conhecidos = new Set<string>(DOMINIOS_GRADE.map((d) => d.id));
  const grupos = DOMINIOS_GRADE.map((d) => ({
    ...d,
    tipos: grade
      .filter((t) => (conhecidos.has(t.dominio ?? "") && t.dominio !== "outros" ? t.dominio : "outros") === d.id)
      .sort(porNome),
  })).filter((g) => g.tipos.length > 0);
  return {
    todos, grupos, cadastros, visiveis: filtrados.length,
    total: tipos.length,
  };
}

/** Contagem do bloco: `null`/ausente vira "—" (hoje nem todo tipo conta). */
export function fmtContagem(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("pt-BR");
}

// ── Passo 2: registros (GET /exclusoes/buscar) ──────────────────────────────────────────────────────────────────
export type RegistroBusca = {
  id: string;
  titulo: string;
  subtitulo: string;
  tipo_real?: string;
  /** AAAA-MM-DD; `null` nos tipos sem data (cadastros). */
  data?: string | null;
};

export const tipoDoRegistro = (r: RegistroBusca, tipo: string) => r.tipo_real || tipo;
export const chaveRegistro = (r: RegistroBusca, tipo: string) => `${tipoDoRegistro(r, tipo)}:${r.id}`;

const RE_DATA_BR = /(\d{2})\/(\d{2})\/(\d{4})/;

/** Data ISO do registro: a que o servidor mandou; senão, a primeira dd/mm/aaaa que aparece no título (tipos antigos). */
export function dataDoRegistro(r: RegistroBusca): string | null {
  if (r.data) return r.data.slice(0, 10);
  const m = RE_DATA_BR.exec(r.titulo || "");
  return m ? `${m[3]}-${m[2]}-${m[1]}` : null;
}

export function dataBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return a && m && d ? `${d}/${m}/${a}` : "—";
}

/** Título sem a data repetida: "11153 — Toque 17/10/2026" vira "11153 — Toque" (a data tem coluna própria). */
export function tituloSemData(r: RegistroBusca): string {
  const iso = dataDoRegistro(r);
  if (!iso) return r.titulo;
  const br = dataBr(iso);
  const limpo = r.titulo.replace(new RegExp(`\\s*[—-]?\\s*${br.replace(/\//g, "\\/")}\\s*$`), "").trim();
  return limpo || r.titulo;
}

export type ColunaOrdem = "data" | "titulo";
export type Ordem = { coluna: ColunaOrdem; dir: 1 | -1 } | null;

/** Alterna a ordem ao clicar no cabeçalho: 1º clique = decrescente para data (mais recente primeiro), crescente para texto. */
export function proximaOrdem(atual: Ordem, coluna: ColunaOrdem): Ordem {
  if (!atual || atual.coluna !== coluna) return { coluna, dir: coluna === "data" ? -1 : 1 };
  return { coluna, dir: atual.dir === 1 ? -1 : 1 };
}

/** `null` = ordem do servidor (mais recentes primeiro). Registro sem data vai para o fim em qualquer direção. */
export function ordenarRegistros(linhas: RegistroBusca[], ordem: Ordem): RegistroBusca[] {
  if (!ordem) return linhas;
  const { coluna, dir } = ordem;
  return [...linhas].sort((a, b) => {
    if (coluna === "data") {
      const da = dataDoRegistro(a);
      const db = dataDoRegistro(b);
      if (!da && !db) return 0;
      if (!da) return 1;
      if (!db) return -1;
      return da === db ? 0 : (da < db ? -1 : 1) * dir;
    }
    return a.titulo.localeCompare(b.titulo, "pt-BR", { numeric: true }) * dir;
  });
}

export function paginar<T>(linhas: T[], pagina: number, tamanho: number) {
  const total = linhas.length;
  const paginas = Math.max(1, Math.ceil(total / tamanho));
  const atual = Math.min(Math.max(1, pagina), paginas);
  const ini = (atual - 1) * tamanho;
  const fatia = linhas.slice(ini, ini + tamanho);
  return {
    linhas: fatia, pagina: atual, paginas, total,
    de: total === 0 ? 0 : ini + 1, ate: ini + fatia.length,
  };
}

/** Números das páginas a mostrar (1 … atual-1 atual atual+1 … última), no máximo ~7 botões. */
export function botoesPagina(atual: number, paginas: number): (number | "…")[] {
  if (paginas <= 7) return Array.from({ length: paginas }, (_, i) => i + 1);
  const out: (number | "…")[] = [1];
  const ini = Math.max(2, atual - 1);
  const fim = Math.min(paginas - 1, atual + 1);
  if (ini > 2) out.push("…");
  for (let p = ini; p <= fim; p++) out.push(p);
  if (fim < paginas - 1) out.push("…");
  out.push(paginas);
  return out;
}

/** Quantos registros o servidor devolve no máximo (o resto some da lista): 200 por tipo, 300 em "Todos os lançamentos". */
export function tetoDaBusca(tipo: string): number {
  return tipo === "todos_lancamentos" ? 300 : 200;
}

// ── Lote (checkboxes → itens[]) ─────────────────────────────────────────────────────────────────────────────────
export type Selecao = Map<string, RegistroBusca>;

/** Marca/desmarca uma linha. Passou do limite do lote? Não marca e avisa (`estourou`). */
export function alternarSelecao(sel: Selecao, chave: string, r: RegistroBusca, limite = LIMITE_LOTE): { sel: Selecao; estourou: boolean } {
  const novo = new Map(sel);
  if (novo.has(chave)) {
    novo.delete(chave);
    return { sel: novo, estourou: false };
  }
  if (novo.size >= limite) return { sel, estourou: true };
  novo.set(chave, r);
  return { sel: novo, estourou: false };
}

/** Caixa do cabeçalho: se todas as linhas da página já estão marcadas, desmarca-as; senão marca até o limite do lote. */
export function alternarPagina(sel: Selecao, linhas: RegistroBusca[], tipo: string, limite = LIMITE_LOTE): { sel: Selecao; estourou: boolean } {
  const chaves = linhas.map((r) => chaveRegistro(r, tipo));
  const todas = chaves.length > 0 && chaves.every((c) => sel.has(c));
  const novo = new Map(sel);
  if (todas) {
    chaves.forEach((c) => novo.delete(c));
    return { sel: novo, estourou: false };
  }
  let estourou = false;
  linhas.forEach((r, i) => {
    const c = chaves[i];
    if (novo.has(c)) return;
    if (novo.size >= limite) { estourou = true; return; }
    novo.set(c, r);
  });
  return { sel: novo, estourou };
}

/** Depois de recarregar a lista, só ficam marcados os que continuam nela: nunca se apaga o que o usuário não vê. */
export function podarSelecao(sel: Selecao, linhas: RegistroBusca[], tipo: string): Selecao {
  const vivos = new Set(linhas.map((r) => chaveRegistro(r, tipo)));
  const novo = new Map<string, RegistroBusca>();
  sel.forEach((r, c) => { if (vivos.has(c)) novo.set(c, r); });
  return novo.size === sel.size ? sel : novo;
}

/** Corpo de `itens[]` do POST /exclusoes/impacto|confirmar. Em "Todos os lançamentos" cada item usa o tipo de ORIGEM. */
export function itensDoLote(sel: Selecao, tipo: string): { tipo: string; id: string }[] {
  return [...sel.values()].map((r) => ({ tipo: tipoDoRegistro(r, tipo), id: String(r.id) }));
}

// ── Passo 3 / retorno ───────────────────────────────────────────────────────────────────────────────────────────
/** Tipos cujo "apagar" só DESFAZ um campo do registro de origem (nenhuma linha some): o verbo da tela muda. */
export const TIPOS_QUE_DESFAZEM = new Set(["diagnostico"]);

export function verboDe(tipo: string): "desfazer" | "apagar" {
  return TIPOS_QUE_DESFAZEM.has(tipo) ? "desfazer" : "apagar";
}

export type ResultadoApi = {
  status: string;
  comprovante?: string;
  id?: number;
  solicitado_por?: string;
  itens?: string[];
  bloqueados?: { titulo: string; motivo: string }[];
  avisos?: string[];
};

export type Retorno = {
  tom: "ok" | "pedido" | "erro";
  texto: string;
  comprovante?: string;
  detalhes: string[];
  /** Atalho útil: "trilha" (admin apagou), "pedidos" (operador pediu). */
  atalho?: "trilha" | "pedidos";
};

/** Texto do retorno depois de apagar/pedir — sempre diz o que aconteceu e o que fazer em seguida. */
export function montarRetorno(r: ResultadoApi, titulo: string, nLote = 0): Retorno {
  const detalhes: string[] = [];
  if (r.avisos?.length) detalhes.push(...r.avisos);
  if (r.bloqueados?.length) {
    detalhes.push(`${r.bloqueados.length} ${r.bloqueados.length === 1 ? "item ficou" : "itens ficaram"} de fora: ${r.bloqueados.map((b) => b.titulo).join("; ")}.`);
  }
  if (r.status === "excluido") {
    const n = nLote > 0 ? (r.itens?.length ?? nLote) : 0;
    return {
      tom: "ok", comprovante: r.comprovante, detalhes, atalho: "trilha",
      texto: nLote > 0 ? `Excluído o lote de ${nLote} ${nLote === 1 ? "registro" : "registros"} (${n} ${n === 1 ? "item" : "itens"}).` : `Excluído: ${titulo}.`,
    };
  }
  if (r.status === "ja_pedido") return { tom: "pedido", texto: `Você já tinha pedido a exclusão de ${titulo}.`, detalhes, atalho: "pedidos" };
  if (r.status === "apoiado") {
    return {
      tom: "pedido", detalhes, atalho: "pedidos",
      texto: r.solicitado_por ? `Você apoiou o pedido de ${r.solicitado_por}: ${titulo}.` : `Você apoiou o pedido que já existia: ${titulo}.`,
    };
  }
  if (r.status === "solicitado") return { tom: "pedido", texto: `Pedido enviado: ${titulo}. O administrador decide.`, detalhes, atalho: "pedidos" };
  return { tom: "erro", texto: `Resposta inesperada do servidor (${r.status}).`, detalhes };
}

/** O que o servidor exige (espelho para a tela; o servidor repete tudo). */
export function exigencias(risco: "baixo" | "medio" | "alto", souAdmin: boolean) {
  return {
    motivo: !souAdmin || risco === "medio" || risco === "alto",
    // Só o admin digita a confirmação: o operador gera pedido, e quem confirma é o admin ao aprovar.
    confirmacao: souAdmin && risco === "alto",
  };
}

/** Mensagem de um erro capturado (`catch (e)` é `unknown`): a do servidor quando há, senão o texto padrão. */
export function mensagemDe(e: unknown, padrao: string): string {
  return e instanceof Error && e.message ? e.message : padrao;
}
