// Sugestão pelo fornecedor: a partir do ÚLTIMO lançamento do mesmo fornecedor/cliente, o que o formulário
// pode preencher sozinho (produto, conta gerencial, centro de custo, classificação, prazo de vencimento).
// Função pura sobre o extrato que o app já carrega (GET /financeiro/lancamentos) — sem endpoint novo.
// Tudo que sai daqui é só SUGESTÃO: o formulário preenche apenas campos ainda vazios e marca a origem.

export type LinhaExtrato = {
  tipo?: string; numero_lancamento?: string | null; fornecedor?: string | null;
  data_emissao?: string | null; data_vencimento?: string | null; parcela_num?: number | null;
  centro_custo?: string | null; classificacao?: string | null; natureza_fin?: string | null;
  gerado_por?: string | null; id?: number;
  itens?: {
    produto?: string | null; tipo_item?: string | null; codigo_conta_gerencial?: string | null; nome_conta_gerencial?: string | null;
    quantidade?: number | null; valor_unitario?: number | null; eh_vale?: boolean; gerado_por?: string | null;
  }[];
};

export type SugestaoFornecedor = {
  numeroLancamento: string; dataEmissao: string | null;
  produto: string | null; tipoItem: "produto" | "servico";
  codigoConta: string | null; nomeConta: string | null;
  centroCusto: string | null; classificacao: string | null; naturezaFin: string | null;
  /** Dias entre a emissão e o 1º vencimento do último lançamento (null se não der para saber ou for absurdo). */
  prazoDias: number | null;
};

const norm = (s: string | null | undefined) => (s || "").trim().toLowerCase();

function diasEntre(a: string, b: string): number {
  const [ya, ma, da] = a.split("-").map(Number);
  const [yb, mb, db] = b.split("-").map(Number);
  return Math.round((Date.UTC(yb, mb - 1, db) - Date.UTC(ya, ma - 1, da)) / 86400000);
}

/** Último lançamento (mais recente por emissão, depois por número) do fornecedor/cliente, ignorando notas automáticas. */
export function sugestaoDoFornecedor(extrato: LinhaExtrato[], nome: string, tipo: "despesa" | "receita"): SugestaoFornecedor | null {
  const alvo = norm(nome);
  if (!alvo) return null;
  const doFornecedor = extrato.filter((l) => l.tipo === tipo && norm(l.fornecedor) === alvo && l.numero_lancamento && !l.gerado_por);
  if (!doFornecedor.length) return null;
  // Uma nota = um número de lançamento (parcelas são linhas); fica a de emissão mais recente.
  const porNota = new Map<string, LinhaExtrato[]>();
  for (const l of doFornecedor) porNota.set(l.numero_lancamento as string, [...(porNota.get(l.numero_lancamento as string) || []), l]);
  const notas = Array.from(porNota.entries()).sort(([na, a], [nb, b]) => {
    const da = a[0].data_emissao || "", db = b[0].data_emissao || "";
    return db.localeCompare(da) || nb.localeCompare(na);
  });
  const [numero, linhas] = notas[0];
  const primeira = [...linhas].sort((x, y) => (x.parcela_num ?? 1) - (y.parcela_num ?? 1))[0];
  // Item "da fazenda": vale de funcionário e itens gerados pelo sistema não dizem nada sobre o fornecedor.
  const item = (primeira.itens || []).find((i) => i.produto && !i.eh_vale && !i.gerado_por);
  let prazo: number | null = null;
  if (primeira.data_emissao && primeira.data_vencimento) {
    const d = diasEntre(primeira.data_emissao, primeira.data_vencimento);
    prazo = d >= 0 && d <= 180 ? d : null;
  }
  return {
    numeroLancamento: numero, dataEmissao: primeira.data_emissao || null,
    produto: item?.produto || null, tipoItem: item?.tipo_item === "servico" ? "servico" : "produto",
    codigoConta: item?.codigo_conta_gerencial || null, nomeConta: item?.nome_conta_gerencial || null,
    centroCusto: primeira.centro_custo && primeira.centro_custo !== "Sem centro de custo" ? primeira.centro_custo : null,
    classificacao: primeira.classificacao || null, naturezaFin: primeira.natureza_fin || null,
    prazoDias: prazo,
  };
}

/** Soma `dias` a uma data AAAA-MM-DD (UTC, sem fuso). */
export function somarDias(data: string, dias: number): string {
  const [y, m, d] = data.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + dias)).toISOString().slice(0, 10);
}
