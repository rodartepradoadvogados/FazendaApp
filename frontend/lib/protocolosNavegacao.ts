// Central de Protocolos (app/protocolos/page.tsx) — hierarquia das abas e o
// esquema de URL. PURO (sem React, sem "@/"): roda no `node --test`.
//
// Hierarquia aprovada pelo dono (10/2026) — a antiga aba "Vacinas e exames"
// deixou de existir; o conteúdo foi para dentro das quatro abas:
//
//   Cadastro        › Sanidade | IATF | Indução | Customizado | Lida
//                     Sanidade › Curativa | Preventiva › Vacina | Exame | Outros preventivos
//   Aplicar         › Sanitário | IATF | Indução | Customizado | Lida
//                     Sanitário › Curativo | Preventivo › Vacina | Exame | Outros preventivos
//   Acompanhamento  › Todos | Sanitário | IATF | Indução | Customizado | Lida
//   Concluídos        (Sanitário › Curativo | Preventivo › Vacina | Exame | Outros)
//
// URL nova (querystring de /protocolos):
//   aba   = cadastro | aplicar | acompanhamento | concluidos
//   area  = sanidade (Cadastro) / sanitario (demais) | iatf | inducao | customizado | lida
//           (ausente em Acompanhamento/Concluídos = "Todos")
//   san   = curativa|preventiva (Cadastro) / curativo|preventivo (demais) — aceita os dois gêneros
//   tipo  = vacina | exame | outros (só com san preventivo)
//   + atalhos: caixa, passo (Cadastro); dia, marcar, caixas (Aplicar).
//   ex.: ?aba=cadastro&area=sanidade&san=preventiva&tipo=vacina&caixa=3&passo=7
//        ?aba=aplicar&area=sanitario&san=preventivo&tipo=exame&dia=7
//
// URL antiga continua aceita como atalho (links salvos, notas e push antigos):
//   ?aba=vacinas&sub=cadastro[&caixa=3&passo=7] → Cadastro › Sanidade › Preventiva
//   ?aba=vacinas&sub=marcados[&dia=7|&caixas=1,2|&marcar=<caixa>-<animal>,...] → Aplicar › Sanitário › Preventivo
//   ?aba=lancamento → Aplicar; ?aba=historico → Concluídos;
//   ?aba=cadastro&tipo=iatf (ou sanitario/inducao/customizado/lida) → aquela área do Cadastro.
// Sem `tipo` (vacina/exame/outros) mas com caixa/dia, a página busca o tipo
// pela API e posiciona no seletor certo (`resolver`).

export type AbaCentral = "cadastro" | "aplicar" | "acompanhamento" | "concluidos";
/** "" = Todos (só Acompanhamento/Concluídos). */
export type AreaCentral = "" | "sanitario" | "iatf" | "inducao" | "customizado" | "lida";
export type LadoSanitario = "curativo" | "preventivo";
export type GrupoPreventivo = "vacina" | "exame" | "outros";

export type NavCentral = { aba: AbaCentral; area: AreaCentral; san: LadoSanitario; grupo: GrupoPreventivo };
export type AtalhoCentral = {
  caixa: number | null; passo: number | null; dia: number | null;
  pares: { caixa_id: number; animal_id: number }[]; caixas: number[];
};
export type LeituraCentral = {
  nav: NavCentral; atalho: AtalhoCentral;
  /** O grupo (vacina/exame/outros) não veio na URL e há caixa/dia para descobrir pela API. */
  resolver: { caixa: number } | { dia: number } | null;
};

export const ABAS_CENTRAL: AbaCentral[] = ["cadastro", "aplicar", "acompanhamento", "concluidos"];
export const AREAS_CENTRAL: Exclude<AreaCentral, "">[] = ["sanitario", "iatf", "inducao", "customizado", "lida"];
export const GRUPOS_PREVENTIVO: GrupoPreventivo[] = ["vacina", "exame", "outros"];
export const ROTULO_GRUPO: Record<GrupoPreventivo, string> = { vacina: "Vacina", exame: "Exame", outros: "Outros preventivos" };
const ABAS_LEGADO: Record<string, AbaCentral> = { lancamento: "aplicar", historico: "concluidos" };

/** Grupo do seletor a partir do tipo da caixa: tudo que não é vacina nem exame cai em "Outros" (vermífugo, outro…). */
export function grupoDoTipo(tipo: string | null | undefined): GrupoPreventivo {
  return tipo === "vacina" ? "vacina" : tipo === "exame" ? "exame" : "outros";
}
export function tipoNoGrupo(tipo: string | null | undefined, grupo: GrupoPreventivo | null | undefined): boolean {
  return !grupo || grupoDoTipo(tipo) === grupo;
}
/** Dia marcado pertence ao grupo se alguma das caixas dele é do grupo (um dia pode juntar vacina e vermífugo). */
export function diaNoGrupo(dia: { tipo?: string | null; caixas?: { tipo?: string | null }[] | null }, grupo: GrupoPreventivo | null | undefined): boolean {
  if (!grupo) return true;
  const cxs = dia.caixas || [];
  return cxs.length ? cxs.some((c) => grupoDoTipo(c.tipo) === grupo) : grupoDoTipo(dia.tipo) === grupo;
}
/** Grupo "principal" de um dia (para abrir um dia por id): o da primeira caixa; sem caixas, o tipo do dia. */
export function grupoDoDia(dia: { tipo?: string | null; caixas?: { tipo?: string | null }[] | null }): GrupoPreventivo {
  const cxs = dia.caixas || [];
  return grupoDoTipo(cxs.length ? cxs[0].tipo : dia.tipo);
}
/** Tipo que já vem marcado no "Criar do zero" do wizard. */
export function tipoInicialDoGrupo(grupo: GrupoPreventivo | null | undefined): "vacina" | "exame" | "vermifugo" {
  return grupo === "exame" ? "exame" : grupo === "outros" ? "vermifugo" : "vacina";
}

export function navPadrao(aba: AbaCentral = "acompanhamento"): NavCentral {
  return { aba, area: aba === "cadastro" || aba === "aplicar" ? "sanitario" : "", san: "curativo", grupo: "vacina" };
}
/** Troca de aba mantendo o que faz sentido (área, curativo/preventivo, grupo). "Todos" não existe em Cadastro/Aplicar. */
export function navParaAba(nav: NavCentral, aba: AbaCentral): NavCentral {
  const area = !nav.area && (aba === "cadastro" || aba === "aplicar") ? "sanitario" : nav.area;
  return { ...nav, aba, area };
}

const int = (v: string | null): number | null => (v && /^\d+$/.test(v.trim()) && Number(v) > 0 ? Number(v) : null);
const ints = (v: string | null): number[] => (v || "").split(",").map((x) => int(x)).filter((n): n is number => n != null);

function lerArea(v: string | null): AreaCentral | null {
  if (!v) return null;
  if (v === "sanidade" || v === "sanitario") return "sanitario";
  if (v === "todos") return "";
  return (AREAS_CENTRAL as string[]).includes(v) ? (v as AreaCentral) : null;
}
function lerSan(v: string | null): LadoSanitario | null {
  if (v === "curativa" || v === "curativo") return "curativo";
  if (v === "preventiva" || v === "preventivo") return "preventivo";
  return null;
}
function lerGrupo(v: string | null): GrupoPreventivo | null {
  if (v === "vacina" || v === "exame" || v === "outros") return v;
  if (v === "vermifugo" || v === "outro") return "outros";
  return null;
}

/** Lê a querystring (nova ou antiga) e devolve onde a página deve abrir. */
export function lerUrlCentral(entrada: URLSearchParams | string): LeituraCentral {
  const q = typeof entrada === "string" ? new URLSearchParams(entrada.replace(/^[^?]*\?/, "")) : entrada;
  const pares = (q.get("marcar") || "").split(",").map((x) => x.split("-").map((n) => int(n)))
    .filter(([c, a]) => c != null && a != null).map(([c, a]) => ({ caixa_id: c as number, animal_id: a as number }));
  const atalho: AtalhoCentral = { caixa: int(q.get("caixa")), passo: int(q.get("passo")), dia: int(q.get("dia")), pares, caixas: ints(q.get("caixas")) };

  const abaQs = q.get("aba") || "";
  const grupo = lerGrupo(q.get("tipo"));
  let nav: NavCentral;
  if (abaQs === "vacinas") {
    // Atalho antigo: a aba "Vacinas e exames" (sub=cadastro | marcados).
    const marcados = q.get("sub") === "marcados" || !!(atalho.dia || atalho.pares.length || atalho.caixas.length);
    nav = { ...navPadrao(marcados ? "aplicar" : "cadastro"), area: "sanitario", san: "preventivo" };
  } else {
    const aba = (ABAS_LEGADO[abaQs] ?? abaQs) as AbaCentral;
    nav = navPadrao((ABAS_CENTRAL as string[]).includes(aba) ? aba : "acompanhamento");
    const area = lerArea(q.get("area"));
    const san = lerSan(q.get("san"));
    if (area != null) nav.area = area;
    // `?tipo=iatf` era o atalho do Cadastro antigo (tipo de protocolo); hoje `tipo` é o grupo do preventivo.
    else if (lerArea(q.get("tipo"))) nav.area = lerArea(q.get("tipo")) as AreaCentral;
    if (san) nav.san = san;
    else if (grupo) nav.san = "preventivo";
    if (san || grupo) nav.area = "sanitario";
    if (!nav.area && (nav.aba === "cadastro" || nav.aba === "aplicar")) nav.area = "sanitario";
  }
  if (grupo) nav.grupo = grupo;

  let resolver: LeituraCentral["resolver"] = null;
  if (!grupo && nav.area === "sanitario" && nav.san === "preventivo") {
    if (nav.aba === "cadastro" && atalho.caixa) resolver = { caixa: atalho.caixa };
    else if (atalho.dia) resolver = { dia: atalho.dia };
    else if (atalho.caixas.length) resolver = { caixa: atalho.caixas[0] };
    else if (atalho.pares.length) resolver = { caixa: atalho.pares[0].caixa_id };
  }
  return { nav, atalho, resolver };
}

/** Monta a URL nova de /protocolos para um ponto da hierarquia (+ atalhos opcionais). */
export function urlCentral(nav: Partial<Omit<NavCentral, "grupo">> & { aba: AbaCentral; grupo?: GrupoPreventivo | null },
  extra: Partial<AtalhoCentral> = {}): string {
  // grupo null = "não sei o grupo": a URL sai sem `tipo` e a página descobre pela caixa/dia.
  const n = { ...navPadrao(nav.aba), ...nav };
  const q = new URLSearchParams();
  q.set("aba", n.aba);
  const cadastro = n.aba === "cadastro";
  if (n.area) q.set("area", n.area === "sanitario" && cadastro ? "sanidade" : n.area);
  if (n.area === "sanitario") {
    q.set("san", n.san === "preventivo" ? (cadastro ? "preventiva" : "preventivo") : (cadastro ? "curativa" : "curativo"));
    if (n.san === "preventivo" && n.grupo) q.set("tipo", n.grupo);
  }
  if (extra.caixa) q.set("caixa", String(extra.caixa));
  if (extra.passo) q.set("passo", String(extra.passo));
  if (extra.dia) q.set("dia", String(extra.dia));
  if (extra.caixas?.length) q.set("caixas", extra.caixas.join(","));
  if (extra.pares?.length) q.set("marcar", extra.pares.map((p) => `${p.caixa_id}-${p.animal_id}`).join(","));
  return `/protocolos?${q.toString().replace(/%2C/g, ",")}`;
}

/** Atalhos prontos para os links de fora (Sanidade, Agenda, Parâmetros…). Sem `grupo`, a página descobre pela caixa/dia. */
export const linkCentral = {
  cadastroPreventivo: (extra: Partial<AtalhoCentral> = {}, grupo: GrupoPreventivo | null = null) =>
    urlCentral({ aba: "cadastro", area: "sanitario", san: "preventivo", grupo }, extra),
  aplicarPreventivo: (extra: Partial<AtalhoCentral> = {}, grupo: GrupoPreventivo | null = null) =>
    urlCentral({ aba: "aplicar", area: "sanitario", san: "preventivo", grupo }, extra),
};
