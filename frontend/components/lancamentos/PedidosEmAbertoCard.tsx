"use client";
import { useEffect, useState } from "react";
import { ShoppingCart, CircleDollarSign } from "lucide-react";
import { fetchPedidos, formatBRL } from "@/lib/api";
import { type PrefillPedido } from "@/components/FormFinanceiro";

type ItemPedidoAberto = {
  produto_servico: string; tipo_item: "produto" | "servico";
  quantidade?: number | null; valor_unitario_estimado?: number | null;
  valor_total_estimado: number; valor_atendido: number;
  codigo_conta_gerencial?: string | null; nome_conta_gerencial?: string | null;
};
type PedidoAberto = {
  id: number; numero_pedido: string; fornecedor_cliente: string | null;
  status: string; valor_total_estimado: number; valor_atendido: number;
  itens: ItemPedidoAberto[];
};

/**
 * Segunda porta de entrada pro mesmo fluxo do ícone "$ Lançar em Financeiro"
 * de app/pedidos/page.tsx — só que a partir de Financeiro > Lançar, pra quem
 * já tem um pedido em aberto e nem sabia que dava pra puxá-lo direto pra cá
 * (o vínculo em si já existia: seletor "Vincular a um pedido" dentro do
 * próprio FormFinanceiro, ver `pedidosAbertos`). Mesma lista/filtro que o
 * FormFinanceiro já busca sozinho (status ainda não cancelado/atendido, do
 * tipo compra/venda correspondente) — só fica visível ANTES de abrir o
 * formulário, em vez de escondida num <select>.
 *
 * "Finalizar pedido" monta o mesmo `PrefillPedido` que app/pedidos/page.tsx
 * já constrói para o botão $ (mesmo shape, valor restante = estimado - já
 * atendido) e entrega pro pai, que repassa pra prop `prefillPedido` do
 * FormFinanceiro genérico ao lado.
 */
export function PedidosEmAbertoCard({ tipo, onFinalizar }: {
  tipo: "despesa" | "receita";
  onFinalizar: (prefill: PrefillPedido) => void;
}) {
  const [pedidos, setPedidos] = useState<PedidoAberto[] | null>(null);

  // Mesmo filtro que FormFinanceiro já aplica sozinho no seu próprio
  // `pedidosAbertos` (ver components/FormFinanceiro.tsx) — refaz a busca a
  // cada troca de tipo, igual lá.
  useEffect(() => {
    fetchPedidos({ tipo: tipo === "despesa" ? "compra" : "venda" })
      .then((lista: PedidoAberto[]) => setPedidos(lista.filter((p) => p.status !== "cancelado" && p.status !== "atendido")))
      .catch(() => setPedidos([]));
  }, [tipo]);

  // Sem endpoint novo, sem card vazio poluindo a tela — some por completo
  // enquanto carrega ou quando não há nenhum pedido em aberto do tipo atual.
  if (!pedidos || pedidos.length === 0) return null;

  return (
    <div className="card mb-4" style={{ background: "var(--surface-2)" }}>
      <p style={{
        fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase",
        color: "var(--text-muted)", marginBottom: "0.6rem", display: "flex", alignItems: "center", gap: "0.35rem",
      }}>
        <ShoppingCart size={13} /> Pedidos em aberto
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
        {pedidos.map((p) => {
          const restante = p.valor_total_estimado - p.valor_atendido;
          return (
            <div key={p.id} style={{
              display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap",
              background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.65rem",
            }}>
              <div style={{ flex: 1, minWidth: 200 }}>
                <div style={{ fontSize: "0.82rem", fontWeight: 600 }}>{p.numero_pedido} — {p.fornecedor_cliente || "sem contraparte"}</div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                  {formatBRL(restante > 0 ? restante : p.valor_total_estimado)} restante · {formatBRL(p.valor_total_estimado)} no total
                </div>
              </div>
              <button type="button" className="btn-secondary" style={{ fontSize: "0.76rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                onClick={() => onFinalizar({
                  id: p.id, fornecedorCliente: p.fornecedor_cliente,
                  itens: p.itens.map((i) => ({
                    produto: i.produto_servico, tipo_item: i.tipo_item,
                    quantidade: i.quantidade, valor_unitario_estimado: i.valor_unitario_estimado,
                    valor_total_estimado: i.valor_total_estimado - i.valor_atendido > 0 ? i.valor_total_estimado - i.valor_atendido : i.valor_total_estimado,
                    codigo_conta_gerencial: i.codigo_conta_gerencial, nome_conta_gerencial: i.nome_conta_gerencial,
                  })),
                })}
              >
                <CircleDollarSign size={13} /> Finalizar pedido
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
