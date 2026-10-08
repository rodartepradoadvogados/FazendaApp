"use client";
// TEMPORÁRIO (verificação visual do ResumoView) — apagar.
import { useState } from "react";
import ResumoView, { type DrillContas } from "@/components/financeiro/ResumoView";
import type { Lanc } from "@/lib/financeiroTipos";
import { hojeLocal, somaDias } from "@/lib/financeiroSituacao";

let seq = 0;
function l(p: Partial<Lanc>): Lanc {
  seq++;
  return { id: seq, numero_lancamento: `LC-${seq}`, tipo: "despesa", valor: 100, valor_pago: null, desconto_acrescimo: 0, centro_custo: "Leite",
    codigo_conta: "3", conta_completa: "3.01", descricao: "Nota", fornecedor: "Fornecedor", responsavel: null, tipo_documento: "NF",
    numero_documento: null, numero_os_orcamento: null, numero_documento_pagamento: null, conta_bancaria: null, forma_pagamento: null,
    data_vencimento_cartao: null, entregue: null, parcela_num: 1, parcela_total: 1, data_competencia: null, data_pagamento: null,
    data_vencimento: hojeLocal(), data_emissao: null, mes_competencia: null, mes_caixa: null, ...p } as Lanc;
}
export default function Page() {
  const h = hojeLocal(); const e = (n: number) => somaDias(h, n);
  const vazio = typeof window !== "undefined" && location.search.includes("vazio");
  const [regs] = useState<Lanc[]>(vazio ? [] : [
    l({ fornecedor: "Agropecuária Rio Verde", valor: 1600, data_vencimento: e(-6) }),
    l({ fornecedor: "Posto Mil", valor: 2358, data_vencimento: e(-3) }),
    l({ fornecedor: "Coop Leite", valor: 1200, data_vencimento: e(-1), fatura_id: 1 }),
    l({ fornecedor: "Energisa", valor: 820, data_vencimento: e(0) }),
    l({ fornecedor: "Davi Pires", valor: 3500, data_vencimento: e(1), tipo_documento: "Contrato", parcela_num: 1, parcela_total: 3 }),
    l({ fornecedor: "Vet Saúde", valor: 3200, data_vencimento: e(2) }),
    l({ fornecedor: "Nutri", valor: 1950, data_vencimento: e(3) }),
    l({ fornecedor: "Nutri", valor: 6900, data_vencimento: e(8) }),
    l({ fornecedor: "Sementes", valor: 6400, data_vencimento: e(10) }),
    l({ fornecedor: "Internet", valor: 900, data_vencimento: e(13) }),
    l({ fornecedor: "Trator", valor: 15338.63, data_vencimento: e(25) }),
    l({ fornecedor: "Trator", valor: 15338.63, data_vencimento: e(55) }),
    l({ fornecedor: "Sem venc", valor: 77, data_vencimento: null }),
    l({ tipo: "receita", fornecedor: "Laticínio", valor: 42000, data_vencimento: e(5) }),
  ]);
  const [log, setLog] = useState("");
  const f = (s: string) => () => setLog(s);
  return (
    <div className="p-6">
      <div className="mb-4"><h1 className="text-2xl font-bold">Controle Financeiro</h1></div>
      <ResumoView regs={regs} onDrill={(d: DrillContas) => setLog(JSON.stringify(d))} onAbrirLivro={(c) => setLog("livro:" + c)}
        onAbrirFaturas={f("faturas")} onAbrirCartao={f("cartao")} onBaixar={(x) => setLog("baixar:" + x.id)} onIrParaContas={f("contas")} />
      <output id="log">{log}</output>
    </div>
  );
}
