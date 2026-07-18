"use client";
import { useEffect, useState } from "react";
import { Plus, XCircle } from "lucide-react";
import { fetchPessoas, fetchContratos, criarContrato, encerrarContrato, formatBRL } from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { ParcelamentoEditor, type Parcela } from "@/components/ParcelamentoEditor";
import ValeAvulsoSection from "@/components/ValeAvulsoSection";

type Pessoa = { id: number; nome: string; tipos: string[] };
type ParcelaContrato = { id: number; data_vencimento: string; valor: number; status: string; numero_lancamento_gerado: string | null };
type ValeAvulso = { id: number; valor: number; forma_pagamento: string; data_pagamento: string; observacao: string | null };
type Contrato = {
  id: number; pessoa_id: number; pessoa_nome: string; descricao: string; valor_total: number;
  forma_pagamento: string | null; status: string; observacao: string | null;
  origem_lembrete_agenda_id: number | null; parcelas: ParcelaContrato[]; vales: ValeAvulso[];
};

const FORMAS = [
  { id: "", label: "Sem frequência definida (lembrete mensal na Agenda)" },
  { id: "mensal", label: "Mensal" },
  { id: "quinzenal", label: "Quinzenal" },
  { id: "semanal", label: "Semanal" },
];

const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };
const inputSm: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", width: "100%",
};

export default function ContratoView() {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [itens, setItens] = useState<Contrato[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [descricao, setDescricao] = useState("");
  const [valorTotal, setValorTotal] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("");
  const [dataPrimeiroPagamento, setDataPrimeiroPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [parcelas, setParcelas] = useState<Parcela[]>([]);
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const carregar = () => fetchContratos().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchPessoas().then(setPessoas).catch(() => {}); }, []);

  async function salvar() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione a pessoa." }); return; }
    if (!descricao.trim()) { setMsg({ tipo: "erro", texto: "Informe a descrição do contrato." }); return; }
    if (!valorTotal || parseFloat(valorTotal) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor total." }); return; }
    if (formaPagamento && !parcelas.length) { setMsg({ tipo: "erro", texto: "Gere as parcelas do pagamento." }); return; }
    setSalvando(true);
    try {
      await criarContrato({
        pessoa_id: Number(pessoaId), descricao: descricao.trim(), valor_total: parseFloat(valorTotal),
        forma_pagamento: formaPagamento || null, observacao: observacao || undefined,
        parcelas: formaPagamento ? parcelas.map((p) => ({ data_vencimento: p.data_vencimento, valor: parseFloat(p.valor) || 0 })) : undefined,
      });
      setMsg({
        tipo: "sucesso",
        texto: formaPagamento
          ? "Contrato lançado."
          : "Contrato lançado — todo dia 1º do mês haverá um alerta na Agenda para pagar ou definir uma nova data.",
      });
      setPessoaId(""); setDescricao(""); setValorTotal(""); setFormaPagamento(""); setObservacao(""); setParcelas([]);
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar contrato" });
    } finally {
      setSalvando(false);
    }
  }

  async function encerrar(id: number) {
    try {
      await encerrarContrato(id);
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao encerrar contrato" });
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      <SecaoRecolhivel titulo="Novo contrato" icon={Plus} defaultAberta={false} descricao="Valor total pago por frequência ou sem data fixa">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label style={lbl}>Pessoa</label>
            <select style={inputSm} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Selecione…</option>
              {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
          <div style={{ gridColumn: "span 2" }}>
            <label style={lbl}>Descrição do contrato</label>
            <input style={inputSm} value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="Ex.: Consultoria, parceria de arrendamento…" />
          </div>
          <div>
            <label style={lbl}>Valor total (R$)</label>
            <input type="number" step="0.01" style={inputSm} value={valorTotal} onChange={(e) => setValorTotal(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Forma de pagamento</label>
            <select style={inputSm} value={formaPagamento} onChange={(e) => { setFormaPagamento(e.target.value); setParcelas([]); }}>
              {FORMAS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
          </div>
          {formaPagamento && (
            <div>
              <label style={lbl}>Data do primeiro pagamento</label>
              <input type="date" style={inputSm} value={dataPrimeiroPagamento} onChange={(e) => setDataPrimeiroPagamento(e.target.value)} />
            </div>
          )}
        </div>

        {formaPagamento ? (
          <div className="mb-3">
            <ParcelamentoEditor
              valorTotal={parseFloat(valorTotal) || 0} frequencia={formaPagamento} primeiraData={dataPrimeiroPagamento}
              parcelas={parcelas} setParcelas={setParcelas}
            />
          </div>
        ) : (
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginBottom: "0.8rem" }}>
            Sem frequência definida: todo dia 1º do mês haverá um alerta na Agenda para pagar este contrato ou definir uma nova data.
          </p>
        )}

        <div><label style={lbl}>Observação</label>
          <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar contrato"}
        </button>
      </SecaoRecolhivel>

      <SecaoRecolhivel titulo="Vale de contrato" icon={Plus} defaultAberta={false} descricao="Adiantamento abatido da próxima parcela pendente">
        <ValeAvulsoSection
          origemTipo="contrato"
          origens={(itens ?? []).filter((c) => c.status !== "encerrado").map((c) => ({ id: c.id, label: `${c.pessoa_nome} — ${c.descricao}` }))}
          onLancado={carregar}
        />
      </SecaoRecolhivel>

      <div className="card mt-4">
        <div className="card-header mb-3">Contratos lançados</div>
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum contrato lançado ainda.</p>}
        {itens && itens.map((c) => (
          <div key={c.id} style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.8rem", marginBottom: "0.8rem" }}>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <strong>{c.pessoa_nome}</strong> — {c.descricao}
                <span style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginLeft: "0.5rem" }}>({c.status})</span>
              </div>
              <div className="flex items-center gap-2">
                <span style={{ fontWeight: 700 }}>{formatBRL(c.valor_total)}</span>
                {c.status === "ativo" && (
                  <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => encerrar(c.id)}>
                    <XCircle size={13} /> Encerrar
                  </button>
                )}
              </div>
            </div>
            {c.parcelas.length > 0 ? (
              <table className="fazenda-table" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
                <thead><tr><th>Vencimento</th><th>Valor</th><th>Status</th></tr></thead>
                <tbody>
                  {c.parcelas.map((p) => (
                    <tr key={p.id}><td>{p.data_vencimento}</td><td>{formatBRL(p.valor)}</td><td>{p.status}</td></tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.3rem" }}>
                Sem frequência definida — alerta mensal na Agenda todo dia 1º.
              </p>
            )}
            {c.vales.length > 0 && (
              <table className="fazenda-table" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
                <thead><tr><th>Vale</th><th>Data</th><th>Forma</th></tr></thead>
                <tbody>
                  {c.vales.map((v) => (
                    <tr key={v.id}><td>{formatBRL(v.valor)}</td><td>{v.data_pagamento}</td><td>{v.forma_pagamento}</td></tr>
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
