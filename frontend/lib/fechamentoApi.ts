// Relatórios › Entrega ao contador (Fase C5): chamadas e tipos do Fechamento do
// mês, da Conciliação bancária e do Pacote do contador. Arquivo próprio (e não
// lib/api.ts) para a integração com as outras telas da Fase C ser só uma linha.
// Contrato: docs/financeiro-fechamento-conciliacao.md.
import { API, authFetch, erroDaResposta } from "@/lib/api";

// ── Fechamento do mês ──────────────────────────────────────────────────────
export type StatusMes = "aberto" | "fechado" | "em_curso";
export type EventoFechamento = {
  id: number; mes: string; acao: "fechar" | "reabrir"; motivo: string | null; usuario: string | null;
  criado_em: string | null; retrato_sha256: string | null; pendencias_no_fechamento: number;
};
export type ItemChecklist = {
  id: string; nome: string; txt: string; ok: boolean; bloqueia: boolean; quantidade: number;
  itens: Record<string, unknown>[]; destino: string | null; rotulo_acao: string | null; resumo: string | null;
};
export type Retrato = {
  mes: string; regras_v2: boolean;
  dre_competencia: { linhas: Record<string, number>; nao_classificado: number; fora_da_dre: number };
  dre_caixa: { linhas: Record<string, number>; nao_classificado: number; fora_da_dre: number };
  caixa: { entradas: number; saidas: number; saldos_fim_do_mes: Record<string, number> };
};
export type SituacaoMes = {
  mes: string; inicio: string; fim: string; regras_v2: boolean; status: StatusMes; pode_fechar_a_partir_de: string;
  evento_atual: EventoFechamento | null; trilha_do_mes: EventoFechamento[];
  checklist: ItemChecklist[]; pendencias: number;
  retrato_atual: Retrato; retrato_atual_sha256: string;
  retrato_fechamento?: Retrato | null; mudou_desde_o_fechamento?: boolean;
};
export type MesResumo = { mes: string; status: StatusMes; fechado_em: string | null; fechado_por: string | null; reaberto: boolean };
export type MesesResposta = { regras_v2: boolean; hoje: string; meses: MesResumo[]; trilha: EventoFechamento[] };

async function json<T>(res: Response, padrao: string): Promise<T> {
  if (!res.ok) throw await erroDaResposta(res, padrao);
  return res.json() as Promise<T>;
}

export async function fetchMesesFechamento(ate?: string, quantidade = 24): Promise<MesesResposta> {
  const q = new URLSearchParams({ quantidade: String(quantidade) });
  if (ate) q.set("ate", ate);
  return json(await authFetch(`${API}/financeiro/fechamento/meses?${q}`, { cache: "no-store" }), "Erro ao ler os meses do fechamento");
}

export async function fetchFechamentoMes(mes: string): Promise<SituacaoMes> {
  return json(await authFetch(`${API}/financeiro/fechamento/${mes}`, { cache: "no-store" }), "Erro ao ler o fechamento do mês");
}

export async function fecharMes(mes: string, dados: { motivo?: string | null; forcar?: boolean }) {
  return json<{ evento: EventoFechamento }>(await authFetch(`${API}/financeiro/fechamento/${mes}/fechar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  }), "Erro ao fechar o mês");
}

export async function reabrirMes(mes: string, motivo: string) {
  return json<{ evento: EventoFechamento }>(await authFetch(`${API}/financeiro/fechamento/${mes}/reabrir`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ motivo }),
  }), "Erro ao reabrir o mês");
}

// ── Conciliação bancária ───────────────────────────────────────────────────
export type MovSistema = {
  tipo: "lancamento" | "transferencia"; id: number; data: string; valor: number;
  descricao: string | null; fornecedor: string | null; numero_lancamento: string | null; documento?: string | null;
  exata?: boolean; diferenca?: number; dias?: number; pontuacao?: number;
};
export type LinhaExtrato = {
  id: number; data: string; valor: number; historico: string | null; documento: string | null;
  status: "pendente" | "pareado" | "sem_lancamento"; lancamento_id: number | null; transferencia_id: number | null;
  observacao: string | null; conciliado_em: string | null;
  par: MovSistema | null; sugestao: MovSistema | null; alternativas: MovSistema[];
};
export type SaldosConciliacao = {
  saldo_extrato: number | null; saldo_sistema: number | null; diferenca: number | null; bate: boolean | null;
  data: string; pendente_saldo_abertura: boolean;
};
export type SituacaoConciliacao = {
  conta_corrente_id: number; conta: string; banco: string; periodo: { inicio: string; fim: string }; importado: boolean;
  linhas: LinhaExtrato[]; so_no_sistema: MovSistema[];
  contagem: { linhas: number; pareadas: number; pendentes: number; sem_lancamento: number; so_no_sistema: number; sugestoes_exatas: number };
  movimento: { extrato: number; sistema: number; diferenca: number };
  saldos: SaldosConciliacao;
};
export type ResumoContaConciliacao = {
  conta_corrente_id: number; conta: string; importado: boolean; tem_movimento: boolean; pendentes: number;
  so_no_sistema: number; saldos: SaldosConciliacao; movimento: { extrato: number; sistema: number; diferenca: number }; conciliada: boolean;
};
export type ConciliacaoResposta = {
  mes: string; contas: { id: number; rotulo: string; banco: string }[]; resumo: ResumoContaConciliacao[];
  situacao: SituacaoConciliacao | null;
  importacoes?: { id: number; formato: string; data_inicio: string | null; data_fim: string | null; saldo_final: number | null;
    data_saldo: string | null; linhas_novas: number; linhas_repetidas: number; criado_em: string }[];
};

export async function fetchConciliacao(mes: string, contaId?: number | null): Promise<ConciliacaoResposta> {
  const q = new URLSearchParams({ mes });
  if (contaId) q.set("conta_corrente_id", String(contaId));
  return json(await authFetch(`${API}/financeiro/conciliacao?${q}`, { cache: "no-store" }), "Erro ao ler a conciliação");
}

export async function importarExtrato(contaId: number, arquivo: File) {
  const fd = new FormData();
  fd.append("conta_corrente_id", String(contaId));
  fd.append("arquivo", arquivo);
  return json<{ formato: string; linhas_novas: number; linhas_repetidas: number; data_inicio: string | null; data_fim: string | null; saldo_final: number | null }>(
    await authFetch(`${API}/financeiro/conciliacao/importar`, { method: "POST", body: fd }), "Erro ao importar o extrato");
}

async function postLinha(linhaId: number, acao: string, corpo?: unknown) {
  return json<{ id: number; status: string }>(await authFetch(`${API}/financeiro/conciliacao/linhas/${linhaId}/${acao}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo ?? {}),
  }), "Erro ao conciliar a linha");
}
export const parearLinha = (linhaId: number, par: { lancamento_id?: number; transferencia_id?: number }) => postLinha(linhaId, "parear", par);
export const marcarSemLancamento = (linhaId: number, observacao?: string) => postLinha(linhaId, "sem-lancamento", { observacao });
export const desfazerLinha = (linhaId: number) => postLinha(linhaId, "desfazer");

export async function confirmarSugestoes(contaId: number, mes: string, linhaIds?: number[]) {
  return json<{ pareadas: number }>(await authFetch(`${API}/financeiro/conciliacao/confirmar-sugestoes`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conta_corrente_id: contaId, mes, linha_ids: linhaIds ?? null }),
  }), "Erro ao confirmar os pareamentos");
}

// ── Pacote do contador ─────────────────────────────────────────────────────
export type ItemPacote = { id: string; nome: string; formato: string; ok: boolean; detalhe: string };
export type PacoteResumo = {
  cabecalho: { fazenda: string; documento: string | null; periodo: { inicio: string; fim: string }; regime: string; centro: string;
    gerado_em: string; gerado_por: string; regras_v2: boolean };
  itens: ItemPacote[]; metodo: string[];
  dre: { competencia: { resultado: number; receita_liquida: number }; caixa: { resultado: number; receita_liquida: number } };
  livro: { saldo_inicial: number; saldo_final: number; entradas: number; saidas: number; saldo_inicial_pendente: boolean;
    receitas_atividade: number | null; despesas_atividade: number | null; lancamentos: number;
    meses: { mes: string; entradas: number; saidas: number; saldo: number; lancamentos: number }[] };
  pendencias: { mes: string; conferencia: string; quantidade: number; bloqueia: boolean; detalhe: string }[];
  conciliacao: ResumoContaConciliacao[];
  fechamentos: { meses: { mes: string; status: string; retrato_sha256: string | null }[]; trilha: EventoFechamento[] };
  patrimonio: { bens: number; depreciacao_periodo: number; inconsistencias: unknown[] };
  nao_classificados: { codigo: string | null; nome: string | null }[];
  arquivos: string[];
};

export async function fetchPacoteContador(inicio: string, fim: string): Promise<PacoteResumo> {
  const q = new URLSearchParams({ data_inicio: inicio, data_fim: fim });
  return json(await authFetch(`${API}/financeiro/pacote-contador?${q}`, { cache: "no-store" }), "Erro ao montar o pacote do contador");
}

/** Baixa o ZIP (ou só o PDF) do pacote; devolve o nome do arquivo baixado. */
export async function baixarPacoteContador(inicio: string, fim: string, formato: "zip" | "pdf"): Promise<string> {
  const q = new URLSearchParams({ data_inicio: inicio, data_fim: fim });
  const res = await authFetch(`${API}/financeiro/pacote-contador/${formato}?${q}`);
  if (!res.ok) throw await erroDaResposta(res, "Erro ao gerar o pacote do contador");
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const nome = /filename="?([^"]+)"?/.exec(cd)?.[1] || `pacote-contador_${inicio}_${fim}.${formato}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = nome;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return nome;
}
