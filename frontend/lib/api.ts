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
export function logout() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("token"); localStorage.removeItem("usuario");
    location.href = "/login";
  }
}
// Mapa rota → módulo (para menu e bloqueio de páginas).
export const ROTA_MODULO: Record<string, string> = {
  "/": "capa", "/indicadores": "indicadores", "/agenda": "agenda", "/lancamentos": "lancamentos",
  "/reproducao": "reproducao", "/analise-reprodutiva": "analise", "/relatorios": "reproducao", "/rebanho": "rebanho",
  "/producao": "producao", "/alimentacao": "alimentacao", "/sanidade": "sanidade", "/recria": "recria",
  "/financeiro": "financeiro", "/estoque": "estoque", "/pedidos": "pedidos", "/parametros": "parametros", "/upload": "upload",
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
// Permissão específica para publicar/gerenciar matérias do blog (News) e
// confirmar a revisão de publicação definitiva — independente de admin (ver
// backend/fazenda/auth.py::exigir_pode_publicar). Todo usuário nasce sem ela.
export function podePublicarMaterias(): boolean {
  return getUsuario()?.pode_publicar_materias_blog === true;
}
export async function fetchUsuarios() {
  const res = await fetch(`${API}/auth/usuarios`, { headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {}, cache: "no-store" });
  if (!res.ok) throw new Error(`Usuários error: ${res.status}`);
  return res.json();
}
export type UsuarioAcesso = { id: number; username: string; nome: string | null; papel: string; ativo: boolean; ultimo_login: string | null };
export async function fetchAcessos(): Promise<UsuarioAcesso[]> {
  const res = await authFetch(`${API}/auth/usuarios/acessos`);
  if (!res.ok) throw new Error(`Acessos error: ${res.status}`);
  return res.json();
}
export async function criarUsuario(dados: { username: string; senha: string; nome?: string; papel: string; permissoes: string[]; email?: string; pode_publicar_materias_blog?: boolean }) {
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

export async function login(username: string, senha: string) {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, senha }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || "Usuário ou senha inválidos");
  }
  const data = await res.json();
  localStorage.setItem("token", data.token);
  localStorage.setItem("usuario", JSON.stringify(data.usuario));
  // Paleta salva no cadastro do usuário tem prioridade sobre o que já estava no navegador.
  if (data.usuario?.paleta === "vinho" || data.usuario?.paleta === "verde") {
    document.documentElement.setAttribute("data-paleta", data.usuario.paleta);
    localStorage.setItem("paleta", data.usuario.paleta);
  }
  return data.usuario;
}

// Preferência pessoal de paleta de cores (Vinho/Verde) — cada usuário guarda a sua.
export async function salvarPreferenciaPaleta(paleta: "vinho" | "verde") {
  const res = await fetch(`${API}/auth/preferencias`, {
    method: "PUT", headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: JSON.stringify({ paleta }),
  });
  if (!res.ok) throw new Error("Erro ao salvar preferência de paleta");
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
export async function marcarEventoRealizado(eventoId: string, animais?: string[], medicamentos?: MedicamentoIatf[]) {
  const res = await authFetch(`${API}/agenda/realizados`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ evento_id: eventoId, animais: animais || undefined, medicamentos: medicamentos && medicamentos.length ? medicamentos : undefined }),
  });
  if (!res.ok) throw new Error("Erro ao marcar como realizado");
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

export async function fetchServicosAnalise() {
  const res = await authFetch(`${API}/reproducao/servicos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Análise error: ${res.status}`);
  return res.json();
}

export type IndicadoresMensais = { meses: string[]; series: Record<string, (number | null)[]> };
export async function fetchIndicadoresMensais(): Promise<IndicadoresMensais> {
  const res = await authFetch(`${API}/reproducao/indicadores-mensais`, { cache: "no-store" });
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
export async function gerarRelatorioPersonalizado(dados: { parametros: string[]; data_de?: string; data_ate?: string }) {
  const res = await authFetch(`${API}/indicadores/relatorio-personalizado`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao gerar relatório personalizado"); }
  return res.json() as Promise<{ colunas: ParametroRelatorioPersonalizado[]; linhas: Record<string, any>[] }>;
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

export async function fetchAgendaVeterinario() {
  const res = await authFetch(`${API}/reproducao/agenda-veterinario`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Agenda do veterinário error: ${res.status}`);
  return res.json();
}

export async function registrarReconfirmacao(dados: {
  numero_matriz: string; data_reconfirmacao: string; resultado: "positivo" | "negativo";
}) {
  const res = await authFetch(`${API}/reproducao/reconfirmacao`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar reconfirmação"); }
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
  nome: string; tipos: string[]; telefone?: string; email?: string; observacoes?: string; ativo?: boolean;
  salario_base?: number; data_admissao?: string;
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

// ── Vale de funcionário (Financeiro > Folha de pagamento) ──
export async function fetchVales() {
  const res = await authFetch(`${API}/cadastro/vales`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Vales error: ${res.status}`);
  return res.json();
}
export async function criarVale(dados: {
  pessoa_id: number; valor_total: number; forma_pagamento: string; data_pagamento: string;
  parcelas: number; competencia_inicio: string; observacao?: string; confirmar?: boolean;
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
export async function criarDiaria(dados: { pessoa_id: number; valor_diaria: number; data_inicio: string; observacao?: string }) {
  const res = await authFetch(`${API}/cadastro/diarias`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar diária"); }
  return res.json();
}
export async function registrarPagamentoDiaria(diariaId: number, dados: { data_pagamento: string; valor: number; observacao?: string }) {
  const res = await authFetch(`${API}/cadastro/diarias/${diariaId}/pagamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar pagamento"); }
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
export async function atualizarMetaEstoque(id: number, dados: { unidade_embalagem?: string | null; medida_embalagem?: string | null; quantidade_embalagem?: number | null; fornecedor_id?: number | null; estocavel?: boolean | null }) {
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

// ── Lotes (cadastro + parâmetros) ──
export async function fetchLotes() {
  const res = await authFetch(`${API}/lotes/`, { cache: "no-store" });
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

export async function criarMovimentacao(dados: {
  data_movimento: string; hora_movimento?: string; motivo?: string; observacao?: string;
  responsavel?: string; lote_destino_codigo: string; animais: string[];
}) {
  const res = await authFetch(`${API}/movimentacoes/mover`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao mover animais"); }
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
  categoria_alvo?: string | null; doenca_id?: number | null; categoria_preventiva?: string | null;
  data_primeiro?: string | null; frequencia_valor?: number | null; frequencia_unidade?: string | null;
  gatilho?: string | null; gatilho_lote?: string | null; gatilho_idade_meses?: number | null; offset_dias?: number | null;
  produto_padrao?: string | null; dose_padrao?: number | null; unidade_padrao?: string | null; via_padrao?: string | null;
  agenda_dias_antes?: number | null;
  // Exclusão mútua — ex.: não agendar se o animal já recebeu o evento apontado
  // aqui (alternativas de vacina/estirpe para a mesma doença).
  condicao_evento_id?: number | null;
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
export async function criarProtocoloSanitario(dados: { nome: string; doenca_id?: number | null; eh_mastite?: boolean; ativo?: boolean; etapas: ProtocoloEtapa[] }) {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar protocolo sanitário"); }
  return res.json();
}
export async function atualizarProtocoloSanitario(id: number, dados: { nome: string; doenca_id?: number | null; eh_mastite?: boolean; ativo?: boolean; etapas: ProtocoloEtapa[] }) {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar protocolo sanitário"); }
  return res.json();
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
  principio_ativo_id?: number; dosagem?: string; unidade?: string; veterinario?: string; frequencia_valor: number; frequencia_unidade: string;
  data_evento: string; observacao?: string; ativo?: boolean; realizado?: boolean;
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
  entradas: { numero_matriz: string; ordenhas: number[] }[];
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
export async function sugestaoLoteEvento(dados: { numero_matriz: string; categoria_abrev: string; del_dias?: number | null; data_nasc?: string | null }) {
  const res = await authFetch(`${API}/producao/sugestao-lote-evento`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao buscar sugestão de lote"); }
  return res.json();
}

// ── Serviço/IA: protocolo IATF (só agenda) e inseminação (o evento em si) ──
export type HormonioIatf = { dia: number; produto: string; dose?: number | null; unidade?: string; via?: string };
export async function criarProtocoloIatf(dados: { animais: string[]; data_d0: string; protocolo?: string; hormonios?: HormonioIatf[] }) {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao agendar protocolo IATF"); }
  return res.json();
}
export async function fetchProtocolosIatfAtivos() {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf/ativos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos IATF ativos error: ${res.status}`);
  return res.json();
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

export async function fetchPatrimonio() {
  const res = await authFetch(`${API}/financeiro/patrimonio`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Patrimônio error: ${res.status}`);
  return res.json();
}

export async function fetchOpcoesFinanceiro() {
  const res = await authFetch(`${API}/financeiro/opcoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Opções financeiro error: ${res.status}`);
  return res.json();
}

export async function fetchPlanoContas() {
  const res = await authFetch(`${API}/financeiro/plano-contas`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Plano de contas error: ${res.status}`);
  return res.json();
}
type ContaGerencialPayload = {
  codigo: string; nome: string; ativa?: boolean; participa_atividade?: boolean; fluxo?: boolean; tipo_fixo_variavel?: string;
  rmca_receita_leite?: boolean; rmca_custo_alimentacao?: boolean;
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

// ── Contas correntes (Configurações > Parâmetros financeiros) ──
export async function fetchContasCorrentes() {
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

export async function marcarPagoFinanceiro(id: number, dados: {
  data_pagamento: string; valor_pago: number; conta_bancaria?: string; numero_documento_pagamento?: string;
  forma_pagamento?: string; data_vencimento_cartao?: string;
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
  desconto_acrescimo?: number | null; responsavel?: string | null;
}) {
  const res = await authFetch(`${API}/financeiro/lancamentos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao editar o lançamento"); }
  return res.json();
}

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
export type AnexoLancamento = { id: number; nome_arquivo: string; mime_type: string; tamanho_bytes: number; criado_em?: string };

export async function anexarArquivoLancamento(numeroLancamento: string, file: File): Promise<AnexoLancamento> {
  const form = new FormData();
  form.append("file", file);
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
export type RecriaIdadeParto = { meta_idade_parto: number; estatisticas: WisconsinStats | null; distribuicao: { mes: number; n: number; pct: number }[]; custo_excedente: { n: number; dias_excedentes_total: number; custo_total: number; dias_por_novilha: number; custo_por_novilha: number } };
export type RecriaCiclo = { ciclo: number; inicio: string; fim: string; elegiveis: number; servidos: number; prenhes: number; taxa_servico: number | null; taxa_concepcao: number | null; taxa_prenhez: number | null };
export const fetchRecriaIdadeParto = (): Promise<RecriaIdadeParto> => _rGet(`/recria/reproducao/idade-parto`);
export const fetchRecriaTaxaPrenhez = (ini: string, fim: string, vwp = 0): Promise<{ ciclos: RecriaCiclo[]; taxa_prenhez_media: number | null; total_servicos: number }> =>
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

export type Estratificacao = { total: number; estratos: Record<string, number>; percentuais: Record<string, number>; vacas_total: number; pct_lactacao_sobre_total: number; pct_lactacao_sobre_vacas: number };
export const fetchEstratificacaoRebanho = (): Promise<Estratificacao> => _rGet(`/animais/estratificacao`);

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

// ── News (blog de pecuária leiteira) ──
export type NoticiaNews = {
  id: number; fonte_id: number; manchete: string; resumo?: string | null; link: string;
  data_publicacao?: string | null; capturado_em: string; materia?: string | null; fontes?: string[];
  revisado_final: boolean; revisado_final_em?: string | null; revisado_final_por?: string | null;
};
export type NewsFeed = { janela_dias: number; fontes: { fonte: { id: number; nome: string; url: string; erro?: string | null }; noticias: NoticiaNews[] }[] };

export const fetchNoticias = (verTudo = false): Promise<NewsFeed> => _rGet(`/news/${verTudo ? "?ver_tudo=true" : ""}`);

export type MateriaBlogIn = { manchete: string; materia: string; fontes: string[] };
export const criarMateriaBlog = (d: MateriaBlogIn): Promise<NoticiaNews> => _rSend(`/news/materias`, "POST", d);
export const excluirMateriaBlog = (id: number) => _rSend(`/news/materias/${id}`, "DELETE");
export const revisarPublicacaoFinal = (id: number): Promise<NoticiaNews> => _rSend(`/news/materias/${id}/revisar-final`, "POST");

// ── Assistente Claude (protótipo, admin-only) ──
export type AssistenteResposta = { resposta: string; historico: any[] };
export async function perguntarAssistente(mensagem: string, historico: any[] = []): Promise<AssistenteResposta> {
  return _rSend(`/assistente/perguntar`, "POST", { mensagem, historico });
}
