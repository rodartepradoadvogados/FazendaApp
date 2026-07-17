"use client";
import { useEffect, useState } from "react";
import { Plus, DollarSign } from "lucide-react";
import { fetchPessoas, fetchDiarias, criarDiaria, registrarPagamentoDiaria, formatBRL } from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { Modal } from "@/components/Modal";

type Pessoa = { id: number; nome: string; tipos: string[] };
type Pagamento = { id: number; data_pagamento: string; valor: number; observacao: string | null };
type Diaria = {
  id: number; pessoa_id: number; pessoa_nome: string; valor_diaria: number; data_inicio: string; status: string;
  numero_diarias: number; total_ate_hoje: number; valor_pago: number; saldo_devedor: number; pagamentos: Pagamento[];
};

const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };
const inputSm: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", width: "100%",
};

export default function DiariaView() {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [itens, setItens] = useState<Diaria[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [valorDiaria, setValorDiaria] = useState("");
  const [dataInicio, setDataInicio] = useState(() => new Date().toISOString().slice(0, 10));
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const [pagandoId, setPagandoId] = useState<number | null>(null);
  const [valorPagamento, setValorPagamento] = useState("");
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [pagoErro, setPagoErro] = useState<string | null>(null);

  const carregar = () => fetchDiarias().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchPessoas().then(setPessoas).catch(() => {}); }, []);

  async function salvar() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione a diarista." }); return; }
    if (!valorDiaria || parseFloat(valorDiaria) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor da diária." }); return; }
    if (!dataInicio) { setMsg({ tipo: "erro", texto: "Informe a data de início." }); return; }
    setSalvando(true);
    try {
      await criarDiaria({ pessoa_id: Number(pessoaId), valor_diaria: parseFloat(valorDiaria), data_inicio: dataInicio, observacao: observacao || undefined });
      setMsg({ tipo: "sucesso", texto: "Diarista lançada." });
      setPessoaId(""); setValorDiaria(""); setObservacao("");
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar diária" });
    } finally {
      setSalvando(false);
    }
  }

  async function registrarPagamento(diariaId: number) {
    setPagoErro(null);
    if (!valorPagamento || parseFloat(valorPagamento) <= 0) { setPagoErro("Informe o valor do pagamento."); return; }
    try {
      await registrarPagamentoDiaria(diariaId, { data_pagamento: dataPagamento, valor: parseFloat(valorPagamento) });
      setPagandoId(null); setValorPagamento("");
      carregar();
    } catch (e: any) {
      setPagoErro(e.message || "Erro ao registrar pagamento");
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      <SecaoRecolhivel titulo="Nova diarista" icon={Plus} defaultAberta={false} descricao="Valor da diária e data de início da contagem">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label style={lbl}>Diarista</label>
            <select style={inputSm} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Selecione…</option>
              {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Valor da diária (R$)</label>
            <input type="number" step="0.01" style={inputSm} value={valorDiaria} onChange={(e) => setValorDiaria(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Data de início</label>
            <input type="date" style={inputSm} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} />
          </div>
        </div>
        <div><label style={lbl}>Observação</label>
          <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar diarista"}
        </button>
      </SecaoRecolhivel>

      <div className="card mt-4">
        <div className="card-header mb-3">Controle de diárias</div>
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma diarista lançada ainda.</p>}
        {itens && itens.length > 0 && (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <th>Nome</th><th>Início</th><th>Nº diárias</th><th>Valor diária</th>
                  <th>Total até hoje</th><th>Pago</th><th>Saldo devedor</th><th></th>
                </tr>
              </thead>
              <tbody>
                {itens.map((d) => (
                  <tr key={d.id}>
                    <td style={{ fontWeight: 700 }}>{d.pessoa_nome}</td>
                    <td>{d.data_inicio}</td>
                    <td>{d.numero_diarias}</td>
                    <td>{formatBRL(d.valor_diaria)}</td>
                    <td>{formatBRL(d.total_ate_hoje)}</td>
                    <td>{formatBRL(d.valor_pago)}</td>
                    <td style={{ fontWeight: 700, color: d.saldo_devedor > 0 ? "var(--amber)" : "var(--green-light)" }}>{formatBRL(d.saldo_devedor)}</td>
                    <td>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                        onClick={() => { setPagandoId(d.id); setValorPagamento(d.saldo_devedor > 0 ? d.saldo_devedor.toFixed(2) : ""); setPagoErro(null); }}>
                        <DollarSign size={13} /> Pagar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {pagandoId !== null && (
        <Modal title="Registrar pagamento de diária" onClose={() => setPagandoId(null)} width="380px">
          <div>
            <label style={lbl}>Data do pagamento</label>
            <input type="date" style={inputSm} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} />
          </div>
          <div style={{ marginTop: "0.6rem" }}>
            <label style={lbl}>Valor (R$)</label>
            <input type="number" step="0.01" style={inputSm} value={valorPagamento} onChange={(e) => setValorPagamento(e.target.value)} />
          </div>
          {pagoErro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{pagoErro}</p>}
          <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "1rem" }} onClick={() => registrarPagamento(pagandoId)}>
            Confirmar pagamento
          </button>
        </Modal>
      )}
    </div>
  );
}
