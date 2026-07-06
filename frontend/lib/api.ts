// Funções de comunicação com o backend FastAPI
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    const res = await fetch(`${API}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchAgenda(data?: string) {
  const url = data ? `${API}/agenda/?data=${data}` : `${API}/agenda/`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Agenda error: ${res.status}`);
  return res.json();
}

export async function fetchAnimais(params?: { grupo?: string; sit_rep?: string }) {
  const qs = new URLSearchParams();
  if (params?.grupo) qs.set("grupo", params.grupo);
  if (params?.sit_rep) qs.set("sit_rep", params.sit_rep);
  const res = await fetch(`${API}/animais/?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Animais error: ${res.status}`);
  return res.json();
}

export async function fetchIndicadores(data?: string) {
  const url = data ? `${API}/indicadores/?data=${data}` : `${API}/indicadores/`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Indicadores error: ${res.status}`);
  return res.json();
}

export async function fetchServicosAnalise() {
  const res = await fetch(`${API}/reproducao/servicos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Análise error: ${res.status}`);
  return res.json();
}

export async function fetchAlimentacao() {
  const res = await fetch(`${API}/alimentacao/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Alimentação error: ${res.status}`);
  return res.json();
}

export async function fetchProducao() {
  const res = await fetch(`${API}/producao/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Produção error: ${res.status}`);
  return res.json();
}

export async function fetchControles() {
  const res = await fetch(`${API}/producao/controles`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Controles error: ${res.status}`);
  return res.json();
}

export async function fetchLancamentos() {
  const res = await fetch(`${API}/financeiro/lancamentos`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Financeiro error: ${res.status}`);
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
  const res = await fetch(`${API}/financeiro/dre?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`DRE error: ${res.status}`);
  return res.json();
}

export async function uploadCSV(tipo: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  let res: Response;
  try {
    res = await fetch(`${API}/upload/${tipo}`, {
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
  const res = await fetch(`${API}/agenda/manual?${qs}`, { method: "POST" });
  if (!res.ok) throw new Error("Erro ao adicionar evento");
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
