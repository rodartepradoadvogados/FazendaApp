// Histórico local dos KPIs do Cockpit do Painel CowData — usado para desenhar
// a seta de tendência e o sparkline nos cartões (ver app/painel-cowdata/page.tsx).
//
// LIMITAÇÃO CONHECIDA (aceita conscientemente, redesign T10): o backend não
// guarda série histórica nenhuma desses números hoje — /fazendas/catalogo/
// resumo-cowdata sempre devolve só a fotografia ATUAL (ver
// backend/fazenda/api/routers/fazendas.py::resumo_cowdata) — e mudar isso
// exigiria uma tabela nova + um job, fora do escopo (zero mudança de backend
// neste redesign). Guardamos então uma leitura por DIA (fuso do navegador de
// quem abre o Cockpit) em localStorage, sobrescrevendo a de hoje a cada
// carregamento — assim a tendência/sparkline refletem a evolução real ao
// longo dos dias em que o painel foi aberto NESTE navegador, não um histórico
// de verdade guardado no servidor. Consequências assumidas: (1) é por
// navegador/dispositivo, não compartilhado entre quem administra a CowData;
// (2) um dia em que ninguém abre o Cockpit não vira um ponto na série
// (amostragem por uso, não por tempo); (3) limpar dados do site zera o
// histórico. Nenhuma dessas é um problema de dado errado — é sempre a
// fotografia real do resumo-cowdata no dia em que foi lida, só que a série
// como um todo é parcial.
export type PontoHistoricoKpisCowData = {
  data: string; // "AAAA-MM-DD", data local de quem abriu o Cockpit
  mrr: number;
  total_fazendas: number;
  ativo: number;
  aguardando_aprovacao: number;
};

const CHAVE_LOCALSTORAGE = "painel_cowdata_historico_kpis_v1";
const MAX_PONTOS = 30; // ~1 mês de leituras diárias é o bastante para o sparkline

function dataLocalDeHoje(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function lerHistorico(): PontoHistoricoKpisCowData[] {
  if (typeof window === "undefined") return [];
  try {
    const bruto = window.localStorage.getItem(CHAVE_LOCALSTORAGE);
    if (!bruto) return [];
    const lista = JSON.parse(bruto);
    return Array.isArray(lista) ? lista : [];
  } catch {
    return [];
  }
}

/** Registra a leitura de hoje (substitui a de hoje se já existir) e devolve a
 * série completa, mais antiga primeiro — pronta para o sparkline. */
export function registrarLeituraKpisCowData(resumo: {
  mrr: number; total_fazendas: number; ativo: number; aguardando_aprovacao: number;
}): PontoHistoricoKpisCowData[] {
  const historico = lerHistorico();
  const hoje = dataLocalDeHoje();
  const ponto: PontoHistoricoKpisCowData = {
    data: hoje, mrr: resumo.mrr, total_fazendas: resumo.total_fazendas,
    ativo: resumo.ativo, aguardando_aprovacao: resumo.aguardando_aprovacao,
  };
  const idxHoje = historico.findIndex((p) => p.data === hoje);
  if (idxHoje >= 0) historico[idxHoje] = ponto;
  else historico.push(ponto);
  const cortado = historico.slice(-MAX_PONTOS);
  if (typeof window !== "undefined") {
    try { window.localStorage.setItem(CHAVE_LOCALSTORAGE, JSON.stringify(cortado)); } catch { /* modo privado, quota etc. — segue sem persistir */ }
  }
  return cortado;
}

export type TendenciaKpi = { direcao: "alta" | "baixa" | "estavel" | "sem_dado"; delta: number; percentual: number | null };

/** Compara o valor de hoje com a leitura anterior mais recente (dia diferente
 * de hoje) — "sem_dado" quando ainda não há nenhuma leitura anterior guardada
 * (primeira vez que o Cockpit é aberto neste navegador). */
export function calcularTendencia(historico: PontoHistoricoKpisCowData[], chave: keyof Omit<PontoHistoricoKpisCowData, "data">): TendenciaKpi {
  if (historico.length < 2) return { direcao: "sem_dado", delta: 0, percentual: null };
  const atual = historico[historico.length - 1];
  const anterior = historico[historico.length - 2];
  const delta = atual[chave] - anterior[chave];
  const percentual = anterior[chave] !== 0 ? (delta / Math.abs(anterior[chave])) * 100 : null;
  return { direcao: delta > 0 ? "alta" : delta < 0 ? "baixa" : "estavel", delta, percentual };
}
