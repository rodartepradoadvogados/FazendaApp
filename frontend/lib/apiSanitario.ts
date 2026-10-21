// Cliente tipado do Sanitário Preventivo v2 — TODAS as rotas de /sanitario e
// de /painel-cowdata/sanitario (backend/fazenda/api/routers/sanitario/).
// O site e o app de campo usam este mesmo cliente.
//
// Erros: toda resposta não-OK vira `ErroApi` (lib/api.ts) com o `detail`
// preservado. Os 409 de decisão do back (`consentimento_necessario`,
// `decisao_riscos_necessaria`, `versao_desatualizada`, `nome_duplicado`) e o
// 422 de validação do wizard (`{codigo: "validacao", erros}`) são lidos com
// `codigoDoErro` / `errosValidacaoDoErro` — a tela abre o pop-up certo e
// reenvia com a decisão.
//
// Todo corpo enviado passa por um serializador de lib/sanitarioTipos.ts (os
// schemas do back têm `extra="forbid"`: campo desconhecido = 422).
import { API, authFetch, erroDaResposta, ErroApi } from "./api.ts";
import {
  carenciaParaEnvio, codigoDoDetalhe, consentimentoParaEnvio, definicaoParaEnvio, diaCriarParaEnvio, diaEditarParaEnvio,
  errosDoDetalhe, lancamentoParaEnvio, parametrosParaEnvio, registroParaEnvio,
  type CaixaDetalhe, type CaixaResumo, type Calendario, type CampoHoje, type CarenciaDecisaoIn, type CatalogoCentralItem,
  type CatalogoItemFazenda, type ConsentimentoIn, type DefinicaoCaixa, type DefinicaoCatalogo, type Dia, type DiaCriarIn,
  type DiaEditarIn, type DiaItemIn, type Dispositivo, type ErroEtapa, type EuSanitario, type FichaDia, type FichaVazia,
  type ImportacaoPlanilha, type JanelaCaixa, type LancamentoSimplesIn, type LeiteSeparado, type LogItem, type ModeloPlanilha,
  type ModoLeite, type NotaAgenda, type PacoteOffline, type Painel, type Parametros, type ParametrosIn, type Prazo,
  type PreviaCaixa, type Registro, type RegistroIn, type Resultado, type ResultadoRegistro, type ResumoPrevistas,
  type SincronizarOut, type Simulacao, type SituacaoCaixaAnimal, type TipoCaixa, type ValidacaoCaixa, type Veterinarios,
} from "./sanitarioTipos.ts";

const BASE = `${API}/sanitario`;
const BASE_COWDATA = `${API}/painel-cowdata/sanitario`;

type Query = Record<string, string | number | boolean | null | undefined>;
function qs(q?: Query): string {
  if (!q) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
async function pedir<T>(url: string, metodo: string, corpo: unknown, padrao: string): Promise<T> {
  const opts: RequestInit = { method: metodo };
  if (corpo !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(corpo);
  }
  const res = await authFetch(url, opts);
  if (!res.ok) throw await erroDaResposta(res, padrao);
  return res.json() as Promise<T>;
}
const get = <T>(path: string, q?: Query, padrao = "Não foi possível carregar.") => pedir<T>(`${BASE}${path}${qs(q)}`, "GET", undefined, padrao);
const post = <T>(path: string, corpo: unknown = {}, padrao = "Não foi possível gravar.") => pedir<T>(`${BASE}${path}`, "POST", corpo, padrao);
const put = <T>(path: string, corpo: unknown, padrao = "Não foi possível salvar.") => pedir<T>(`${BASE}${path}`, "PUT", corpo, padrao);
const del = <T>(path: string, padrao = "Não foi possível remover.") => pedir<T>(`${BASE}${path}`, "DELETE", undefined, padrao);

/** Código do 409/422 estruturado (ou null). */
export function codigoDoErro(e: unknown): string | null {
  return e instanceof ErroApi ? codigoDoDetalhe(e.detalhe) : null;
}
/** O `detail` cru de um erro de API (para ler os itens do 409). */
export function detalheDoErro<T = Record<string, unknown>>(e: unknown): T | null {
  return e instanceof ErroApi && e.detalhe && typeof e.detalhe === "object" ? (e.detalhe as T) : null;
}
export function errosValidacaoDoErro(e: unknown): ErroEtapa[] {
  return e instanceof ErroApi ? errosDoDetalhe(e.detalhe) : [];
}
/** Mensagem legível de qualquer erro (nunca "[object Object]"). */
export function mensagemDoErro(e: unknown, padrao = "Algo deu errado. Tente de novo."): string {
  if (e instanceof Error && e.message) return e.message;
  return padrao;
}

// ════════════════════════════════════════════════════════════════════════════
// Cadastro (caixas, wizard, catálogo da fazenda, parâmetros, veterinários, eu)
// ════════════════════════════════════════════════════════════════════════════
export const listarCaixas = (estado?: "ativa" | "inativa" | "arquivada" | "todas") =>
  get<CaixaResumo[]>("/caixas", { estado }, "Não foi possível carregar os cadastros.");
export const obterCaixa = (id: number) => get<CaixaDetalhe>(`/caixas/${id}`);
export const obterVersaoCaixa = (id: number, versaoId: number) =>
  get<{ id: number; numero: number; vigente_desde: string; vigente_ate: string | null; definicao: DefinicaoCaixa }>(`/caixas/${id}/versoes/${versaoId}`);
export const fichaVaziaCaixa = (id: number, linhas = 25) => get<FichaVazia>(`/caixas/${id}/ficha-vazia`, { linhas });
export const fichaVazia = (caixaIds: number[], linhas = 25) => get<FichaVazia>("/ficha-vazia", { caixa_ids: caixaIds.join(","), linhas });
export const validarCaixa = (definicao: Partial<DefinicaoCaixa>, etapa?: number | null, caixaId?: number | null) =>
  post<ValidacaoCaixa>("/caixas/validar", { definicao: definicaoParaEnvio(definicao), etapa: etapa ?? null, caixa_id: caixaId ?? null });
export const previaCaixa = (definicao: Partial<DefinicaoCaixa>, dataBase?: string | null) =>
  post<PreviaCaixa>("/caixas/previa", { definicao: definicaoParaEnvio(definicao), data_base: dataBase ?? null }, "Não foi possível calcular a prévia.");
export const criarCaixa = (definicao: Partial<DefinicaoCaixa>, estado: "ativa" | "inativa" = "inativa", aceitarCarencia = false) =>
  post<CaixaDetalhe>("/caixas", { definicao: definicaoParaEnvio(definicao), estado, aceitar_carencia: aceitarCarencia }, "Não foi possível salvar o cadastro.");
export const novaVersaoCaixa = (id: number, definicao: Partial<DefinicaoCaixa>, aceitarCarencia = false) =>
  put<CaixaDetalhe>(`/caixas/${id}`, { definicao: definicaoParaEnvio(definicao), aceitar_carencia: aceitarCarencia }, "Não foi possível salvar a versão nova.");
export const mudarEstadoCaixas = (caixaIds: number[], acao: "ativar" | "inativar" | "arquivar" | "reativar", motivo?: string | null) =>
  post<{ acao: string; resultados: { caixa_id: number; ok: boolean; erro: string | null }[] }>(
    "/caixas/estado", { caixa_ids: caixaIds, acao, motivo: motivo || null });
export const aceitarCarenciaCaixa = (id: number, modoLeite: ModoLeite, leiteDias?: number | null, carneDias?: number | null) =>
  post<{ id: number; caixa_id: number; caixa_versao_id: number; modo_leite: ModoLeite; leite_dias: number | null;
    carne_dias: number | null; aceito_em: string }>(`/caixas/${id}/carencia/aceite`,
    { modo_leite: modoLeite, leite_dias: leiteDias ?? null, carne_dias: carneDias ?? null });
export const catalogoDaFazenda = () => get<CatalogoItemFazenda[]>("/catalogo", undefined, "Não foi possível carregar o catálogo.");
export const ativarDoCatalogo = (versaoId: number, estado: "ativa" | "inativa" = "inativa") =>
  post<CaixaDetalhe>(`/catalogo/${versaoId}/ativar`, { estado }, "Não foi possível ativar do catálogo.");
export const atualizarDoCatalogo = (caixaId: number) =>
  post<CaixaDetalhe>(`/caixas/${caixaId}/atualizar-do-catalogo`, {}, "Não foi possível atualizar a cópia.");
export const obterParametros = () => get<Parametros>("/parametros");
export const salvarParametros = (p: ParametrosIn | Partial<Parametros>) => put<Parametros>("/parametros", parametrosParaEnvio(p));
export const listarVeterinarios = () => get<Veterinarios>("/veterinarios");
export const meuPapel = () => get<EuSanitario>("/eu");

// ════════════════════════════════════════════════════════════════════════════
// Dias ("Vacina"/"Exame"), registros, estorno, resultado, conflitos
// ════════════════════════════════════════════════════════════════════════════
export const listarDias = (f?: { estado?: string; de?: string; ate?: string }) => get<Dia[]>("/dias", f, "Não foi possível carregar os dias marcados.");
export const dataPrevista = (caixaIds: number[]) => get<{ data_prevista: string }>("/dias/data-prevista", { caixa_ids: caixaIds.join(",") });
export const obterDia = (id: number) => get<Dia>(`/dias/${id}`);
export const fichaDoDia = (id: number) => get<FichaDia>(`/dias/${id}/ficha`);
export const logDoDia = (id: number) => get<LogItem[]>(`/dias/${id}/log`);
export const registrosDoDia = (id: number) => get<Registro[]>(`/dias/${id}/registros`);
export const simularDia = (caixaIds: number[], data: string, dataPrev?: string | null, animalIds?: number[] | null) =>
  post<Simulacao>("/dias/simular", { caixa_ids: caixaIds, data, data_prevista: dataPrev ?? null, animal_ids: animalIds ?? null },
    "Não foi possível simular a data.");
export const marcarDia = (d: DiaCriarIn) => post<Dia>("/dias", diaCriarParaEnvio(d), "Não foi possível marcar o dia.");
export const editarDia = (id: number, d: DiaEditarIn) => put<Dia>(`/dias/${id}`, diaEditarParaEnvio(d), "Não foi possível salvar o dia.");
export const adicionarAnimaisDia = (id: number, itens: DiaItemIn[], consentimentos: ConsentimentoIn[] = []) =>
  post<Dia>(`/dias/${id}/itens`, {
    itens: itens.map((i) => ({ animal_id: i.animal_id, ...(i.caixa_id != null ? { caixa_id: i.caixa_id } : {}), ...(i.caixa_ids ? { caixa_ids: i.caixa_ids } : {}) })),
    consentimentos: consentimentos.map(consentimentoParaEnvio),
  }, "Não foi possível adicionar os animais.");
export const removerAnimalDia = (id: number, itemId: number) => del<Dia>(`/dias/${id}/itens/${itemId}`);
export const decidirCarenciaDia = (id: number, caixaId: number, modo: ModoLeite, leiteDias?: number | null, carneDias?: number | null) =>
  post<{ dia_id: number; caixa_id: number; aceite_id: number; modo: ModoLeite; leite_dias: number | null; carne_dias: number | null }>(
    `/dias/${id}/carencia`, { caixa_id: caixaId, modo, leite_dias: leiteDias ?? null, carne_dias: carneDias ?? null });
export const registrarNoDia = (id: number, registros: RegistroIn[], opts: { canal?: "site" | "app" | "curral";
  dispositivoUid?: string | null; carencia?: Record<number, CarenciaDecisaoIn> } = {}) =>
  post<ResultadoRegistro>(`/dias/${id}/registros`, {
    registros: registros.map(registroParaEnvio), canal: opts.canal ?? "site", dispositivo_uid: opts.dispositivoUid ?? null,
    carencia: carenciasParaEnvio(opts.carencia),
  }, "Não foi possível registrar.");
export const aplicarGrupo = (id: number, opts: { itemIds?: number[] | null; hora?: string | null; aplicadorPessoaId?: number | null;
  aplicadorTexto?: string | null; canal?: "site" | "app" | "curral"; carencia?: Record<number, CarenciaDecisaoIn> } = {}) =>
  post<ResultadoRegistro>(`/dias/${id}/aplicar`, {
    item_ids: opts.itemIds ?? null, hora: opts.hora ?? null, aplicador_pessoa_id: opts.aplicadorPessoaId ?? null,
    aplicador_texto: opts.aplicadorTexto ?? null, canal: opts.canal ?? "site", carencia: carenciasParaEnvio(opts.carencia),
  }, "Não foi possível aplicar.");
export const desfazerRegistros = (registroIds: number[]) =>
  post<{ desfeitos?: number; [k: string]: unknown }>("/registros/desfazer", { registro_ids: registroIds }, "Não foi possível desfazer.");
export const estornarRegistro = (registroId: number, motivo: string) =>
  post<Record<string, unknown>>(`/registros/${registroId}/estornar`, { motivo }, "Não foi possível estornar.");
export const lancarResultado = (registroId: number, r: { resultado: Resultado; resultado_valor?: number | null;
  resultado_detalhe?: Record<string, unknown> | null; veterinario_pessoa_id?: number | null; veterinario_texto?: string | null;
  crmv_texto?: string | null }) =>
  post<Record<string, unknown>>(`/registros/${registroId}/resultado`, {
    resultado: r.resultado, resultado_valor: r.resultado_valor ?? null, resultado_detalhe: r.resultado_detalhe ?? null,
    veterinario_pessoa_id: r.veterinario_pessoa_id ?? null, veterinario_texto: r.veterinario_texto ?? null, crmv_texto: r.crmv_texto ?? null,
  }, "Não foi possível lançar o resultado.");
export const fecharDia = (id: number, faltantes: "voltar" | "dispensar" = "voltar", motivo?: string | null) =>
  post<Dia>(`/dias/${id}/fechar`, { faltantes, motivo: motivo || null }, "Não foi possível fechar o dia.");
export const cancelarDia = (id: number, motivo?: string | null) =>
  post<Dia>(`/dias/${id}/cancelar`, { motivo: motivo || null }, "Não foi possível cancelar o dia.");
export const dispensarAnimais = (itens: { caixa_id: number; animal_id: number; ciclo_chave?: string | null; dose_num?: number | null }[],
  acao: "dispensar" | "descartar" = "dispensar", motivo?: string | null) =>
  post<{ dispensados: number; acao: string }>("/situacoes/dispensar", { itens, acao, motivo: motivo || null });
export const listarConflitos = () => get<LogItem[]>("/conflitos");
export const decidirConflito = (logId: number, manter: "existente" | "novo") =>
  post<Record<string, unknown>>(`/conflitos/${logId}/decidir`, { manter });

function carenciasParaEnvio(c?: Record<number, CarenciaDecisaoIn>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(c || {})) out[String(Number(k))] = carenciaParaEnvio(v);
  return out;
}

// ════════════════════════════════════════════════════════════════════════════
// App de campo
// ════════════════════════════════════════════════════════════════════════════
export const campoHoje = () => get<CampoHoje>("/campo/hoje");
export const pacoteOffline = (diaId: number) => get<PacoteOffline>(`/dias/${diaId}/pacote-offline`);
export const heartbeat = (dispositivoUid: string, filaPendentes: number, opts: { nome?: string | null; maisAntigoEm?: string | null } = {}) =>
  post<Dispositivo>("/dispositivos/heartbeat", { dispositivo_uid: dispositivoUid, nome: opts.nome ?? null,
    fila_pendentes: filaPendentes, fila_mais_antigo_em: opts.maisAntigoEm ?? null });
export const listarDispositivos = () => get<Dispositivo[]>("/dispositivos");
export const sincronizarCampo = (dispositivoUid: string, registros: (RegistroIn & { dia_id?: number | null; outro_texto?: string | null })[],
  opts: { nome?: string | null; restantes?: number } = {}) =>
  post<SincronizarOut>("/campo/sincronizar", {
    dispositivo_uid: dispositivoUid, nome: opts.nome ?? null, fila_pendentes_restantes: opts.restantes ?? 0,
    registros: registros.map((r) => ({ ...registroParaEnvio(r), dia_id: r.dia_id ?? null, outro_texto: r.outro_texto ?? null })),
  }, "Não foi possível enviar os registros.");

// ════════════════════════════════════════════════════════════════════════════
// Consultas (Sanidade › Preventiva, Agenda, ficha) — só leitura
// ════════════════════════════════════════════════════════════════════════════
export const painel = (dias = 30) => get<Painel>("/painel", { dias }, "Não foi possível carregar o painel.");
export const animaisNaJanela = (f?: { caixa_id?: number | null; estado?: string | null }) =>
  get<JanelaCaixa[]>("/janela", f, "Não foi possível carregar os animais na janela.");
export const calendario = (ano?: number) => get<Calendario>("/calendario", { ano }, "Não foi possível carregar o calendário.");
export const listarRegistros = (f?: { de?: string; ate?: string; caixa_id?: number | null; origem?: string | null;
  animal_id?: number | null; incluir_estornados?: boolean; limite?: number }) =>
  get<Registro[]>("/registros", f, "Não foi possível carregar as aplicações.");
export const historico = (f: { animal_id?: number | null; caixa_id?: number | null }) => get<Registro[]>("/historico", f);
export const situacaoAnimal = (animalId: number) =>
  get<{ animal_id: number; numero: string; caixas: SituacaoCaixaAnimal[] }>(`/animais/${animalId}/situacao`);
export const historicoAnimal = (animalId: number) =>
  get<{ animal_id: number; numero: string; registros: Registro[]; exames: Registro[] }>(`/animais/${animalId}/historico`);
export const resumoAgenda = (dias = 30) => get<ResumoPrevistas>("/agenda/resumo", { dias });
export const listarNotas = (abertas = true) => get<NotaAgenda[]>("/notas", { abertas });
export const resolverNota = (id: number) => post<{ id: number; resolvida_em: string }>(`/notas/${id}/resolver`);
export const listarPrazos = (estado: string | null = "aberto") => get<Prazo[]>("/prazos", { estado: estado ?? "" });
export const cumprirPrazo = (id: number, d: { documento_numero?: string | null; cumprido_em?: string | null }) =>
  post<Prazo>(`/prazos/${id}/cumprir`, { documento_numero: d.documento_numero || null, cumprido_em: d.cumprido_em || null });
export const listarLog = (f?: { dia_id?: number; caixa_id?: number; animal_id?: number; tipo?: string; limite?: number }) =>
  get<LogItem[]>("/log", f, "Não foi possível carregar o registro de decisões.");
export const leiteSeparado = () => get<LeiteSeparado>("/leite-separado", undefined, "Não foi possível carregar o leite separado.");

// ════════════════════════════════════════════════════════════════════════════
// Lançamentos › Preventivo (simples, ficha, planilha)
// ════════════════════════════════════════════════════════════════════════════
export const lancamentoSimples = (l: LancamentoSimplesIn) =>
  post<ResultadoRegistro>("/lancamento-simples", lancamentoParaEnvio(l), "Não foi possível gravar o lançamento.");
export const modeloPlanilha = () => get<ModeloPlanilha>("/importar-planilha/modelo");
export async function importarPlanilha(arquivo: File): Promise<ImportacaoPlanilha> {
  const fd = new FormData();
  fd.append("file", arquivo);
  const res = await authFetch(`${BASE}/importar-planilha`, { method: "POST", body: fd });
  if (!res.ok) throw await erroDaResposta(res, "Não foi possível importar a planilha.");
  return res.json();
}

// ════════════════════════════════════════════════════════════════════════════
// Cockpit CowData › Catálogo sanitário (central, sem fazenda)
// ════════════════════════════════════════════════════════════════════════════
export const listarCatalogoCentral = async (): Promise<CatalogoCentralItem[]> =>
  pedir(`${BASE_COWDATA}/catalogo`, "GET", undefined, "Não foi possível carregar o catálogo central.");
export const obterCatalogoCentral = async (id: number): Promise<CatalogoCentralItem> =>
  pedir(`${BASE_COWDATA}/catalogo/${id}`, "GET", undefined, "Não foi possível carregar o item.");
export const criarCatalogoCentral = (d: { chave: string; nome: string; tipo: TipoCaixa; padrao_fabrica?: boolean; ativo?: boolean;
  uf_sugerida?: string | null; definicao: Partial<DefinicaoCatalogo>; nota_mudanca?: string | null; base_legal?: string | null }) =>
  pedir<CatalogoCentralItem>(`${BASE_COWDATA}/catalogo`, "POST", {
    chave: d.chave, nome: d.nome, tipo: d.tipo, padrao_fabrica: !!d.padrao_fabrica, ativo: d.ativo ?? true,
    uf_sugerida: d.uf_sugerida || null, definicao: definicaoParaEnvio(d.definicao, { catalogo: true }),
    nota_mudanca: d.nota_mudanca || null, base_legal: d.base_legal || null,
  }, "Não foi possível criar o item.");
export const editarCatalogoCentral = (id: number, d: { nome?: string; ativo?: boolean; padrao_fabrica?: boolean; uf_sugerida?: string | null }) =>
  pedir<CatalogoCentralItem>(`${BASE_COWDATA}/catalogo/${id}`, "PUT", d, "Não foi possível salvar o item.");
export const publicarVersaoCatalogo = (id: number, definicao: Partial<DefinicaoCatalogo>, notaMudanca?: string | null, baseLegal?: string | null) =>
  pedir<CatalogoCentralItem>(`${BASE_COWDATA}/catalogo/${id}/versoes`, "POST", {
    definicao: definicaoParaEnvio(definicao, { catalogo: true }), nota_mudanca: notaMudanca || null, base_legal: baseLegal || null,
  }, "Não foi possível publicar a versão.");
