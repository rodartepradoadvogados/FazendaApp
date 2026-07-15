"use client";
// Tipos e agregações compartilhados pelas 4 sub-telas de Financeiro do Menu
// (Fluxo de caixa, DRE, RMCA, Extrato completo) — todas só leitura, lendo do
// mesmo endpoint "cru" do site (GET /financeiro/lancamentos) e filtrando no
// cliente, igual ao próprio site faz hoje (ver financeiro/page.tsx).
export type Lancamento = {
  id: number;
  numero_lancamento: string;
  tipo: string; // "receita" | "despesa"
  valor: number;
  centro_custo: string;
  codigo_conta: string;
  descricao: string;
  fornecedor: string;
  numero_documento?: string | null;
  data_competencia: string | null;
  data_pagamento: string | null;
  data_vencimento: string | null;
};

export type Opcoes = { centros_custo?: string[] };

export function dentroPeriodo(data: string | null, inicio: string, fim: string): boolean {
  if (!data) return false;
  return data >= inicio && data <= fim;
}

/** Pílula simples de filtro (Todos / Receitas / Despesas). */
export const TIPOS_FILTRO = [
  { chave: "ambos", rotulo: "Ambos" },
  { chave: "receita", rotulo: "Receitas" },
  { chave: "despesa", rotulo: "Despesas" },
] as const;
export type TipoFiltro = (typeof TIPOS_FILTRO)[number]["chave"];
