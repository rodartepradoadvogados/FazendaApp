"use client";
// Ponte entre o Balanço de estoque (site e app) e o Lançamento financeiro —
// ao marcar "gerar movimentação financeira" numa entrada/saída de estoque,
// a tela de destino escuta este evento e abre já preenchida com os dados do
// próprio balanço (produto, conta gerencial, quantidade, valor, data),
// faltando só o que é exclusivo do financeiro (pagamento, parcelamento,
// acréscimo/desconto, número do pagamento). Mesmo padrão de
// `alimentoEstoqueBridge.ts`, mas "sticky": como pedir o lançamento
// normalmente troca de aba/tela (o formulário de destino só monta DEPOIS do
// disparo), guarda o último pedido não consumido para quem inscrever
// depois também recebê-lo, e não só quem já estava ouvindo.
export type PrefillLancamentoEstoque = {
  tipo: "despesa" | "receita";
  produto: string;
  quantidade: number;
  unidade?: string | null;
  valor_unitario?: number | null;
  valor_total?: number | null;
  codigo_conta_gerencial?: string | null;
  data_emissao?: string;
  observacao?: string;
};

const EVT_FINANCEIRO = "fazenda:ir-lancamento-financeiro-do-estoque";
let pendente: PrefillLancamentoEstoque | null = null;

export function pedirLancamentoFinanceiro(dados: PrefillLancamentoEstoque) {
  pendente = dados;
  window.dispatchEvent(new CustomEvent<PrefillLancamentoEstoque>(EVT_FINANCEIRO, { detail: dados }));
}

export function onPedidoLancamentoFinanceiro(cb: (dados: PrefillLancamentoEstoque) => void) {
  if (pendente) {
    const dados = pendente;
    pendente = null;
    cb(dados);
  }
  const handler = (e: Event) => cb((e as CustomEvent<PrefillLancamentoEstoque>).detail);
  window.addEventListener(EVT_FINANCEIRO, handler);
  return () => window.removeEventListener(EVT_FINANCEIRO, handler);
}
