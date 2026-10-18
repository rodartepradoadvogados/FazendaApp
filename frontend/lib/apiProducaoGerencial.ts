// Chamadas novas das telas gerenciais de Lançamentos › Produção (Qualidade do leite etc.). Arquivo próprio (não em api.ts)
// para não disputar o arquivo compartilhado com as outras telas em andamento.
import { API, authFetch } from "@/lib/api";
import type { FaixaBonificacao } from "@/lib/qualidadeLeite";

/** GET /producao/faixas-bonificacao-qualidade — tabela de bonificação do laticínio (Configurações › Parâmetros). */
export async function fetchFaixasBonificacaoQualidade(): Promise<FaixaBonificacao[]> {
  const res = await authFetch(`${API}/producao/faixas-bonificacao-qualidade`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Faixas de bonificação: ${res.status}`);
  const d = await res.json();
  return Array.isArray(d?.faixas) ? d.faixas : [];
}
