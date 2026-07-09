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
  "/reproducao": "reproducao", "/analise-reprodutiva": "analise", "/rebanho": "rebanho",
  "/producao": "producao", "/alimentacao": "alimentacao", "/sanidade": "sanidade",
  "/financeiro": "financeiro", "/estoque": "estoque", "/parametros": "parametros", "/upload": "upload",
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
export async function fetchUsuarios() {
  const res = await fetch(`${API}/auth/usuarios`, { headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {}, cache: "no-store" });
  if (!res.ok) throw new Error(`Usuários error: ${res.status}`);
  return res.json();
}
export async function criarUsuario(dados: { username: string; senha: string; nome?: string; papel: string; permissoes: string[] }) {
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
  return data.usuario;
}

// fetch com token; redireciona ao login se a sessão cair (401).
function authFetch(url: string, opts: RequestInit = {}): Promise<Response> {
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

export async function marcarEventoRealizado(eventoId: string) {
  const res = await authFetch(`${API}/agenda/realizados`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ evento_id: eventoId }),
  });
  if (!res.ok) throw new Error("Erro ao marcar como realizado");
  return res.json();
}

export async function desmarcarEventoRealizado(eventoId: string) {
  const res = await authFetch(`${API}/agenda/realizados/${eventoId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erro ao desfazer");
  return res.json();
}

export async function fetchAnimais(params?: { grupo?: string; sit_rep?: string }) {
  const qs = new URLSearchParams();
  if (params?.grupo) qs.set("grupo", params.grupo);
  if (params?.sit_rep) qs.set("sit_rep", params.sit_rep);
  const res = await authFetch(`${API}/animais/?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Animais error: ${res.status}`);
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

export async function salvarDiagnostico(dados: {
  numero_matriz: string; data_diagnostico: string; resultado: "retoque" | "reconfirmada" | "negativo"; metodo?: string;
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
export async function criarPessoa(dados: { nome: string; tipo: string; telefone?: string; email?: string; observacoes?: string; ativo?: boolean; salario_base?: number }) {
  const res = await authFetch(`${API}/cadastro/pessoas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao criar pessoa"); }
  return res.json();
}
export async function atualizarPessoa(id: number, dados: { nome: string; tipo: string; telefone?: string; email?: string; observacoes?: string; ativo?: boolean; salario_base?: number }) {
  const res = await authFetch(`${API}/cadastro/pessoas/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao atualizar pessoa"); }
  return res.json();
}

// ── Folha de pagamento (Configurações > Cadastro / Financeiro) ──
export async function fetchFolhaPagamento() {
  const res = await authFetch(`${API}/cadastro/folha-pagamento`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Folha de pagamento error: ${res.status}`);
  return res.json();
}
export async function criarFolhaPagamento(dados: { pessoa_id: number; competencia: string; valor_bruto: number; descontos?: number; data_pagamento?: string; status?: string; observacao?: string; recorrente?: boolean; dia_vencimento?: number | null }) {
  const res = await authFetch(`${API}/cadastro/folha-pagamento`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar folha de pagamento"); }
  return res.json();
}
export async function atualizarFolhaPagamento(id: number, dados: { pessoa_id: number; competencia: string; valor_bruto: number; descontos?: number; data_pagamento?: string; status?: string; observacao?: string; recorrente?: boolean; dia_vencimento?: number | null }) {
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
export async function atualizarMetaEstoque(id: number, dados: { ensacado?: boolean | null; kg_por_saco?: number | null; fornecedor_id?: number | null }) {
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
  animais: string[]; tipo_baixa: string; motivo: string; motivo_doenca?: string;
  valor?: number; cliente?: string; data_baixa: string; observacao?: string; responsavel?: string;
}) {
  const res = await authFetch(`${API}/baixas/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao registrar baixa"); }
  return res.json();
}

export async function fetchSanidade() {
  const res = await authFetch(`${API}/sanidade/aplicacoes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Sanidade error: ${res.status}`);
  return res.json();
}

export async function fetchUnidadesCompativeis(produto: string) {
  const res = await authFetch(`${API}/sanidade/unidades-compativeis?produto=${encodeURIComponent(produto)}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Unidades compatíveis error: ${res.status}`);
  return res.json();
}

export async function criarAplicacaoSanidade(dados: {
  data_aplicacao: string; animais: string[]; responsavel?: string; observacao?: string;
  itens: { produto: string; via?: string; quantidade: number; unidade: string }[];
}) {
  const res = await authFetch(`${API}/sanidade/aplicacoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar aplicação de sanidade"); }
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

const _doencas = _crudNomeAtivo("doencas", "Doença");
export const fetchDoencas = _doencas.listar;
export const criarDoenca = _doencas.criar;
export const atualizarDoenca = _doencas.atualizar;

const _eventosSanitarios = _crudNomeAtivo("eventos-sanitarios", "Evento sanitário");
export const fetchEventosSanitarios = _eventosSanitarios.listar;
export const criarEventoSanitario = _eventosSanitarios.criar;
export const atualizarEventoSanitario = _eventosSanitarios.atualizar;

// ── Protocolo sanitário (cadastro + lançamento) ──
export type ProtocoloEtapa = { dia: number; produto: string; dosagem: number; unidade: string; via?: string | null };
export async function fetchProtocolosSanitarios() {
  const res = await authFetch(`${API}/cadastro/protocolos-sanitarios`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Protocolos sanitários error: ${res.status}`);
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
  protocolo_id: number; numero_matriz: string; data_inicio: string; responsavel?: string; observacao?: string;
  classificacao_mastite?: string; resultado_cmt?: string; tetos_afetados?: string[];
}) {
  const res = await authFetch(`${API}/sanidade/protocolos/lancamentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar protocolo sanitário"); }
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
  principio_ativo_id?: number; dosagem?: string; frequencia_valor: number; frequencia_unidade: string;
  data_evento: string; observacao?: string; ativo?: boolean;
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

export async function fetchEstoque() {
  const res = await authFetch(`${API}/estoque/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Estoque error: ${res.status}`);
  return res.json();
}

export async function movimentarEstoque(dados: {
  nome: string; movimento: string; quantidade: number; unidade?: string; data_movimento: string; observacao?: string;
}) {
  const res = await authFetch(`${API}/estoque/movimentar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar movimento de estoque"); }
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

// ── Lançamento de dieta (Lançamentos > Alimentação) ──
export async function fetchAlimentosPadrao() {
  const res = await authFetch(`${API}/alimentacao/alimentos-padrao`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Alimentos padrão error: ${res.status}`);
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

export async function criarDieta(dados: {
  lote: number; responsavel?: string; data_abertura: string; data_prevista_encerramento?: string; observacao?: string;
  itens: { alimento: string; quantidade: number; unidade: string }[];
}) {
  const res = await authFetch(`${API}/alimentacao/dietas`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao lançar dieta"); }
  return res.json();
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
// ── Secagem ──
export async function fetchSecagemInfo(numeroMatriz: string) {
  const res = await authFetch(`${API}/producao/secagem-info?numero_matriz=${encodeURIComponent(numeroMatriz)}`, { cache: "no-store" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao buscar dados de secagem"); }
  return res.json();
}
export async function criarSecagem(dados: {
  numero_matriz: string; data_secagem: string; motivo: string; escore_condicao_corporal?: number | null;
  observacao?: string; responsavel?: string;
  produtos: { produto: string; via?: string; quantidade: number; unidade: string }[];
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
export async function criarProtocoloIatf(dados: { animais: string[]; data_d0: string; protocolo?: string }) {
  const res = await authFetch(`${API}/reproducao/protocolo-iatf`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao agendar protocolo IATF"); }
  return res.json();
}
export async function criarServico(dados: {
  numero_matriz: string; data_servico: string; tipo_servico?: string;
  protocolo?: string; reprodutor?: string; responsavel?: string;
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
  retencao_placenta?: boolean; gemelar?: boolean; observacao?: string;
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

export async function importarXmlFinanceiro(xml: string) {
  const res = await authFetch(`${API}/financeiro/importar-xml`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ xml }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao ler o XML"); }
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
  observacao?: string;
}) {
  const qs = new URLSearchParams({
    data_evento: data.data_evento,
    descricao: data.descricao,
    categoria: data.categoria || "Gestão/Financeiro",
  });
  if (data.numero_animal) qs.set("numero_animal", data.numero_animal);
  if (data.observacao) qs.set("observacao", data.observacao);
  const res = await authFetch(`${API}/agenda/manual?${qs}`, { method: "POST" });
  if (!res.ok) throw new Error("Erro ao adicionar evento");
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
