// Regras de tela da seleção de fêmeas para serviço reprodutivo (Inseminação, Protocolo IATF, Indução de cio): quem é apta,
// quem pede confirmação, quem está bloqueada — e como isso aparece na tabela. Funções puras.
//
// A decisão é do SERVIDOR (backend/fazenda/rules/aptidao.py + iatf_vigente.py, via GET /reproducao/aptidao-servico): o
// mesmo código que dá o 409 ao gravar. Aqui só se traduz o veredito em três níveis, com o motivo em texto:
//   · "apta"       — marcável, sem aviso;
//   · "confirmar"  — o servidor aceita FORÇAR (peso da novilha lançado abaixo do mínimo, matriz que consta gestante):
//                    marcável; ao salvar pede "Confirmar e lançar mesmo assim";
//   · "bloqueada"  — o servidor recusa de forma dura (idade mínima, a descartar, baixada, não é fêmea, já em protocolo
//                    IATF vigente): caixa desabilitada, motivo à vista.
// Enquanto o veredito do servidor não chegou (ou falhou), vale o que a página já antecipava (`motivosInaptidao`: só
// bloqueios duros, vindos de `inaptidaoServico`) e, para "consta gestante", o estado reprodutivo ao vivo.
import type { AptidaoServicoApi } from "./api.ts";

export type NivelAptidao = "apta" | "confirmar" | "bloqueada";
export type Aptidao = { nivel: NivelAptidao; /** texto curto para a coluna */ motivo?: string; /** frase inteira (dica) */ detalhe?: string; codigo?: string };

export const APTA: Aptidao = { nivel: "apta" };

/** "7120 tem 6,0 meses — abaixo da idade mínima de aptidão (15 meses, em Configurações > Parâmetros). Mais texto." →
 *  "Tem 6,0 meses — abaixo da idade mínima de aptidão": sem o número do animal, sem parênteses de configuração, só a 1ª frase. */
export function motivoCurto(mensagem: string | null | undefined, numero?: string): string {
  let t = (mensagem ?? "").trim();
  if (!t) return "";
  if (numero && t.startsWith(`${numero} `)) t = t.slice(numero.length + 1);
  t = t.replace(/\s*\([^)]*Configurações[^)]*\)/g, "");
  const fim = t.search(/\.\s|\.$/);
  if (fim > 0) t = t.slice(0, fim);
  t = t.replace(/\s+$/, "");
  return t ? t[0].toUpperCase() + t.slice(1) : "";
}

export type EntradaAptidao = {
  numero: string;
  /** Resposta de GET /reproducao/aptidao-servico (ou null enquanto não chegou / se falhou). */
  api: AptidaoServicoApi | null;
  /** número -> motivo de inaptidão dura que a página antecipa (fallback sem `api`). */
  motivosLocais?: ReadonlyMap<string, string>;
  /** O estado reprodutivo ao vivo diz "gestante" (fallback sem `api`). */
  gestanteLocal?: boolean;
  /** Trava "já em protocolo IATF vigente" (Protocolo IATF; Inseminação com cio natural / monta natural). */
  bloquearEmProtocolo?: boolean;
  /** Protocolo de destino (modo "adicionar a um em andamento"): estar nele já é "já está neste protocolo". */
  protocoloDestinoId?: number | null;
  /** Data do serviço (AAAA-MM-DD): um protocolo cujo D0 é POSTERIOR a ela não conflita (o servidor só conta D0 ≤ data). */
  dataReferencia?: string;
};

/** Veredito de UMA fêmea para a tabela. Ordem: já em protocolo → veredito do servidor → antecipação local. */
export function aptidaoDe(e: EntradaAptidao): Aptidao {
  const prot = e.api?.em_protocolo[e.numero];
  if (e.bloquearEmProtocolo && prot && (!e.dataReferencia || prot.data_d0.slice(0, 10) <= e.dataReferencia)) {
    if (e.protocoloDestinoId != null && prot.lancamento_id === e.protocoloDestinoId) {
      return { nivel: "bloqueada", codigo: "neste_protocolo", motivo: "Já está neste protocolo", detalhe: `${e.numero} já está no protocolo escolhido.` };
    }
    return {
      nivel: "bloqueada", codigo: "em_protocolo", motivo: `Já em protocolo IATF vigente (D0 ${dataBr(prot.data_d0).slice(0, 5)})`,
      detalhe: `${e.numero} já está em protocolo IATF vigente — ${prot.nome_protocolo}, D0 em ${dataBr(prot.data_d0)}.`,
    };
  }
  if (e.api) {
    const v = e.api.animais[e.numero];
    if (!v) return APTA;
    const curto = motivoCurto(v.mensagem, e.numero) || "Não apta a servir";
    return { nivel: v.confirmavel ? "confirmar" : "bloqueada", codigo: v.motivo ?? undefined, motivo: curto, detalhe: v.mensagem ?? undefined };
  }
  const local = e.motivosLocais?.get(e.numero);
  if (local) return { nivel: "bloqueada", codigo: "local", motivo: local[0].toUpperCase() + local.slice(1) };
  if (e.gestanteLocal) return { nivel: "confirmar", codigo: "gestante", motivo: "Consta gestante" };
  return APTA;
}

function dataBr(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

/* ───────────────────────────── linhas da tabela ───────────────────────────── */

/** O que a tabela precisa de cada fêmea (já resolvido: nada de API aqui dentro). */
export type LinhaFemea = {
  numero: string;
  lote: string;
  categoria: string;
  /** "DEL 96" (vaca em lactação) ou "17 meses" (novilha) ou "—". */
  marco: string;
  /** Rótulo ao vivo da situação reprodutiva. */
  situacao: string;
  /** Texto "IA 05/08/2026" / "Monta 05/08/2026" / "—" e a data ISO (para ordenar). */
  ultima: string;
  /** Selo curto do protocolo vigente ("IATF 06/10"), quando houver. */
  protocolo?: string;
  protocoloTitulo?: string;
  /** Veio marcada (diagnóstico negativo, Agenda). */
  preMarcada?: boolean;
  aptidao: Aptidao;
  /** Está em PEV (período de espera voluntário) — filtro rápido da Indução de cio. */
  emPev?: boolean;
};

export const SEM_LOTE = "Sem lote";

export type AnimalBase = {
  numero: string; grupo_primario?: string | null; categoria_abrev?: string | null; categoria_completa?: string | null;
  sit_rep?: string | null; del_dias?: number | null; em_lactacao?: boolean; idade_meses?: number | null;
};
export type EstadoBase = {
  estado: string; categoria?: string | null; del_dias: number | null; data_servico: string | null; tipo_servico: string | null;
};

const iso10 = (s: string) => s.slice(0, 10);

export function marcoDe(a: AnimalBase, est?: EstadoBase | null): string {
  const del = est?.del_dias ?? a.del_dias ?? null;
  const emLact = a.em_lactacao ?? (del != null && del > 0);
  if (emLact && del != null && del >= 0) return `DEL ${del}`;
  if (a.idade_meses != null) return `${Math.floor(a.idade_meses)} meses`;
  return "—";
}

export function ultimaServicoDe(est?: EstadoBase | null): string {
  if (!est?.data_servico) return "—";
  const tipo = (est.tipo_servico || "").toLowerCase().startsWith("monta") ? "Monta" : "IA";
  return `${tipo} ${dataBr(iso10(est.data_servico))}`;
}

export function seloProtocolo(nome: string, dataD0: string): string {
  const [, m, d] = iso10(dataD0).split("-");
  return `IATF ${d}/${m}`;
}

export function montarLinhas(opts: {
  animais: readonly AnimalBase[];
  estados: ReadonlyMap<string, EstadoBase>;
  rotuloEstado: (numero: string) => string;
  api: AptidaoServicoApi | null;
  motivosLocais?: ReadonlyMap<string, string>;
  bloquearEmProtocolo?: boolean;
  protocoloDestinoId?: number | null;
  dataReferencia?: string;
  preMarcadas?: ReadonlySet<string>;
  /** false = a aptidão é só informativa (Indução de cio): nunca bloqueia, só avisa "Confira". */
  usarServidor?: boolean;
}): LinhaFemea[] {
  const usarServidor = opts.usarServidor !== false;
  return opts.animais.map((a) => {
    const est = opts.estados.get(a.numero) ?? null;
    const prot = opts.api?.em_protocolo[a.numero];
    let aptidao = aptidaoDe({
      numero: a.numero, api: usarServidor ? opts.api : null, motivosLocais: opts.motivosLocais,
      gestanteLocal: est?.estado === "gestante", bloquearEmProtocolo: usarServidor && opts.bloquearEmProtocolo,
      protocoloDestinoId: opts.protocoloDestinoId, dataReferencia: opts.dataReferencia,
    });
    if (!usarServidor && aptidao.nivel !== "apta") aptidao = { ...aptidao, nivel: "confirmar" };
    return {
      numero: a.numero,
      lote: a.grupo_primario || SEM_LOTE,
      categoria: a.categoria_abrev || a.categoria_completa || est?.categoria || "—",
      marco: marcoDe(a, est),
      situacao: opts.rotuloEstado(a.numero),
      ultima: ultimaServicoDe(est),
      protocolo: prot ? seloProtocolo(prot.nome_protocolo, prot.data_d0) : undefined,
      protocoloTitulo: prot ? prot.nome_protocolo : undefined,
      preMarcada: opts.preMarcadas?.has(a.numero),
      aptidao,
      emPev: est?.estado === "pev",
    };
  });
}

/* ───────────────────────────── busca, grupos e seleção ───────────────────────────── */

const normaliza = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export function filtraLinhas(linhas: readonly LinhaFemea[], busca: string): LinhaFemea[] {
  const q = normaliza(busca.trim());
  if (!q) return [...linhas];
  return linhas.filter((l) => normaliza(`${l.numero} ${l.lote} ${l.categoria} ${l.situacao}`).includes(q));
}

export function ordenaNumero(a: string, b: string): number {
  return a.localeCompare(b, "pt-BR", { numeric: true });
}

export function agrupaPorLote(linhas: readonly LinhaFemea[]): { lote: string; itens: LinhaFemea[] }[] {
  const m = new Map<string, LinhaFemea[]>();
  for (const l of linhas) m.set(l.lote, [...(m.get(l.lote) ?? []), l]);
  return [...m.entries()]
    .sort(([a], [b]) => ordenaNumero(a, b))
    .map(([lote, itens]) => ({ lote, itens: [...itens].sort((x, y) => ordenaNumero(x.numero, y.numero)) }));
}

export const marcavel = (l: LinhaFemea) => l.aptidao.nivel !== "bloqueada";
export const ehApta = (l: LinhaFemea) => l.aptidao.nivel === "apta";

export function alterna(set: ReadonlySet<string>, v: string): Set<string> {
  const s = new Set(set);
  if (s.has(v)) s.delete(v); else s.add(v);
  return s;
}

export function todasAptasMarcadas(itens: readonly LinhaFemea[], sel: ReadonlySet<string>): boolean {
  const aptas = itens.filter(ehApta);
  return aptas.length > 0 && aptas.every((l) => sel.has(l.numero));
}

/** Marca (ou desmarca, se já estão todas) as APTAS do conjunto. Quem pede confirmação ou está bloqueada nunca entra sozinha. */
export function alternaAptas(sel: ReadonlySet<string>, itens: readonly LinhaFemea[]): Set<string> {
  const aptas = itens.filter(ehApta);
  const todas = todasAptasMarcadas(itens, sel);
  const s = new Set(sel);
  aptas.forEach((l) => (todas ? s.delete(l.numero) : s.add(l.numero)));
  return s;
}

/** Tira da seleção quem ficou bloqueada (o veredito mudou: nova data, protocolo lançado…) — nunca se envia bloqueada. */
export function semBloqueadas(sel: ReadonlySet<string>, linhas: readonly LinhaFemea[]): Set<string> {
  const bloq = new Set(linhas.filter((l) => !marcavel(l)).map((l) => l.numero));
  return new Set([...sel].filter((n) => !bloq.has(n)));
}

export type ResumoSelecao = { marcadas: LinhaFemea[]; pedemConfirmacao: number; total: number };
export function resumoSelecao(linhas: readonly LinhaFemea[], sel: ReadonlySet<string>): ResumoSelecao {
  const marcadas = linhas.filter((l) => sel.has(l.numero));
  return { marcadas, pedemConfirmacao: marcadas.filter((l) => l.aptidao.nivel === "confirmar").length, total: marcadas.length };
}

export function contagemFaixa(linhas: readonly LinhaFemea[]) {
  return {
    total: linhas.length,
    aptas: linhas.filter(ehApta).length,
    confirmar: linhas.filter((l) => l.aptidao.nivel === "confirmar").length,
    bloqueadas: linhas.filter((l) => l.aptidao.nivel === "bloqueada").length,
  };
}
