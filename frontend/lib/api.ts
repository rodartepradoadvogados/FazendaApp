// Funções de comunicação com o backend FastAPI
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
export type FazendaAtual = { id: number; nome: string; cidade?: string | null; uf?: string | null; vinculo_contador?: boolean; vinculo_consultor?: boolean };
export function getFazendaAtual(): FazendaAtual | null {
  if (typeof window === "undefined") return null;
  try { return JSON.parse(localStorage.getItem("fazenda_atual") || "null"); } catch { return null; }
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
    localStorage.removeItem("manter_conectado");
    location.href = "/login";
  }
}
// Mapa rota → módulo (para menu e bloqueio de páginas).
export const ROTA_MODULO: Record<string, string> = {
  "/": "capa", "/indicadores": "indicadores", "/agenda": "agenda", "/lancamentos": "lancamentos", "/protocolos": "lancamentos",
  "/reproducao": "reproducao", "/analise-reprodutiva": "analise", "/relatorios": "reproducao", "/rebanho": "rebanho",
  "/producao": "producao", "/alimentacao": "alimentacao", "/sanidade": "sanidade", "/recria": "recria",
  "/financeiro": "financeiro", "/estoque": "estoque", "/pedidos": "pedidos", "/parametros": "parametros", "/upload": "upload",
  "/analise-relatorios": "indicadores",
};

// Permissão de módulo para o usuário logado (admin tem tudo).
export function podeModulo(mod: string): boolean {
  const u = getUsuario();
  if (!u) return false;
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
  pessoa_id?: number; nome?: string; // uma das duas: pessoa_id (fazenda) ou nome (conta sem fazenda, ex.: equipe CowData)
}) {
  const res = await fetch(`${API}/auth/usuarios`, {
    method: "POST", headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar usuário"); }
  return res.json();
}
export async function atualizarUsuario(id: number, dados: any) {
  const res = await fetch(`${API}/auth/usuarios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar"); }
  return res.json();
}

export async function login(username: string, senha: string, manterConectado = false) {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, senha, manter_conectado: manterConectado }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || "Usuário ou senha inválidos");
  }
  const data = await res.json();
  localStorage.setItem("token", data.token);
  localStorage.setItem("usuario", JSON.stringify(data.usuario));
  if (data.fazenda_atual) localStorage.setItem("fazenda_atual", JSON.stringify(data.fazenda_atual));
  else localStorage.removeItem("fazenda_atual");
  // Sessão de validade longa (90 dias) — ver TOKEN_VALIDADE_LONGA_S no backend.
  if (manterConectado) localStorage.setItem("manter_conectado", "1");
  else localStorage.removeItem("manter_conectado");
  // Espelha a sessão no armazenamento nativo (@capacitor/preferences), mais
  // durável que o localStorage da WebView — só quando "Manter conectado" está
  // marcado (ver lib/nativo.ts::salvarSessaoNativa). Fora do app nativo não
  // faz nada. Best-effort, sem aguardar: não pode atrasar o login.
  if (manterConectado) {
    import("@/lib/nativo")
      .then(({ salvarSessaoNativa }) => salvarSessaoNativa(data.token, data.usuario, data.fazenda_atual || null))
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao selecionar fazenda"); }
  const data = await res.json();
  localStorage.setItem("token", data.token);
  localStorage.setItem("fazenda_atual", JSON.stringify(data.fazenda_atual));
  // Mantém a cópia nativa sincronizada com o token novo (o backend reemite o
  // token ao trocar de fazenda) — mesma lógica de login(), ver lib/nativo.ts.
  if (manterConectadoAtivo()) {
    import("@/lib/nativo")
      .then(({ salvarSessaoNativa }) => salvarSessaoNativa(data.token, getUsuario(), data.fazenda_atual))
      .catch(() => {});
  }
  return data.fazenda_atual;
}

export async function fetchMinhasFazendas(): Promise<FazendaAtual[]> {
  const res = await authFetch(`${API}/fazendas/minhas`);
  if (!res.ok) throw new Error(`Fazendas error: ${res.status}`);
  return res.json();
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
  | "planejamento" | "pedidos" | "estoque" | "alimentacao" | "agricultura" | "consultor";
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar fazenda"); }
  return res.json();
}
export async function atualizarFazenda(fazendaId: number, dados: {
  nome?: string; cidade?: string; uf?: string;
  tipo_documento?: string; documento?: string; endereco?: string; cep?: string;
  representante_nome?: string; representante_cpf?: string; exige_aprovacao_suporte?: boolean;
}): Promise<Fazenda> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar fazenda"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao definir contrato"); }
  return res.json();
}
export async function aprovarContratoFazenda(fazendaId: number): Promise<ContratoFazenda> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/aprovar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao aprovar contrato"); }
  return res.json();
}
export async function suspenderContratoFazenda(fazendaId: number): Promise<ContratoFazenda> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/suspender`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao suspender contrato"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar preço"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao anexar contrato"); }
  return res.json();
}
export async function excluirAnexoContrato(anexoId: number): Promise<void> {
  const res = await authFetch(`${API}/fazendas/contrato/anexos/${anexoId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir anexo"); }
}
// Antes era um <a href> direto pro endpoint — mas ele exige Bearer token
// (backend/fazenda/api/routers/fazendas.py), então abrir a URL crua sem
// autenticação sempre dava 401. Segue o mesmo padrão de baixarArquivoAutenticado
// (definida mais abaixo neste arquivo).
export async function baixarAnexoContrato(anexoId: number, nomeArquivoFallback: string): Promise<void> {
  const res = await authFetch(`${API}/fazendas/contrato/anexos/${anexoId}`);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao baixar anexo"); }
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
};
export type PessoaCowDataIn = {
  nome: string; cargo: string; telefones?: string[]; emails?: string[];
  cpf_cnpj?: string | null; cep?: string | null;
  salario_base?: number | null; data_admissao?: string | null;
  observacoes?: string | null; ativo?: boolean;
};
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Erro (${res.status})`); }
  return res.json();
}

export const fetchCargosCowData = (): Promise<string[]> => _pcGet(`/equipe/cargos`);
export const fetchEquipeCowData = (): Promise<PessoaCowData[]> => _pcGet(`/equipe/pessoas`);
export const criarMembroEquipeCowData = (d: PessoaCowDataIn): Promise<PessoaCowData> => _pcSend(`/equipe/pessoas`, "POST", d);
export const editarMembroEquipeCowData = (id: number, d: PessoaCowDataIn): Promise<PessoaCowData> => _pcSend(`/equipe/pessoas/${id}`, "PUT", d);
export const excluirMembroEquipeCowData = (id: number): Promise<{ ok: boolean }> => _pcSend(`/equipe/pessoas/${id}`, "DELETE");

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
export type FazendaCofre = { id: number; nome: string; exige_aprovacao_suporte: boolean };
export type PedidoAcessoSuporte = {
  id: number; fazenda_id: number; fazenda_nome: string; usuario_id: number; solicitante_nome: string | null;
  motivo: string; status: "aguardando_aprovacao" | "aprovado" | "negado";
  aprovador_nome: string | null; pedido_em: string; decidido_em: string | null;
};
export type SessaoAcessoSuporte = {
  id: number; fazenda_id: number; fazenda_nome: string; usuario_id: number; membro_nome: string | null;
  motivo: string; iniciada_em: string; expira_em: string; encerrada_em: string | null;
  ativa: boolean; segundos_restantes: number;
};
export type AuditoriaAcessoSuporte = {
  id: number; quando: string; fazenda_id: number; fazenda_nome: string; usuario_id: number;
  membro_nome: string | null; acao: "entrada" | "saida";
};

export const fetchMotivosAcessoSuporte = (): Promise<string[]> => _pcGet(`/cofre/motivos`);
export const fetchFazendasCofre = (): Promise<FazendaCofre[]> => _pcGet(`/cofre/fazendas`);
export const fetchSessoesAtivasCofre = (): Promise<SessaoAcessoSuporte[]> => _pcGet(`/cofre/sessoes-ativas`);
export const fetchPedidosRecentesCofre = (): Promise<PedidoAcessoSuporte[]> => _pcGet(`/cofre/pedidos`);
export const fetchAuditoriaRecenteCofre = (): Promise<AuditoriaAcessoSuporte[]> => _pcGet(`/cofre/auditoria`);
export const solicitarAcessoCofre = (d: { fazenda_id: number; motivo: string }): Promise<PedidoAcessoSuporte> =>
  _pcSend(`/cofre/pedidos`, "POST", d);
export const aprovarPedidoCofre = (id: number): Promise<PedidoAcessoSuporte> => _pcSend(`/cofre/pedidos/${id}/aprovar`, "POST");
export const negarPedidoCofre = (id: number): Promise<PedidoAcessoSuporte> => _pcSend(`/cofre/pedidos/${id}/negar`, "POST");
export const encerrarSessaoCofre = (id: number): Promise<SessaoAcessoSuporte> => _pcSend(`/cofre/sessoes/${id}/encerrar`, "POST");

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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao gerar o contrato"); }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `contrato-cowdata-fazenda-${fazendaId}.html`;
  a.click();
  URL.revokeObjectURL(url);
}
export async function assinarContratoZapSign(fazendaId: number): Promise<AssinaturaZapSign> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/contrato/assinar-zapsign`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar assinatura no ZapSign"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar cobrança no Asaas"); }
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
export async function vincularUsuarioFazenda(
  fazendaId: number, dados: { username: string; contratante?: boolean; consultor?: boolean; contador?: boolean },
): Promise<{ vinculado: boolean; usuario_id: number; username: string }> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/vincular-usuario`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao vincular usuário"); }
  return res.json();
}
export async function desvincularUsuarioFazenda(fazendaId: number, usuarioId: number): Promise<void> {
  const res = await authFetch(`${API}/fazendas/${fazendaId}/vincular-usuario/${usuarioId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao desvincular usuário"); }
}

// ── Consultor independente (Fase 2C) — assinatura própria (fora de qualquer
// fazenda-tenant), fazendas gerenciadas por importação de planilha, e o modo
// Simulação (cálculo puro, nunca persistido). Ver
// backend/fazenda/models/consultores.py e fazenda/api/routers/consultores.py.
export type PlanoConsultorNome = "consultor_standard" | "consultor_gold" | "consultor_diamond";
export type PlanoConsultorCatalogo = { nome: string; preco: number; limite_fazendas: number };
export type ContratoConsultor = {
  usuario_id: number;
  status: "aguardando_aprovacao" | "ativo" | "suspenso" | null;
  plano: PlanoConsultorNome | null;
  limite_fazendas: number | null;
  data_fechamento?: string | null;
};
export type ContratoConsultorAdmin = ContratoConsultor & { username: string | null };
export type CategoriaImportacao =
  | "rebanho" | "reprodutivo" | "produtivo" | "sanitario" | "financeiro" | "estoque" | "alimentacao" | "agricultura";
export type FazendaGerenciada = {
  id: number; nome: string; produtor: string | null; cidade: string | null; uf: string | null;
  observacoes: string | null; criado_em: string;
};
export type RegistroImportado = {
  id: number; categoria: CategoriaImportacao; data_referencia: string | null;
  dados: Record<string, string>; arquivo_origem: string; criado_em: string;
};

export async function fetchPlanosConsultorCatalogo(): Promise<Record<PlanoConsultorNome, PlanoConsultorCatalogo>> {
  const res = await authFetch(`${API}/consultor/catalogo/planos`);
  if (!res.ok) throw new Error(`Catálogo de planos de consultor error: ${res.status}`);
  return res.json();
}
export async function solicitarPlanoConsultor(plano: PlanoConsultorNome): Promise<ContratoConsultor> {
  const res = await authFetch(`${API}/consultor/solicitar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plano }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao solicitar plano"); }
  return res.json();
}
export async function fetchMeuContratoConsultor(): Promise<ContratoConsultor> {
  const res = await authFetch(`${API}/consultor/meu-contrato`);
  if (!res.ok) throw new Error(`Meu contrato de consultor error: ${res.status}`);
  return res.json();
}
export async function fetchContratosConsultor(): Promise<ContratoConsultorAdmin[]> {
  const res = await authFetch(`${API}/consultor/todos`);
  if (!res.ok) throw new Error(`Contratos de consultor error: ${res.status}`);
  return res.json();
}
export async function aprovarContratoConsultor(usuarioId: number): Promise<ContratoConsultor> {
  const res = await authFetch(`${API}/consultor/${usuarioId}/aprovar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao aprovar contrato"); }
  return res.json();
}
export async function suspenderContratoConsultor(usuarioId: number): Promise<ContratoConsultor> {
  const res = await authFetch(`${API}/consultor/${usuarioId}/suspender`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao suspender contrato"); }
  return res.json();
}

export async function fetchFazendasGerenciadas(): Promise<FazendaGerenciada[]> {
  const res = await authFetch(`${API}/consultor/fazendas`);
  if (!res.ok) throw new Error(`Fazendas gerenciadas error: ${res.status}`);
  return res.json();
}
export async function criarFazendaGerenciada(dados: {
  nome: string; produtor?: string; cidade?: string; uf?: string; observacoes?: string;
}): Promise<FazendaGerenciada> {
  const res = await authFetch(`${API}/consultor/fazendas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cadastrar fazenda gerenciada"); }
  return res.json();
}
export async function excluirFazendaGerenciada(fazendaGerenciadaId: number): Promise<void> {
  const res = await authFetch(`${API}/consultor/fazendas/${fazendaGerenciadaId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir fazenda gerenciada"); }
}
export async function importarPlanilhaGerenciada(
  fazendaGerenciadaId: number, categoria: CategoriaImportacao, file: File,
): Promise<{ categoria: string; criados: number }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("categoria", categoria);
  const res = await authFetch(`${API}/consultor/fazendas/${fazendaGerenciadaId}/importar`, { method: "POST", body: fd });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao importar planilha"); }
  return res.json();
}
export async function fetchIndicadoresGerenciados(
  fazendaGerenciadaId: number, categoria?: CategoriaImportacao,
): Promise<RegistroImportado[]> {
  const qs = categoria ? `?categoria=${categoria}` : "";
  const res = await authFetch(`${API}/consultor/fazendas/${fazendaGerenciadaId}/indicadores${qs}`);
  if (!res.ok) throw new Error(`Indicadores importados error: ${res.status}`);
  return res.json();
}
export async function excluirRegistroImportado(fazendaGerenciadaId: number, registroId: number): Promise<void> {
  const res = await authFetch(`${API}/consultor/fazendas/${fazendaGerenciadaId}/importacoes/${registroId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir registro importado"); }
}

export type SimulacaoIn = {
  vacas_lactacao: number; producao_media_litro_vaca_dia: number; preco_litro: number;
  custo_alimentar_vaca_dia: number; outros_custos_mensais?: number; taxa_prenhez_pct?: number | null;
};
export type SimulacaoOut = {
  producao_total_litro_dia: number; producao_total_litro_mes: number; receita_mes: number;
  custo_alimentar_mes: number; custo_total_mes: number; margem_mes: number;
  custo_por_litro: number | null; margem_por_litro: number | null; taxa_prenhez_pct: number | null;
};
export async function calcularSimulacaoConsultor(dados: SimulacaoIn): Promise<SimulacaoOut> {
  const res = await authFetch(`${API}/consultor/simulacao/calcular`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao calcular simulação"); }
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
    throw new Error(d.detail || "Não foi possível enviar o e-mail de redefinição.");
  }
}

export async function redefinirSenha(token: string, novaSenha: string): Promise<void> {
  const res = await fetch(`${API}/auth/redefinir-senha`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, nova_senha: novaSenha }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || "Não foi possível redefinir a senha.");
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar preferência"); }
  const usuario = await res.json();
  try {
    const atual = getUsuario();
    if (atual) localStorage.setItem("usuario", JSON.stringify({ ...atual, ...usuario }));
  } catch { /* ignore */ }
  return usuario;
}

// fetch com token; redireciona ao login se a sessão cair (401).
// Exportado para a fila offline do app móvel (lib/offline.ts) reutilizar.
export function authFetch(url: string, opts: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(opts.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...opts, headers, cache: "no-store" }).then((res) => {
    if (res.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      logout();
    }
    return res;
  });
}

// Traduz o "Failed to fetch" (erro de rede do navegador) numa mensagem acionável.
// Esse erro NÃO é HTTP — significa que a requisição não chegou a receber resposta:
// API fora do ar, NEXT_PUBLIC_API_URL não configurada/errada, ou CORS bloqueado.
function netError(e: unknown): Error {
  if (e instanceof TypeError) {
    return new Error(
      `Sem conexão com a API (${API}). ` +
        `Verifique se o backend está no ar e se NEXT_PUBLIC_API_URL aponta para ele (e se o CORS libera este site).`
    );
  }
  return e instanceof Error ? e : new Error(String(e));
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

export type MedicamentoIatf = { produto: string; estoque_id?: number | null; dose?: number | null; unidade?: string | null; via?: string | null };
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
};
export async function marcarEventoRealizado(eventoId: string, animais?: string[], medicamentos?: MedicamentoIatf[], extras?: RealizadoExtras) {
  const res = await authFetch(`${API}/agenda/realizados`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      evento_id: eventoId, animais: animais || undefined, medicamentos: medicamentos && medicamentos.length ? medicamentos : undefined,
      ...(extras || {}),
    }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao marcar como realizado"); }
  return res.json();
}

export async function desmarcarEventoRealizado(eventoId: string) {
  const res = await authFetch(`${API}/agenda/realizados/${eventoId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erro ao desfazer");
  return res.json();
}

export async function aplicarBstLote(dados: {
  numeros_matriz: string[]; data_aplicacao: string; produto?: string; dose?: number | null; unidade?: string | null; responsavel?: string; aplicado?: boolean;
}) {
  const res = await authFetch(`${API}/agenda/bst/aplicar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar aplicação de BST"); }
  return res.json();
}

export async function marcarInaptaBst(dados: { numeros_matriz: string[]; inapta?: boolean }) {
  const res = await authFetch(`${API}/agenda/bst/marcar-inapta`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao marcar animal como inapto"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar indução de lactação"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar protocolo de indução de lactação"); }
  return res.json();
}
export async function atualizarProtocoloInducaoLactacao(id: number, dados: ProtocoloInducaoLactacaoPayload) {
  const res = await authFetch(`${API}/cadastro/protocolos-inducao-lactacao/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar protocolo de indução de lactação"); }
  return res.json();
}

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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Ficha do animal error: ${res.status}`); }
  return res.json();
}

export async function fetchIndicadores(data?: string) {
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
type ServicoEditPayload = {
  data_servico?: string; tipo_servico?: string; reprodutor?: string; tipo_semen?: string; inseminador?: string;
  data_diagnostico?: string; diagnostico?: string; metodo_diagnostico?: string;
  data_perda_prenhez?: string; motivo_perda_prenhez?: string;
};
export async function atualizarServico(id: number, dados: ServicoEditPayload) {
  const res = await authFetch(`${API}/reproducao/servicos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar serviço"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar parto"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao verificar mãe"); }
  return res.json();
}
export async function atualizarSecagem(id: number, dados: { data_secagem?: string; motivo?: string; escore_condicao_corporal?: number | null; observacao?: string }) {
  const res = await authFetch(`${API}/reproducao/secagens/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar secagem"); }
  return res.json();
}

export type IndicadoresMensais = { meses: string[]; series: Record<string, (number | null)[]> };
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao gerar relatório personalizado"); }
  return res.json() as Promise<{ colunas: ParametroRelatorioPersonalizado[]; linhas: Record<string, any>[]; resumo: ResumoRelatorioPersonalizado }>;
}

// ── Relatórios gerenciais e de manejo (Reprodução) ──
export async function fetchRelatoriosManejo() {
  const res = await authFetch(`${API}/relatorios/manejo`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Relatórios de manejo error: ${res.status}`);
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
    throw new Error(d.detail || `Sugestão de acasalamento error: ${res.status}`);
  }
  return res.json() as Promise<SugestaoAcasalamento>;
}
export async function criarServicoLote(dados: {
  animais: string[]; data_servico: string; tipo: "cio_natural" | "iatf" | "monta_natural";
  reprodutor?: string; responsavel?: string; protocolo_lancamento_id?: number | null; auto_lancar_iatf?: boolean;
  tipo_semen?: string | null;
}) {
  const res = await authFetch(`${API}/reproducao/servico-lote`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar inseminação"); }
  return res.json() as Promise<{ criados: number; incompativeis: string[]; tipo: string }>;
}
type EstoqueSemenDados = { touro_nome: string; codigo?: string | null; naab?: string | null; central?: string | null; tipo: string; doses: number; valor_unitario?: number | null; local_armazenamento?: string | null; observacao?: string | null; ativo?: boolean };
export async function criarEstoqueSemen(dados: EstoqueSemenDados) {
  const res = await authFetch(`${API}/cadastro/estoque-semen`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cadastrar sêmen"); }
  return res.json();
}
export async function atualizarEstoqueSemen(id: number, dados: EstoqueSemenDados) {
  const res = await authFetch(`${API}/cadastro/estoque-semen/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar sêmen"); }
  return res.json();
}
export async function excluirEstoqueSemen(id: number) {
  const res = await authFetch(`${API}/cadastro/estoque-semen/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir sêmen"); }
  return res.json();
}

export async function salvarDiagnostico(dados: {
  numero_matriz: string; data_diagnostico: string; resultado: "retoque" | "reconfirmada" | "negativo" | "indefinido"; metodo?: string;
}) {
  const res = await authFetch(`${API}/reproducao/diagnostico`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar diagnóstico"); }
  return res.json();
}

export type AgendaVetItem = {
  numero_matriz: string; categoria: string; peso: number | null;
  dias_inseminada: number | null; data_servico: string | null;
  tocada: boolean; reconfirmada: boolean;
  diagnostico: string | null; diagnostico_reconfirmacao: string | null;
  atrasada?: boolean; dias_para_parto?: number | null; motivo?: string;
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
  { chave: "verificar_aptidao", rotulo: "Verificar aptidão" },
  { chave: "novilhas_gestantes", rotulo: "Novilhas gestantes" },
  { chave: "vacas_gestantes", rotulo: "Vacas gestantes" },
  { chave: "verificar_pre_parto", rotulo: "Verificar pré-parto" },
  { chave: "vazias_por_diagnostico", rotulo: "Vazias por diagnóstico" },
  { chave: "pendentes_classificacao", rotulo: "Pendentes de classificação" },
  { chave: "observacao_cio", rotulo: "Observação de cio" },
];

export async function registrarReconfirmacao(dados: {
  numero_matriz: string; data_reconfirmacao: string; resultado: "positivo" | "negativo";
}) {
  const res = await authFetch(`${API}/reproducao/reconfirmacao`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar reconfirmação"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao enviar diagnóstico por e-mail"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar perda de prenhez"); }
  return res.json();
}

// Abre lactação de um animal sem parto associado (popup pós-aborto — "deseja
// abrir lactação para o animal X?").
export async function abrirLactacao(numeroMatriz: string) {
  const res = await authFetch(`${API}/reproducao/animais/${encodeURIComponent(numeroMatriz)}/abrir-lactacao`, {
    method: "POST",
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao abrir lactação"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar fornecedor"); }
  return res.json();
}
export async function atualizarFornecedor(id: number, dados: { nome: string; tipo: string; categoria?: string; cnpj_cpf?: string; telefone?: string; email?: string; observacoes?: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/fornecedores/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar fornecedor"); }
  return res.json();
}

// ── Pessoas (Configurações > Cadastro) ──
export async function fetchPessoas() {
  const res = await authFetch(`${API}/cadastro/pessoas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Pessoas error: ${res.status}`);
  return res.json();
}
type PessoaDados = {
  nome: string; tipos: string[]; telefones?: string[]; emails?: string[]; cpf_cnpj?: string; cep?: string;
  observacoes?: string; ativo?: boolean; salario_base?: number; data_admissao?: string;
  rg?: string; data_nascimento?: string; genero?: string; estado_civil?: string;
  endereco_rua?: string; endereco_numero?: string; endereco_bairro?: string; endereco_cidade?: string; endereco_uf?: string;
};
export async function criarPessoa(dados: PessoaDados) {
  const res = await authFetch(`${API}/cadastro/pessoas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar pessoa"); }
  return res.json();
}
export async function atualizarPessoa(id: number, dados: PessoaDados) {
  const res = await authFetch(`${API}/cadastro/pessoas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar pessoa"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar tipo de pessoa"); }
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
};
export async function criarFolhaPagamento(dados: FolhaPagamentoDados) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar folha de pagamento"); }
  return res.json();
}
export async function atualizarFolhaPagamento(id: number, dados: FolhaPagamentoDados) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar folha de pagamento"); }
  return res.json();
}
export async function excluirFolhaPagamento(id: number) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir lançamento de folha"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar guia de FGTS/DCTF"); }
  return res.json();
}
export async function fetchGuiasFolhaEncargo(): Promise<GuiaFolhaEncargo[]> {
  const res = await authFetch(`${API}/cadastro/folha-pagamento/guias`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Guias de FGTS/DCTF error: ${res.status}`);
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
  status: "pendente" | "pago";
  pode_excluir: boolean;
  vencido: boolean;
};
export async function fetchFolhaPagamentoUnificada(): Promise<LinhaFolhaUnificada[]> {
  const res = await authFetch(`${API}/cadastro/folha-pagamento-unificada`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Folha de pagamento (unificada) error: ${res.status}`);
  return res.json();
}
export async function excluirParcelaEmpreitada(id: number) {
  const res = await authFetch(`${API}/cadastro/empreitadas/parcelas/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir parcela de empreitada"); }
  return res.json();
}
export async function excluirParcelaContrato(id: number) {
  const res = await authFetch(`${API}/cadastro/contratos/parcelas/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir parcela de contrato"); }
  return res.json();
}
export async function atualizarParcelaEmpreitada(id: number, dados: { data_vencimento: string; valor: number }) {
  const res = await authFetch(`${API}/cadastro/empreitadas/parcelas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar parcela de empreitada"); }
  return res.json();
}
export async function atualizarParcelaContrato(id: number, dados: { data_vencimento: string; valor: number }) {
  const res = await authFetch(`${API}/cadastro/contratos/parcelas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar parcela de contrato"); }
  return res.json();
}
export async function redistribuirParcelasEmpreitada(empreitadaId: number) {
  const res = await authFetch(`${API}/cadastro/empreitadas/${empreitadaId}/parcelas/redistribuir`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao redistribuir parcelas"); }
  return res.json();
}
export async function redistribuirParcelasContrato(contratoId: number) {
  const res = await authFetch(`${API}/cadastro/contratos/${contratoId}/parcelas/redistribuir`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao redistribuir parcelas"); }
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
export async function excluirVale(valeId: number) {
  const res = await authFetch(`${API}/cadastro/vales/${valeId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir vale"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar empreitada"); }
  return res.json();
}
export async function concluirEtapaEmpreitada(empreitadaId: number, etapaId: number) {
  const res = await authFetch(`${API}/cadastro/empreitadas/${empreitadaId}/etapas/${etapaId}/concluir`, { method: "PUT" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao concluir etapa"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar contrato"); }
  return res.json();
}
export async function encerrarContrato(id: number) {
  const res = await authFetch(`${API}/cadastro/contratos/${id}/encerrar`, { method: "PUT" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao encerrar contrato"); }
  return res.json();
}

// ── Diária (Financeiro > Ações > Folha de Pagamento) ──
export async function fetchDiarias() {
  const res = await authFetch(`${API}/cadastro/diarias`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Diárias error: ${res.status}`);
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar diária"); }
  return res.json();
}
export async function atualizarDiaria(diariaId: number, dados: { data_inicio: string; data_fim?: string | null; ajuste_numero_diarias?: number | null }) {
  const res = await authFetch(`${API}/cadastro/diarias/${diariaId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar diária"); }
  return res.json();
}
export async function registrarPagamentoDiaria(diariaId: number, dados: { data_pagamento: string; valor: number; observacao?: string }) {
  const res = await authFetch(`${API}/cadastro/diarias/${diariaId}/pagamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar pagamento"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar parâmetro padrão"); }
  return res.json();
}
export async function responderAuditoriaDiaria(auditoriaId: number, diasTrabalhados: number) {
  const res = await authFetch(`${API}/cadastro/diarias/auditorias/${auditoriaId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dias_trabalhados: diasTrabalhados }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao responder auditoria"); }
  return res.json();
}

// ── Férias (Financeiro > Ações > Folha de Pagamento > Férias / 13º) ──
// Controle DENTRO do app (cálculo, lançamento e acompanhamento) — sem envio
// ao eSocial (fora de escopo).
export type FeriasDados = {
  pessoa_id: number; periodo_aquisitivo_inicio: string; periodo_aquisitivo_fim: string;
  dias_direito?: number; dias_gozados: number; data_inicio_gozo: string; data_fim_gozo: string;
  abono_pecuniario_dias?: number; data_pagamento?: string; status?: string; observacao?: string;
  centro_custo?: string;
};
export type RegistroFerias = FeriasDados & {
  id: number; pessoa_nome: string; valor_ferias: number; valor_terco_constitucional: number;
  valor_total: number; numero_lancamento_gerado: string | null; usuario_nome?: string | null;
  status: string;
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar férias"); }
  return res.json();
}
export async function atualizarFerias(id: number, dados: FeriasDados) {
  const res = await authFetch(`${API}/cadastro/ferias/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar férias"); }
  return res.json();
}
export async function excluirFerias(id: number) {
  const res = await authFetch(`${API}/cadastro/ferias/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir férias"); }
  return res.json();
}

// ── 13º salário (Financeiro > Ações > Folha de Pagamento > Férias / 13º) ──
export type DecimoTerceiroDados = {
  pessoa_id: number; ano: number; parcela?: string; meses_trabalhados: number;
  valor_inss?: number; valor_ir?: number; data_pagamento?: string; status?: string;
  observacao?: string; centro_custo?: string;
};
export type RegistroDecimoTerceiro = DecimoTerceiroDados & {
  id: number; pessoa_nome: string; valor_bruto: number; valor_liquido: number;
  numero_lancamento_gerado: string | null; usuario_nome?: string | null; status: string;
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar 13º salário"); }
  return res.json();
}
export async function atualizarDecimoTerceiro(id: number, dados: DecimoTerceiroDados) {
  const res = await authFetch(`${API}/cadastro/decimo-terceiro/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar 13º salário"); }
  return res.json();
}
export async function excluirDecimoTerceiro(id: number) {
  const res = await authFetch(`${API}/cadastro/decimo-terceiro/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir 13º salário"); }
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
export type CalculoRescisao = {
  tipo_rescisao: TipoRescisao;
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
  valor_total: number;
};
export type RegistroRescisao = {
  id: number; numero_lancamento: string | null; descricao: string; fornecedor_cliente: string | null;
  valor_total: number; data_competencia: string; data_vencimento: string | null; valor_pago: number | null;
};

export async function simularRescisao(dados: RescisaoDados): Promise<CalculoRescisao> {
  const res = await authFetch(`${API}/cadastro/rescisao/calcular`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao calcular rescisão"); }
  return res.json();
}
export async function criarRescisao(dados: RescisaoDados): Promise<CalculoRescisao> {
  const res = await authFetch(`${API}/cadastro/rescisao`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar rescisão"); }
  return res.json();
}
export async function fetchRescisoes(): Promise<RegistroRescisao[]> {
  const res = await authFetch(`${API}/cadastro/rescisao`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Rescisão error: ${res.status}`);
  return res.json();
}

export async function criarValeAvulso(dados: {
  origem_tipo: "empreitada" | "contrato" | "diaria"; origem_id: number; valor: number;
  forma_pagamento: string; data_pagamento: string; observacao?: string;
  // Conta bancária de onde sai o vale — obrigatória quando a forma de pagamento
  // implica saída de caixa agora (dinheiro/pix/transferência); ver _validar_conta_vale_avulso.
  conta_corrente_id?: number;
}) {
  const res = await authFetch(`${API}/cadastro/vale-avulso`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar vale"); }
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
export async function excluirValeAvulso(valeId: number) {
  const res = await authFetch(`${API}/cadastro/vale-avulso/${valeId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir vale"); }
  return res.json();
}

export async function criarAnimalFicha(dados: Record<string, any>) {
  const res = await authFetch(`${API}/cadastro/animais`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cadastrar animal"); }
  return res.json();
}
export async function atualizarAnimalFicha(numero: string, dados: Record<string, any>) {
  const res = await authFetch(`${API}/cadastro/animais/${numero}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar ficha"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cadastrar item de estoque"); }
  return res.json();
}
export async function atualizarItemEstoque(id: number, dados: Record<string, unknown>) {
  const res = await authFetch(`${API}/estoque/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar item de estoque"); }
  return res.json();
}
export async function atualizarMetaEstoque(id: number, dados: { unidade_embalagem?: string | null; medida_embalagem?: string | null; quantidade_embalagem?: number | null; fornecedor_id?: number | null; conta_gerencial_despesa_padrao?: string | null; estocavel?: boolean | null }) {
  const res = await authFetch(`${API}/cadastro/estoque-itens/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar item"); }
  return res.json();
}

export async function fetchParametros() {
  const res = await authFetch(`${API}/parametros/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Parâmetros error: ${res.status}`);
  return res.json();
}

export async function atualizarParametro(chave: string, valor: number | string | boolean) {
  const res = await authFetch(`${API}/parametros/${chave}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ valor }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar parâmetro"); }
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
export async function baixarPdfManualFazenda() {
  const res = await authFetch(`${API}/manual-fazenda/pdf`);
  if (!res.ok) throw new Error(`Erro ao gerar PDF do Manual da Fazenda: ${res.status}`);
  const blob = await res.blob();
  const { baixarArquivo } = await import("./nativo");
  await baixarArquivo(blob, "manual_da_fazenda.pdf");
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar parâmetros do Manual da Fazenda"); }
  return res.json() as Promise<ParametroManualFazenda>;
}
export async function anexarContratoManejo(arquivo: File) {
  const form = new FormData();
  form.append("arquivo", arquivo);
  const res = await authFetch(`${API}/manual-fazenda/contrato-anexo`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao anexar contrato"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar sugestão"); }
  return res.json() as Promise<SugestaoManualFazenda>;
}
export async function atualizarSugestaoManualFazenda(id: number, dados: { texto: string; categoria: string; ativo: boolean; ordem: number }) {
  const res = await authFetch(`${API}/manual-fazenda/sugestoes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar sugestão"); }
  return res.json() as Promise<SugestaoManualFazenda>;
}
export async function excluirSugestaoManualFazenda(id: number) {
  const res = await authFetch(`${API}/manual-fazenda/sugestoes/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir sugestão"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar lote"); }
  return res.json();
}
export async function atualizarLote(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/lotes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar lote"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar safra"); }
  return res.json();
}
export async function atualizarSafra(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/safras/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar safra"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao mover animais"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar parâmetro"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar motivo"); }
  return res.json();
}
export async function atualizarMotivoMovimentacao(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/movimentacoes/motivos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar motivo"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar motivo de baixa"); }
  return res.json();
}
export async function atualizarMotivoBaixa(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/motivos-baixa/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar motivo de baixa"); }
  return res.json();
}

// ── Raças (Configurações > Cadastro) ──
export async function fetchRacas() {
  const res = await authFetch(`${API}/cadastro/racas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Raças error: ${res.status}`);
  return res.json();
}
export async function criarRaca(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/racas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar raça"); }
  return res.json();
}
export async function atualizarRaca(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/racas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar raça"); }
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
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Erro ao criar ${rotulo.toLowerCase()}`); }
      return res.json();
    },
    atualizar: async (id: number, dados: { nome: string; ativo: boolean }): Promise<ItemCadastroSimples> => {
      const res = await authFetch(`${API}/cadastro/${rota}/${id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Erro ao atualizar ${rotulo.toLowerCase()}`); }
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

const apiCategoriasEstoque = criarApiCadastroSimples("categorias-estoque", "Categoria de estoque");
export const fetchCategoriasEstoqueCadastro = apiCategoriasEstoque.fetch;
export const criarCategoriaEstoque = apiCategoriasEstoque.criar;
export const atualizarCategoriaEstoque = apiCategoriasEstoque.atualizar;

const apiFinalidadesEstoque = criarApiCadastroSimples("finalidades-estoque", "Finalidade de estoque");
export const fetchFinalidadesEstoqueCadastro = apiFinalidadesEstoque.fetch;
export const criarFinalidadeEstoque = apiFinalidadesEstoque.criar;
export const atualizarFinalidadeEstoque = apiFinalidadesEstoque.atualizar;

const apiUnidadesEstoque = criarApiCadastroSimples("unidades-estoque", "Unidade de estoque");
export const fetchUnidadesEstoqueCadastro = apiUnidadesEstoque.fetch;
export const criarUnidadeEstoque = apiUnidadesEstoque.criar;
export const atualizarUnidadeEstoque = apiUnidadesEstoque.atualizar;

const apiUnidadesEmbalagemEstoque = criarApiCadastroSimples("unidades-embalagem-estoque", "Unidade de embalagem");
export const fetchUnidadesEmbalagemEstoqueCadastro = apiUnidadesEmbalagemEstoque.fetch;
export const criarUnidadeEmbalagemEstoque = apiUnidadesEmbalagemEstoque.criar;
export const atualizarUnidadeEmbalagemEstoque = apiUnidadesEmbalagemEstoque.atualizar;

const apiUnidadesMedidaEmbalagemEstoque = criarApiCadastroSimples("unidades-medida-embalagem-estoque", "Unidade de medida");
export const fetchUnidadesMedidaEmbalagemEstoqueCadastro = apiUnidadesMedidaEmbalagemEstoque.fetch;
export const criarUnidadeMedidaEmbalagemEstoque = apiUnidadesMedidaEmbalagemEstoque.criar;
export const atualizarUnidadeMedidaEmbalagemEstoque = apiUnidadesMedidaEmbalagemEstoque.atualizar;

// ── Graus de sangue (Configurações > Cadastro) ──
export async function fetchGrausSangue() {
  const res = await authFetch(`${API}/cadastro/graus-sangue`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Graus de sangue error: ${res.status}`);
  return res.json();
}
export async function criarGrauSangue(dados: { nome: string; fracao_holandes?: number | null; ativo?: boolean }) {
  const res = await authFetch(`${API}/cadastro/graus-sangue`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar grau de sangue"); }
  return res.json();
}
export async function atualizarGrauSangue(id: number, dados: { nome: string; fracao_holandes?: number | null; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/graus-sangue/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar grau de sangue"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar motivo de venda"); }
  return res.json();
}
export async function atualizarMotivoVenda(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/motivos-venda/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar motivo de venda"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar serviço"); }
  return res.json();
}
export async function atualizarServicoCadastro(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/servicos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar serviço"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar tipo de serviço"); }
  return res.json();
}
export async function atualizarTipoServico(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/tipos-servico/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar tipo de serviço"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar método"); }
  return res.json();
}
export async function atualizarMetodoServico(id: number, dados: { nome: string; tipo_servico_id: number; ativo: boolean }) {
  const res = await authFetch(`${API}/cadastro/metodos-servico/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar método"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar baixa"); }
  return res.json();
}

export async function marcarADescartar(dados: { animais: string[]; descartar?: boolean; observacao?: string }) {
  const res = await authFetch(`${API}/baixas/a-descartar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao marcar A descartar"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar compra"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar venda"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar compra de sêmen"); }
  return res.json();
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar colostragem"); }
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
  itens: { produto: string; via?: string; quantidade: number; unidade: string; estoque_id?: number | null }[];
  aplicado?: boolean;
}) {
  const res = await authFetch(`${API}/sanidade/aplicacoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar aplicação de sanidade"); }
  return res.json();
}

export async function editarAplicacaoSanidade(id: number, dados: {
  data_aplicacao?: string; produto?: string; dose?: number | null; unidade?: string | null;
  via?: string | null; responsavel?: string | null; obs?: string | null;
}) {
  const res = await authFetch(`${API}/sanidade/aplicacoes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar aplicação"); }
  return res.json();
}

export async function excluirAplicacaoSanidade(id: number) {
  const res = await authFetch(`${API}/sanidade/aplicacoes/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir aplicação"); }
  return res.json();
}

export async function marcarCuraAplicacao(id: number, curada: boolean) {
  const res = await authFetch(`${API}/sanidade/aplicacoes/${id}/cura`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ curada }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao marcar cura"); }
  return res.json();
}

export async function marcarCuraProtocolo(lancamentoId: number, curada: boolean) {
  const res = await authFetch(`${API}/sanidade/mastite/cura`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lancamento_id: lancamentoId, curada }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao marcar cura"); }
  return res.json();
}

export type CasoTaxaCura = {
  origem: "aplicacao" | "protocolo"; id: number; numero: string; tratamento: string;
  data: string | null; curada: boolean; lote: string | null; categoria: string; status_lactacao: string;
};
export async function fetchTaxaCura(): Promise<{ casos: CasoTaxaCura[]; total: number; curados: number; taxa_cura_pct: number | null }> {
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
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Erro ao criar ${rotulo.toLowerCase()}`); }
      return res.json();
    },
    atualizar: async (id: number, dados: { nome: string; ativo: boolean }) => {
      const res = await authFetch(`${API}/cadastro/${caminho}/${id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Erro ao atualizar ${rotulo.toLowerCase()}`); }
      return res.json();
    },
  };
}
const _principiosAtivos = _crudNomeAtivo("principios-ativos", "Princípio ativo");
export const fetchPrincipiosAtivos = _principiosAtivos.listar;
export const criarPrincipioAtivo = _principiosAtivos.criar;
export const atualizarPrincipioAtivo = _principiosAtivos.atualizar;
export async function restaurarCatalogoPrincipios(): Promise<{ criados: number; total: number }> {
  const res = await authFetch(`${API}/cadastro/principios-ativos/restaurar-catalogo`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao restaurar catálogo"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar evento sanitário"); }
  return res.json();
}
export async function atualizarEventoSanitario(id: number, dados: EventoSanitarioPayload) {
  const res = await authFetch(`${API}/cadastro/eventos-sanitarios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar evento sanitário"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar exame"); }
  return res.json();
}
export async function atualizarExame(id: number, dados: ExameDefinicaoPayload) {
  const res = await authFetch(`${API}/cadastro/exames/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar exame"); }
  return res.json();
}
export async function excluirExame(id: number) {
  const res = await authFetch(`${API}/cadastro/exames/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir exame"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar agendamento"); }
  return res.json();
}
export async function atualizarAgendamentoPesagem(id: number, dados: Record<string, any>) {
  const res = await authFetch(`${API}/cadastro/agendamentos-pesagem/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar agendamento"); }
  return res.json();
}
export async function excluirAgendamentoPesagem(id: number) {
  const res = await authFetch(`${API}/cadastro/agendamentos-pesagem/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir"); }
  return res.json();
}

// ── Protocolo sanitário (cadastro + lançamento) ──
// criterio_tipo: "medicamento" (produto = item de estoque), "principio_ativo"
// ou "classificacao" (produto = o valor do critério; medicamento escolhido no lançamento).
export type ProtocoloEtapa = { dia: number; criterio_tipo?: string; produto: string; dosagem: number; unidade: string; via?: string | null; observacao?: string | null };
export async function fetchProtocolosSanitarios() {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos sanitários error: ${res.status}`);
  return res.json();
}
export async function importarProtocoloSanitarioExcel(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao importar planilha"); }
  return res.json();
}
export async function criarProtocoloSanitario(dados: { nome: string; doenca_id?: number | null; eh_mastite?: boolean; dia_inicial?: number; ativo?: boolean; etapas: ProtocoloEtapa[] }) {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar protocolo sanitário"); }
  return res.json();
}
export async function atualizarProtocoloSanitario(id: number, dados: { nome: string; doenca_id?: number | null; eh_mastite?: boolean; dia_inicial?: number; ativo?: boolean; etapas: ProtocoloEtapa[] }) {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar protocolo sanitário"); }
  return res.json();
}
export async function excluirProtocoloSanitario(id: number): Promise<void> {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir protocolo sanitário"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar protocolo sanitário"); }
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
};
export async function criarCalendarioSanitario(dados: CalendarioSanitarioPayload) {
  const res = await authFetch(`${API}/sanidade/calendario`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar regra do calendário sanitário"); }
  return res.json();
}
export async function atualizarCalendarioSanitario(id: number, dados: CalendarioSanitarioPayload) {
  const res = await authFetch(`${API}/sanidade/calendario/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar regra do calendário sanitário"); }
  return res.json();
}
export async function excluirCalendarioSanitario(id: number) {
  const res = await authFetch(`${API}/sanidade/calendario/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir regra do calendário sanitário"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar cronograma"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Relatório de eventos de vida error: ${res.status}`); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cadastrar preventivo"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar movimento de estoque"); }
  return res.json();
}

export type MovimentoEstoqueRow = {
  id: number; nome_item: string; movimento: string; quantidade: number; unidade?: string | null;
  data_movimento: string; observacao?: string | null; usuario_nome?: string | null;
};
export async function fetchMovimentosEstoque(): Promise<{ movimentos: MovimentoEstoqueRow[]; total: number }> {
  const res = await authFetch(`${API}/estoque/movimentos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Movimentos de estoque error: ${res.status}`);
  return res.json();
}

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
export type CategoriaAlimento = { id: number; nome: string; ativo: boolean };
export async function fetchCategoriasAlimento(): Promise<CategoriaAlimento[]> {
  const res = await authFetch(`${API}/alimentacao/categorias`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Categorias de alimento error: ${res.status}`);
  return res.json();
}
export async function criarCategoriaAlimento(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/alimentacao/categorias`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar categoria"); }
  return res.json();
}
export async function atualizarCategoriaAlimento(id: number, dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/alimentacao/categorias/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar categoria"); }
  return res.json();
}
export async function excluirCategoriaAlimento(id: number) {
  const res = await authFetch(`${API}/alimentacao/categorias/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir categoria"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar alimento"); }
  return res.json();
}
export async function atualizarAlimento(id: number, dados: AlimentoIn): Promise<Alimento> {
  const res = await authFetch(`${API}/alimentacao/alimentos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar alimento"); }
  return res.json();
}
export async function excluirAlimento(id: number) {
  const res = await authFetch(`${API}/alimentacao/alimentos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir alimento"); }
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
  return res.json() as Promise<{ alimentos: string[]; produto_ids: number[]; linhas: string[][] }>;
}
export async function criarProdutoTabelaNutricional(nome: string) {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/produtos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cadastrar produto"); }
  return res.json();
}
export async function renomearProdutoTabelaNutricional(id: number, nome: string) {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/produtos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao renomear produto"); }
  return res.json();
}
export async function excluirProdutoTabelaNutricional(id: number) {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/produtos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir produto"); }
  return res.json();
}
export async function salvarValoresTabelaNutricional(itens: { produto_id: number; nutriente: string; valor: string }[]) {
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/valores`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ itens }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar tabela nutricional"); }
  return res.json();
}
export function baixarModeloTabelaNutricional() {
  return baixarArquivoAutenticado("/alimentacao/tabela-nutricional/modelo", "tabela_nutricional_modelo.xlsx");
}
export async function importarTabelaNutricional(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/alimentacao/tabela-nutricional/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao importar planilha"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar matéria seca"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar análise bromatológica"); }
  return res.json();
}
export async function criarDieta(dados: {
  lote: number; responsavel?: string; data_abertura: string; data_prevista_encerramento?: string; observacao?: string;
  base_quantidade?: string; leite_bezerros_kg_dia?: number | null;
  itens: { alimento: string; quantidade: number; unidade: string; base?: string; ms_pct?: number | null }[]; encerrar_anterior?: boolean;
}) {
  const res = await authFetch(`${API}/alimentacao/dietas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar dieta"); }
  return res.json();
}
export type ContextoDieta = {
  lote: number; nome: string | null; qtd_animais: number; del_medio: number | null; media_cl: number | null; data_ult_cl: string | null;
  animais: { numero: string; del_dias: number | null; ult_cl_kg: number | null; data_ult_leite: string | null }[];
  ultima_dieta: { data_abertura: string; responsavel: string | null; itens: { alimento: string; unidade: string; total_dia: number; por_cabeca: number | null }[] } | null;
};
export async function fetchContextoDieta(lote: number) {
  const res = await authFetch(`${API}/alimentacao/dietas/contexto/${lote}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Contexto dieta error: ${res.status}`);
  return res.json() as Promise<ContextoDieta>;
}
export type ApresentacaoDieta = {
  lote: number; nome: string | null; qtd_animais: number; data_abertura: string; data_prevista_encerramento: string | null;
  num_tratos: number; vagao_kg_dia: number; vagao_kg_trato: number;
  itens: { alimento: string; unidade: string; total_dia: number; por_cabeca: number | null; total_trato: number }[];
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao encerrar dieta"); }
  return res.json();
}

export async function registrarRealDieta(id: number, dados: { data: string; itens: { alimento: string; quantidade: number; unidade: string }[] }) {
  const res = await authFetch(`${API}/alimentacao/dietas/${id}/real`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar o real oferecido"); }
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
};
export type PrincipioFarmacia = {
  id: number; nome: string; ativo: boolean; categoria: string | null; categoria_software: string | null;
  uso_principal: string | null; justificativa: string | null;
  eh_biologico: boolean; doenca_id: number | null; unidade_base: string | null; unidade_apresentacao: string | null;
  estoque_minimo_apresentacoes: number; total_base: number | null; total_apresentacoes: number;
  qtd_marcas_estoque: number; abaixo_minimo: boolean; precisa_inicializar: boolean; itens: ApresentacaoFarmacia[];
};
export type MarcaComercial = { id: number; principio_ativo_id: number; nome_comercial: string; laboratorio: string | null; ativo: boolean };
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar princípio"); }
  return res.json();
}
export async function criarPrincipioFarmacia(dados: Record<string, any>) {
  const res = await authFetch(`${API}/farmacia/principios`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar princípio"); }
  return res.json();
}
export async function criarMarcaFarmacia(dados: { principio_ativo_id: number; nome_comercial: string; laboratorio?: string }) {
  const res = await authFetch(`${API}/farmacia/medicamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar marca"); }
  return res.json();
}
export async function excluirMarcaFarmacia(id: number) {
  const res = await authFetch(`${API}/farmacia/medicamentos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir marca"); }
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
export async function inicializarEstoqueFarmacia(estoqueId: number, dados: { quantidade: number; data?: string; observacao?: string }) {
  const res = await authFetch(`${API}/farmacia/estoque/${estoqueId}/inicializar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao inicializar estoque"); }
  return res.json();
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao indicar princípio para a doença"); }
  return res.json() as Promise<IndicacaoTerapeutica>;
}
export async function excluirIndicacao(id: number) {
  const res = await authFetch(`${API}/farmacia/indicacoes/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir indicação"); }
  return res.json();
}
export async function fetchIndicacoesDoenca(doencaId: number) {
  const res = await authFetch(`${API}/sanidade/indicacoes-doenca/${doencaId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Indicações por doença error: ${res.status}`);
  return res.json() as Promise<{ doenca_id: number; doenca: string; opcoes: OpcaoIndicacaoDoenca[] }>;
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

export async function criarControlesLeiteiros(dados: {
  data_controle: string;
  entradas: { numero_matriz: string; ordenhas: (number | null)[] }[];
}) {
  const res = await authFetch(`${API}/producao/controles`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar controle leiteiro"); }
  return res.json();
}

// Baixa um arquivo binário autenticado (o backend exige Bearer token, então não
// dá pra usar um <a href> direto) — dispara o download no navegador via blob.
async function baixarArquivoAutenticado(path: string, nomeArquivoFallback: string) {
  const res = await authFetch(`${API}${path}`);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao baixar arquivo"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao importar planilha"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar pesagem corporal"); }
  return res.json();
}

export function baixarModeloPesagemCorporal() {
  return baixarArquivoAutenticado("/producao/pesagens/modelo-excel", "modelo_pesagem_corporal.xlsx");
}

export async function importarPesagemCorporalPlanilha(file: File): Promise<{ criados: number; erros: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/producao/pesagens/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao importar planilha"); }
  return res.json();
}
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar qualidade do leite"); }
  return res.json();
}

export function baixarModeloQualidadeLeite() {
  return baixarArquivoAutenticado("/producao/qualidade-leite/modelo-excel", "modelo_qualidade_leite.xlsx");
}

export async function importarQualidadeLeitePlanilha(file: File): Promise<{ criados: number; erros: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/producao/qualidade-leite/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao importar planilha"); }
  return res.json();
}

// ── Venda mensal do leite ──
export async function fetchEntregaLeiteMensal() {
  const res = await authFetch(`${API}/producao/entrega-leite`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Venda mensal do leite error: ${res.status}`);
  return res.json();
}
export async function criarEntregaLeiteMensal(dados: { competencia: string; quantidade_litros: number; observacao?: string | null }) {
  const res = await authFetch(`${API}/producao/entrega-leite`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar entrega mensal do leite"); }
  return res.json();
}

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
    throw new Error(d.detail || "Não foi possível ajustar a próxima aplicação de BST.");
  }
  return res.json();
}

// ── Secagem ──
export async function fetchSecagemInfo(numeroMatriz: string) {
  const res = await authFetch(`${API}/producao/secagem-info?numero_matriz=${encodeURIComponent(numeroMatriz)}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao buscar dados de secagem"); }
  return res.json();
}
export async function criarSecagem(dados: {
  numero_matriz: string; data_secagem: string; motivo: string; escore_condicao_corporal?: number | null;
  observacao?: string; responsavel?: string; aplicado?: boolean;
  produtos: { produto: string; via?: string; quantidade: number; unidade: string }[];
  vacinas_pre_parto?: string[];
  vacina_pre_parto_aplicada_agora?: boolean;
}) {
  const res = await authFetch(`${API}/producao/secagem`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar secagem"); }
  return res.json();
}
export type LoteSugeridoEvento = { codigo: string; nome: string; rotulo: string };
export async function sugestaoLoteEvento(dados: { numero_matriz: string; categoria_abrev: string; del_dias?: number | null; data_nasc?: string | null }): Promise<{ lote_sugerido: LoteSugeridoEvento | null }> {
  const res = await authFetch(`${API}/producao/sugestao-lote-evento`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao buscar sugestão de lote"); }
  return res.json();
}

// ── Serviço/IA: protocolo IATF (só agenda) e inseminação (o evento em si) ──
export type HormonioIatf = { dia: number; produto: string; dose?: number | null; unidade?: string; via?: string };
// Nome do lançamento é sempre automático (Central de Protocolos) — não se
// digita mais; protocolo_id é opcional (molde cadastrado, só para
// pré-preencher os hormônios e citar no nome).
export async function criarProtocoloIatf(dados: { animais: string[]; data_d0: string; protocolo_id?: number | null; hormonios?: HormonioIatf[] }) {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao agendar protocolo IATF"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cadastrar protocolo IATF"); }
  return res.json();
}
export async function atualizarProtocoloIatfCadastrado(id: number, dados: { nome: string; observacao?: string | null; ativo?: boolean; etapas: EtapaProtocoloIatf[] }): Promise<ProtocoloIatfMolde> {
  const res = await authFetch(`${API}/cadastro/protocolos-iatf/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar protocolo IATF"); }
  return res.json();
}
export async function excluirProtocoloIatfCadastrado(id: number): Promise<void> {
  const res = await authFetch(`${API}/cadastro/protocolos-iatf/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir protocolo IATF"); }
}

// ── Central de Protocolos — Acompanhamento e Histórico (IATF + Indução +
// Sanitário + Customizado, juntos e filtráveis por nome/período/tipo) ──
export type LinhaCentralProtocolos = {
  tipo: "produtivo" | "reprodutivo" | "sanitario"; origem: "iatf" | "inducao" | "sanitario" | "customizado";
  origem_id: number; nome: string; data_inicio: string; data_fim: string;
  etapas_total: number; etapas_realizadas: number; etapas_faltam: number;
  animais: number; status: "ativo" | "concluido" | "cancelado";
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
export async function fetchProtocolosIatfAtivos() {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf/ativos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos IATF ativos error: ${res.status}`);
  return res.json();
}
export type CandidataIatfProjetada = {
  numero_matriz: string; sit_rep: string | null; del_dias: number | null; motivo: string;
  del_dias_projetado: number | null; apta_na_proxima_visita: boolean;
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao adicionar animais ao protocolo"); }
  return res.json();
}
// Corrige uma inclusão por engano num lançamento ativo — só permite remover
// se nenhuma etapa do animal já foi confirmada (ver reproducao.py).
export async function removerAnimalIatf(lancamentoId: number, numeroMatriz: string): Promise<void> {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf/${lancamentoId}/animais/${encodeURIComponent(numeroMatriz)}`, {
    method: "DELETE",
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao remover animal do protocolo"); }
}
export async function criarServico(dados: {
  numero_matriz: string; data_servico: string; tipo_servico?: string;
  protocolo?: string; reprodutor?: string; responsavel?: string;
  tipo_semen?: string | null;
}) {
  const res = await authFetch(`${API}/reproducao/servico`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar serviço/inseminação"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar parto"); }
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
  valor_total?: number | null; depreciavel?: boolean; metodo_depreciacao?: string | null;
  vida_util?: string | null; valor_residual?: number | null; valor_mercado_atual?: number | null;
  atualizacao_valor_mercado_frequencia_meses?: number | null;
};

export async function criarPatrimonio(dados: PatrimonioPayload) {
  const res = await authFetch(`${API}/financeiro/patrimonio`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cadastrar patrimônio"); }
  return res.json();
}

export async function atualizarPatrimonio(itemId: number, dados: PatrimonioPayload) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar patrimônio"); }
  return res.json();
}

export async function atualizarValorMercadoPatrimonio(itemId: number, valorMercadoAtual: number, data?: string) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}/valor-mercado`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ valor_mercado_atual: valorMercadoAtual, data: data || null }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar valor de mercado"); }
  return res.json();
}

export async function vincularLancamentoPatrimonio(numeroLancamento: string, patrimonioId: number | null) {
  const res = await authFetch(`${API}/financeiro/lancamentos/${encodeURIComponent(numeroLancamento)}/patrimonio`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ patrimonio_id: patrimonioId }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao vincular patrimônio"); }
  return res.json();
}

export async function atualizarPlanoManutencaoPatrimonio(itemId: number, dados: {
  frequencia_manutencao_meses?: number | null; data_ultima_manutencao?: string | null;
  data_proxima_manutencao?: string | null; observacao_manutencao?: string | null;
}) {
  const res = await authFetch(`${API}/financeiro/patrimonio/${itemId}/manutencao-plano`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar o plano de manutenção"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cadastrar cartão"); }
  return res.json();
}

export async function atualizarCartaoCredito(cartaoId: number, dados: CartaoCreditoPayload): Promise<CartaoCredito> {
  const res = await authFetch(`${API}/financeiro/cartoes/${cartaoId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar cartão"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar compra no cartão"); }
  return res.json();
}

export async function fecharFaturaCartao(faturaId: number): Promise<FaturaCartao> {
  const res = await authFetch(`${API}/financeiro/cartoes/faturas/${faturaId}/fechar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao fechar fatura"); }
  return res.json();
}

export async function pagarFaturaCartao(faturaId: number, dados: {
  data_pagamento?: string | null; codigo_conta_gerencial?: string | null; nome_conta_gerencial?: string | null; centro_custo?: string | null;
} = {}): Promise<FaturaCartao & { lancamento: any }> {
  const res = await authFetch(`${API}/financeiro/cartoes/faturas/${faturaId}/pagar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao pagar fatura"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar a manutenção"); }
  return res.json();
}

export async function fetchOpcoesFinanceiro() {
  const res = await authFetch(`${API}/financeiro/opcoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Opções financeiro error: ${res.status}`);
  return res.json();
}

// Link pro painel do Supabase (Table Editor) — botão em Relatórios
// financeiros; backend bloqueia consultor (ver fazenda.auth.exigir_nao_consultor).
// url: null quando o Supabase não está configurado.
export async function fetchSupabaseDashboardUrl(): Promise<{ url: string | null }> {
  const res = await authFetch(`${API}/financeiro/supabase-dashboard-url`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Link do Supabase error: ${res.status}`);
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar conta gerencial"); }
  return res.json();
}
export async function atualizarContaGerencial(id: number, dados: ContaGerencialPayload) {
  const res = await authFetch(`${API}/financeiro/plano-contas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar conta gerencial"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao vincular evento"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Custo por safra error: ${res.status}`); }
  return res.json();
}

// ── Contas correntes (Configurações > Parâmetros financeiros) ──
// Traz id + rótulo legível de cada conta — usado sempre que o formulário
// precisa gravar o vínculo com a conta (conta_corrente_id), e não só exibir
// o texto (diferente de `fetchOpcoesFinanceiro().contas_bancarias`, que só
// devolve rótulos em texto, sem id).
export type ContaCorrenteCadastro = {
  id: number; banco: string; agencia: string; numero_conta: string; ativo: boolean; rotulo: string;
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar conta corrente"); }
  return res.json();
}
export async function atualizarContaCorrente(id: number, dados: { banco: string; agencia: string; numero_conta: string; ativo: boolean }) {
  const res = await authFetch(`${API}/financeiro/contas-correntes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar conta corrente"); }
  return res.json();
}

// ── Centros de custo (Configurações > Parâmetros financeiros) ──
export async function fetchCentrosCusto() {
  const res = await authFetch(`${API}/financeiro/centros-custo`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Centros de custo error: ${res.status}`);
  return res.json();
}
export async function criarCentroCusto(dados: { nome: string; ativo?: boolean }) {
  const res = await authFetch(`${API}/financeiro/centros-custo`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar centro de custo"); }
  return res.json();
}
export async function atualizarCentroCusto(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/financeiro/centros-custo/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar centro de custo"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar tipo de documento"); }
  return res.json();
}
export async function atualizarTipoDocumento(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/financeiro/tipos-documento/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar tipo de documento"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar forma de pagamento"); }
  return res.json();
}
export async function atualizarFormaPagamentoCadastro(id: number, dados: { nome: string; ativo: boolean }) {
  const res = await authFetch(`${API}/financeiro/formas-pagamento-cadastro/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar forma de pagamento"); }
  return res.json();
}

export async function criarLancamentoFinanceiro(dados: any) {
  const res = await authFetch(`${API}/financeiro/lancamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar lançamento"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar lançamento recorrente"); }
  return res.json();
}
export async function atualizarLancamentoRecorrente(id: number, dados: LancamentoRecorrentePayload) {
  const res = await authFetch(`${API}/financeiro/recorrentes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar lançamento recorrente"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao gerar o lançamento"); }
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
  const res = await authFetch(`${API}/financeiro/lancamentos/${id}/pagar`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao dar baixa"); }
  return res.json();
}

export async function criarBaixaLote(dados: {
  lancamento_ids: number[]; data_pagamento: string; conta_bancaria?: string;
  forma_pagamento?: string; data_vencimento_cartao?: string; numero_documento_pagamento?: string;
}) {
  const res = await authFetch(`${API}/financeiro/lancamentos/baixa-lote`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao dar baixa em lote"); }
  return res.json();
}

// Baixa em lote com pagamento diferente por nota (data/valor/conta/forma por linha).
export type BaixaLoteItem = {
  lancamento_id: number; data_pagamento: string; valor_pago: number;
  conta_bancaria?: string; forma_pagamento?: string; data_vencimento_cartao?: string; numero_documento_pagamento?: string;
};
export async function criarBaixaLoteDetalhada(itens: BaixaLoteItem[]) {
  const res = await authFetch(`${API}/financeiro/lancamentos/baixa-lote-detalhada`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ itens }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao dar baixa em lote"); }
  return res.json();
}

export async function atualizarLancamentoFinanceiro(id: number, dados: {
  descricao?: string | null; codigo_conta?: string | null; centro_custo?: string | null;
  fornecedor_cliente?: string | null; numero_nota?: string | null; numero_documento_pagamento?: string | null; tipo_documento?: string | null;
  numero_os_orcamento?: string | null; numero_boleto?: string | null;
  data_emissao?: string | null; data_vencimento?: string | null; data_competencia?: string | null;
  data_prevista_entrada?: string | null; data_pedido?: string | null;
  quantidade?: number | null; valor_unitario?: number | null; valor_total?: number | null;
  desconto_acrescimo?: number | null; responsavel?: string | null; produto?: string | null;
}) {
  const res = await authFetch(`${API}/financeiro/lancamentos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar o lançamento"); }
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
export type SugestoesCadastro = { fornecedor: SugestaoCadastroItem | null; itens: SugestaoCadastroItem[] };

export async function importarXmlFinanceiro(xml: string) {
  const res = await authFetch(`${API}/financeiro/importar-xml`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ xml }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao ler o XML"); }
  return res.json();
}

export async function lerDocumentoFinanceiro(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/financeiro/ler-documento`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao ler o documento"); }
  return res.json();
}

// Anexos do lançamento (ex.: boleto de um parcelamento) — o lançamento já
// precisa existir (numero_lancamento vem do retorno de criarLancamentoFinanceiro).
export type AnexoLancamento = { id: number; nome_arquivo: string; mime_type: string; tamanho_bytes: number; categoria?: string | null; criado_em?: string };

export async function anexarArquivoLancamento(numeroLancamento: string, file: File, categoria?: string | null): Promise<AnexoLancamento> {
  const form = new FormData();
  form.append("file", file);
  if (categoria) form.append("categoria", categoria);
  const res = await authFetch(`${API}/financeiro/lancamentos/${encodeURIComponent(numeroLancamento)}/anexos`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao anexar o arquivo"); }
  return res.json();
}

export async function listarAnexosLancamento(numeroLancamento: string): Promise<AnexoLancamento[]> {
  const res = await authFetch(`${API}/financeiro/lancamentos/${encodeURIComponent(numeroLancamento)}/anexos`);
  if (!res.ok) throw new Error("Erro ao listar anexos");
  return res.json();
}

export function urlAnexoLancamento(anexoId: number): string {
  return `${API}/financeiro/anexos/${anexoId}`;
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao enviar o recibo por e-mail"); }
}

export async function excluirAnexoLancamento(anexoId: number) {
  const res = await authFetch(`${API}/financeiro/anexos/${anexoId}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir anexo"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar item de orçamento"); }
  return res.json();
}
export async function atualizarItemOrcamento(id: number, dados: OrcamentoItemPayload) {
  const res = await authFetch(`${API}/planejamento/orcamento/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar item de orçamento"); }
  return res.json();
}
export async function excluirItemOrcamento(id: number) {
  const res = await authFetch(`${API}/planejamento/orcamento/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir item de orçamento"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar cenário"); }
  return res.json();
}
export async function atualizarCenario(id: number, dados: CenarioPayload) {
  const res = await authFetch(`${API}/planejamento/cenarios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar cenário"); }
  return res.json();
}
export async function excluirCenario(id: number) {
  const res = await authFetch(`${API}/planejamento/cenarios/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir cenário"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar item do cenário"); }
  return res.json();
}
export async function atualizarItemCenario(id: number, dados: PlanejamentoItemPayload) {
  const res = await authFetch(`${API}/planejamento/itens/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar item do cenário"); }
  return res.json();
}
export async function excluirItemCenario(id: number) {
  const res = await authFetch(`${API}/planejamento/itens/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir item do cenário"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao importar para pedido"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar pedido"); }
  return res.json();
}
export async function atualizarPedido(id: number, dados: PedidoPayload) {
  const res = await authFetch(`${API}/pedidos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar pedido"); }
  return res.json();
}
export async function atualizarStatusPedido(id: number, status: string) {
  const res = await authFetch(`${API}/pedidos/${id}/status`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar status do pedido"); }
  return res.json();
}
export async function excluirPedido(id: number) {
  const res = await authFetch(`${API}/pedidos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir pedido"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao importar"); }
  return res.json();
}

export async function backfillFornecedoresEstoque() {
  const res = await authFetch(`${API}/importar/backfill`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao rodar o backfill"); }
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
    throw new Error(err.detail || "Erro no upload");
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao adicionar evento"); }
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
// FastAPI 422 traz "detail" como lista de erros de validação, não string — normaliza para texto.
function detalheErro(d: any, fallback: string): string {
  if (typeof d?.detail === "string") return d.detail;
  if (Array.isArray(d?.detail)) return d.detail.map((e: any) => e.msg || JSON.stringify(e)).join("; ");
  return fallback;
}
export async function impactoExclusao(tipo: string, id: string) {
  const res = await authFetch(`${API}/exclusoes/impacto`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tipo, id }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(detalheErro(d, "Erro ao calcular impacto")); }
  return res.json();
}
export async function confirmarExclusao(tipo: string, id: string) {
  const res = await authFetch(`${API}/exclusoes/confirmar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tipo, id }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(detalheErro(d, "Erro ao excluir")); }
  return res.json();
}
export async function fetchPendentesExclusao() {
  const res = await authFetch(`${API}/exclusoes/pendentes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Pendências de exclusão error: ${res.status}`);
  return res.json();
}
export async function aprovarExclusao(id: number) {
  const res = await authFetch(`${API}/exclusoes/pendentes/${id}/aprovar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(detalheErro(d, "Erro ao aprovar")); }
  return res.json();
}
export async function rejeitarExclusao(id: number, motivo?: string) {
  const res = await authFetch(`${API}/exclusoes/pendentes/${id}/rejeitar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ motivo }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(detalheErro(d, "Erro ao rejeitar")); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao ativar notificações"); }
  return res.json();
}

export async function unsubscribePush(endpoint?: string) {
  const res = await authFetch(`${API}/push/subscribe`, {
    method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint: endpoint || null }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao desativar notificações"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar notificações"); }
  return res.json();
}

export async function removerTokenFcm(token?: string): Promise<{ ok: boolean }> {
  const res = await authFetch(`${API}/push/registrar-fcm`, {
    method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: token || null }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao remover notificações"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar"); }
  return res.json();
}

export async function aprovarLancamento(id: number) {
  const res = await authFetch(`${API}/aprovacoes/${id}/aprovar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao aprovar"); }
  return res.json();
}

export async function rejeitarLancamento(id: number) {
  const res = await authFetch(`${API}/aprovacoes/${id}/rejeitar`, { method: "POST" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao rejeitar"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Erro (${res.status})`); }
  return res.json();
}

export type RecriaOcorrencia = { id: number; numero_matriz: string; doenca: string; data_ocorrencia: string; observacao?: string | null; origem: string; usuario_nome?: string | null };
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
export type RecriaJanela = { id?: number; doenca: string; dia_min: number; dia_max: number; dias_antecedencia: number; ativo: boolean };

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
export const criarRecriaOcorrencia = (d: { numero_matriz: string; doenca: string; data_ocorrencia: string; observacao?: string }) => _rSend(`/recria/ocorrencias`, "POST", d);
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
export type RecriaCiclo = { ciclo: number; inicio: string; fim: string; elegiveis: number; servidos: number; prenhes: number; taxa_servico: number | null; taxa_concepcao: number | null; taxa_prenhez: number | null };
export const fetchRecriaIdadeParto = (): Promise<RecriaIdadeParto> => _rGet(`/recria/reproducao/idade-parto`);
export const fetchRecriaTaxaPrenhez = (ini: string, fim: string, vwp = 0): Promise<{ ciclos: RecriaCiclo[]; taxa_prenhez_media: number | null; total_servicos: number; meta_taxa_prenhez: number }> =>
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
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Erro ao importar planilha");
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
  situacao_reprodutiva?: "vazia" | "inseminada" | "prenha" | null;
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
export const fetchTouros = (): Promise<Touro[]> => _rGet(`/cadastro/touros`);
export const fetchCamposPlanilhaTouros = (): Promise<string[]> => _rGet(`/cadastro/touros/campos-planilha`);
export const criarTouro = (d: TouroIn): Promise<Touro> => _rSend(`/cadastro/touros`, "POST", d);
export const atualizarTouro = (id: number, d: TouroIn): Promise<Touro> => _rSend(`/cadastro/touros/${id}`, "PUT", d);
export const excluirTouro = (id: number) => _rSend(`/cadastro/touros/${id}`, "DELETE");
export const recarregarCatalogoTouros = (): Promise<{ touros_antes: number; touros_depois: number }> => _rSend(`/cadastro/touros/recarregar-catalogo`, "POST");

export type ProvaMediaCampos = Record<
  "leite_kg" | "gordura_kg" | "gordura_pct" | "proteina_kg" | "proteina_pct" | "tpi" | "nm_dolar"
  | "tipo_composto" | "ubere_composto" | "pernas_composto" | "ccs_score" | "fertilidade_filhas" | "facilidade_parto",
  number | null
>;
export type ProvaMediaRecorte = { prova: ProvaMediaCampos; total_doses: number; touros_considerados: number };
export type ProvaMediaSemen = {
  botijao: ProvaMediaRecorte;
  servicos_periodo: ProvaMediaRecorte & { de: string | null; ate: string | null };
};
export const fetchProvaMediaSemen = (de?: string, ate?: string): Promise<ProvaMediaSemen> => {
  const p = new URLSearchParams();
  if (de) p.set("de", de);
  if (ate) p.set("ate", ate);
  const qs = p.toString();
  return _rGet(`/cadastro/estoque-semen/prova-media${qs ? `?${qs}` : ""}`);
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao arquivar documento"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir documento"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir foto"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Senha incorreta"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao abrir chamado"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao calcular juros"); }
  return res.json();
}

// Lançamento extraordinário do contador (guia/imposto/multa) — mesmo POST
// /financeiro/lancamentos de sempre, só que com o cadeado destravado.
export async function criarLancamentoExtraordinario(dados: any, tokenDesbloqueio: string) {
  const res = await authFetch(`${API}/financeiro/lancamentos`, {
    method: "POST", headers: { "Content-Type": "application/json", ...comDesbloqueio(tokenDesbloqueio) },
    body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar lançamento"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar alerta"); }
  return res.json();
}

export async function editarAlertaIndicador(id: number, dados: { operador?: string; valor_limite?: number; ativo?: boolean }): Promise<AlertaIndicador> {
  const res = await authFetch(`${API}/alertas-indicador/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar alerta"); }
  return res.json();
}

export async function excluirAlertaIndicador(id: number): Promise<void> {
  const res = await authFetch(`${API}/alertas-indicador/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir alerta"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar filtro"); }
  return res.json();
}

export async function excluirFiltroSalvo(id: number): Promise<void> {
  const res = await authFetch(`${API}/filtros-salvos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir filtro salvo"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar protocolo"); }
  return res.json();
}
export async function atualizarProtocoloCustomizado(id: number, dados: {
  nome: string; categoria: string; tipo?: string | null; dia_inicial: number; observacao?: string | null; ativo?: boolean;
  etapas: EtapaProtocoloCustomizado[];
}): Promise<ProtocoloCustomizado> {
  const res = await authFetch(`${API}/cadastro/protocolos-customizados/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar protocolo"); }
  return res.json();
}
export async function excluirProtocoloCustomizado(id: number): Promise<void> {
  const res = await authFetch(`${API}/cadastro/protocolos-customizados/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir protocolo"); }
}

export async function fetchProtocolosCustomizadosParaLancar(): Promise<ProtocoloCustomizado[]> {
  const res = await authFetch(`${API}/protocolos-customizados`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos personalizados error: ${res.status}`);
  return res.json();
}
export async function lancarProtocoloCustomizado(dados: {
  protocolo_id: number; animais: string[]; lote?: string | null; data_inicio: string;
  responsavel?: string | null; observacao?: string | null;
}): Promise<{ criado: boolean; lancamento_id: number; eventos_criados: number; animais: number }> {
  const res = await authFetch(`${API}/protocolos-customizados/lancar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar protocolo"); }
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
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao cancelar lançamento"); }
}
