export type Filtros = Record<string, unknown>;
const str = (v: unknown) => (typeof v === "string" ? v : "");

/** Converte um filtro salvo das telas antigas (Pagas, Recebidas, Extrato, Todas, Livro) no formato da tela Consultas. */
export function filtroAntigoParaConsultas(filtros: Filtros, origem: "pagas" | "recebidas" | "extrato" | "todas_contas" | "livro"): Filtros {
  const tipo = str(filtros.relTipo);
  const movimento = origem === "pagas" ? "pagamento" : origem === "recebidas" ? "recebimento" : tipo === "receita" ? "recebimento" : tipo === "despesa" ? "pagamento" : "ambos";
  const periodo = str(filtros.campoPeriodoContas);
  return {
    movimento,
    periodoPor: periodo === "emissao" || periodo === "vencimento" ? periodo : "pagamento",
    de: str(filtros.inicio),
    ate: str(filtros.fim),
    centro: str(filtros.centro),
    banco: str(filtros.contaBanco),
    documento: str(filtros.relDocumento),
    produto: str(filtros.relProduto),
    fornecedor: str(filtros.relFornecedor),
    conta: str(filtros.relConta),
    contaNome: str(filtros.relContaNome),
    ...(origem === "livro" ? { modo: "livro" } : {}),
  };
}
