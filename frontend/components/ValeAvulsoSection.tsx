"use client";
// Vale (adiantamento) para Empreitada/Contrato/Diária — mesma ideia do Vale
// de funcionário (FolhaPagamentoView.tsx), mas sem competência/folha mensal
// para descontar: o backend abate automaticamente da(s) próxima(s) parcela(s)
// /etapa(s) pendente(s) (Empreitada/Contrato) ou do saldo devedor acumulado
// (Diária) — ver `_aplicar_vale_avulso` em cadastro.py.
import { useEffect, useState } from "react";
import { criarValeAvulso, fetchContasCorrentes, type ContaCorrenteCadastro } from "@/lib/api";
import { lbl, inputSm } from "@/components/estiloCampoAvulso";

const FORMAS_VALE_AVULSO = [
  { id: "dinheiro", label: "Dinheiro" },
  { id: "pix", label: "Pix" },
  { id: "transferencia", label: "Transferência" },
  { id: "desconto_proximo_pagamento", label: "Descontar do próximo pagamento" },
];

// Mesma regra do backend (`_validar_conta_vale_avulso`): a conta bancária só
// faz sentido quando o dinheiro sai AGORA — "descontar do próximo pagamento"
// não movimenta banco nenhum na hora do vale, então nem pede conta nem gera
// lançamento no extrato.
const contaObrigatoria = (forma: string) => forma !== "desconto_proximo_pagamento";

export type OrigemVale = { id: number; label: string };

export default function ValeAvulsoSection({
  origemTipo, origens, onLancado,
}: { origemTipo: "empreitada" | "contrato" | "diaria"; origens: OrigemVale[]; onLancado: () => void }) {
  const [origemId, setOrigemId] = useState("");
  const [valor, setValor] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("dinheiro");
  const [contaCorrenteId, setContaCorrenteId] = useState("");
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);
  const [contasCorrentes, setContasCorrentes] = useState<ContaCorrenteCadastro[]>([]);
  useEffect(() => { fetchContasCorrentes().then(setContasCorrentes).catch(() => {}); }, []);

  async function salvar() {
    setMsg(null);
    if (!origemId) { setMsg({ tipo: "erro", texto: "Selecione a quem se refere o vale." }); return; }
    if (!valor || parseFloat(valor) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor do vale." }); return; }
    if (contaObrigatoria(formaPagamento) && !contaCorrenteId) {
      setMsg({ tipo: "erro", texto: "Selecione a conta bancária de onde sai o vale." }); return;
    }
    setSalvando(true);
    try {
      await criarValeAvulso({
        origem_tipo: origemTipo, origem_id: Number(origemId), valor: parseFloat(valor),
        forma_pagamento: formaPagamento, data_pagamento: dataPagamento, observacao: observacao || undefined,
        conta_corrente_id: contaObrigatoria(formaPagamento) && contaCorrenteId ? Number(contaCorrenteId) : undefined,
      });
      setMsg({ tipo: "sucesso", texto: "Vale lançado — já abatido do que ainda falta pagar." });
      setOrigemId(""); setValor(""); setObservacao("");
      onLancado();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar vale" });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
      <div style={{ gridColumn: "span 2" }}>
        <label style={lbl}>Referente a</label>
        <select style={inputSm} value={origemId} onChange={(e) => setOrigemId(e.target.value)}>
          <option value="">Selecione…</option>
          {origens.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
      </div>
      <div>
        <label style={lbl}>Valor do vale (R$)</label>
        <input type="number" step="0.01" style={inputSm} value={valor} onChange={(e) => setValor(e.target.value)} />
      </div>
      <div>
        <label style={lbl}>Forma de pagamento</label>
        <select style={inputSm} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)}>
          {FORMAS_VALE_AVULSO.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
        </select>
      </div>
      {contaObrigatoria(formaPagamento) && (
        <div>
          <label style={lbl}>Conta bancária</label>
          <select style={inputSm} value={contaCorrenteId} onChange={(e) => setContaCorrenteId(e.target.value)}>
            <option value="">Selecione…</option>
            {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
          </select>
        </div>
      )}
      <div>
        <label style={lbl}>Data do pagamento</label>
        <input type="date" style={inputSm} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} />
      </div>
      <div style={{ gridColumn: "1 / -1" }}>
        <label style={lbl}>Observação</label>
        <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} />
      </div>
      {msg && <p style={{ gridColumn: "1 / -1", color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: 0 }}>{msg.texto}</p>}
      <div>
        <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar vale"}
        </button>
      </div>
    </div>
  );
}
