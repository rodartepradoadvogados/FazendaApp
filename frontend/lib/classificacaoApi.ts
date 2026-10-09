// Relatórios › Resultado › Classificar: chamadas e tipos da fila de pendências de
// classificação, do lote de ações e do Desfazer. Arquivo próprio (e não lib/api.ts)
// pelo mesmo motivo de fechamentoApi.ts. Contrato: docs/financeiro-regras-v2.md §13.
import { API, authFetch, erroDaResposta } from "@/lib/api";

export type MotivoClassificacao =
  | "conta_sem_linha_dre" | "sem_codigo_conta" | "item_sem_conta_automatica" | "natureza_nao_informada";
export type TipoAcao = "conta" | "natureza" | "linha_dre";

/** Para onde a ação grava: a conta do plano (`codigo`) ou o lançamento (`numero_lancamento`, + `item_id` ou `conta_id`). */
export type AlvoAcao = { codigo?: string; numero_lancamento?: string | null; item_id?: number | null; conta_id?: number | null };
export type AcaoClassificacao = { tipo: TipoAcao; alvo: AlvoAcao; valor: string };

export type SugestaoClassificacao = AcaoClassificacao & { rotulo: string; motivo: string };

export type LinhaPendencia = {
  chave: string; motivo: MotivoClassificacao;
  numero_lancamento: string | null; conta_id: number | null; item_id: number | null;
  tipo: "receita" | "despesa"; valor: number; parcelas: number; data: string | null; pago: boolean;
  fornecedor: string | null; descricao: string | null; produto: string | null; centro_custo: string | null;
  codigo_conta: string | null; nome_conta: string | null; conta_no_plano: boolean;
  natureza_atual: string | null; origem_automatica: string | null;
  mes_fechado: boolean; meses_fechados: string[];
  acoes: Record<TipoAcao, boolean>; travas: Partial<Record<TipoAcao, string>>;
  sugestao: SugestaoClassificacao | null;
};

export type ResumoMotivo = {
  motivo: MotivoClassificacao; rotulo: string; explicacao: string; quantidade: number; contas: number;
  total_receita: number; total_despesa: number; travado: string | null;
};

export type GrupoConta = {
  motivo: MotivoClassificacao; codigo: string | null; nome: string | null; conta_no_plano: boolean;
  quantidade: number; total_receita: number; total_despesa: number; sugestao: SugestaoClassificacao | null;
};

export type UltimoLote = { lote: string; criado_em: string; alteracoes: number; motivo: string | null };

export type FilaClassificacao = {
  periodo: { inicio: string; fim: string }; regime: string; centro_custo: string | null; regras_v2: boolean;
  resumo: { total_pendencias: number; total_receita: number; total_despesa: number; mostradas: number; truncado: boolean };
  por_motivo: ResumoMotivo[]; por_conta: GrupoConta[]; pendencias: LinhaPendencia[];
  bloqueios: { motivo: MotivoClassificacao; porque: string }[];
  ultimo_lote: UltimoLote | null;
};

export type ResultadoLote = {
  lote: string | null; aplicadas: number; sem_mudanca: number; alteracoes: number; avisos: string[];
  acoes: { indice: number; tipo: TipoAcao; mudou: boolean; alvo: string }[];
};

export type ResultadoReversao = {
  lote: string; revertidas: number; ja_revertidas: number;
  conflitos: { tabela: string; id: number; campo: string; valor_atual: unknown }[]; nao_encontradas: unknown[];
};

async function json<T>(res: Response, padrao: string): Promise<T> {
  if (!res.ok) throw await erroDaResposta(res, padrao);
  return res.json() as Promise<T>;
}

export async function fetchFilaClassificacao(p: {
  data_inicio: string; data_fim: string; regime: "competencia" | "caixa"; centro_custo?: string | null;
}): Promise<FilaClassificacao> {
  const q = new URLSearchParams({ data_inicio: p.data_inicio, data_fim: p.data_fim, regime: p.regime });
  if (p.centro_custo) q.set("centro_custo", p.centro_custo);
  return json(await authFetch(`${API}/financeiro/classificacao/pendencias?${q}`, { cache: "no-store" }), "Erro ao ler o que falta classificar");
}

export async function aplicarClassificacao(acoes: AcaoClassificacao[], motivo?: string | null): Promise<ResultadoLote> {
  return json(await authFetch(`${API}/financeiro/classificacao/aplicar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ acoes, motivo: motivo || null }),
  }), "Erro ao classificar");
}

export async function reverterClassificacao(lote: string): Promise<ResultadoReversao> {
  return json(await authFetch(`${API}/financeiro/classificacao/reverter/${encodeURIComponent(lote)}`, { method: "POST" }), "Erro ao desfazer a classificação");
}
