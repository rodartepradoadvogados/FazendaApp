// Visibilidade por CONTRATO — fonte única de "o que esta fazenda/usuário vê".
//
// Antes a regra morava em 3 mapas que divergiam (ROTA_MODULO e MODULO_CONTRATO
// em lib/api.ts, `links` da Sidebar) e na Agenda. Agora existe UMA tabela
// rota → módulos (qualquer-de) e UMA tabela módulo-do-front → módulos
// comerciais do contrato (qualquer-de); ROTA_MODULO/MODULO_CONTRATO de api.ts
// são derivados daqui.
//
// Este arquivo é PURO e roda sob `node --experimental-strip-types --test`
// (ver modulos.test.ts): nada de import de api.ts (senão o teste carregaria o
// app inteiro e criaria ciclo, já que api.ts delega a este módulo), nada de
// alias "@/". Toda função de decisão recebe o contexto por parâmetro; a única
// exceção é contextoAtual(), que lê o localStorage (e só roda no navegador).

/** Contexto de decisão. `modulosContratados === null` = sem dado (resposta
 *  antiga em cache / token sem fazenda): NÃO restringe nada. Lista vazia É uma
 *  restrição de verdade. */
export type CtxModulos = {
  papel: string | null;
  permissoes: string[];
  modulosContratados: string[] | null;
  contratoStatus: string | null;
  /** Sessão de suporte CowData dentro da fazenda-cliente: passa por tudo. */
  suporte: boolean;
  /** Dono da plataforma / membro da Equipe CowData: não é barrado pela tela de
   *  contrato aguardando/suspenso (mas continua sujeito aos módulos). */
  isento?: boolean;
};

/** Chaves comerciais que dão sentido à Capa, Lançamentos e Indicadores:
 *  sem nenhuma delas a fazenda não tem rebanho para mostrar. */
export const MODULOS_DE_REBANHO = ["rebanho", "reprodutivo", "produtivo"];

/** Módulo do FRONT (nome da permissão do usuário) → módulos COMERCIAIS do
 *  contrato (qualquer-de). `null` = transversal, sem trava de contrato.
 *  Módulo ausente da tabela também não é restringido. */
export const MODULO_CONTRATO: Record<string, string[] | null> = {
  capa: MODULOS_DE_REBANHO,
  indicadores: MODULOS_DE_REBANHO,
  lancamentos: MODULOS_DE_REBANHO,
  analise: ["reprodutivo"],
  agenda: null,
  rebanho: ["rebanho"],
  reproducao: ["reprodutivo"],
  producao: ["produtivo"],
  recria: ["produtivo"],
  alimentacao: ["alimentacao"],
  sanidade: ["sanitario"],
  financeiro: ["financeiro"],
  estoque: ["estoque"],
  pedidos: ["pedidos"],
  parametros: null,
  upload: null,
};

/** Rota → módulos do front (qualquer-de). A primeira entrada é o "módulo
 *  principal" (ROTA_MODULO). Rota ausente = livre para qualquer logado. */
export const ROTA_MODULOS: Record<string, string[]> = {
  "/": ["capa"],
  "/indicadores": ["indicadores"],
  "/agenda": ["agenda"],
  "/lancamentos": ["lancamentos"],
  "/protocolos": ["lancamentos"],
  "/reproducao": ["reproducao"],
  "/analise-reprodutiva": ["analise"],
  "/relatorios": ["reproducao"],
  "/rebanho": ["rebanho"],
  "/ciclos-21-dias": ["reproducao"],
  // Histórico reúne Reprodução + Produção: basta uma das duas.
  "/historico": ["reproducao", "producao"],
  "/producao": ["producao"],
  "/alimentacao": ["alimentacao"],
  "/sanidade": ["sanidade"],
  "/recria": ["recria"],
  "/financeiro": ["financeiro"],
  "/estoque": ["estoque"],
  "/pedidos": ["pedidos"],
  "/cotacoes": ["pedidos"],
  "/parametros": ["parametros"],
  "/upload": ["upload"],
  "/analise-relatorios": ["indicadores"],
};

/** Derivado: rota → módulo principal (compatível com o antigo ROTA_MODULO). */
export const ROTA_MODULO: Record<string, string> = Object.fromEntries(
  Object.entries(ROTA_MODULOS).map(([rota, mods]) => [rota, mods[0]]),
);

/** Tela exibida quando o contrato está aguardando aprovação ou suspenso. */
export const ROTA_CONTRATO_INATIVO = "/contrato-inativo";

const STATUS_INATIVOS = ["aguardando_aprovacao", "suspenso"];

/** Ordem de pouso quando não há Capa útil (fazenda sem rebanho). */
const ORDEM_POUSO = ["/agenda", "/financeiro", "/cotacoes", "/pedidos"];

export function contratoInativo(ctx: CtxModulos): boolean {
  return ctx.contratoStatus != null && STATUS_INATIVOS.includes(ctx.contratoStatus);
}

/** O contrato inativo trava ESTE usuário? Suporte e dono/equipe passam. */
export function contratoBloqueia(ctx: CtxModulos): boolean {
  return contratoInativo(ctx) && !ctx.suporte && !ctx.isento;
}

/** Texto da tela de contrato inativo (tom neutro, sem culpar). */
export function mensagemContrato(status: string | null): { titulo: string; texto: string } {
  if (status === "suspenso") {
    return {
      titulo: "Acesso suspenso — fale com a CowData",
      texto: "O acesso desta fazenda está suspenso no momento. Entre em contato com a CowData para entender os próximos passos. Seus dados continuam guardados.",
    };
  }
  return {
    titulo: "Seu acesso está em análise",
    texto: "A CowData está concluindo a liberação desta fazenda. Assim que for aprovada, o sistema abre sozinho nesta tela. Se precisar de ajuda, fale com a CowData.",
  };
}

/** A fazenda contratou este módulo COMERCIAL (rebanho, financeiro, estoque…)?
 *  Sem dado (null) não restringe; suporte sempre passa; contrato inativo
 *  (para quem não é isento) não libera nada. */
export function moduloContratado(chave: string, ctx: CtxModulos = contextoAtual()): boolean {
  if (ctx.suporte) return true;
  if (contratoBloqueia(ctx)) return false;
  if (ctx.modulosContratados == null) return true;
  return ctx.modulosContratados.includes(chave);
}

/** Qualquer um dos módulos comerciais contratado? */
function algumContratado(chaves: string[], ctx: CtxModulos): boolean {
  return chaves.some((c) => moduloContratado(c, ctx));
}

/** Variante para o nome de módulo do FRONT (o de ROTA_MODULO/permissão): a
 *  fazenda contratou algo que o habilita? Módulo transversal/desconhecido = sim. */
export function moduloFrontContratado(mod: string, ctx: CtxModulos = contextoAtual()): boolean {
  if (ctx.suporte) return true;
  if (contratoBloqueia(ctx)) return false;
  const chaves = MODULO_CONTRATO[mod];
  if (!chaves) return true;
  return algumContratado(chaves, ctx);
}

/** Permissão + contrato para um módulo do front (era podeModulo de api.ts). */
export function podeModuloCtx(mod: string, ctx: CtxModulos = contextoAtual()): boolean {
  if (!ctx.papel) return false;
  if (!moduloFrontContratado(mod, ctx)) return false;
  if (ctx.papel === "admin") return true;
  return Array.isArray(ctx.permissoes) && ctx.permissoes.includes(mod);
}

/** A fazenda tem rebanho/reprodução/produção (Capa, Lançamentos, Indicadores
 *  fazem sentido)? */
export function temCapaUtil(ctx: CtxModulos = contextoAtual()): boolean {
  if (ctx.suporte) return true;
  if (contratoBloqueia(ctx)) return false;
  return algumContratado(MODULOS_DE_REBANHO, ctx);
}

/** O usuário abre esta rota? Rota fora da tabela = livre (portal, configurações
 *  etc. decidem por conta própria). "/" depende só da Capa útil (a Home nunca
 *  foi barrada por permissão "capa" — ver AuthShell). */
export function visivel(rota: string, ctx: CtxModulos = contextoAtual()): boolean {
  if (!ctx.papel) return false;
  if (rota === ROTA_CONTRATO_INATIVO) return true;
  if (contratoBloqueia(ctx)) return false;
  if (rota === "/") return temCapaUtil(ctx);
  const mods = ROTA_MODULOS[rota];
  if (!mods) return true;
  return mods.some((m) => podeModuloCtx(m, ctx));
}

/** Para o MENU: igual a visivel(), mas a Capa também exige a permissão "capa"
 *  (o item sai do menu para quem não tem, embora "/" continue abrindo). */
export function visivelNoMenu(rota: string, ctx: CtxModulos = contextoAtual()): boolean {
  if (rota === "/") return visivel(rota, ctx) && podeModuloCtx("capa", ctx);
  return visivel(rota, ctx);
}

/** Primeira rota onde esta pessoa pode pousar. Nunca devolve uma rota que ela
 *  própria não abre (anti-laço): Capa se há rebanho; senão Agenda, Financeiro,
 *  Cotações, Pedidos (a primeira permitida); último recurso /portal. Contrato
 *  aguardando/suspenso → tela de contrato inativo. */
export function rotaInicial(ctx: CtxModulos = contextoAtual()): string {
  if (contratoBloqueia(ctx)) return ROTA_CONTRATO_INATIVO;
  if (temCapaUtil(ctx)) return "/";
  for (const r of ORDEM_POUSO) if (visivel(r, ctx)) return r;
  return "/portal";
}

/** Itens do menu lateral — rótulos/tooltips curtos e sem citar módulos que a
 *  fazenda pode não ter. O ícone fica na Sidebar (chave = href). */
export type ItemMenu = { href: string; label: string; title: string; grupo: string };
export const ITENS_MENU: ItemMenu[] = [
  { href: "/",               label: "Capa",                  title: "Visão geral da fazenda", grupo: "Ciclo diário" },
  { href: "/agenda",         label: "Agenda",                title: "Pendências e eventos do dia", grupo: "Ciclo diário" },
  { href: "/lancamentos",    label: "Lançamentos",           title: "Registrar eventos do dia a dia", grupo: "Ciclo diário" },
  { href: "/protocolos",     label: "Central de Protocolos", title: "Protocolos: cadastro, aplicação e acompanhamento", grupo: "Ciclo diário" },
  { href: "/rebanho",        label: "Rebanho",               title: "Animais, lotes e ficha do animal", grupo: "Manejo do rebanho" },
  { href: "/historico",      label: "Histórico",             title: "Histórico de reprodução e produção", grupo: "Manejo do rebanho" },
  { href: "/ciclos-21-dias", label: "Ciclos de 21 dias",     title: "Risco de prenhez em ciclos de 21 dias", grupo: "Manejo do rebanho" },
  { href: "/sanidade",       label: "Sanidade",              title: "Aplicações, protocolos e calendário sanitário", grupo: "Insumos e sanidade" },
  { href: "/alimentacao",    label: "Alimentação",           title: "Dieta, consumo e necessidade por lote", grupo: "Insumos e sanidade" },
  { href: "/estoque",        label: "Estoque",               title: "Quantidades, valores e itens abaixo do mínimo", grupo: "Insumos e sanidade" },
  { href: "/financeiro",     label: "Controle Financeiro",   title: "Contas a pagar e a receber, folha e indicadores", grupo: "Financeiro" },
  { href: "/cotacoes",       label: "Cotações",              title: "Compare propostas de fornecedores", grupo: "Financeiro" },
  { href: "/pedidos",        label: "Pedidos",               title: "Intenção de compra e venda", grupo: "Financeiro" },
];

/** Itens do menu que este contexto enxerga (em ordem). */
export function itensDoMenu(ctx: CtxModulos = contextoAtual()): ItemMenu[] {
  return ITENS_MENU.filter((i) => visivelNoMenu(i.href, ctx));
}

/** Atalho "Insights" (Indicadores/Relatórios/Listas): só com algo a mostrar. */
export function temInsights(ctx: CtxModulos = contextoAtual()): boolean {
  return visivel("/indicadores", ctx) || visivel("/relatorios", ctx);
}

/** Destino do atalho Insights (primeira aba aberta). */
export function insightsHref(ctx: CtxModulos = contextoAtual()): string {
  return visivel("/indicadores", ctx) ? "/indicadores" : "/relatorios";
}

function lerJson(chave: string): Record<string, unknown> | null {
  try { return JSON.parse(localStorage.getItem(chave) || "null"); } catch { return null; }
}

/** Contexto da sessão atual, lido do localStorage (mesmas chaves de
 *  getUsuario/getFazendaAtual/getModoSuporte em api.ts). Único ponto impuro
 *  deste arquivo; no servidor devolve o contexto "ninguém logado". */
export function contextoAtual(): CtxModulos {
  if (typeof window === "undefined") {
    return { papel: null, permissoes: [], modulosContratados: null, contratoStatus: null, suporte: false };
  }
  const u = lerJson("usuario");
  const f = lerJson("fazenda_atual");
  return {
    papel: typeof u?.papel === "string" ? u.papel : null,
    permissoes: Array.isArray(u?.permissoes) ? (u.permissoes as string[]) : [],
    modulosContratados: Array.isArray(f?.modulos_contratados) ? (f.modulos_contratados as string[]) : null,
    contratoStatus: typeof f?.contrato_status === "string" ? f.contrato_status : null,
    suporte: lerJson("modo_suporte") != null,
    isento: u?.eh_dono === true || u?.eh_equipe_cowdata === true,
  };
}
