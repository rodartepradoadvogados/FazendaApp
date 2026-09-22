// Funções de comunicação com o backend FastAPI
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Mesmo gerador de `lib/offline.ts::gerarId` (não importado de lá pra evitar
// import circular — offline.ts já importa authFetch daqui). Usado só pelo
// header Idempotency-Key em POST/PUT sensíveis a duplo clique/retry de rede
// (ver main.py::_idempotencia) — não crypto.randomUUID() porque WebView
// Android desatualizado (uso rural comum) pode não ter a API.
function gerarChaveIdempotencia(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Extrai uma mensagem legível do `detail` de um erro da API.
 *
 * O FastAPI devolve `detail` como STRING quando é um `HTTPException` de
 * negócio (ex.: "Selecione ao menos um animal"), mas como uma LISTA DE
 * OBJETOS `[{loc, msg, type}, ...]` quando é um erro de validação do
 * Pydantic (422) — e todo `throw new Error(mensagemErroApi(d.detail) || "…")` do projeto
 * (280+ ocorrências) assumia string. `Error()` converte o valor recebido com
 * `String()`; `String([{...}])` vira exatamente o texto "[object Object]"
 * que aparecia na tela sem explicar nada ao usuário.
 *
 * Retorna `null` quando não há nada aproveitável, para o chamador continuar
 * caindo no `|| "mensagem padrão"` de sempre — só troca `d.detail` por
 * `mensagemErroApi(d.detail)` no lugar de sempre.
 */
export function mensagemErroApi(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    const partes = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) return String((item as any).msg);
        return null;
      })
      .filter((s): s is string => !!s);
    if (partes.length) return partes.join("; ");
  }
  if (detail && typeof detail === "object" && "msg" in (detail as any)) {
    return String((detail as any).msg);
  }
  // Os 409 de confirmação do módulo de RH (vale acima do pendente, pagamento
  // de diária acima do saldo devedor) mandam o texto em `mensagem`, junto dos
  // números que o aviso precisa mostrar. Sem esta linha o aviso caía no
  // genérico "Erro ao lançar vale" — a trava funcionava e a pessoa não
  // entendia por quê.
  if (detail && typeof detail === "object" && "mensagem" in (detail as any)) {
    return String((detail as any).mensagem);
  }
  return null;
}

/**
 * Erro de API que preserva o `detail` estruturado do backend.
 *
 * Nasceu para as travas de aptidão (`POST /reproducao/servico` e irmãos) e de
 * lactação aberta (`POST /producao/controles`): as duas devolvem 409 com um
 * objeto `{erro, msg, motivo, confirmavel, …}`, e a tela precisa saber se
 * aquele bloqueio específico admite um "confirmar mesmo assim" (`forcar`) ou
 * se é definitivo. Um `Error` com só a mensagem obrigaria a tela a adivinhar
 * isso lendo o texto.
 *
 * `message` continua sendo a mensagem legível de sempre, então quem só faz
 * `catch (e) { setErro(e.message) }` não muda em nada.
 */
/** O formato do `detail` que as travas devolvem no 409. */
type DetalheBloqueio = {
  motivo?: string | null; confirmavel?: boolean; erro?: string | null;
  secagem_anterior?: { id: number; data_secagem: string; motivo: string } | null;
};

export class ErroApi extends Error {
  status: number;
  detalhe: unknown;
  constructor(mensagem: string, status: number, detalhe: unknown) {
    super(mensagem);
    this.name = "ErroApi";
    this.status = status;
    this.detalhe = detalhe;
  }
  /** O `detail` quando ele é o objeto estruturado de bloqueio; senão `null`. */
  private get bloqueio(): DetalheBloqueio | null {
    return this.detalhe && typeof this.detalhe === "object" ? (this.detalhe as DetalheBloqueio) : null;
  }
  /** Código do motivo do bloqueio (ex.: "idade", "gestante", "sem_pesagem"). */
  get motivo(): string | null {
    return this.bloqueio?.motivo ?? null;
  }
  /** True quando reenviar com `forcar: true` destrava (bloqueio limítrofe, não erro grave). */
  get confirmavel(): boolean {
    return !!this.bloqueio?.confirmavel;
  }
  /** A secagem que já fechou a lactação, quando o bloqueio é
   * "sem_lactacao_aberta" no lançamento de Secagem (ver `POST
   * /producao/secagem`) — a tela usa isto pra oferecer "substituir a data
   * desta secagem" em vez de só mostrar a mensagem de erro. */
  get secagemAnterior(): { id: number; data_secagem: string; motivo: string } | null {
    return this.bloqueio?.erro === "sem_lactacao_aberta" ? (this.bloqueio?.secagem_anterior ?? null) : null;
  }
}

/** Lê o corpo do erro e devolve um `ErroApi` com o `detail` preservado. */
export async function erroDaResposta(res: Response, padrao: string): Promise<ErroApi> {
  const d: { detail?: unknown } = await res.json().catch(() => ({}));
  return new ErroApi(mensagemErroApi(d?.detail) || padrao, res.status, d?.detail);
}

// ── Autenticação ──
export function getToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem("token");
}
export function getUsuario(): any | null {
  if (typeof window === "undefined") return null;
  try { return JSON.parse(localStorage.getItem("usuario") || "null"); } catch { return null; }
}
// "Manter conectado neste aparelho" (checkbox no login) — gravado à parte do
// token pra outras partes do app saberem que esta é uma sessão de validade
// longa (90 dias, ver backend/fazenda/auth.py::TOKEN_VALIDADE_LONGA_S) sem
// precisar decodificar o token. Usado por lib/idle.ts (não desloga por
// inatividade numa sessão "manter conectado" — senão a promessa da checkbox
// vira letra morta) e por lib/nativo.ts (só espelha no armazenamento nativo
// as sessões marcadas assim).
export function manterConectadoAtivo(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem("manter_conectado") === "1";
}
// Piloto conservador de multi-fazenda (ver backend/fazenda/models/multitenant.py)
// — fazenda selecionada no login/troca de fazenda. Ausente para todo mundo
// que nunca teve mais de uma fazenda vinculada (o caso de hoje).
export type FazendaAtual = {
  id: number; nome: string; cidade?: string | null; uf?: string | null;
  vinculo_contador?: boolean; vinculo_consultor?: boolean; vinculo_contratante?: boolean;
  // Entrada sintética "Painel CowData" na tela de escolha do login (só para
  // EMAILS_DONO_EQUIVALENTE) — id=0 sentinela, nunca uma fazenda de verdade.
  // Ver fazenda/api/routers/auth.py::login.
  cowdata?: boolean;
  // Módulos comerciais ativos do CONTRATO desta fazenda (ver
  // fazenda.auth.exigir_modulo_contratado) — usado por
  // moduloContratadoPelaFazenda()/podeFormularDietas() para a Sidebar
  // esconder o que a fazenda não comprou. `undefined` (resposta antiga em
  // cache) não filtra nada; lista vazia É uma restrição de verdade.
  modulos_contratados?: string[];
  // Fazenda-sandbox (ex.: "Fazenda Teste", cópia da fazenda real Jairo
  // Nasser — ver ehFazendaTeste() abaixo e FazendaTesteBanner.tsx). Ausente
  // em respostas antigas do backend (rollout em andamento noutra frente) —
  // tratado como `false`, nunca como "não sei": mostrar a tarja errado por
  // padrão seria pior que não mostrar, mas o inverso (deixar de mostrar
  // numa fazenda de teste de verdade) é o risco que este campo existe pra
  // evitar, então o dia em que o backend passar a mandá-lo, a tarja aparece
  // sozinha sem precisar tocar neste arquivo de novo.
  eh_teste?: boolean;
};
export function getFazendaAtual(): FazendaAtual | null {
  if (typeof window === "undefined") return null;
  try { return JSON.parse(localStorage.getItem("fazenda_atual") || "null"); } catch { return null; }
}
// A fazenda ATUAL (não uma fazenda qualquer da lista) é o sandbox de testes?
// Único ponto de leitura de `eh_teste` — FazendaTesteBanner.tsx e qualquer
// outra tela que precise saber usam esta função, nunca o campo cru, para o
// default "ausente = false" (ver comentário em FazendaAtual acima) valer em
// todo lugar de uma vez só.
export function ehFazendaTeste(): boolean {
  return getFazendaAtual()?.eh_teste === true;
}
export function logout() {
  if (typeof window !== "undefined") {
    // Best-effort, sem aguardar — dentro do app nativo, remove o token FCM
    // deste aparelho (senão o próximo funcionário a usar o mesmo celular
    // continuaria recebendo as notificações do usuário que saiu) e apaga a
    // cópia nativa da sessão (senão um próximo login com "Manter conectado"
    // neste mesmo aparelho a restauraria). Fora do app, ambas não fazem nada.
    // Dispara antes do redirect pra dar a maior chance possível da requisição
    // sair antes da navegação.
    import("@/lib/nativo").then(({ removerPushNativo, limparSessaoNativa }) => {
      removerPushNativo();
      limparSessaoNativa();
    }).catch(() => {});
    localStorage.removeItem("token"); localStorage.removeItem("usuario"); localStorage.removeItem("fazenda_atual");
    localStorage.removeItem("manter_conectado"); localStorage.removeItem("modo_suporte"); localStorage.removeItem("conta_ativa");
    location.href = "/login";
  }
}
// Mapa rota → módulo (para menu e bloqueio de páginas).
export const ROTA_MODULO: Record<string, string> = {
  "/": "capa", "/indicadores": "indicadores", "/agenda": "agenda", "/lancamentos": "lancamentos", "/protocolos": "lancamentos",
  "/reproducao": "reproducao", "/analise-reprodutiva": "analise", "/relatorios": "reproducao", "/rebanho": "rebanho",
  "/ciclos-21-dias": "reproducao",
  "/producao": "producao", "/alimentacao": "alimentacao", "/sanidade": "sanidade", "/recria": "recria",
  "/financeiro": "financeiro", "/estoque": "estoque", "/pedidos": "pedidos", "/parametros": "parametros", "/upload": "upload",
  "/analise-relatorios": "indicadores",
};

// Mapa módulo do FRONTEND (ROTA_MODULO acima) -> módulo COMERCIAL do
// backend (fazenda.auth.exigir_modulo_contratado, wireup em main.py) — os
// nomes são diferentes dos dois lados por motivos históricos (a rota nasceu
// antes do piloto de planos/módulos). Só entram aqui os módulos com
// correspondência 1:1 clara e conferida contra main.py; os transversais
// (agenda, indicadores, parametros, upload, lancamentos, analise) não têm
// nenhum exigir_modulo_contratado no backend — ficam de fora de propósito.
const MODULO_CONTRATO: Record<string, string> = {
  rebanho: "rebanho", producao: "produtivo", recria: "produtivo", alimentacao: "alimentacao",
  sanidade: "sanitario", financeiro: "financeiro", estoque: "estoque", pedidos: "pedidos", reproducao: "reprodutivo",
};
// A FAZENDA (não o usuário) contratou este módulo? Espelha a trava de plano
// do backend — sem isso, um admin via qualquer plano enxergava "acesso
// integral" na Sidebar mesmo em fazenda Standard, só descobrindo a
// restrição ao clicar e levar 403 (bug real encontrado em produção).
// Ausência de `modulos_contratados` (token sem fazenda selecionada, ou
// resposta de login antiga em cache antes deste campo existir) não
// restringe nada — só passa a filtrar quando o backend manda a lista de
// verdade, igual ao "sem retroatividade" de get_fazenda_atual_id. Sessão de
// suporte sempre libera (getModoSuporte), espelhando o bypass adicionado em
// exigir_modulo_contratado para o mesmo caso.
export function moduloContratadoPelaFazenda(mod: string): boolean {
  if (getModoSuporte()) return true;
  const chaveComercial = MODULO_CONTRATO[mod];
  if (!chaveComercial) return true;
  const lista = getFazendaAtual()?.modulos_contratados;
  if (lista == null) return true;
  return lista.includes(chaveComercial);
}
// Permissão de módulo para o usuário logado (admin tem tudo) — E a fazenda
// precisa ter contratado esse módulo (ver moduloContratadoPelaFazenda acima).
export function podeModulo(mod: string): boolean {
  const u = getUsuario();
  if (!u) return false;
  if (!moduloContratadoPelaFazenda(mod)) return false;
  if (u.papel === "admin") return true;
  return Array.isArray(u.permissoes) && u.permissoes.includes(mod);
}
export function ehAdmin(): boolean {
  return getUsuario()?.papel === "admin";
}
// Proprietário da fazenda — único com acesso ao relatório de últimos acessos
// (ver backend/fazenda/auth.py::exigir_dono). O backend já resolve isso pelo
// e-mail cadastrado e devolve o booleano pronto em /auth/me e /auth/login.
export function ehDono(): boolean {
  return getUsuario()?.eh_dono === true;
}
// Membro da Equipe CowData com login próprio (ago/2026) — não é dono, mas
// entra no Painel CowData com acesso restrito às áreas liberadas (ver
// backend/fazenda/models/equipe_cowdata_acesso.py e
// fazenda/api/routers/auth.py::_publico). Usado por AuthShell.tsx (gate de
// /painel-cowdata) e pelo menu do painel (filtra por área).
export function ehMembroEquipeCowData(): boolean {
  return getUsuario()?.eh_equipe_cowdata === true;
}
export function areasPainelCowData(): string[] {
  return Array.isArray(getUsuario()?.areas_painel_cowdata) ? getUsuario().areas_painel_cowdata : [];
}
export function temAreaPainelCowData(area: string): boolean {
  return ehDono() || areasPainelCowData().includes(area);
}
// Tipos de Pessoa vinculados a um Usuario operador que recebem o menu
// restrito do app de campo — empreiteiro/prestador/diarista/funcionário
// não veem Aprovações nem Financeiro, e Protocolos sobe pro topo do menu.
// (Ver frontend/app/app/menu/page.tsx.)
const TIPOS_MENU_RESTRITO = ["Empreiteiro", "Prestador de serviços", "Diarista", "Funcionário"];
export function ehOperadorRestrito(): boolean {
  const u = getUsuario();
  if (!u || u.papel !== "operador") return false;
  const tipo = u.pessoa_tipo as string | null | undefined; // CSV de TipoPessoa.nome, ver backend/fazenda/api/routers/auth.py::_publico
  return !!tipo && TIPOS_MENU_RESTRITO.some((t) => tipo.includes(t));
}
// Contador externo da fazenda (vínculo UsuarioFazenda.contador) — login cai
// direto no Painel do Contador (/contador), casca própria, nunca a
// navegação normal da fazenda. Ver components/AuthShell.tsx.
export function ehContador(): boolean {
  return getFazendaAtual()?.vinculo_contador === true;
}
// Vínculo externo (veterinário/agrônomo convidado) — mesmo acesso de um
// funcionário comum dentro da fazenda, mas deve ficar de fora de
// funcionalidades sensíveis específicas (ex.: link para o banco de dados
// externo em Relatórios financeiros), mesmo com o módulo financeiro liberado.
export function ehConsultor(): boolean {
  return getFazendaAtual()?.vinculo_consultor === true;
}
// Formulação de Dietas (/dietas — portal próprio, ver components/dietas/
// DietasLayout.tsx): dono-equivalente (Alexandre Rodarte e Alexandre Scarpa)
// OU Consultor CowData vinculado a ESTA fazenda. Espelha
// backend/fazenda/auth.py::exigir_admin_ou_consultor_fazenda — eixo de
// acesso à parte, deliberadamente FORA de ROTA_MODULO/podeModulo (ver
// comentário no backend sobre por que isso não empilha com permissão comum).
//
// Mudou em ago/2026 (backlog #127): admin comum e o contratante da própria
// fazenda-cliente NÃO entram mais — é serviço prestado pela CowData, não
// autoatendimento. Consultor externo convidado pelo cliente também não: o
// vínculo `consultor` sozinho não basta, tem que ser Equipe CowData com
// cargo Consultor (eh_consultor_cowdata, calculado no backend).
export function podeFormularDietas(): boolean {
  const consultorCowDataNestaFazenda = getUsuario()?.eh_consultor_cowdata === true
    && getFazendaAtual()?.vinculo_consultor === true;
  // Sessão de suporte CowData passa, igual ao dono — é o mesmo bypass que o
  // backend já faz nessa dependência (sem vínculo NESTA fazenda-cliente, o
  // membro de suporte cairia no 403 apesar de precisar da tela pra ajudar).
  const acessoDeUsuario = ehDono() || getModoSuporte() != null || consultorCowDataNestaFazenda;
  if (!acessoDeUsuario) return false;
  // Módulo à-la-carte, fora de todo pacote do catálogo (ver planos.py) — a
  // FAZENDA precisa ter contratado à parte, mesmo sendo admin/dono/consultor
  // (nenhum bypass por papel no backend, ver exigir_modulo_contratado
  // aplicado junto com exigir_admin_ou_consultor_fazenda em main.py). Sessão
  // de suporte sempre libera, espelhando o mesmo bypass do backend.
  return moduloContratadoDireto("formulacao_dietas");
}
// Variante de moduloContratadoPelaFazenda() para módulos à-la-carte que não
// têm uma chave em ROTA_MODULO/MODULO_CONTRATO (não aparecem na Sidebar
// comum) — mesma regra de bypass por suporte e de "sem dado não bloqueia".
function moduloContratadoDireto(chaveComercial: string): boolean {
  if (getModoSuporte()) return true;
  const lista = getFazendaAtual()?.modulos_contratados;
  if (lista == null) return true;
  return lista.includes(chaveComercial);
}
// A FAZENDA contratou o módulo à-la-carte Formulação de Dietas? Diferente de
// podeFormularDietas() (que também exige ser dono/consultor CowData — eixo
// de acesso ao PORTAL de autoria /dietas): esta função só checa o módulo,
// para telas de uso comum (ex.: Alimentação > lançar dieta) que precisam
// saber se "importar dieta formulada" deve aparecer, sem restringir por
// quem pode CRIAR simulações.
export function moduloFormulacaoDietasAtivo(): boolean {
  return moduloContratadoDireto("formulacao_dietas");
}
// "Contratante-administrador": quem pode ver Configurações > Auditoria
// CowData (auditoria de acessos de suporte + Confiança e LGPD) — dono
// sempre pode; senão precisa ser admin desta fazenda E o vínculo
// contratante (o usuário mestre que contratou o plano), não qualquer admin.
// Espelha o gate real do backend (exigir_contratante_ou_dono, usado em
// GET /painel-cowdata/cofre/minha-fazenda/acoes).
export function ehContratanteAdministrador(): boolean {
  return ehDono() || (ehAdmin() && getFazendaAtual()?.vinculo_contratante === true);
}
// Administração de News/Blog (matérias: criar, editar, revisar, aprovar) —
// o dono sempre pode; além dele, só quem o dono designar via o toggle
// "Permitir publicação de matérias no blog" em Usuários (Usuario.pode_publicar_materias_blog).
// Ver backend/fazenda/auth.py::exigir_pode_publicar.
export function podePublicarMaterias(): boolean {
  return ehDono() || getUsuario()?.pode_publicar_materias_blog === true;
}
export async function fetchUsuarios() {
  const res = await fetch(`${API}/auth/usuarios`, { headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {}, cache: "no-store" });
  if (!res.ok) throw new Error(`Usuários error: ${res.status}`);
  return res.json();
}
export type UsuarioAcesso = { id: number; username: string; nome: string | null; papel: string; ativo: boolean; ultimo_login: string | null; ultimos_acessos: string[] };
export async function fetchAcessos(): Promise<UsuarioAcesso[]> {
  const res = await authFetch(`${API}/auth/usuarios/acessos`);
  if (!res.ok) throw new Error(`Acessos error: ${res.status}`);
  return res.json();
}

// ── Auditoria de atividade (lançamentos por usuário) — só o proprietário, ver ehDono() ──
export type AuditoriaTipo = { chave: string; label: string };
export type AuditoriaUsuario = { id: number; username: string; nome: string | null; ativo: boolean };
export type AuditoriaItem = { chave: string; label: string; id: number; data: string | null; resumo: string };
export async function fetchAuditoriaOpcoes(): Promise<{ tipos: AuditoriaTipo[]; usuarios: AuditoriaUsuario[] }> {
  const res = await authFetch(`${API}/auditoria/opcoes`);
  if (!res.ok) throw new Error(`Auditoria opções error: ${res.status}`);
  return res.json();
}
export async function fetchAuditoriaAtividades(params: { usuario_id: number; data_inicio?: string; data_fim?: string; chaves?: string[] }): Promise<{ usuario: AuditoriaUsuario; total: number; itens: AuditoriaItem[] }> {
  const qs = new URLSearchParams({ usuario_id: String(params.usuario_id) });
  if (params.data_inicio) qs.set("data_inicio", params.data_inicio);
  if (params.data_fim) qs.set("data_fim", params.data_fim);
  if (params.chaves && params.chaves.length) qs.set("chaves", params.chaves.join(","));
  const res = await authFetch(`${API}/auditoria/atividades?${qs}`);
  if (!res.ok) throw new Error(`Auditoria atividades error: ${res.status}`);
  return res.json();
}
export async function criarUsuario(dados: {
  username: string; senha: string; papel: string; permissoes: string[]; email?: string; pode_publicar_materias_blog?: boolean;
  // `pessoa_id` é o caminho: todo login nasce de uma pessoa já cadastrada
  // DENTRO de uma fazenda, e o backend cria o vínculo usuário↔fazenda no mesmo
  // commit (ver backend auth.py::_fazenda_do_novo_usuario — fazenda → pessoa →
  // usuário, sempre nessa ordem). `nome` livre, sem pessoa, é recusado com 400
  // em qualquer instalação com fazenda cadastrada; a equipe da própria CowData
  // tem tela própria (Painel CowData > Equipe), não passa por aqui.
  pessoa_id?: number; nome?: string;
}) {
  const res = await fetch(`${API}/auth/usuarios`, {
    method: "POST", headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar usuário"); }
  return res.json();
}
export async function atualizarUsuario(id: number, dados: any) {
  const res = await fetch(`${API}/auth/usuarios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar"); }
  return res.json();
}

export async function login(username: string, senha: string, manterConectado = false) {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, senha, manter_conectado: manterConectado }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(mensagemErroApi(d.detail) || "Usuário ou senha inválidos");
  }
  const data = await res.json();
  localStorage.setItem("token", data.token);
  localStorage.setItem("usuario", JSON.stringify(data.usuario));
  if (data.fazenda_atual) localStorage.setItem("fazenda_atual", JSON.stringify(data.fazenda_atual));
  else localStorage.removeItem("fazenda_atual");
  // "conta_ativa" (ver getContaAtivaId, abaixo) alimenta a tela-eixo de
  // troca de conta (EscolherConta.tsx) — só sabe marcar "Você está aqui" em
  // cima de uma escolha de verdade já feita. Login com auto-seleção (0 ou 1
  // fazenda vinculada, sem a opção Painel CowData) já conta como escolha
  // feita; quando o login devolve selecao_fazenda_necessaria, ainda não há
  // nada pra marcar até a escolha de verdade (ver selecionarFazenda/
  // entrarPainelCowData, mais abaixo).
  if (data.fazenda_atual) localStorage.setItem("conta_ativa", String(data.fazenda_atual.id));
  else localStorage.removeItem("conta_ativa");
  // Login de verdade encerra qualquer marcador de modo suporte de uma sessão
  // anterior — nunca deve sobreviver a um novo login.
  localStorage.removeItem("modo_suporte");
  // Sessão de validade longa (90 dias) — ver TOKEN_VALIDADE_LONGA_S no backend.
  if (manterConectado) localStorage.setItem("manter_conectado", "1");
  else localStorage.removeItem("manter_conectado");
  // Espelha a sessão no armazenamento nativo (@capacitor/preferences), mais
  // durável que o localStorage da WebView — só quando "Manter conectado" está
  // marcado (ver lib/nativo.ts::salvarSessaoNativa). Fora do app nativo não
  // faz nada. Best-effort, sem aguardar: não pode atrasar o login.
  if (manterConectado) {
    import("@/lib/nativo")
      .then(({ salvarSessaoNativa }) => salvarSessaoNativa(data.token, data.usuario, data.fazenda_atual || null, data.fazenda_atual ? String(data.fazenda_atual.id) : null))
      .catch(() => {});
  }
  // Paleta salva no cadastro do usuário tem prioridade sobre o que já estava no navegador.
  if (data.usuario?.paleta === "vinho" || data.usuario?.paleta === "verde" || data.usuario?.paleta === "azul") {
    document.documentElement.setAttribute("data-paleta", data.usuario.paleta);
    localStorage.setItem("paleta", data.usuario.paleta);
  }
  // Piloto conservador de multi-fazenda: quando o usuário está vinculado a
  // mais de uma fazenda, a página de login mostra a tela de escolha em vez
  // de navegar direto (ver POST /auth/selecionar-fazenda) — devolve a
  // resposta inteira (não só usuario) para o chamador checar isso.
  return data;
}

export async function selecionarFazenda(fazendaId: number): Promise<FazendaAtual> {
  const res = await fetch(`${API}/auth/selecionar-fazenda`, {
    method: "POST", headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: JSON.stringify({ fazenda_id: fazendaId }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao selecionar fazenda"); }
  const data = await res.json();
  localStorage.setItem("token", data.token);
  localStorage.setItem("fazenda_atual", JSON.stringify(data.fazenda_atual));
  // Ver comentário em login() — esta É a escolha de verdade que faltava.
  localStorage.setItem("conta_ativa", String(data.fazenda_atual.id));
  // Escolher a fazenda DIRETO (administrador) nunca carrega modo suporte.
  localStorage.removeItem("modo_suporte");
  // Mantém a cópia nativa sincronizada com o token novo (o backend reemite o
  // token ao trocar de fazenda) — mesma lógica de login(), ver lib/nativo.ts.
  if (manterConectadoAtivo()) {
    import("@/lib/nativo")
      .then(({ salvarSessaoNativa }) => salvarSessaoNativa(data.token, getUsuario(), data.fazenda_atual, String(data.fazenda_atual.id)))
      .catch(() => {});
  }
  return data.fazenda_atual;
}

export async function fetchMinhasFazendas(): Promise<FazendaAtual[]> {
  const res = await authFetch(`${API}/fazendas/minhas`);
  if (!res.ok) throw new Error(`Fazendas error: ${res.status}`);
  return res.json();
}

// ── Tela-eixo de troca de conta (ver components/EscolherConta.tsx e
// app/escolher-conta/page.tsx) ──

// Conta ativa neste aparelho AGORA — gravada a cada escolha de verdade (ver
// login/selecionarFazenda/entrarPainelCowData, acima e abaixo): 0 = Painel
// CowData, id>0 = a fazenda, null = nenhuma escolha feita ainda (janela
// entre o login e a tela de escolha, quando há mais de um acesso). Único
// ponto de leitura — EscolherConta.tsx usa isto pra saber qual opção
// mostrar esmaecida com "Você está aqui"; sem essa marcação a pessoa clica
// na própria conta achando que trocou, e nada acontece.
export function getContaAtivaId(): number | null {
  if (typeof window === "undefined") return null;
  const v = localStorage.getItem("conta_ativa");
  return v == null ? null : Number(v);
}

// Mesma lista (e o MESMO critério) que POST /auth/login devolve em
// "fazendas_disponiveis" — só que chamável a qualquer momento depois do
// login (ver GET /auth/contas-disponiveis no backend). Devolve a lista
// mesmo com 0 ou 1 opção: quem decide se vale a pena perguntar (> 1) é
// quem chama (AuthShell só pergunta sozinho ao abrir o app quando há
// escolha de verdade; o menu "Trocar de conta" pergunta sempre).
export async function fetchContasDisponiveis(): Promise<FazendaAtual[]> {
  const res = await authFetch(`${API}/auth/contas-disponiveis`);
  if (!res.ok) throw new Error(`Contas disponíveis error: ${res.status}`);
  const data = await res.json();
  return data.opcoes as FazendaAtual[];
}

// Reemite o token do usuário SEM a claim "fid" — o formato que o Painel
// CowData espera (ver backend/fazenda/auth.py::get_fazenda_atual_id).
// Necessário quando quem JÁ entrou numa fazenda (token com fid) pede para
// trocar para o Painel CowData: diferente da entrada logo após o login
// (onde o token que POST /auth/login emitiu já não tem fid, ver
// app/login/page.tsx), o token atual aqui tem fid gravado e não serve
// (ver POST /auth/entrar-painel-cowdata no backend — RESTRITO a
// dono-equivalente/Equipe CowData; nunca confiar só na UI escondendo a
// opção, o 403 de lá é a trava de verdade).
export async function entrarPainelCowData(): Promise<void> {
  const res = await authFetch(`${API}/auth/entrar-painel-cowdata`, { method: "POST" });
  if (!res.ok) throw await erroDaResposta(res, "Não foi possível entrar no Painel CowData");
  const data = await res.json();
  localStorage.setItem("token", data.token);
  // Painel CowData nunca tem fazenda selecionada (token sem fid, ver acima).
  localStorage.removeItem("fazenda_atual");
  localStorage.setItem("conta_ativa", "0");
  localStorage.removeItem("modo_suporte");
  if (manterConectadoAtivo()) {
    import("@/lib/nativo")
      .then(({ salvarSessaoNativa }) => salvarSessaoNativa(data.token, getUsuario(), null, "0"))
      .catch(() => {});
  }
}

// Ação de escolha na tela-eixo (EscolherConta.tsx / app/escolher-conta) —
// único ponto que sabe a diferença entre "escolheu uma fazenda de verdade"
// (POST /auth/selecionar-fazenda) e "escolheu o Painel CowData" (token sem
// fid, ver entrarPainelCowData acima); quem chama só decide para onde
// navegar depois.
export async function escolherConta(opcao: FazendaAtual): Promise<void> {
  if (opcao.cowdata) { await entrarPainelCowData(); return; }
  await selecionarFazenda(opcao.id);
}

// ── Planos comerciais e contrato por fazenda (Fase 2A, dono only) ──
// Ver backend/fazenda/models/planos.py e fazenda/api/routers/fazendas.py.
export type Fazenda = {
  id: number; nome: string; cidade?: string | null; uf?: string | null; ativa: boolean;
  tipo_documento?: "cpf" | "cnpj" | null; documento?: string | null; endereco?: string | null; cep?: string | null;
  representante_nome?: string | null; representante_cpf?: string | null;
  exige_aprovacao_suporte?: boolean;
};
export type ModuloComercial =
  | "rebanho" | "reprodutivo" | "produtivo" | "sanitario" | "financeiro"
  | "planejamento" | "pedidos" | "estoque" | "alimentacao" | "agricultura" | "consultor"
  | "formulacao_dietas";
export type PlanoNome = "standard" | "silver" | "gold" | "diamond";
export type ModuloDoContrato = { modulo: ModuloComercial; preco: number; ativo: boolean };
export type ContratoFazenda = {
  fazenda_id: number;
  status: "aguardando_aprovacao" | "ativo" | "suspenso" | null;
  plano: PlanoNome | null;
  aprovado_por_usuario_id?: number | null;
  data_fechamento?: string | null;
  modulos: ModuloDoContrato[];
  ciclo_pagamento: CicloPagamento;
  desconto_pct?: number;
  preco_mensal?: number;
  valor_total_ciclo?: number;
};
export type PlanoCatalogo = { nome: string; preco: number; modulos: ModuloComercial[] };
export type PrecoModulo = { modulo: ModuloComercial; preco: number };
export type AnexoContrato = { id: number; nome_arquivo: string; mime_type: string; tamanho_bytes: number; criado_em: string };

export async function fetchFazendas(): Promise<Fazenda[]> {
  const res = await authFetch(`${API}/fazendas/`);
  if (!res.ok) throw new Error(`Fazendas error: ${res.status}`);
  return res.json();
}
export async function criarFazenda(dados: { nome: string; cidade?: string; uf?: string }): Promise<Fazenda> {
  const res = await authFetch(`${API}/fazendas/`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar fazenda"); }
  return res.json();
}
export async function atualizarFazenda(fazendaId: number, dados: {
  nome?: string; cidade?: string; uf?: string;
  tipo_documento?: string; documento?: string; endereco?: string; cep?: string;
  representante_nome?: string; representante_cpf?: string; exige_aprovacao_suporte?: boolean;
}): Promise<Fazenda> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar fazenda"); }
  return res.json();
}
export async function fetchContratoFazenda(fazendaId: number): Promise<ContratoFazenda> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato`);
  if (!res.ok) throw new Error(`Contrato error: ${res.status}`);
  return res.json();
}
export async function definirContratoFazenda(
  fazendaId: number,
  dados: { plano: PlanoNome | null; modulos: { modulo: ModuloComercial; preco: number }[]; ciclo_pagamento?: CicloPagamento },
): Promise<ContratoFazenda> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao definir contrato"); }
  return res.json();
}
export async function aprovarContratoFazenda(fazendaId: number): Promise<ContratoFazenda> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/aprovar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao aprovar contrato"); }
  return res.json();
}
export async function suspenderContratoFazenda(fazendaId: number): Promise<ContratoFazenda> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/suspender`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao suspender contrato"); }
  return res.json();
}
export async function fetchPlanosCatalogo(): Promise<Record<PlanoNome, PlanoCatalogo>> {
  const res = await authFetch(`${API}/fazendas/catalogo/planos`);
  if (!res.ok) throw new Error(`Catálogo de planos error: ${res.status}`);
  return res.json();
}
// Cockpit do Painel CowData — ver app/painel-cowdata/.
export type ResumoCowData = {
  total_fazendas: number; mrr: number;
  ativo: number; aguardando_aprovacao: number; suspenso: number; sem_contrato: number;
};
export async function fetchResumoCowData(): Promise<ResumoCowData> {
  const res = await authFetch(`${API}/fazendas/catalogo/resumo-cowdata`);
  if (!res.ok) throw new Error(`Resumo CowData error: ${res.status}`);
  return res.json();
}
export async function fetchPrecosModulo(): Promise<PrecoModulo[]> {
  const res = await authFetch(`${API}/fazendas/catalogo/precos-modulo`);
  if (!res.ok) throw new Error(`Preços de módulo error: ${res.status}`);
  return res.json();
}
export async function atualizarPrecoModulo(modulo: ModuloComercial, preco: number): Promise<PrecoModulo> {
  const res = await authFetch(`${API}/fazendas/catalogo/precos-modulo/${modulo}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ modulo, preco }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar preço"); }
  return res.json();
}
export async function fetchAnexosContrato(fazendaId: number): Promise<AnexoContrato[]> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/anexos`);
  if (!res.ok) throw new Error(`Anexos error: ${res.status}`);
  return res.json();
}
export async function anexarContrato(fazendaId: number, file: File): Promise<AnexoContrato> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/anexos`, { method: "POST", body: fd });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao anexar contrato"); }
  return res.json();
}
export async function excluirAnexoContrato(anexoId: number): Promise<void> {
  const res = await authFetch(`${API}/fazendas/contrato/anexos/${anexoId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir anexo"); }
}
// Antes era um <a href> direto pro endpoint — mas ele exige Bearer token
// (backend/fazenda/api/routers/fazendas.py), então abrir a URL crua sem
// autenticação sempre dava 401. Segue o mesmo padrão de baixarArquivoAutenticado
// (definida mais abaixo neste arquivo).
export async function baixarAnexoContrato(anexoId: number, nomeArquivoFallback: string): Promise<void> {
  const res = await authFetch(`${API}/fazendas/contrato/anexos/${anexoId}`);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao baixar anexo"); }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = nomeArquivoFallback;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

// ── Painel Mestre CowData: Equipe própria (Sócio/Comercial/T.I./Financeiro/
// Marketing/Suporte) e Financeiro CowData (livro-caixa independente) ──
// Ver backend/fazenda/api/routers/painel_cowdata.py.
export type PessoaCowData = {
  id: number; nome: string; cargo: string;
  telefones: string[]; emails: string[];
  cpf_cnpj?: string | null; cep?: string | null;
  salario_base?: number | null; data_admissao?: string | null;
  observacoes?: string | null; ativo: boolean;
  rg?: string | null; genero?: string | null; estado_civil?: string | null;
  endereco_rua?: string | null; endereco_numero?: string | null; endereco_bairro?: string | null;
  endereco_cidade?: string | null; endereco_uf?: string | null;
  tipo_vinculo?: "funcionario" | "pj" | null; subtipo_pj?: string | null; pagamento_mensal?: number | null;
};
export type PessoaCowDataIn = {
  nome: string; cargo: string; telefones?: string[]; emails?: string[];
  cpf_cnpj?: string | null; cep?: string | null;
  salario_base?: number | null; data_admissao?: string | null;
  observacoes?: string | null; ativo?: boolean;
  rg?: string | null; genero?: string | null; estado_civil?: string | null;
  endereco_rua?: string | null; endereco_numero?: string | null; endereco_bairro?: string | null;
  endereco_cidade?: string | null; endereco_uf?: string | null;
  tipo_vinculo?: "funcionario" | "pj" | null; subtipo_pj?: string | null; pagamento_mensal?: number | null;
};
export const fetchTiposVinculoCowData = (): Promise<{ tipos_vinculo: string[]; subtipos_pj: string[] }> => _pcGet(`/equipe/tipos-vinculo`);
export type FolhaCowData = {
  id: number; pessoa_id: number; competencia: string; valor_bruto: number; descontos: number;
  valor_liquido: number; status: "pendente" | "pago"; data_pagamento?: string | null; observacao?: string | null;
};
export type FolhaCowDataIn = {
  competencia: string; valor_bruto: number; descontos?: number; valor_liquido: number;
  status?: "pendente" | "pago"; data_pagamento?: string | null; observacao?: string | null;
};
export type LancamentoCowData = {
  id: number; tipo: "receita" | "despesa"; categoria: string; descricao: string;
  contraparte?: string | null; valor: number; data: string; origem: "manual";
};
export type LancamentoCowDataIn = {
  tipo: "receita" | "despesa"; categoria: string; descricao: string; contraparte?: string | null; valor: number; data: string;
};
export type ResumoFinanceiroCowData = { receita: number; despesa: number; resultado: number };
export type MovimentoCowData = { data: string; tipo: "receita" | "despesa"; categoria: string; descricao: string; valor: number; saldo_acumulado: number };
export type FluxoCaixaCowDataMes = { competencia: string; entradas: number; saidas: number; saldo_mes: number; saldo_acumulado: number };
export type DreCowData = { ano: number; receita_total: number; despesas_por_categoria: Record<string, number>; despesa_total: number; resultado: number };

async function _pcGet(path: string) {
  const res = await authFetch(`${API}/painel-cowdata${path}`);
  if (!res.ok) throw new Error(`Painel CowData ${path}: ${res.status}`);
  return res.json();
}
async function _pcSend(path: string, method: string, body?: any) {
  const res = await authFetch(`${API}/painel-cowdata${path}`, {
    method, headers: { "Content-Type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Erro (${res.status})`); }
  return res.json();
}

export const fetchCargosCowData = (): Promise<string[]> => _pcGet(`/equipe/cargos`);
export const fetchEquipeCowData = (): Promise<PessoaCowData[]> => _pcGet(`/equipe/pessoas`);
export const criarMembroEquipeCowData = (d: PessoaCowDataIn): Promise<PessoaCowData> => _pcSend(`/equipe/pessoas`, "POST", d);
export const editarMembroEquipeCowData = (id: number, d: PessoaCowDataIn): Promise<PessoaCowData> => _pcSend(`/equipe/pessoas/${id}`, "PUT", d);
export const excluirMembroEquipeCowData = (id: number): Promise<{ ok: boolean }> => _pcSend(`/equipe/pessoas/${id}`, "DELETE");

// Consultores CowData disponíveis para vincular a uma fazenda-cliente —
// membros ATIVOS da Equipe CowData com cargo Consultor que já têm login
// ATIVO. Alimenta o seletor do plano Diamond/sob medida em FazendasAdmin.tsx.
export type ConsultorCowData = { pessoa_id: number; usuario_id: number; nome: string; username: string; email: string | null };
export const fetchConsultoresCowData = (): Promise<ConsultorCowData[]> => _pcGet(`/equipe/consultores`);

// Login + permissões de um membro no próprio Painel CowData (ago/2026) —
// ver AREAS_PAINEL_COWDATA no backend. Restrito ao dono (não ao membro logado).
export const AREAS_PAINEL_COWDATA = ["cockpit", "assinaturas", "fazendas", "financeiro", "equipe", "produto", "cofre", "confianca", "cadastros", "farmacia"] as const;
export type AreaPainelCowData = typeof AREAS_PAINEL_COWDATA[number];
export const LABEL_AREA_PAINEL_COWDATA: Record<AreaPainelCowData, string> = {
  cockpit: "Cockpit", assinaturas: "Assinaturas", fazendas: "Fazendas", financeiro: "Financeiro",
  equipe: "Equipe", produto: "Produtos e robôs", cofre: "Cofre de acesso (Suporte)", confianca: "Confiança e LGPD",
  cadastros: "Cadastros globais",
  // "farmacia" existe em AREAS_PAINEL_COWDATA (backend) desde que
  // painel_cowdata_farmacia.py nasceu, mas faltava aqui — sem ela o dono não
  // tinha como conceder a área e todo membro batia em 403 na Farmácia.
  farmacia: "Farmácia CowData",
};
// Nível de sigilo (#132) — quanto de uma fazenda-cliente este membro enxerga
// numa sessão de suporte (Cofre de acesso), eixo à parte de "áreas" (o que
// ele vê no Painel CowData). Rótulo/descrição aqui, não no componente, para
// qualquer outra tela que venha a mostrar o nível reusar o mesmo texto —
// pedido explícito: nunca expor "basico/tecnico/total" cru na interface.
export const NIVEIS_SIGILO_EQUIPE_COWDATA = ["basico", "tecnico", "total"] as const;
export type NivelSigiloEquipeCowData = typeof NIVEIS_SIGILO_EQUIPE_COWDATA[number];
export const LABEL_NIVEL_SIGILO_EQUIPE_COWDATA: Record<NivelSigiloEquipeCowData, string> = {
  basico: "Somente operação da fazenda",
  tecnico: "Operação + financeiro e custos",
  total: "Acesso completo",
};
export const DESCRICAO_NIVEL_SIGILO_EQUIPE_COWDATA: Record<NivelSigiloEquipeCowData, string> = {
  basico: "Vê rebanho, reprodução, sanidade, produção e estoque. Não vê financeiro, folha de pagamento, contratos nem custos.",
  tecnico: "Tudo do nível anterior, mais financeiro e custos (lançamentos, estoque valorado, indicadores de custo). Continua sem ver folha de pagamento, salários, rescisões, vales ou dados pessoais de funcionários.",
  total: "Vê tudo, sem restrição — igual a entrar na fazenda como administrador (ações destrutivas continuam bloqueadas em modo suporte, isso não muda).",
};
export type UsuarioEquipeCowData = {
  usuario_id: number; username: string; email: string; ativo: boolean; areas: string[];
  nivel_sigilo: NivelSigiloEquipeCowData;
  pode_suspender_assinatura: boolean; pode_acessar_fazendas: boolean; pode_alterar_cadastro: boolean;
  pode_modificar_suspender_plano: boolean; pode_emitir_auditar_contratos: boolean; pode_emitir_cobrancas: boolean;
  pode_vincular_usuarios: boolean; pode_cadastrar_usuarios: boolean;
  // Sete permissões de EDIÇÃO no próprio Painel CowData (set/2026) — ver
  // PERMISSOES_EDICAO_PAINEL_COWDATA no backend. Consulta continua vindo da
  // área; estas só liberam a escrita.
  pode_editar_cadastros_globais: boolean; pode_editar_touros_naab: boolean; pode_editar_farmacia: boolean;
  pode_consultar_usuarios: boolean; pode_editar_usuarios: boolean; pode_controlar_acesso_usuarios: boolean;
  pode_editar_news: boolean;
};
export type UsuarioEquipeCowDataIn = {
  username: string; email: string; senha?: string | null; ativo?: boolean; areas: string[];
  nivel_sigilo?: NivelSigiloEquipeCowData;
  pode_suspender_assinatura?: boolean; pode_acessar_fazendas?: boolean; pode_alterar_cadastro?: boolean;
  pode_modificar_suspender_plano?: boolean; pode_emitir_auditar_contratos?: boolean; pode_emitir_cobrancas?: boolean;
  pode_vincular_usuarios?: boolean; pode_cadastrar_usuarios?: boolean;
  pode_editar_cadastros_globais?: boolean; pode_editar_touros_naab?: boolean; pode_editar_farmacia?: boolean;
  pode_consultar_usuarios?: boolean; pode_editar_usuarios?: boolean; pode_controlar_acesso_usuarios?: boolean;
  pode_editar_news?: boolean;
};
// As sete permissões de EDIÇÃO no Painel CowData, na ordem em que o dono as
// pediu. `livre` marca aquelas cujo CONSULTAR não depende de permissão
// nenhuma — a tela precisa dizer isso em voz alta para ninguém achar que
// desmarcar a caixa esconde a informação.
export type CampoPermissaoEdicaoCowData =
  | "pode_editar_cadastros_globais" | "pode_editar_touros_naab" | "pode_editar_farmacia"
  | "pode_consultar_usuarios" | "pode_editar_usuarios" | "pode_controlar_acesso_usuarios"
  | "pode_editar_news";
export const PERMISSOES_EDICAO_PAINEL_COWDATA: {
  campo: CampoPermissaoEdicaoCowData; rotulo: string; ajuda: string; consultaLivre: boolean;
}[] = [
  { campo: "pode_editar_cadastros_globais", rotulo: "Pode editar cadastros globais?",
    ajuda: "Aplicar, renomear e desativar motivos, raças, grau de sangue, unidades de estoque e tipos/métodos reprodutivos nas fazendas-cliente.",
    consultaLivre: true },
  { campo: "pode_editar_touros_naab", rotulo: "Pode editar touros NAAB?",
    ajuda: "Cadastrar, editar, excluir, recarregar o catálogo padrão e importar a planilha do fornecedor. O catálogo é o mesmo para todas as fazendas.",
    consultaLivre: true },
  { campo: "pode_editar_farmacia", rotulo: "Pode editar a Farmácia CowData?",
    ajuda: "Criar e alterar categorias, princípios ativos e medicamentos do catálogo central, e propagá-los para as fazendas-cliente.",
    consultaLivre: true },
  { campo: "pode_consultar_usuarios", rotulo: "Pode consultar usuários das fazendas-cliente?",
    ajuda: "Ver a lista de pessoas e de logins de cada fazenda-cliente na tela Usuários.",
    consultaLivre: false },
  { campo: "pode_editar_usuarios", rotulo: "Pode editar usuários das fazendas-cliente?",
    ajuda: "Criar um login e alterar login/e-mail de quem já existe.",
    consultaLivre: false },
  { campo: "pode_controlar_acesso_usuarios", rotulo: "Pode controlar o acesso desses usuários?",
    ajuda: "Definir senha, papel, permissões de módulo e situação (ativo/inativo) — é o que decide quem entra e até onde vai. Vale também na criação do login.",
    consultaLivre: false },
  { campo: "pode_editar_news", rotulo: "Pode editar News?",
    ajuda: "Publicar, editar, excluir e revisar matérias do blog, e gerenciar as fotos delas.",
    consultaLivre: false },
];

export const fetchUsuarioEquipeCowData = (pessoaId: number): Promise<UsuarioEquipeCowData | null> => _pcGet(`/equipe/pessoas/${pessoaId}/usuario`);
export const criarUsuarioEquipeCowData = (pessoaId: number, d: UsuarioEquipeCowDataIn): Promise<UsuarioEquipeCowData> =>
  _pcSend(`/equipe/pessoas/${pessoaId}/usuario`, "POST", d);
export const editarUsuarioEquipeCowData = (pessoaId: number, d: UsuarioEquipeCowDataIn): Promise<UsuarioEquipeCowData> =>
  _pcSend(`/equipe/pessoas/${pessoaId}/usuario`, "PUT", d);

// Cadastros globais (Painel CowData > Cadastros): motivos/raças/grau de
// sangue/unidades de estoque/tipos e métodos de serviço reprodutivo,
// aplicáveis a todas as fazendas-cliente de uma vez ou só às selecionadas —
// ver backend/fazenda/api/routers/painel_cowdata_cadastros.py.
export type CategoriaCadastroCowData =
  | "motivo_baixa" | "motivo_movimentacao" | "raca" | "grau_sangue" | "tipo_servico"
  | "estoque_local" | "estoque_categoria" | "estoque_finalidade" | "estoque_unidade"
  | "estoque_unidade_embalagem" | "estoque_unidade_medida_embalagem";
export type FazendaCadastroCowData = { id: number; nome: string };
export type ItemCadastroCowData = { nome: string; fracao_holandes: number | null; em_fazendas: number[]; total_fazendas: number };
export type ItemMetodoCadastroCowData = { tipo_nome: string; nome: string; em_fazendas: number[]; total_fazendas: number };
export type AplicarCadastroResultado = { criados: number; atualizados: number; ja_existiam: number; total_fazendas: number };

export const fetchCategoriasCadastroCowData = (): Promise<{ chave: string; label: string }[]> => _pcGet(`/cadastros/categorias`);
export const fetchFazendasCadastroCowData = (): Promise<FazendaCadastroCowData[]> => _pcGet(`/cadastros/fazendas`);
export const fetchItensCadastroCowData = (categoria: CategoriaCadastroCowData): Promise<{ itens: ItemCadastroCowData[]; fazendas: FazendaCadastroCowData[] }> =>
  _pcGet(`/cadastros/${categoria}`);
export const aplicarItemCadastroCowData = (
  categoria: CategoriaCadastroCowData, dados: { nome: string; fracao_holandes?: number | null; fazenda_ids?: number[] | null },
): Promise<AplicarCadastroResultado> => _pcSend(`/cadastros/${categoria}/aplicar`, "POST", dados);
export const renomearItemCadastroCowData = (
  categoria: CategoriaCadastroCowData, dados: { nome_atual: string; novo_nome: string; fazenda_ids?: number[] | null },
): Promise<{ renomeados: number; pulados_por_conflito: number; nao_encontrados: number }> =>
  _pcSend(`/cadastros/${categoria}/renomear`, "PUT", dados);
export const desativarItemCadastroCowData = (
  categoria: CategoriaCadastroCowData, dados: { nome: string; fazenda_ids?: number[] | null },
): Promise<{ desativados: number }> => _pcSend(`/cadastros/${categoria}/desativar`, "POST", dados);

export const fetchMetodosCadastroCowData = (): Promise<{ itens: ItemMetodoCadastroCowData[]; fazendas: FazendaCadastroCowData[] }> =>
  _pcGet(`/cadastros/metodo_servico/listar`);
export const aplicarMetodoCadastroCowData = (
  dados: { tipo_nome: string; nome: string; fazenda_ids?: number[] | null },
): Promise<AplicarCadastroResultado & { sem_tipo_correspondente: number }> => _pcSend(`/cadastros/metodo_servico/aplicar`, "POST", dados);

// Usuários (Painel CowData > Usuários): login de operador de UMA
// fazenda-cliente escolhida explicitamente, sem entrar via modo suporte —
// ver backend/fazenda/api/routers/painel_cowdata_usuarios.py. Diferente de
// Cadastros globais, nunca "aplica em várias fazendas" — cada usuário é
// sempre de uma fazenda só.
export type PessoaUsuarioCowData = { id: number; nome: string; tipo: string; email: string | null; tem_usuario: boolean };
export type UsuarioCowData = {
  id: number; username: string; nome: string; papel: "admin" | "operador"; permissoes: string[]; ativo: boolean;
  email: string | null; pessoa_id: number | null; pessoa_nome: string | null; vinculo_contratante: boolean;
};
export type NovoUsuarioCowData = { pessoa_id: number; username: string; senha: string; papel: "admin" | "operador"; permissoes?: string[]; email?: string | null };
export type EditarUsuarioCowData = { username?: string; papel?: "admin" | "operador"; permissoes?: string[]; ativo?: boolean; senha?: string; email?: string | null };

export const fetchPessoasUsuarioCowData = (fazendaId: number): Promise<PessoaUsuarioCowData[]> => _pcGet(`/usuarios/${fazendaId}/pessoas`);
export const fetchUsuariosDaFazendaCowData = (fazendaId: number): Promise<UsuarioCowData[]> => _pcGet(`/usuarios/${fazendaId}`);
export const criarUsuarioDaFazendaCowData = (fazendaId: number, dados: NovoUsuarioCowData): Promise<UsuarioCowData> =>
  _pcSend(`/usuarios/${fazendaId}`, "POST", dados);
export const editarUsuarioDaFazendaCowData = (fazendaId: number, usuarioId: number, dados: EditarUsuarioCowData): Promise<UsuarioCowData> =>
  _pcSend(`/usuarios/${fazendaId}/${usuarioId}`, "PUT", dados);

// Parâmetros (Painel CowData > Parâmetros): mesma mecânica de Cadastros
// globais (aplicar em todas as fazendas-cliente ou só nas selecionadas),
// mas em cima de ParametroFazenda — ver backend/fazenda/api/routers/
// painel_cowdata_parametros.py. Só os 36 parâmetros de manejo/metas/agenda/
// RH/financeiro dessa tabela — não inclui a aba "Parâmetros financeiros" da
// fazenda (contas correntes, plano de contas, centro de custo), que guarda
// dado de identidade por fazenda e não faz sentido replicar.
export type ItemParametroCowData = {
  chave: string; label: string; grupo: string; tipo: "int" | "float" | "bool" | "date";
  unidade: string | null; valor_global: number | boolean | string | null;
  personalizado_em: number[]; total_personalizados: number;
};
export const fetchFazendasParametroCowData = (): Promise<FazendaCadastroCowData[]> => _pcGet(`/parametros/fazendas`);
export const fetchParametrosCowData = (): Promise<{ grupos: Record<string, { titulo: string; itens: ItemParametroCowData[] }> }> =>
  _pcGet(`/parametros/`);
export const aplicarParametroCowData = (
  chave: string, dados: { valor: number | boolean | string; fazenda_ids?: number[] | null },
): Promise<{ atualizados: number; total_fazendas: number; global_atualizado: boolean }> =>
  _pcSend(`/parametros/${chave}`, "PUT", dados);

export const fetchFolhaMembroCowData = (pessoaId: number): Promise<FolhaCowData[]> => _pcGet(`/equipe/pessoas/${pessoaId}/folha`);
export const lancarFolhaMembroCowData = (pessoaId: number, d: FolhaCowDataIn): Promise<FolhaCowData> =>
  _pcSend(`/equipe/pessoas/${pessoaId}/folha`, "POST", d);
export const editarFolhaCowData = (folhaId: number, d: FolhaCowDataIn): Promise<FolhaCowData> => _pcSend(`/equipe/folha/${folhaId}`, "PUT", d);
export const excluirFolhaCowData = (folhaId: number): Promise<{ ok: boolean }> => _pcSend(`/equipe/folha/${folhaId}`, "DELETE");

export const fetchCategoriasFinanceiroCowData = (): Promise<{ receita: string[]; despesa: string[] }> => _pcGet(`/financeiro/categorias`);
export const fetchLancamentosCowData = (de?: string, ate?: string): Promise<LancamentoCowData[]> => {
  const qs = new URLSearchParams();
  if (de) qs.set("de", de);
  if (ate) qs.set("ate", ate);
  const query = qs.toString();
  return _pcGet(`/financeiro/lancamentos${query ? `?${query}` : ""}`);
};
export const criarLancamentoCowData = (d: LancamentoCowDataIn): Promise<LancamentoCowData> => _pcSend(`/financeiro/lancamentos`, "POST", d);
export const editarLancamentoCowData = (id: number, d: LancamentoCowDataIn): Promise<LancamentoCowData> =>
  _pcSend(`/financeiro/lancamentos/${id}`, "PUT", d);
export const excluirLancamentoCowData = (id: number): Promise<{ ok: boolean }> => _pcSend(`/financeiro/lancamentos/${id}`, "DELETE");

export const fetchResumoFinanceiroCowData = (de: string, ate: string): Promise<ResumoFinanceiroCowData> =>
  _pcGet(`/financeiro/resumo?de=${de}&ate=${ate}`);
export const fetchLivroCaixaCowData = (de: string, ate: string): Promise<MovimentoCowData[]> =>
  _pcGet(`/financeiro/livro-caixa?de=${de}&ate=${ate}`);
export const fetchFluxoCaixaCowData = (de: string, ate: string): Promise<FluxoCaixaCowDataMes[]> =>
  _pcGet(`/financeiro/fluxo-caixa?de=${de}&ate=${ate}`);
export const fetchDreCowData = (ano: number): Promise<DreCowData> => _pcGet(`/financeiro/dre?ano=${ano}`);

// ── Cofre de acesso — pedido/sessão/auditoria de suporte por fazenda-cliente ──
// Ver backend/fazenda/models/cofre_acesso.py e fazenda/api/routers/cofre_acesso.py.
export type FazendaCofre = {
  id: number; nome: string; exige_aprovacao_suporte: boolean;
  plano_nome: string | null; modulos: string[];
};
export type PedidoAcessoSuporte = {
  id: number; protocolo: string | null; fazenda_id: number; fazenda_nome: string; usuario_id: number; solicitante_nome: string | null;
  modulos_contratados: string[];
  motivo: string; assunto_chamado: string | null; observacao: string | null; status: "aguardando_aprovacao" | "aprovado" | "negado";
  aprovador_nome: string | null; pedido_em: string; decidido_em: string | null;
  // Presentes só quando status vira "aprovado" na hora (fazenda sem
  // exige_aprovacao_suporte — ver POST /cofre/pedidos): token novo, já
  // com a claim "suporte", pronto pra substituir o token guardado e entrar
  // na fazenda como suporte. nivel_sigilo vem junto (#132) — o nível
  // carimbado nesse token, calculado a partir de PermissaoEquipeCowData de
  // quem pediu.
  token?: string; sessao_id?: number; sessao_expira_em?: string; nivel_sigilo?: NivelSigiloEquipeCowData;
  // Entrar em modo suporte também pode cair numa fazenda de teste (ex.:
  // suporte testando algo na Fazenda Teste) — propagado para FazendaAtual em
  // entrarComoSuporte() abaixo, mesma regra de "ausente = false" do campo em
  // FazendaAtual.
  eh_teste?: boolean;
};
export type SessaoAcessoSuporte = {
  id: number; protocolo: string | null; fazenda_id: number; fazenda_nome: string; usuario_id: number; membro_nome: string | null;
  motivo: string; assunto_chamado: string | null; nivel_sigilo: NivelSigiloEquipeCowData;
  iniciada_em: string; expira_em: string; encerrada_em: string | null;
  ativa: boolean; segundos_restantes: number;
};
export type AuditoriaAcessoSuporte = {
  id: number; quando: string; fazenda_id: number; fazenda_nome: string; usuario_id: number;
  membro_nome: string | null; acao: "entrada" | "saida"; nivel_sigilo: NivelSigiloEquipeCowData | null;
};
// Auditoria granular — uma linha por escrita (POST/PUT/PATCH/DELETE)
// tentada durante uma sessão de suporte (permitida ou bloqueada) e por
// LEITURA (GET) bloqueada por nível de sigilo (#132; leitura permitida não
// gera linha).
export type AcaoAuditoriaSuporte = {
  id: number; sessao_id: number; protocolo: string | null; fazenda_id: number; fazenda_nome: string;
  usuario_id: number; membro_nome: string | null; metodo: string; caminho: string;
  status_code: number | null; bloqueado: boolean; nivel_sigilo: NivelSigiloEquipeCowData | null; quando: string;
};

export const fetchMotivosAcessoSuporte = (): Promise<string[]> => _pcGet(`/cofre/motivos`);
export const fetchFazendasCofre = (): Promise<FazendaCofre[]> => _pcGet(`/cofre/fazendas`);
export const fetchSessoesAtivasCofre = (): Promise<SessaoAcessoSuporte[]> => _pcGet(`/cofre/sessoes-ativas`);
export const fetchPedidosRecentesCofre = (): Promise<PedidoAcessoSuporte[]> => _pcGet(`/cofre/pedidos`);
export const fetchAuditoriaRecenteCofre = (): Promise<AuditoriaAcessoSuporte[]> => _pcGet(`/cofre/auditoria`);
export const fetchAcoesSuporte = (sessaoId?: number): Promise<AcaoAuditoriaSuporte[]> =>
  _pcGet(`/cofre/acoes${sessaoId ? `?sessao_id=${sessaoId}` : ""}`);
// Lado do cliente: só a fazenda selecionada, só para contratante-admin dela
// (ou dono) — usado em Configurações > Auditoria CowData. Mesma rota
// /painel-cowdata/cofre/*, mas gated por exigir_contratante_ou_dono, não
// exigir_dono (ver fazenda/api/routers/cofre_acesso.py).
export const fetchAcoesSuporteDaMinhaFazenda = (): Promise<AcaoAuditoriaSuporte[]> => _pcGet(`/cofre/minha-fazenda/acoes`);
export const solicitarAcessoCofre = (d: { fazenda_id: number; motivo: string; assunto_chamado: string; observacao?: string }): Promise<PedidoAcessoSuporte> =>
  _pcSend(`/cofre/pedidos`, "POST", d);
export const aprovarPedidoCofre = (id: number): Promise<PedidoAcessoSuporte> => _pcSend(`/cofre/pedidos/${id}/aprovar`, "POST");
export const negarPedidoCofre = (id: number): Promise<PedidoAcessoSuporte> => _pcSend(`/cofre/pedidos/${id}/negar`, "POST");

// Marcador local de "estou numa fazenda como suporte CowData agora" — não
// vem de /auth/me (a claim "suporte" mora só no token, decodificá-lo no
// cliente pra isso seria mais complexo que só guardar o que a própria
// resposta de solicitarAcessoCofre já devolve). Gravado no momento em que o
// pedido de acesso é aprovado (entrarComoSuporte, abaixo) e limpo ao
// encerrar a sessão, fazer logout, ou logar/trocar de fazenda de novo.
export type ModoSuporte = {
  sessaoId: number; protocolo: string | null; fazendaNome: string; expiraEm: string;
  // Campos exigidos pela faixa fixa (ver SuporteBanner.tsx): nome de quem
  // entrou, hora exata da entrada e motivo escolhido — tudo isso já vem na
  // resposta do próprio pedido aprovado, sem chamada extra.
  membroNome: string; entradaEm: string; motivo: string;
  // Nível de sigilo desta sessão (#132) — mostrado na faixa pra quem está em
  // modo suporte não ser pego de surpresa por um 403 de "não alcança X".
  nivelSigilo: NivelSigiloEquipeCowData;
};
export function getModoSuporte(): ModoSuporte | null {
  if (typeof window === "undefined") return null;
  try { return JSON.parse(localStorage.getItem("modo_suporte") || "null"); } catch { return null; }
}
function limparModoSuporte() {
  localStorage.removeItem("modo_suporte");
}

/** Pede acesso de suporte a uma fazenda a partir do Painel CowData e, se
 *  aprovado na hora (caso normal — ver Fazenda.exige_aprovacao_suporte),
 *  já troca o token guardado pelo de suporte e devolve a fazenda pra
 *  navegar pra dentro dela. Lança se ficar "aguardando_aprovacao" (fazenda
 *  rara com essa trava ligada) — quem chamar deve tratar esse caso à parte. */
export async function entrarComoSuporte(
  fazendaId: number, motivo: string, assuntoChamado: string, observacao?: string,
): Promise<FazendaAtual> {
  const pedido = await solicitarAcessoCofre({ fazenda_id: fazendaId, motivo, assunto_chamado: assuntoChamado, observacao });
  if (pedido.status !== "aprovado" || !pedido.token || !pedido.sessao_id || !pedido.sessao_expira_em) {
    throw new Error("Pedido enviado, mas aguardando aprovação — essa fazenda exige aprovação prévia de acesso de suporte.");
  }
  localStorage.setItem("token", pedido.token);
  const fazendaAtual: FazendaAtual = { id: pedido.fazenda_id, nome: pedido.fazenda_nome, modulos_contratados: pedido.modulos_contratados, eh_teste: pedido.eh_teste };
  localStorage.setItem("fazenda_atual", JSON.stringify(fazendaAtual));
  const membroNome = getUsuario()?.nome || getUsuario()?.username || "Equipe CowData";
  localStorage.setItem("modo_suporte", JSON.stringify({
    sessaoId: pedido.sessao_id, protocolo: pedido.protocolo, fazendaNome: pedido.fazenda_nome,
    expiraEm: pedido.sessao_expira_em, membroNome, entradaEm: new Date().toISOString(), motivo,
    nivelSigilo: pedido.nivel_sigilo || "basico",
  } satisfies ModoSuporte));
  return fazendaAtual;
}

export async function encerrarModoSuporte(): Promise<void> {
  const modo = getModoSuporte();
  if (modo) await encerrarSessaoCofre(modo.sessaoId).catch(() => {});
  limparModoSuporte();
}
export const encerrarSessaoCofre = (id: number): Promise<SessaoAcessoSuporte> => _pcSend(`/cofre/sessoes/${id}/encerrar`, "POST");

// Piloto de fazenda-sandbox (ago/2026): "Fazenda Teste" é uma cópia completa
// da fazenda real Jairo Nasser para a equipe testar com dado realista. A
// sincronização é DESTRUTIVA no destino — apaga tudo da Fazenda Teste e
// recopia da origem — por isso o resultado devolve o tamanho da cópia
// (tabelas/linhas/duração) para a tela poder mostrar prova concreta do que
// aconteceu, não só um "ok" mudo. `origem_id` fixo em 1 (Jairo Nasser): hoje
// existe uma única fazenda real alimentando o sandbox — se um dia houver
// mais de uma origem possível, isto vira parâmetro da tela em vez de
// constante aqui.
export const ORIGEM_SINCRONIZACAO_FAZENDA_TESTE_ID = 1;
export type ResultadoSincronizacaoFazendaTeste = {
  status: "ok"; origem: string; destino: string; tabelas: number; linhas_copiadas: number; duracao_s: number; avisos: string[];
};
export async function sincronizarFazendaTeste(destinoId: number): Promise<ResultadoSincronizacaoFazendaTeste> {
  let res: Response;
  try {
    res = await authFetch(`${API}/painel-cowdata/fazendas/${destinoId}/sincronizar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origem_id: ORIGEM_SINCRONIZACAO_FAZENDA_TESTE_ID }),
    });
  } catch (e) {
    // TypeError = "Failed to fetch": aqui SIM é queda de conexão de verdade —
    // a cópia leva dezenas de segundos, tempo real de sobra pra um
    // proxy/gateway derrubar a conexão no meio do caminho (ver netError). Os
    // dois `if` abaixo (409/403) tratam respostas HTTP de verdade, nunca
    // devem reaproveitar esta mensagem de "sem conexão" — é exatamente o
    // engano que este trecho existe para não repetir (ver pedido do usuário).
    throw netError(e);
  }
  if (res.status === 409) {
    // Trava do backend: só se sincroniza POR CIMA de uma fazenda marcada como
    // teste — nunca sobrescrever sem querer uma fazenda real.
    throw await erroDaResposta(res, "Esta fazenda não é uma fazenda de teste — a sincronização só pode ter uma fazenda de teste como destino.");
  }
  if (res.status === 403) {
    throw await erroDaResposta(res, "Sem permissão de administrador CowData para sincronizar fazendas.");
  }
  if (!res.ok) {
    throw await erroDaResposta(res, `Falha ao sincronizar (HTTP ${res.status}).`);
  }
  return res.json();
}

// Contrato-modelo CowData ("Baixar contrato") e assinatura eletrônica via
// ZapSign ("Assinar contrato") — ver fazenda/rules/contrato_render.py e
// fazenda/rules/zapsign.py no backend.
export type CicloPagamento = "mensal" | "trimestral" | "semestral";
export type AssinaturaZapSign = {
  id: number; document_token: string; sign_url: string | null; status: string;
  criado_em: string; assinado_em: string | null;
} | null;

export async function baixarModeloContrato(fazendaId: number, dados?: {
  documento?: string; endereco?: string; representante_nome?: string; representante_cpf?: string;
  cidade_foro?: string; estado_foro?: string;
}): Promise<void> {
  const params = new URLSearchParams(Object.entries(dados || {}).filter(([, v]) => v) as [string, string][]);
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/modelo${params.toString() ? `?${params}` : ""}`);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao gerar o contrato"); }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `contrato-cowdata-fazenda-${fazendaId}.html`;
  a.click();
  URL.revokeObjectURL(url);
}
// Contrato do membro da Equipe CowData — CLT ou prestação de serviços PJ,
// escolhido pelo `tipo_vinculo` do cadastro (ver
// fazenda/rules/contrato_equipe_render.py). Mesmo fluxo de download do
// contrato de fazenda-cliente acima: baixa o HTML e salva como arquivo.
export async function baixarContratoMembroEquipe(pessoaId: number, dados?: {
  funcao?: string; local_prestacao?: string; jornada_semanal?: string; experiencia_dias?: string;
  objeto_servico?: string; dia_pagamento?: string; vigencia?: string;
  representante_nome?: string; representante_cpf?: string;
  cidade_foro?: string; estado_foro?: string;
}): Promise<void> {
  const params = new URLSearchParams(Object.entries(dados || {}).filter(([, v]) => v) as [string, string][]);
  const res = await authFetch(`${API}/painel-cowdata/equipe/pessoas/${pessoaId}/contrato${params.toString() ? `?${params}` : ""}`);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao gerar o contrato"); }
  const blob = await res.blob();
  // O backend já devolve o nome certo (contrato-clt-<nome>.html /
  // contrato-pj-<nome>.html) no Content-Disposition — reaproveita em vez de
  // remontar o nome aqui e arriscar divergir do arquivo servido.
  const nome = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1] || `contrato-${pessoaId}.html`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  URL.revokeObjectURL(url);
}
export async function assinarContratoZapSign(fazendaId: number): Promise<AssinaturaZapSign> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/assinar-zapsign`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar assinatura no ZapSign"); }
  return res.json();
}
export async function fetchStatusAssinaturaZapSign(fazendaId: number): Promise<AssinaturaZapSign> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/assinatura-zapsign`);
  if (!res.ok) throw new Error(`Status de assinatura error: ${res.status}`);
  return res.json();
}

// Cobrança da assinatura via Asaas — ver fazenda/rules/asaas.py.
export type CobrancaAsaasIn = { pagador_nome: string; pagador_documento: string; pagador_email?: string };
export type CobrancaAsaas = {
  id: number; tipo: "assinatura_mensal" | "pix_semestral" | "boleto"; valor: number;
  status: string; criado_em: string; pago_em: string | null;
};
async function _postAsaas(path: string, dados: CobrancaAsaasIn): Promise<any> {
  const res = await authFetch(`${API}/asaas/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar cobrança no Asaas"); }
  return res.json();
}
export const criarAssinaturaAsaas = (fazendaId: number, dados: CobrancaAsaasIn) => _postAsaas(`${fazendaId}/assinatura`, dados);
export const criarPixSemestralAsaas = (fazendaId: number, dados: CobrancaAsaasIn) => _postAsaas(`${fazendaId}/pix-semestral`, dados);
export const criarBoletoAsaas = (fazendaId: number, dados: CobrancaAsaasIn) => _postAsaas(`${fazendaId}/boleto`, dados);
export async function fetchCobrancasAsaas(fazendaId: number): Promise<CobrancaAsaas[]> {
  const res = await authFetch(`${API}/asaas/${fazendaId}`);
  if (!res.ok) throw new Error(`Cobranças error: ${res.status}`);
  return res.json();
}

// Vínculo de usuário a uma fazenda — contratante (administra a fazenda),
// consultor externo (veterinário/agrônomo; só aceito em fazenda com módulo
// "consultor" contratado — plano Diamond) ou contador externo (sem gate de
// plano, mas cai direto no Painel do Contador — só Financeiro, só leitura/
// exportação). Ver Fase 2B e fazenda/models/multitenant.py::UsuarioFazenda.
export type UsuarioVinculado = { usuario_id: number; username: string; nome: string | null; contratante: boolean; consultor: boolean; contador: boolean };

export async function fetchUsuariosVinculados(fazendaId: number): Promise<UsuarioVinculado[]> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/usuarios`);
  if (!res.ok) throw new Error(`Usuários vinculados error: ${res.status}`);
  return res.json();
}
// `usuario_id` OU `username` — o backend aceita os dois (ver
// fazendas.py::VincularUsuarioIn). O seletor de Consultor CowData usa o id,
// que ele já conhece; a caixa de vínculo manual usa o username digitado.
export async function vincularUsuarioFazenda(
  fazendaId: number,
  dados: { username?: string; usuario_id?: number; contratante?: boolean; consultor?: boolean; contador?: boolean },
): Promise<{ vinculado: boolean; usuario_id: number; username: string }> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/vincular-usuario`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao vincular usuário"); }
  return res.json();
}
export async function desvincularUsuarioFazenda(fazendaId: number, usuarioId: number): Promise<void> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/vincular-usuario/${usuarioId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao desvincular usuário"); }
}
export async function editarVinculoUsuarioFazenda(
  fazendaId: number, usuarioId: number, dados: { contratante?: boolean; consultor?: boolean; contador?: boolean },
): Promise<UsuarioVinculado> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/vincular-usuario/${usuarioId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar o vínculo"); }
  return res.json();
}

// Fluxo "Esqueci minha senha" — 3 passos: verificar se o login existe (e
// devolver o e-mail mascarado), pedir o envio do e-mail de redefinição, e
// finalmente trocar a senha com o token recebido por e-mail.
export type EsqueciSenhaVerificacao = { existe: boolean; tem_email?: boolean; email_mascarado?: string };

export async function verificarLoginParaResetSenha(username: string): Promise<EsqueciSenhaVerificacao> {
  const res = await fetch(`${API}/auth/esqueci-senha/verificar`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  if (!res.ok) throw new Error("Não foi possível verificar o login agora.");
  return res.json();
}

export async function enviarResetSenha(username: string): Promise<void> {
  const res = await fetch(`${API}/auth/esqueci-senha/enviar`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(mensagemErroApi(d.detail) || "Não foi possível enviar o e-mail de redefinição.");
  }
}

export async function redefinirSenha(token: string, novaSenha: string): Promise<void> {
  const res = await fetch(`${API}/auth/redefinir-senha`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, nova_senha: novaSenha }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(mensagemErroApi(d.detail) || "Não foi possível redefinir a senha.");
  }
}

// Preferência pessoal de paleta de cores (Vinho/Verde/Azul) — cada usuário guarda a sua.
export async function salvarPreferenciaPaleta(paleta: "vinho" | "verde" | "azul") {
  return salvarPreferencias({ paleta });
}

// Reivindicar o acesso de proprietário sem precisar saber/digitar o e-mail
// exato que o backend usa como identificador (EMAIL_DONO) — evita o erro
// comum de digitar o próprio e-mail pessoal ali, achando que é isso que
// libera o Controle de Acesso (aquele fluxo antigo só salvava um contato
// comum e nunca promovia ninguém). Backend aplica as mesmas travas de sempre
// (precisa ser admin, e ninguém mais pode já ser dono).
export async function reivindicarProprietario() {
  return salvarPreferencias({ reivindicar_proprietario: true });
}

async function salvarPreferencias(dados: { paleta?: "vinho" | "verde" | "azul"; email?: string; reivindicar_proprietario?: boolean }) {
  const res = await fetch(`${API}/auth/preferencias`, {
    method: "PUT", headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar preferência"); }
  const usuario = await res.json();
  try {
    const atual = getUsuario();
    if (atual) localStorage.setItem("usuario", JSON.stringify({ ...atual, ...usuario }));
  } catch { /* ignore */ }
  return usuario;
}

// fetch com token; redireciona ao login se a sessão cair (401), e à tela de
// escolha de conta se a sessão não disser em qual fazenda ela está (409 com o
// cabeçalho X-Fazenda-Nao-Selecionada).
// Exportado para a fila offline do app móvel (lib/offline.ts) reutilizar.
export function authFetch(url: string, opts: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(opts.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...opts, headers, cache: "no-store" }).then(async (res) => {
    if (res.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      logout();
    }
    // A trava de tenant do backend (fazenda/auth.py::exigir_fazenda_selecionada)
    // recusa qualquer rota de fazenda quando o token não diz em qual fazenda a
    // requisição acontece. Quem cai aqui é sobretudo quem já estava logado com
    // um token antigo, de antes do multi-fazenda: para essa pessoa o certo é
    // escolher a conta, não ver um erro. Só o cabeçalho identifica esta recusa
    // — 409 sozinho é status de negócio em várias outras rotas. A sessão NÃO é
    // descartada (ao contrário do 401): o login continua válido, só falta
    // escolher onde entrar.
    if (
      res.status === 409 && typeof window !== "undefined" &&
      !location.pathname.startsWith("/escolher-conta") && !location.pathname.startsWith("/login")
    ) {
      // Cabeçalho é o caminho rápido (navegador normal). Fallback pelo CORPO
      // (`detail.codigo`) — bug relatado em 12/09/2026: no app Android
      // empacotado (Capacitor, capacitor.config.ts -> CapacitorHttp:{enabled:
      // true}), toda requisição passa pela ponte nativa (OkHttp) em vez do
      // fetch da WebView, e essa ponte nem sempre repassa cabeçalhos de
      // resposta CUSTOMIZADOS pro objeto Response que o JS enxerga — um
      // funcionário ficava preso vendo "Não foi possível carregar a agenda"
      // em vez de cair aqui. `res.clone()` porque quem chamou `authFetch`
      // ainda vai ler o corpo desta mesma resposta depois.
      let precisaEscolherConta = !!res.headers.get("X-Fazenda-Nao-Selecionada");
      if (!precisaEscolherConta) {
        try {
          const corpo = await res.clone().json();
          precisaEscolherConta = corpo?.detail?.codigo === "fazenda_nao_selecionada";
        } catch { /* corpo não é JSON, ou não deu pra ler — segue sem redirecionar */ }
      }
      if (precisaEscolherConta) location.href = "/escolher-conta";
    }
    return res;
  }).catch((e) => {
    // Falha de rede (fetch rejeitado) — NÃO é HTTP: a requisição nem chegou a
    // receber resposta. Diferente do 401 acima, aqui a sessão NÃO é descartada:
    // só avisamos a UI (banner de "sem conexão" via evento) e re-propaga o erro
    // tipado para quem chamou. Não toca em getToken()/logout() nem no 409.
    const erro = netError(e);
    if (erro instanceof NetworkError && typeof window !== "undefined") {
      window.dispatchEvent(new Event("cowdata:offline"));
    }
    throw erro;
  });
}

// Erro tipado para "a rede caiu" (fetch rejeitado), distinto de HTTP 4xx/5xx.
// Estende TypeError (e não Error) de propósito: os loops de retry existentes
// (fetchComRetry) checam `instanceof TypeError` para decidir se vale tentar de
// novo — NetworkError precisa continuar entrando nesse grupo.
export class NetworkError extends TypeError {
  constructor(mensagem: string) {
    super(mensagem);
    this.name = "NetworkError";
  }
}

// Traduz o "Failed to fetch" (erro de rede do navegador) numa mensagem acionável.
// Esse erro NÃO é HTTP — significa que a requisição não chegou a receber resposta:
// API fora do ar, NEXT_PUBLIC_API_URL não configurada/errada, ou CORS bloqueado.
function netError(e: unknown): Error {
  if (e instanceof NetworkError) return e;
  if (e instanceof TypeError) {
    return new NetworkError(
      `Sem conexão com a API (${API}). ` +
        `Verifique se o backend está no ar e se NEXT_PUBLIC_API_URL aponta para ele (e se o CORS libera este site).`
    );
  }
  return e instanceof Error ? e : new Error(String(e));
}

// Mesma origem de erro que netError (TypeError = "Failed to fetch"), mas para
// chamadas de processamento pesado (OCR de documento, leitura de XML) onde a
// causa típica é o proxy/gateway derrubando a conexão por demora, não a API
// estar de fato fora do ar — a mensagem genérica de netError ("verifique se o
// backend está no ar / CORS") é enganosa aqui e assustava o usuário mesmo com
// o salvamento manual funcionando normalmente em seguida.
function netErrorProcessamento(e: unknown, oQue: string): Error {
  if (e instanceof TypeError) {
    return new Error(
      `A leitura automática ${oQue} demorou demais e a conexão caiu no meio do caminho. ` +
        `Nada foi lançado por causa disso — pode preencher os campos manualmente ou tentar de novo.`
    );
  }
  return e instanceof Error ? e : new Error(String(e));
}

// Reexecuta uma chamada que falhou por "Failed to fetch" (TypeError — sem
// resposta nenhuma do servidor, não um erro de negócio 4xx/5xx) até
// `tentativas` vezes, com pausa crescente entre elas. Extraído do padrão já
// usado em criarLancamentoFinanceiro/marcarPagoFinanceiro para não repetir a
// mesma lacuna de proteção numa função nova — essa assimetria (só algumas
// telas de Financeiro toleram uma queda momentânea de conexão) já foi
// reportada 3x pelo usuário (agentes #174/#192 e o relato de 04/09/2026).
async function fetchComRetry(fazer: () => Promise<Response>, tentativas = 3): Promise<Response> {
  let ultimoErro: unknown;
  for (let tentativa = 0; tentativa < tentativas; tentativa++) {
    try {
      return await fazer();
    } catch (e) {
      if (!(e instanceof TypeError)) throw netError(e);
      ultimoErro = e;
      if (tentativa < tentativas - 1) await new Promise((r) => setTimeout(r, 600 * (tentativa + 1)));
    }
  }
  throw netError(ultimoErro);
}

// Verifica se o backend responde. Usado pelo indicador de status.
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await authFetch(`${API}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchAgenda(data?: string, dias?: number) {
  const qs = new URLSearchParams();
  if (data) qs.set("data", data);
  if (dias) qs.set("dias", String(dias));
  const url = `${API}/agenda/${qs.toString() ? `?${qs}` : ""}`;
  const res = await authFetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Agenda error: ${res.status}`);
  return res.json();
}

export type MedicamentoIatf = {
  produto: string; estoque_id?: number | null;
  // "de qual lote/frasco de COMPRA?" (Fase G) — só usado hoje pelo protocolo
  // Sanitário na Central (ver DetalheCentralProtocolo.dias[].hormonios[].opcoes[].lotes);
  // IATF/Indução ainda ignoram este campo no backend.
  lote_id?: number | null;
  dose?: number | null; unidade?: string | null; via?: string | null;
};
// Cronograma sanitário (ver fazenda/rules/cronograma_sanitario.py) + overrides
// de aplicação agendada — cada campo só é lido pelo prefixo de evento_id
// correspondente no backend (agenda.py::RealizadoIn), ignorado nos demais.
export type RealizadoExtras = {
  incluir?: boolean;                    // cronograma_sanitario_animal_ — incluir/excluir o animal
  modo?: "veterinario" | "propria";     // cronograma_sanitario_modo_/_urgente_ — decisão de execução
  veterinario_pessoa_id?: number;       // idem, quando modo="veterinario"
  nova_data?: string;                   // idem — presente = adiar em vez de decidir
  motivo?: string;                      // idem — motivo do adiamento (opcional)
  responsavel?: string;                 // cronograma_sanitario_aplicar_ / aplic_agendada_
  observacao?: string;                  // idem
  produto?: string; dose?: number; unidade?: string; via?: string; // overrides de aplicação agendada
  // Checklist da Ocorrência (redesenho do evento sanitário) — cronograma_sanitario_checklist_.
  acao?: "pular";                       // ausente = confirma o item (comportamento decidido pela chave já gravada nele)
  resposta?: string;                    // "sim"/"nao" (item vet) ou horário (item horario)
  numero_matriz?: string;               // cronograma_sanitario_incluir_manual_ — animal a incluir fora da janela
};
export async function marcarEventoRealizado(eventoId: string, animais?: string[], medicamentos?: MedicamentoIatf[], extras?: RealizadoExtras) {
  const res = await authFetch(`${API}/agenda/realizados`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      evento_id: eventoId, animais: animais || undefined, medicamentos: medicamentos && medicamentos.length ? medicamentos : undefined,
      ...(extras || {}),
    }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao marcar como realizado"); }
  return res.json();
}

export async function desmarcarEventoRealizado(eventoId: string) {
  const res = await authFetch(`${API}/agenda/realizados/${eventoId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erro ao desfazer");
  return res.json();
}

export async function aplicarBstLote(dados: {
  numeros_matriz: string[]; data_aplicacao: string; produto?: string; dose?: number | null; unidade?: string | null; responsavel?: string; aplicado?: boolean;
  // true (padrão) = `dose` é a dose de UM animal; false = `dose` é o TOTAL do
  // lote selecionado, e o backend divide por numeros_matriz.length antes de
  // gravar/baixar — evita confundir total com por-animal no estoque/relatório.
  dose_por_animal?: boolean;
}) {
  const res = await authFetch(`${API}/agenda/bst/aplicar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar aplicação de BST"); }
  return res.json();
}

export async function marcarInaptaBst(dados: { numeros_matriz: string[]; inapta?: boolean }) {
  const res = await authFetch(`${API}/agenda/bst/marcar-inapta`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao marcar animal como inapto"); }
  return res.json();
}

export async function fetchProtocoloIatfConcluidos() {
  const res = await authFetch(`${API}/agenda/protocolo-iatf/concluidos`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao buscar protocolos IATF concluídos");
  return res.json();
}

export async function fetchProtocoloInducaoConcluidos() {
  const res = await authFetch(`${API}/agenda/protocolo-inducao-lactacao/concluidos`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao buscar induções de lactação concluídas");
  return res.json();
}

// ── Protocolo de indução de lactação (Lançamentos > Produção) ──
export async function fetchProtocolosInducaoLactacao() {
  const res = await authFetch(`${API}/producao/protocolos-inducao-lactacao`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao buscar protocolos de indução de lactação");
  return res.json();
}
export async function lancarInducaoLactacao(dados: {
  protocolo_id: number; animais: string[]; data_d0: string; responsavel?: string; observacao?: string;
}) {
  const res = await authFetch(`${API}/producao/inducao-lactacao`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar indução de lactação"); }
  return res.json();
}
export async function fetchInducaoLactacaoAtivos() {
  const res = await authFetch(`${API}/producao/inducao-lactacao/ativos`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao buscar induções de lactação em andamento");
  return res.json();
}

// ── Cadastro do protocolo de indução de lactação (Configurações > Cadastro >
// Sanitário > Indução de lactação) — CRUD completo; a leitura acima
// (fetchProtocolosInducaoLactacao, /producao/...) é só o seletor enxuto usado
// na hora de lançar. ──
export type EtapaInducaoLactacao = {
  id?: number;
  dia: number;
  tipo: "medicamento" | "dispositivo" | "manejo";
  principio_ativo_id?: number | null;
  produto: string;
  acao_dispositivo?: "colocar" | "retirar" | null;
  dose?: number | null;
  unidade?: string | null;
  via?: string | null;
};
export type ProtocoloInducaoLactacaoPayload = {
  nome: string;
  dia_inicial: number;
  observacao?: string;
  ativo: boolean;
  etapas: EtapaInducaoLactacao[];
};
export type ProtocoloInducaoLactacaoCadastro = ProtocoloInducaoLactacaoPayload & { id: number; criado_em: string };

export async function fetchProtocolosInducaoLactacaoCadastro(): Promise<ProtocoloInducaoLactacaoCadastro[]> {
  const res = await authFetch(`${API}/cadastro/protocolos-inducao-lactacao`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao buscar protocolos de indução de lactação");
  return res.json();
}
export async function criarProtocoloInducaoLactacao(dados: ProtocoloInducaoLactacaoPayload) {
  const res = await authFetch(`${API}/cadastro/protocolos-inducao-lactacao`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar protocolo de indução de lactação"); }
  return res.json();
}
export async function atualizarProtocoloInducaoLactacao(id: number, dados: ProtocoloInducaoLactacaoPayload) {
  const res = await authFetch(`${API}/cadastro/protocolos-inducao-lactacao/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar protocolo de indução de lactação"); }
  return res.json();
}
// G8 — espelha excluir_protocolo_sanitario/excluir_protocolo_iatf_cadastrado:
// 409 se o protocolo já foi lançado ao menos uma vez (usar `ativo: false` em vez disso).
export async function excluirProtocoloInducaoLactacao(id: number) {
  const res = await authFetch(`${API}/cadastro/protocolos-inducao-lactacao/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir protocolo de indução de lactação"); }
  return res.json();
}

// Produção do animal AO VIVO, em GET /animais/ — do ControleLeiteiro mais
// recente lançado no app, caindo para o campo congelado `ult_cl_kg` (CSV do
// Ideagri) só para quem nunca teve controle lançado. `producao_origem` existe
// para a tela poder dizer de onde o número veio: "congelado" é dado que não
// anda mais, e o usuário tem direito de saber olhando.
export type ProducaoOrigem = "controle" | "congelado";

export type AnimalProducaoAoVivo = {
  producao_kg: number | null;
  producao_data: string | null;
  producao_origem: ProducaoOrigem | null;
};

export async function fetchAnimais(params?: { grupo?: string; sit_rep?: string; incluirMachos?: boolean }) {
  const qs = new URLSearchParams();
  if (params?.grupo) qs.set("grupo", params.grupo);
  if (params?.sit_rep) qs.set("sit_rep", params.sit_rep);
  if (params?.incluirMachos) qs.set("incluir_machos", "true");
  const res = await authFetch(`${API}/animais/?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Animais error: ${res.status}`);
  return res.json();
}

export async function fetchFichaAnimal(numero: string) {
  const res = await authFetch(`${API}/animais/${encodeURIComponent(numero)}/ficha`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Ficha do animal error: ${res.status}`); }
  return res.json();
}

// Bloco "producao" de GET /indicadores/ (fazenda/rules/indicadores.py::calcular_indicadores).
// Contrato único das quatro telas que mostram produção — Capa, Indicadores,
// e as duas do app. Antes cada uma redeclarava seu próprio tipo parcial sobre
// um `any`, e foi por aí que o card e a lista passaram a mostrar números
// diferentes com o mesmo nome sem ninguém notar.
//
// A separação que este tipo torna explícita:
//   - o bloco de cima é O CONTROLE DO DIA: `producao_total_dia_kg` é a soma
//     exata das linhas de `controle_nums` na data `data_controle`. O card é a
//     soma da sua própria lista por construção, não por coincidência;
//   - `ultimo_por_animal` é o acumulado antigo (último controle de CADA vaca,
//     em qualquer data, com fallback para o campo congelado do CSV). Continua
//     disponível, mas com nome que diz o que ele é.
export type IndicadoresProducaoUltimoPorAnimal = {
  producao_total_kg: number;
  producao_media_kg: number | null;
  vacas_com_producao: number;
  /** Quantas vieram de um ControleLeiteiro lançado no app. */
  de_controle: number;
  /** Quantas ainda vêm de Animal.ult_cl_kg (CSV do Ideagri, importação aposentada). */
  congelado: number;
  congelado_nums: string[];
};

export type IndicadoresProducao = {
  /** Dia do controle leiteiro mais recente lançado. null = nenhum controle. */
  data_controle: string | null;
  producao_total_dia_kg: number;
  producao_media_kg: number | null;
  vacas_no_controle: number;
  /** Números das matrizes controladas em `data_controle` — a lista do card. */
  controle_nums: string[];
  vacas_lactacao: number;
  cobertura_controle_pct: number | null;
  /** DEL médio AO VIVO (último parto, zerado por secagem posterior). */
  del_medio: number | null;
  del_medio_animais: number;
  ultimo_por_animal: IndicadoresProducaoUltimoPorAnimal;
  /** Compatibilidade: igual a `vacas_no_controle`. */
  vacas_com_producao: number;
};

// Bloco "reproducao_categorias.<todas|vaca|novilha>" de GET /indicadores/
// (fazenda/rules/indicadores.py::_reproducao_categorias). Cada contador vem
// pareado com o `_nums` do MESMO objeto — é o que `lib/cartaoDrillDown.ts`
// exige ao ler os dois campos: não dá para escrever `conta: "prenhes"` e
// `nums: "aptas_nums"` sem que o par exista de verdade neste tipo.
export type ReproducaoCategoria = {
  aptas: number; aptas_nums: string[];
  prenhes: number; prenhes_nums: string[];
  vazias: number; vazias_nums: string[];
  inseminadas: number; inseminadas_nums: string[];
  pev: number; pev_nums: string[];
  a_inseminar: number; a_inseminar_nums: string[];
  nao_classificadas: number; nao_classificadas_nums: string[];
  em_protocolo: number; em_protocolo_nums: string[];
};

// Bloco "reproducao" de GET /indicadores/ (mesmo módulo). `prenhes_programa_nums`
// e `vazias_programa_nums` são os denominadores do PROGRAMA reprodutivo (R1) —
// pareiam com `taxa_prenhez_pct`/`perc_vazias_pct`, não com `prenhes`/`vazias`
// (que são o INVENTÁRIO cru do rebanho inteiro, sem os cortes de R1). Ver o
// comentário longo em indicadores.py sobre por que os dois existem.
export type IndicadoresReproducao = {
  aptas: number; aptas_nums: string[];
  prenhes: number; vazias: number; inseminadas: number;
  taxa_prenhez_pct: number | null; prenhes_programa_nums: string[];
  perc_vazias_pct: number | null; vazias_programa_nums: string[];
  servicos_positivos: number; servicos_negativos: number;
  iep_dias: number | null; iep_meses: number | null;
  partos_previstos: { em_30_dias: number; em_60_dias: number; em_90_dias: number };
  partos_previstos_nums: { em_30_dias: string[]; em_60_dias: string[]; em_90_dias: string[] };
  partos_previstos_datas: Record<string, string>;
  gestantes_detalhe: { numero: string; dias_gestacao: number; parto_previsto: string }[];
  iep_por_matriz: { numero: string; iep_dias: number; data_ultimo_parto: string }[];
  concepcao_desde: string;
  taxa_servico_pct: number | null;
  taxa_concepcao_pct: number | null;
  taxa_prenhez_ciclo_pct: number | null;
  servicos_por_prenhez: number | null;
  taxa_perda_prenhez_pct: number | null;
  perc_vacas_prenhas_pct: number | null;
  dias_abertos: number | null;
  del_1a_ia: number | null;
};

// O resto do payload segue destipado (cada tela declara o recorte que usa);
// a assinatura de índice existe para isso não quebrar enquanto migramos.
export type IndicadoresResposta = {
  producao?: IndicadoresProducao;
  reproducao?: IndicadoresReproducao;
  reproducao_categorias?: { todas: ReproducaoCategoria; vaca: ReproducaoCategoria; novilha: ReproducaoCategoria };
  [chave: string]: any;
};

export async function fetchIndicadores(data?: string): Promise<IndicadoresResposta> {
  const url = data ? `${API}/indicadores/?data=${data}` : `${API}/indicadores/`;
  const res = await authFetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Indicadores error: ${res.status}`);
  return res.json();
}

export type NaoConformidadeItem = {
  chave: string;
  dominio: "reproducao" | "recria" | "financeiro" | "manejo";
  label: string;
  sublabel: string;
  valor: number;
  meta: number | null;
  unidade: string;
  maior_melhor: boolean;
  status: "ok" | "atencao" | "critico";
  rota: string;
  rota_label: string;
};
export type NaoConformidadeSemMeta = {
  chave: string; dominio: string; label: string; sublabel: string; valor: number; unidade: string;
  rota: string; rota_label: string;
};
export type NaoConformidadesResp = {
  itens: NaoConformidadeItem[];
  sem_meta: NaoConformidadeSemMeta[];
  resumo: { critico: number; atencao: number; ok: number; total: number };
  atualizado_em: string;
};
export async function fetchNaoConformidades(): Promise<NaoConformidadesResp> {
  const res = await authFetch(`${API}/nao-conformidades/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Não conformidades error: ${res.status}`);
  return res.json();
}

export async function fetchServicosAnalise() {
  const res = await authFetch(`${API}/reproducao/servicos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Análise error: ${res.status}`);
  return res.json();
}

// Ciclos de 21 dias — risco de prenhez no padrão BREDSUM\E do DairyComp.
// BR ELIG (elegíveis para inseminação) → BRED (servidas) → PG ELIG (elegíveis
// para prenhez) → PREG (prenhes). Ver backend/fazenda/rules/programa_reprodutivo.py.
export type CicloReprodutivo = {
  ciclo: number; inicio: string; fim: string;
  br_elig: number; bred: number; taxa_servico: number | null;
  pg_elig: number; preg: number; taxa_prenhez: number | null;
  taxa_concepcao: number | null; servicos_com_resultado: number;
  // False enquanto não passaram os dias de "resultado conhecido" desde o fim do
  // ciclo: PG ELIG já está cheio e PREG ainda não, então a prenhez e a concepção
  // estão subestimadas por construção. Quem exibe não pode comparar com a meta.
  janela_dg_completa: boolean;
  animais: { br_elig: string[]; bred: string[]; pg_elig: string[]; preg: string[] };
};
export type CiclosResposta = {
  ancora: string; modo: "inicio" | "fim"; categoria: string;
  periodo: { inicio: string; fim: string };
  ciclos: CicloReprodutivo[];
  resumo: {
    taxa_servico: number | null; taxa_prenhez: number | null;
    taxa_concepcao: number | null;
    // `animais_avaliados`: quantos animais passaram por pelo menos um balde
    // do BREDSUM\E (união de BR ELIG/BRED/PG ELIG/PREG de todos os ciclos) —
    // NÃO é o tamanho do rebanho carregado. Quem quer o rebanho carregado
    // (gestantes e baixadas incluídas) usa `animais_carregados`.
    animais_avaliados: number; animais_carregados: number;
  };
  metas: { taxa_servico: number; taxa_prenhez: number; taxa_concepcao: number };
  parametros: { pev_dias: number; dias_minimos_no_ciclo: number; dias_resultado_conhecido: number };
  ressalva_historica: string;
};
export async function fetchCiclos21Dias(
  ancora: string, modo: "inicio" | "fim", nCiclos: number, categoria: string,
): Promise<CiclosResposta> {
  const qs = new URLSearchParams({ ancora, modo, n_ciclos: String(nCiclos), categoria });
  const res = await authFetch(`${API}/reproducao/ciclos-21-dias?${qs}`, { cache: "no-store" });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(mensagemErroApi(d.detail) || `Ciclos de 21 dias error: ${res.status}`);
  }
  return res.json();
}
type ServicoEditPayload = {
  data_servico?: string; tipo_servico?: string; reprodutor?: string; tipo_semen?: string; inseminador?: string;
  data_diagnostico?: string; diagnostico?: string; metodo_diagnostico?: string;
  data_perda_prenhez?: string; motivo_perda_prenhez?: string;
};
export async function atualizarServico(id: number, dados: ServicoEditPayload) {
  const res = await authFetch(`${API}/reproducao/servicos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar serviço"); }
  return res.json();
}
export async function atualizarParto(id: number, dados: {
  data_parto?: string; tipo_parto?: string; retencao_placenta?: boolean;
  numero_cria_1?: string | null; numero_cria_2?: string | null;
  sexo_cria_1?: string | null; sexo_cria_2?: string | null;
  gemelar?: boolean | null; gemelar_sexo?: string | null;
}) {
  const res = await authFetch(`${API}/reproducao/partos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar parto"); }
  return res.json();
}

export type VerificacaoMaeParto = {
  mae_encontrada: boolean;
  parto_correspondente: { data_parto: string | null; ordem_parto: number | null } | null;
  partos_da_mae: { data_parto: string | null; ordem_parto: number | null }[];
  inconsistencias: string[];
};
// Chamado antes de salvar a Ficha do Animal quando o campo "mãe" muda —
// cruza com os partos da mãe já registrados (ver PUT /reproducao/verificar-mae).
export async function verificarMaeParto(maeNumero: string, animalNumero?: string): Promise<VerificacaoMaeParto> {
  const params = new URLSearchParams({ mae_numero: maeNumero });
  if (animalNumero) params.set("animal_numero", animalNumero);
  const res = await authFetch(`${API}/reproducao/verificar-mae?${params.toString()}`);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao verificar mãe"); }
  return res.json();
}
export async function atualizarSecagem(id: number, dados: { data_secagem?: string; motivo?: string; escore_condicao_corporal?: number | null; observacao?: string }) {
  const res = await authFetch(`${API}/reproducao/secagens/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar secagem"); }
  return res.json();
}

// `janela_dg_completa` — mesmo vocabulário de `ResultadoCiclo.janela_dg_completa`
// (ciclos de 21 dias): alinhado 1:1 com `meses`, indica se aquele mês já
// passou da janela de diagnóstico (R7) ou ainda está "em apuração" — a
// concepção ainda pode subir. O mês corrente quase sempre vem `false`.
export type IndicadoresMensais = { meses: string[]; series: Record<string, (number | null)[]>; janela_dg_completa: boolean[] };
export type IndicadoresMensaisFiltros = {
  ini?: string;
  fim?: string;
  filtros?: Record<string, string[]>;
};
export async function fetchIndicadoresMensais(params?: IndicadoresMensaisFiltros): Promise<IndicadoresMensais> {
  const q = new URLSearchParams();
  if (params?.ini) q.set("ini", params.ini);
  if (params?.fim) q.set("fim", params.fim);
  if (params?.filtros) {
    for (const [chave, valores] of Object.entries(params.filtros)) {
      for (const v of valores ?? []) q.append(chave, v);
    }
  }
  const qs = q.toString();
  const res = await authFetch(`${API}/reproducao/indicadores-mensais${qs ? `?${qs}` : ""}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Indicadores mensais error: ${res.status}`);
  return res.json();
}

// ── Relatório personalizado (Análise > Relatório personalizado) ──
export type ParametroRelatorioPersonalizado = { id: string; label: string; categoria: string; tipo: "texto" | "numero" | "data" | "booleano" };
export async function fetchCatalogoRelatorioPersonalizado() {
  const res = await authFetch(`${API}/indicadores/relatorio-personalizado/catalogo`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Catálogo do relatório personalizado error: ${res.status}`);
  return res.json() as Promise<ParametroRelatorioPersonalizado[]>;
}
export type ResumoRelatorioPersonalizado = {
  quantidade_animais: number;
  taxa_servico_pct: number | null;
  taxa_concepcao_pct: number | null;
  taxa_prenhez_pct: number | null;
  novilhas_aptas_ate_meses: number;
  novilhas_aptas_meses_criterio: number;
  quantidade_perda_prenhez: number;
  percentual_perda_prenhez_pct: number | null;
  percentual_nascimento_macho_pct: number | null;
  percentual_nascimento_femea_pct: number | null;
  taxa_cura_pct: number | null;
};
export async function gerarRelatorioPersonalizado(dados: { parametros: string[]; data_de?: string; data_ate?: string; novilhas_aptas_meses?: number }) {
  const res = await authFetch(`${API}/indicadores/relatorio-personalizado`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao gerar relatório personalizado"); }
  return res.json() as Promise<{ colunas: ParametroRelatorioPersonalizado[]; linhas: Record<string, any>[]; resumo: ResumoRelatorioPersonalizado }>;
}

// ── Relatórios gerenciais e de manejo (Reprodução) ──
export async function fetchRelatoriosManejo() {
  const res = await authFetch(`${API}/relatorios/manejo`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatórios de manejo error: ${res.status}`);
  return res.json();
}

// ── Combinador de Listas (Insights > Listas) ──
export type AnimalCombinador = {
  numero: string;
  lote: string | null;
  categoria_etaria: "vaca" | "novilha" | "bezerra" | null;
  categoria_cadastro: string | null;
  idade_dias: number | null;
  peso_kg: number | null;
  producao_kg: number | null;
  situacao_produtiva: "lactacao" | "seca" | null;
  dias_pos_parto: number | null;
  dias_para_parto: number | null;
  dias_gestacao: number | null;
  dias_desde_servico: number | null;
  situacao_reprodutiva: "vazia" | "vazia_atrasada" | "inseminada" | "prenha" | null;
  dias_desde_pesagem: number | null;
  dias_desde_producao: number | null;
  dias_desde_aptidao: number | null;
  apta: boolean | null;
};
export type CombinadorListasData = {
  animais: AnimalCombinador[];
  lotes: string[];
  categorias_cadastro: { id: number; nome: string; ordem: number }[];
};
export async function fetchCombinadorListas(): Promise<CombinadorListasData> {
  const res = await authFetch(`${API}/relatorios/combinador-listas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Combinador de listas error: ${res.status}`);
  return res.json();
}
export async function fetchRelatorioGerencial(nome: string, params?: Record<string, string | number>) {
  const qs = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => qs.set(k, String(v)));
  const res = await authFetch(`${API}/relatorios/gerencial/${nome}?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório gerencial error: ${res.status}`);
  return res.json();
}

// ── Estoque de sêmen (Configurações > Cadastro) ──
export async function fetchEstoqueSemen() {
  const res = await authFetch(`${API}/cadastro/estoque-semen`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Estoque de sêmen error: ${res.status}`);
  return res.json();
}
export type SemenDisponivel = {
  touros: { nome: string; tipo: "convencional" | "sexado" | "fazenda"; doses: number }[];
  totais: { convencional: number; sexado: number };
  minimos: { convencional: number; sexado: number };
  abaixo_minimo: { convencional: boolean; sexado: boolean };
};
export async function fetchSemenDisponivel() {
  const res = await authFetch(`${API}/cadastro/estoque-semen/disponivel`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Sêmen disponível error: ${res.status}`);
  return res.json() as Promise<SemenDisponivel>;
}

// ── Acasalamento direcionado (sugestão de touro por vaca) ──
export type SugestaoTouro = {
  naab?: string | null;
  nome?: string | null;
  tpi?: number | null;
  nm_dolar?: number | null;
  leite_kg?: number | null;
  doses?: number | null;
  tipo?: "convencional" | "sexado" | "fazenda" | string;
  score: number;
  tem_ancestral_comum: boolean;
  motivo: string;
};
export type SugestaoAcasalamento = {
  numero_matriz: string;
  criterios: string[];
  sugestoes: SugestaoTouro[];
  ancestrais_maternos_avaliados: boolean;
};
export async function fetchSugestaoAcasalamento(numeroMatriz: string): Promise<SugestaoAcasalamento> {
  const res = await authFetch(`${API}/reproducao/acasalamento/sugestao?numero_matriz=${encodeURIComponent(numeroMatriz)}`, { cache: "no-store" });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(mensagemErroApi(d.detail) || `Sugestão de acasalamento error: ${res.status}`);
  }
  return res.json() as Promise<SugestaoAcasalamento>;
}
export async function criarServicoLote(dados: {
  animais: string[]; data_servico: string; tipo: "cio_natural" | "iatf" | "monta_natural";
  reprodutor?: string; responsavel?: string; protocolo_lancamento_id?: number | null; auto_lancar_iatf?: boolean;
  tipo_semen?: string | null;
  // Confirmação manual dos bloqueios de aptidão CONFIRMÁVEIS (novilha sem
  // pesagem/abaixo do peso, matriz que consta como gestante) — ver
  // backend/fazenda/rules/aptidao.py. Nunca destrava idade/sexo/baixado.
  forcar?: boolean;
}) {
  const res = await authFetch(`${API}/reproducao/servico-lote`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) throw await erroDaResposta(res, "Erro ao registrar inseminação");
  return res.json() as Promise<{ criados: number; incompativeis: string[]; tipo: string }>;
}

// Indução de cio (PGF2α/Cloprostenol) — estímulo hormonal lançado à parte de
// protocolo IATF, inseminação e diagnóstico (ver reproducao.py). Gera
// histórico (Sanidade com atividade própria) e alimenta o alerta "Observar
// cio" na Agenda, 2 a 5 dias depois da aplicação.
export type InducaoCioLancamento = {
  id: number; numero_matriz: string; data_aplicacao: string | null; produto: string;
  dose: number | null; unidade: string | null; via: string | null; responsavel: string | null; observacao: string | null;
};
export async function registrarInducaoCio(dados: {
  numeros_matriz: string[]; data_aplicacao: string; produto?: string;
  dose?: number | null; unidade?: string | null; via?: string | null; responsavel?: string | null; observacao?: string | null;
}) {
  const res = await authFetch(`${API}/reproducao/inducao-cio`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar indução de cio"); }
  return res.json() as Promise<{ aplicados: number; avisos: string[] }>;
}
export async function fetchInducoesCio(): Promise<InducaoCioLancamento[]> {
  const res = await authFetch(`${API}/reproducao/inducao-cio`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao buscar histórico de indução de cio");
  return res.json();
}
export async function excluirInducaoCio(id: number) {
  const res = await authFetch(`${API}/reproducao/inducao-cio/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir lançamento"); }
  return res.json();
}
type EstoqueSemenDados = { touro_nome: string; codigo?: string | null; naab?: string | null; central?: string | null; tipo: string; doses: number; valor_unitario?: number | null; local_armazenamento?: string | null; observacao?: string | null; ativo?: boolean };
export async function criarEstoqueSemen(dados: EstoqueSemenDados) {
  const res = await authFetch(`${API}/cadastro/estoque-semen`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cadastrar sêmen"); }
  return res.json();
}
export async function atualizarEstoqueSemen(id: number, dados: EstoqueSemenDados) {
  const res = await authFetch(`${API}/cadastro/estoque-semen/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar sêmen"); }
  return res.json();
}
export async function excluirEstoqueSemen(id: number) {
  const res = await authFetch(`${API}/cadastro/estoque-semen/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir sêmen"); }
  return res.json();
}

export async function salvarDiagnostico(dados: {
  numero_matriz: string; data_diagnostico: string; resultado: "retoque" | "reconfirmada" | "negativo" | "indefinido"; metodo?: string;
}) {
  const res = await authFetch(`${API}/reproducao/diagnostico`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar diagnóstico"); }
  return res.json();
}

export type AgendaVetItem = {
  numero_matriz: string; categoria: string; peso: number | null;
  lote_atual: string | null;
  dias_inseminada: number | null; data_servico: string | null;
  inseminador: string | null; touro: string | null; tipo_servico: string | null; metodo: string | null;
  tocada: boolean; reconfirmada: boolean;
  data_diagnostico: string | null; diagnostico: string | null;
  data_reconfirmacao: string | null; diagnostico_reconfirmacao: string | null;
  tem_servico?: boolean;
  atrasada?: boolean; dias_para_parto?: number | null; motivo?: string;
  data_dg_negativo?: string | null; del_projetado_proximo_servico?: number | null;
  pev_dias_restantes_projetado?: number | null; proxima_data_dg_estimada?: string | null;
};
export type AgendaVetResposta = {
  data_referencia: string; projetado?: boolean; listas: Record<string, AgendaVetItem[]>; totais: Record<string, number>;
  ultimo_servico?: string | null; proxima_visita_reprodutiva?: string | null; intervalo_visita_reprodutiva?: number;
};

// data (opcional, AAAA-MM-DD): simula um cenário projetado numa data futura
// (ex.: a próxima visita do veterinário) — ver #490.
export async function fetchAgendaVeterinario(data?: string): Promise<AgendaVetResposta> {
  const qs = data ? `?data=${encodeURIComponent(data)}` : "";
  const res = await authFetch(`${API}/reproducao/agenda-veterinario${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Agenda Reprodutiva error: ${res.status}`);
  return res.json();
}

// Rótulos amigáveis das listas da Agenda do veterinário — usados tanto na
// própria tela quanto em seletores que semeiam animais a partir dela (ex.:
// Diagnóstico de gestação "por Agenda do veterinário").
export const LISTAS_AGENDA_VETERINARIO: { chave: string; rotulo: string }[] = [
  { chave: "inseminadas_1_29", rotulo: "Inseminadas 1–29 dias" },
  { chave: "inseminadas_30_59", rotulo: "Inseminadas 30–59 dias — toque" },
  { chave: "inseminadas_60_mais", rotulo: "Inseminadas 60+ dias — reconfirmação" },
  { chave: "novilhas_aptas_vazias", rotulo: "Novilhas aptas vazias" },
  { chave: "novilhas_gestantes", rotulo: "Novilhas gestantes" },
  { chave: "vacas_gestantes", rotulo: "Vacas gestantes" },
  { chave: "verificar_pre_parto", rotulo: "Verificar pré-parto" },
  { chave: "vazias_por_diagnostico", rotulo: "Vazias por diagnóstico" },
  { chave: "pendentes_classificacao", rotulo: "Pendentes de classificação" },
  { chave: "observacao_cio", rotulo: "Observação de cio" },
];

// ── Card configurável da Agenda Reprodutiva (4 eixos: categoria/lote/
// situação/período) — ver fazenda.rules.agenda_reprodutiva_configuravel. ──
export type SituacaoCard = "pev" | "inseminada" | "gestante" | "vazia" | "vazia_atrasada" | "a_descartar";

export type CardAgendaReprodutivaConfig = {
  categoria: "todas" | "vaca" | "novilha";
  lotes: string[];
  situacao: SituacaoCard;
  periodos: [number, number][];
  somente_atrasadas: boolean;
  exceto_atrasadas: boolean;
};

export type ItemCardAgendaReprodutiva = {
  numero_matriz: string; categoria: string | null; lote_atual: string | null;
  estado: string | null; del_dias: number | null; dias_gestacao: number | null;
  dias_desde_servico: number | null; data_servico: string | null; parto_previsto: string | null;
};

export async function fetchAgendaReprodutivaCard(
  config: CardAgendaReprodutivaConfig, data?: string,
): Promise<{ data_referencia: string; total: number; itens: ItemCardAgendaReprodutiva[] }> {
  const qs = data ? `?data=${encodeURIComponent(data)}` : "";
  const res = await authFetch(`${API}/reproducao/agenda-reprodutiva/card${qs}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao montar o card"); }
  return res.json();
}


export async function registrarReconfirmacao(dados: {
  numero_matriz: string; data_reconfirmacao: string; resultado: "positivo" | "negativo";
}) {
  const res = await authFetch(`${API}/reproducao/reconfirmacao`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar reconfirmação"); }
  return res.json();
}

// Último diagnóstico de gestação da matriz (Agenda do veterinário) + envio por e-mail.
export async function fetchUltimoDiagnostico(numeroMatriz: string) {
  const res = await authFetch(`${API}/reproducao/animais/${encodeURIComponent(numeroMatriz)}/ultimo-diagnostico`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Último diagnóstico error: ${res.status}`);
  return res.json();
}
export async function enviarDiagnosticoEmail(numeroMatriz: string, destinatario: string) {
  const res = await authFetch(`${API}/reproducao/animais/${encodeURIComponent(numeroMatriz)}/diagnostico/enviar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ destinatario }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao enviar diagnóstico por e-mail"); }
  return res.json();
}

export async function fetchPartosHistorico() {
  const res = await authFetch(`${API}/reproducao/partos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Partos error: ${res.status}`);
  return res.json();
}

export async function fetchSecagensHistorico() {
  const res = await authFetch(`${API}/reproducao/secagens`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Secagens error: ${res.status}`);
  return res.json();
}

export async function registrarPerdaPrenhez(dados: {
  numero_matriz: string; data_perda_prenhez: string; motivo: "aborto" | "natimorto" | "outros";
}) {
  const res = await authFetch(`${API}/reproducao/perda-prenhez`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar perda de prenhez"); }
  return res.json();
}

/**
 * Encerramento de gestação — o caminho ÚNICO de "esta gestação acabou".
 *
 * Substitui, no fluxo de aborto, a dupla incoerente que existia antes:
 * `registrarPerdaPrenhez` (que NÃO criava Parto nenhum e carimbava a perda no
 * serviço mais recente por data, nem sempre o certo) seguida de
 * `abrirLactacao` (que só gravava `del_dias = 0`, sem nem receber a data do
 * evento). Numa transação só, o backend cria o `Parto`, carimba a perda no
 * serviço vigente positivo correto, abre a `Lactacao` com a data REAL do
 * evento e sincroniza o DEL. Ver POST /reproducao/encerramento-gestacao.
 */
export async function encerrarGestacao(dados: {
  numero_matriz: string;
  data: string;
  tipo: "parto" | "aborto" | "natimorto";
  abrir_lactacao?: boolean;
  motivo?: "aborto" | "natimorto" | "outros";
  crias?: { numero: string; sexo: string; nasceu_viva?: boolean }[];
  retencao_placenta?: boolean;
  gemelar?: boolean;
  gemelar_sexo?: string;
  tipo_parto?: string;
  observacao?: string;
  forcar?: boolean;
}) {
  const res = await authFetch(`${API}/reproducao/encerramento-gestacao`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) throw await erroDaResposta(res, "Erro ao registrar o encerramento da gestação");
  return res.json() as Promise<{
    criado: boolean; tipo: string; parto_id: number | null; ordem_parto: number | null;
    crias_criadas: string[]; crias_baixadas: string[];
    perda_prenhez_servico_id: number | null;
    lactacao_id: number | null; lactacao_aberta: boolean; del_dias: number | null;
    sugerir_lote: boolean;
  }>;
}

// Abre lactação de um animal sem parto associado (popup pós-aborto — "deseja
// abrir lactação para o animal X?").
//
// @deprecated Só grava `del_dias = 0` e não recebe a data do evento — use
// `encerrarGestacao` com `abrir_lactacao: true`, que abre uma `Lactacao` de
// verdade com a data real. Mantido porque outras telas ainda o chamam.
export async function abrirLactacao(numeroMatriz: string) {
  const res = await authFetch(`${API}/reproducao/animais/${encodeURIComponent(numeroMatriz)}/abrir-lactacao`, {
    method: "POST",
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao abrir lactação"); }
  return res.json();
}

export async function fetchFornecedores() {
  const res = await authFetch(`${API}/cadastro/fornecedores`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Fornecedores error: ${res.status}`);
  return res.json();
}
export async function criarFornecedor(dados: { nome: string; tipo: string; categoria?: string; cnpj_cpf?: string; telefone?: string; email?: string; observacoes?: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/fornecedores`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar fornecedor"); }
  return res.json();
}
export async function atualizarFornecedor(id: number, dados: { nome: string; tipo: string; categoria?: string; cnpj_cpf?: string; telefone?: string; email?: string; observacoes?: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/fornecedores/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar fornecedor"); }
  return res.json();
}

// ── Pessoas (Configurações > Cadastro) ──
export async function fetchPessoas() {
  const res = await authFetch(`${API}/cadastro/pessoas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Pessoas error: ${res.status}`);
  return res.json();
}
/** Periodicidade e regime do vale-alimentação — ver
 *  `backend/fazenda/rules/vale_alimentacao.py`. "antecipado" significa que o
 *  VA de uma competência sai na folha da competência ANTERIOR. */
export type PeriodicidadeValeAlimentacao = "diario" | "mensal";
export type RegimeValeAlimentacao = "antecipado" | "vencido";
type PessoaDados = {
  nome: string; tipos: string[]; telefones?: string[]; emails?: string[]; cpf_cnpj?: string; cep?: string;
  observacoes?: string; ativo?: boolean; salario_base?: number; data_admissao?: string;
  rg?: string; data_nascimento?: string; genero?: string; estado_civil?: string;
  endereco_rua?: string; endereco_numero?: string; endereco_bairro?: string; endereco_cidade?: string; endereco_uf?: string;
  /** Configuração do vale-alimentação: a folha gera a linha do holerite a
   *  partir daqui, não de uma rubrica lançada mês a mês. */
  vale_alimentacao?: boolean;
  vale_alimentacao_valor?: number;
  vale_alimentacao_periodicidade?: PeriodicidadeValeAlimentacao;
  vale_alimentacao_regime?: RegimeValeAlimentacao;
};
export async function criarPessoa(dados: PessoaDados) {
  const res = await authFetch(`${API}/cadastro/pessoas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar pessoa"); }
  return res.json();
}
export async function atualizarPessoa(id: number, dados: PessoaDados) {
  const res = await authFetch(`${API}/cadastro/pessoas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar pessoa"); }
  return res.json();
}
export async function excluirPessoa(id: number) {
  const res = await authFetch(`${API}/cadastro/pessoas/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir pessoa"); }
  return res.json();
}

// Anexos de Pessoa — RG, CPF, carteira de trabalho, contratos, holerite,
// comprovantes (ver PessoaAnexo no backend), com validade opcional; quando
// há validade, a Agenda alerta antes do vencimento — hoje só para "Contrato
// de trabalho por prazo determinado" (15 dias antes).
export const CATEGORIAS_PESSOA_ANEXO = [
  "RG", "CPF", "Carteira de trabalho", "Ficha de registro",
  "Contrato de trabalho por prazo indeterminado", "Contrato de trabalho por prazo determinado",
  "Contrato de empreita", "Holerite", "Comprovante de pagamento", "Comprovante de vale",
];
export type AnexoPessoa = {
  id: number; nome_arquivo: string; mime_type: string; tamanho_bytes: number; categoria: string;
  data_validade?: string | null; criado_em?: string;
};
export async function anexarArquivoPessoa(pessoaId: number, file: File, categoria: string, dataValidade?: string | null): Promise<AnexoPessoa> {
  const form = new FormData();
  form.append("file", file);
  form.append("categoria", categoria);
  if (dataValidade) form.append("data_validade", dataValidade);
  const res = await authFetch(`${API}/cadastro/pessoas/${pessoaId}/anexos`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao anexar o arquivo"); }
  return res.json();
}
export async function listarAnexosPessoa(pessoaId: number): Promise<AnexoPessoa[]> {
  const res = await authFetch(`${API}/cadastro/pessoas/${pessoaId}/anexos`);
  if (!res.ok) throw new Error("Erro ao listar anexos da pessoa");
  return res.json();
}
export function urlAnexoPessoa(anexoId: number): string {
  return `${API}/cadastro/pessoas/anexos/${anexoId}`;
}
export async function excluirAnexoPessoa(anexoId: number) {
  const res = await authFetch(`${API}/cadastro/pessoas/anexos/${anexoId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir anexo"); }
  return res.json();
}
export async function fetchInseminadores(): Promise<string[]> {
  const res = await authFetch(`${API}/cadastro/pessoas/inseminadores`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Inseminadores error: ${res.status}`);
  return res.json();
}

// ── Tipos de pessoa (Configurações > Cadastro > Pessoas, botão "+") ──
export async function fetchTiposPessoa(): Promise<{ id: number; nome: string; ativo: boolean }[]> {
  const res = await authFetch(`${API}/cadastro/pessoas/tipos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Tipos de pessoa error: ${res.status}`);
  return res.json();
}
export async function criarTipoPessoa(nome: string) {
  const res = await authFetch(`${API}/cadastro/pessoas/tipos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar tipo de pessoa"); }
  return res.json();
}

// Sugestão de valor proporcional da folha no mês de admissão da pessoa (ou
// null fora desse mês) — usada em Financeiro > Ações > Folha de Pagamento.
export async function fetchProporcionalAdmissao(pessoaId: number, competencia: string): Promise<
  { dias_trabalhados: number; dias_mes: number; fracao: number } | null
> {
  const res = await authFetch(
    `${API}/cadastro/folha-pagamento/proporcional-admissao?pessoa_id=${pessoaId}&competencia=${competencia}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`Proporcional admissão error: ${res.status}`);
  return res.json();
}

// ── Discriminação do holerite (as 4 colunas do recibo de papel) ──
// Cada linha do discriminado passa a dizer DE ONDE o valor veio: a coluna
// `referencia` ("7,78% sobre R$ 2.000,00", "Parcela 3 de 13 · vale de
// 12/03/2026") e, quando é desconto de vale, a `origem` com o `vale_id` — o
// que substitui o antigo `/vale/i.test(label)` (regex no rótulo em português,
// que nunca teve como desempatar dois vales de mesmo valor no mesmo mês).
// `label`/`valor` continuam sendo o texto e o valor com sinal de antes.
export type OrigemVale = {
  tipo: "vale";
  vale_id: number;
  parcela_id: number | null;
  parcela: number;
  parcelas_total: number;
  valor_total: number;
  data_pagamento: string | null;
  forma_pagamento: string;
  observacao: string | null;
  numero_documento_pagamento: string | null;
  numero_lancamento_gerado: string | null;
  /** true quando forma_pagamento === "desconto_integral_folha": não houve
   *  saída de caixa, então NÃO existe lançamento no extrato — por desenho. */
  sem_saida_de_caixa: boolean;
  origem_lancamento: {
    item_id: number | null; numero_lancamento: string | null; produto: string | null;
    valor_item: number | null; fornecedor_cliente: string | null;
    numero_documento: string | null; data_emissao: string | null;
  } | null;
  aplicada: boolean;
};
export type OrigemRetencao = {
  tipo: "retencao";
  percentual: number | null;
  base: number | null;
  /** null quando não há percentual gravado — sem base declarada, conferir
   *  seria inventar o percentual a partir do valor. */
  confere: boolean | null;
  diferenca: number | null;
};
/** A compra (parcela de lançamento financeiro) que um desconto está abatendo —
 *  o que a janela sobreposta de consulta de contas devolve e o que viaja junto
 *  da linha do recibo. */
export type CompraDoDesconto = {
  conta_id: number;
  numero_lancamento: string | null;
  descricao: string | null;
  fornecedor_cliente: string | null;
  numero_nota: string | null;
  tipo_documento: string | null;
  centro_custo: string | null;
  data_emissao: string | null;
  data_vencimento: string | null;
  data_pagamento: string | null;
  valor_total: number;
  valor_pago: number | null;
  parcela_num: number | null;
  parcela_total: number | null;
};
/** Origem de uma rubrica acrescentada ao holerite (vencimento ou desconto).
 *  O enquadramento vem CONGELADO do servidor — a tela nunca decide natureza
 *  nem incidência, só mostra o que foi gravado no lançamento. */
export type OrigemRubrica = {
  tipo: "rubrica";
  rubrica_id: number;
  codigo: string;
  rotulo: string;
  especie: "vencimento" | "desconto";
  descricao: string | null;
  natureza: "salarial" | "indenizatoria";
  incide_inss: boolean;
  incide_irrf: boolean;
  incide_fgts: boolean;
  incorpora_base: boolean;
  /** "2026-08" no aumento na folha (a partir de quando vira salário-base);
   *  null em todas as demais. */
  competencia_incorporacao: string | null;
  /**
   * Se esta verba pode ser alterada NO ATO DO PAGAMENTO sem confirmação
   * ("livre" → a coluna mostra "Editar") ou só depois do aviso do cadeado
   * ("contratual"). Vem do catálogo do servidor (`rules/rubrica_folha.py`),
   * NUNCA de uma segunda lista escrita aqui — ver `pagamentoFolhaRegras.ts`.
   * Opcional porque discriminação congelada antes deste campo existir não o
   * tem; quem lê trata a ausência como "contratual" (pedir confirmação é o
   * lado seguro de não saber).
   */
  alteracao?: "livre" | "contratual";
  fundamento: string | null;
  compra: CompraDoDesconto | null;
};
export type LinhaHolerite = {
  label: string;
  valor: number;
  tipo: "bruto" | "inss" | "ir" | "vale" | "outros" | "liquido" | "ferias" | "terco" | "abono"
    | "vencimento_extra" | "desconto_extra";
  descricao: string;
  referencia: string;
  provento: number | null;
  desconto: number | null;
  origem: OrigemVale | OrigemRetencao | OrigemRubrica | null;
};
/**
 * Parcela de vale que a FAZENDA assumiu (mês desconsiderado ou vale
 * cancelado). Chega num campo SEPARADO de `detalhe` — nunca dentro dele —
 * porque não é desconto de ninguém e não pode entrar em soma nenhuma; existe
 * só para o painel de vale explicar por que o desconto sumiu daquele mês e
 * continuar oferecendo o botão "Ações", que é a porta para desfazer.
 * `provento`/`desconto`/`valor` vêm neutros do servidor pelo mesmo motivo: o
 * valor real está em `valor_assumido`.
 */
export type LinhaValeAssumido = Omit<LinhaHolerite, "tipo"> & {
  tipo: "vale_assumido";
  valor_assumido: number;
  motivo: string | null;
  competencia: string;
};
export type TotaisHolerite = {
  total_proventos: number;
  total_descontos: number;
  liquido: number;
  /** Descontos maiores que vencimentos: não é um líquido válido, é um
   *  excedente — e um recibo assim não pode ser emitido. */
  liquido_negativo: boolean;
  excedente: number;
};
export type BasesHolerite = {
  /** Sempre `FolhaPagamento.valor_bruto`, NUNCA `Pessoa.salario_base` (valor
   *  vivo: reimprimir 2024 mostraria o salário de hoje). */
  salario_base: number;
  /** Base das retenções = salário + rubricas SALARIAIS (bonificação, guelta,
   *  aumento). Reembolso e indenização não entram: são indenizatórios. */
  base_inss: number | null;
  base_ir: number | null;
  /** Quanto das bases veio de rubrica salarial — 0 na folha comum. */
  rubricas_tributaveis?: number;
  fgts_projetado: number | null;
  percentual_fgts: number | null;
  dctf_projetado: number | null;
};

// ── Folha de pagamento (Configurações > Cadastro / Financeiro) ──
export async function fetchFolhaPagamento() {
  const res = await authFetch(`${API}/cadastro/folha-pagamento`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Folha de pagamento error: ${res.status}`);
  return res.json();
}
type FolhaPagamentoDados = {
  pessoa_id: number; competencia: string; valor_bruto: number; descontos?: number;
  percentual_inss?: number; percentual_ir?: number; valor_inss?: number; valor_ir?: number;
  // FGTS/DCTF — opcionais, só para projeção (ver `gerarGuiasFgtsDctf` abaixo).
  percentual_fgts?: number | null; valor_fgts?: number | null;
  percentual_dctf?: number | null; valor_dctf?: number | null;
  data_pagamento?: string; status?: string; observacao?: string; recorrente?: boolean; dia_vencimento?: number | null;
  // Conta bancária de onde sai o pagamento — OPCIONAL (ver _resolver_conta_corrente
  // no backend); preenche ContaGerencial.conta_bancaria, usado pelos relatórios gerenciais.
  conta_corrente_id?: number | null;
};
export async function criarFolhaPagamento(dados: FolhaPagamentoDados) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar folha de pagamento"); }
  return res.json();
}
export async function atualizarFolhaPagamento(id: number, dados: FolhaPagamentoDados) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar folha de pagamento"); }
  return res.json();
}
export async function excluirFolhaPagamento(id: number) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir lançamento de folha"); }
  return res.json();
}
/**
 * Estorna o pagamento de uma folha — desfaz a baixa da conta a pagar,
 * devolve o lançamento a "pendente" e DESCONGELA a discriminação.
 *
 * A rota existe desde o C7, mas nenhuma tela a chamava: o holerite mandava o
 * usuário "estornar o pagamento para acrescentar ou corrigir vencimentos e
 * descontos" e não havia botão nenhum para isso — o caminho era mexer no
 * banco à mão.
 */
export async function estornarPagamentoFolha(id: number) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/${id}/estornar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao estornar o pagamento da folha"); }
  return res.json();
}

// ── Pagar a folha lançando valor DISTINTO nas verbas (ver
// backend/.../rh_folha_pagar.py). O pop-up do ato do pagamento: cada verba tem
// a coluna de edição ("Editar" ou cadeado), e a diferença de uma parcela de
// VALE ainda precisa de destino — as decisões do painel de ações do vale,
// disparadas por quanto se está pagando agora, mais `acrescimo_avulso`, que só
// existe para quem descontou a MAIS (o excedente vira linha própria do
// holerite em vez de antecipar o saldo). ──
export type DecisaoDiferencaFolha = "abater" | "desconsiderar" | "reparcelar" | "acrescimo_avulso";
export type PagarFolhaDados = {
  data_pagamento: string;
  /** Parcelas de vale — as únicas cuja diferença abre uma decisão, por serem
   *  a única verba que é dívida da pessoa. */
  verbas?: { parcela_id: number; valor_pago: number }[];
  /** As demais verbas da coluna de edição. `confirmado` é a marca do CADEADO:
   *  nas verbas contratuais o servidor recusa a alteração que chega sem ele —
   *  a trava não pode existir só na tela. */
  rubricas?: { rubrica_id: number; valor_pago: number; confirmado: boolean }[];
  retencoes?: { tipo: "inss" | "ir"; valor_pago: number; confirmado: boolean }[];
  /** Para MAIOR vira aumento incorporado (novo salário daí em diante); para
   *  MENOR o servidor recusa com 400 — CLT, art. 468. */
  salario?: { valor_pago: number; confirmado: boolean };
  outros_descontos?: { valor_pago: number };
  decisao?: {
    tipo: DecisaoDiferencaFolha;
    /** abater: conta que RECEBEU a devolução em dinheiro (opcional — abatimento
     *  que é perdão não tem entrada de caixa a lançar). */
    conta_corrente_id?: number;
    parcelas?: number;             // reparcelar
    competencia_inicio?: string;   // reparcelar (padrão: a competência seguinte)
    motivo?: string;
    /** reparcelar: confirma prosseguir mesmo deixando alguma competência acima
     *  de 40% do salário em desconto de vale (409 do backend). */
    confirmar?: boolean;
  };
};
export type PagarFolhaResultado = {
  id: number; status: string; valor_liquido: number; valor_vale?: number;
  recibo_congelado: boolean;
  decisoes: { decisao: DecisaoDiferencaFolha; valor: number; resumo: string }[];
  /** O que a coluna de edição gravou — uma entrada por verba alterada. */
  alteracoes?: { verba: string; de: number; para: number; resumo: string }[];
  [chave: string]: any;
};
export async function pagarFolhaComVerbas(id: number, dados: PagarFolhaDados): Promise<PagarFolhaResultado> {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/${id}/pagar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) {
    // Preserva `detail`/`status` (mesmo padrão de `criarVale`): o 409 de
    // "ultrapassa 40% do salário" ao reparcelar a diferença precisa do
    // `detail.competencias_excedidas` estruturado para a tela oferecer o
    // "confirmar mesmo assim", e não só de uma string solta.
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(
      mensagemErroApi(d.detail) || (typeof d.detail === "object" ? d.detail?.mensagem : null)
      || "Erro ao registrar o pagamento da folha",
    );
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// ── Guia de FGTS/DCTF — lançamento manual ou por leitura automática (ver
// POST /financeiro/ler-documento, tipo_documento "guia_fgts"/"guia_dctf")
// — substitui o antigo "gerar guias" (soma projetada sem vínculo com guia
// real, removido por decisão do usuário) ──
export type GuiaFolhaEncargo = {
  id: number;
  tipo: "fgts" | "dctf";
  competencia: string;
  codigo_receita: string | null;
  valor_principal: number;
  valor_multa: number;
  valor_juros: number;
  valor_total: number;
  data_vencimento: string;
  linha_digitavel: string | null;
  numero_lancamento: string | null;
  origem: "manual" | "leitura_automatica";
  criado_em: string;
};
export type GuiaFolhaEncargoDados = {
  tipo: "fgts" | "dctf";
  competencia: string;
  codigo_receita?: string | null;
  valor_principal: number;
  valor_multa?: number;
  valor_juros?: number;
  data_vencimento: string;
  linha_digitavel?: string | null;
  origem?: "manual" | "leitura_automatica";
  centro_custo?: string;
};
export async function lancarGuiaFolhaEncargo(dados: GuiaFolhaEncargoDados): Promise<GuiaFolhaEncargo & { conta_id: number }> {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/guias`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar guia de FGTS/DCTF"); }
  return res.json();
}
export async function fetchGuiasFolhaEncargo(): Promise<GuiaFolhaEncargo[]> {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/guias`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Guias de FGTS/DCTF error: ${res.status}`);
  return res.json();
}
export async function atualizarGuiaFolhaEncargo(
  guiaId: number, dados: GuiaFolhaEncargoDados,
): Promise<GuiaFolhaEncargo & { conta_id: number | null }> {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/guias/${guiaId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar guia de FGTS/DCTF"); }
  return res.json();
}
export async function excluirGuiaFolhaEncargo(guiaId: number) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/guias/${guiaId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir guia de FGTS/DCTF"); }
  return res.json();
}

// ── Folha de pagamento unificada (funcionário + empreita + contrato + diária + férias/13º) ──
export type LinhaFolhaUnificada = {
  tipo: "funcionario" | "empreita" | "contrato" | "diaria" | "ferias_decimo";
  origem_id: number;
  origem_subtipo: string;
  pessoa_id: number;
  pessoa_nome: string;
  descricao: string;
  valor: number;
  data_vencimento: string | null;
  data_pagamento: string | null;
  /** O tipo dizia só "pendente | pago" e o servidor sempre pôde mandar um
   *  TERCEIRO estado: férias e 13º absorvidos por uma rescisão saem com
   *  "cancelado_rescisao" (ver STATUS_CANCELADO_RESCISAO em rh_folha.py). A
   *  tela lia isso como "não é pago, logo é pendente" e cobrava de novo, na
   *  tabela, um valor que já foi pago dentro das verbas rescisórias. */
  status: "pendente" | "pago" | "cancelado_rescisao";
  pode_excluir: boolean;
  vencido: boolean;
  /** Discriminado do documento — presente em funcionário (holerite completo) e
   *  em férias/13º (recibo com referência própria). O ledger já calculava isso
   *  e descartava ao montar a linha: era por isso que a tela de Contas não
   *  tinha o que mostrar ao clicar num nome. */
  detalhe?: LinhaHolerite[];
  /** As parcelas de vale que a FAZENDA assumiu naquela competência — campo
   *  separado de `detalhe`, nunca dentro dele, porque não são desconto de
   *  ninguém e não podem entrar em soma nenhuma. Vêm até aqui só para o
   *  documento EXPLICAR por que o desconto de vale sumiu do mês: esta é a
   *  tela de consulta (Contas > Holerites e recibos), que não tem o painel de
   *  ações onde a explicação já aparecia. */
  vale_assumido?: LinhaValeAssumido[];
  totais?: TotaisHolerite;
  bases?: BasesHolerite;
  competencia?: string;
  numero_lancamento_gerado?: string | null;
  observacao?: string | null;
};
export async function fetchFolhaPagamentoUnificada(): Promise<LinhaFolhaUnificada[]> {
  const res = await authFetch(`${API}/cadastro/folha-pagamento-unificada`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Folha de pagamento (unificada) error: ${res.status}`);
  return res.json();
}

// ── Rubricas do holerite (vencimentos e descontos acrescentados) ──
// O enquadramento trabalhista (natureza salarial × indenizatória e as
// incidências de INSS/IRRF/FGTS) é decidido no SERVIDOR a partir do código —
// a tela manda o código e exibe a consequência, nunca a define. Ver
// backend/fazenda/rules/rubrica_folha.py.
export type RubricaCatalogoItem = {
  codigo: string;
  rotulo: string;
  fundamento: string;
  natureza?: "salarial" | "indenizatoria";
  incide_inss?: boolean;
  incide_irrf?: boolean;
  incide_fgts?: boolean;
  incorpora_base?: boolean;
  exige_compra?: boolean;
  /** Ver `OrigemRubrica.alteracao` — o eixo da coluna de edição do pagamento. */
  alteracao?: "livre" | "contratual";
};
export type CatalogoRubricas = { vencimentos: RubricaCatalogoItem[]; descontos: RubricaCatalogoItem[] };
export type RubricaFolha = {
  id: number;
  folha_id: number;
  pessoa_id: number;
  competencia: string;
  especie: "vencimento" | "desconto";
  codigo: string;
  descricao: string | null;
  valor: number;
  natureza: "salarial" | "indenizatoria";
  incide_inss: boolean;
  incide_irrf: boolean;
  incide_fgts: boolean;
  incorpora_base: boolean;
  conta_gerencial_id: number | null;
  numero_lancamento: string | null;
  rotulo: string;
  referencia: string;
  compra: CompraDoDesconto | null;
};
export type RubricaFolhaDados = {
  especie: "vencimento" | "desconto";
  codigo: string;
  valor: number;
  descricao?: string | null;
  conta_gerencial_id?: number | null;
};
export async function fetchCatalogoRubricas(): Promise<CatalogoRubricas> {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/rubricas/catalogo`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Catálogo de rubricas error: ${res.status}`);
  return res.json();
}
export async function fetchComprasParaDesconto(busca?: string): Promise<CompraDoDesconto[]> {
  const qs = busca ? `?busca=${encodeURIComponent(busca)}` : "";
  const res = await authFetch(`${API}/cadastro/folha-pagamento/rubricas/compras${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Consulta de contas error: ${res.status}`);
  return res.json();
}
export async function fetchRubricasFolha(folhaId: number): Promise<RubricaFolha[]> {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/${folhaId}/rubricas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Rubricas da folha error: ${res.status}`);
  return res.json();
}
export async function criarRubricaFolha(folhaId: number, dados: RubricaFolhaDados) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/${folhaId}/rubricas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao acrescentar a rubrica"); }
  return res.json();
}
export async function atualizarRubricaFolha(rubricaId: number, dados: { valor: number; descricao?: string | null }) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/rubricas/${rubricaId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar a rubrica"); }
  return res.json();
}
export async function excluirRubricaFolha(rubricaId: number) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/rubricas/${rubricaId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir a rubrica"); }
  return res.json();
}
export async function excluirParcelaEmpreitada(id: number) {
  const res = await authFetch(`${API}/cadastro/empreitadas/parcelas/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir parcela de empreitada"); }
  return res.json();
}
export async function excluirParcelaContrato(id: number) {
  const res = await authFetch(`${API}/cadastro/contratos/parcelas/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir parcela de contrato"); }
  return res.json();
}
export async function atualizarParcelaEmpreitada(id: number, dados: { data_vencimento: string; valor: number }) {
  const res = await authFetch(`${API}/cadastro/empreitadas/parcelas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar parcela de empreitada"); }
  return res.json();
}
export async function atualizarParcelaContrato(id: number, dados: { data_vencimento: string; valor: number }) {
  const res = await authFetch(`${API}/cadastro/contratos/parcelas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar parcela de contrato"); }
  return res.json();
}
export async function redistribuirParcelasEmpreitada(empreitadaId: number) {
  const res = await authFetch(`${API}/cadastro/empreitadas/${empreitadaId}/parcelas/redistribuir`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao redistribuir parcelas"); }
  return res.json();
}
export async function redistribuirParcelasContrato(contratoId: number) {
  const res = await authFetch(`${API}/cadastro/contratos/${contratoId}/parcelas/redistribuir`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao redistribuir parcelas"); }
  return res.json();
}

// ── Vale de funcionário (Financeiro > Folha de pagamento) ──
export async function fetchVales() {
  const res = await authFetch(`${API}/cadastro/vales`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Vales error: ${res.status}`);
  return res.json();
}
export async function criarVale(dados: {
  pessoa_id: number; valor_total: number; forma_pagamento: string; data_pagamento: string;
  parcelas: number; competencia_inicio: string; observacao?: string; numero_documento_pagamento?: string;
  // Conta bancária de onde sai o vale — obrigatória quando a forma de pagamento
  // implica saída de caixa agora (dinheiro/pix/transferência); ver _validar_conta_vale.
  conta_corrente_id?: number; confirmar?: boolean;
}) {
  const res = await authFetch(`${API}/cadastro/vales`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(typeof d.detail === "string" ? d.detail : d.detail?.mensagem || "Erro ao lançar vale");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}
export async function atualizarVale(valeId: number, dados: {
  pessoa_id: number; valor_total: number; forma_pagamento: string; data_pagamento: string;
  parcelas: number; competencia_inicio: string; observacao?: string; numero_documento_pagamento?: string;
  conta_corrente_id?: number; confirmar?: boolean;
}) {
  const res = await authFetch(`${API}/cadastro/vales/${valeId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(typeof d.detail === "string" ? d.detail : d.detail?.mensagem || "Erro ao editar vale");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}
/** O que a tela precisa mostrar ANTES de perguntar "excluir este vale?".
 *
 * EXCLUIR ≠ CANCELAR (a distinção que originou esta prévia): excluir é para o
 * vale que NUNCA DEVERIA TER EXISTIDO — apaga o vale E a saída de caixa que
 * ele criou no Financeiro. Para o vale que aconteceu e só não vai mais ser
 * cobrado, a porta é a ação "Cancelar o vale" (painel de ações do vale), que
 * mantém a saída de caixa e tem desfazer.
 *
 * `confirmacao` e `alternativa` vêm PRONTAS do backend de propósito: o número
 * do lançamento (LC-...), o valor e a data da baixa vivem só no Financeiro —
 * montar essa frase no front seria inventar texto com dados que ele não tem.
 * `impedimento` preenchido = o backend vai recusar (400); mostre o motivo em
 * vez de perguntar. */
export type PreviaExclusaoVale = {
  pode_excluir: boolean;
  impedimento: string | null;
  lancamento: {
    numero_lancamento: string | null; valor: number | null;
    data_pagamento: string | null; conta_bancaria: string | null; descricao: string | null;
  } | null;
  confirmacao: string;
  alternativa: string;
};
export async function previaExclusaoVale(valeId: number): Promise<PreviaExclusaoVale> {
  const res = await authFetch(`${API}/cadastro/vales/${valeId}/exclusao`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao conferir o vale"); }
  return res.json();
}
export async function excluirVale(valeId: number) {
  const res = await authFetch(`${API}/cadastro/vales/${valeId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir vale"); }
  return res.json();
}
/** Edita UMA parcela do vale (sem recriar as demais) — se o valor divergir do
 * calculado, o backend responde 409 com {mensagem, valor_calculado,
 * valor_informado, diferenca, parcelas_pendentes_restantes}; reenviar com
 * `acao` ("conceder" | "redistribuir_igual" | "redistribuir_livre") e
 * `confirmar: true` (e `valores_parcelas` se redistribuir_livre). */
export async function atualizarParcelaVale(valeId: number, parcelaId: number, dados: {
  valor: number; acao?: "conceder" | "redistribuir_igual" | "redistribuir_livre";
  valores_parcelas?: Record<number, number>; confirmar?: boolean; confirmar_divergencia_total?: boolean;
  /** Confirma concentrar, em alguma competência, mais de 40% do salário em
   *  desconto de vale — 409 com `{mensagem, competencias_excedidas, limite}`.
   *  Campo PRÓPRIO, separado de `confirmar` (que é a divergência de valor):
   *  são dois avisos diferentes e cada um precisa ser lido antes de passar. */
  confirmar_teto?: boolean;
}) {
  const res = await authFetch(`${API}/cadastro/vales/${valeId}/parcelas/${parcelaId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(typeof d.detail === "string" ? d.detail : d.detail?.mensagem || "Erro ao editar parcela do vale");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}
// ── Ações do dono sobre um vale já lançado (Folha > vale > Ações) ──
// As quatro decisões que existiam na cabeça do dono e não existiam na tela:
// reparcelar o saldo, abater um valor, desconsiderar o vale de UM mês e
// cancelar o vale inteiro. As duas últimas mexem TAMBÉM no Financeiro (o
// valor deixa de ser cobrança da pessoa e vira despesa da fazenda), e é por
// isso que a resposta traz `financeiro` — a tela precisa poder dizer o que
// aconteceu do outro lado. Ver backend/.../cadastro/rh_vale_acoes.py.
export type ValeAcao =
  | "reparcelar" | "abater" | "desconsiderar_mes" | "cancelar"
  // As três voltas atrás (rh_vale_acoes.py): desfazem um abatimento lançado
  // por engano, um mês desconsiderado e o cancelamento do vale inteiro. Só
  // aparecem em `acoes_disponiveis` quando o servidor diz que são possíveis
  // NESTE vale — ver AcoesValeModal.
  | "estornar_abatimento" | "reverter_desconsideracao" | "reverter_cancelamento";
export type ValeAcaoIn = {
  acao: ValeAcao;
  parcelas?: number;              // reparcelar
  competencia_inicio?: string;    // reparcelar (padrão: 1ª competência pendente)
  valor?: number;                 // abater; estornar_abatimento (opcional: tudo)
  conta_corrente_id?: number;     // abater: conta que RECEBEU a devolução (opcional)
  competencia?: string;           // desconsiderar_mes; reverter_desconsideracao (obrigatória)
  motivo?: string;
  /** reparcelar: confirma prosseguir mesmo deixando alguma competência acima
   *  de 40% do salário em desconto de vale — o 409 traz
   *  `{mensagem, competencias_excedidas, limite}`. */
  confirmar?: boolean;
};
export type ValeAcaoContexto = {
  vale_id: number;
  status: "ativo" | "cancelado";
  valor_total: number;
  valor_abatido: number;
  valor_assumido_fazenda: number;
  saldo_pendente: number;
  parcelas: {
    id: number; competencia: string; valor: number;
    assumida_pela_fazenda: boolean; motivo_assuncao: string | null;
    pendente: boolean; competencia_paga: boolean;
  }[];
  acoes_disponiveis: ValeAcao[];
  /** Competências assumidas pela fazenda que ainda dá para voltar a descontar
   *  (folha em aberto) — o seletor de `reverter_desconsideracao` sai daqui, e
   *  não de uma dedução da tela, para não discordar da recusa do POST. Inclui
   *  mês SEM folha lançada: é a única porta do desfazer nesse caso, porque
   *  sem folha não existe painel de descontos onde o botão moraria. */
  competencias_revertiveis: string[];
  /** Por que a volta do cancelamento não está disponível, em palavras — null
   *  quando ela está (ou quando o vale nem está cancelado). Sem isto a tela
   *  ficaria muda justamente diante da ação mais destrutiva das seis. */
  impedimento_reverter_cancelamento?: string | null;
};
export type ValeAcaoResultado = {
  acao: ValeAcao;
  resumo: string;
  vale: ValeAcaoContexto;
  financeiro?: { natureza: "item_de_nota" | "lancamento_proprio" | "sem_lastro"; numero_lancamento: string | null };
  [chave: string]: any;
};

export async function fetchAcoesVale(valeId: number): Promise<ValeAcaoContexto> {
  const res = await authFetch(`${API}/cadastro/vales/${valeId}/acoes`, { cache: "no-store" });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(mensagemErroApi(d.detail) || "Erro ao buscar as ações do vale");
  }
  return res.json();
}

export async function executarAcaoVale(valeId: number, dados: ValeAcaoIn): Promise<ValeAcaoResultado> {
  const res = await authFetch(`${API}/cadastro/vales/${valeId}/acoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(typeof d.detail === "string" ? d.detail : d.detail?.mensagem || "Erro ao executar a ação do vale");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/** G15 — exclui UMA parcela do vale (não o vale inteiro; para isso já existe
 * `excluirVale`). 400 se a parcela já caiu em folha paga, ou se for a única
 * parcela do vale (exclua o vale inteiro nesse caso). Sem `confirmar`, a API
 * responde 409 com `detail = {mensagem, valor_parcela, valor_vale, soma_apos,
 * parcelas_pendentes_posteriores}` — mesmo padrão de `atualizarParcelaVale`;
 * reenviar com `confirmar: true` e a `acao` escolhida. */
export type ExcluirParcelaValeOpts = { acao?: "conceder" | "redistribuir_igual"; confirmar?: boolean };
export async function excluirParcelaVale(valeId: number, parcelaId: number, opts: ExcluirParcelaValeOpts = {}) {
  const qs = new URLSearchParams({ acao: opts.acao || "conceder", confirmar: opts.confirmar ? "true" : "false" });
  const res = await authFetch(`${API}/cadastro/vales/${valeId}/parcelas/${parcelaId}?${qs}`, { method: "DELETE" });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(typeof d.detail === "string" ? d.detail : d.detail?.mensagem || "Erro ao excluir parcela do vale");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// ── Empreitada (Financeiro > Ações > Folha de Pagamento) ──
export async function fetchEmpreitadas() {
  const res = await authFetch(`${API}/cadastro/empreitadas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Empreitadas error: ${res.status}`);
  return res.json();
}
export async function criarEmpreitada(dados: {
  pessoa_id: number; descricao: string; valor_total: number; tipo_pagamento: string; observacao?: string;
  parcelas?: { data_vencimento: string; valor: number }[];
  etapas?: { nome: string; valor: number }[];
}) {
  const res = await authFetch(`${API}/cadastro/empreitadas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar empreitada"); }
  return res.json();
}
export async function concluirEtapaEmpreitada(empreitadaId: number, etapaId: number) {
  const res = await authFetch(`${API}/cadastro/empreitadas/${empreitadaId}/etapas/${etapaId}/concluir`, { method: "PUT" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao concluir etapa"); }
  return res.json();
}

// ── Contrato (Financeiro > Ações > Folha de Pagamento) ──
export async function fetchContratos() {
  const res = await authFetch(`${API}/cadastro/contratos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Contratos error: ${res.status}`);
  return res.json();
}
export async function criarContrato(dados: {
  pessoa_id: number; descricao: string; valor_total: number; forma_pagamento?: string | null; observacao?: string;
  parcelas?: { data_vencimento: string; valor: number }[];
}) {
  const res = await authFetch(`${API}/cadastro/contratos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar contrato"); }
  return res.json();
}
export async function encerrarContrato(id: number) {
  const res = await authFetch(`${API}/cadastro/contratos/${id}/encerrar`, { method: "PUT" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao encerrar contrato"); }
  return res.json();
}

// ── Diária (Financeiro > Ações > Folha de Pagamento) ──
// Por padrão só traz quem ainda está fazendo diárias (status "ativo") — ver
// `incluirFinalizadas` para trazer também as encerradas (ver encerrarDiaria).
export async function fetchDiarias(incluirFinalizadas = false) {
  const qs = incluirFinalizadas ? "?incluir_finalizadas=true" : "";
  const res = await authFetch(`${API}/cadastro/diarias${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Diárias error: ${res.status}`);
  return res.json();
}
/** Encerra o período e, havendo saldo devedor, EMITE a conta a pagar (que
 * cai sozinha na Agenda e em Contas a Pagar). `data_encerramento` é o último
 * dia trabalhado — sem ele o contador não parava e o período "encerrado"
 * seguia somando diária todo dia, invisível. O corpo é opcional no backend
 * por compatibilidade, mas a tela sempre manda a data. */
export async function encerrarDiaria(id: number, dados?: {
  data_encerramento?: string; data_vencimento?: string; emitir_conta?: boolean;
}) {
  const res = await authFetch(`${API}/cadastro/diarias/${id}/encerrar`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados ?? {}),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao encerrar diária"); }
  return res.json();
}
/** Desfaz o encerramento: apaga a cobrança em aberto e descongela o
 * apurado. Recusado (400) se a conta emitida já foi paga — nesse caso o
 * caminho é estornar a baixa em Financeiro › Lançamentos. */
export async function reabrirDiaria(id: number) {
  const res = await authFetch(`${API}/cadastro/diarias/${id}/reabrir`, { method: "PUT" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao reabrir diária"); }
  return res.json();
}
export async function criarDiaria(dados: {
  pessoa_id: number; valor_diaria: number; data_inicio: string; data_fim?: string | null; observacao?: string;
  conta_dia_a_dia?: boolean; auditar_periodicamente?: boolean | null;
  frequencia_auditoria?: string | null; dia_semana_auditoria?: number | null; intervalo_dias_auditoria?: number | null;
}) {
  const res = await authFetch(`${API}/cadastro/diarias`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar diária"); }
  return res.json();
}
export async function atualizarDiaria(diariaId: number, dados: { data_inicio: string; data_fim?: string | null; ajuste_numero_diarias?: number | null }) {
  const res = await authFetch(`${API}/cadastro/diarias/${diariaId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar diária"); }
  return res.json();
}
/** Pagar acima do saldo devedor da diária responde 409 com {mensagem,
 * saldo_devedor, excedente, total_ate_hoje, valor_pago, valor_vale} — pagar a
 * mais continua permitido (acerto final, gorjeta, arredondamento), mas nunca
 * em silêncio: reenviar com `confirmar_excedente: true` depois de mostrar o
 * aviso. Sem isso o operador que digita o total esquecendo o adiantamento
 * paga duas vezes sem nenhum sinal. */
export async function registrarPagamentoDiaria(diariaId: number, dados: {
  data_pagamento: string; valor: number; observacao?: string;
  // Conta bancária de onde sai o pagamento — OPCIONAL (ver _resolver_conta_corrente no backend).
  conta_corrente_id?: number | null;
  confirmar_excedente?: boolean;
}): Promise<{ numero_lancamento_gerado: string } & Record<string, any>> {
  const res = await authFetch(`${API}/cadastro/diarias/${diariaId}/pagamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar pagamento"); }
  return res.json();
}

export type ParametroDiariaPadrao = {
  auditar_periodicamente: boolean; frequencia_auditoria: string;
  dia_semana_auditoria: number; intervalo_dias_auditoria: number;
};
export async function fetchParametroDiariaPadrao(): Promise<ParametroDiariaPadrao> {
  const res = await authFetch(`${API}/cadastro/diarias/parametro-padrao`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Parâmetro padrão de diária error: ${res.status}`);
  return res.json();
}
export async function salvarParametroDiariaPadrao(dados: ParametroDiariaPadrao) {
  const res = await authFetch(`${API}/cadastro/diarias/parametro-padrao`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar parâmetro padrão"); }
  return res.json();
}
export async function responderAuditoriaDiaria(auditoriaId: number, diasTrabalhados: number) {
  const res = await authFetch(`${API}/cadastro/diarias/auditorias/${auditoriaId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dias_trabalhados: diasTrabalhados }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao responder auditoria"); }
  return res.json();
}

// Calendário "estilo Cinemark" de dias trabalhados/folga da diária — todo dia
// nasce marcado como trabalhado (`trabalhado: true`), o usuário toca nos dias
// de folga pra desmarcar. `dias` sempre vem denso (um item por dia corrido no
// período), então o componente só precisa renderizar o que a API manda, sem
// nenhuma lógica de "default" no cliente.
export type DiaTrabalhadoDiaria = { data: string; trabalhado: boolean; meia_diaria: boolean; pago: boolean };
export type DiasDiariaResposta = {
  diaria_id: number; pessoa_nome: string; valor_diaria: number;
  data_inicio: string; data_fim: string | null; hoje: string;
  modo: "ultimo_periodo" | "completo";
  periodo_inicio: string; periodo_fim: string;
  ultima_folga: string | null; controle_por_dia_desde: string | null;
  nunca_auditado: boolean; pago_ate: string | null;
  dias: DiaTrabalhadoDiaria[];
  resumo_periodo: { dias_no_periodo: number; dias_trabalhados: number; dias_folga: number; dias_meia_diaria: number; valor_periodo: number };
};
export async function fetchDiasDiaria(
  diariaId: number, params?: { modo?: "ultimo_periodo" | "completo"; desde?: string; ate?: string },
): Promise<DiasDiariaResposta> {
  const qs = new URLSearchParams();
  if (params?.modo) qs.set("modo", params.modo);
  if (params?.desde) qs.set("desde", params.desde);
  if (params?.ate) qs.set("ate", params.ate);
  const query = qs.toString();
  const res = await authFetch(`${API}/cadastro/diarias/${diariaId}/dias${query ? `?${query}` : ""}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Dias da diária error: ${res.status}`); }
  return res.json();
}
/** Substitui (replace, não merge) o estado dos dias do período informado. Se
 * o período já tem pagamento registrado, a API responde 409 com uma
 * mensagem pronta em `detail` (`err.message`/`err.detail`) — reenviar com
 * `confirmar_periodo_pago: true`; mesmo idioma de `atualizarParcelaVale` etc.
 * (ver `err.status` nesta função). */
export async function salvarDiasDiaria(diariaId: number, dados: {
  periodo_inicio: string; periodo_fim: string; dias_nao_trabalhados: string[];
  dias_meia_diaria?: string[]; confirmar_periodo_pago?: boolean;
}): Promise<unknown> {
  const res = await authFetch(`${API}/cadastro/diarias/${diariaId}/dias`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(mensagemErroApi(d.detail) || "Erro ao salvar dias trabalhados");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// ── Férias (Financeiro > Ações > Folha de Pagamento > Férias / 13º) ──
// ── Média das verbas variáveis habituais (13º, férias e rescisão) ──
// A integração das parcelas SALARIAIS VARIÁVEIS (bonificação por
// produtividade, gueltas, vale-alimentação de natureza salarial…) nas bases de
// 13º, férias e rescisão — CLT, art. 457, §1º, e Súmula 45 do TST. Cada verba
// tem a SUA janela: 13º pelo ANO CIVIL (Decreto 57.155/65, art. 2º), férias
// pelo PERÍODO AQUISITIVO (CLT, art. 142) e aviso prévio indenizado pelos
// ÚLTIMOS 12 MESES.
//
// DESLIGADO POR PADRÃO (Configurações > Parâmetros > Folha de pagamento / RH,
// "O sistema calcula as médias de verbas variáveis…"): sem ele, `aplicada` vem
// false, `media` vem 0 e as três contas saem só sobre o salário-base, exatamente
// como antes. É por isso que a tela precisa saber distinguir "não apurada" de
// "apurada e deu zero" — são coisas diferentes, e o dono tem de ver qual é.
export type JanelaMediaVariaveis = "ano_civil" | "periodo_aquisitivo" | "ultimos_12_meses";
export type RubricaDaMedia = { codigo: string; rotulo: string; valor: number };
export type CompetenciaDaMedia = {
  competencia: string; rotulo: string; valor: number;
  /** Contrato vigente, mas sem folha lançada naquele mês. Entra no divisor
   *  valendo ZERO (Decreto 57.155/65, art. 2º: "meses de vigência do
   *  contrato"), e por isso precisa aparecer marcado — é o que explica um
   *  divisor maior que o número de meses com movimento. */
  sem_folha: boolean;
  rubricas: RubricaDaMedia[];
};
export type ComposicaoMediaVariaveis = {
  /** false = a média NÃO foi apurada (parâmetro desligado). Diferente de
   *  `media === 0`, que é "apurada e a pessoa não teve variável no período". */
  aplicada: boolean;
  janela: JanelaMediaVariaveis;
  fundamento: string;
  motivo?: string;
  inicio: string | null; fim: string | null; rotulo_janela: string;
  competencias: CompetenciaDaMedia[];
  competencias_sem_folha: number;
  total: number;
  divisor: number;
  divisor_imposto: boolean;
  criterio_divisor: string;
  media: number;
};

/** Prévia da média — só lê, não grava. Existe para o "valor sugerido" que a
 *  tela calcula no navegador não divergir do que o servidor vai gravar. */
export async function fetchPreviaMediaVariaveis(params: {
  pessoa_id: number; janela: JanelaMediaVariaveis;
  inicio?: string; fim?: string; ano?: number; meses_trabalhados?: number;
}): Promise<ComposicaoMediaVariaveis> {
  const busca = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") busca.set(k, String(v)); });
  const res = await authFetch(`${API}/cadastro/media-verbas-variaveis?${busca.toString()}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao calcular a média de verbas variáveis"); }
  return res.json();
}

// Controle DENTRO do app (cálculo, lançamento e acompanhamento) — sem envio
// ao eSocial (fora de escopo).
export type FeriasDados = {
  pessoa_id: number; periodo_aquisitivo_inicio: string; periodo_aquisitivo_fim: string;
  dias_direito?: number; dias_gozados: number; data_inicio_gozo: string; data_fim_gozo: string;
  abono_pecuniario_dias?: number; data_pagamento?: string; status?: string; observacao?: string;
  centro_custo?: string;
  // Conta bancária de onde sai o pagamento — OPCIONAL (ver _resolver_conta_corrente no backend).
  conta_corrente_id?: number | null;
};
export type RegistroFerias = FeriasDados & {
  id: number; pessoa_nome: string; valor_ferias: number; valor_terco_constitucional: number;
  valor_total: number; numero_lancamento_gerado: string | null; usuario_nome?: string | null;
  status: string;
  /** Média das variáveis do PERÍODO AQUISITIVO que entrou na base (CLT, art.
   *  142). `null` = não apurada — o lançamento saiu só sobre o salário-base. */
  media_variaveis?: number | null;
  /** A composição CONGELADA no lançamento — é ela que o dono abre para
   *  conferir de onde saiu a média. Nunca reapurada na leitura. */
  media_variaveis_detalhe?: ComposicaoMediaVariaveis | null;
};
export async function fetchFerias(): Promise<RegistroFerias[]> {
  const res = await authFetch(`${API}/cadastro/ferias`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Férias error: ${res.status}`);
  return res.json();
}
export async function criarFerias(dados: FeriasDados) {
  const res = await authFetch(`${API}/cadastro/ferias`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar férias"); }
  return res.json();
}
export async function atualizarFerias(id: number, dados: FeriasDados) {
  const res = await authFetch(`${API}/cadastro/ferias/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar férias"); }
  return res.json();
}
export async function excluirFerias(id: number) {
  const res = await authFetch(`${API}/cadastro/ferias/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir férias"); }
  return res.json();
}

// ── 13º salário (Financeiro > Ações > Folha de Pagamento > Férias / 13º) ──
export type DecimoTerceiroDados = {
  pessoa_id: number; ano: number; parcela?: string; meses_trabalhados: number;
  valor_inss?: number; valor_ir?: number; data_pagamento?: string; status?: string;
  observacao?: string; centro_custo?: string;
  // Conta bancária de onde sai o pagamento — OPCIONAL (ver _resolver_conta_corrente no backend).
  conta_corrente_id?: number | null;
};
export type RegistroDecimoTerceiro = DecimoTerceiroDados & {
  id: number; pessoa_nome: string; valor_bruto: number; valor_liquido: number;
  numero_lancamento_gerado: string | null; usuario_nome?: string | null; status: string;
  valor_integral?: number | null;
  /** Média das variáveis do ANO CIVIL, dividida pelos mesmos avos do 13º
   *  (Decreto 57.155/65, art. 2º). `null` = não apurada. */
  media_variaveis?: number | null;
  media_variaveis_detalhe?: ComposicaoMediaVariaveis | null;
};
export async function fetchDecimoTerceiro(): Promise<RegistroDecimoTerceiro[]> {
  const res = await authFetch(`${API}/cadastro/decimo-terceiro`, { cache: "no-store" });
  if (!res.ok) throw new Error(`13º salário error: ${res.status}`);
  return res.json();
}
export async function criarDecimoTerceiro(dados: DecimoTerceiroDados) {
  const res = await authFetch(`${API}/cadastro/decimo-terceiro`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar 13º salário"); }
  return res.json();
}
export async function atualizarDecimoTerceiro(id: number, dados: DecimoTerceiroDados) {
  const res = await authFetch(`${API}/cadastro/decimo-terceiro/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar 13º salário"); }
  return res.json();
}
export async function excluirDecimoTerceiro(id: number) {
  const res = await authFetch(`${API}/cadastro/decimo-terceiro/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir 13º salário"); }
  return res.json();
}

// ── Rescisão (Financeiro > Ações > Folha de Pagamento > Férias / 13º / Rescisão) ──
// Verbas rescisórias da CLT (saldo de salário, aviso prévio, férias
// vencidas/proporcionais, 13º proporcional, multa de FGTS estimada) para as
// 4 modalidades mais comuns. Sem eSocial/TRCT oficial (fora de escopo, mesma
// linha de férias/13º). Diferente de férias/13º, não há registro de
// acompanhamento dedicado — só o lançamento em Contas a Pagar.
export type TipoRescisao = "sem_justa_causa" | "pedido_demissao" | "justa_causa" | "acordo_mutuo";
export type RescisaoDados = {
  pessoa_id: number; tipo_rescisao: TipoRescisao; data_desligamento: string;
  dias_ferias_vencidas?: number; aviso_previo_trabalhado?: boolean;
  data_pagamento?: string; status?: string; observacao?: string; centro_custo?: string;
};
/** Saldo de vale ainda COBRÁVEL da pessoa (parcelas não assumidas pela
 *  fazenda, de vales ativos, em competências sem folha paga) — o número que
 *  faltava na rescisão. Sem ele o campo "Vale em aberto" nascia em zero e era
 *  assim que ficava: uma rescisão real foi fechada deixando R$ 6.485,00 de
 *  vale de pé, em competências que nunca mais teriam folha para descontar.
 *  O backend recusa fechar a rescisão enquanto sobrar saldo não endereçado. */
export type SaldoValeEmAberto = {
  total: number;
  competencias: { competencia: string; valor: number }[];
  parcela_ids: number[];
};
export type CalculoRescisao = {
  tipo_rescisao: TipoRescisao;
  /** O saldo de vale a descontar — usado para pré-preencher (editável) o
   *  campo "Vale em aberto" da simulação. */
  vale_em_aberto: SaldoValeEmAberto;
  saldo_salario: { dias_trabalhados_mes: number; valor: number };
  aviso_previo: { devido: boolean; dias: number; dias_indenizados: number; trabalhado: boolean; valor: number };
  ferias_vencidas: { valor_ferias: number; valor_terco_constitucional: number; valor_abono: number; valor_total: number };
  ferias_proporcionais: { valor_ferias: number; valor_terco_constitucional: number; valor_abono: number; valor_total: number; meses: number };
  decimo_terceiro_proporcional: { meses: number; valor: number };
  fgts: {
    estimativa: boolean; percentual_mensal_estimado: number; meses_considerados: number;
    deposito_total_estimado: number; percentual_multa: number; multa: number; percentual_saque_permitido: number;
  };
  data_referencia_tempo_servico: string;
  /** As três médias aplicadas — uma por natureza de verba. */
  medias_variaveis: { decimo_terceiro: number; ferias: number; aviso_previo: number; alguma: boolean };
  /** As três composições, para a tela mostrar de onde saiu cada média ANTES
   *  de o dono decidir lançar. */
  medias_variaveis_composicao: MediasVariaveisComposicao;
  valor_total: number;
};
export async function simularRescisao(dados: RescisaoDados): Promise<CalculoRescisao> {
  const res = await authFetch(`${API}/cadastro/rescisao/calcular`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao calcular rescisão"); }
  return res.json();
}

// Simulação/fechamento persistidos de rescisão (fluxo em 4 etapas: simular →
// editar verbas → fechar → acompanhar). Diferente de `simularRescisao`
// acima (só calcula, não grava nada), estes endpoints (plural `/rescisoes`)
// gravam um rascunho editável que só vira lançamento em Contas a Pagar
// quando fechado.
export type StatusRescisao = "simulacao" | "fechada";
export type FormaLancamentoRescisao = "unico" | "detalhado";
export type LinhaDetalheRescisao = { label: string; valor: number };
/** As três composições da rescisão, chaveadas pela verba: cada uma tem a SUA
 *  janela, e é por isso que são três e não uma. */
export type MediasVariaveisComposicao = {
  decimo_terceiro: ComposicaoMediaVariaveis;
  ferias: ComposicaoMediaVariaveis;
  aviso_previo: ComposicaoMediaVariaveis;
};

export type RescisaoSimulacaoDados = {
  pessoa_id: number; tipo_rescisao: TipoRescisao; data_desligamento: string;
  dias_ferias_vencidas?: number; aviso_previo_trabalhado?: boolean;
  observacao?: string | null; centro_custo?: string;
  // Overrides das verbas calculadas — null/omitido = servidor usa o valor calculado.
  valor_saldo_salario?: number | null; valor_aviso_previo?: number | null;
  valor_ferias_vencidas?: number | null; valor_ferias_proporcionais?: number | null;
  valor_decimo_terceiro_proporcional?: number | null; valor_multa_fgts?: number | null;
  // Descontos — sempre manuais (o servidor nunca calcula sozinho).
  valor_inss?: number; valor_ir?: number; valor_vale_em_aberto?: number;
};

export type RegistroRescisaoFuncionario = {
  id: number; pessoa_id: number | null; tipo_rescisao: TipoRescisao | null;
  data_desligamento: string; dias_ferias_vencidas: number; aviso_previo_trabalhado: boolean;
  salario_base: number; data_admissao: string | null;
  valor_saldo_salario: number; valor_aviso_previo: number; valor_ferias_vencidas: number;
  valor_ferias_proporcionais: number; valor_decimo_terceiro_proporcional: number; valor_multa_fgts: number;
  valor_inss: number; valor_ir: number; valor_vale_em_aberto: number;
  valor_bruto: number; valor_total: number;
  dias_saldo_salario: number; dias_aviso_previo: number; dias_aviso_previo_indenizados: number;
  meses_ferias_proporcionais: number; meses_decimo_terceiro: number; percentual_multa_fgts: number;
  status: StatusRescisao; forma_lancamento: FormaLancamentoRescisao | null;
  data_fechamento: string | null; data_pagamento: string | null; inativou_pessoa: boolean;
  observacao: string | null; numero_lancamento_gerado: string | null; centro_custo: string | null;
  criado_em: string; usuario_id: number | null; fazenda_id: number;
  pessoa_nome: string; usuario_nome: string | null; detalhe: LinhaDetalheRescisao[]; legado: boolean;
  /** As três médias congeladas no cálculo — `null` quando não apuradas. */
  media_variaveis_decimo_terceiro?: number | null;
  media_variaveis_ferias?: number | null;
  media_variaveis_aviso_previo?: number | null;
  medias_variaveis_composicao?: MediasVariaveisComposicao | null;
  /** Só nas SIMULAÇÕES (null nas fechadas e nas legado): o saldo de vale ainda
   *  cobrável. Numa rescisão fechada o saldo já foi resolvido — o fechamento
   *  recusa enquanto sobrar. */
  vale_em_aberto?: SaldoValeEmAberto | null;
  // Só presentes em linhas legado (projeção de ContaGerencial pré-migração).
  legado_conta_id?: number; descricao?: string;
};

export type RescisaoFecharDados = {
  forma_lancamento?: FormaLancamentoRescisao; status_pagamento?: "pendente" | "pago";
  data_pagamento?: string | null; inativar_pessoa?: boolean; centro_custo?: string | null;
  // Conta bancária de onde sai o pagamento — OPCIONAL (ver _resolver_conta_corrente
  // no backend); aplicada a todas as contas geradas, mesmo no fechamento "detalhado".
  conta_corrente_id?: number | null;
};

export async function fetchRescisoesFuncionario(): Promise<RegistroRescisaoFuncionario[]> {
  const res = await authFetch(`${API}/cadastro/rescisoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Rescisões error: ${res.status}`);
  return res.json();
}
export async function criarSimulacaoRescisao(dados: RescisaoSimulacaoDados): Promise<RegistroRescisaoFuncionario> {
  const res = await authFetch(`${API}/cadastro/rescisoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar simulação de rescisão"); }
  return res.json();
}
export async function atualizarSimulacaoRescisao(id: number, dados: RescisaoSimulacaoDados): Promise<RegistroRescisaoFuncionario> {
  const res = await authFetch(`${API}/cadastro/rescisoes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar simulação de rescisão"); }
  return res.json();
}
export async function excluirSimulacaoRescisao(id: number) {
  const res = await authFetch(`${API}/cadastro/rescisoes/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir simulação de rescisão"); }
  return res.json();
}
export async function fecharRescisao(id: number, dados: RescisaoFecharDados): Promise<RegistroRescisaoFuncionario> {
  const res = await authFetch(`${API}/cadastro/rescisoes/${id}/fechar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao fechar rescisão"); }
  return res.json();
}

// Último valor unitário pago num produto ou serviço, para a mini-observação
// abaixo do item em Contas a pagar. Devolve `null` quando o item nunca foi
// comprado — a tela NÃO deve inventar número nesse caso, apenas não mostrar
// a observação. Independe de quantidade e valor informados no item atual.
export type UltimoPrecoProduto = {
  produto: string;
  valor_unitario: number;
  data: string | null;
  numero_lancamento: string | null;
} | null;

export async function fetchUltimoPrecoProduto(produto: string): Promise<UltimoPrecoProduto> {
  const nome = (produto || "").trim();
  if (!nome) return null;
  const res = await authFetch(`${API}/financeiro/ultimo-preco?produto=${encodeURIComponent(nome)}`, { cache: "no-store" });
  if (!res.ok) return null;   // sem histórico não é erro — é ausência de observação
  const d = await res.json().catch(() => null);
  return d && typeof d.valor_unitario === "number" ? d : null;
}

// Comprovante de pagamento de vale. Espelha o padrão já usado no anexo de
// lançamento financeiro (anexarArquivoLancamentoPorId acima): multipart, o
// arquivo vai para o mesmo Storage, e a categoria default é "Comprovante".
// `tipo` distingue os dois modelos de vale que existem no sistema — o vale
// marcado a partir de um item de lançamento já herda o anexo da própria nota.
export async function anexarComprovanteVale(
  tipo: "funcionario" | "avulso", valeId: number, file: File,
): Promise<{ id: number; nome_arquivo: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/cadastro/vales/${tipo}/${valeId}/comprovante`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao anexar o comprovante"); }
  return res.json();
}

export async function listarComprovantesVale(
  tipo: "funcionario" | "avulso", valeId: number,
): Promise<{ id: number; nome_arquivo: string; mime_type: string; criado_em: string }[]> {
  const res = await authFetch(`${API}/cadastro/vales/${tipo}/${valeId}/comprovante`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function excluirComprovanteVale(anexoId: number) {
  const res = await authFetch(`${API}/cadastro/vales/comprovante/${anexoId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir o comprovante"); }
  return res.json();
}

export function urlComprovanteVale(anexoId: number): string {
  return `${API}/cadastro/vales/comprovante/${anexoId}`;
}

/** Vale maior que o saldo pendente do alvo responde 409 com {mensagem,
 * saldo_pendente, excedente} — adiantar acima do pendente é legítimo (etapa
 * ainda não cadastrada, contrato a prorrogar, contrato sem frequência
 * definida, que não tem parcela nenhuma), então não se recusa: avisa-se e,
 * com `confirmar_excedente: true`, a sobra fica gravada como valor não
 * abatido em vez de sumir do controle. */
export async function criarValeAvulso(dados: {
  origem_tipo: "empreitada" | "contrato" | "diaria"; origem_id: number; valor: number;
  forma_pagamento: string; data_pagamento: string; observacao?: string;
  // Conta bancária de onde sai o vale — obrigatória quando a forma de pagamento
  // implica saída de caixa agora (dinheiro/pix/transferência); ver _validar_conta_vale_avulso.
  conta_corrente_id?: number;
  confirmar_excedente?: boolean;
}) {
  const res = await authFetch(`${API}/cadastro/vale-avulso`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar vale"); }
  return res.json();
}
export async function fetchValesAvulsos() {
  const res = await authFetch(`${API}/cadastro/vale-avulso/todos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Vales avulsos error: ${res.status}`);
  return res.json();
}
/** Se `valor` divergir do valor atual do vale, o backend responde 409 com
 * {mensagem, valor_calculado, valor_informado, diferenca}; reenviar com
 * `acao` ("conceder" | "redistribuir_igual" | "redistribuir_livre") e
 * `confirmar: true` (e `valores_itens` — parcela/etapa do alvo → novo valor —
 * se redistribuir_livre). Resposta: {vale, origem} (origem já atualizada). */
export async function atualizarValeAvulso(valeId: number, dados: {
  origem_tipo: "empreitada" | "contrato" | "diaria"; origem_id: number; valor: number;
  forma_pagamento: string; data_pagamento: string; observacao?: string;
  conta_corrente_id?: number;
  acao?: "conceder" | "redistribuir_igual" | "redistribuir_livre";
  valores_itens?: Record<number, number>; confirmar?: boolean;
}) {
  const res = await authFetch(`${API}/cadastro/vale-avulso/${valeId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(typeof d.detail === "string" ? d.detail : d.detail?.mensagem || "Erro ao editar vale");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}
/** Prévia da exclusão do vale avulso — mesma ideia (e mesmo formato) de
 * `previaExclusaoVale`. Aqui a alternativa é editar o vale: "cancelar o
 * vale" é ação do vale de FUNCIONÁRIO, não existe para o avulso. */
export async function previaExclusaoValeAvulso(valeId: number): Promise<PreviaExclusaoVale> {
  const res = await authFetch(`${API}/cadastro/vale-avulso/${valeId}/exclusao`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao conferir o vale"); }
  return res.json();
}
export async function excluirValeAvulso(valeId: number) {
  const res = await authFetch(`${API}/cadastro/vale-avulso/${valeId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir vale"); }
  return res.json();
}

export async function criarAnimalFicha(dados: Record<string, any>) {
  const res = await authFetch(`${API}/cadastro/animais`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(mensagemErroApi(d.detail) || "Erro ao cadastrar animal");
    err.status = res.status;
    throw err;
  }
  return res.json();
}
export async function atualizarAnimalFicha(numero: string, dados: Record<string, any>) {
  const res = await authFetch(`${API}/cadastro/animais/${numero}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(mensagemErroApi(d.detail) || "Erro ao atualizar ficha");
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// Corrige o número/brinco de um animal (01/09/2026) — só admin do tenant
// (backend: Depends(exigir_admin)); a Ficha do Animal reforça isso com um
// cadeado que precisa ser destravado antes de mostrar o campo.
export async function renumerarAnimal(numeroAtual: string, novoNumero: string) {
  const res = await authFetch(`${API}/cadastro/animais/${numeroAtual}/renumerar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ novo_numero: novoNumero }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(mensagemErroApi(d.detail) || "Erro ao renumerar animal");
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<{ numero_antigo: string; numero_novo: string; tabelas_afetadas: string[] }>;
}

// Fêmeas da fazenda com pelo menos 1 parto registrado — matrizes possíveis
// para a sugestão/autocomplete do campo "Número da mãe" na ficha do animal
// (CadastroAnimalForm). O backend valida a compatibilidade de verdade ao
// salvar (ver validar_e_vincular_mae) — isto aqui é só a sugestão no campo.
export type MatrizComParto = { numero: string; nome: string | null };
export async function fetchMatrizesComParto(): Promise<MatrizComParto[]> {
  const res = await authFetch(`${API}/cadastro/animais/matrizes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Matrizes com parto error: ${res.status}`);
  return res.json();
}

export async function fetchItensEstoqueCadastro() {
  const res = await authFetch(`${API}/cadastro/estoque-itens`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Itens de estoque error: ${res.status}`);
  return res.json();
}
export async function criarItemEstoque(dados: Record<string, unknown>) {
  const res = await authFetch(`${API}/estoque/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cadastrar item de estoque"); }
  return res.json();
}
export async function atualizarItemEstoque(id: number, dados: Record<string, unknown>) {
  const res = await authFetch(`${API}/estoque/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar item de estoque"); }
  return res.json();
}
export async function atualizarMetaEstoque(id: number, dados: { unidade_embalagem?: string | null; medida_embalagem?: string | null; quantidade_embalagem?: number | null; fornecedor_id?: number | null; conta_gerencial_despesa_padrao?: string | null; estocavel?: boolean | null }) {
  const res = await authFetch(`${API}/cadastro/estoque-itens/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar item"); }
  return res.json();
}
export async function excluirItemEstoque(id: number): Promise<{ excluido: boolean }> {
  const res = await authFetch(`${API}/estoque/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir item de estoque"); }
  return res.json();
}

export async function fetchParametros() {
  const res = await authFetch(`${API}/parametros/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Parâmetros error: ${res.status}`);
  return res.json();
}

// Secagem/Parto sugerem mover o animal para o lote de secas/lote 03 — este
// parâmetro (Configurações > Parâmetros) decide se o formulário pergunta
// (padrão) ou move sozinho, sem popup de confirmação.
export async function fetchTransferenciaLoteAutomatica(): Promise<boolean> {
  const res = await authFetch(`${API}/parametros/transferencia-lote-automatica`, { cache: "no-store" });
  if (!res.ok) return false;
  return (await res.json()).automatica === true;
}

export async function atualizarParametro(chave: string, valor: number | string | boolean) {
  const res = await authFetch(`${API}/parametros/${chave}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ valor }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar parâmetro"); }
  return res.json();
}

// ── Manual da Fazenda (rotina automática + insights + sugestões) ──
export type ParametroManualFazenda = {
  id: number;
  email_semanal_ativo: boolean;
  ultimo_envio_semanal_em: string | null;
  responsavel_manejo_nome: string | null;
  responsavel_manejo_empresa: string | null;
  tem_contrato_manejo: boolean;
  contrato_manejo_arquivo_nome: string | null;
};
export type SugestaoManualFazenda = { id: number; texto: string; categoria: string; ativo: boolean; ordem: number };
export type RotinaItemManual = { titulo: string; descricao: string; proximas_datas: string[] } | null;
export type ManualFazenda = {
  gerado_em: string;
  responsavel_manejo: { nome: string | null; empresa: string | null; tem_contrato: boolean; contrato_arquivo_nome: string | null };
  rotina: {
    bst: RotinaItemManual;
    visita_reprodutiva: RotinaItemManual;
    sanitario: { titulo: string; vencidas: number; proxima: { protocolo: string; data: string; animal: string } | null };
    compras: { nome: string; quantidade: number; estoque_minimo: number }[];
  };
  resultado: {
    total_animais: number; vacas_lactacao: number;
    taxa_prenhez_pct: number | null; taxa_concepcao_pct: number | null; taxa_servico_pct: number | null;
    producao_media_kg: number | null; producao_total_dia_kg: number | null; del_medio: number | null;
  };
  insights: { categoria: string; metrica: string; tendencia: "alta" | "queda"; variacao_pct: number; valor_recente: number; valor_anterior: number; unidade: string; texto: string }[];
  sugestoes: { texto: string; categoria: string; origem: "usuario" | "automatica" }[];
};

export async function fetchManualFazenda() {
  const res = await authFetch(`${API}/manual-fazenda/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Manual da Fazenda error: ${res.status}`);
  return res.json() as Promise<ManualFazenda>;
}
export async function baixarPdfManualFazenda(modo: "baixar" | "compartilhar" = "baixar") {
  const res = await authFetch(`${API}/manual-fazenda/pdf`);
  if (!res.ok) throw new Error(`Erro ao gerar PDF do Manual da Fazenda: ${res.status}`);
  const blob = await res.blob();
  const { baixarArquivo, salvarArquivo } = await import("./nativo");
  if (modo === "compartilhar") await baixarArquivo(blob, "manual_da_fazenda.pdf");
  else await salvarArquivo(blob, "manual_da_fazenda.pdf");
}
export async function fetchParametrosManualFazenda() {
  const res = await authFetch(`${API}/manual-fazenda/parametros`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Parâmetros do Manual da Fazenda error: ${res.status}`);
  return res.json() as Promise<ParametroManualFazenda>;
}
export async function atualizarParametrosManualFazenda(dados: {
  email_semanal_ativo: boolean; responsavel_manejo_nome?: string | null; responsavel_manejo_empresa?: string | null; tem_contrato_manejo: boolean;
}) {
  const res = await authFetch(`${API}/manual-fazenda/parametros`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar parâmetros do Manual da Fazenda"); }
  return res.json() as Promise<ParametroManualFazenda>;
}
export async function anexarContratoManejo(arquivo: File) {
  const form = new FormData();
  form.append("arquivo", arquivo);
  const res = await authFetch(`${API}/manual-fazenda/contrato-anexo`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao anexar contrato"); }
  return res.json() as Promise<ParametroManualFazenda>;
}
export async function fetchSugestoesManualFazenda() {
  const res = await authFetch(`${API}/manual-fazenda/sugestoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Sugestões do Manual da Fazenda error: ${res.status}`);
  return res.json() as Promise<SugestaoManualFazenda[]>;
}
export async function criarSugestaoManualFazenda(dados: { texto: string; categoria: string; ativo: boolean; ordem: number }) {
  const res = await authFetch(`${API}/manual-fazenda/sugestoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar sugestão"); }
  return res.json() as Promise<SugestaoManualFazenda>;
}
export async function atualizarSugestaoManualFazenda(id: number, dados: { texto: string; categoria: string; ativo: boolean; ordem: number }) {
  const res = await authFetch(`${API}/manual-fazenda/sugestoes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar sugestão"); }
  return res.json() as Promise<SugestaoManualFazenda>;
}
export async function excluirSugestaoManualFazenda(id: number) {
  const res = await authFetch(`${API}/manual-fazenda/sugestoes/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir sugestão"); }
  return res.json();
}

// ── Lotes (cadastro + parâmetros) ──
// `incluirInativos`: só a tela de cadastro (Configurações) precisa ver lotes
// inativos — seletores de destino/movimentação usam o padrão (só ativos).
export async function fetchLotes(opts?: { incluirInativos?: boolean }) {
  const qs = opts?.incluirInativos ? "?incluir_inativos=true" : "";
  const res = await authFetch(`${API}/lotes/${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lotes error: ${res.status}`);
  return res.json();
}
// `dados` inclui código/nome, faixas (del/producao/peso/dias_para_parto/idade_dias)
// e os critérios booleanos (status_lactacao, categorias, pre_parto, em_tratamento,
// novilhas_inseminadas, novilhas_gestantes) — ver fazenda.rules.lote_criterios.
export async function criarLote(dados: Record<string, any>) {
  const res = await authFetch(`${API}/lotes/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar lote"); }
  return res.json();
}
export async function atualizarLote(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/lotes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar lote"); }
  return res.json();
}
export async function previewCriteriosLote(dados: Record<string, any>) {
  const res = await authFetch(`${API}/lotes/preview`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) throw new Error(`Prévia de critérios error: ${res.status}`);
  return res.json();
}

// ── Safra (Configurações > Cadastro) — Opção A do plano de custo agrícola:
// nome, hectares e toneladas produzidas, usados pelo relatório de custo por
// hectare/tonelada (ver fetchCustoSafra, abaixo) ──
export async function fetchSafras() {
  const res = await authFetch(`${API}/safras/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Safras error: ${res.status}`);
  return res.json();
}
export async function criarSafra(dados: Record<string, any>) {
  const res = await authFetch(`${API}/safras/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar safra"); }
  return res.json();
}
export async function atualizarSafra(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/safras/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar safra"); }
  return res.json();
}

// ── Movimentação de animais entre lotes ──
export async function fetchMovimentacoes(params?: { numero_matriz?: string; data_inicio?: string; data_fim?: string }) {
  const qs = new URLSearchParams();
  if (params?.numero_matriz) qs.set("numero_matriz", params.numero_matriz);
  if (params?.data_inicio) qs.set("data_inicio", params.data_inicio);
  if (params?.data_fim) qs.set("data_fim", params.data_fim);
  const res = await authFetch(`${API}/movimentacoes/?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Movimentações error: ${res.status}`);
  return res.json();
}
export async function fetchSugestoesMovimentacao() {
  const res = await authFetch(`${API}/movimentacoes/sugestoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Sugestões de movimentação error: ${res.status}`);
  return res.json();
}

// Resposta real do backend (fazenda/api/routers/movimentacoes.py `mover_animais`):
// `movidos` conta quantos animais tiveram o lote de fato alterado;
// `nao_encontrados` lista números que não existem (fazenda_id errado, digitado
// errado etc.) — usado para não reportar "movido com sucesso" quando na
// verdade ninguém foi movido.
export type ResultadoMovimentacao = { movidos: number; nao_encontrados: string[] };
// De onde veio a movimentação — não confundir com `motivo` (texto livre, pode
// repetir o mesmo valor tanto numa troca manual quanto numa automática). Ver
// o comentário completo em fazenda.models.animais.MovimentoLote.origem.
// - "manual": Rebanho > Movimentar animais, ou inativação de lote (Configurações).
// - "sugestao_confirmada": pop-up de sugestão pós-evento (parto/secagem/pré-parto) confirmado pelo usuário.
// - "sugestao_automatica": mesma sugestão do motor de critérios, aplicada sem pop-up (ex.: cria no parto em lote).
// - "sugestao_passiva": card da Agenda ou tela Rebanho > Sugestões de movimentação.
export type OrigemMovimentacao = "manual" | "sugestao_confirmada" | "sugestao_automatica" | "sugestao_passiva" | "importacao";
export async function criarMovimentacao(dados: {
  data_movimento: string; hora_movimento?: string; motivo?: string; observacao?: string;
  responsavel?: string; lote_destino_codigo: string; animais: string[]; origem?: OrigemMovimentacao;
}): Promise<ResultadoMovimentacao> {
  const res = await authFetch(`${API}/movimentacoes/mover`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao mover animais"); }
  return res.json();
}

// ── Parâmetro de agendamento das sugestões de movimentação (Configurações > Cadastro > Lotes) ──
export type ParametroAgendamentoMovimentacao = { modo: "na_data_parametro" | "dia_fixo_semana"; dia_semana: number };
export async function fetchParametroAgendamentoMovimentacao(): Promise<ParametroAgendamentoMovimentacao> {
  const res = await authFetch(`${API}/movimentacoes/parametro-agendamento`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Parâmetro de agendamento error: ${res.status}`);
  return res.json();
}
export async function salvarParametroAgendamentoMovimentacao(dados: ParametroAgendamentoMovimentacao) {
  const res = await authFetch(`${API}/movimentacoes/parametro-agendamento`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar parâmetro"); }
  return res.json();
}

// ── Motivos de movimentação (Configurações > Cadastro) ──
export async function fetchMotivosMovimentacao() {
  const res = await authFetch(`${API}/movimentacoes/motivos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Motivos de movimentação error: ${res.status}`);
  return res.json();
}
export async function fetchMotivosMovimentacaoCadastro() {
  const res = await authFetch(`${API}/movimentacoes/motivos/cadastro`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Motivos de movimentação error: ${res.status}`);
  return res.json();
}
export async function criarMotivoMovimentacao(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/movimentacoes/motivos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar motivo"); }
  return res.json();
}
export async function atualizarMotivoMovimentacao(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/movimentacoes/motivos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar motivo"); }
  return res.json();
}

// ── Motivos de baixa (Configurações > Cadastro) ──
export async function fetchMotivosBaixaCadastro() {
  const res = await authFetch(`${API}/cadastro/motivos-baixa`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Motivos de baixa error: ${res.status}`);
  return res.json();
}
export async function criarMotivoBaixa(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/motivos-baixa`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar motivo de baixa"); }
  return res.json();
}
export async function atualizarMotivoBaixa(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/motivos-baixa/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar motivo de baixa"); }
  return res.json();
}

// ── Raças (Configurações > Cadastro) ──
export async function fetchRacas() {
  const res = await authFetch(`${API}/cadastro/racas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Raças error: ${res.status}`);
  return res.json();
}
export async function criarRaca(dados: { nome: string; nota?: string | null; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/racas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar raça"); }
  return res.json();
}
export async function atualizarRaca(id: number, dados: { nome: string; nota?: string | null; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/racas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar raça"); }
  return res.json();
}

export type ItemCadastroSimples = { id: number; nome: string; ativo: boolean };

// Fábrica de fetch/criar/atualizar para os cadastros "nome + ativo" simples
// (mesmo padrão de Raça acima) — evita repetir a mesma tripla de funções
// para cada cadastro novo (ver Local de Armazenamento/Categoria/Finalidade/
// Unidade/Unidade de embalagem/Unidade de medida do estoque, abaixo).
function criarApiCadastroSimples(rota: string, rotulo: string) {
  return {
    fetch: async (): Promise<ItemCadastroSimples[]> => {
      const res = await authFetch(`${API}/cadastro/${rota}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`${rotulo} error: ${res.status}`);
      return res.json();
    },
    criar: async (dados: { nome: string; ativo?: boolean }): Promise<ItemCadastroSimples> => {
      const res = await authFetch(`${API}/cadastro/${rota}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Erro ao criar ${rotulo.toLowerCase()}`); }
      return res.json();
    },
    atualizar: async (id: number, dados: { nome: string; ativo: boolean }): Promise<ItemCadastroSimples> => {
      const res = await authFetch(`${API}/cadastro/${rota}/${id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Erro ao atualizar ${rotulo.toLowerCase()}`); }
      return res.json();
    },
    excluir: async (id: number): Promise<{ excluido: boolean }> => {
      const res = await authFetch(`${API}/cadastro/${rota}/${id}`, { method: "DELETE" });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Erro ao excluir ${rotulo.toLowerCase()}`); }
      return res.json();
    },
  };
}

// Cadastros de apoio ao item de estoque (Configurações > Cadastro > Estoque)
// — antes listas fixas (CATEGORIAS_ESTOQUE, FINALIDADES_ESTOQUE, UNIDADES,
// UNIDADES_EMBALAGEM, MEDIDAS_EMBALAGEM) ou texto livre sem sugestão
// (local_armazenamento), agora cadastráveis.
const apiLocaisArmazenamento = criarApiCadastroSimples("locais-armazenamento", "Local de armazenamento");
export const fetchLocaisArmazenamento = apiLocaisArmazenamento.fetch;
export const criarLocalArmazenamento = apiLocaisArmazenamento.criar;
export const atualizarLocalArmazenamento = apiLocaisArmazenamento.atualizar;
export const excluirLocalArmazenamento = apiLocaisArmazenamento.excluir;

const apiCategoriasEstoque = criarApiCadastroSimples("categorias-estoque", "Categoria de estoque");
export const fetchCategoriasEstoqueCadastro = apiCategoriasEstoque.fetch;
export const criarCategoriaEstoque = apiCategoriasEstoque.criar;
export const atualizarCategoriaEstoque = apiCategoriasEstoque.atualizar;
export const excluirCategoriaEstoque = apiCategoriasEstoque.excluir;

const apiFinalidadesEstoque = criarApiCadastroSimples("finalidades-estoque", "Finalidade de estoque");
export const fetchFinalidadesEstoqueCadastro = apiFinalidadesEstoque.fetch;
export const criarFinalidadeEstoque = apiFinalidadesEstoque.criar;
export const atualizarFinalidadeEstoque = apiFinalidadesEstoque.atualizar;
export const excluirFinalidadeEstoque = apiFinalidadesEstoque.excluir;

const apiUnidadesEstoque = criarApiCadastroSimples("unidades-estoque", "Unidade de estoque");
export const fetchUnidadesEstoqueCadastro = apiUnidadesEstoque.fetch;
export const criarUnidadeEstoque = apiUnidadesEstoque.criar;
export const atualizarUnidadeEstoque = apiUnidadesEstoque.atualizar;
export const excluirUnidadeEstoque = apiUnidadesEstoque.excluir;

const apiUnidadesEmbalagemEstoque = criarApiCadastroSimples("unidades-embalagem-estoque", "Unidade de embalagem");
export const fetchUnidadesEmbalagemEstoqueCadastro = apiUnidadesEmbalagemEstoque.fetch;
export const criarUnidadeEmbalagemEstoque = apiUnidadesEmbalagemEstoque.criar;
export const atualizarUnidadeEmbalagemEstoque = apiUnidadesEmbalagemEstoque.atualizar;
export const excluirUnidadeEmbalagemEstoque = apiUnidadesEmbalagemEstoque.excluir;

const apiUnidadesMedidaEmbalagemEstoque = criarApiCadastroSimples("unidades-medida-embalagem-estoque", "Unidade de medida");
export const fetchUnidadesMedidaEmbalagemEstoqueCadastro = apiUnidadesMedidaEmbalagemEstoque.fetch;
export const criarUnidadeMedidaEmbalagemEstoque = apiUnidadesMedidaEmbalagemEstoque.criar;
export const atualizarUnidadeMedidaEmbalagemEstoque = apiUnidadesMedidaEmbalagemEstoque.atualizar;
export const excluirUnidadeMedidaEmbalagemEstoque = apiUnidadesMedidaEmbalagemEstoque.excluir;

// Laboratório / Categoria (medicamento) / Classificação do medicamento —
// catálogos globais cadastrados no Painel CowData, visíveis automaticamente
// aqui (ver rules/visibilidade.py::visivel(), global_compartilhado=True em
// _crud_nome_ativo). `criar` aqui sempre grava com o fazenda_id da PRÓPRIA
// fazenda (get_fazenda_id_escrita, nunca nulo) — pedido do usuário
// (04/09/2026): "Laboratório, com botão de + novo, que, se lançado na
// fazenda, não vai para o painel CowData". Sem `excluir`/`atualizar`
// expostos: o tenant só cria as PRÓPRIAS linhas novas, nunca edita/apaga a
// linha global (isso é papel exclusivo do Painel CowData).
const apiLaboratorios = criarApiCadastroSimples("laboratorios", "Laboratório");
export const fetchLaboratoriosCadastro = apiLaboratorios.fetch;
export const criarLaboratorioCadastro = apiLaboratorios.criar;

const apiCategoriasMedicamento = criarApiCadastroSimples("categorias-medicamento", "Categoria (medicamento)");
export const fetchCategoriasMedicamentoCadastro = apiCategoriasMedicamento.fetch;

const apiClassificacoesMedicamento = criarApiCadastroSimples("classificacoes-medicamento", "Classificação do medicamento");
export const fetchClassificacoesMedicamentoCadastro = apiClassificacoesMedicamento.fetch;

// ── Graus de sangue (Configurações > Cadastro) ──
export async function fetchGrausSangue() {
  const res = await authFetch(`${API}/cadastro/graus-sangue`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Graus de sangue error: ${res.status}`);
  return res.json();
}
export async function criarGrauSangue(dados: { nome: string; fracao_holandes?: number | null; nota?: string | null; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/graus-sangue`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar grau de sangue"); }
  return res.json();
}
export async function atualizarGrauSangue(id: number, dados: { nome: string; fracao_holandes?: number | null; nota?: string | null; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/graus-sangue/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar grau de sangue"); }
  return res.json();
}

// ── Motivos de venda de animal (Configurações > Parâmetros > Parâmetros gerais) ──
export async function fetchMotivosVenda() {
  const res = await authFetch(`${API}/cadastro/motivos-venda`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Motivos de venda error: ${res.status}`);
  return res.json();
}
export async function criarMotivoVenda(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/motivos-venda`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar motivo de venda"); }
  return res.json();
}
export async function atualizarMotivoVenda(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/motivos-venda/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar motivo de venda"); }
  return res.json();
}

// ── Cadastro de Serviços (lançamento financeiro > produto ou serviço) ──
export async function fetchServicosCadastro() {
  const res = await authFetch(`${API}/cadastro/servicos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Serviços error: ${res.status}`);
  return res.json();
}
export async function criarServicoCadastro(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/servicos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar serviço"); }
  return res.json();
}
export async function atualizarServicoCadastro(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/servicos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar serviço"); }
  return res.json();
}

// ── Tipos de serviço / Métodos reprodutivos (Configurações > Cadastro) ──
export async function fetchTiposServico() {
  const res = await authFetch(`${API}/cadastro/tipos-servico`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Tipos de serviço error: ${res.status}`);
  return res.json() as Promise<{ id: number; nome: string; ativo: boolean }[]>;
}
export async function criarTipoServico(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/tipos-servico`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar tipo de serviço"); }
  return res.json();
}
export async function atualizarTipoServico(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/tipos-servico/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar tipo de serviço"); }
  return res.json();
}
export type MetodoServico = { id: number; nome: string; tipo_servico_id: number; tipo_servico_nome?: string | null; codigo_interno: string | null; ativo: boolean };
export async function fetchMetodosServico() {
  const res = await authFetch(`${API}/cadastro/metodos-servico`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Métodos de serviço error: ${res.status}`);
  return res.json() as Promise<MetodoServico[]>;
}
export async function criarMetodoServico(dados: { nome: string; tipo_servico_id: number; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/metodos-servico`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar método"); }
  return res.json();
}
export async function atualizarMetodoServico(id: number, dados: { nome: string; tipo_servico_id: number; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/metodos-servico/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar método"); }
  return res.json();
}

// ── Baixa de animal (Rebanho > Baixar animal) ──
export async function fetchOpcoesBaixa() {
  const res = await authFetch(`${API}/baixas/motivos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Opções de baixa error: ${res.status}`);
  return res.json();
}
export async function fetchBaixas() {
  const res = await authFetch(`${API}/baixas/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Baixas error: ${res.status}`);
  return res.json();
}
export async function criarBaixaAnimal(dados: {
  animais: string[]; tipo_baixa: string; motivo: string; motivo_doenca?: string; motivo_outro?: string;
  valor?: number; cliente?: string; tipo_valor?: string; venda_recria?: boolean; data_baixa: string; observacao?: string; responsavel?: string;
  pagar_comissao?: boolean; corretor_nome?: string; valor_comissao?: number; forma_comissao?: string;
}) {
  const res = await authFetch(`${API}/baixas/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar baixa"); }
  return res.json();
}

// `marcado_em`: QUANDO SE DECIDIU (ausente = hoje). É a data que o motor
// reprodutivo lê para reconstruir o passado — por isso é editável, para quem
// lança com atraso gravar o dia real da decisão.
// `previsto_em`: QUANDO SE PRETENDE tirar do rebanho (ausente = sem previsão,
// que é um estado legítimo). Só informativa: não move taxa nenhuma.
export async function marcarADescartar(dados: {
  animais: string[]; descartar?: boolean; observacao?: string;
  marcado_em?: string | null; previsto_em?: string | null;
}) {
  const res = await authFetch(`${API}/baixas/a-descartar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao marcar A descartar"); }
  return res.json();
}

// ── Compra / Venda de animal (Lançamentos > Compra/Venda) ──
type ParcelaPayload = { data_vencimento: string; valor: number };
// Campos ricos comuns ao lançamento de compra e de venda de animal — espelha
// CompraIn/VendaIn do backend (conta gerencial restrita, documento, datas,
// parcelamento, pagamento, GTA, ICMS e comissão de corretagem opcional).
type CompraVendaCamposComuns = {
  codigo_conta_gerencial: string;
  descricao?: string; centro_custo?: string; tipo_documento?: string; numero_documento?: string;
  data_emissao?: string; data_vencimento?: string; data_pedido?: string; entregue?: boolean;
  desconto?: number; acrescimo?: number; parcelas?: ParcelaPayload[];
  data_pagamento?: string; valor_pago?: number; conta_bancaria?: string; numero_documento_pagamento?: string;
  gta?: string; icms_incide?: boolean; icms_tipo?: string; icms_valor?: number;
  pagar_comissao?: boolean; corretor_nome?: string; valor_comissao?: number; forma_comissao?: string;
  data_vencimento_comissao?: string; parcelas_comissao?: ParcelaPayload[];
};

export async function fetchComprasAnimais() {
  const res = await authFetch(`${API}/compras-animais/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Compras de animais error: ${res.status}`);
  return res.json();
}
export async function criarCompraAnimal(dados: CompraVendaCamposComuns & {
  animais: string[]; vendedor: string; valor: number; tipo_valor: string; data_compra: string;
  observacao?: string; responsavel?: string; data_prevista_entrada?: string;
}) {
  const res = await authFetch(`${API}/compras-animais/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar compra"); }
  return res.json();
}

export async function fetchVendasAnimais() {
  const res = await authFetch(`${API}/vendas-animais/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Vendas de animais error: ${res.status}`);
  return res.json();
}
export async function criarVendaAnimal(dados: CompraVendaCamposComuns & {
  animais: string[]; comprador: string; valor: number; tipo_valor: string; data_venda: string;
  observacao?: string; responsavel?: string; categorias?: string[]; motivo_venda?: string; data_prevista_saida?: string;
}) {
  const res = await authFetch(`${API}/vendas-animais/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar venda"); }
  return res.json();
}

export type LinhaRelatorioCompraVendaAnimal = {
  tipo: "compra" | "venda";
  numero_animal: string;
  contraparte: string;
  data: string;
  valor: number;
  tipo_valor: string;
  gta: string | null;
  icms_incide: boolean | null;
  icms_tipo: string | null;
  icms_valor: number | null;
  numero_lancamento: string | null;
  numero_documento: string | null;
  centro_custo: string | null;
  codigo_conta: string | null;
  categorias: string | null;
  motivo_venda: string | null;
  usuario_nome?: string | null;
};
export async function fetchRelatorioCompraVendaAnimais(filtros: {
  numero?: string; dataDe?: string; dataAte?: string; numeroDocumento?: string; gta?: string;
}) {
  const params = new URLSearchParams();
  if (filtros.numero) params.set("numero", filtros.numero);
  if (filtros.dataDe) params.set("data_de", filtros.dataDe);
  if (filtros.dataAte) params.set("data_ate", filtros.dataAte);
  if (filtros.numeroDocumento) params.set("numero_documento", filtros.numeroDocumento);
  if (filtros.gta) params.set("gta", filtros.gta);
  const res = await authFetch(`${API}/relatorio-compra-venda-animais/?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório de compra/venda de animais error: ${res.status}`);
  return res.json() as Promise<LinhaRelatorioCompraVendaAnimal[]>;
}

// Rastreabilidade sanitária (Sanidade > Rastreabilidade) — linha do tempo de
// GTA + aplicações + protocolos + exames + doenças, filtrável por animal,
// período ou nº de GTA. Ver GET /relatorio-rastreabilidade-sanitaria/.
export type LinhaRastreabilidadeSanitaria = {
  numero_animal: string;
  nome_animal: string | null;
  tipo_evento: "Compra" | "Venda" | "Aplicação sanitária" | "Protocolo sanitário" | "Exame" | "Doença (ocorrência clínica)" | "Baixa";
  data: string;
  gta: string | null;
  descricao: string | null;
  contraparte: string | null;
  produto: string | null;
  resultado: string | null;
  doenca: string | null;
  responsavel: string | null;
};
export async function fetchRastreabilidadeSanitaria(filtros: {
  numero?: string; gta?: string; dataDe?: string; dataAte?: string;
}) {
  const params = new URLSearchParams();
  if (filtros.numero) params.set("numero", filtros.numero);
  if (filtros.gta) params.set("gta", filtros.gta);
  if (filtros.dataDe) params.set("data_de", filtros.dataDe);
  if (filtros.dataAte) params.set("data_ate", filtros.dataAte);
  const res = await authFetch(`${API}/relatorio-rastreabilidade-sanitaria/?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório de rastreabilidade sanitária error: ${res.status}`);
  return res.json() as Promise<LinhaRastreabilidadeSanitaria[]>;
}

// ── Compra de sêmen (Lançamentos > Compra/Venda > Comprar sêmen) ──
export async function fetchComprasSemen() {
  const res = await authFetch(`${API}/compras-semen/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Compras de sêmen error: ${res.status}`);
  return res.json();
}
export type ItemCompraSemen = {
  origem: "estoque" | "naab"; estoque_semen_id?: number; naab?: string; touro_nome?: string; central?: string;
  tipo?: string; valor: number; tipo_valor: string; doses: number;
};
export async function criarCompraSemen(dados: CompraVendaCamposComuns & {
  itens: ItemCompraSemen[];
  vendedor: string; data_compra: string;
  observacao?: string; responsavel?: string; data_prevista_entrada?: string;
}) {
  const res = await authFetch(`${API}/compras-semen/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar compra de sêmen"); }
  return res.json();
}

// Relatório de compra de sêmen (Financeiro > Relatórios > Compra de sêmen) —
// espelho de fetchRelatorioCompraVendaAnimais, mesma ideia de filtros
// (período, documento) trocando animal/GTA por touro/vendedor.
export type LinhaRelatorioCompraSemen = {
  touro_nome: string;
  naab: string | null;
  origem: "estoque" | "naab";
  tipo: string;
  doses: number;
  valor_unitario: number;
  valor_total: number;
  vendedor: string;
  data_compra: string;
  responsavel: string | null;
  observacao: string | null;
  numero_lancamento: string | null;
  numero_documento: string | null;
  centro_custo: string | null;
  codigo_conta: string | null;
  usuario_nome?: string | null;
};
export async function fetchRelatorioCompraSemen(filtros: {
  touro?: string; naab?: string; vendedor?: string; dataDe?: string; dataAte?: string; numeroDocumento?: string;
}) {
  const params = new URLSearchParams();
  if (filtros.touro) params.set("touro", filtros.touro);
  if (filtros.naab) params.set("naab", filtros.naab);
  if (filtros.vendedor) params.set("vendedor", filtros.vendedor);
  if (filtros.dataDe) params.set("data_de", filtros.dataDe);
  if (filtros.dataAte) params.set("data_ate", filtros.dataAte);
  if (filtros.numeroDocumento) params.set("numero_documento", filtros.numeroDocumento);
  const res = await authFetch(`${API}/relatorio-compra-semen/?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório de compra de sêmen error: ${res.status}`);
  return res.json() as Promise<LinhaRelatorioCompraSemen[]>;
}

export async function fetchSanidade() {
  const res = await authFetch(`${API}/sanidade/aplicacoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Sanidade error: ${res.status}`);
  return res.json();
}

export async function registrarColostragem(dados: {
  numero_animal: string; tomou_colostro?: boolean; litros_colostro?: number; brix_colostro?: number;
  data_colostro?: string; hora_parto?: string; hora_colostro?: string; peso_nascer_kg?: number;
  brix_soro?: number; proteina_serica?: number; apenas_colostro_po?: boolean;
  data_teste_sangue?: string; observacao?: string;
}) {
  const res = await authFetch(`${API}/sanidade/colostragem`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar colostragem"); }
  return res.json();
}

export async function fetchRelatorioBezerras(filtros: { faixaEtaria?: string; numero?: string; lote?: string; numeros?: string[] }) {
  const params = new URLSearchParams();
  if (filtros.faixaEtaria) params.set("faixa_etaria", filtros.faixaEtaria);
  if (filtros.numero) params.set("numero", filtros.numero);
  if (filtros.lote) params.set("lote", filtros.lote);
  if (filtros.numeros) filtros.numeros.forEach((n) => params.append("numeros", n));
  const res = await authFetch(`${API}/sanidade/relatorio-bezerras?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório de bezerras error: ${res.status}`);
  return res.json();
}

export async function fetchUnidadesCompativeis(produto: string) {
  const res = await authFetch(`${API}/sanidade/unidades-compativeis?produto=${encodeURIComponent(produto)}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Unidades compatíveis error: ${res.status}`);
  return res.json();
}

export async function criarAplicacaoSanidade(dados: {
  data_aplicacao: string; animais: string[]; responsavel?: string; observacao?: string;
  itens: { produto: string; via?: string; quantidade: number; unidade: string; estoque_id?: number | null; lote_id?: number | null }[];
  aplicado?: boolean;
}) {
  const res = await authFetch(`${API}/sanidade/aplicacoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar aplicação de sanidade"); }
  return res.json();
}

export async function editarAplicacaoSanidade(id: number, dados: {
  data_aplicacao?: string; produto?: string; dose?: number | null; unidade?: string | null;
  via?: string | null; responsavel?: string | null; obs?: string | null;
}) {
  const res = await authFetch(`${API}/sanidade/aplicacoes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar aplicação"); }
  return res.json();
}

export async function excluirAplicacaoSanidade(id: number) {
  const res = await authFetch(`${API}/sanidade/aplicacoes/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir aplicação"); }
  return res.json();
}

export async function marcarCuraAplicacao(id: number, curada: boolean) {
  const res = await authFetch(`${API}/sanidade/aplicacoes/${id}/cura`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ curada }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao marcar cura"); }
  return res.json();
}

export async function confirmarLactacaoInducao(
  lancamentoId: number, numeroMatriz: string, entrouEmLactacao: boolean, dataInicio?: string, incluirBst?: boolean,
) {
  // Resposta ao card "Confirmar início de lactação" da Agenda (indução de
  // lactação concluída sem lactação aberta — ver agenda.py::
  // eventos_confirmar_lactacao_inducao). "Não" não grava nada no backend
  // além do ack; quem tira o card da Agenda é sempre o
  // marcarEventoRealizado chamado em seguida pelo handler, igual à cura.
  // `incluirBst`: o protocolo de indução já aplica BST no animal, então
  // marcar aqui já deixa ele em "Incluir no próximo BST" sem esperar o DEL
  // mínimo normal (ver Animal.bst_pendente_inducao_lactacao).
  const res = await authFetch(`${API}/producao/inducao-lactacao/${lancamentoId}/${encodeURIComponent(numeroMatriz)}/confirmar`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entrou_em_lactacao: entrouEmLactacao, data_inicio: dataInicio || undefined, incluir_bst: incluirBst || false }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao confirmar início de lactação"); }
  return res.json();
}

export async function marcarCuraProtocolo(lancamentoId: number, curada: boolean) {
  // Rota nova, com nome correto — /mastite/cura (retrocompatibilidade) segue
  // funcionando pois o app em produção ainda a chama, mas serve qualquer
  // protocolo sanitário, não só mastite.
  const res = await authFetch(`${API}/sanidade/protocolos/lancamentos/${lancamentoId}/cura`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lancamento_id: lancamentoId, curada }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao marcar cura"); }
  return res.json();
}

export type CasoTaxaCura = {
  origem: "aplicacao" | "protocolo"; id: number; numero: string; tratamento: string;
  data: string | null; curada: boolean | null; avaliado: boolean;
  lote: string | null; categoria: string; status_lactacao: string;
};
export async function fetchTaxaCura(): Promise<{
  casos: CasoTaxaCura[]; total: number; total_avaliados: number; curados: number; nao_curados: number;
  total_nao_avaliados: number; taxa_cura_pct: number | null; cobertura_avaliacao_pct: number | null;
}> {
  const res = await authFetch(`${API}/sanidade/taxa-cura`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Taxa de cura error: ${res.status}`);
  return res.json();
}

// ── Princípio ativo / Doença / Evento sanitário (Configurações > Cadastro) ──
function _crudNomeAtivo(caminho: string, rotulo: string) {
  return {
    listar: async () => {
      const res = await authFetch(`${API}/cadastro/${caminho}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`${rotulo} error: ${res.status}`);
      return res.json();
    },
    criar: async (dados: { nome: string; ativo?: boolean }) => {
      const res = await authFetch(`${API}/cadastro/${caminho}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Erro ao criar ${rotulo.toLowerCase()}`); }
      return res.json();
    },
    atualizar: async (id: number, dados: { nome: string; ativo: boolean }) => {
      const res = await authFetch(`${API}/cadastro/${caminho}/${id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Erro ao atualizar ${rotulo.toLowerCase()}`); }
      return res.json();
    },
  };
}
const _principiosAtivos = _crudNomeAtivo("principios-ativos", "Princípio ativo");
export const fetchPrincipiosAtivos = _principiosAtivos.listar;
export const criarPrincipioAtivo = _principiosAtivos.criar;
export const atualizarPrincipioAtivo = _principiosAtivos.atualizar;
// Escrita no catálogo GLOBAL de princípios ativos: a rota mudou de
// /cadastro/... para /painel-cowdata/farmacia/... (achado 35 da auditoria).
// Lá ela não tinha gate de papel nenhum e qualquer usuário de qualquer
// fazenda com o módulo sanitário reescrevia o catálogo que todas as
// fazendas-cliente enxergam. O botão que chama isto só é renderizado no
// Painel CowData (Farmacia.tsx, ramo `!somenteLeitura`), então a tela do
// tenant não perdeu nada.
export async function restaurarCatalogoPrincipios(): Promise<{ criados: number; total: number }> {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/principios/restaurar-catalogo`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao restaurar catálogo"); }
  return res.json();
}

const _doencas = _crudNomeAtivo("doencas", "Doença");
export const fetchDoencas = _doencas.listar;
export const criarDoenca = _doencas.criar;
export const atualizarDoenca = _doencas.atualizar;

// Evento sanitário — cadastro rico (nome + agendamento por época/evento +
// medicamento padrão). Alimenta o calendário sanitário e a Agenda.
export type EventoSanitarioPayload = {
  nome: string; ativo?: boolean;
  tipo_agendamento?: "nenhum" | "epoca" | "evento";
  categoria_alvo?: string | null; sexo_alvo?: "F" | "M" | null; doenca_id?: number | null; categoria_preventiva?: string | null;
  data_primeiro?: string | null; frequencia_valor?: number | null; frequencia_unidade?: string | null;
  gatilho?: string | null; gatilho_lote?: string | null; gatilho_idade_meses?: number | null; offset_dias?: number | null;
  produto_padrao?: string | null; dose_padrao?: number | null; unidade_padrao?: string | null; via_padrao?: string | null;
  agenda_dias_antes?: number | null;
  // Exclusão mútua — ex.: não agendar se o animal já recebeu o evento apontado
  // aqui (alternativas de vacina/estirpe para a mesma doença).
  condicao_evento_id?: number | null;
  // Só para exame: qual ExameDefinicao decide o tipo de resultado
  // (diagnóstico/numérico) mostrado no lançamento de Sanitário > Preventivo.
  exame_definicao_id?: number | null;
  // Nome de um serviço cadastrado (Configurações > Cadastro > Serviços) —
  // liga este evento ao botão "Lançar financeiro" no calendário sanitário.
  servico_financeiro?: string | null;
  // Janela de aplicação — após o gatilho, de/até quando o animal ainda está
  // dentro da janela. Cada limite tem sua própria unidade (dias ou meses).
  janela_de_valor?: number | null; janela_de_unidade?: "dias" | "meses" | null;
  janela_ate_valor?: number | null; janela_ate_unidade?: "dias" | "meses" | null;
  // O que acontece quando a janela se encerra sem aplicação: "sair" | "manter" | "notificar".
  acao_fora_janela?: string | null;
  // Teto etário (opcional) — além dessa idade, "manter" nunca se aplica.
  teto_etario_valor?: number | null; teto_etario_unidade?: "dias" | "meses" | null;
  // Veterinário padrão sugerido no agendamento (editável na hora).
  veterinario_padrao_pessoa_id?: number | null;
  veterinario_padrao_nome?: string | null;
};
export async function fetchEventosSanitarios() {
  const res = await authFetch(`${API}/cadastro/eventos-sanitarios`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Evento sanitário error: ${res.status}`);
  return res.json();
}
export async function criarEventoSanitario(dados: EventoSanitarioPayload) {
  const res = await authFetch(`${API}/cadastro/eventos-sanitarios`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar evento sanitário"); }
  return res.json();
}
export async function atualizarEventoSanitario(id: number, dados: EventoSanitarioPayload) {
  const res = await authFetch(`${API}/cadastro/eventos-sanitarios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar evento sanitário"); }
  return res.json();
}

// Exame (Configurações > Cadastro > Sanitário > Exames) — nome + tipo de
// resultado (diagnóstico ou numérico), vinculado ao princípio ativo. Decide
// o que aparece no lançamento de Sanitário > Preventivo para um evento do
// tipo exame — nunca gera aplicação de medicamento nem baixa de estoque.
export type ExameDefinicaoPayload = {
  nome: string; ativo?: boolean;
  principio_ativo_id?: number | null;
  tipo_resultado?: "diagnostico" | "numerico";
  faixa_min?: number | null; faixa_max?: number | null;
  acao_abaixo?: string | null; acao_dentro?: string | null; acao_acima?: string | null;
  observacao?: string | null;
};
export async function fetchExames() {
  const res = await authFetch(`${API}/cadastro/exames`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Exames error: ${res.status}`);
  return res.json();
}
export async function criarExame(dados: ExameDefinicaoPayload) {
  const res = await authFetch(`${API}/cadastro/exames`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar exame"); }
  return res.json();
}
export async function atualizarExame(id: number, dados: ExameDefinicaoPayload) {
  const res = await authFetch(`${API}/cadastro/exames/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar exame"); }
  return res.json();
}
export async function excluirExame(id: number) {
  const res = await authFetch(`${API}/cadastro/exames/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir exame"); }
  return res.json();
}

// Template de Checklist por Tipo (redesenho do evento sanitário, seção
// 3.7.3) — só leitura por aqui: ponto de partida do passo 4 do wizard novo
// de Cadastro (seção 3.7.0), Central de Protocolos > Cadastro > Sanitário >
// Preventivo.
export type ChecklistTemplateItemDTO = { chave: string; nome: string; ordem: number };
export async function fetchChecklistTemplate(tipo: "vacina" | "exame"): Promise<ChecklistTemplateItemDTO[]> {
  const res = await authFetch(`${API}/cadastro/checklist-template?tipo=${tipo}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Template de checklist error: ${res.status}`);
  return res.json();
}

// Resultados de exames (relatório) — GET /sanidade/exames/resultados.
export type ExameResultado = {
  id: number; numero_matriz: string; evento_sanitario_id: number; evento_sanitario_nome: string | null;
  exame_definicao_id: number | null; data_exame: string;
  resultado: "positivo" | "negativo" | "indefinido" | null;
  valor_numerico: number | null; banda: "abaixo" | "dentro" | "acima" | null;
  veterinario: string | null; observacao: string | null;
};
export async function fetchResultadosExame(filtros?: { eventoSanitarioId?: number; resultado?: string; dataDe?: string; dataAte?: string }) {
  const qs = new URLSearchParams();
  if (filtros?.eventoSanitarioId) qs.set("evento_sanitario_id", String(filtros.eventoSanitarioId));
  if (filtros?.resultado) qs.set("resultado", filtros.resultado);
  if (filtros?.dataDe) qs.set("data_de", filtros.dataDe);
  if (filtros?.dataAte) qs.set("data_ate", filtros.dataAte);
  const res = await authFetch(`${API}/sanidade/exames/resultados${qs.toString() ? `?${qs}` : ""}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Resultados de exame error: ${res.status}`);
  return res.json() as Promise<ExameResultado[]>;
}
export async function atualizarResultadoExame(id: number, dados: {
  data_exame?: string; resultado?: "positivo" | "negativo" | "indefinido" | null;
  valor_numerico?: number | null; veterinario?: string | null; observacao?: string | null;
}) {
  const res = await authFetch(`${API}/sanidade/exames/resultados/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar resultado do exame"); }
  return res.json() as Promise<ExameResultado>;
}

// Classificações de medicamento (para cadastrar/protocolar por classificação).
export const CLASSIFICACOES_MEDICAMENTO = ["Antimicrobiano", "Anti-inflamatório", "Antibiótico", "Antiparasitário", "Vacina", "Hormônio", "Outro"];

// Finalidade de um item de ESTOQUE (Estoque.finalidade) — decide se ele
// aparece nos seletores de aplicação de medicamento/hormônio. Só "Medicamento"
// entra nesses seletores; os demais existem para EXCLUIR ração/material/
// equipamento deles. Sêmen não usa este campo (tabela própria).
export const FINALIDADES_ESTOQUE = ["Medicamento", "Ração/Alimento", "Material/Insumo", "Equipamento", "Outro"];

// Categoria do item de estoque — mesma lista de fazenda.rules.categorias.CATEGORIAS_FORNECEDOR
// no backend (o produto e o fornecedor que o vende compartilham a mesma categoria).
export const CATEGORIAS_ESTOQUE = [
  "Ração e insumos alimentares",
  "Sêmen e genética",
  "Medicamentos e produtos veterinários",
  "Equipamentos e manutenção",
  "Combustível e transporte",
  "Serviços veterinários/técnicos",
  "Energia e utilidades",
  "Embalagens e materiais",
  "Outros",
];

// Medicamentos (itens de estoque) que cumprem um critério — usado ao lançar um
// protocolo cadastrado por princípio ativo ou classificação. Sem nenhum
// critério, vira o catálogo geral de medicamento/hormônio/vacina. Por padrão
// só traz itens com saldo em estoque — "incluir_sem_estoque" resolve o
// problema na hora (mesmo padrão do "incluir touros sem estoque" da Inseminação).
export async function fetchMedicamentos(filtro: { principio_ativo?: string; classificacao?: string; doenca?: string; finalidade?: string; incluir_sem_estoque?: boolean }) {
  const params = new URLSearchParams();
  if (filtro.principio_ativo) params.set("principio_ativo", filtro.principio_ativo);
  if (filtro.classificacao) params.set("classificacao", filtro.classificacao);
  if (filtro.doenca) params.set("doenca", filtro.doenca);
  if (filtro.finalidade) params.set("finalidade", filtro.finalidade);
  if (filtro.incluir_sem_estoque) params.set("incluir_sem_estoque", "true");
  const res = await authFetch(`${API}/estoque/medicamentos?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Medicamentos error: ${res.status}`);
  return res.json();
}

// ── Agendamento de pesagem do rebanho (Configurações) ──
export type AgendamentoPesagem = {
  id: number; nome: string; ativo: boolean; idade_min_dias: number | null; idade_max_dias: number | null;
  categoria_alvo: string | null; frequencia_valor: number; frequencia_unidade: string; dia_semana: number; data_referencia: string;
};
export async function fetchAgendamentosPesagem() {
  const res = await authFetch(`${API}/cadastro/agendamentos-pesagem`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Agendamentos de pesagem error: ${res.status}`);
  return res.json() as Promise<AgendamentoPesagem[]>;
}
export async function criarAgendamentoPesagem(dados: Record<string, any>) {
  const res = await authFetch(`${API}/cadastro/agendamentos-pesagem`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar agendamento"); }
  return res.json();
}
export async function atualizarAgendamentoPesagem(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/cadastro/agendamentos-pesagem/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar agendamento"); }
  return res.json();
}
export async function excluirAgendamentoPesagem(id: number) {
  const res = await authFetch(`${API}/cadastro/agendamentos-pesagem/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir"); }
  return res.json();
}

// ── Protocolo sanitário (cadastro + lançamento) ──
// criterio_tipo: "medicamento" (produto = item de estoque), "principio_ativo"
// ou "classificacao" (produto = o valor do critério; medicamento escolhido no lançamento).
export type ProtocoloEtapa = {
  dia: number; criterio_tipo?: string; produto: string; dosagem: number; unidade: string;
  via?: string | null; observacao?: string | null;
  // Onda "Protocolo à Mostra" — "fixa" (padrão, é o legado inteiro): `dosagem`
  // é a dose pronta. "por_peso": `dosagem` é a dose A CADA `dose_referencia_kg`
  // de peso vivo do animal — ver rules.dose_protocolo no backend.
  modo_dose?: "fixa" | "por_peso"; dose_referencia_kg?: number | null;
};

/** "2 mL" (fixa) ou "2 mL a cada 15 kg PV" (por peso) — a mesma fórmula
 * sempre exibida como texto, nunca escondida atrás de um número calculado
 * sozinho. Usada em toda tela que lista etapas de protocolo sanitário
 * (cadastro, lançamento, Central de Protocolos, Agenda). */
export function formatarDoseEtapa(e: Pick<ProtocoloEtapa, "dosagem" | "unidade" | "modo_dose" | "dose_referencia_kg">): string {
  if (e.modo_dose === "por_peso" && e.dose_referencia_kg) {
    return `${e.dosagem}${e.unidade ? ` ${e.unidade}` : ""} a cada ${e.dose_referencia_kg}kg PV`;
  }
  return `${e.dosagem}${e.unidade ? ` ${e.unidade}` : ""}`;
}

/** Dose calculada para um animal de `pesoKg`, quando a etapa é "por_peso".
 * null quando a etapa é dose fixa (nada a calcular) ou falta o peso. */
export function calcularDoseEtapa(e: Pick<ProtocoloEtapa, "dosagem" | "modo_dose" | "dose_referencia_kg">, pesoKg: number | null | undefined): number | null {
  if (e.modo_dose !== "por_peso" || !e.dose_referencia_kg || !pesoKg) return null;
  return Math.round((e.dosagem * (pesoKg / e.dose_referencia_kg)) * 10) / 10;
}
export async function fetchProtocolosSanitarios() {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos sanitários error: ${res.status}`);
  return res.json();
}
export async function importarProtocoloSanitarioExcel(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao importar planilha"); }
  return res.json();
}
export async function criarProtocoloSanitario(dados: { nome: string; doenca_id?: number | null; eh_mastite?: boolean; dia_inicial?: number; finalidade?: string | null; ativo?: boolean; etapas: ProtocoloEtapa[] }) {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar protocolo sanitário"); }
  return res.json();
}
export async function atualizarProtocoloSanitario(id: number, dados: { nome: string; doenca_id?: number | null; eh_mastite?: boolean; dia_inicial?: number; finalidade?: string | null; ativo?: boolean; etapas: ProtocoloEtapa[] }) {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar protocolo sanitário"); }
  return res.json();
}
export async function excluirProtocoloSanitario(id: number): Promise<void> {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir protocolo sanitário"); }
}
export async function fetchLancamentosProtocolo() {
  const res = await authFetch(`${API}/sanidade/protocolos/lancamentos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lançamentos de protocolo error: ${res.status}`);
  return res.json();
}
export async function lancarProtocoloSanitario(dados: {
  protocolo_id: number; numeros_matriz: string[]; data_inicio: string; responsavel?: string; observacao?: string;
  classificacao_mastite?: string; grau_mastite?: number; agente?: string; resultado_cmt?: string; tetos_afetados?: string[];
  escolhas_medicamento?: Record<string, string>;
}) {
  const res = await authFetch(`${API}/sanidade/protocolos/lancamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar protocolo sanitário"); }
  return res.json();
}

export async function fetchMastiteOpcoes(): Promise<{ agentes: string[]; graus: number[]; tetos: string[]; resultados_cmt: string[] }> {
  const res = await authFetch(`${API}/sanidade/mastite/opcoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Mastite opções error: ${res.status}`);
  return res.json();
}
export async function fetchMastiteContexto(numero: string): Promise<{ del_atual: number | null; ccs_ultima: number | null; data_ccs: string | null; cmt_ultimo: string | null }> {
  const res = await authFetch(`${API}/sanidade/mastite/contexto?numero=${encodeURIComponent(numero)}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Mastite contexto error: ${res.status}`);
  return res.json();
}

// ── Calendário sanitário (Sanidade) ──
export async function fetchCalendarioSanitario(filtros?: { dataInicio?: string; dataFim?: string; eventoSanitarioId?: number }) {
  const params = new URLSearchParams();
  if (filtros?.dataInicio) params.set("data_inicio", filtros.dataInicio);
  if (filtros?.dataFim) params.set("data_fim", filtros.dataFim);
  if (filtros?.eventoSanitarioId) params.set("evento_sanitario_id", String(filtros.eventoSanitarioId));
  const res = await authFetch(`${API}/sanidade/calendario?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Calendário sanitário error: ${res.status}`);
  return res.json();
}

type CalendarioSanitarioPayload = {
  evento_sanitario_id: number; categoria_alvo?: string; doenca_id?: number; produto?: string;
  principio_ativo_id?: number; dosagem?: string; unidade?: string; responsavel?: string; veterinario?: string; frequencia_valor: number; frequencia_unidade: string;
  data_evento: string; observacao?: string; ativo?: boolean; realizado?: boolean;
  // Liga esta regra ao workflow de Cronograma sanitário (ver
  // fazenda/rules/cronograma_sanitario.py): animal que bate o critério entra
  // numa lista de espera em vez de virar pendência de aplicar na hora.
  usa_cronograma?: boolean;
  // Passo 4 do wizard novo (redesenho, seção 3.7.0) — checklist congelado
  // para esta regra. Omitir preserva qualquer customização já existente;
  // mandar (mesmo lista vazia) substitui por completo.
  checklist_itens?: ChecklistTemplateItemDTO[];
};
export async function criarCalendarioSanitario(dados: CalendarioSanitarioPayload) {
  const res = await authFetch(`${API}/sanidade/calendario`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar regra do calendário sanitário"); }
  return res.json();
}
export async function atualizarCalendarioSanitario(id: number, dados: CalendarioSanitarioPayload) {
  const res = await authFetch(`${API}/sanidade/calendario/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar regra do calendário sanitário"); }
  return res.json();
}
export async function excluirCalendarioSanitario(id: number) {
  const res = await authFetch(`${API}/sanidade/calendario/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir regra do calendário sanitário"); }
  return res.json();
}

// Cronogramas sanitários (regras usa_cronograma=True) — Sanidade > Preventiva >
// Cronogramas. Lista as ocorrências (abertas ou concluídas) com contagem de
// animais por status (sugerido/incluído/excluído/aplicado).
export async function fetchCronogramasSanitarios(filtros?: { calendarioId?: number; status?: string }) {
  const params = new URLSearchParams();
  if (filtros?.calendarioId) params.set("calendario_id", String(filtros.calendarioId));
  if (filtros?.status) params.set("status", filtros.status);
  const res = await authFetch(`${API}/sanidade/cronogramas?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Cronogramas sanitários error: ${res.status}`);
  return res.json();
}
// Cria (ou devolve, se já existir) o cronograma em aberto de uma regra — card
// Cronogramas > "Novo cronograma". Sempre exige uma regra existente marcada
// usa_cronograma=True; nunca cria um cronograma solto.
export async function criarCronogramaSanitario(calendarioSanitarioId: number) {
  const res = await authFetch(`${API}/sanidade/cronogramas`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ calendario_sanitario_id: calendarioSanitarioId }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar cronograma"); }
  return res.json();
}

// ── Ocorrência (redesenho do evento sanitário, telas 1-2) ──────────────────
// GET /sanidade/ocorrencias e /ocorrencias/{id} — ver
// fazenda/api/routers/sanidade.py e docs/redesenho-evento-sanitario.md.
export type EstadoOcorrencia = "provavel" | "em_edicao" | "confirmado" | "realizado";
export type LinhaOcorrencia = {
  calendario_sanitario_id: number; cronograma_id: number | null;
  evento_sanitario_nome: string; tipo: "vacina" | "exame" | "tratamento";
  categoria_alvo: string | null; data_prevista: string; estado: EstadoOcorrencia;
  animais_incluidos: number; animais_sugeridos: number; veterinario_nome: string | null;
  atraso_dias: number; alerta_clinico: boolean;
};
export type IndicadoresOcorrencias = {
  vencidas: number; provaveis_30d: number; confirmadas_aguardando: number; alerta_clinico_ativo: number;
};
export async function fetchOcorrencias(): Promise<{ indicadores: IndicadoresOcorrencias; linhas: LinhaOcorrencia[] }> {
  const res = await authFetch(`${API}/sanidade/ocorrencias`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Ocorrências error: ${res.status}`);
  return res.json();
}

export type ChecklistItemOcorrencia = {
  id: number; chave: "estoque" | "vet" | "horario" | "lotes" | "financeiro" | "custom"; nome: string;
  status: "pendente" | "cumprido" | "pulado"; resposta: string | null; observacao: string | null;
  respondido_em: string | null;
};
export type AnimalOcorrencia = {
  id: number; numero_matriz: string; status: "sugerido" | "incluido" | "excluido" | "aplicado";
  data_sugestao: string; data_decisao: string | null;
};
export type DetalheOcorrencia = {
  cronograma_id: number; calendario_sanitario_id: number | null; evento_sanitario_nome: string;
  tipo: "vacina" | "exame" | "tratamento"; categoria_alvo: string | null; data_prevista: string;
  estado: EstadoOcorrencia; checklist_desconsiderado: boolean; checklist_desconsiderado_motivo: string | null;
  veterinario_nome: string | null; alerta_clinico: boolean;
  // Saldo do produto vinculado à regra — aviso honesto (não é o cálculo
  // preciso "dá pra aplicar em todos os incluídos", só o saldo atual),
  // pedido pelo usuário em 12/09/2026 para o item "estoque" do checklist.
  estoque: { produto: string; encontrado: boolean; saldo: number | null; unidade: string | null } | null;
  animais: AnimalOcorrencia[]; checklist: ChecklistItemOcorrencia[];
};
export async function fetchDetalheOcorrencia(cronogramaId: number): Promise<DetalheOcorrencia> {
  const res = await authFetch(`${API}/sanidade/ocorrencias/${cronogramaId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Detalhe da ocorrência error: ${res.status}`);
  return res.json();
}

export type JanelaCalendarioEvento = {
  calendario_sanitario_id: number; evento_sanitario_id: number; evento_sanitario_nome: string;
  categoria_alvo: string | null; categoria_preventiva: string | null; servico_financeiro: string | null;
  usa_cronograma: boolean; data: string; animais: number | null; estimativa: boolean;
  estimativa_base: "ultima_aplicacao" | null;
  cronograma: { id: number; status: string; modo_execucao: string | null; veterinario_nome: string | null; animais_contagem: { sugerido: number; incluido: number; excluido: number; aplicado: number } } | null;
};
export type JanelaCalendario = {
  data_inicio: string; data_fim: string; animais_total: number; tem_estimativa: boolean;
  sugerir_veterinario: boolean; eventos: JanelaCalendarioEvento[];
};
// Card CALENDÁRIO — projeção agrupada das próximas ocorrências (vacina/exame),
// com estimativa de animais e sinalização de "vale chamar o veterinário".
export async function fetchCalendarioVisao(filtros?: { dataInicio?: string; dataFim?: string }) {
  const params = new URLSearchParams();
  if (filtros?.dataInicio) params.set("data_inicio", filtros.dataInicio);
  if (filtros?.dataFim) params.set("data_fim", filtros.dataFim);
  const res = await authFetch(`${API}/sanidade/calendario/visao?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Calendário sanitário (visão) error: ${res.status}`);
  return res.json() as Promise<{ janelas: JanelaCalendario[]; min_animais_agrupamento: number; janela_agrupamento_dias: number }>;
}

// ── Relatório de eventos de vida (mudança de categoria) ──
export async function fetchEventosVidaVocabulario(): Promise<{ gatilho: string; rotulo: string }[]> {
  const res = await authFetch(`${API}/sanidade/calendario/eventos-vida`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Eventos de vida error: ${res.status}`);
  return res.json();
}
export async function fetchRelatorioEventosVida(filtros: {
  gatilho?: string; eventoSanitarioId?: number; gatilhoLote?: string; gatilhoIdadeMeses?: number;
  dataInicio?: string; dataFim?: string;
}) {
  const params = new URLSearchParams();
  if (filtros.gatilho) params.set("gatilho", filtros.gatilho);
  if (filtros.eventoSanitarioId) params.set("evento_sanitario_id", String(filtros.eventoSanitarioId));
  if (filtros.gatilhoLote) params.set("gatilho_lote", filtros.gatilhoLote);
  if (filtros.gatilhoIdadeMeses) params.set("gatilho_idade_meses", String(filtros.gatilhoIdadeMeses));
  if (filtros.dataInicio) params.set("data_inicio", filtros.dataInicio);
  if (filtros.dataFim) params.set("data_fim", filtros.dataFim);
  const res = await authFetch(`${API}/sanidade/calendario/relatorio-eventos-vida?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Relatório de eventos de vida error: ${res.status}`); }
  return res.json();
}

export type CadastrarPreventivoPayload = {
  evento_sanitario_id: number; categoria_alvo?: string | null; data_evento: string;
  frequencia_valor: number; frequencia_unidade: string; animais: string[]; aplicar?: boolean;
  // "Já foi aplicado?" — só importa quando aplicar=true; default true (comportamento antigo).
  aplicado?: boolean;
  veterinario?: string | null; responsavel?: string | null; observacao?: string | null;
  // Overrides opcionais do produto/dose/via/princípio ativo padrão do evento —
  // usados na confirmação inline da Agenda ("dar baixa" sem abrir Lançamentos).
  produto?: string | null; dose?: number | null; unidade?: string | null; via?: string | null;
  principio_ativo_id?: number | null;
  // Diagnóstico do exame (só evento categoria_preventiva == "exame") — nunca
  // gera aplicação de medicamento nem baixa de estoque, só ExameResultado
  // (relatório) + ação automática (positivo → A descartar).
  resultado_exame?: "positivo" | "negativo" | "indefinido" | null;
  resultado_numerico?: number | null;
  // Baixa de uma ocorrência de uma regra do calendário sanitário já existente
  // — quando informado, não cria regra nova nem redefine frequência, só marca
  // a ocorrência como realizada (resolve a pendência da Agenda).
  calendario_id?: number | null;
};
export async function cadastrarPreventivo(dados: CadastrarPreventivoPayload) {
  const res = await authFetch(`${API}/sanidade/calendario/cadastrar-preventivo`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cadastrar preventivo"); }
  return res.json();
}

export async function fetchEstoque() {
  const res = await authFetch(`${API}/estoque/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Estoque error: ${res.status}`);
  return res.json();
}

export async function movimentarEstoque(dados: {
  nome: string; movimento: string; quantidade: number; unidade?: string; data_movimento: string; observacao?: string;
  pedido_id?: number | null; pedido_item_id?: number | null;
}) {
  const res = await authFetch(`${API}/estoque/movimentar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar movimento de estoque"); }
  return res.json();
}

export type MovimentoEstoqueRow = {
  id: number; nome_item: string; movimento: string; quantidade: number; unidade?: string | null;
  data_movimento: string; observacao?: string | null; usuario_nome?: string | null;
  // Rótulo pronto (ex.: "100 ml/frasco") de qual embalagem este movimento
  // afetou, quando o lote tinha um tamanho cadastrado — null nos demais casos.
  embalagem?: string | null;
};
export async function fetchMovimentosEstoque(): Promise<{ movimentos: MovimentoEstoqueRow[]; total: number }> {
  const res = await authFetch(`${API}/estoque/movimentos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Movimentos de estoque error: ${res.status}`);
  return res.json();
}

// G1 — só movimento manual (`origem_tipo` nulo) pode ser editado/excluído por
// aqui; movimento gerado por outro lançamento (Sanidade, Protocolo, Secagem…)
// dá 400 e aponta pra desfazer pelo lançamento de origem.
export type MovimentoEstoqueEditIn = {
  quantidade: number; unidade?: string | null; data_movimento: string; observacao?: string | null;
};
export async function atualizarMovimentoEstoque(id: number, dados: MovimentoEstoqueEditIn) {
  const res = await authFetch(`${API}/estoque/movimentos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar movimento de estoque"); }
  return res.json() as Promise<MovimentoEstoqueRow & { saldo_item: number }>;
}
// A exclusão do movimento manual roteia pelo motor genérico — ver
// confirmarExclusao("movimento_estoque", id) em "── Exclusões ──" abaixo.

export async function fetchAlimentacao() {
  const res = await authFetch(`${API}/alimentacao/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Alimentação error: ${res.status}`);
  return res.json();
}

export async function fetchNecessidadeMensal() {
  const res = await authFetch(`${API}/alimentacao/necessidade-mensal`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Necessidade mensal error: ${res.status}`);
  return res.json();
}

export async function fetchEstadoBaixaAlimentacao() {
  const res = await authFetch(`${API}/alimentacao/estado-baixa`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Estado da baixa error: ${res.status}`);
  return res.json();
}

// ── Categorias de alimento e cadastro de Alimento (Configurações > Cadastro
// > Alimentação > Categorias / Alimentos) ──
// `categoria_pai_id` é a auto-FK que dá o SEGUNDO nível (ex.: "Proteico" e
// "Energético" abaixo de "Concentrado"). São só dois níveis: uma categoria com
// pai não pode virar pai de outra — quem barra é o backend.
// `Alimento.categoria_alimento_id` continua sendo UMA só FK, e pode apontar
// tanto para uma raiz quanto para uma subcategoria. Quem aponta para uma
// subcategoria tem a categoria derivada do pai dela — é assim que a tela de
// Alimentos preenche as colunas Categoria e Subcategoria sem um segundo campo.
export type CategoriaAlimento = {
  id: number; nome: string; ativo: boolean; categoria_pai_id: number | null;
};
export async function fetchCategoriasAlimento(): Promise<CategoriaAlimento[]> {
  const res = await authFetch(`${API}/alimentacao/categorias`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Categorias de alimento error: ${res.status}`);
  return res.json();
}
export async function criarCategoriaAlimento(dados: { nome: string; ativo?: boolean; categoria_pai_id?: number | null }) {
  const res = await authFetch(`${API}/alimentacao/categorias`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar categoria"); }
  return res.json();
}
export async function atualizarCategoriaAlimento(id: number, dados: { nome: string; ativo?: boolean; categoria_pai_id?: number | null }) {
  const res = await authFetch(`${API}/alimentacao/categorias/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar categoria"); }
  return res.json();
}
export async function excluirCategoriaAlimento(id: number) {
  const res = await authFetch(`${API}/alimentacao/categorias/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir categoria"); }
  return res.json();
}

export type Alimento = {
  id: number; nome: string; categoria_alimento_id: number | null; observacao: string | null; ativo: boolean;
  estoque_vinculado: any[];
};
export async function fetchAlimentos(): Promise<Alimento[]> {
  const res = await authFetch(`${API}/alimentacao/alimentos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Alimentos error: ${res.status}`);
  return res.json();
}
export type AlimentoIn = {
  nome: string; categoria_alimento_id?: number | null; observacao?: string | null; ativo?: boolean; estoque_ids?: number[];
};
export async function criarAlimento(dados: AlimentoIn): Promise<Alimento> {
  const res = await authFetch(`${API}/alimentacao/alimentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar alimento"); }
  return res.json();
}
export async function atualizarAlimento(id: number, dados: AlimentoIn): Promise<Alimento> {
  const res = await authFetch(`${API}/alimentacao/alimentos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar alimento"); }
  return res.json();
}
export async function excluirAlimento(id: number) {
  const res = await authFetch(`${API}/alimentacao/alimentos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir alimento"); }
  return res.json();
}

// ── Fase P0-B: relatório de conferência (SOMENTE LEITURA) do refactor
// Alimento/Estoque — aba "Conferência" de Configurações > Cadastro >
// Alimentação. Ver backend/fazenda/api/routers/alimentacao.py::relatorio_migracao.
export type RelatorioMigracaoItem = {
  id: number; nome: string; quantidade: number | null; unidade: string | null; finalidade: string | null;
  fontes: { dieta: number; curva_abc: number; lancamento_item: number; sanidade: number };
  quantidade_movimentos: number; primeiro_movimento: string | null; ultimo_movimento: string | null;
  candidatos_mesclagem: { id: number; nome: string }[];
};
export type RelatorioMigracaoProdutoSemCategoria = {
  id: number; nome: string; quantidade: number | null; unidade: string | null; finalidade: string | null; motivo: string;
};
export type RelatorioMigracaoDesmembramento = {
  alimento_id: number; alimento_nome: string | null;
  produtos: { id: number; nome: string; quantidade: number | null; unidade: string | null }[];
  tem_alimento_nutricional: boolean;
  // Fase P1: qual dos `produtos` acima (se algum) já foi escolhido
  // deliberadamente como o item que recebe a baixa automática — null significa
  // que ninguém escolheu ainda, e o sistema segue na ordem arbitrária de hoje.
  estoque_preferido_id: number | null;
};
export type RelatorioMigracaoDivergenciaNome = {
  alimento_id: number; alimento_nome: string; estoque_id: number; estoque_nome: string;
  quantidade_laudos_pelo_nome_atual: number;
  // Fase P1: quantos desses laudos já estão ligados por id (imunes a um
  // futuro rename do Alimento) — informativo, não muda nenhuma resolução.
  quantidade_laudos_pelo_id: number;
};
export type RelatorioMigracaoIngredienteNaoResolvivel = {
  ingrediente: string; classificacao: "resolve_0" | "ambiguo"; motivo: string;
  candidatos: { id: number; nome: string }[];
};
export type RelatorioMigracaoItemRmca = { id: number; nome: string; conta_gerencial_despesa_padrao: string | null; finalidade: string | null };
export type RelatorioMigracao = {
  fantasmas_importacao: RelatorioMigracaoItem[];
  fantasmas_ponte: RelatorioMigracaoItem[];
  produtos_sem_categoria: RelatorioMigracaoProdutoSemCategoria[];
  desmembramentos: RelatorioMigracaoDesmembramento[];
  divergencia_nome: RelatorioMigracaoDivergenciaNome[];
  ingredientes_nao_resolviveis: RelatorioMigracaoIngredienteNaoResolvivel[];
  rmca: {
    so_pela_conta: RelatorioMigracaoItemRmca[]; so_pela_finalidade: RelatorioMigracaoItemRmca[]; por_ambas: RelatorioMigracaoItemRmca[];
  };
};
export async function fetchRelatorioMigracaoAlimentacao(): Promise<RelatorioMigracao> {
  const res = await authFetch(`${API}/alimentacao/migracao/relatorio`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório de conferência error: ${res.status}`);
  return res.json();
}

// Fase P1 — as duas únicas ações que a aba "Conferência" ganha (o resto da
// aba continua somente leitura): escolher qual item de Estoque recebe a
// baixa automática de um Alimento com 2+ candidatos, e ligar um item de
// Estoque direto a uma CategoriaAlimento, sem precisar de um Alimento no meio.
export async function atualizarEstoquePreferidoAlimento(alimentoId: number, estoqueId: number | null): Promise<Alimento> {
  const res = await authFetch(`${API}/alimentacao/alimentos/${alimentoId}/estoque-preferido`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ estoque_id: estoqueId }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao definir o item preferido"); }
  return res.json();
}
// Nome diferente de `atualizarCategoriaEstoque` (acima, Cadastro > Estoque >
// Categoria — texto livre, sem relação nenhuma) DE PROPÓSITO: esta aqui grava
// `Estoque.categoria_alimento_id`, o vínculo novo da Fase P1 com o cadastro de
// CategoriaAlimento (o mesmo de Configurações > Cadastro > Alimentação >
// Categorias) — duas colunas, dois conceitos, dois endpoints diferentes.
export async function atualizarCategoriaAlimentoEstoque(estoqueId: number, categoriaAlimentoId: number | null) {
  const res = await authFetch(`${API}/alimentacao/estoque/${estoqueId}/categoria`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ categoria_alimento_id: categoriaAlimentoId }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao definir a categoria do item de estoque"); }
  return res.json();
}

// ── Lançamento de dieta (Lançamentos > Alimentação) ──
export async function fetchAlimentosPadrao() {
  const res = await authFetch(`${API}/alimentacao/alimentos-padrao`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Alimentos padrão error: ${res.status}`);
  return res.json();
}
export async function fetchTabelaNutricional() {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Tabela nutricional error: ${res.status}`);
  return res.json() as Promise<{ alimentos: string[]; produto_ids: number[]; estoque_ids: (number | null)[]; linhas: string[][] }>;
}
export async function criarProdutoTabelaNutricional(dados: { nome?: string; estoque_id?: number }) {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/produtos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cadastrar produto"); }
  return res.json();
}
export type GerarComposicaoResposta = {
  criado: boolean; alimento_nutricional_id: number;
  convertidos: Record<string, number>; nao_convertidos: Record<string, string>;
};
export async function gerarComposicaoDeTabelaNutricional(produtoId: number): Promise<GerarComposicaoResposta> {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/produtos/${produtoId}/gerar-composicao`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao gerar composição"); }
  return res.json();
}
export async function renomearProdutoTabelaNutricional(id: number, nome: string) {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/produtos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao renomear produto"); }
  return res.json();
}
export async function excluirProdutoTabelaNutricional(id: number) {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/produtos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir produto"); }
  return res.json();
}
export async function salvarValoresTabelaNutricional(itens: { produto_id: number; nutriente: string; valor: string }[]) {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/valores`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ itens }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar tabela nutricional"); }
  return res.json();
}
export function baixarModeloTabelaNutricional() {
  return baixarArquivoAutenticado("/alimentacao/tabela-nutricional/modelo", "tabela_nutricional_modelo.xlsx");
}
export async function importarTabelaNutricional(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao importar planilha"); }
  return res.json();
}

export async function fetchDietas(filtros?: { lote?: number; ativo?: boolean }) {
  const params = new URLSearchParams();
  if (filtros?.lote != null) params.set("lote", String(filtros.lote));
  if (filtros?.ativo != null) params.set("ativo", String(filtros.ativo));
  const res = await authFetch(`${API}/alimentacao/dietas?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Dietas error: ${res.status}`);
  return res.json();
}

export async function fetchMateriaSeca(): Promise<{ id?: number; nome: string; ms_pct: number | null }[]> {
  const res = await authFetch(`${API}/alimentacao/materia-seca`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Matéria seca error: ${res.status}`);
  return res.json();
}
export async function salvarMateriaSeca(dados: { nome: string; ms_pct: number | null }) {
  const res = await authFetch(`${API}/alimentacao/materia-seca`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar matéria seca"); }
  return res.json();
}

export type AnaliseBromatologica = {
  id: number; data: string; alimento: string;
  ms_pct: number | null; pb_pct: number | null; fdn_pct: number | null; fda_pct: number | null;
  ndt_pct: number | null; ee_pct: number | null; cinzas_pct: number | null; ca_pct: number | null; p_pct: number | null;
  observacao: string | null; criado_em: string; usuario_nome: string | null;
};
export async function fetchAnaliseBromatologica(): Promise<{ registros: AnaliseBromatologica[]; total: number }> {
  const res = await authFetch(`${API}/alimentacao/analise-bromatologica`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Análise bromatológica error: ${res.status}`);
  return res.json();
}
export async function criarAnaliseBromatologica(dados: {
  data: string; alimento: string;
  ms_pct?: number | null; pb_pct?: number | null; fdn_pct?: number | null; fda_pct?: number | null;
  ndt_pct?: number | null; ee_pct?: number | null; cinzas_pct?: number | null; ca_pct?: number | null; p_pct?: number | null;
  observacao?: string | null;
}) {
  const res = await authFetch(`${API}/alimentacao/analise-bromatologica`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar análise bromatológica"); }
  return res.json();
}
export async function criarDieta(dados: {
  lote: number; responsavel?: string; data_abertura: string; data_prevista_encerramento?: string; observacao?: string;
  base_quantidade?: string; leite_bezerros_kg_dia?: number | null;
  itens: { alimento: string; quantidade: number; unidade: string; base?: string; ms_pct?: number | null; base_quantidade?: string | null }[]; encerrar_anterior?: boolean;
}) {
  const res = await authFetch(`${API}/alimentacao/dietas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar dieta"); }
  return res.json();
}
export type ContextoDieta = {
  lote: number; nome: string | null; qtd_animais: number; del_medio: number | null; media_cl: number | null; data_ult_cl: string | null;
  animais: { numero: string; del_dias: number | null; ult_cl_kg: number | null; data_ult_leite: string | null }[];
  ultima_dieta: {
    data_abertura: string; data_prevista_encerramento: string | null; responsavel: string | null;
    base_quantidade: string | null; leite_bezerros_kg_dia: number | null; leite_por_bezerro_kg_dia: number | null;
    // `total_dia` só é `null` no caso extremo de um item com override
    // "por cabeça" num lote sem nenhum animal ativo (não há efetivo para
    // multiplicar e chegar no total do lote) — ver `_totais_item` no backend.
    itens: { alimento: string; unidade: string; total_dia: number | null; por_cabeca: number | null }[];
  } | null;
};
export async function fetchContextoDieta(lote: number) {
  const res = await authFetch(`${API}/alimentacao/dietas/contexto/${lote}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Contexto dieta error: ${res.status}`);
  return res.json() as Promise<ContextoDieta>;
}
export type ApresentacaoDieta = {
  lote: number; nome: string | null; qtd_animais: number; data_abertura: string; data_prevista_encerramento: string | null;
  num_tratos: number; vagao_kg_dia: number; vagao_kg_trato: number;
  // `total_dia`/`total_trato` só ficam `null` no caso extremo de um item com
  // override "por cabeça" num lote sem nenhum animal ativo — ver
  // `_totais_item` no backend.
  itens: { alimento: string; unidade: string; total_dia: number | null; por_cabeca: number | null; total_trato: number | null }[];
};
export async function fetchApresentacaoDieta(id: number) {
  const res = await authFetch(`${API}/alimentacao/dietas/${id}/apresentacao`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Apresentação dieta error: ${res.status}`);
  return res.json() as Promise<ApresentacaoDieta>;
}

export async function encerrarDieta(id: number, dataEfetivoEncerramento: string) {
  const res = await authFetch(`${API}/alimentacao/dietas/${id}/encerrar`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data_efetivo_encerramento: dataEfetivoEncerramento }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao encerrar dieta"); }
  return res.json();
}

export async function registrarRealDieta(id: number, dados: { data: string; itens: { alimento: string; quantidade: number; unidade: string }[] }) {
  const res = await authFetch(`${API}/alimentacao/dietas/${id}/real`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar o real oferecido"); }
  return res.json();
}

export async function fetchComparativoDieta(id: number) {
  const res = await authFetch(`${API}/alimentacao/dietas/${id}/comparativo`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Comparativo da dieta error: ${res.status}`);
  return res.json();
}

// ── Farmácia (estoque por princípio ativo) ──
export type ApresentacaoFarmacia = {
  estoque_id: number; nome: string; marca: string | null; medicamento_comercial_id: number | null;
  saldo: number; unidade: string | null; volume_por_apresentacao: number | null; volume_unidade: string | null;
  apresentacoes: number | null; estoque_inicializado: boolean;
  // Unidade de medida ATUAL do item (ex.: "ml/frasco") — ver
  // ApresentacaoEmbalagemEstoque no backend. Nunca assumir "ml"/"frasco":
  // sempre exibir este valor tal como veio, seja lá qual for.
  medida_embalagem?: string | null;
  // Composição por embalagem — só presente (não-vazio) quando o item usa o
  // cadastro novo de "Unidade (embalagem)" com lotes em aberto vinculados a
  // um tamanho. Cada linha = um lote de compra ainda com saldo.
  lotes_embalagem?: { apresentacao_quantidade: number | null; quantidade_restante: number }[];
};
export type PrincipioFarmacia = {
  id: number; nome: string; ativo: boolean; categoria: string | null; categoria_software: string | null;
  uso_principal: string | null; justificativa: string | null;
  eh_biologico: boolean; doenca_id: number | null; unidade_base: string | null; unidade_apresentacao: string | null;
  estoque_minimo_apresentacoes: number; estoque_minimo_base: number | null; minimo_modo: "base" | "apresentacoes";
  precisa_reconciliar_minimo: boolean;
  total_base: number | null; total_apresentacoes: number;
  qtd_marcas_estoque: number; abaixo_minimo: boolean; precisa_inicializar: boolean; itens: ApresentacaoFarmacia[];
};
export type MarcaComercial = { id: number; principio_ativo_id: number; nome_comercial: string; laboratorio: string | null; ativo: boolean };
export async function definirEstoqueMinimoFarmacia(principioId: number, estoqueMinimoBase: number) {
  const res = await authFetch(`${API}/farmacia/principios/${principioId}/estoque-minimo`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ estoque_minimo_base: estoqueMinimoBase }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao definir estoque mínimo"); }
  return res.json() as Promise<PrincipioFarmacia>;
}
export async function fetchFarmaciaPrincipios() {
  const res = await authFetch(`${API}/farmacia/principios`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Farmácia error: ${res.status}`);
  return res.json() as Promise<PrincipioFarmacia[]>;
}
export async function fetchFarmaciaDetalhe(id: number) {
  const res = await authFetch(`${API}/farmacia/principios/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Detalhe do princípio error: ${res.status}`);
  return res.json();
}
export async function atualizarPrincipioFarmacia(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/farmacia/principios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar princípio"); }
  return res.json();
}
export async function criarPrincipioFarmacia(dados: Record<string, any>) {
  const res = await authFetch(`${API}/farmacia/principios`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar princípio"); }
  return res.json();
}
export async function criarMarcaFarmacia(dados: { principio_ativo_id: number; nome_comercial: string; laboratorio?: string }) {
  const res = await authFetch(`${API}/farmacia/medicamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar marca"); }
  return res.json();
}
export async function excluirMarcaFarmacia(id: number) {
  const res = await authFetch(`${API}/farmacia/medicamentos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir marca"); }
  return res.json();
}
export async function fetchApresentacoesFarmacia(params: { principio_ativo_id?: number; produto?: string }) {
  const qs = new URLSearchParams();
  if (params.principio_ativo_id != null) qs.set("principio_ativo_id", String(params.principio_ativo_id));
  if (params.produto) qs.set("produto", params.produto);
  const res = await authFetch(`${API}/farmacia/apresentacoes?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Apresentações error: ${res.status}`);
  return res.json() as Promise<ApresentacaoFarmacia[]>;
}
// Lotes/frascos de compra (Fase G, 01/09/2026) — pedido do usuário:
// "registrar/comprar um medicamento escolhendo um tamanho de frasco/
// embalagem específico com sua própria dosagem, rastrear múltiplos lotes de
// tamanhos diferentes do mesmo medicamento em estoque, e — ao aplicar —
// escolher explicitamente de qual frasco/lote a dose saiu, ou, se nenhum for
// escolhido, baixar automaticamente do lote mais antigo primeiro (FIFO)."
export type LoteEstoque = {
  id: number; estoque_id: number; numero_lote: string | null; data_compra: string;
  quantidade_comprada: number; quantidade_restante: number; valor_unitario: number | null;
  observacao: string | null; ativo: boolean;
  // De qual embalagem cadastrada (ApresentacaoEmbalagemEstoque) este lote
  // veio — `apresentacao_quantidade` é resolvida ao vivo pelo backend
  // (nunca copiada), sempre um NÚMERO puro: mostrar ao lado dele a unidade
  // de medida ATUAL do item (`Estoque.medida_embalagem`), nunca um valor
  // fixo tipo "ml" ou "frasco" — ver ApresentacaoEmbalagemEstoque no backend.
  apresentacao_id: number | null; apresentacao_quantidade: number | null;
};
export async function fetchLotesEstoque(estoqueId: number) {
  const res = await authFetch(`${API}/estoque/${estoqueId}/lotes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lotes error: ${res.status}`);
  return res.json() as Promise<LoteEstoque[]>;
}
export async function abrirLoteEstoque(estoqueId: number, dados: {
  quantidade: number; data_compra: string; valor_unitario?: number | null; numero_lote?: string | null;
  observacao?: string | null; apresentacao_id?: number | null;
}) {
  const res = await authFetch(`${API}/estoque/${estoqueId}/lotes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao abrir lote"); }
  return res.json() as Promise<LoteEstoque & { avisos: string[] }>;
}

// Embalagens (tamanhos de frasco/pacote) cadastráveis por item de Estoque —
// pedido do usuário (04/09/2026): comprar "Agrovet frasco de 100ml" ou
// "Agrovet frasco de 50ml" sem precisar de um item de Estoque à parte pra
// cada tamanho. Só o número (`quantidade`) é cadastrado aqui — a unidade é
// sempre `Estoque.medida_embalagem` do item, nunca duplicada nesta tabela.
export type ApresentacaoEmbalagemEstoque = {
  id: number; estoque_id: number; quantidade: number; ativa: boolean;
};
export async function fetchEmbalagensEstoque(estoqueId: number) {
  const res = await authFetch(`${API}/estoque/${estoqueId}/embalagens`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Embalagens error: ${res.status}`);
  return res.json() as Promise<ApresentacaoEmbalagemEstoque[]>;
}
export async function criarEmbalagemEstoque(estoqueId: number, quantidade: number) {
  const res = await authFetch(`${API}/estoque/${estoqueId}/embalagens`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ quantidade }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cadastrar embalagem"); }
  return res.json() as Promise<ApresentacaoEmbalagemEstoque>;
}
export async function removerEmbalagemEstoque(estoqueId: number, embalagemId: number) {
  const res = await authFetch(`${API}/estoque/${estoqueId}/embalagens/${embalagemId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao remover embalagem"); }
  return res.json();
}

export async function inicializarEstoqueFarmacia(estoqueId: number, dados: { quantidade: number; data?: string; observacao?: string }) {
  const res = await authFetch(`${API}/farmacia/estoque/${estoqueId}/inicializar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao inicializar estoque"); }
  return res.json();
}

// Mesclagem de itens de Estoque (01/09/2026) — "o tenant alinhar com o
// padrão CowData sem perder histórico/estoque": junta um item digitado pela
// fazenda com o item-fantasma que o fan-out do Painel CowData criou (ou
// dois itens duplicados quaisquer do mesmo princípio ativo), preservando
// MovimentoEstoque, lotes/frascos abertos e saldo físico do(s) perdedor(es)
// — ver POST /estoque/{sobrevivente_id}/mesclar.
export type SugestaoMesclagem = {
  principio_ativo_id: number; principio_ativo_nome: string; sobrevivente_sugerido_id: number;
  itens: { id: number; nome: string; quantidade: number | null; medicamento_comercial_id?: number | null }[];
};
export async function fetchSugestoesMesclagem() {
  const res = await authFetch(`${API}/estoque/sugestoes-mesclagem`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Sugestões de mesclagem error: ${res.status}`);
  return res.json() as Promise<SugestaoMesclagem[]>;
}
export async function mesclarItensEstoque(sobreviventeId: number, perdedorIds: number[]) {
  const res = await authFetch(`${API}/estoque/${sobreviventeId}/mesclar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ perdedor_ids: perdedorIds }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao mesclar itens"); }
  return res.json() as Promise<{
    sobrevivente: Record<string, any>; mesclados: number; estoque_transferido: number; alinhou_padrao_cowdata: boolean;
  }>;
}

// ── Indicações terapêuticas (substituto inteligente: princípio ↔ doença ↔ prioridade) ──
export type IndicacaoTerapeutica = { id: number; doenca_id: number; doenca: string; prioridade: number };
export type OpcaoIndicacaoDoenca = {
  principio_ativo_id: number; nome: string; classificacao: string | null; prioridade: number;
  status_estoque: "ok" | "low" | "out"; total_apresentacoes: number | null; unidade_apresentacao: string | null;
  marcas: string[];
};
export async function fetchIndicacoes(principioAtivoId: number) {
  const res = await authFetch(`${API}/farmacia/indicacoes?principio_ativo_id=${principioAtivoId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Indicações error: ${res.status}`);
  return res.json() as Promise<IndicacaoTerapeutica[]>;
}
export async function criarIndicacao(dados: { principio_ativo_id: number; doenca_id: number; prioridade: number }) {
  const res = await authFetch(`${API}/farmacia/indicacoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao indicar princípio para a doença"); }
  return res.json() as Promise<IndicacaoTerapeutica>;
}
export async function excluirIndicacao(id: number) {
  const res = await authFetch(`${API}/farmacia/indicacoes/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir indicação"); }
  return res.json();
}
export async function fetchIndicacoesDoenca(doencaId: number) {
  const res = await authFetch(`${API}/sanidade/indicacoes-doenca/${doencaId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Indicações por doença error: ${res.status}`);
  return res.json() as Promise<{ doenca_id: number; doenca: string; opcoes: OpcaoIndicacaoDoenca[] }>;
}

// ── Catálogo de indicações da aba Farmácia (Fase 5) ──
// Tela única: cada INDICAÇÃO (doença/manejo, `tipo` = doenca | reprodutivo |
// produtivo | preventivo | suporte) traz a cadeia completa PRINCÍPIOS que
// tratam → MARCAS de cada princípio, já com bula e carência formatada
// (`carencia.texto`, pronto do backend — ver lib/carencia.ts para o preview
// do formulário). Catálogo nasce global (fazenda_id nulo); a fazenda que
// quer editar bula/prioridade/nota PERSONALIZA a indicação antes (clona).
export type CarenciaFarmacia = {
  leite_dias: number | null; carne_dias: number | null; proibido_lactacao: boolean; texto: string;
  liberacao_leite?: string | null; liberacao_carne?: string | null;
};
export type MarcaIndicacaoCatalogo = {
  id: number; nome_comercial: string; laboratorio: string | null; uso_principal: string | null;
  concentracao: string | null; dose_texto: string | null; dose_padrao: number | null; unidade_dose: string | null;
  via_padrao: string | null; link_bula: string | null; alerta: string | null; alerta_gestacao: boolean;
  carencia: CarenciaFarmacia; editavel: boolean;
};
export type PrincipioIndicacaoCatalogo = {
  id: number; nome: string; categoria_software: string | null; prioridade: number; nota: string | null;
  indicacao_id: number; abaixo_minimo: boolean; total_apresentacoes: number; precisa_inicializar: boolean;
  marcas: MarcaIndicacaoCatalogo[];
};
export type IndicacaoCatalogo = {
  id: number; nome: string; tipo: string; descricao: string | null;
  personalizada: boolean; origem_id: number | null; principios: PrincipioIndicacaoCatalogo[];
};
export async function fetchIndicacoesCatalogo(tipo?: string, busca?: string) {
  const qs = new URLSearchParams();
  if (tipo) qs.set("tipo", tipo);
  if (busca) qs.set("busca", busca);
  const res = await authFetch(`${API}/farmacia/indicacoes-catalogo${qs.toString() ? `?${qs}` : ""}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Catálogo de indicações error: ${res.status}`);
  return res.json() as Promise<IndicacaoCatalogo[]>;
}
export async function personalizarIndicacao(id: number) {
  const res = await authFetch(`${API}/farmacia/indicacoes/${id}/personalizar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao personalizar indicação"); }
  return res.json() as Promise<IndicacaoCatalogo>;
}
export async function despersonalizarIndicacao(id: number) {
  const res = await authFetch(`${API}/farmacia/indicacoes/${id}/personalizar`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao voltar ao padrão"); }
  return res.json();
}
// Editar um campo do padrão (marca global ou vínculo global) personaliza a
// indicação automaticamente num passo só — o backend clona pra fazenda e
// aplica a edição no clone, sinalizando isso em `personalizou_automaticamente`
// pra tela poder avisar o usuário (ver Farmacia.tsx).
export async function atualizarMarcaFarmacia(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/farmacia/medicamentos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar a bula"); }
  return res.json() as Promise<Record<string, any> & { personalizou_automaticamente?: boolean }>;
}
export async function atualizarVinculoIndicacao(id: number, dados: { prioridade: number; nota?: string | null }) {
  const res = await authFetch(`${API}/farmacia/indicacoes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar prioridade/nota"); }
  return res.json() as Promise<{
    id: number; doenca_id: number; principio_ativo_id: number; prioridade: number; nota: string | null;
    personalizou_automaticamente?: boolean;
  }>;
}

// ── Painel CowData > Farmácia — cadastro CENTRAL do catálogo padrão
// (categoria/doença, princípio ativo, medicamento) que fica visível a TODAS
// as fazendas-cliente (catálogo global) e, no caso de medicamento, também
// gera automaticamente o item de Estoque em cada uma (inativo/não-estocável,
// pra o tenant ativar se quiser) — ver backend/fazenda/api/routers/
// painel_cowdata_farmacia.py.
export type CategoriaFarmaciaCowData = {
  id: number; nome: string; tipo: string; descricao: string | null; ativo: boolean; fazenda_id: number | null;
};
export type PrincipioFarmaciaCowData = Record<string, any> & { id: number; nome: string };
export type MedicamentoFarmaciaCowData = Record<string, any> & {
  id: number; nome_comercial: string; principio_ativo_ids: number[]; doenca_ids: number[];
  fan_out_fazendas: number; fan_out_total_fazendas: number;
};

export async function fetchCategoriasFarmaciaCowData() {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/categorias`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Categorias error: ${res.status}`);
  return res.json() as Promise<CategoriaFarmaciaCowData[]>;
}
export async function criarCategoriaFarmaciaCowData(dados: { nome: string; tipo: string; descricao?: string | null; ativo?: boolean }) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/categorias`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar categoria"); }
  return res.json() as Promise<CategoriaFarmaciaCowData>;
}
export async function atualizarCategoriaFarmaciaCowData(id: number, dados: { nome: string; tipo: string; descricao?: string | null; ativo?: boolean }) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/categorias/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar categoria"); }
  return res.json() as Promise<CategoriaFarmaciaCowData>;
}
export async function fetchPrincipiosFarmaciaCowData() {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/principios`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Princípios error: ${res.status}`);
  return res.json() as Promise<PrincipioFarmaciaCowData[]>;
}
export async function criarPrincipioFarmaciaCowData(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/principios`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar princípio ativo"); }
  return res.json() as Promise<PrincipioFarmaciaCowData>;
}
export async function atualizarPrincipioFarmaciaCowData(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/principios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar princípio ativo"); }
  return res.json() as Promise<PrincipioFarmaciaCowData>;
}
export async function excluirPrincipioFarmaciaCowData(id: number) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/principios/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir princípio ativo"); }
  return res.json() as Promise<{ excluido: boolean; impacto: string[] }>;
}
export async function fetchMedicamentosFarmaciaCowData() {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/medicamentos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Medicamentos error: ${res.status}`);
  return res.json() as Promise<MedicamentoFarmaciaCowData[]>;
}
export async function fetchMedicamentoGlobalDetalhe(id: number) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/medicamentos/${id}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Detalhe do medicamento error: ${res.status}`); }
  return res.json() as Promise<Record<string, any>>;
}
export async function criarMedicamentoFarmaciaCowData(dados: Record<string, any>) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/medicamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar medicamento"); }
  return res.json() as Promise<MedicamentoFarmaciaCowData & { fan_out: { criados: number; ja_existiam: number } }>;
}
export async function atualizarMedicamentoFarmaciaCowData(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/medicamentos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar medicamento"); }
  return res.json() as Promise<MedicamentoFarmaciaCowData>;
}
export async function refazerFanoutMedicamentoFarmaciaCowData(id: number) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/medicamentos/${id}/fanout`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao propagar medicamento"); }
  return res.json() as Promise<{ criados: number; ja_existiam: number }>;
}

// Laboratório / Categoria (medicamento) / Classificação do medicamento —
// cadastro central no Painel CowData (mesmo padrão "nome + ativo" de
// Princípios ativos acima, ver painel_cowdata_farmacia.py::_crud_catalogo_global).
function criarApiCatalogoFarmaciaCowData(rota: string, rotulo: string) {
  return {
    fetch: async (): Promise<ItemCadastroSimples[]> => {
      const res = await authFetch(`${API}/painel-cowdata/farmacia/${rota}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`${rotulo} error: ${res.status}`);
      return res.json();
    },
    criar: async (dados: { nome: string; ativo?: boolean }): Promise<ItemCadastroSimples> => {
      const res = await authFetch(`${API}/painel-cowdata/farmacia/${rota}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Erro ao criar ${rotulo.toLowerCase()}`); }
      return res.json();
    },
    atualizar: async (id: number, dados: { nome: string; ativo: boolean }): Promise<ItemCadastroSimples> => {
      const res = await authFetch(`${API}/painel-cowdata/farmacia/${rota}/${id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Erro ao atualizar ${rotulo.toLowerCase()}`); }
      return res.json();
    },
  };
}

const apiLaboratoriosFarmaciaCowData = criarApiCatalogoFarmaciaCowData("laboratorios", "Laboratório");
export const fetchLaboratoriosFarmaciaCowData = apiLaboratoriosFarmaciaCowData.fetch;
export const criarLaboratorioFarmaciaCowData = apiLaboratoriosFarmaciaCowData.criar;
export const atualizarLaboratorioFarmaciaCowData = apiLaboratoriosFarmaciaCowData.atualizar;

const apiCategoriasMedicamentoFarmaciaCowData = criarApiCatalogoFarmaciaCowData("categorias-medicamento", "Categoria (medicamento)");
export const fetchCategoriasMedicamentoFarmaciaCowData = apiCategoriasMedicamentoFarmaciaCowData.fetch;
export const criarCategoriaMedicamentoFarmaciaCowData = apiCategoriasMedicamentoFarmaciaCowData.criar;
export const atualizarCategoriaMedicamentoFarmaciaCowData = apiCategoriasMedicamentoFarmaciaCowData.atualizar;

const apiClassificacoesMedicamentoFarmaciaCowData = criarApiCatalogoFarmaciaCowData("classificacoes-medicamento", "Classificação do medicamento");
export const fetchClassificacoesMedicamentoFarmaciaCowData = apiClassificacoesMedicamentoFarmaciaCowData.fetch;
export const criarClassificacaoMedicamentoFarmaciaCowData = apiClassificacoesMedicamentoFarmaciaCowData.criar;
export const atualizarClassificacaoMedicamentoFarmaciaCowData = apiClassificacoesMedicamentoFarmaciaCowData.atualizar;

// Substitutivos (Fase E, 01/09/2026) — tabela dinâmica de cruzamento: 1º
// nível filtra medicamentos por um eixo/item; 2º nível ranqueia os
// substitutos de um medicamento pivô por atributos clínicos coincidentes.
export type EixoFiltroSubstitutivos = "doenca" | "principio" | "categoria" | "classificacao" | "laboratorio";
export type MedicamentoSubstituto = MedicamentoFarmaciaCowData & {
  pontuacao_substituto: number;
  coincidencias: { principio_ativo_ids: number[]; doenca_ids: number[]; categoria_medicamento_ids: number[]; classificacao_medicamento_ids: number[] };
};

export async function fetchSubstitutivosPorFiltro(eixo: EixoFiltroSubstitutivos, valorId: number) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/substitutivos?eixo=${eixo}&valor_id=${valorId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Substitutivos error: ${res.status}`);
  return res.json() as Promise<MedicamentoFarmaciaCowData[]>;
}
export async function fetchSubstitutivosDeMedicamento(medicamentoId: number) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/medicamentos/${medicamentoId}/substitutivos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Substitutivos error: ${res.status}`);
  return res.json() as Promise<MedicamentoSubstituto[]>;
}

// Diagnóstico (proposta validada em artefato, 04/09/2026) — audita, fazenda
// por fazenda, se o catálogo central chegou direito no estoque do tenant.
// Ver docstring da seção em painel_cowdata_farmacia.py.
export type ItemDiagnosticoCasado = {
  estoque_id: number; nome: string; medicamento_comercial_id: number; nome_comercial_central: string | null;
  principio_ativo: string | null; categoria: string | null; classificacao_medicamento: string | null;
};
export type ItemDiagnosticoOrfao = {
  estoque_id: number; nome: string; principio_ativo: string | null; categoria: string | null;
  classificacao_medicamento: string | null; ativo: boolean;
};
export type ItemDiagnosticoAusente = MedicamentoFarmaciaCowData & { estoque_id: null };
export type DiagnosticoFarmacia = {
  fazenda_id: number; casados: ItemDiagnosticoCasado[]; orfaos: ItemDiagnosticoOrfao[]; ausentes: ItemDiagnosticoAusente[];
};

export async function fetchFazendasFarmaciaCowData() {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/fazendas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Fazendas error: ${res.status}`);
  return res.json() as Promise<{ id: number; nome: string }[]>;
}
export async function fetchDiagnosticoFarmaciaCowData(fazendaId: number) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/diagnostico?fazenda_id=${fazendaId}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Diagnóstico error: ${res.status}`); }
  return res.json() as Promise<DiagnosticoFarmacia>;
}
export async function vincularDiagnosticoFarmaciaCowData(dados: { fazenda_id: number; estoque_id: number; medicamento_comercial_id: number }) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/diagnostico/vincular`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao vincular ao catálogo central"); }
  return res.json() as Promise<Record<string, any>>;
}
export async function ativarDiagnosticoFarmaciaCowData(dados: { fazenda_id: number; medicamento_comercial_id: number }) {
  const res = await authFetch(`${API}/painel-cowdata/farmacia/diagnostico/ativar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar item de estoque"); }
  return res.json() as Promise<Record<string, any>>;
}

export async function fetchProducao() {
  const res = await authFetch(`${API}/producao/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Produção error: ${res.status}`);
  return res.json();
}

export async function fetchControles() {
  const res = await authFetch(`${API}/producao/controles`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Controles error: ${res.status}`);
  return res.json();
}

// Reconstrução de Parto.ordem_parto — a FONTE do dado (não o derivado em
// ControleLeiteiro, logo abaixo). Ver fazenda/api/routers/producao.py (seção
// "Reconstrução de Parto.ordem_parto") e rules/parto.py para o porquê
// completo. Rode esta ANTES da de Controles: aquela lê Parto.ordem_parto
// como fonte de verdade. GET nunca grava nada; POST só grava com
// `confirmar: true` explícito.
export type AmostraDivergenciaOrdemPartoPartos = {
  numero_matriz: string;
  data_parto: string | null;
  ordem_hoje: number | null;
  ordem_correta: number | null;
};
export type DivergenciasOrdemPartoPartos = {
  partos: number;
  matrizes_com_parto: number;
  muda: number;
  vira_desconhecido: number;
  periodo_partos: [string, string] | null;
  amostra: AmostraDivergenciaOrdemPartoPartos[];
};
export async function fetchDivergenciasOrdemPartoPartos(): Promise<DivergenciasOrdemPartoPartos> {
  const res = await authFetch(`${API}/producao/ordem-parto/partos/divergencias`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao levantar as divergências de ordem de parto"); }
  return res.json();
}
export async function reconstruirOrdemPartoPartos(confirmar: boolean): Promise<{ gravados: number }> {
  const res = await authFetch(`${API}/producao/ordem-parto/partos/reconstruir`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmar }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao reconstruir a ordem de parto"); }
  return res.json();
}

// Reconstrução de ControleLeiteiro.ordem_parto — ferramenta de correção de
// dados histórica, ver fazenda/api/routers/producao.py (seção "Reconstrução
// de ControleLeiteiro.ordem_parto") e rules/ordem_parto_historica.py para o
// porquê completo. GET nunca grava nada; POST só grava com
// `confirmar: true` explícito.
export type AmostraDivergenciaOrdemParto = {
  numero_matriz: string;
  data_controle: string | null;
  ordem_hoje: number | null;
  ordem_correta: number | null;
};
export type DivergenciasOrdemParto = {
  partos: number;
  controles: number;
  animais_com_parto: number;
  lactacoes_por_ordem: Record<string, number>;
  idade_ao_parto: Record<string, number>;
  muda: number;
  vira_desconhecido: number;
  periodo_partos: [string, string] | null;
  periodo_controles: [string, string] | null;
  amostra: AmostraDivergenciaOrdemParto[];
};
export async function fetchDivergenciasOrdemParto(): Promise<DivergenciasOrdemParto> {
  const res = await authFetch(`${API}/producao/ordem-parto/divergencias`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao levantar as divergências de ordem de parto"); }
  return res.json();
}
export async function reconstruirOrdemParto(confirmar: boolean): Promise<{ gravados: number }> {
  const res = await authFetch(`${API}/producao/ordem-parto/reconstruir`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmar }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao reconstruir a ordem de parto"); }
  return res.json();
}

// Reconstrução de ControleLeiteiro.del_no_controle — mesmo padrão report-first
// da ordem de parto acima, ver fazenda/api/routers/producao.py (seção
// "Reconstrução de ControleLeiteiro.del_no_controle"). GET nunca grava nada;
// POST só grava com `confirmar: true` explícito.
export type AmostraDivergenciaDelControle = {
  numero_matriz: string;
  data_controle: string | null;
  del_hoje: number | null;
  del_correto: number | null;
};
export type DivergenciasDelControle = {
  controles: number;
  muda: number;
  sem_lactacao: number;
  periodo_controles: [string, string] | null;
  amostra: AmostraDivergenciaDelControle[];
};
export async function fetchDivergenciasDelControle(): Promise<DivergenciasDelControle> {
  const res = await authFetch(`${API}/producao/del-controle/divergencias`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao levantar as divergências de DEL"); }
  return res.json();
}
export async function reconstruirDelControle(confirmar: boolean): Promise<{ gravados: number }> {
  const res = await authFetch(`${API}/producao/del-controle/reconstruir`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmar }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao reconstruir o DEL dos controles"); }
  return res.json();
}

// Equivalente maduro — redesign "padronização por vaca" (ver nota de
// redesign no topo de `fazenda/rules/equivalente_maduro.py`). O trio de
// apresentação (produz hoje / produzirá / diferença) nunca aparece sozinho;
// os tipos abaixo espelham exatamente o `TrioEquivalenteMaduro` do backend.
// Fatores fixos de tabela (Holandês, sempre — não depende mais de mínimo de
// lactações do rebanho); confiança é a fração medida/projetada, não mais
// tamanho de amostra do rebanho.
export type NivelConfiancaEM = "muito baixa" | "baixa" | "média" | "alta";

export type TrioEquivalenteMaduro = {
  numero_matriz?: string;
  ordem_parto: number | null;
  classe: number | null;
  producao_hoje_kg: number | null;
  n_controles: number;
  ja_maduro: boolean;
  producao_maturidade_kg: number | null;
  diferenca_kg: number | null;
  confianca_nivel: NivelConfiancaEM | null;
  confianca_fracao: number | null; // kg medido / kg projetado, 0..1
  sem_base: boolean;
  motivo: string | null;
  // Presentes só nas linhas do relatório/ficha (não na calculadora avulsa).
  del_atual?: number;
  del_ultimo_controle?: number | null;
  estimada?: boolean;
  secagem_precoce?: boolean;
  faltam_partos_maturidade?: number | null;
  producao_dia_historica_kg?: number | null;
};

// Painel de aferição — fator observado no próprio rebanho × fator fixo de
// tabela, por classe. Puramente informativo (collapsible no front); nunca
// altera a conta do trio acima.
export type LinhaAfericaoEM = {
  classe: number;
  n_lactacoes: number;
  fator_observado: number | null;
  fator_tabela: number;
  divergencia_pct: number | null;
  confianca_observado: "baixa" | "ok" | null;
};

export type RelatorioEquivalenteMaduro = {
  painel_afericao: LinhaAfericaoEM[];
  animais: TrioEquivalenteMaduro[];
};

export async function fetchEquivalenteMaduro(): Promise<RelatorioEquivalenteMaduro> {
  const res = await authFetch(`${API}/producao/equivalente-maduro`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Equivalente maduro error: ${res.status}`);
  return res.json();
}

export async function fetchEquivalenteMaduroDoAnimal(numeroMatriz: string): Promise<TrioEquivalenteMaduro> {
  const res = await authFetch(`${API}/producao/equivalente-maduro/${encodeURIComponent(numeroMatriz)}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Equivalente maduro error: ${res.status}`); }
  return res.json();
}

export async function calcularEquivalenteMaduro(dados: {
  ordem_parto: number;
  pontos: { del_dias: number; producao_kg: number }[];
  del_secagem?: number | null;
}): Promise<TrioEquivalenteMaduro> {
  const res = await authFetch(`${API}/producao/equivalente-maduro/calcular`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao calcular equivalente maduro"); }
  return res.json();
}

export async function criarControlesLeiteiros(dados: {
  data_controle: string;
  entradas: { numero_matriz: string; ordenhas: (number | null)[] }[];
}) {
  const res = await authFetch(`${API}/producao/controles`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  // 409 = animal sem lactação aberta na data (ver POST /producao/controles).
  // `erroDaResposta` preserva o `detail` para a tela poder dizer QUAL vaca.
  if (!res.ok) throw await erroDaResposta(res, "Erro ao lançar controle leiteiro");
  return res.json();
}

// Baixa um arquivo binário autenticado (o backend exige Bearer token, então não
// dá pra usar um <a href> direto) — dispara o download no navegador via blob.
// Exportada (só pra este único uso fora do arquivo até agora) porque
// lib/dietas.ts precisa dela pro download do modelo da biblioteca de
// alimentos — mesmo padrão de baixarModeloTabelaNutricional/baixarModeloCocho
// aqui embaixo, só que noutro arquivo por Formulação de Dietas ter seu
// próprio módulo de tipos/chamadas (ver cabeçalho de lib/dietas.ts).
export async function baixarArquivoAutenticado(path: string, nomeArquivoFallback: string) {
  const res = await authFetch(`${API}${path}`);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao baixar arquivo"); }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const nome = /filename="?([^"]+)"?/.exec(cd)?.[1] || nomeArquivoFallback;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = nome;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

export function baixarModeloControleLeiteiro(modo: "animal" | "lote") {
  return baixarArquivoAutenticado(
    `/producao/controle-leiteiro/modelo-excel?modo=${modo}`,
    `modelo_controle_leiteiro_${modo}.xlsx`,
  );
}

export async function importarControleLeiteiroPlanilha(file: File): Promise<{ criados: number; erros: string[]; modo: "animal" | "lote" }> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/producao/controle-leiteiro/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao importar planilha"); }
  return res.json();
}

// Fluxo de revisão: enviar a planilha só devolve as linhas normalizadas
// (sem gravar nada) — o usuário edita na tela e só então confirma
// (POST /confirmar), com as linhas já corrigidas se precisar.
export type LinhaControleLeiteiroPreview = {
  numero_matriz: string; data_controle: string;
  ordenha1_kg: number | null; ordenha2_kg: number | null; ordenha3_kg: number | null; total_kg: number | null;
};
export async function preVisualizarControleLeiteiroPlanilha(file: File): Promise<{ linhas: LinhaControleLeiteiroPreview[]; erros: string[]; modo: "animal" | "lote" }> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/producao/controle-leiteiro/pre-visualizar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao ler a planilha"); }
  return res.json();
}
export async function confirmarControleLeiteiroPlanilha(linhas: LinhaControleLeiteiroPreview[]): Promise<{ criados: number }> {
  const res = await authFetch(`${API}/producao/controle-leiteiro/confirmar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ linhas }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar o controle leiteiro"); }
  return res.json();
}

// ── Pesagem corporal (peso vivo) ──
export async function criarPesagensCorporais(dados: {
  data_pesagem: string;
  entradas: { numero_matriz: string; peso_kg: number }[];
}) {
  const res = await authFetch(`${API}/producao/pesagens`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar pesagem corporal"); }
  return res.json();
}

export function baixarModeloPesagemCorporal() {
  return baixarArquivoAutenticado("/producao/pesagens/modelo-excel", "modelo_pesagem_corporal.xlsx");
}

export async function importarPesagemCorporalPlanilha(file: File): Promise<{ criados: number; erros: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/producao/pesagens/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao importar planilha"); }
  return res.json();
}

// G7 — /producao/pesagens/relatorio (acima) agrega por animal e não devolve
// `id`; esta é a listagem individual (com id) que sustenta editar/excluir.
export type PesagemFiltros = { numero_matriz?: string; grupo?: string; data_inicio?: string; data_fim?: string; limite?: number };
export type PesagemLinha = {
  id: number; numero_matriz: string; data_pesagem: string; peso_kg: number;
  del_dias: number | null; idade_meses: number | null; grupo_primario: string | null;
  fase: string | null; usuario_nome: string | null;
};
export async function fetchPesagens(filtros: PesagemFiltros = {}): Promise<{ pesagens: PesagemLinha[]; total: number }> {
  const qs = new URLSearchParams();
  if (filtros.numero_matriz) qs.set("numero_matriz", filtros.numero_matriz);
  if (filtros.grupo) qs.set("grupo", filtros.grupo);
  if (filtros.data_inicio) qs.set("data_inicio", filtros.data_inicio);
  if (filtros.data_fim) qs.set("data_fim", filtros.data_fim);
  if (filtros.limite) qs.set("limite", String(filtros.limite));
  const res = await authFetch(`${API}/producao/pesagens?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Pesagens error: ${res.status}`);
  return res.json();
}
// `data_pesagem`/`peso_kg` são opcionais (exclude_unset no backend) — manda só o que mudou.
// Mudar a data recalcula `fase`; `del_dias`/`idade_meses`/`grupo_primario` são
// fotos do momento do lançamento e não são recalculados.
export type PesagemEditIn = { data_pesagem?: string; peso_kg?: number };
export async function atualizarPesagem(id: number, dados: PesagemEditIn) {
  const res = await authFetch(`${API}/producao/pesagens/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar pesagem"); }
  return res.json();
}
// A exclusão roteia pelo motor genérico — confirmarExclusao("pesagem_corporal", id).

// ── Qualidade do leite ──
export async function fetchQualidadeLeite() {
  const res = await authFetch(`${API}/producao/qualidade-leite`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Qualidade do leite error: ${res.status}`);
  return res.json();
}
export async function criarQualidadeLeite(dados: {
  numero_matriz?: string | null; data_coleta: string;
  ccs?: number | null; cbt?: number | null; gordura_pct?: number | null; proteina_pct?: number | null;
  solidos_totais_pct?: number | null; esd_pct?: number | null; lactose_pct?: number | null; nul?: number | null; observacao?: string | null;
}) {
  const res = await authFetch(`${API}/producao/qualidade-leite`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar qualidade do leite"); }
  return res.json();
}

export function baixarModeloQualidadeLeite() {
  return baixarArquivoAutenticado("/producao/qualidade-leite/modelo-excel", "modelo_qualidade_leite.xlsx");
}

export async function importarQualidadeLeitePlanilha(file: File): Promise<{ criados: number; erros: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/producao/qualidade-leite/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao importar planilha"); }
  return res.json();
}

// ── Venda mensal do leite ──
export async function fetchEntregaLeiteMensal() {
  const res = await authFetch(`${API}/producao/entrega-leite`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Venda mensal do leite error: ${res.status}`);
  return res.json();
}
export async function criarEntregaLeiteMensal(dados: { competencia: string; quantidade_litros: number; unidade?: string; observacao?: string | null }) {
  const res = await authFetch(`${API}/producao/entrega-leite`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar entrega mensal do leite"); }
  return res.json();
}
// G6 — o POST acima já faz upsert por competência (editar o valor de um mês
// já funciona); o PUT serve pra corrigir a COMPETÊNCIA errada. 409 se a nova
// competência já tiver outro registro na mesma fazenda.
export type EntregaLeiteEditIn = { competencia: string; quantidade_litros: number; unidade?: string; observacao?: string | null };
export async function atualizarEntregaLeite(id: number, dados: EntregaLeiteEditIn) {
  const res = await authFetch(`${API}/producao/entrega-leite/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar entrega de leite"); }
  return res.json();
}
// A exclusão roteia pelo motor genérico — confirmarExclusao("entrega_leite", id).

// ── Relatório controle leiteiro × ITALAC × entrega ──
export async function fetchRelatorioControleEntrega(dataInicio?: string, dataFim?: string) {
  const params = new URLSearchParams();
  if (dataInicio) params.set("data_inicio", dataInicio);
  if (dataFim) params.set("data_fim", dataFim);
  const res = await authFetch(`${API}/producao/relatorio-controle-entrega?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório controle × entregue error: ${res.status}`);
  return res.json();
}

// ── Relatório de BST (Produção) ──
export async function fetchRelatorioBst() {
  const res = await authFetch(`${API}/producao/relatorio-bst`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório de BST error: ${res.status}`);
  return res.json();
}

export async function ajustarProximaAplicacaoBst(novaData: string, modo: "intervalo" | "referencia") {
  const res = await authFetch(`${API}/producao/bst/ajustar-proxima-aplicacao`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nova_data: novaData, modo }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(mensagemErroApi(d.detail) || "Não foi possível ajustar a próxima aplicação de BST.");
  }
  return res.json();
}

// ── Secagem ──
export async function fetchSecagemInfo(numeroMatriz: string) {
  const res = await authFetch(`${API}/producao/secagem-info?numero_matriz=${encodeURIComponent(numeroMatriz)}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao buscar dados de secagem"); }
  return res.json();
}
export async function criarSecagem(dados: {
  numero_matriz: string; data_secagem: string; motivo: string; escore_condicao_corporal?: number | null;
  observacao?: string; responsavel?: string; aplicado?: boolean;
  produtos: { produto: string; via?: string; quantidade: number; unidade: string }[];
  vacinas_pre_parto?: string[];
  vacina_pre_parto_aplicada_agora?: boolean;
  vacina_pre_parto?: boolean | null;
  // Resposta a "esta vaca já consta como seca — substituir ou cancelar?"
  // (ver `ErroApi.secagemAnterior` abaixo): id da secagem a substituir.
  substituir_secagem_id?: number;
}) {
  const res = await authFetch(`${API}/producao/secagem`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  // `erroDaResposta` preserva o `detail` para a tela oferecer "substituir a
  // secagem anterior ou cancelar" em vez de só mostrar a mensagem de erro.
  if (!res.ok) throw await erroDaResposta(res, "Erro ao lançar secagem");
  return res.json();
}
export type LoteSugeridoEvento = { codigo: string; nome: string; rotulo: string };
export async function sugestaoLoteEvento(dados: { numero_matriz: string; categoria_abrev: string; del_dias?: number | null; data_nasc?: string | null }): Promise<{ lote_sugerido: LoteSugeridoEvento | null }> {
  const res = await authFetch(`${API}/producao/sugestao-lote-evento`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao buscar sugestão de lote"); }
  return res.json();
}

// ── Serviço/IA: protocolo IATF (só agenda) e inseminação (o evento em si) ──
export type HormonioIatf = { dia: number; produto: string; dose?: number | null; unidade?: string; via?: string };
// Nome do lançamento é sempre automático (Central de Protocolos) — não se
// digita mais; protocolo_id é opcional (molde cadastrado, só para
// pré-preencher os hormônios e citar no nome).
export async function criarProtocoloIatf(dados: { animais: string[]; data_d0: string; protocolo_id?: number | null; hormonios?: HormonioIatf[]; forcar?: boolean }) {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) throw await erroDaResposta(res, "Erro ao agendar protocolo IATF");
  return res.json();
}

// ── Molde de IATF (Central de Protocolos > Cadastro) ──
export type EtapaProtocoloIatf = {
  dia: number; criterio_tipo: "medicamento" | "principio_ativo" | "classificacao";
  principio_ativo_id?: number | null; produto: string; dose?: number | null; unidade?: string; via?: string;
};
export type ProtocoloIatfMolde = {
  id: number; nome: string; observacao: string | null; ativo: boolean; etapas: EtapaProtocoloIatf[];
};
export async function fetchProtocolosIatfCadastrados(): Promise<ProtocoloIatfMolde[]> {
  const res = await authFetch(`${API}/cadastro/protocolos-iatf`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos IATF cadastrados error: ${res.status}`);
  return res.json();
}
export async function criarProtocoloIatfCadastrado(dados: { nome: string; observacao?: string | null; ativo?: boolean; etapas: EtapaProtocoloIatf[] }): Promise<ProtocoloIatfMolde> {
  const res = await authFetch(`${API}/cadastro/protocolos-iatf`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cadastrar protocolo IATF"); }
  return res.json();
}
export async function atualizarProtocoloIatfCadastrado(id: number, dados: { nome: string; observacao?: string | null; ativo?: boolean; etapas: EtapaProtocoloIatf[] }): Promise<ProtocoloIatfMolde> {
  const res = await authFetch(`${API}/cadastro/protocolos-iatf/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar protocolo IATF"); }
  return res.json();
}
export async function excluirProtocoloIatfCadastrado(id: number): Promise<void> {
  const res = await authFetch(`${API}/cadastro/protocolos-iatf/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir protocolo IATF"); }
}

// ── Central de Protocolos — Acompanhamento e Histórico (IATF + Indução +
// Sanitário + Customizado, juntos e filtráveis por nome/período/tipo) ──
export type LinhaCentralProtocolos = {
  tipo: "produtivo" | "reprodutivo" | "sanitario" | "lida"; origem: "iatf" | "inducao" | "sanitario" | "customizado" | "lida";
  origem_id: number; nome: string; data_inicio: string; data_fim: string;
  etapas_total: number; etapas_realizadas: number; etapas_faltam: number;
  // "encerrado": acabou antes do fim do cronograma. As etapas que sobraram
  // seguem contadas como NÃO realizadas — encerrar não maquia o progresso.
  animais: number; status: "ativo" | "concluido" | "encerrado" | "cancelado";
  encerrado_em?: string | null; encerrado_motivo?: string | null;
};
export async function fetchCentralProtocolosAcompanhamento(params?: { nome?: string; tipo?: string }): Promise<LinhaCentralProtocolos[]> {
  const qs = new URLSearchParams();
  if (params?.nome) qs.set("nome", params.nome);
  if (params?.tipo) qs.set("tipo", params.tipo);
  const res = await authFetch(`${API}/central-protocolos/acompanhamento?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Central de Protocolos (acompanhamento) error: ${res.status}`);
  return res.json();
}
export async function fetchCentralProtocolosHistorico(params?: { nome?: string; tipo?: string; data_de?: string; data_ate?: string }): Promise<LinhaCentralProtocolos[]> {
  const qs = new URLSearchParams();
  if (params?.nome) qs.set("nome", params.nome);
  if (params?.tipo) qs.set("tipo", params.tipo);
  if (params?.data_de) qs.set("data_de", params.data_de);
  if (params?.data_ate) qs.set("data_ate", params.data_ate);
  const res = await authFetch(`${API}/central-protocolos/historico?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Central de Protocolos (histórico) error: ${res.status}`);
  return res.json();
}

// Detalhe de UM lançamento: a grade animal × dia. É o que permite fechar o
// ciclo — até 08/2026 a Agenda era o único lugar capaz de marcar uma etapa
// como realizada, e ela escondia a etapa cujo dia já tinha passado.
export type CelulaProtocolo = {
  dia: number; rotulo: string; data_prevista: string; data_realizacao: string | null;
  realizada: boolean; estado: "realizada" | "atrasada" | "pendente";
};
// Opção de frasco em estoque para um hormônio do dia (mesmo formato que a
// Agenda já usa em `hormonios`/`medicamentos_opcoes`, ver agenda/page.tsx).
// `estoque_id` vem `null` e `sem_estoque` vem `true` para uma marca comercial
// cadastrada que ainda não tem frasco em Estoque — só aparece com
// `incluirSemEstoque` habilitado; escolher uma dessas não abate estoque.
export type OpcaoMedicamento = {
  estoque_id: number | null; nome: string; marca: string | null; saldo: number | null;
  unidade: string | null; estoque_inicializado: boolean; sem_estoque: boolean;
  // "de qual lote/frasco de COMPRA?" (Fase G) — só vem preenchido para
  // origem === "sanitario" hoje (ver central_protocolos.py::detalhe), e só
  // quando o frasco (estoque_id) tem algum lote aberto com saldo.
  lotes?: { id: number; numero_lote: string | null; data_compra: string; quantidade_restante: number }[];
};
export type HormonioProtocolo = {
  produto: string; dose: number | null; unidade: string | null; via: string | null;
  opcoes: OpcaoMedicamento[];
};
export type DetalheCentralProtocolo = {
  origem: string; origem_id: number; nome: string; data_inicio: string | null;
  responsavel: string | null; encerrado_em: string | null; encerrado_motivo: string | null;
  ativo: boolean; etapas_total: number; etapas_realizadas: number; etapas_atrasadas: number;
  dias: {
    dia: number; rotulo: string; data_prevista: string; descricao: string | null; total: number; realizadas: number;
    // Vem preenchido para origem === "iatf", "inducao" ou "sanitario" — o
    // "qual medicamento/frasco?" que a Agenda já pergunta, agora também na
    // Central (Sanitário ganhou também o "de qual lote?", ver OpcaoMedicamento.lotes).
    hormonios?: HormonioProtocolo[];
  }[];
  animais: { numero_matriz: string; celulas: CelulaProtocolo[] }[];
};

export async function fetchDetalheProtocolo(
  origem: string, origemId: number, incluirSemEstoque?: boolean,
): Promise<DetalheCentralProtocolo> {
  const qs = incluirSemEstoque ? "?incluir_sem_estoque=true" : "";
  const res = await authFetch(`${API}/central-protocolos/${origem}/${origemId}${qs}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao carregar o protocolo"); }
  return res.json();
}

export async function darBaixaProtocolo(origem: string, origemId: number, dados: {
  dia: number; animais?: string[] | null; data_realizacao?: string | null; medicamentos?: MedicamentoIatf[] | null;
}): Promise<{ ok: boolean; avisos: string[] }> {
  const res = await authFetch(`${API}/central-protocolos/${origem}/${origemId}/baixa`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao dar baixa"); }
  return res.json();
}

/** Desfaz UMA aplicação já confirmada (um animal, um dia) — diferente de
 *  cancelar, que desfaz o lançamento inteiro. Só IATF estorna estoque (o
 *  backend documenta o motivo do escopo). */
export async function desfazerAplicacao(origem: string, origemId: number, dia: number, numeroMatriz: string): Promise<{ ok: boolean; avisos: string[] }> {
  const res = await authFetch(`${API}/central-protocolos/${origem}/${origemId}/baixa`, {
    method: "DELETE", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dia, numero_matriz: numeroMatriz }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao desfazer a aplicação"); }
  return res.json();
}

export async function renomearProtocolo(origem: string, origemId: number, nome: string): Promise<{ ok: boolean; nome: string }> {
  const res = await authFetch(`${API}/central-protocolos/${origem}/${origemId}/renomear`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao renomear o protocolo"); }
  return res.json();
}

// G16 — genérico para as 4 origens (iatf, inducao, customizado, lida); todos
// os campos são opcionais (exclude_unset no backend). 400 se o protocolo
// estiver encerrado/cancelado, ou se `data_inicio` mudar com etapa já
// aplicada. Mudar `data_inicio` desloca `data_prevista` de todas as
// aplicações pelo mesmo delta.
export type EditarLancamentoProtocoloIn = {
  data_inicio?: string; responsavel?: string; observacao?: string; nome?: string;
};
export async function editarLancamentoProtocolo(origem: string, origemId: number, dados: EditarLancamentoProtocoloIn) {
  const res = await authFetch(`${API}/central-protocolos/${origem}/${origemId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar o lançamento do protocolo"); }
  return res.json();
}

export async function encerrarProtocolo(origem: string, origemId: number, motivo?: string) {
  const res = await authFetch(`${API}/central-protocolos/${origem}/${origemId}/encerrar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ motivo: motivo || null }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao encerrar o protocolo"); }
  return res.json();
}

/** Cancelar ≠ encerrar: aqui as aplicações voltam a "não realizadas" e o
 *  estoque consumido é devolvido. A Sanidade registrada na ficha do animal
 *  permanece — o produto entrou nele, e isso não se reescreve. */
export async function cancelarProtocolo(origem: string, origemId: number, motivo?: string): Promise<{ ok: boolean; avisos: string[] }> {
  const res = await authFetch(`${API}/central-protocolos/${origem}/${origemId}/cancelar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ motivo: motivo || null }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cancelar o protocolo"); }
  return res.json();
}

export async function reabrirProtocolo(origem: string, origemId: number) {
  const res = await authFetch(`${API}/central-protocolos/${origem}/${origemId}/encerrar`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao reabrir o protocolo"); }
  return res.json();
}
export async function fetchProtocolosIatfAtivos() {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf/ativos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos IATF ativos error: ${res.status}`);
  return res.json();
}
// A lista É a lista da próxima visita: o estado reprodutivo de cada animal é
// avaliado NAQUELA data, não hoje. Por isso `apta_na_proxima_visita` é sempre
// true — quem não estará apta lá simplesmente não vem. `apta_hoje` distingue
// quem já pode ser trabalhada agora de quem só na visita.
export type CandidataIatfProjetada = {
  numero_matriz: string; sit_rep: string | null; del_dias: number | null; motivo: string;
  estado: string; estado_rotulo: string;
  del_dias_projetado: number | null; apta_na_proxima_visita: boolean; apta_hoje: boolean;
};
export async function fetchCandidatasIatfProjetadas() {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf/candidatas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Candidatas IATF error: ${res.status}`);
  return res.json() as Promise<{ candidatas: CandidataIatfProjetada[]; proxima_visita_iatf: string | null }>;
}
export async function fetchLancamentosIatf() {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf/lancamentos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lançamentos IATF error: ${res.status}`);
  return res.json() as Promise<{ lancamento_id: number; nome_protocolo: string; data_d0: string; qtd_animais: number }[]>;
}
export async function adicionarAnimaisIatf(lancamentoId: number, animais: string[]) {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf/${lancamentoId}/animais`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ animais }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao adicionar animais ao protocolo"); }
  return res.json();
}
// Corrige uma inclusão por engano num lançamento ativo — só permite remover
// se nenhuma etapa do animal já foi confirmada (ver reproducao.py).
export async function removerAnimalIatf(lancamentoId: number, numeroMatriz: string): Promise<void> {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf/${lancamentoId}/animais/${encodeURIComponent(numeroMatriz)}`, {
    method: "DELETE",
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao remover animal do protocolo"); }
}
export async function criarServico(dados: {
  numero_matriz: string; data_servico: string; tipo_servico?: string;
  protocolo?: string; reprodutor?: string; responsavel?: string;
  tipo_semen?: string | null;
  forcar?: boolean;  // ver criarServicoLote
}) {
  const res = await authFetch(`${API}/reproducao/servico`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) throw await erroDaResposta(res, "Erro ao lançar serviço/inseminação");
  return res.json();
}

// ── Parto / nascimento ──
export async function criarParto(dados: {
  numero_matriz: string; data_parto: string; tipo_parto?: string;
  crias: { numero: string; sexo: string; nasceu_viva?: boolean }[];
  retencao_placenta?: boolean; gemelar?: boolean; gemelar_sexo?: string; observacao?: string;
}) {
  const res = await authFetch(`${API}/reproducao/parto`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar parto"); }
  return res.json();
}

export async function fetchRelatorioPesagemCorporal(params?: {
  numero_matriz?: string; grupo?: string; data_inicio?: string; data_fim?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.numero_matriz) qs.set("numero_matriz", params.numero_matriz);
  if (params?.grupo) qs.set("grupo", params.grupo);
  if (params?.data_inicio) qs.set("data_inicio", params.data_inicio);
  if (params?.data_fim) qs.set("data_fim", params.data_fim);
  const res = await authFetch(`${API}/producao/pesagens/relatorio?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório de pesagem error: ${res.status}`);
  return res.json();
}

export async function fetchLancamentos() {
  const res = await authFetch(`${API}/financeiro/lancamentos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Financeiro error: ${res.status}`);
  return res.json();
}

// Só o resultado (receita − despesa) do mês de competência mais recente —
// usado pelo card "Resultado do mês" da Capa. Evita puxar fetchLancamentos()
// (extrato financeiro completo, todo o histórico) só para esse número; ver
// GET /financeiro/resultado-mes-recente.
export type ResultadoMesRecente = { mes: string | null; resultado: number | null };
export async function fetchResultadoMesRecente(): Promise<ResultadoMesRecente> {
  const res = await authFetch(`${API}/financeiro/resultado-mes-recente`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Resultado do mês error: ${res.status}`);
  return res.json();
}

export async function fetchPatrimonioListaSimples(): Promise<{ id: number; nome: string; tipo: string | null }[]> {
  const res = await authFetch(`${API}/financeiro/patrimonio/lista-simples`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Patrimônio error: ${res.status}`);
  return res.json();
}

export async function fetchPatrimonio() {
  const res = await authFetch(`${API}/financeiro/patrimonio`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Patrimônio error: ${res.status}`);
  return res.json();
}

export type PatrimonioPayload = {
  nome: string; tipo?: string | null; numero?: string | null; atividade_cultura?: string | null;
  data_imobilizacao?: string | null; quantidade?: number | null; unidade?: string | null;
  valor_total?: number | null; valor_por_unidade?: boolean; depreciavel?: boolean;
  metodo_depreciacao?: string | null;
  vida_util?: string | null; valor_residual?: number | null; valor_mercado_atual?: number | null;
  atualizacao_valor_mercado_frequencia_meses?: number | null;
  // Onda 2 — vida útil estruturada (substitui o texto livre `vida_util`) e
  // parâmetros dos métodos acelerado / por uso.
  vida_util_anos?: number | null; vida_util_meses?: number | null;
  fator_saldo_decrescente?: number | null;
  unidades_vida_util_total?: number | null; unidades_consumidas?: number | null;
  unidade_uso?: string | null;
};

// --- Onda 2: listas fechadas, código PAT e baixa ----------------------------
export type OpcoesPatrimonio = {
  tipos: string[];
  unidades: string[];
  metodos: { valor: string; rotulo: string; ajuda: string }[];
  motivos_baixa: { valor: string; rotulo: string; tem_valor_venda: boolean }[];
};

export async function fetchOpcoesPatrimonio(): Promise<OpcoesPatrimonio> {
  const res = await authFetch(`${API}/financeiro/patrimonio/opcoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Opções de patrimônio: ${res.status}`);
  return res.json();
}

/** confirmar=false devolve só a prévia (nada é gravado) — report-first. */
export async function gerarCodigosPatrimonio(confirmar = false) {
  const res = await authFetch(`${API}/financeiro/patrimonio/codigos-gerar?confirmar=${confirmar}`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao gerar códigos"); }
  return res.json();
}

export async function baixarPatrimonio(itemId: number, dados: {
  data_baixa: string; motivo: string; valor_recebido?: number | null; observacao?: string | null;
}) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}/baixa`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao baixar o bem"); }
  return res.json();
}

export async function estornarBaixaPatrimonio(itemId: number) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}/estornar-baixa`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao estornar a baixa"); }
  return res.json();
}

// --- Onda 3b: DRE Gerencial em cascata --------------------------------------
export type LinhaDre = {
  chave: string; rotulo: string; operador: string; eh_subtotal: boolean;
  valor: number; contas?: { codigo: string | null; nome: string | null; valor: number }[];
};

export type ContaDre = { codigo: string | null; nome: string | null; valor: number };

export type DreResposta = {
  periodo: { inicio: string; fim: string };
  regime: string; centro_custo: string | null;
  receitas_total: number; despesas_total: number; resultado: number;
  cascata: LinhaDre[];
  nao_classificado: { total: number; contas: ContaDre[] };
  fora_da_dre: { total: number; contas: ContaDre[] };
  depreciacao_periodo: { total: number; inconsistencias: { item: string; numero: string | null; motivo: string }[] };
};

export async function fetchDreCascata(params: {
  data_inicio: string; data_fim: string; regime?: string; centro_custo?: string | null;
}) {
  const q = new URLSearchParams({
    data_inicio: params.data_inicio, data_fim: params.data_fim,
    regime: params.regime || "competencia",
  });
  if (params.centro_custo) q.set("centro_custo", params.centro_custo);
  const res = await authFetch(`${API}/financeiro/dre?${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`DRE: ${res.status}`);
  return res.json() as Promise<DreResposta>;
}

export async function fetchDreConferencia(params: { data_inicio: string; data_fim: string; regime?: string }) {
  const q = new URLSearchParams({
    data_inicio: params.data_inicio, data_fim: params.data_fim,
    regime: params.regime || "competencia",
  });
  const res = await authFetch(`${API}/financeiro/dre/conferencia?${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Conferência da DRE: ${res.status}`);
  return res.json();
}

export async function classificarContaDre(codigo: string, linhaDre: string | null) {
  const res = await authFetch(`${API}/financeiro/plano-contas/${encodeURIComponent(codigo)}/linha-dre`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ linha_dre: linhaDre }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao classificar a conta"); }
  return res.json();
}

// --- Onda 4: Caixa Real ------------------------------------------------------
export type CaixaReal = {
  saldo_inicial: number; saldo_final: number; total_entradas: number; total_saidas: number;
  variacao: number; fundo_reserva: number; folga_minima: number; dias: number;
  primeiro_dia_negativo: string | null; primeiro_dia_abaixo_da_reserva: string | null;
  compromissos_sem_vencimento: number;
  contas: { id: number; nome: string; saldo: number }[];
  serie: {
    data: string; entradas: number; saidas: number; saldo: number;
    itens: { descricao: string | null; valor: number; tipo: string; vencido: boolean; data_original: string }[];
  }[];
};

export async function fetchCaixaReal(dias?: number): Promise<CaixaReal> {
  const q = dias ? `?dias=${dias}` : "";
  const res = await authFetch(`${API}/financeiro/caixa-real${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Caixa Real: ${res.status}`);
  return res.json();
}

export async function fetchFundoReservaSugerido(mesesHistorico = 6) {
  const res = await authFetch(`${API}/financeiro/caixa-real/fundo-reserva-sugerido?meses_historico=${mesesHistorico}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Fundo de reserva sugerido: ${res.status}`);
  return res.json();
}

export async function criarPatrimonio(dados: PatrimonioPayload) {
  const res = await authFetch(`${API}/financeiro/patrimonio`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cadastrar patrimônio"); }
  return res.json();
}

export async function atualizarPatrimonio(itemId: number, dados: PatrimonioPayload) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar patrimônio"); }
  return res.json();
}

export async function atualizarValorMercadoPatrimonio(itemId: number, valorMercadoAtual: number, data?: string) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}/valor-mercado`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ valor_mercado_atual: valorMercadoAtual, data: data || null }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar valor de mercado"); }
  return res.json();
}

export async function vincularLancamentoPatrimonio(numeroLancamento: string, patrimonioId: number | null) {
  const res = await fetchComRetry(() => authFetch(`${API}/financeiro/lancamentos/${encodeURIComponent(numeroLancamento)}/patrimonio`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ patrimonio_id: patrimonioId }),
  }));
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao vincular patrimônio"); }
  return res.json();
}

export async function atualizarPlanoManutencaoPatrimonio(itemId: number, dados: {
  frequencia_manutencao_meses?: number | null; data_ultima_manutencao?: string | null;
  data_proxima_manutencao?: string | null; observacao_manutencao?: string | null;
}) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}/manutencao-plano`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar o plano de manutenção"); }
  return res.json();
}

// ── Cartão de crédito (Controle Financeiro > Cartão de crédito) ────────────
export type CartaoCredito = {
  id: number; apelido: string; bandeira: string | null; banco_emissor: string | null;
  conta_bancaria_id: number | null; dia_fechamento: number; dia_vencimento: number;
  melhor_dia_compra: number; limite: number | null; controla_milhas: boolean;
  milhas_por_real: number | null; ativo: boolean; milhas_totais?: number | null;
};
export type CartaoCreditoPayload = {
  apelido: string; bandeira?: string | null; banco_emissor?: string | null;
  conta_bancaria_id?: number | null; dia_fechamento: number; dia_vencimento: number;
  limite?: number | null; controla_milhas?: boolean; milhas_por_real?: number | null; ativo?: boolean;
};
export type FaturaCartao = {
  id: number; cartao_id: number; competencia: string; data_fechamento: string; data_vencimento: string;
  valor_total: number | null; milhas_acumuladas: number | null; status: "aberta" | "fechada" | "paga";
  numero_lancamento: string | null;
};
export type LancamentoCartao = {
  id: number; cartao_id: number; fatura_id: number; data_compra: string; descricao: string;
  codigo_conta_gerencial: string | null; nome_conta_gerencial: string | null; centro_custo: string | null;
  valor: number; parcela_num: number | null; parcela_total: number | null; observacao: string | null;
};
export type LancamentoCartaoPayload = {
  data_compra: string; descricao: string; codigo_conta_gerencial?: string | null;
  nome_conta_gerencial?: string | null; centro_custo?: string | null; valor: number;
  parcela_num?: number | null; parcela_total?: number | null; observacao?: string | null;
};

export async function fetchCartoesCredito(): Promise<CartaoCredito[]> {
  const res = await authFetch(`${API}/financeiro/cartoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Cartões de crédito error: ${res.status}`);
  return res.json();
}

export async function fetchCartaoCredito(cartaoId: number): Promise<CartaoCredito> {
  const res = await authFetch(`${API}/financeiro/cartoes/${cartaoId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Cartão de crédito error: ${res.status}`);
  return res.json();
}

export async function criarCartaoCredito(dados: CartaoCreditoPayload): Promise<CartaoCredito> {
  const res = await authFetch(`${API}/financeiro/cartoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cadastrar cartão"); }
  return res.json();
}

export async function atualizarCartaoCredito(cartaoId: number, dados: CartaoCreditoPayload): Promise<CartaoCredito> {
  const res = await authFetch(`${API}/financeiro/cartoes/${cartaoId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar cartão"); }
  return res.json();
}

export async function fetchExtratoCartao(cartaoId: number, competencia?: string): Promise<{ cartao: CartaoCredito; fatura: FaturaCartao; lancamentos: LancamentoCartao[] }> {
  const qs = competencia ? `?competencia=${encodeURIComponent(competencia)}` : "";
  const res = await authFetch(`${API}/financeiro/cartoes/${cartaoId}/extrato${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Extrato do cartão error: ${res.status}`);
  return res.json();
}

export async function fetchFaturasCartao(cartaoId: number): Promise<FaturaCartao[]> {
  const res = await authFetch(`${API}/financeiro/cartoes/${cartaoId}/faturas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Faturas do cartão error: ${res.status}`);
  return res.json();
}

export async function criarLancamentoCartao(cartaoId: number, dados: LancamentoCartaoPayload): Promise<LancamentoCartao> {
  const res = await authFetch(`${API}/financeiro/cartoes/${cartaoId}/lancamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar compra no cartão"); }
  return res.json();
}

export async function fecharFaturaCartao(faturaId: number): Promise<FaturaCartao> {
  const res = await authFetch(`${API}/financeiro/cartoes/faturas/${faturaId}/fechar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao fechar fatura"); }
  return res.json();
}

export async function pagarFaturaCartao(faturaId: number, dados: {
  data_pagamento?: string | null; codigo_conta_gerencial?: string | null; nome_conta_gerencial?: string | null; centro_custo?: string | null;
} = {}): Promise<FaturaCartao & { lancamento: any }> {
  const res = await authFetch(`${API}/financeiro/cartoes/faturas/${faturaId}/pagar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao pagar fatura"); }
  return res.json();
}

export async function fetchManutencoesPatrimonio(itemId: number) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}/manutencoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Histórico de manutenção error: ${res.status}`);
  return res.json();
}

export async function registrarManutencaoPatrimonio(itemId: number, dados: {
  data_realizacao: string; descricao?: string | null; fornecedor?: string | null; valor?: number | null;
  centro_custo?: string; status?: string; data_pagamento?: string | null; observacao?: string | null;
  gerar_conta_a_pagar?: boolean;
}) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}/manutencao`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar a manutenção"); }
  return res.json();
}

export async function fetchOpcoesFinanceiro() {
  const res = await authFetch(`${API}/financeiro/opcoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Opções financeiro error: ${res.status}`);
  return res.json();
}

// Coluna de contexto (histórico) do fornecedor/cliente na tela de
// lançamento — em aberto, último lançamento, últimos lançamentos e
// documentos já anexados a alguma nota dele. Só leitura.
export type ContextoFornecedor = {
  em_aberto: number;
  ultimo_lancamento: string | null;
  ultimos_lancamentos: { numero_lancamento: string | null; numero_documento: string | null; data: string | null; valor: number; pago: boolean }[];
  documentos_anexados: { nome_arquivo: string; categoria: string | null; criado_em: string }[];
};
export async function fetchContextoFornecedor(nome: string, tipo: "despesa" | "receita" = "despesa"): Promise<ContextoFornecedor> {
  const res = await authFetch(`${API}/financeiro/contexto-fornecedor?nome=${encodeURIComponent(nome)}&tipo=${tipo}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Contexto do fornecedor error: ${res.status}`);
  return res.json();
}

export async function fetchPlanoContas() {
  const res = await authFetch(`${API}/financeiro/plano-contas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Plano de contas error: ${res.status}`);
  return res.json();
}
type ContaGerencialPayload = {
  codigo: string; nome: string; ativa?: boolean; participa_atividade?: boolean; fluxo?: boolean; tipo_fixo_variavel?: string;
  rmca_receita_leite?: boolean; rmca_custo_alimentacao?: boolean; natureza?: string;
  pede_vinculo_sanitario_reprodutivo?: boolean;
};
export async function criarContaGerencial(dados: ContaGerencialPayload) {
  const res = await authFetch(`${API}/financeiro/plano-contas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar conta gerencial"); }
  return res.json();
}
export async function atualizarContaGerencial(id: number, dados: ContaGerencialPayload) {
  const res = await authFetch(`${API}/financeiro/plano-contas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar conta gerencial"); }
  return res.json();
}

export type CandidatoVinculoSanitarioReprodutivo = {
  tipo: "servico" | "sanidade" | "exame";
  ids: number[];
  rotulo: string;
  data: string | null;
  responsavel: string | null;
};
export async function fetchCandidatosVinculoSanitarioReprodutivo() {
  const res = await authFetch(`${API}/financeiro/candidatos-vinculo-sanitario-reprodutivo`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Candidatos de vínculo error: ${res.status}`);
  return res.json() as Promise<{ servicos: CandidatoVinculoSanitarioReprodutivo[]; vacinas: CandidatoVinculoSanitarioReprodutivo[]; exames: CandidatoVinculoSanitarioReprodutivo[] }>;
}
export async function vincularEventoSanitarioReprodutivo(dados: { tipo: string; ids: number[]; numero_lancamento: string }) {
  const res = await authFetch(`${API}/financeiro/vincular-evento-sanitario-reprodutivo`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao vincular evento"); }
  return res.json();
}
export async function fetchLancamentosPorData(data: string, tipo: "despesa" | "receita" = "despesa") {
  const res = await authFetch(`${API}/financeiro/lancamentos-por-data?data=${data}&tipo=${tipo}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lançamentos por data error: ${res.status}`);
  return res.json() as Promise<{ numero_lancamento: string; fornecedor_cliente: string | null; descricao: string | null; valor_total: number; status: string }[]>;
}

export async function fetchRmca(dataInicio: string, dataFim: string) {
  const res = await authFetch(`${API}/financeiro/rmca?data_inicio=${dataInicio}&data_fim=${dataFim}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`RMCA error: ${res.status}`);
  return res.json();
}

export async function fetchCustoLitroLeite(dataInicio: string, dataFim: string) {
  const res = await authFetch(`${API}/financeiro/custo-litro-leite?data_inicio=${dataInicio}&data_fim=${dataFim}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Custo por litro de leite error: ${res.status}`);
  return res.json();
}

export async function fetchCustoHectare(dataInicio: string, dataFim: string, centroCusto?: string) {
  const qs = new URLSearchParams({ data_inicio: dataInicio, data_fim: dataFim });
  if (centroCusto) qs.set("centro_custo", centroCusto);
  const res = await authFetch(`${API}/financeiro/custo-hectare?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Custo por hectare error: ${res.status}`);
  return res.json();
}

export async function fetchCustoVacaLote(dataInicio: string, dataFim: string, centroCusto?: string) {
  const qs = new URLSearchParams({ data_inicio: dataInicio, data_fim: dataFim });
  if (centroCusto) qs.set("centro_custo", centroCusto);
  const res = await authFetch(`${API}/financeiro/custo-vaca-lote?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Custo por vaca/lote error: ${res.status}`);
  return res.json();
}

export async function fetchCustoSafra(safraId: number) {
  const res = await authFetch(`${API}/financeiro/custo-safra?safra_id=${safraId}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Custo por safra error: ${res.status}`); }
  return res.json();
}

// ── Contas correntes (Configurações > Parâmetros financeiros) ──
// Traz id + rótulo legível de cada conta — usado sempre que o formulário
// precisa gravar o vínculo com a conta (conta_corrente_id), e não só exibir
// o texto (diferente de `fetchOpcoesFinanceiro().contas_bancarias`, que só
// devolve rótulos em texto, sem id).
export type ContaCorrenteCadastro = {
  id: number; banco: string; agencia: string; numero_conta: string; ativo: boolean; rotulo: string;
  // Saldo calculado ("entradas − saídas"), não persistido — ver
  // calcular_saldos_contas_correntes no backend. Soma lançamentos pagos
  // vinculados à conta + transferências entre contas.
  saldo: number;
};
export async function fetchContasCorrentes(): Promise<ContaCorrenteCadastro[]> {
  const res = await authFetch(`${API}/financeiro/contas-correntes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Contas correntes error: ${res.status}`);
  return res.json();
}
export async function criarContaCorrente(dados: { banco: string; agencia: string; numero_conta: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/financeiro/contas-correntes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar conta corrente"); }
  return res.json();
}
export async function atualizarContaCorrente(id: number, dados: { banco: string; agencia: string; numero_conta: string; ativo: boolean }) {
  const res = await authFetch(`${API}/financeiro/contas-correntes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar conta corrente"); }
  return res.json();
}

// Transferência entre contas correntes — não é despesa nem receita da
// fazenda (dinheiro sai de uma conta própria e entra em outra), por isso
// fica fora do DRE/relatórios gerenciais; só ajusta o saldo calculado das
// duas contas (ver TransferenciaContas no backend).
export type TransferenciaContas = {
  id: number; conta_origem_id: number; conta_destino_id: number; valor: number; data: string;
  observacao: string | null; criado_em: string; usuario_id: number | null;
};
export async function fetchTransferenciasContas(): Promise<TransferenciaContas[]> {
  const res = await authFetch(`${API}/financeiro/contas-correntes/transferencias`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Transferências entre contas error: ${res.status}`);
  return res.json();
}
export async function criarTransferenciaContas(dados: {
  conta_origem_id: number; conta_destino_id: number; valor: number; data: string; observacao?: string;
}) {
  const res = await authFetch(`${API}/financeiro/contas-correntes/transferencias`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao transferir entre contas"); }
  return res.json();
}

// ── Centros de custo (Configurações > Parâmetros financeiros) ──
// `padrao`: usado automaticamente no Lançamento simplificado (Lançamentos >
// Financeiro) — no máximo 1 marcado por fazenda (ver ParametrosFinanceiros.tsx
// e components/FormFinanceiroSimplificado.tsx).
export type CentroCustoCadastro = { id: number; nome: string; ativo: boolean; padrao: boolean };
export async function fetchCentrosCusto(): Promise<CentroCustoCadastro[]> {
  const res = await authFetch(`${API}/financeiro/centros-custo`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Centros de custo error: ${res.status}`);
  return res.json();
}
export async function criarCentroCusto(dados: { nome: string; ativo?: boolean; padrao?: boolean }) {
  const res = await authFetch(`${API}/financeiro/centros-custo`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar centro de custo"); }
  return res.json();
}
export async function atualizarCentroCusto(id: number, dados: { nome: string; ativo: boolean; padrao?: boolean }) {
  const res = await authFetch(`${API}/financeiro/centros-custo/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar centro de custo"); }
  return res.json();
}

// ── Tipos de documento (Configurações > Parâmetros financeiros) ──
export async function fetchTiposDocumentoCadastro() {
  const res = await authFetch(`${API}/financeiro/tipos-documento`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Tipos de documento error: ${res.status}`);
  return res.json();
}
export async function criarTipoDocumento(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/financeiro/tipos-documento`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar tipo de documento"); }
  return res.json();
}
export async function atualizarTipoDocumento(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/financeiro/tipos-documento/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar tipo de documento"); }
  return res.json();
}

// ── Formas de pagamento (Configurações > Parâmetros financeiros) ──
export async function fetchFormasPagamentoCadastro() {
  const res = await authFetch(`${API}/financeiro/formas-pagamento-cadastro`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Formas de pagamento error: ${res.status}`);
  return res.json();
}
export async function criarFormaPagamentoCadastro(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/financeiro/formas-pagamento-cadastro`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar forma de pagamento"); }
  return res.json();
}
export async function atualizarFormaPagamentoCadastro(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/financeiro/formas-pagamento-cadastro/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar forma de pagamento"); }
  return res.json();
}

// ── Classificações de lançamento (Configurações > Parâmetros financeiros) ──
// Ex.: Medicamentos, Ração, Manutenção — selecionável ao lançar conta a
// pagar/receber, cadastrável na hora (ver FormFinanceiro/FormEditarLancamento).
export async function fetchClassificacoesCadastro() {
  const res = await authFetch(`${API}/financeiro/classificacoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Classificações error: ${res.status}`);
  return res.json();
}
export async function criarClassificacao(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/financeiro/classificacoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar classificação"); }
  return res.json();
}
export async function atualizarClassificacao(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/financeiro/classificacoes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar classificação"); }
  return res.json();
}

export async function criarLancamentoFinanceiro(dados: any) {
  // Mesma chave em todas as tentativas: se uma delas chegou a gravar no
  // servidor mas a resposta se perdeu no caminho de volta (o "Failed to
  // fetch" que aparece com o lançamento já salvo — relato real de usuário em
  // conexão rural instável), o backend reconhece a chave repetida e devolve
  // o mesmo lançamento em vez de duplicar (ver Idempotency-Key). Uma única
  // retentativa IMEDIATA cai no mesmo blackout de poucos segundos que
  // derrubou a 1ª — até 2 retentativas, com uma pequena pausa entre elas,
  // dão tempo da conexão se recuperar antes de desistir e mostrar erro pro
  // usuário como se nada tivesse sido salvo.
  const chave = gerarChaveIdempotencia();
  const post = () => authFetch(`${API}/financeiro/lancamentos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": chave },
    body: JSON.stringify(dados),
  });
  let res: Response | undefined;
  let ultimoErro: unknown;
  for (let tentativa = 0; tentativa < 3; tentativa++) {
    try {
      res = await post();
      break;
    } catch (e) {
      if (!(e instanceof TypeError)) throw netError(e);
      ultimoErro = e;
      if (tentativa < 2) await new Promise((r) => setTimeout(r, 600 * (tentativa + 1)));
    }
  }
  if (!res) throw netError(ultimoErro);
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    // Preserva `detail`/`status` (padrão `criarVale`) — o 409 de "estourou 40%
    // do salário" de um item marcado como vale (ver ValeItemModal) precisa do
    // `detail.competencias_excedidas` estruturado, não só de uma string solta.
    const err: any = new Error(mensagemErroApi(d.detail) || (typeof d.detail === "object" ? d.detail?.mensagem : null) || "Erro ao criar lançamento");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// ── Vale a partir de um item de lançamento financeiro (checkbox "É vale de
// funcionário?" na linha do item, ver ValeItemModal/FormFinanceiro) ──
export type ValeItemOrigem = {
  origem_tipo: "empreitada" | "contrato" | "diaria"; origem_id: number;
  label: string; saldo_pendente: number | null; itens_pendentes: number | null;
};
export type ValeItemOpcoes = {
  pessoa_id: number; pessoa_nome: string; tipos: string[];
  folha: { disponivel: boolean; motivo: string | null; salario_base: number | null; limite_por_competencia: number | null };
  origens: ValeItemOrigem[];
  sugestao: { modo: "folha" | "avulso"; origem_tipo?: string | null; origem_id?: number | null } | null;
  bloqueio: string | null;
};
export type ValeItemIn = {
  pessoa_id: number;
  modo: "folha" | "avulso";
  // Quanto DO ITEM é vale: "integral" (o item inteiro, comportamento de
  // sempre) ou "parcial" — e aí exatamente um entre `percentual` e `valor`.
  // O caso do dono: 2/3 da ração de cachorro são do funcionário, 1/3 é dele;
  // a sobra vira despesa normal da fazenda, na mesma conta gerencial e no
  // mesmo centro de custo (o backend divide o item em duas linhas).
  abrangencia?: "integral" | "parcial";
  percentual?: number | null;
  valor?: number | null;
  parcelas?: number;
  competencia_inicio?: string | null;
  origem_tipo?: "empreitada" | "contrato" | "diaria" | null;
  origem_id?: number | null;
  observacao?: string | null;
  confirmar?: boolean;
};
export type ValeItemResultado = {
  item_id: number; numero_lancamento: string; vale_tipo: "funcionario" | "avulso";
  vale_id: number; valor: number; data_pagamento: string;
  // Preenchido só no vale parcial: a linha gêmea que ficou com a fazenda.
  parte_fazenda: { item_id: number; valor: number; quantidade: number | null } | null;
  pessoa_id: number; pessoa_nome: string; resumo: string;
};

export async function fetchOpcoesValeItem(pessoaId: number): Promise<ValeItemOpcoes> {
  const res = await authFetch(`${API}/cadastro/vale-item/opcoes?pessoa_id=${pessoaId}`, { cache: "no-store" });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(mensagemErroApi(d.detail) || "Erro ao buscar opções de vale");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function marcarItemComoVale(itemId: number, dados: ValeItemIn): Promise<ValeItemResultado> {
  // Mesma chave em todas as tentativas — sem isto, uma resposta perdida no
  // caminho de volta faria a 2ª tentativa bater no 409 "item já gerou um
  // vale" mesmo com o vale já criado com sucesso na 1ª (ver Idempotency-Key).
  const chave = gerarChaveIdempotencia();
  const res = await fetchComRetry(() => authFetch(`${API}/cadastro/vale-item/${itemId}`, {
    method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": chave }, body: JSON.stringify(dados),
  }));
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    // Preserva `detail`/`status` (mesmo padrão de `criarVale`) — o 409 de
    // "item já gerou um vale" e o 409 de "estourou 40% do salário" chegam
    // com `detail` estruturado (objeto), não só uma string.
    const err: any = new Error(typeof d.detail === "string" ? d.detail : d.detail?.mensagem || "Erro ao marcar item como vale");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function desmarcarItemComoVale(itemId: number, excluirVale: boolean) {
  const res = await fetchComRetry(() => authFetch(`${API}/cadastro/vale-item/${itemId}?excluir_vale=${excluirVale ? "true" : "false"}`, { method: "DELETE" }));
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(typeof d.detail === "string" ? d.detail : d.detail?.mensagem || "Erro ao desmarcar vale");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// ── Lançamentos recorrentes (Financeiro > Ações > Lançamentos recorrentes) ──
// Modelo com os dados FIXOS de uma conta que se repete todo período (energia,
// internet, telefone, assinatura, aluguel) — "gerar" cria um LancamentoFinanceiro
// de verdade, só com os dados variáveis daquele período (ver FormFinanceiro para
// o lançamento manual completo; aqui é o atalho a partir do modelo cadastrado).
export type LancamentoRecorrente = {
  id: number;
  descricao: string;
  tipo: "receita" | "despesa";
  fornecedor_cliente: string | null;
  centro_custo: string | null;
  codigo_conta_gerencial: string | null;
  nome_conta_gerencial: string | null;
  tipo_item: "produto" | "servico" | null;
  responsavel_padrao: string | null;
  tipo_documento_padrao: string | null;
  forma_pagamento_padrao: string | null;
  conta_bancaria_padrao: string | null;
  dia_vencimento: number | null;
  periodicidade: string;
  observacao: string | null;
  ativo: boolean;
  ultimo_numero_lancamento: string | null;
  ultima_geracao_em: string | null;
};
export type LancamentoRecorrentePayload = {
  descricao: string; tipo: "receita" | "despesa";
  fornecedor_cliente?: string | null; centro_custo?: string | null;
  codigo_conta_gerencial?: string | null; nome_conta_gerencial?: string | null;
  tipo_item?: "produto" | "servico" | null;
  responsavel_padrao?: string | null; tipo_documento_padrao?: string | null;
  forma_pagamento_padrao?: string | null; conta_bancaria_padrao?: string | null;
  dia_vencimento?: number | null; periodicidade?: string; observacao?: string | null; ativo?: boolean;
};
export async function fetchLancamentosRecorrentes(): Promise<LancamentoRecorrente[]> {
  const res = await authFetch(`${API}/financeiro/recorrentes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lançamentos recorrentes error: ${res.status}`);
  return res.json();
}
export async function criarLancamentoRecorrente(dados: LancamentoRecorrentePayload) {
  const res = await authFetch(`${API}/financeiro/recorrentes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar lançamento recorrente"); }
  return res.json();
}
export async function atualizarLancamentoRecorrente(id: number, dados: LancamentoRecorrentePayload) {
  const res = await authFetch(`${API}/financeiro/recorrentes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar lançamento recorrente"); }
  return res.json();
}
export type GerarLancamentoRecorrentePayload = {
  valor: number;
  data_emissao?: string | null;
  data_vencimento?: string | null;
  numero_boleto?: string | null;
  numero_documento?: string | null;
  observacao?: string | null;
  ja_pago?: boolean;
  data_pagamento?: string | null;
  valor_pago?: number | null;
  conta_bancaria?: string | null;
  forma_pagamento?: string | null;
  numero_documento_pagamento?: string | null;
};
export async function gerarLancamentoRecorrente(modeloId: number, dados: GerarLancamentoRecorrentePayload) {
  const res = await authFetch(`${API}/financeiro/recorrentes/${modeloId}/gerar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao gerar o lançamento"); }
  return res.json();
}

export async function marcarPagoFinanceiro(id: number, dados: {
  data_pagamento: string; valor_pago: number; conta_bancaria?: string; numero_documento_pagamento?: string;
  forma_pagamento?: string; data_vencimento_cartao?: string;
  // Diferença entre valor_pago e o valor do lançamento dividida em novas
  // parcelas do mesmo lançamento, em vez de virar desconto/acréscimo — ver
  // PUT /financeiro/lancamentos/{id}/pagar.
  parcelas_diferenca?: { data_vencimento: string; valor: number }[];
}) {
  // Mesma chave em todas as tentativas: se uma delas chegou a gravar a baixa
  // no servidor mas a resposta se perdeu no caminho de volta (o "Failed to
  // fetch" que aparece em "Ações > Pagamento" com o lançamento já baixado —
  // conexão rural instável costuma cair bem no meio do PUT), o middleware de
  // idempotência (main.py::_idempotencia) reconhece a chave repetida e
  // devolve a mesma resposta em vez de baixar de novo. Mesmo padrão de
  // criarLancamentoFinanceiro, acima.
  const chave = gerarChaveIdempotencia();
  const res = await fetchComRetry(() => authFetch(`${API}/financeiro/lancamentos/${id}/pagar`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", "Idempotency-Key": chave },
    body: JSON.stringify(dados),
  }));
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao dar baixa"); }
  return res.json();
}

export async function criarBaixaLote(dados: {
  lancamento_ids: number[]; data_pagamento: string; conta_bancaria?: string;
  forma_pagamento?: string; data_vencimento_cartao?: string; numero_documento_pagamento?: string;
}) {
  // Mesma chave em todas as tentativas — mesmo padrão de marcarPagoFinanceiro
  // (a versão individual desta mesma operação), que já tinha essa proteção.
  const chave = gerarChaveIdempotencia();
  const res = await fetchComRetry(() => authFetch(`${API}/financeiro/lancamentos/baixa-lote`, {
    method: "PUT", headers: { "Content-Type": "application/json", "Idempotency-Key": chave }, body: JSON.stringify(dados),
  }));
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao dar baixa em lote"); }
  return res.json();
}

// Baixa em lote com pagamento diferente por nota (data/valor/conta/forma por linha).
export type BaixaLoteItem = {
  lancamento_id: number; data_pagamento: string; valor_pago: number;
  conta_bancaria?: string; forma_pagamento?: string; data_vencimento_cartao?: string; numero_documento_pagamento?: string;
  // Mesmo mecanismo/formato de marcarPagoFinanceiro (baixa individual): sem
  // isto, a diferença entre valor_pago e o valor da nota vira
  // desconto_acrescimo, perdoada/cobrada de uma vez (comportamento de
  // sempre). Preenchido, a diferença migra inteira para nova(s) parcela(s)
  // do mesmo lançamento — ver PUT /financeiro/lancamentos/baixa-lote-detalhada.
  parcelas_diferenca?: { data_vencimento: string; valor: number }[];
};
export async function criarBaixaLoteDetalhada(itens: BaixaLoteItem[]) {
  const chave = gerarChaveIdempotencia();
  const res = await fetchComRetry(() => authFetch(`${API}/financeiro/lancamentos/baixa-lote-detalhada`, {
    method: "PUT", headers: { "Content-Type": "application/json", "Idempotency-Key": chave }, body: JSON.stringify({ itens }),
  }));
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao dar baixa em lote"); }
  return res.json();
}

export async function atualizarLancamentoFinanceiro(id: number, dados: {
  descricao?: string | null; codigo_conta?: string | null; centro_custo?: string | null; classificacao?: string | null;
  fornecedor_cliente?: string | null; numero_nota?: string | null; numero_documento_pagamento?: string | null; tipo_documento?: string | null;
  numero_os_orcamento?: string | null; numero_boleto?: string | null;
  data_emissao?: string | null; data_vencimento?: string | null; data_competencia?: string | null;
  data_prevista_entrada?: string | null; data_pedido?: string | null;
  quantidade?: number | null; valor_unitario?: number | null; valor_total?: number | null;
  desconto_acrescimo?: number | null; responsavel?: string | null; produto?: string | null;
}) {
  // Sem retentativa nenhuma até aqui — era a única gravação de Financeiro
  // que mostrava "Sem conexão com a API" (netError) numa queda momentânea de
  // conexão mesmo quando o PUT tinha ido e voltado direitinho no navegador
  // (relato de 04/09/2026: "quando salvo lançamentos financeiros, sempre dá
  // esse aviso, mas continua salvando"). PUT substitui os mesmos campos
  // sempre — repetir não duplica nada, então não precisa de Idempotency-Key.
  const res = await fetchComRetry(() => authFetch(`${API}/financeiro/lancamentos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  }));
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar o lançamento"); }
  return res.json();
}

// Associa/renomeia o produto/serviço de UM item já lançado (LancamentoItem)
// para um nome do catálogo — "associar a produto já existente" e o passo
// seguinte a "cadastrar produto novo" na tela de edição (ver
// FormEditarLancamento). Quando o item é um produto de estoque com
// quantidade > 0 e ainda sem entrada registrada, o backend também dá baixa
// (entrada) retroativa — ver PUT /financeiro/itens/{id}/vincular-produto.
export async function vincularProdutoItem(itemId: number, produto: string) {
  const chave = gerarChaveIdempotencia();
  const res = await fetchComRetry(() => authFetch(`${API}/financeiro/itens/${itemId}/vincular-produto`, {
    method: "PUT", headers: { "Content-Type": "application/json", "Idempotency-Key": chave }, body: JSON.stringify({ produto }),
  }));
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao associar o produto/serviço"); }
  return res.json() as Promise<{ id: number; produto: string; avisos_estoque: string[] }>;
}

// G2 — reverte a baixa (o lançamento volta para "em aberto"); não exclui o
// lançamento. Se a baixa criou parcela(s) para cobrir a diferença de valor
// pago (ver marcarPagoFinanceiro/parcelas_diferenca), a API responde 409 com
// `detail = {mensagem, parcelas}` — reenviar com `confirmar_parcelas_diferenca: true`
// para apagar essas parcelas e restaurar `parcela_total` das remanescentes.
export type EstornoLancamentoIn = { motivo?: string | null; confirmar_parcelas_diferenca?: boolean };
export type EstornoLancamentoOut = Record<string, any> & {
  estornado: true; parcelas_diferenca_removidas: number; avisos: string[];
};
export async function estornarPagamentoLancamento(id: number, dados: EstornoLancamentoIn = {}): Promise<EstornoLancamentoOut> {
  const chave = gerarChaveIdempotencia();
  const res = await fetchComRetry(() => authFetch(`${API}/financeiro/lancamentos/${id}/estornar`, {
    method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": chave }, body: JSON.stringify(dados),
  }));
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    const err: any = new Error(typeof d.detail === "string" ? d.detail : d.detail?.mensagem || "Erro ao estornar pagamento");
    err.detail = d.detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// Sugestão de casamento entre o texto vindo da nota/documento e o cadastro
// existente (fornecedor, produto de estoque ou serviço) — só aparece quando
// há semelhança mas não certeza (confiança "provavel"; ver
// backend/fazenda/rules/sugestao_documento.py). Devolvida junto do resultado
// de importarXmlFinanceiro/lerDocumentoFinanceiro, dentro de `sugestoes_cadastro`.
export type SugestaoCadastroItem = {
  texto: string; candidato: string; score: number; confianca: "provavel";
  tipo?: "produto" | "servico"; indice?: number;
};
// fornecedor_confianca vai sempre (não só quando há sugestão) — "exato" não
// precisa de nada (já bate sozinho), "provavel"/"incerto" são os dois casos
// em que o texto bruto da nota não é, ele mesmo, um nome já cadastrado —
// gatilho pra oferecer "salvar como apelido padrão" (ver
// criarFornecedorApelido) quando o usuário corrige/confirma o fornecedor.
export type SugestoesCadastro = {
  fornecedor: SugestaoCadastroItem | null;
  fornecedor_confianca: "exato" | "provavel" | "incerto" | null;
  itens: SugestaoCadastroItem[];
};

// Ensina o sistema a reconhecer um nome de fornecedor/cliente como aparece
// BRUTO num documento (razão social completa da nota) como um nome já
// cadastrado — usado quando fornecedor_confianca acima não é "exato". Por
// fazenda (nunca cruza tenants). Chamar de novo com o mesmo nomeBruto
// ATUALIZA o apelido em vez de duplicar.
export async function criarFornecedorApelido(nomeBruto: string, nomeCanonico: string) {
  const res = await authFetch(`${API}/financeiro/fornecedor-apelidos`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nome_bruto: nomeBruto, nome_canonico: nomeCanonico }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar apelido de fornecedor"); }
  return res.json();
}

export async function importarXmlFinanceiro(xml: string) {
  let res: Response;
  try {
    res = await authFetch(`${API}/financeiro/importar-xml`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ xml }),
    });
  } catch (e) {
    throw netErrorProcessamento(e, "do XML"); // "Failed to fetch" cru vira uma mensagem acionável, sem alarme falso de "backend fora do ar".
  }
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao ler o XML"); }
  return res.json();
}

// Leitura automática (OCR) de PDF/JPEG/PNG — pode demorar bastante num
// documento com várias páginas (ver comentário em run_in_threadpool no
// backend); se a conexão cair no meio (proxy/gateway derrubando por
// demora, Wi-Fi instável etc.), `fetch` lança um TypeError cru ("Failed to
// fetch") — sem o try/catch abaixo, essa falha de REDE ficava indistinguível
// de qualquer outro erro de NEGÓCIO (documento ilegível, tipo não
// suportado...) pro usuário, que via só o texto bruto do navegador.
// `netErrorProcessamento` traduz isso numa mensagem clara sem o alarme falso
// de "backend fora do ar/CORS" do netError genérico — aqui a causa típica é
// só o gateway cortando por demora, não a API estar de fato indisponível.
export async function lerDocumentoFinanceiro(file: File) {
  const form = new FormData();
  form.append("file", file);
  let res: Response;
  try {
    res = await authFetch(`${API}/financeiro/ler-documento`, { method: "POST", body: form });
  } catch (e) {
    throw netErrorProcessamento(e, "do documento");
  }
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao ler o documento"); }
  return res.json();
}

// Anexos do lançamento (ex.: boleto de um parcelamento) — o lançamento já
// precisa existir (numero_lancamento vem do retorno de criarLancamentoFinanceiro).
// numero_documento/data_documento: o número/data impressos no PRÓPRIO
// documento (nº da nota, do boleto, da OS, do orçamento...) — é por eles que
// a Central de Documentos acha um documento específico dentro de um
// lançamento que reúne vários (ver app/documentos-central/page.tsx).
export type AnexoLancamento = {
  id: number; nome_arquivo: string; mime_type: string; tamanho_bytes: number; categoria?: string | null;
  numero_documento?: string | null; data_documento?: string | null; criado_em?: string;
};

export async function anexarArquivoLancamento(
  numeroLancamento: string, file: File, categoria?: string | null,
  numeroDocumento?: string | null, dataDocumento?: string | null,
): Promise<AnexoLancamento> {
  // Mesma chave nas duas tentativas: upload de foto/comprovante é o request
  // mais exposto a "Failed to fetch" com sucesso no servidor (arquivo maior,
  // conexão rural instável derruba no meio da volta da resposta) — mesmo
  // padrão de criarLancamentoFinanceiro/marcarPagoFinanceiro, acima. A key
  // vai por fora do FormData (o middleware de idempotência só olha o header).
  const chave = gerarChaveIdempotencia();
  const enviar = () => {
    const form = new FormData();
    form.append("file", file);
    if (categoria) form.append("categoria", categoria);
    if (numeroDocumento) form.append("numero_documento", numeroDocumento);
    if (dataDocumento) form.append("data_documento", dataDocumento);
    return authFetch(`${API}/financeiro/lancamentos/${encodeURIComponent(numeroLancamento)}/anexos`, {
      method: "POST", headers: { "Idempotency-Key": chave }, body: form,
    });
  };
  let res: Response;
  try {
    res = await enviar();
  } catch (e) {
    if (!(e instanceof TypeError)) throw netError(e);
    res = await enviar().catch((e2) => { throw netError(e2); }); // 1 nova tentativa, mesma chave
  }
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao anexar o arquivo"); }
  return res.json();
}

export async function listarAnexosLancamento(numeroLancamento: string): Promise<AnexoLancamento[]> {
  const res = await authFetch(`${API}/financeiro/lancamentos/${encodeURIComponent(numeroLancamento)}/anexos`);
  if (!res.ok) throw new Error("Erro ao listar anexos");
  return res.json();
}

// Mesmas duas operações, ancoradas no id do lançamento. Necessário porque
// lançamento importado da planilha nasce sem `numero_lancamento`, e sem ele
// não havia como anexar comprovante nenhum — o backend emite a numeração na
// primeira anexação (ver _garantir_numero_lancamento).
export async function anexarArquivoLancamentoPorId(
  lancamentoId: number, file: File, categoria?: string | null,
  numeroDocumento?: string | null, dataDocumento?: string | null,
): Promise<AnexoLancamento> {
  // Usado pelo comprovante em "Ações > Pagamento" (PagamentoIndividualView) —
  // mesma chave nas duas tentativas, mesmo motivo de anexarArquivoLancamento
  // acima: foto de comprovante em conexão rural instável é o caso mais
  // exposto a "Failed to fetch" com o upload já salvo no servidor.
  const chave = gerarChaveIdempotencia();
  const enviar = () => {
    const form = new FormData();
    form.append("file", file);
    if (categoria) form.append("categoria", categoria);
    if (numeroDocumento) form.append("numero_documento", numeroDocumento);
    if (dataDocumento) form.append("data_documento", dataDocumento);
    return authFetch(`${API}/financeiro/lancamentos/por-id/${lancamentoId}/anexos`, {
      method: "POST", headers: { "Idempotency-Key": chave }, body: form,
    });
  };
  let res: Response;
  try {
    res = await enviar();
  } catch (e) {
    if (!(e instanceof TypeError)) throw netError(e);
    res = await enviar().catch((e2) => { throw netError(e2); }); // 1 nova tentativa, mesma chave
  }
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao anexar o arquivo"); }
  return res.json();
}

// Um ou mais comprovantes para vários lançamentos pagos na mesma remessa
// (Financeiro > Pagamento em lote) — o banco às vezes emite mais de um
// recibo para a mesma remessa (o PDF da remessa inteira + o comprovante de
// uma linha, por exemplo). Cada arquivo sobe uma vez só e o backend cria o
// vínculo com cada lançamento, para que todos exibam os comprovantes no
// relatório de Contas pagas — ver anexar_comprovante_em_lote no backend.
export async function anexarComprovanteEmLote(
  lancamentoIds: number[], files: File[], categoria?: string | null,
): Promise<{ anexados: number; arquivos: string[]; nome_arquivo: string | null; anexo_ids: number[]; numeros_lancamento: string[] }> {
  // Mesma chave em todas as tentativas — mesmo padrão de anexarArquivoLancamento:
  // upload de comprovante é o request mais exposto a "Failed to fetch" com o
  // arquivo já salvo (conexão rural instável, arquivo maior demora mais).
  const chave = gerarChaveIdempotencia();
  const enviar = () => {
    const form = new FormData();
    files.forEach((f) => form.append("file", f));
    form.append("lancamento_ids", lancamentoIds.join(","));
    if (categoria) form.append("categoria", categoria);
    return authFetch(`${API}/financeiro/lancamentos/anexos-lote`, {
      method: "POST", headers: { "Idempotency-Key": chave }, body: form,
    });
  };
  const res = await fetchComRetry(enviar);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao anexar o comprovante do lote"); }
  return res.json();
}

export async function listarAnexosLancamentoPorId(lancamentoId: number): Promise<AnexoLancamento[]> {
  const res = await authFetch(`${API}/financeiro/lancamentos/por-id/${lancamentoId}/anexos`);
  if (!res.ok) throw new Error("Erro ao listar anexos");
  return res.json();
}

export function urlAnexoLancamento(anexoId: number): string {
  return `${API}/financeiro/anexos/${anexoId}`;
}

// Central de Documentos (Administração) — busca unificada sobre o arquivo
// fiscal-contábil (só admin) e os anexos de lançamento (só quem tem o
// módulo financeiro); o backend decide o que cada usuário vê (ver
// central_documentos.py) — o frontend só mostra o que voltou.
export type LinhaCentralDocumento = {
  origem: "fiscal" | "financeiro"; id: number; categoria: string | null; nome_arquivo: string;
  numero_documento: string | null; data_documento: string | null; criado_em: string;
  numero_lancamento: string | null; fornecedor_cliente: string | null; descricao: string | null; url: string;
};

export async function fetchCentralDocumentos(filtros?: {
  categoria?: string; numero_documento?: string; data_de?: string; data_ate?: string;
}): Promise<LinhaCentralDocumento[]> {
  const params = new URLSearchParams();
  if (filtros?.categoria) params.set("categoria", filtros.categoria);
  if (filtros?.numero_documento) params.set("numero_documento", filtros.numero_documento);
  if (filtros?.data_de) params.set("data_de", filtros.data_de);
  if (filtros?.data_ate) params.set("data_ate", filtros.data_ate);
  const qs = params.toString();
  const res = await authFetch(`${API}/documentos-central${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error("Erro ao buscar documentos");
  return res.json();
}

// Abre o documento (fiscal ou financeiro) numa aba nova — o `url` já vem
// pronto na linha da Central de Documentos, só falta a base da API e o
// mesmo mecanismo autenticado usado no resto do site.
export function abrirLinhaCentralDocumento(linha: LinhaCentralDocumento): string {
  return `${API}${linha.url}`;
}

export async function fetchDestinatarioRecibo(numeroLancamento: string): Promise<{ nome: string | null; email: string | null }> {
  const res = await authFetch(`${API}/financeiro/lancamentos/${encodeURIComponent(numeroLancamento)}/destinatario-recibo`);
  if (!res.ok) return { nome: null, email: null };
  return res.json();
}

export async function enviarReciboEmail(numeroLancamento: string, destinatario: string, arquivo: Blob): Promise<void> {
  const form = new FormData();
  form.append("destinatario", destinatario);
  form.append("arquivo", arquivo, `recibo_${numeroLancamento}.pdf`);
  const res = await authFetch(`${API}/financeiro/lancamentos/${encodeURIComponent(numeroLancamento)}/recibo/enviar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao enviar o recibo por e-mail"); }
}

export async function excluirAnexoLancamento(anexoId: number) {
  const res = await authFetch(`${API}/financeiro/anexos/${anexoId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir anexo"); }
  return res.json();
}

export type LancamentoParecido = {
  id: number; numero_lancamento: string | null; tipo: string; fornecedor_cliente: string | null;
  valor_total: number | null; numero_documento: string | null; data_emissao: string | null;
  data_competencia: string | null; centro_custo: string | null; origem: string | null;
};
export async function fetchPossiveisDuplicados(params: {
  tipo: string; valor_total: number; fornecedor_cliente?: string; data_emissao?: string;
}): Promise<LancamentoParecido[]> {
  const qs = new URLSearchParams({ tipo: params.tipo, valor_total: String(params.valor_total) });
  if (params.fornecedor_cliente) qs.set("fornecedor_cliente", params.fornecedor_cliente);
  if (params.data_emissao) qs.set("data_emissao", params.data_emissao);
  const res = await authFetch(`${API}/financeiro/possiveis-duplicados?${qs}`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchDRE(params: {
  data_inicio: string;
  data_fim: string;
  regime?: string;
  centro_custo?: string;
}) {
  const qs = new URLSearchParams({
    data_inicio: params.data_inicio,
    data_fim: params.data_fim,
    regime: params.regime || "competencia",
  });
  if (params.centro_custo) qs.set("centro_custo", params.centro_custo);
  const res = await authFetch(`${API}/financeiro/dre?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`DRE error: ${res.status}`);
  return res.json();
}

// ── Planejamento (Financeiro > Planejamento: Orçamento + Planejamento financeiro) ──
export type OrcamentoItemPayload = {
  ano: number; mes: number; codigo_conta_gerencial: string; centro_custo?: string | null;
  tipo: "receita" | "despesa"; valor_orcado: number; observacao?: string | null;
};
export async function fetchOrcamento(ano?: number) {
  const qs = ano ? `?ano=${ano}` : "";
  const res = await authFetch(`${API}/planejamento/orcamento${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Orçamento error: ${res.status}`);
  return res.json();
}
export async function criarItemOrcamento(dados: OrcamentoItemPayload) {
  const res = await authFetch(`${API}/planejamento/orcamento`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar item de orçamento"); }
  return res.json();
}
export async function atualizarItemOrcamento(id: number, dados: OrcamentoItemPayload) {
  const res = await authFetch(`${API}/planejamento/orcamento/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar item de orçamento"); }
  return res.json();
}
export async function excluirItemOrcamento(id: number) {
  const res = await authFetch(`${API}/planejamento/orcamento/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir item de orçamento"); }
}
export async function fetchComparativoOrcado(params: { ano: number; mes_inicio?: number; mes_fim?: number; centro_custo?: string }) {
  const qs = new URLSearchParams({ ano: String(params.ano) });
  if (params.mes_inicio) qs.set("mes_inicio", String(params.mes_inicio));
  if (params.mes_fim) qs.set("mes_fim", String(params.mes_fim));
  if (params.centro_custo) qs.set("centro_custo", params.centro_custo);
  const res = await authFetch(`${API}/planejamento/orcamento/comparativo?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Comparativo orçado x realizado error: ${res.status}`);
  return res.json();
}

export type CenarioPayload = { nome: string; tipo?: "otimista" | "realista" | "pessimista" | "personalizado"; observacao?: string | null };
export async function fetchCenarios() {
  const res = await authFetch(`${API}/planejamento/cenarios`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Cenários error: ${res.status}`);
  return res.json();
}
export async function criarCenario(dados: CenarioPayload) {
  const res = await authFetch(`${API}/planejamento/cenarios`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar cenário"); }
  return res.json();
}
export async function atualizarCenario(id: number, dados: CenarioPayload) {
  const res = await authFetch(`${API}/planejamento/cenarios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar cenário"); }
  return res.json();
}
export async function excluirCenario(id: number) {
  const res = await authFetch(`${API}/planejamento/cenarios/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir cenário"); }
}

export type PlanejamentoItemPayload = {
  mes_competencia: string; codigo_conta_gerencial: string; centro_custo?: string | null;
  tipo: "receita" | "despesa"; valor_previsto: number; observacao?: string | null;
};
export async function fetchItensCenario(cenarioId: number) {
  const res = await authFetch(`${API}/planejamento/cenarios/${cenarioId}/itens`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Itens do cenário error: ${res.status}`);
  return res.json();
}
export async function criarItemCenario(cenarioId: number, dados: PlanejamentoItemPayload) {
  const res = await authFetch(`${API}/planejamento/cenarios/${cenarioId}/itens`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar item do cenário"); }
  return res.json();
}
export async function atualizarItemCenario(id: number, dados: PlanejamentoItemPayload) {
  const res = await authFetch(`${API}/planejamento/itens/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar item do cenário"); }
  return res.json();
}
export async function excluirItemCenario(id: number) {
  const res = await authFetch(`${API}/planejamento/itens/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir item do cenário"); }
}
export async function fetchProjecaoCenario(cenarioId: number) {
  const res = await authFetch(`${API}/planejamento/cenarios/${cenarioId}/projecao`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Projeção do cenário error: ${res.status}`);
  return res.json();
}

export async function importarParaPedido(dados: {
  origem_tipo: "orcamento" | "planejamento_financeiro"; origem_item_id: number;
  tipo_pedido: "compra" | "venda"; fornecedor_cliente?: string | null; data_pedido?: string | null;
}) {
  const res = await authFetch(`${API}/planejamento/importar-para-pedido`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao importar para pedido"); }
  return res.json();
}

// ── Pedidos (módulo próprio — só reflete em Estoque/Financeiro quando vinculado a um lançamento/movimento) ──
export type PedidoItemPayload = {
  tipo_item: "produto" | "servico"; produto_servico: string;
  codigo_conta_gerencial?: string | null; nome_conta_gerencial?: string | null;
  quantidade?: number | null; valor_unitario_estimado?: number | null; valor_total_estimado: number;
};
export type PedidoPayload = {
  tipo: "compra" | "venda"; fornecedor_cliente?: string | null; centro_custo?: string | null;
  data_pedido: string; data_prevista?: string | null; observacao?: string | null; responsavel?: string | null;
  itens: PedidoItemPayload[]; origem_tipo?: string | null; origem_item_id?: number | null;
};
export async function fetchOpcoesPedidos() {
  const res = await authFetch(`${API}/pedidos/opcoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Opções de pedidos error: ${res.status}`);
  return res.json();
}
export async function fetchPedidos(filtro?: { tipo?: string; status?: string; fornecedor_cliente?: string; data_inicio?: string; data_fim?: string }) {
  const qs = new URLSearchParams();
  Object.entries(filtro || {}).forEach(([k, v]) => { if (v) qs.set(k, v); });
  const res = await authFetch(`${API}/pedidos/?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Pedidos error: ${res.status}`);
  return res.json();
}
export async function fetchPedido(id: number) {
  const res = await authFetch(`${API}/pedidos/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Pedido error: ${res.status}`);
  return res.json();
}
export async function criarPedido(dados: PedidoPayload) {
  const res = await authFetch(`${API}/pedidos/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar pedido"); }
  return res.json();
}
export async function atualizarPedido(id: number, dados: PedidoPayload) {
  const res = await authFetch(`${API}/pedidos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar pedido"); }
  return res.json();
}
export async function atualizarStatusPedido(id: number, status: string) {
  const res = await authFetch(`${API}/pedidos/${id}/status`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar status do pedido"); }
  return res.json();
}
export async function excluirPedido(id: number) {
  const res = await authFetch(`${API}/pedidos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir pedido"); }
}
export async function atualizarRastreioPedido(id: number, dados: { enviado: boolean; codigo_rastreio?: string | null; link_rastreio?: string | null }) {
  const res = await authFetch(`${API}/pedidos/${id}/rastreio`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar rastreio do pedido"); }
  return res.json();
}
// Marca quanto de um item do pedido já foi FISICAMENTE entregue — valor
// ABSOLUTO novo do item (substitui, não soma). O status do pedido volta
// recalculado (nunca mais escolhido à mão) e, se faltar algo para fechar a
// ponta financeira, `pendencias` traz o que falta (ver marcar_entrega_item_pedido).
export type EntregaItemPedidoResultado = {
  id: number; status: string; pendencias: string[]; avisos_estoque: string[];
  item: { id: number; quantidade_entregue: number };
};
export async function marcarEntregaItemPedido(pedidoId: number, itemId: number, quantidadeEntregue: number): Promise<EntregaItemPedidoResultado> {
  const res = await authFetch(`${API}/pedidos/${pedidoId}/itens/${itemId}/entrega`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ quantidade_entregue: quantidadeEntregue }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao marcar entrega do item"); }
  return res.json();
}

// Anexos de Pedido — orçamento, ordem de serviço ou outro documento, com
// validade opcional (ver PedidoAnexo no backend); quando há validade, a
// Agenda alerta 2 dias antes do vencimento enquanto o pedido segue aberto/
// parcialmente atendido.
export const CATEGORIAS_PEDIDO_ANEXO = ["Orçamento", "Ordem de serviço", "Outro documento"];
export type AnexoPedido = {
  id: number; nome_arquivo: string; mime_type: string; tamanho_bytes: number; categoria: string;
  data_validade?: string | null; criado_em?: string;
};
export async function anexarArquivoPedido(pedidoId: number, file: File, categoria: string, dataValidade?: string | null): Promise<AnexoPedido> {
  const form = new FormData();
  form.append("file", file);
  form.append("categoria", categoria);
  if (dataValidade) form.append("data_validade", dataValidade);
  const res = await authFetch(`${API}/pedidos/${pedidoId}/anexos`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao anexar o arquivo"); }
  return res.json();
}
export async function listarAnexosPedido(pedidoId: number): Promise<AnexoPedido[]> {
  const res = await authFetch(`${API}/pedidos/${pedidoId}/anexos`);
  if (!res.ok) throw new Error("Erro ao listar anexos do pedido");
  return res.json();
}
export function urlAnexoPedido(anexoId: number): string {
  return `${API}/pedidos/anexos/${anexoId}`;
}
export async function excluirAnexoPedido(anexoId: number) {
  const res = await authFetch(`${API}/pedidos/anexos/${anexoId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir anexo"); }
  return res.json();
}

export async function fetchModelosImportar() {
  const res = await authFetch(`${API}/importar/modelos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Modelos de importação error: ${res.status}`);
  return res.json();
}

export async function importarCSV(categoria: string, file: File, extra?: Record<string, string>) {
  const form = new FormData();
  form.append("file", file);
  Object.entries(extra || {}).forEach(([k, v]) => form.append(k, v));
  const res = await authFetch(`${API}/importar/${categoria}`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao importar"); }
  return res.json();
}

export async function backfillFornecedoresEstoque() {
  const res = await authFetch(`${API}/importar/backfill`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao rodar o backfill"); }
  return res.json();
}

export async function uploadCSV(tipo: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  let res: Response;
  try {
    res = await authFetch(`${API}/upload/${tipo}`, {
      method: "POST",
      body: form,
    });
  } catch (e) {
    throw netError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(mensagemErroApi(err.detail) || "Erro no upload");
  }
  return res.json();
}

export async function addEventoManual(data: {
  data_evento: string;
  descricao: string;
  categoria?: string;
  numero_animal?: string;
  lotes?: string;
  tipo_evento?: string;
  observacao?: string;
  recorrente?: boolean;
  intervalo_dias?: number;
  intervalo_meses?: number;
}) {
  const res = await authFetch(`${API}/agenda/manual`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      data_evento: data.data_evento,
      descricao: data.descricao,
      categoria: data.categoria || "Gestão/Financeiro",
      numero_animal: data.numero_animal || null,
      lotes: data.lotes || null,
      tipo_evento: data.tipo_evento || null,
      observacao: data.observacao || null,
      recorrente: data.recorrente || false,
      intervalo_dias: data.intervalo_dias || null,
      intervalo_meses: data.intervalo_meses || null,
    }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao adicionar evento"); }
  return res.json();
}

// ── Exclusões (busca/solicitação abertas a todos; aprovar/rejeitar só admin) ──
export async function fetchTiposExclusao() {
  const res = await authFetch(`${API}/exclusoes/tipos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Tipos de exclusão error: ${res.status}`);
  return res.json();
}
export async function buscarExclusao(tipo: string, termo: string, dataInicio = "", dataFim = "") {
  const qs = new URLSearchParams({ tipo, termo, data_inicio: dataInicio, data_fim: dataFim });
  const res = await authFetch(`${API}/exclusoes/buscar?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Busca de exclusão error: ${res.status}`);
  return res.json();
}
export async function impactoExclusao(tipo: string, id: string) {
  const res = await authFetch(`${API}/exclusoes/impacto`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tipo, id }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao calcular impacto"); }
  return res.json();
}
export async function confirmarExclusao(tipo: string, id: string) {
  const res = await authFetch(`${API}/exclusoes/confirmar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tipo, id }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir"); }
  return res.json();
}
export async function fetchPendentesExclusao() {
  const res = await authFetch(`${API}/exclusoes/pendentes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Pendências de exclusão error: ${res.status}`);
  return res.json();
}
export async function aprovarExclusao(id: number) {
  const res = await authFetch(`${API}/exclusoes/pendentes/${id}/aprovar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao aprovar"); }
  return res.json();
}
export async function rejeitarExclusao(id: number, motivo?: string) {
  const res = await authFetch(`${API}/exclusoes/pendentes/${id}/rejeitar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ motivo }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao rejeitar"); }
  return res.json();
}

// ── Notificações (sininho) ──
export async function fetchNotificacoes() {
  const res = await authFetch(`${API}/notificacoes/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Notificações error: ${res.status}`);
  return res.json();
}

// ── Push nativo (Web Push, PWA) ──
export async function fetchPushChavePublica(): Promise<{ chave_publica: string }> {
  const res = await fetch(`${API}/push/chave-publica`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Chave pública do push error: ${res.status}`);
  return res.json();
}

export async function subscribePush(dados: { endpoint: string; keys: { p256dh: string; auth: string }; user_agent?: string }) {
  const res = await authFetch(`${API}/push/subscribe`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao ativar notificações"); }
  return res.json();
}

export async function unsubscribePush(endpoint?: string) {
  const res = await authFetch(`${API}/push/subscribe`, {
    method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint: endpoint || null }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao desativar notificações"); }
  return res.json();
}

// ── Push nativo (FCM, app Android Capacitor) ──
// Canal irmão do Web Push acima — usado só dentro do app nativo (ver
// lib/nativo.ts), que não confia no PushManager/service worker (não
// funciona de forma confiável com o app fechado dentro da WebView).
export async function registrarTokenFcm(dados: {
  token: string; plataforma?: string; modelo?: string; device_id?: string;
}): Promise<{ ok: boolean }> {
  const res = await authFetch(`${API}/push/registrar-fcm`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao registrar notificações"); }
  return res.json();
}

export async function removerTokenFcm(token?: string): Promise<{ ok: boolean }> {
  const res = await authFetch(`${API}/push/registrar-fcm`, {
    method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: token || null }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao remover notificações"); }
  return res.json();
}

// ── Aprovações de lançamentos vindos do Telegram (só admin) ──
export type LancamentoPendente = {
  id: number; tipo: string; rotulo: string; resumo: string; dados: Record<string, any>;
  status: string; erro: string | null; solicitante_nome: string | null; solicitante_chat_id: number | null;
  criado_em: string | null; decidido_em: string | null; decidido_por: string | null;
};

export async function fetchAprovacoes(): Promise<LancamentoPendente[]> {
  const res = await authFetch(`${API}/aprovacoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Aprovações error: ${res.status}`);
  return res.json();
}

export async function fetchAprovacoesContagem(): Promise<{ pendentes: number }> {
  const res = await authFetch(`${API}/aprovacoes/contagem`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Contagem error: ${res.status}`);
  return res.json();
}

export async function editarLancamentoPendente(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/aprovacoes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dados }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar"); }
  return res.json();
}

export async function aprovarLancamento(id: number) {
  const res = await authFetch(`${API}/aprovacoes/${id}/aprovar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao aprovar"); }
  return res.json();
}

export async function rejeitarLancamento(id: number) {
  const res = await authFetch(`${API}/aprovacoes/${id}/rejeitar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao rejeitar"); }
  return res.json();
}

// G17 — fila de decididos (aprovados/rejeitados), com a possibilidade de
// desfazer. `pode_desfazer` é sempre true para rejeitado; para aprovado, só
// quando o backend conseguiu gravar o(s) registro(s) criados (ver
// `LancamentoPendente.registro_criado`) e eles ainda existem — aprovações
// antigas (de antes desta coluna existir) vêm com `pode_desfazer: false` e
// `motivo_nao_desfaz` explicando o porquê.
export type LancamentoPendenteDecidido = LancamentoPendente & {
  pode_desfazer: boolean; motivo_nao_desfaz: string | null;
};
export async function fetchAprovacoesDecididas(limite = 30): Promise<LancamentoPendenteDecidido[]> {
  const res = await authFetch(`${API}/aprovacoes/decididas?limite=${limite}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Aprovações decididas error: ${res.status}`);
  return res.json();
}
/** Rejeitado → volta a "pendente" (pode ser reavaliado). Aprovado → desfaz o
 * que foi criado (mesmo trio do motor de exclusões: desvincula vale, estorna
 * estoque, `session.delete`) e também volta a "pendente" — 400 se o registro
 * não for reversível (`registro_criado` ausente ou `reversivel: false`), 409
 * se ainda estiver "pendente" (nada pra desfazer). */
export async function desfazerAprovacao(id: number) {
  const res = await authFetch(`${API}/aprovacoes/${id}/desfazer`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao desfazer aprovação"); }
  return res.json();
}

export function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
  }).format(value);
}

export function formatDate(iso: string): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export function today(): string {
  return new Date().toISOString().split("T")[0];
}

export function firstDayOfMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

// ── Módulo RECRIA (Dossiê de Desempenho Zootécnico) ──
const _rHead = () => ({ "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) });
async function _rGet(path: string) {
  const res = await fetch(`${API}${path}`, { headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {}, cache: "no-store" });
  if (!res.ok) throw new Error(`Recria ${path}: ${res.status}`);
  return res.json();
}
async function _rSend(path: string, method: string, body?: any) {
  const res = await fetch(`${API}${path}`, { method, headers: _rHead(), ...(body ? { body: JSON.stringify(body) } : {}) });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || `Erro (${res.status})`); }
  return res.json();
}

export type RecriaOcorrencia = { id: number; numero_matriz: string; doenca: string; doenca_id?: number | null; data_ocorrencia: string; observacao?: string | null; origem: string; usuario_nome?: string | null };
export type RecriaPontoCritico = { dia_pico: number; dia_min: number; dia_max: number; casos_na_janela: number; total_casos: number; pct_na_janela: number };
export type RecriaCurva = {
  doenca: string; total_casos: number;
  curva: { dia: number; casos: number }[];
  ponto_critico: RecriaPontoCritico | null;
  incidencia_por_fase: { fase: string; dia_min: number; dia_max: number; casos: number; animais_afetados: number; animais_em_risco: number; incidencia_pct: number | null }[];
};
export type RecriaMetas = { idade_parto_meses: number; idade_prenhez_meses: number; idade_1a_cobertura_meses: number; taxa_prenhez_meta: number; desvio_padrao_meta: number; custo_diario_recria: number };
export type RecriaPesoAlvo = { id?: number; mes: number; peso_min_kg: number; peso_max_kg: number };
export type RecriaFase = { id?: number; nome: string; dia_min: number; dia_max: number; ordem: number; ativo: boolean };
export type RecriaJanela = { id?: number; doenca: string; doenca_id?: number | null; dia_min: number; dia_max: number; dias_antecedencia: number; ativo: boolean };

export const fetchRecriaDoencas = (): Promise<{ doenca: string; casos: number }[]> => _rGet(`/recria/doencas`);
export const fetchRecriaCurva = (doenca: string, ini?: string, fim?: string): Promise<RecriaCurva> => {
  const p = new URLSearchParams({ doenca }); if (ini) p.set("ini", ini); if (fim) p.set("fim", fim);
  return _rGet(`/recria/saude/curva?${p.toString()}`);
};
export const fetchRecriaPesoAlvoResumo = (): Promise<{ linhas: any[] }> => _rGet(`/recria/crescimento/peso-alvo`);
export const fetchRecriaOcorrencias = (doenca = "", numero = ""): Promise<RecriaOcorrencia[]> => {
  const p = new URLSearchParams(); if (doenca) p.set("doenca", doenca); if (numero) p.set("numero_matriz", numero);
  return _rGet(`/recria/ocorrencias${p.toString() ? "?" + p.toString() : ""}`);
};
export const criarRecriaOcorrencia = (d: { numero_matriz: string; doenca: string; doenca_id?: number | null; data_ocorrencia: string; observacao?: string }) => _rSend(`/recria/ocorrencias`, "POST", d);
export const excluirRecriaOcorrencia = (id: number) => _rSend(`/recria/ocorrencias/${id}`, "DELETE");
export const fetchRecriaMetas = (): Promise<RecriaMetas> => _rGet(`/recria/metas`);
export const salvarRecriaMetas = (d: RecriaMetas) => _rSend(`/recria/metas`, "PUT", d);
export const fetchRecriaPesoAlvo = (): Promise<RecriaPesoAlvo[]> => _rGet(`/recria/peso-alvo`);
export const salvarRecriaPesoAlvo = (d: RecriaPesoAlvo) => _rSend(`/recria/peso-alvo`, "POST", d);
export const excluirRecriaPesoAlvo = (mes: number) => _rSend(`/recria/peso-alvo/${mes}`, "DELETE");
export const fetchRecriaFases = (): Promise<RecriaFase[]> => _rGet(`/recria/fases`);
export const criarRecriaFase = (d: RecriaFase) => _rSend(`/recria/fases`, "POST", d);
export const excluirRecriaFase = (id: number) => _rSend(`/recria/fases/${id}`, "DELETE");
export const fetchRecriaJanelas = (): Promise<RecriaJanela[]> => _rGet(`/recria/janelas`);
export const criarRecriaJanela = (d: RecriaJanela) => _rSend(`/recria/janelas`, "POST", d);
export const excluirRecriaJanela = (id: number) => _rSend(`/recria/janelas/${id}`, "DELETE");

export type RecriaBenchmark = { id?: number; indicador: string; unidade?: string | null; melhor_e_maior: boolean; top5?: number | null; top10?: number | null; top25?: number | null; top50?: number | null; top75?: number | null; valor_fazenda?: number | null; ordem: number; fonte: string; faixa_fazenda?: string | null };
export const fetchRecriaBenchmark = (): Promise<RecriaBenchmark[]> => _rGet(`/recria/benchmark`);
export const salvarRecriaBenchmark = (d: RecriaBenchmark) => _rSend(`/recria/benchmark`, "POST", d);
export const excluirRecriaBenchmark = (id: number) => _rSend(`/recria/benchmark/${id}`, "DELETE");

export type WisconsinStats = { n: number; media: number; minimo: number; maximo: number; desvio_padrao: number; assimetria: number; curtose: number; idade_tipica_min: number; idade_tipica_max: number; amplitude_tipica: number };
export type RecriaIdadeParto = { meta_idade_parto: number; meta_desvio_padrao: number; estatisticas: WisconsinStats | null; distribuicao: { mes: number; n: number; pct: number }[]; custo_excedente: { n: number; dias_excedentes_total: number; custo_total: number; dias_por_novilha: number; custo_por_novilha: number } };
// Vem do mesmo motor que `CicloReprodutivo` (programa_reprodutivo.py), só
// filtrado em novilhas. `elegiveis`/`servidos`/`prenhes` são aliases legados de
// `br_elig`/`bred`/`preg`, mantidos por compatibilidade da tela de Recria.
// ATENÇÃO: a taxa de prenhez usa `pg_elig` como denominador, não `elegiveis` —
// os dois diferem quando há baixa durante a janela de diagnóstico.
export type RecriaCiclo = {
  ciclo: number; inicio: string; fim: string;
  elegiveis: number; servidos: number; prenhes: number;
  br_elig: number; bred: number; pg_elig: number; preg: number;
  servicos_com_resultado: number; janela_dg_completa: boolean;
  animais: { br_elig: string[]; bred: string[]; pg_elig: string[]; preg: string[] };
  taxa_servico: number | null; taxa_concepcao: number | null; taxa_prenhez: number | null;
};
export const fetchRecriaIdadeParto = (): Promise<RecriaIdadeParto> => _rGet(`/recria/reproducao/idade-parto`);
export const fetchRecriaTaxaPrenhez = (ini: string, fim: string, vwp = 0): Promise<{ ciclos: RecriaCiclo[]; taxa_prenhez_media: number | null; total_servicos: number; /** Quantos entraram em pelo menos um balde do BREDSUM\E — não o tamanho do rebanho carregado (ver `animais_carregados`). */ animais_avaliados: number; animais_carregados: number; meta_taxa_prenhez: number }> =>
  _rGet(`/recria/reproducao/taxa-prenhez?ini=${ini}&fim=${fim}&vwp_dias=${vwp}`);

export type RecriaDossie = {
  gerado_em: string;
  kpis: Record<string, number | null>;
  secoes: { titulo: string; colunas: { header: string; key: string }[]; linhas: Record<string, unknown>[] }[];
};
export const fetchRecriaDossie = (): Promise<RecriaDossie> => _rGet(`/recria/dossie`);

export type RecriaCocho = { id?: number; data: string; lote: string; num_animais: number; kg_ofertado: number; kg_sobra: number; kg_formulado?: number | null; observacao?: string | null; kg_consumido?: number; pct_sobra?: number | null; ims_consumida_animal?: number; ims_formulada_animal?: number | null; usuario_nome?: string | null };
export const fetchRecriaCocho = (lote = "", ini = "", fim = ""): Promise<{ registros: RecriaCocho[]; lotes: string[] }> => {
  const p = new URLSearchParams(); if (lote) p.set("lote", lote); if (ini) p.set("ini", ini); if (fim) p.set("fim", fim);
  return _rGet(`/recria/cocho${p.toString() ? "?" + p.toString() : ""}`);
};
export const criarRecriaCocho = (d: RecriaCocho) => _rSend(`/recria/cocho`, "POST", d);
export const excluirRecriaCocho = (id: number) => _rSend(`/recria/cocho/${id}`, "DELETE");

export function baixarModeloCocho() {
  return baixarArquivoAutenticado("/recria/cocho/modelo-excel", "modelo_leitura_cocho.xlsx");
}

export async function importarCochoPlanilha(file: File): Promise<{ criados: number; erros: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/recria/cocho/importar`, { method: "POST", body: form });
  if (!res.ok) throw new Error(mensagemErroApi((await res.json().catch(() => null))?.detail) || "Erro ao importar planilha");
  return res.json();
}

export type Estratificacao = {
  total: number; estratos: Record<string, number>; numeros: Record<string, string[]>;
  percentuais: Record<string, number>; vacas_total: number; numeros_vacas_total: string[];
  pct_lactacao_sobre_total: number; pct_lactacao_sobre_vacas: number;
};
export const fetchEstratificacaoRebanho = (): Promise<Estratificacao> => _rGet(`/animais/estratificacao`);

// ── Estados reprodutivos AO VIVO (substitui o Animal.sit_rep congelado do CSV
// nas listas de drill-down de Rebanho > Indicadores, ver Indicadores.tsx) ──
export type EstadoReprodutivoAnimal = {
  numero: string; estado: string; categoria: string; lote: string | null;
  del_dias: number | null; data_ultimo_parto: string | null;
  dias_gestacao: number | null; parto_previsto: string | null;
  data_servico: string | null; tipo_servico: string | null; protocolo: string | null;
  dias_desde_servico: number | null;
  protocolo_d0?: string | null; protocolo_dia_atual?: number | null;
};
export type EstadosReprodutivos = {
  data_referencia: string; animais: EstadoReprodutivoAnimal[];
  contagem: Record<string, number>; parametros: Record<string, number>;
};
export const fetchEstadosReprodutivos = (): Promise<EstadosReprodutivos> => _rGet(`/indicadores/estados-reprodutivos`);

export type CategoriaManejo = {
  id?: number; nome: string; dia_min: number; dia_max?: number | null;
  peso_min_kg?: number | null; peso_max_kg?: number | null; usa_status_reprodutivo: boolean;
  // Critérios adicionais — todos opcionais; deixe em branco para não filtrar por eles.
  // "vazia" casa também com a atrasada (retrocompatibilidade); "vazia_atrasada"
  // restringe à novilha/vaca que passou do prazo — ver
  // fazenda/api/routers/recria.py::situacao_reprodutiva_casa.
  situacao_reprodutiva?: "vazia" | "vazia_atrasada" | "inseminada" | "prenha" | null;
  situacao_produtiva?: "lactacao" | "seca" | null;
  dias_gestacao_min?: number | null; dias_gestacao_max?: number | null;
  dias_desde_servico_min?: number | null; dias_desde_servico_max?: number | null;
  dias_para_parto_min?: number | null; dias_para_parto_max?: number | null;
  dias_pos_parto_min?: number | null; dias_pos_parto_max?: number | null;
  ordem: number; ativo: boolean;
};
export const fetchCategoriasManejo = (): Promise<CategoriaManejo[]> => _rGet(`/recria/categorias`);
export const criarCategoriaManejo = (d: CategoriaManejo) => _rSend(`/recria/categorias`, "POST", d);
export const atualizarCategoriaManejo = (id: number, d: CategoriaManejo) => _rSend(`/recria/categorias/${id}`, "PUT", d);
export const excluirCategoriaManejo = (id: number) => _rSend(`/recria/categorias/${id}`, "DELETE");
export const fetchComposicaoCategorias = (): Promise<{ composicao: { categoria: string; n: number }[]; total: number }> => _rGet(`/recria/categorias/composicao`);
export const fetchCategoriaSugerida = (numero: string): Promise<{ categoria: string | null }> => _rGet(`/recria/categorias/animal/${numero}`);

export type Touro = {
  id?: number; naab: string; nome?: string | null; nome_completo?: string | null; raca?: string | null; central?: string | null;
  leite_kg?: number | null; gordura_kg?: number | null; gordura_pct?: number | null;
  proteina_kg?: number | null; proteina_pct?: number | null; tpi?: number | null; nm_dolar?: number | null;
  tipo_composto?: number | null; ubere_composto?: number | null; pernas_composto?: number | null;
  ccs_score?: number | null; fertilidade_filhas?: number | null; facilidade_parto?: number | null;
  fonte?: string | null; rodada_prova?: string | null; observacao?: string | null; atualizado_em?: string | null;
  dados_extra?: string | null; // JSON [[rótulo, valor], ...] — demais dados da planilha do fornecedor
};
export type TouroIn = Omit<Touro, "id" | "atualizado_em" | "dados_extra"> & { dados_extra?: [string, string][] | null };
// LEITURA do catálogo NAAB pela fazenda — não mudou, e é ela que alimenta
// listagem/busca, prova média, estudo de touros, inseminação (inclusive com
// touro fora do estoque), sugestão de acasalamento, ficha do animal e compra
// de sêmen.
export const fetchTouros = (): Promise<Touro[]> => _rGet(`/cadastro/touros`);

// MANUTENÇÃO do catálogo — só no Painel CowData (set/2026). O catálogo é
// GLOBAL (um `Touro` só, sem fazenda_id, lido por todas as fazendas-cliente):
// as rotas de escrita saíram de /cadastro/touros, onde o administrador de
// qualquer fazenda-cliente reescrevia o catálogo de todas, e hoje exigem a
// permissão "editar touros NAAB" do cadastro de equipe. Ver
// backend/fazenda/api/routers/painel_cowdata_touros.py.
export const fetchTourosCowData = (): Promise<Touro[]> => _pcGet(`/touros`);
export const fetchCamposPlanilhaTourosCowData = (): Promise<string[]> => _pcGet(`/touros/campos-planilha`);
export const criarTouroCowData = (d: TouroIn): Promise<Touro> => _pcSend(`/touros`, "POST", d);
export const atualizarTouroCowData = (id: number, d: TouroIn): Promise<Touro> => _pcSend(`/touros/${id}`, "PUT", d);
export const excluirTouroCowData = (id: number) => _pcSend(`/touros/${id}`, "DELETE");
export const recarregarCatalogoTourosCowData = (): Promise<{ touros_antes: number; touros_depois: number }> =>
  _pcSend(`/touros/recarregar-catalogo`, "POST");

// Importar a planilha do fornecedor (Excel ou CSV do ABS BullSearch, Alta,
// Select Sires...). Era `POST /importar/touros_naab`, dentro do Importar
// dados da fazenda: o mesmo upsert no catálogo global protegido só pela
// permissão de Upload da fazenda. Multipart, por isso não passa pelo
// _pcSend (que manda JSON).
export async function importarPlanilhaTourosCowData(file: File, fonte: string, rodada: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("fonte", fonte);
  form.append("rodada", rodada);
  const res = await authFetch(`${API}/painel-cowdata/touros/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao importar o catálogo"); }
  return res.json() as Promise<{ categoria: string; criados?: number; atualizados?: number; erros?: string[] }>;
}

export type ProvaMediaCampos = Record<
  "leite_kg" | "gordura_kg" | "gordura_pct" | "proteina_kg" | "proteina_pct" | "tpi" | "nm_dolar"
  | "tipo_composto" | "ubere_composto" | "pernas_composto" | "ccs_score" | "fertilidade_filhas" | "facilidade_parto",
  number | null
>;
export type ProvaMediaRecorte = { prova: ProvaMediaCampos; touros_considerados: number };
export type ProvaMediaSemen = {
  simples: ProvaMediaRecorte;
  ponderada: ProvaMediaRecorte & { total_doses: number };
};
export const fetchProvaMediaSemen = (opts?: { incluirFazenda?: boolean }): Promise<ProvaMediaSemen> =>
  _rGet(`/cadastro/estoque-semen/prova-media${opts?.incluirFazenda ? "?incluir_fazenda=true" : ""}`);

// "Prova ao vivo" — os MESMOS indicadores genéticos do catálogo (ver
// ProvaMediaSemen acima: leite, gordura, proteína, TPI, NM$, etc.), só que
// ponderados pelo USO REAL do touro na fazenda (nº de serviços em que foi
// de fato usado), não pelas doses hoje em estoque. Não é taxa de concepção
// nem outro indicador de resultado reprodutivo do rebanho.
export type ProvaAoVivoTouro = { touro: string; servicos: number };
export type ProvaAoVivoSemen = {
  prova: ProvaMediaCampos; total_servicos: number; touros_considerados: number; touros: ProvaAoVivoTouro[];
  categoria: string; ano_nascimento: number | null; de: string | null; ate: string | null;
};
export const fetchProvaAoVivoSemen = (filtros?: {
  categoria?: "todas" | "vaca" | "novilha"; anoNascimento?: number; de?: string; ate?: string; incluirFazenda?: boolean;
}): Promise<ProvaAoVivoSemen> => {
  const p = new URLSearchParams();
  if (filtros?.categoria && filtros.categoria !== "todas") p.set("categoria", filtros.categoria);
  if (filtros?.anoNascimento) p.set("ano_nascimento", String(filtros.anoNascimento));
  if (filtros?.de) p.set("de", filtros.de);
  if (filtros?.ate) p.set("ate", filtros.ate);
  if (filtros?.incluirFazenda) p.set("incluir_fazenda", "true");
  const qs = p.toString();
  return _rGet(`/cadastro/estoque-semen/prova-ao-vivo${qs ? `?${qs}` : ""}`);
};

// ── News (blog de pecuária leiteira) ──
export type NoticiaNews = {
  id: number; fonte_id: number; manchete: string; resumo?: string | null; link: string;
  data_publicacao?: string | null; capturado_em: string; materia?: string | null; fontes?: string[];
  revisado_final: boolean; revisado_final_em?: string | null; revisado_final_por?: string | null;
  // Ilustração + rótulo curto (#news-redesign) — caminho público em
  // /news-images/ e pílula de tema, respectivamente; ambos opcionais (nulo
  // em matérias antigas — a tela cai no fundo temático rotativo já existente).
  imagem?: string | null; categoria?: string | null;
};
export type NewsFeed = { janela_dias: number; fontes: { fonte: { id: number; nome: string; url: string; erro?: string | null }; noticias: NoticiaNews[] }[] };

export const fetchNoticias = (verTudo = false): Promise<NewsFeed> => _rGet(`/news/${verTudo ? "?ver_tudo=true" : ""}`);
// Lista TODAS as matérias (publicadas + aguardando revisão) — usada em
// Configurações > News. Diferente de fetchNoticias, que só traz as já
// revisadas (visão pública).
export const fetchTodasMaterias = (): Promise<NoticiaNews[]> => _rGet(`/news/materias`);

export type MateriaBlogIn = { manchete: string; materia: string; fontes: string[]; imagem?: string; categoria?: string };
export const criarMateriaBlog = (d: MateriaBlogIn): Promise<NoticiaNews> => _rSend(`/news/materias`, "POST", d);
export type MateriaBlogEditIn = { manchete: string; materia?: string; resumo?: string; fontes: string[]; imagem?: string; categoria?: string };
export const atualizarMateriaBlog = (id: number, d: MateriaBlogEditIn): Promise<NoticiaNews> => _rSend(`/news/materias/${id}`, "PUT", d);
export const excluirMateriaBlog = (id: number) => _rSend(`/news/materias/${id}`, "DELETE");
export const revisarPublicacaoFinal = (id: number): Promise<NoticiaNews> => _rSend(`/news/materias/${id}/revisar-final`, "POST");

// Nota informativa simples na Capa (distinta de matéria de blog) — só o
// dono da plataforma edita (ver PUT /news/nota-capa em Configurações > News).
export type NotaCapa = { id: number; titulo: string; texto: string; atualizado_em: string };
export const fetchNotaCapa = (): Promise<NotaCapa | null> => _rGet(`/news/nota-capa`);
export const atualizarNotaCapa = (d: { titulo: string; texto: string; ativa: boolean }): Promise<NotaCapa> =>
  _rSend(`/news/nota-capa`, "PUT", d);

// ── Assistente Claude (protótipo — conversa aberta a qualquer usuário
// logado da fazenda piloto; treino restrito a admin, ver
// backend/fazenda/api/routers/assistente.py) ──
export type AssistenteResposta = { resposta: string; historico: any[] };
export async function perguntarAssistente(mensagem: string, historico: any[] = []): Promise<AssistenteResposta> {
  return _rSend(`/assistente/perguntar`, "POST", { mensagem, historico });
}
// Nunca dá 403 — `liberado` diz se pode conversar, `pode_treinar` se pode
// ver a aba/tela de Ensinamentos (admin).
export const fetchAssistenteAcesso = (): Promise<{ liberado: boolean; pode_treinar: boolean }> =>
  _rGet(`/assistente/acesso`);

export type AssistenteEnsinamento = {
  id: number; titulo: string; texto: string; ativo: boolean; criado_em: string; atualizado_em: string;
};
export const fetchEnsinamentos = (): Promise<AssistenteEnsinamento[]> => _rGet(`/assistente/ensinamentos`);
export const criarEnsinamento = (d: { titulo: string; texto: string }): Promise<AssistenteEnsinamento> =>
  _rSend(`/assistente/ensinamentos`, "POST", d);
export const atualizarEnsinamento = (id: number, d: { titulo: string; texto: string; ativo: boolean }): Promise<AssistenteEnsinamento> =>
  _rSend(`/assistente/ensinamentos/${id}`, "PUT", d);
export const excluirEnsinamento = (id: number) => _rSend(`/assistente/ensinamentos/${id}`, "DELETE");

// ── Portal (Administração > Portal > Comunicação) ──
export const ABAS_PORTAL = [
  { id: "sanidade", label: "Sanidade" },
  { id: "alimentacao", label: "Alimentação" },
  { id: "estoque", label: "Estoque" },
  { id: "indicadores", label: "Indicadores" },
  { id: "financeiro", label: "Financeiro" },
  { id: "pedidos", label: "Pedidos" },
  { id: "listas", label: "Listas" },
  { id: "lancamentos", label: "Lançamentos" },
  { id: "agenda", label: "Agenda" },
];

export type PortalDestinatario = { id: number; nome: string; username: string };
export type PortalMensagem = {
  id: number; tipo: "mensagem" | "tarefa" | "foto";
  remetente: string | null; remetente_usuario_id: number;
  destinatario: string | null; destinatario_usuario_id: number;
  aba: string | null; corpo: string; pede_retorno: boolean;
  lida: boolean; resolvida: boolean; resposta_de_id: number | null;
  foto_campo_id: number | null; criado_em: string;
};

export const fetchPortalPermissoes = (): Promise<{ pode_delegar_tarefa: boolean }> => _rGet(`/portal/permissoes`);
export const fetchPortalDestinatarios = (): Promise<PortalDestinatario[]> => _rGet(`/portal/destinatarios`);
export const fetchPortalMensagensPendentes = (): Promise<PortalMensagem[]> => _rGet(`/portal/mensagens/pendentes`);

export const enviarPortalMensagem = (d: { destinatarios_usuario_id: number[]; aba?: string | null; corpo: string; pede_retorno: boolean }) =>
  _rSend(`/portal/mensagens`, "POST", d);
export const marcarPortalMensagemLida = (id: number) => _rSend(`/portal/mensagens/${id}/marcar-lida`, "POST");
export const resolverPortalMensagem = (id: number) => _rSend(`/portal/mensagens/${id}/resolver`, "POST");
export const responderPortalMensagem = (id: number, d: { corpo: string; aba?: string | null }) =>
  _rSend(`/portal/mensagens/${id}/responder`, "POST", d);

export const fetchPortalRelatoriosDisponiveis = (): Promise<Record<string, string>> => _rGet(`/portal/relatorios-disponiveis`);
export const enviarPortalEmail = (d: {
  destinatarios_usuario_id: number[]; assunto: string; corpo?: string;
  relatorio?: string; data_inicio?: string; data_fim?: string;
}) => _rSend(`/portal/email`, "POST", d);

export const delegarPortalTarefa = (d: { destinatarios_usuario_id: number[]; corpo: string; data_evento?: string }) =>
  _rSend(`/portal/tarefas`, "POST", d);

export type PortalOpcaoExportacao = { chave: string; rotulo: string; tem_periodo: boolean };
export const fetchPortalOpcoesExportacao = (): Promise<PortalOpcaoExportacao[]> => _rGet(`/portal/exportar/opcoes`);
export const solicitarPortalExportacao = (d: { itens: { chave: string; data_inicio?: string; data_fim?: string }[] }) =>
  _rSend(`/portal/exportar`, "POST", d);

// ── Arquivo fiscal-contábil (Documentos) ──
// Ver backend/fazenda/api/routers/documentos.py — upload pergunta "inserir
// no balanço?", conteúdo vive no Supabase Storage, aqui só os metadados.
export type DocumentoArquivado = {
  id: number; categoria: string; nome_original: string; mime_type: string; tamanho_bytes: number;
  data_documento: string | null; data_upload: string; inserir_no_balanco: boolean;
  numero_lancamento: string | null; descricao: string | null;
};

export async function fetchCategoriasDocumento(): Promise<string[]> {
  const res = await authFetch(`${API}/documentos/categorias`);
  if (!res.ok) throw new Error("Erro ao listar categorias de documento");
  return res.json();
}

export async function fetchDocumentos(filtros?: {
  categoria?: string; inserir_no_balanco?: boolean; numero_lancamento?: string; data_de?: string; data_ate?: string;
}): Promise<DocumentoArquivado[]> {
  const params = new URLSearchParams();
  if (filtros?.categoria) params.set("categoria", filtros.categoria);
  if (filtros?.inserir_no_balanco !== undefined) params.set("inserir_no_balanco", String(filtros.inserir_no_balanco));
  if (filtros?.numero_lancamento) params.set("numero_lancamento", filtros.numero_lancamento);
  if (filtros?.data_de) params.set("data_de", filtros.data_de);
  if (filtros?.data_ate) params.set("data_ate", filtros.data_ate);
  const qs = params.toString();
  const res = await authFetch(`${API}/documentos${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error("Erro ao listar documentos");
  return res.json();
}

export async function enviarDocumento(dados: {
  file: File; categoria: string; inserirNoBalanco: boolean; numeroLancamento?: string; dataDocumento?: string; descricao?: string;
}): Promise<DocumentoArquivado> {
  const fd = new FormData();
  fd.append("file", dados.file);
  fd.append("categoria", dados.categoria);
  fd.append("inserir_no_balanco", String(dados.inserirNoBalanco));
  if (dados.numeroLancamento) fd.append("numero_lancamento", dados.numeroLancamento);
  if (dados.dataDocumento) fd.append("data_documento", dados.dataDocumento);
  if (dados.descricao) fd.append("descricao", dados.descricao);
  const res = await authFetch(`${API}/documentos/upload`, { method: "POST", body: fd });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao arquivar documento"); }
  return res.json();
}

// Baixa via blob (não um <a href> direto) — o endpoint exige o token da
// sessão, e assim o arquivo nunca aparece com uma URL "crua" navegável.
export async function baixarDocumento(id: number, nomeArquivo: string): Promise<void> {
  const res = await authFetch(`${API}/documentos/${id}/download`);
  if (!res.ok) throw new Error("Erro ao baixar documento");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = nomeArquivo;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

export async function excluirDocumento(id: number): Promise<void> {
  const res = await authFetch(`${API}/documentos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir documento"); }
}

// ── Fotos do campo (app móvel) ──
// Ver backend/fazenda/api/routers/fotos.py — foto tirada pela câmera do
// celular, conteúdo vive no Supabase Storage (bucket próprio), aqui só os
// metadados.
export type FotoCampo = {
  id: number; mime_type: string; tamanho_bytes: number;
  descricao: string | null; identificacao_animal: string | null;
  tipo_assunto: "animal" | "lote" | "outro" | null; animal_id: number | null;
  lotes: string | null; assunto_fixo: string | null; data_captura: string;
};

export async function fetchFotosCampo(filtros?: {
  identificacao_animal?: string; lote?: string; data_de?: string; data_ate?: string;
}): Promise<FotoCampo[]> {
  const params = new URLSearchParams();
  if (filtros?.identificacao_animal) params.set("identificacao_animal", filtros.identificacao_animal);
  if (filtros?.lote) params.set("lote", filtros.lote);
  if (filtros?.data_de) params.set("data_de", filtros.data_de);
  if (filtros?.data_ate) params.set("data_ate", filtros.data_ate);
  const qs = params.toString();
  const res = await authFetch(`${API}/fotos${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error("Erro ao listar fotos");
  return res.json();
}

// Busca via blob (não um <img src="..."> direto) — o endpoint exige o token
// da sessão. Chamador é responsável por URL.revokeObjectURL quando descartar.
export async function fetchFotoCampoUrl(id: number): Promise<string> {
  const res = await authFetch(`${API}/fotos/${id}/arquivo`);
  if (!res.ok) throw new Error("Erro ao carregar foto");
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function excluirFotoCampo(id: number): Promise<void> {
  const res = await authFetch(`${API}/fotos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir foto"); }
}

// ── Banco de fotos do Milknews (blog News) ──
// Ver backend/fazenda/api/routers/fotos_news.py — bucket PÚBLICO do Supabase
// Storage; `url` já vem pronta para uso direto em <img src>, sem autenticação
// (a página pública do blog lê sem login). Gerido na aba Aprovações.
export type PastaFotoNews = { id: number; nome: string; criado_em: string; quantidade_fotos: number };
export type FotoNews = {
  id: number; pasta_id: number | null; nome_arquivo: string; mime_type: string;
  tamanho_bytes: number; tags: string | null; criado_em: string; url: string;
};

export async function fetchPastasFotosNews(): Promise<PastaFotoNews[]> {
  const res = await authFetch(`${API}/fotos-news/pastas`);
  if (!res.ok) throw new Error("Erro ao listar pastas do banco de fotos");
  return res.json();
}
export async function criarPastaFotosNews(nome: string): Promise<PastaFotoNews> {
  const res = await authFetch(`${API}/fotos-news/pastas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar pasta"); }
  return res.json();
}
export async function excluirPastaFotosNews(id: number): Promise<void> {
  const res = await authFetch(`${API}/fotos-news/pastas/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir pasta"); }
}
export async function fetchFotosNews(pastaId?: number | null): Promise<FotoNews[]> {
  const qs = pastaId === null ? "?sem_pasta=true" : pastaId != null ? `?pasta_id=${pastaId}` : "";
  const res = await authFetch(`${API}/fotos-news${qs}`);
  if (!res.ok) throw new Error("Erro ao listar fotos do banco");
  return res.json();
}
export async function enviarFotoNews(file: File, pastaId?: number | null, tags?: string): Promise<FotoNews> {
  const fd = new FormData();
  fd.append("file", file);
  const params = new URLSearchParams();
  if (pastaId != null) params.set("pasta_id", String(pastaId));
  if (tags) params.set("tags", tags);
  const qs = params.toString();
  const res = await authFetch(`${API}/fotos-news/upload${qs ? `?${qs}` : ""}`, { method: "POST", body: fd });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao enviar foto"); }
  return res.json();
}
export async function excluirFotoNews(id: number): Promise<void> {
  const res = await authFetch(`${API}/fotos-news/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir foto"); }
}

// ── Cadeado do Painel do Contador ──
// Reautenticação por senha que destrava, por 15 minutos, lançamentos
// extraordinários, recálculo de juros e abertura de chamado — ver
// backend/fazenda/auth.py::bloquear_escrita_contador e POST /auth/desbloquear.
// O token retornado vai no header X-Desbloqueio das chamadas seguintes.
export async function desbloquearContador(senha: string): Promise<{ token_desbloqueio: string; validade_segundos: number }> {
  const res = await fetch(`${API}/auth/desbloquear`, {
    method: "POST", headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: JSON.stringify({ senha }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Senha incorreta"); }
  return res.json();
}

function comDesbloqueio(token: string): HeadersInit {
  return { "X-Desbloqueio": token };
}

// ── Chamados (suporte) ──
export type Chamado = {
  id: number; assunto: string; descricao: string; status: "aberto" | "em_andamento" | "resolvido";
  criado_em: string; atualizado_em: string; resposta: string | null;
};

export async function fetchChamados(): Promise<Chamado[]> {
  const res = await authFetch(`${API}/chamados`);
  if (!res.ok) throw new Error("Erro ao listar chamados");
  return res.json();
}

export async function abrirChamado(dados: { assunto: string; descricao: string }, tokenDesbloqueio: string): Promise<Chamado> {
  const res = await authFetch(`${API}/chamados`, {
    method: "POST", headers: { "Content-Type": "application/json", ...comDesbloqueio(tokenDesbloqueio) },
    body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao abrir chamado"); }
  return res.json();
}

// ── Recálculo de juros/multa (calculadora — não persiste nada sozinha) ──
export type CalculoJuros = { dias_atraso: number; valor_multa: number; valor_juros: number; valor_atualizado: number };

export async function calcularJuros(
  dados: { valor_original: number; data_vencimento: string; data_referencia?: string; percentual_multa?: number; percentual_juros_mes?: number },
  tokenDesbloqueio: string,
): Promise<CalculoJuros> {
  const res = await authFetch(`${API}/financeiro/calcular-juros`, {
    method: "POST", headers: { "Content-Type": "application/json", ...comDesbloqueio(tokenDesbloqueio) },
    body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao calcular juros"); }
  return res.json();
}

// Lançamento extraordinário do contador (guia/imposto/multa) — mesmo POST
// /financeiro/lancamentos de sempre, só que com o cadeado destravado.
export async function criarLancamentoExtraordinario(dados: any, tokenDesbloqueio: string) {
  const res = await authFetch(`${API}/financeiro/lancamentos`, {
    method: "POST", headers: { "Content-Type": "application/json", ...comDesbloqueio(tokenDesbloqueio) },
    body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar lançamento"); }
  return res.json();
}

// ── Alertas de indicador por limite ──
// Ver backend/fazenda/api/routers/alertas_indicador.py — "avise-me se o
// indicador X passar de Y", disparado pela central de notificações/push.
export type IndicadorCatalogo = { chave: string; label: string };
export type AlertaIndicador = {
  id: number; indicador_chave: string; indicador_label: string;
  operador: "<" | "<=" | ">" | ">="; valor_limite: number; ativo: boolean;
  valor_atual: number | null; disparado: boolean; criado_em: string;
};

export async function fetchCatalogoIndicadores(): Promise<IndicadorCatalogo[]> {
  const res = await authFetch(`${API}/alertas-indicador/catalogo`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao listar catálogo de indicadores");
  return res.json();
}

export async function fetchAlertasIndicador(): Promise<AlertaIndicador[]> {
  const res = await authFetch(`${API}/alertas-indicador`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao listar alertas de indicador");
  return res.json();
}

export async function criarAlertaIndicador(dados: { indicador_chave: string; operador: string; valor_limite: number }): Promise<AlertaIndicador> {
  const res = await authFetch(`${API}/alertas-indicador`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar alerta"); }
  return res.json();
}

export async function editarAlertaIndicador(id: number, dados: { operador?: string; valor_limite?: number; ativo?: boolean }): Promise<AlertaIndicador> {
  const res = await authFetch(`${API}/alertas-indicador/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao editar alerta"); }
  return res.json();
}

export async function excluirAlertaIndicador(id: number): Promise<void> {
  const res = await authFetch(`${API}/alertas-indicador/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir alerta"); }
}

// ── Onboarding (checklist guiado de primeiro acesso) ──
// Ver backend/fazenda/api/routers/onboarding.py — passos fixos no backend;
// aqui só consumimos o estado (o que já foi concluído/dispensado).
export type OnboardingPasso = { chave: string; label: string; rota: string; concluido: boolean };
export type OnboardingEstado = { passos: OnboardingPasso[]; dispensado: boolean; tudo_concluido: boolean };

export async function fetchOnboarding(): Promise<OnboardingEstado> {
  const res = await authFetch(`${API}/onboarding`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao carregar onboarding");
  return res.json();
}

export async function concluirPassoOnboarding(chave: string): Promise<OnboardingEstado> {
  const res = await authFetch(`${API}/onboarding/passos/${encodeURIComponent(chave)}/concluir`, { method: "POST" });
  if (!res.ok) throw new Error("Erro ao concluir passo");
  return res.json();
}

export async function dispensarOnboarding(): Promise<OnboardingEstado> {
  const res = await authFetch(`${API}/onboarding/dispensar`, { method: "POST" });
  if (!res.ok) throw new Error("Erro ao dispensar onboarding");
  return res.json();
}

// ── Filtros salvos (genérico — qualquer tela de relatório pode adotar) ──
// Ver backend/fazenda/api/routers/filtros_salvos.py. `tela` namespacia os
// filtros salvos (ex.: "financeiro_extrato"); `filtros` é um objeto livre,
// específico do formato de estado da tela que está salvando/aplicando.
export type FiltroSalvo = { id: number; tela: string; nome: string; filtros: Record<string, any>; criado_em: string };

export async function fetchFiltrosSalvos(tela: string): Promise<FiltroSalvo[]> {
  const res = await authFetch(`${API}/filtros-salvos?tela=${encodeURIComponent(tela)}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erro ao listar filtros salvos");
  return res.json();
}

export async function criarFiltroSalvo(dados: { tela: string; nome: string; filtros: Record<string, any> }): Promise<FiltroSalvo> {
  const res = await authFetch(`${API}/filtros-salvos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar filtro"); }
  return res.json();
}

export async function excluirFiltroSalvo(id: number): Promise<void> {
  const res = await authFetch(`${API}/filtros-salvos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir filtro salvo"); }
}

// ── Protocolos personalizados (motor de protocolos configurável) ──
// Ver backend/fazenda/api/routers/cadastro/protocolos_customizados.py (molde)
// e backend/fazenda/api/routers/protocolos_customizados.py (lançar/ativos/cancelar).
export type EtapaProtocoloCustomizado = {
  dia: number; descricao_evento: string; insumo_padrao?: string | null;
  dose?: number | null; unidade?: string | null; via?: string | null;
  observacao?: string | null; ordem?: number;
};
export type ProtocoloCustomizado = {
  id: number; nome: string; categoria: string;
  // Classificação macro exigida pela Central de Protocolos — sem isto, o
  // protocolo continua funcionando na Agenda mas fica fora dos filtros de
  // Acompanhamento/Histórico (ver LinhaCentralProtocolos.tipo).
  tipo: "produtivo" | "reprodutivo" | "sanitario" | null;
  dia_inicial: number;
  observacao: string | null; ativo: boolean; duracao_dias: number;
  etapas: EtapaProtocoloCustomizado[];
};
export const CATEGORIAS_PROTOCOLO_CUSTOM: [string, string][] = [
  ["Atividades", "Atividades (geral)"], ["Reprodutivo", "Reprodutivo"], ["Produção", "Produção"],
  ["sanidade", "Sanidade"], ["Rebanho", "Rebanho"], ["Gestão/Financeiro", "Gestão/Financeiro"],
];
export const TIPOS_PROTOCOLO_CUSTOM: [string, string][] = [
  ["produtivo", "Produtivo"], ["reprodutivo", "Reprodutivo"], ["sanitario", "Sanitário"],
];

export async function fetchProtocolosCustomizados(): Promise<ProtocoloCustomizado[]> {
  const res = await authFetch(`${API}/cadastro/protocolos-customizados`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos personalizados error: ${res.status}`);
  return res.json();
}
export async function criarProtocoloCustomizado(dados: {
  nome: string; categoria: string; tipo?: string | null; dia_inicial: number; observacao?: string | null; ativo?: boolean;
  etapas: EtapaProtocoloCustomizado[];
}): Promise<ProtocoloCustomizado> {
  const res = await authFetch(`${API}/cadastro/protocolos-customizados`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar protocolo"); }
  return res.json();
}
export async function atualizarProtocoloCustomizado(id: number, dados: {
  nome: string; categoria: string; tipo?: string | null; dia_inicial: number; observacao?: string | null; ativo?: boolean;
  etapas: EtapaProtocoloCustomizado[];
}): Promise<ProtocoloCustomizado> {
  const res = await authFetch(`${API}/cadastro/protocolos-customizados/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar protocolo"); }
  return res.json();
}
export async function excluirProtocoloCustomizado(id: number): Promise<void> {
  const res = await authFetch(`${API}/cadastro/protocolos-customizados/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir protocolo"); }
}

export async function fetchProtocolosCustomizadosParaLancar(): Promise<ProtocoloCustomizado[]> {
  const res = await authFetch(`${API}/protocolos-customizados`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos personalizados error: ${res.status}`);
  return res.json();
}
export async function lancarProtocoloCustomizado(dados: {
  protocolo_id: number; animais: string[]; lote?: string | null; data_inicio: string;
  responsavel?: string | null; observacao?: string | null;
}): Promise<{ criado: boolean; lancamento_id: number; eventos_criados: number; animais: number; aviso?: string }> {
  const res = await authFetch(`${API}/protocolos-customizados/lancar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar protocolo"); }
  return res.json();
}
export type ProtocoloCustomizadoAtivo = {
  lancamento_id: number; nome_protocolo: string; categoria: string; data_inicio: string; lote: string | null;
  responsavel: string | null; total_etapas: number; pendentes: number; animais: string[];
  proxima_etapa: string; proxima_data: string;
};
export async function fetchProtocolosCustomizadosAtivos(): Promise<ProtocoloCustomizadoAtivo[]> {
  const res = await authFetch(`${API}/protocolos-customizados/ativos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos personalizados ativos error: ${res.status}`);
  return res.json();
}
export async function cancelarLancamentoProtocoloCustomizado(lancamentoId: number): Promise<void> {
  const res = await authFetch(`${API}/protocolos-customizados/${lancamentoId}/cancelar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao cancelar lançamento"); }
}

// ── Lida — tarefas gerais da fazenda (não são protocolo de animal) ──────────
// Sem Tipo produtivo/reprodutivo/sanitário — ver comentário em
// fazenda/models/lida.py (backend) para a diferença em relação ao Protocolo
// Customizado. Duas formas de agendar: "periodo" (D0, D1... como os demais
// protocolos) ou "frequencia" (a cada N dias, entre início e fim).
export type EtapaLida = {
  dia_inicio: number; dia_fim?: number | null; descricao_evento: string;
  insumo_padrao?: string | null; insumo_dose?: number | null; insumo_unidade?: string | null;
  foto_obrigatoria?: boolean; ordem?: number;
};
export type Lida = {
  id: number; nome: string; modo: "periodo" | "frequencia"; dia_inicial: number;
  frequencia_dias: number | null; descricao_evento: string | null;
  insumo_padrao: string | null; insumo_dose: number | null; insumo_unidade: string | null;
  foto_obrigatoria: boolean; dar_baixa_estoque: boolean; vincular_financeiro: boolean;
  observacao: string | null; ativo: boolean; etapas: EtapaLida[]; duracao_dias: number | null;
};
type LidaPayload = {
  nome: string; modo: "periodo" | "frequencia"; dia_inicial?: number;
  frequencia_dias?: number | null; descricao_evento?: string | null;
  insumo_padrao?: string | null; insumo_dose?: number | null; insumo_unidade?: string | null;
  foto_obrigatoria?: boolean; dar_baixa_estoque?: boolean; vincular_financeiro?: boolean;
  observacao?: string | null; ativo?: boolean; etapas?: EtapaLida[];
};

export async function fetchLidas(): Promise<Lida[]> {
  const res = await authFetch(`${API}/cadastro/lidas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lida error: ${res.status}`);
  return res.json();
}
export async function criarLida(dados: LidaPayload): Promise<Lida> {
  const res = await authFetch(`${API}/cadastro/lidas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar lida"); }
  return res.json();
}
export async function atualizarLida(id: number, dados: LidaPayload): Promise<Lida> {
  const res = await authFetch(`${API}/cadastro/lidas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao atualizar lida"); }
  return res.json();
}
export async function excluirLida(id: number): Promise<void> {
  const res = await authFetch(`${API}/cadastro/lidas/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir lida"); }
}

export async function fetchLidasParaLancar(): Promise<Lida[]> {
  const res = await authFetch(`${API}/lida`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lida error: ${res.status}`);
  return res.json();
}
export async function lancarLida(dados: {
  lida_id: number; animais?: string[]; lote?: string | null; data_inicio: string; data_fim?: string | null;
  responsavel?: string | null; observacao?: string | null;
}): Promise<{ criado: boolean; lancamento_id: number; eventos_criados: number; animais: number; aviso?: string }> {
  const res = await authFetch(`${API}/lida/lancar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar lida"); }
  return res.json();
}
export type LidaAtiva = {
  lancamento_id: number; nome_protocolo: string; modo: "periodo" | "frequencia"; data_inicio: string;
  alvo_tipo: "tarefa_fazenda" | "lote" | "animal"; lote: string | null; responsavel: string | null;
  total_etapas: number; pendentes: number; animais: string[];
  proxima_etapa: string; proxima_data: string; proxima_foto_obrigatoria: boolean;
};
export async function fetchLidasAtivas(): Promise<LidaAtiva[]> {
  const res = await authFetch(`${API}/lida/ativos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lida ativos error: ${res.status}`);
  return res.json();
}

// ── Consumo diário de alimento e sobra de cocho (Lançamentos > Alimentação) ──
// `lote` é o INT da dieta (DietaLancamento.lote), não o código de 2 dígitos do
// cadastro nem o "01 - Nome" de Animal.grupo_primario — o lançamento de consumo
// só existe ancorado numa dieta ativa e fala a língua dela. A ponte para o
// cadastro é `String(lote).padStart(2, "0")`.
export type ItemDietaDoLote = {
  alimento: string; alimento_id: number | null;
  quantidade: number; unidade: string;          // quantidade programada
  por_cabeca: number | null;                    // já resolvido pelo backend
  converte_para_kg: boolean;                    // false = fica fora do rateio da sobra
};
export type ConsumoDoDia = {
  lote: number; data: string; num_animais: number | null;
  itens: { alimento: string; quantidade: number; unidade: string; kg_equivalente: number | null }[];
  kg_fornecido_total: number;
  sobra_kg: number | null;
  sobra_pct: number | null;
  dentro_da_faixa: boolean | null;              // null = sem sobra lançada ainda
};
export type ConsumoItemIn = {
  alimento: string; alimento_id?: number | null; quantidade: number; unidade: string;
};
export type RespostaConsumo = {
  ok: boolean;
  // Avisos vindos do motor de estoque (saldo negativo etc.). Hoje os avisos da
  // baixa de alimentação são descartados pelo chamador; com lançamento manual
  // eles passam a ter destinatário — mostre na tela.
  avisos: string[];
};

export async function fetchDietaDoLote(lote: number): Promise<{ itens: ItemDietaDoLote[]; base_quantidade: string } | null> {
  const res = await authFetch(`${API}/alimentacao/consumo/dieta-do-lote?lote=${lote}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Dieta do lote error: ${res.status}`);
  return res.json();
}
export async function fetchConsumoDoDia(lote: number, data: string): Promise<ConsumoDoDia> {
  const res = await authFetch(`${API}/alimentacao/consumo?lote=${lote}&data=${data}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Consumo do dia error: ${res.status}`);
  return res.json();
}
export async function lancarConsumo(dados: {
  lote: number; data: string; num_animais?: number | null;
  origem: "animais" | "kg"; itens: ConsumoItemIn[];
}): Promise<RespostaConsumo> {
  const res = await authFetch(`${API}/alimentacao/consumo`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar consumo"); }
  return res.json();
}
export async function excluirConsumo(id: number) {
  const res = await authFetch(`${API}/alimentacao/consumo/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir consumo"); }
  return res.json();
}
// Relançar a sobra no mesmo dia SUBSTITUI (é medição do dia), ao contrário do
// consumo, que soma (é o vagão passando várias vezes).
export async function lancarSobra(dados: { lote: number; data: string; kg_sobra: number }) {
  const res = await authFetch(`${API}/alimentacao/sobra`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao lançar sobra"); }
  return res.json();
}
export type RelatorioSobra = {
  total_kg_sobra: number; total_kg_fornecido: number; pct_medio: number | null;
  // `pct_do_total` é a fatia do TOTAL DE SOBRA do período que este alimento
  // respondeu — não a proporção dele na dieta. Nomear errado aqui faria a
  // tela exibir "% da dieta" com um número que não é isso.
  por_alimento: { alimento: string; kg_sobra: number; pct_do_total: number }[];
  // Itens da dieta cuja unidade não converte para kg (litro, dose, unidade):
  // ficam FORA do rateio, e o relatório diz quais em vez de silenciar.
  itens_sem_conversao: string[];
};
export async function fetchRelatorioSobra(p: { de: string; ate: string; lote?: number | null }): Promise<RelatorioSobra> {
  const qs = new URLSearchParams({ de: p.de, ate: p.ate });
  if (p.lote != null) qs.set("lote", String(p.lote));
  const res = await authFetch(`${API}/alimentacao/sobra/relatorio?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatório de sobra error: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Vale-alimentação — a FORMA de pagamento e a trava da OJ 413 (set/2026)
//
// Acrescentados no fim do arquivo, e não junto de `PessoaDados`, para não
// tocar num bloco em revisão noutro pull request. Estruturalmente dá no mesmo:
// `criarPessoa`/`atualizarPessoa` recebem o payload como VARIÁVEL (ver
// `CadastroPessoas.tsx::paraPayload`), e o TypeScript só recusa propriedade
// extra em literal de objeto passado direto.
// ---------------------------------------------------------------------------

/** Como o vale-alimentação é pago — o eixo que decide se ele entra ou não nas
 *  bases de INSS, FGTS, 13º e férias. A árvore inteira, com o fundamento de
 *  cada linha, está em
 *  `backend/fazenda/rules/vale_alimentacao.py::natureza_do_vale_alimentacao`:
 *
 *  - `dinheiro`   → SALARIAL, integra tudo (CLT, art. 457, §2º — a exclusão da
 *                   base vale "vedado seu pagamento em dinheiro"). E é
 *                   infração autônoma à Lei 14.442/2022, multa de R$ 5.000 a
 *                   R$ 50.000, dobrada na reincidência;
 *  - `cartao`     → indenizatória, com ou sem PAT (OJ 133 da SDI-1 do TST;
 *                   Solução de Consulta COSIT nº 35/2019 da Receita Federal);
 *  - `in_natura`  → salário-utilidade, INTEGRA (CLT, art. 458, caput), salvo
 *                   se a fazenda for inscrita no PAT (OJ 133).
 *
 *  NÃO existe valor padrão: o servidor recusa o cadastro com o benefício
 *  ligado e a forma em branco. Escolher por conta própria na tela seria tirar
 *  da base do INSS uma verba que talvez tivesse de entrar. */
export type FormaValeAlimentacao = "dinheiro" | "cartao" | "in_natura";

/** Os dois campos novos do cadastro de vale-alimentação. `undefined` na trava
 *  significa "não mexe no que está gravado": a tela só mostra o campo para
 *  administrador, e mandar `false` num PUT de usuário comum desligaria em
 *  silêncio uma proteção que só administrador pode tirar. */
export type ValeAlimentacaoEnquadramentoIn = {
  vale_alimentacao_forma?: FormaValeAlimentacao;
  vale_alimentacao_natureza_travada_salarial?: boolean;
};
