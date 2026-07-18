"use client";
import { useEffect, useMemo, useState } from "react";
import { Plus, Trash2, CheckCircle2 } from "lucide-react";
import { fetchPessoas, fetchEmpreitadas, criarEmpreitada, concluirEtapaEmpreitada, formatBRL } from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { ParcelamentoEditor, type Parcela } from "@/components/ParcelamentoEditor";

type Pessoa = { id: number; nome: string; tipos: string[] };
type Etapa = {
  id: number; nome: string; valor: number; ordem: number; concluida: boolean;
  data_conclusao: string | null; numero_lancamento_gerado: string | null; status_pagamento: string;
};
type ParcelaEmpreitada = { id: number; data_vencimento: string; valor: number; status: string; numero_lancamento_gerado: string | null };
type Empreitada = {
  id: number; pessoa_id: number; pessoa_nome: string; descricao: string; valor_total: number;
  tipo_pagamento: string; status: string; observacao: string | null;
  parcelas: ParcelaEmpreitada[]; etapas: Etapa[];
};

const FREQUENCIAS = [
  { id: "mensal", label: "Mensal" },
  { id: "semanal", label: "Semanal" },
  { id: "quinzenal", label: "Quinzenal" },
  { id: "inicio_empreita", label: "No início da empreita" },
  { id: "fim_empreita", label: "Ao final da empreita" },
  { id: "por_etapa", label: "Ao final de cada etapa" },
];
// Forma de pagamento com data única (não recorrente) — pede só 1 data e
// lança 1 parcela com o valor total, que cai na Agenda/Contas a Pagar
// igual às demais (ver ParcelamentoEditor para mensal/semanal/quinzenal).
const FORMAS_DATA_UNICA = ["inicio_empreita", "fim_empreita"];

const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };
const inputSm: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", width: "100%",
};

type EtapaForm = { nome: string; valor: string };

export default function EmpreitadaView() {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [itens, setItens] = useState<Empreitada[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [descricao, setDescricao] = useState("");
  const [valorTotal, setValorTotal] = useState("");
  const [tipoPagamento, setTipoPagamento] = useState("mensal");
  const [dataPrimeiroPagamento, setDataPrimeiroPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [parcelas, setParcelas] = useState<Parcela[]>([]);
  const [etapasForm, setEtapasForm] = useState<EtapaForm[]>([{ nome: "", valor: "" }]);
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const empreiteiros = useMemo(() => pessoas.filter((p) => p.tipos.includes("Empreiteiro")), [pessoas]);

  const carregar = () => fetchEmpreitadas().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchPessoas().then(setPessoas).catch(() => {}); }, []);

  const dividirEtapasProporcionalmente = () => {
    const n = etapasForm.length || 1;
    const total = parseFloat(valorTotal) || 0;
    const base = Math.floor((total / n) * 100) / 100;
    const resto = Math.round((total - base * n) * 100) / 100;
    setEtapasForm(etapasForm.map((e, i) => ({ ...e, valor: (i === n - 1 ? base + resto : base).toFixed(2) })));
  };

  async function salvar() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione o empreiteiro." }); return; }
    if (!descricao.trim()) { setMsg({ tipo: "erro", texto: "Informe a descrição da empreita." }); return; }
    if (!valorTotal || parseFloat(valorTotal) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor total." }); return; }
    if (tipoPagamento !== "por_etapa" && !FORMAS_DATA_UNICA.includes(tipoPagamento) && !parcelas.length) { setMsg({ tipo: "erro", texto: "Gere as parcelas do pagamento." }); return; }
    if (FORMAS_DATA_UNICA.includes(tipoPagamento) && !dataPrimeiroPagamento) { setMsg({ tipo: "erro", texto: "Informe a data do pagamento." }); return; }
    if (tipoPagamento === "por_etapa" && !etapasForm.some((e) => e.nome.trim() && e.valor)) {
      setMsg({ tipo: "erro", texto: "Informe ao menos uma etapa com nome e valor." }); return;
    }
    setSalvando(true);
    try {
      await criarEmpreitada({
        pessoa_id: Number(pessoaId), descricao: descricao.trim(), valor_total: parseFloat(valorTotal),
        tipo_pagamento: tipoPagamento, observacao: observacao || undefined,
        parcelas: tipoPagamento === "por_etapa" ? undefined
          : FORMAS_DATA_UNICA.includes(tipoPagamento) ? [{ data_vencimento: dataPrimeiroPagamento, valor: parseFloat(valorTotal) || 0 }]
          : parcelas.map((p) => ({ data_vencimento: p.data_vencimento, valor: parseFloat(p.valor) || 0 })),
        etapas: tipoPagamento === "por_etapa"
          ? etapasForm.filter((e) => e.nome.trim() && e.valor).map((e) => ({ nome: e.nome.trim(), valor: parseFloat(e.valor) || 0 }))
          : undefined,
      });
      setMsg({ tipo: "sucesso", texto: "Empreita lançada." });
      setPessoaId(""); setDescricao(""); setValorTotal(""); setObservacao(""); setParcelas([]); setEtapasForm([{ nome: "", valor: "" }]);
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar empreita" });
    } finally {
      setSalvando(false);
    }
  }

  async function concluirEtapa(empreitadaId: number, etapaId: number) {
    try {
      await concluirEtapaEmpreitada(empreitadaId, etapaId);
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao concluir etapa" });
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      <SecaoRecolhivel titulo="Nova empreita" icon={Plus} defaultAberta={false} descricao="Lançamento global (por frequência) ou por etapa">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label style={lbl}>Empreiteiro</label>
            <select style={inputSm} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Selecione…</option>
              {empreiteiros.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
          <div style={{ gridColumn: "span 2" }}>
            <label style={lbl}>Descrição da empreita</label>
            <input style={inputSm} value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="Ex.: Roçagem geral, construção de cerca…" />
          </div>
          <div>
            <label style={lbl}>Valor total (R$)</label>
            <input type="number" step="0.01" style={inputSm} value={valorTotal} onChange={(e) => setValorTotal(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Forma de pagamento</label>
            <select style={inputSm} value={tipoPagamento} onChange={(e) => { setTipoPagamento(e.target.value); setParcelas([]); }}>
              {FREQUENCIAS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
          </div>
          {tipoPagamento !== "por_etapa" && (
            <div>
              <label style={lbl}>{FORMAS_DATA_UNICA.includes(tipoPagamento) ? "Data do pagamento" : "Data do primeiro pagamento"}</label>
              <input type="date" style={inputSm} value={dataPrimeiroPagamento} onChange={(e) => setDataPrimeiroPagamento(e.target.value)} />
            </div>
          )}
        </div>

        {FORMAS_DATA_UNICA.includes(tipoPagamento) ? (
          <p className="mb-3" style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>
            Será lançada 1 conta no valor total ({formatBRL(parseFloat(valorTotal) || 0)}), com vencimento na data acima — cai na Agenda e em Contas a Pagar.
          </p>
        ) : tipoPagamento !== "por_etapa" ? (
          <div className="mb-3">
            <ParcelamentoEditor
              valorTotal={parseFloat(valorTotal) || 0} frequencia={tipoPagamento} primeiraData={dataPrimeiroPagamento}
              parcelas={parcelas} setParcelas={setParcelas}
            />
          </div>
        ) : (
          <div className="mb-3">
            <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginBottom: "0.5rem" }}>
              O pagamento de cada etapa será lançado na Agenda e em Contas a Pagar para análise sempre no dia 1º do mês
              seguinte à conclusão da etapa. Divida o valor total proporcionalmente entre as etapas ou informe um valor
              específico para cada uma — tudo editável.
            </p>
            <div className="overflow-x-auto">
              <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
                <thead><tr><th>Etapa</th><th>Valor (R$)</th><th></th></tr></thead>
                <tbody>
                  {etapasForm.map((et, i) => (
                    <tr key={i}>
                      <td><input style={inputSm} value={et.nome} onChange={(e) => setEtapasForm(etapasForm.map((x, idx) => idx === i ? { ...x, nome: e.target.value } : x))} placeholder={`Etapa ${i + 1}`} /></td>
                      <td><input type="number" step="0.01" style={{ ...inputSm, width: "120px" }} value={et.valor} onChange={(e) => setEtapasForm(etapasForm.map((x, idx) => idx === i ? { ...x, valor: e.target.value } : x))} /></td>
                      <td><button type="button" className="btn-ghost" onClick={() => setEtapasForm(etapasForm.filter((_, idx) => idx !== i))}><Trash2 size={13} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center gap-2" style={{ marginTop: "0.4rem" }}>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setEtapasForm([...etapasForm, { nome: "", valor: "" }])}>
                <Plus size={13} /> Adicionar etapa
              </button>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={dividirEtapasProporcionalmente} disabled={!valorTotal}>
                Dividir proporcionalmente
              </button>
            </div>
          </div>
        )}

        <div><label style={lbl}>Observação</label>
          <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar empreita"}
        </button>
      </SecaoRecolhivel>

      <div className="card mt-4">
        <div className="card-header mb-3">Empreitas lançadas</div>
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma empreita lançada ainda.</p>}
        {itens && itens.map((e) => (
          <div key={e.id} style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.8rem", marginBottom: "0.8rem" }}>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <strong>{e.pessoa_nome}</strong> — {e.descricao}
                <span style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginLeft: "0.5rem" }}>
                  ({e.status === "concluida" ? "concluída" : "em andamento"})
                </span>
              </div>
              <div style={{ fontWeight: 700 }}>{formatBRL(e.valor_total)}</div>
            </div>
            {e.parcelas.length > 0 && (
              <table className="fazenda-table" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
                <thead><tr><th>Vencimento</th><th>Valor</th><th>Status</th></tr></thead>
                <tbody>
                  {e.parcelas.map((p) => (
                    <tr key={p.id}><td>{p.data_vencimento}</td><td>{formatBRL(p.valor)}</td><td>{p.status}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
            {e.etapas.length > 0 && (
              <table className="fazenda-table" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
                <thead><tr><th>Etapa</th><th>Valor</th><th>Situação</th><th></th></tr></thead>
                <tbody>
                  {e.etapas.map((et) => (
                    <tr key={et.id}>
                      <td>{et.nome}</td>
                      <td>{formatBRL(et.valor)}</td>
                      <td>{et.concluida ? `concluída em ${et.data_conclusao} (${et.status_pagamento})` : "pendente"}</td>
                      <td>
                        {!et.concluida && (
                          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => concluirEtapa(e.id, et.id)}>
                            <CheckCircle2 size={13} /> Concluir
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
