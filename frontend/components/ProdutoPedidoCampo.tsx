"use client";
// Campo de produto de Pedidos/Cotações. Com o módulo Estoque, é o EstoquePicker de sempre; sem ele
// (fazenda só-financeiro — Plano Financeiro §2.8) vira um campo de texto livre com sugestões do
// histórico de lançamentos, já que o cadastro de estoque não existe (GET /estoque/ = 403).
import { useEffect, useId, useState } from "react";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import { fetchOpcoesFinanceiro } from "@/lib/api";

// Histórico de nomes de produto já lançados (uma busca por sessão de página).
let historicoEmMemoria: string[] | null = null;

export function ProdutoPedidoCampo({ temEstoque, itensEstoque, value, onChange, placeholder, estilo }: {
  temEstoque: boolean; itensEstoque: EstoqueItemPicker[]; value: string; onChange: (v: string) => void;
  placeholder?: string; estilo: React.CSSProperties;
}) {
  const idLista = useId();
  const [historico, setHistorico] = useState<string[]>(historicoEmMemoria ?? []);
  useEffect(() => {
    if (temEstoque || historicoEmMemoria) return;
    let vivo = true;
    fetchOpcoesFinanceiro()
      .then((d) => { historicoEmMemoria = Array.isArray(d?.produtos) ? d.produtos : []; if (vivo) setHistorico(historicoEmMemoria!); })
      .catch(() => {});
    return () => { vivo = false; };
  }, [temEstoque]);

  if (temEstoque) {
    return <EstoquePicker itens={itensEstoque} value={value} todasFinalidades incluirNaoEstocaveis placeholder={placeholder} onChange={onChange} />;
  }
  return (
    <>
      <input list={idLista} style={{ ...estilo, width: "100%" }} value={value} onChange={(e) => onChange(e.target.value)}
        placeholder="ex.: Ração, Material de escritório, Combustível…" />
      <datalist id={idLista}>{historico.map((p) => <option key={p} value={p} />)}</datalist>
    </>
  );
}
