"use client";
import { Fragment, useEffect, useState } from "react";
import { Wallet, Landmark, Tags, BookOpen, FileText, CreditCard, Plus, Pencil, AlertTriangle, Check, X, ChevronRight, ChevronDown, Stethoscope, SlidersHorizontal, ArrowLeftRight } from "lucide-react";
import {
  fetchContasCorrentes, criarContaCorrente, atualizarContaCorrente,
  criarTransferenciaContas,
  fetchCentrosCusto, criarCentroCusto, atualizarCentroCusto,
  fetchPlanoContas, criarContaGerencial, atualizarContaGerencial,
  fetchTiposDocumentoCadastro, criarTipoDocumento, atualizarTipoDocumento,
  fetchFormasPagamentoCadastro, criarFormaPagamentoCadastro, atualizarFormaPagamentoCadastro,
  fetchClassificacoesCadastro, criarClassificacao, atualizarClassificacao,
} from "@/lib/api";
import { nivelDaConta, estiloNivel, filhosDiretos } from "@/lib/contaGerencial";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { GruposParametrosCards } from "@/components/GruposParametrosCards";

const ABAS = [
  ["parametros", "Parâmetros", SlidersHorizontal],
  ["contas", "Conta corrente", Landmark],
  ["centros", "Centro de custo", Tags],
  ["gerenciais", "Conta gerencial", BookOpen],
  ["tipos-documento", "Tipo de documento", FileText],
  ["formas-pagamento", "Forma de pagamento", CreditCard],
  ["classificacoes", "Classificação", Stethoscope],
] as const;

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

export default function ParametrosFinanceiros() {
  const [aba, setAba] = useState<(typeof ABAS)[number][0]>("parametros");

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Wallet size={22} style={{ color: "var(--dourado)" }} /> Parâmetros financeiros</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Cadastro de conta corrente, centro de custo e conta gerencial — usados nos selects de Financeiro.
        </p>
      </div>

      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        {ABAS.map(([id, label, Icon]) => (
          <button key={id} onClick={() => setAba(id)}
            style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
              border: "1px solid " + (aba === id ? "var(--dourado)" : "var(--border)"),
              background: aba === id ? "rgba(94,26,46,0.4)" : "transparent",
              color: aba === id ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: aba === id ? 700 : 500 }}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {aba === "parametros" && (
        <div className="mb-2">
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "1rem" }}>
            RMCA mínimo aceitável, nome do laticínio (para a receita de leite reconhecer o RMCA) e os parâmetros de folha de pagamento/RH.
          </p>
          <GruposParametrosCards filtro={(id) => id === "financeiro" || id === "folha_rh"} />
        </div>
      )}
      {aba === "contas" && <ContasCorrentes />}
      {aba === "centros" && <CentrosCusto />}
      {aba === "gerenciais" && <ContasGerenciais />}
      {aba === "tipos-documento" && <TiposDocumento />}
      {aba === "formas-pagamento" && <FormasPagamento />}
      {aba === "classificacoes" && <Classificacoes />}
    </div>
  );
}

// ---------------------------------------------------------------------------
type ContaCorrente = { id: number; banco: string; agencia: string; numero_conta: string; ativo: boolean; rotulo: string; saldo: number };
type FormConta = { banco: string; agencia: string; numero_conta: string; ativo: boolean };
const formContaVazio: FormConta = { banco: "", agencia: "", numero_conta: "", ativo: true };

function fmtSaldo(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

type FormTransferencia = { conta_origem_id: string; conta_destino_id: string; valor: string; data: string; observacao: string };
const hoje = () => new Date().toISOString().slice(0, 10);
const formTransferenciaVazio = (): FormTransferencia => ({ conta_origem_id: "", conta_destino_id: "", valor: "", data: hoje(), observacao: "" });

function ContasCorrentes() {
  const [itens, setItens] = useState<ContaCorrente[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<FormConta>(formContaVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const [transferindo, setTransferindo] = useState(false);
  const [formTransf, setFormTransf] = useState<FormTransferencia>(formTransferenciaVazio());
  const [salvandoTransf, setSalvandoTransf] = useState(false);
  const [msgTransf, setMsgTransf] = useState<string | null>(null);

  const carregar = () => fetchContasCorrentes().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(itens ?? []);

  const abrirNovo = () => { setForm(formContaVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (c: ContaCorrente) => { setForm({ banco: c.banco, agencia: c.agencia, numero_conta: c.numero_conta, ativo: c.ativo }); setEditando(c.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.banco.trim() || !form.agencia.trim() || !form.numero_conta.trim()) { setMsg("Banco, agência e nº da conta são obrigatórios."); return; }
    setSalvando(true); setMsg(null);
    try {
      if (editando === "novo") await criarContaCorrente(form);
      else if (typeof editando === "number") await atualizarContaCorrente(editando, form);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const abrirTransferencia = () => { setFormTransf(formTransferenciaVazio()); setTransferindo(true); setMsgTransf(null); };
  const cancelarTransferencia = () => { setTransferindo(false); setMsgTransf(null); };

  const salvarTransferencia = async () => {
    const valor = parseFloat(formTransf.valor.replace(",", "."));
    if (!formTransf.conta_origem_id || !formTransf.conta_destino_id) { setMsgTransf("Selecione a conta de origem e a de destino."); return; }
    if (formTransf.conta_origem_id === formTransf.conta_destino_id) { setMsgTransf("A conta de origem e a de destino precisam ser diferentes."); return; }
    if (!valor || valor <= 0) { setMsgTransf("Informe um valor maior que zero."); return; }
    if (!formTransf.data) { setMsgTransf("Informe a data da transferência."); return; }
    setSalvandoTransf(true); setMsgTransf(null);
    try {
      await criarTransferenciaContas({
        conta_origem_id: Number(formTransf.conta_origem_id),
        conta_destino_id: Number(formTransf.conta_destino_id),
        valor,
        data: formTransf.data,
        observacao: formTransf.observacao.trim() || undefined,
      });
      setTransferindo(false);
      await carregar();
    } catch (e: any) {
      setMsgTransf(e.message || "Erro ao transferir entre contas");
    } finally {
      setSalvandoTransf(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Landmark size={16} /> Contas correntes</span>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirTransferencia} disabled={!itens || itens.length < 2}>
            <ArrowLeftRight size={14} /> Transferir entre contas
          </button>
          <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
            <Plus size={14} /> Novo
          </button>
        </div>
      </div>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {transferindo && (
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
          <p style={{ fontSize: "0.8rem", fontWeight: 700, marginBottom: "0.75rem" }}>Transferir entre contas</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div>
              <label style={labelStyle}>Conta de origem</label>
              <select style={inputStyle} value={formTransf.conta_origem_id} onChange={(e) => setFormTransf({ ...formTransf, conta_origem_id: e.target.value })}>
                <option value="">Selecione…</option>
                {(itens ?? []).map((c) => <option key={c.id} value={c.id}>{c.rotulo} ({fmtSaldo(c.saldo)})</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Conta de destino</label>
              <select style={inputStyle} value={formTransf.conta_destino_id} onChange={(e) => setFormTransf({ ...formTransf, conta_destino_id: e.target.value })}>
                <option value="">Selecione…</option>
                {(itens ?? []).map((c) => <option key={c.id} value={c.id}>{c.rotulo} ({fmtSaldo(c.saldo)})</option>)}
              </select>
            </div>
            <div><label style={labelStyle}>Valor</label>
              <input style={inputStyle} type="number" step="0.01" min="0.01" value={formTransf.valor} onChange={(e) => setFormTransf({ ...formTransf, valor: e.target.value })} /></div>
            <div><label style={labelStyle}>Data</label>
              <input style={inputStyle} type="date" value={formTransf.data} onChange={(e) => setFormTransf({ ...formTransf, data: e.target.value })} /></div>
            <div className="col-span-2 md:col-span-4"><label style={labelStyle}>Observação (opcional)</label>
              <input style={inputStyle} value={formTransf.observacao} onChange={(e) => setFormTransf({ ...formTransf, observacao: e.target.value })} /></div>
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginBottom: "0.5rem" }}>
            Movimenta o saldo das duas contas — não entra como despesa nem receita no DRE.
          </p>
          {msgTransf && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msgTransf}</p>}
          <div className="flex items-center gap-2">
            <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvarTransferencia} disabled={salvandoTransf}><Check size={14} /> {salvandoTransf ? "Transferindo…" : "Transferir"}</button>
            <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelarTransferencia}><X size={14} /> Cancelar</button>
          </div>
        </div>
      )}

      {editando === "novo" && (
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div><label style={labelStyle}>Banco</label><input style={inputStyle} value={form.banco} onChange={(e) => setForm({ ...form, banco: e.target.value })} /></div>
            <div><label style={labelStyle}>Agência</label><input style={inputStyle} value={form.agencia} onChange={(e) => setForm({ ...form, agencia: e.target.value })} /></div>
            <div><label style={labelStyle}>Nº da conta</label><input style={inputStyle} value={form.numero_conta} onChange={(e) => setForm({ ...form, numero_conta: e.target.value })} /></div>
            <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
              <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
          </div>
          {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
          <div className="flex items-center gap-2">
            <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}><Check size={14} /> {salvando ? "Salvando…" : "Salvar"}</button>
            <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}><X size={14} /> Cancelar</button>
          </div>
        </div>
      )}

      {itens && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <ThOrdenavel label="Banco" campo="banco" coluna={coluna} dir={dir} ordenar={ordenar} />
              <ThOrdenavel label="Agência" campo="agencia" coluna={coluna} dir={dir} ordenar={ordenar} />
              <ThOrdenavel label="Nº da conta" campo="numero_conta" coluna={coluna} dir={dir} ordenar={ordenar} />
              <ThOrdenavel label="Saldo" campo="saldo" coluna={coluna} dir={dir} ordenar={ordenar} />
              <th></th>
            </tr></thead>
            <tbody>
              {linhasOrdenadas.map((c) => (
                <Fragment key={c.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{c.banco}{!c.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativa)</span>}</td>
                    <td style={{ fontSize: "0.78rem" }}>{c.agencia}</td>
                    <td style={{ fontSize: "0.78rem" }}>{c.numero_conta}</td>
                    <td style={{ fontSize: "0.78rem", color: c.saldo < 0 ? "var(--red)" : "var(--text)" }}>{fmtSaldo(c.saldo)}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(c)}><Pencil size={13} /> Editar</button>
                    </td>
                  </tr>
                  {editando === c.id && (
                    <tr><td colSpan={5} style={{ padding: 0 }}>
                      <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", margin: "0.5rem 0" }}>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                          <div><label style={labelStyle}>Banco</label><input style={inputStyle} value={form.banco} onChange={(e) => setForm({ ...form, banco: e.target.value })} /></div>
                          <div><label style={labelStyle}>Agência</label><input style={inputStyle} value={form.agencia} onChange={(e) => setForm({ ...form, agencia: e.target.value })} /></div>
                          <div><label style={labelStyle}>Nº da conta</label><input style={inputStyle} value={form.numero_conta} onChange={(e) => setForm({ ...form, numero_conta: e.target.value })} /></div>
                          <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
                            <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
                        </div>
                        {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
                        <div className="flex items-center gap-2">
                          <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}><Check size={14} /> {salvando ? "Salvando…" : "Salvar"}</button>
                          <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}><X size={14} /> Cancelar</button>
                        </div>
                      </div>
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma conta corrente cadastrada ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
type CentroCusto = { id: number; nome: string; ativo: boolean };

function CentrosCusto() {
  const [itens, setItens] = useState<CentroCusto[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<{ nome: string; ativo: boolean }>({ nome: "", ativo: true });
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchCentrosCusto().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(itens ?? []);

  const abrirNovo = () => { setForm({ nome: "", ativo: true }); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (c: CentroCusto) => { setForm({ nome: c.nome, ativo: c.ativo }); setEditando(c.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    setSalvando(true); setMsg(null);
    try {
      if (editando === "novo") await criarCentroCusto(form);
      else if (typeof editando === "number") await atualizarCentroCusto(editando, form);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Tags size={16} /> Centros de custo</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}><Plus size={14} /> Novo</button>
      </div>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
            <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
            <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
              <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
          </div>
          {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
          <div className="flex items-center gap-2">
            <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}><Check size={14} /> {salvando ? "Salvando…" : "Salvar"}</button>
            <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}><X size={14} /> Cancelar</button>
          </div>
        </div>
      )}

      {itens && (
        <table className="fazenda-table">
          <thead><tr><ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} /><th></th></tr></thead>
          <tbody>
            {linhasOrdenadas.map((c) => (
              <Fragment key={c.id}>
                <tr>
                  <td style={{ fontWeight: 700 }}>{c.nome}{!c.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(c)}><Pencil size={13} /> Editar</button>
                  </td>
                </tr>
                {editando === c.id && (
                  <tr><td colSpan={2} style={{ padding: 0 }}>
                    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", margin: "0.5rem 0" }}>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
                        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
                        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
                          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
                      </div>
                      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
                      <div className="flex items-center gap-2">
                        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}><Check size={14} /> {salvando ? "Salvando…" : "Salvar"}</button>
                        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}><X size={14} /> Cancelar</button>
                      </div>
                    </div>
                  </td></tr>
                )}
              </Fragment>
            ))}
            {!itens.length && !editando && <tr><td colSpan={2} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum centro de custo cadastrado ainda.</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cadastro genérico nome+ativo (sem exclusão — soft delete via "Ativo") —
// usado para Tipo de documento e Forma de pagamento, mesmo esqueleto de
// CentrosCusto acima, parametrizado por ícone/rótulo/funções de API.
type NomeAtivo = { id: number; nome: string; ativo: boolean };
function NomeAtivoTab({ icon: Icon, titulo, semNenhum, fetchFn, criarFn, atualizarFn }: {
  icon: any; titulo: string; semNenhum: string;
  fetchFn: () => Promise<NomeAtivo[]>;
  criarFn: (dados: { nome: string; ativo: boolean }) => Promise<any>;
  atualizarFn: (id: number, dados: { nome: string; ativo: boolean }) => Promise<any>;
}) {
  const [itens, setItens] = useState<NomeAtivo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<{ nome: string; ativo: boolean }>({ nome: "", ativo: true });
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchFn().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(itens ?? []);

  const abrirNovo = () => { setForm({ nome: "", ativo: true }); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (c: NomeAtivo) => { setForm({ nome: c.nome, ativo: c.ativo }); setEditando(c.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    setSalvando(true); setMsg(null);
    try {
      if (editando === "novo") await criarFn(form);
      else if (typeof editando === "number") await atualizarFn(editando, form);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const formItem = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>
      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}><Check size={14} /> {salvando ? "Salvando…" : "Salvar"}</button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}><X size={14} /> Cancelar</button>
      </div>
    </div>
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Icon size={16} /> {titulo}</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}><Plus size={14} /> Novo</button>
      </div>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && formItem}

      {itens && (
        <table className="fazenda-table">
          <thead><tr><ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} /><th></th></tr></thead>
          <tbody>
            {linhasOrdenadas.map((c) => (
              <Fragment key={c.id}>
                <tr>
                  <td style={{ fontWeight: 700 }}>{c.nome}{!c.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(c)}><Pencil size={13} /> Editar</button>
                  </td>
                </tr>
                {editando === c.id && <tr><td colSpan={2} style={{ padding: 0 }}>{formItem}</td></tr>}
              </Fragment>
            ))}
            {!itens.length && !editando && <tr><td colSpan={2} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{semNenhum}</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}

function TiposDocumento() {
  return (
    <NomeAtivoTab icon={FileText} titulo="Tipos de documento" semNenhum="Nenhum tipo de documento cadastrado ainda."
      fetchFn={fetchTiposDocumentoCadastro} criarFn={criarTipoDocumento} atualizarFn={atualizarTipoDocumento} />
  );
}

function FormasPagamento() {
  return (
    <NomeAtivoTab icon={CreditCard} titulo="Formas de pagamento" semNenhum="Nenhuma forma de pagamento cadastrada ainda."
      fetchFn={fetchFormasPagamentoCadastro} criarFn={criarFormaPagamentoCadastro} atualizarFn={atualizarFormaPagamentoCadastro} />
  );
}

function Classificacoes() {
  return (
    <NomeAtivoTab icon={Stethoscope} titulo="Classificações" semNenhum="Nenhuma classificação cadastrada ainda — ex.: Medicamentos, Ração, Manutenção."
      fetchFn={fetchClassificacoesCadastro} criarFn={criarClassificacao} atualizarFn={atualizarClassificacao} />
  );
}

// ---------------------------------------------------------------------------
type ContaGerencial = {
  id: number; codigo: string; nome: string; ativa: boolean; tipo_fixo_variavel: string | null;
  rmca_receita_leite: boolean | null; rmca_custo_alimentacao: boolean | null; natureza: string | null;
  pede_vinculo_sanitario_reprodutivo: boolean | null;
};
type FormGerencial = {
  codigo: string; nome: string; ativa: boolean; tipo_fixo_variavel: string;
  rmca_receita_leite: boolean; rmca_custo_alimentacao: boolean; natureza: string;
  pede_vinculo_sanitario_reprodutivo: boolean;
};
const formGerencialVazio: FormGerencial = {
  codigo: "", nome: "", ativa: true, tipo_fixo_variavel: "",
  rmca_receita_leite: false, rmca_custo_alimentacao: false, natureza: "ambos",
  pede_vinculo_sanitario_reprodutivo: false,
};

function ContasGerenciais() {
  const [itens, setItens] = useState<ContaGerencial[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<FormGerencial>(formGerencialVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set());
  const toggle = (cod: string) => setExpandidos((prev) => {
    const n = new Set(prev); n.has(cod) ? n.delete(cod) : n.add(cod); return n;
  });

  const carregar = () => fetchPlanoContas().then((c: ContaGerencial[]) => setItens([...c].sort((a, b) => a.codigo.localeCompare(b.codigo, undefined, { numeric: true })))).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const abrirNovo = () => { setForm(formGerencialVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (c: ContaGerencial) => {
    setForm({
      codigo: c.codigo, nome: c.nome, ativa: c.ativa, tipo_fixo_variavel: c.tipo_fixo_variavel ?? "",
      rmca_receita_leite: c.rmca_receita_leite ?? false, rmca_custo_alimentacao: c.rmca_custo_alimentacao ?? false,
      natureza: c.natureza ?? "ambos",
      pede_vinculo_sanitario_reprodutivo: c.pede_vinculo_sanitario_reprodutivo ?? false,
    });
    setEditando(c.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.codigo.trim() || !form.nome.trim()) { setMsg("Código e nome são obrigatórios."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = {
        codigo: form.codigo.trim(), nome: form.nome.trim(), ativa: form.ativa, tipo_fixo_variavel: form.tipo_fixo_variavel || undefined,
        rmca_receita_leite: form.rmca_receita_leite, rmca_custo_alimentacao: form.rmca_custo_alimentacao,
        natureza: form.natureza || undefined,
        pede_vinculo_sanitario_reprodutivo: form.pede_vinculo_sanitario_reprodutivo,
      };
      if (editando === "novo") await criarContaGerencial(dados);
      else if (typeof editando === "number") await atualizarContaGerencial(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const campos = (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyle}>Código</label><input style={inputStyle} value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} placeholder="ex.: 3.09.09.09" /></div>
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div><label style={labelStyle}>Tipo</label>
          <select style={inputStyle} value={form.tipo_fixo_variavel} onChange={(e) => setForm({ ...form, tipo_fixo_variavel: e.target.value })}>
            <option value="">—</option><option value="Fixa">Fixa</option><option value="Variável">Variável</option>
          </select></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativa} onChange={(e) => setForm({ ...form, ativa: e.target.checked })} /> Ativa</label></div>
      </div>
      <div className="mb-3">
        <label style={labelStyle}>Natureza do lançamento aceito nesta conta</label>
        <div className="flex items-center gap-4 mt-1">
          {(["servico", "produto", "ambos"] as const).map((n) => (
            <label key={n} className="flex items-center gap-2" style={{ fontSize: "0.78rem", cursor: "pointer" }}>
              <input type="radio" checked={form.natureza === n} onChange={() => setForm({ ...form, natureza: n })} />
              {n === "servico" ? "Serviço" : n === "produto" ? "Produto" : "Ambos"}
            </label>
          ))}
        </div>
        <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
          Quem decide se o item do lançamento é serviço ou produto é a escolha do próprio usuário na tela de
          Financeiro &gt; Contas a pagar/a receber; a natureza marcada aqui só restringe, dentro dessa escolha, quais
          contas gerenciais ficam disponíveis para seleção (uma conta "Serviço" some da lista quando o usuário
          escolhe "Produto", e vice-versa; "Ambos" sempre aparece nas duas).
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.rmca_receita_leite} onChange={(e) => setForm({ ...form, rmca_receita_leite: e.target.checked })} /> Conta de receita do leite (indicador RMCA)</label>
        <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.rmca_custo_alimentacao} onChange={(e) => setForm({ ...form, rmca_custo_alimentacao: e.target.checked })} /> Conta de custo com alimentação (indicador RMCA)</label>
      </div>
      <div className="mb-1">
        <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.pede_vinculo_sanitario_reprodutivo}
            onChange={(e) => setForm({ ...form, pede_vinculo_sanitario_reprodutivo: e.target.checked })} />
          Pedir vínculo com aplicação de vacina/exame/visita reprodutiva ao lançar uma despesa nesta conta
        </label>
        <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
          Ex.: marque em "Veterinário/zootecnista" — ao salvar uma despesa nessa conta, o sistema oferece vincular
          o pagamento a um serviço reprodutivo, vacina ou exame já lançado (ver Financeiro &gt; Contas a pagar).
        </p>
      </div>
    </>
  );

  const badgeRmca: React.CSSProperties = {
    fontSize: "0.62rem", padding: "0.05rem 0.4rem", borderRadius: "999px", flexShrink: 0,
    border: "1px solid var(--dourado)", color: "var(--dourado-light)", background: "rgba(184,134,11,0.12)",
  };
  const formEdicao = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", margin: "0.25rem 0 0.5rem" }}>
      {campos}
      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}><Check size={14} /> {salvando ? "Salvando…" : "Salvar"}</button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}><X size={14} /> Cancelar</button>
      </div>
    </div>
  );

  function renderNo(c: ContaGerencial): React.ReactNode {
    const filhos = (itens ? (filhosDiretos(c.codigo, itens as any) as unknown as ContaGerencial[]) : []);
    const temFilhos = filhos.length > 0;
    const aberto = expandidos.has(c.codigo);
    const nivel = nivelDaConta(c.codigo);
    return (
      <Fragment key={c.id ?? c.codigo}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.35rem 0.4rem",
          paddingLeft: `${0.4 + (nivel - 1) * 1.1}rem`, borderBottom: "1px solid var(--border)" }}>
          <button type="button" onClick={() => (temFilhos ? toggle(c.codigo) : abrirEdicao(c))}
            className="row-clickable" title={temFilhos ? (aberto ? "Clique para recolher" : "Clique para expandir") : "Clique para editar"}
            style={{ display: "flex", alignItems: "center", gap: "0.45rem", flex: 1, minWidth: 0, background: "none", border: "none", cursor: "pointer", textAlign: "left", padding: "0.1rem 0" }}>
            <span style={{ width: 14, display: "inline-flex", flexShrink: 0, color: "var(--accent-icon)" }}>
              {temFilhos && (aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
            </span>
            <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", flexShrink: 0 }}>{c.codigo}</span>
            <span style={{ ...estiloNivel(nivel), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.nome}</span>
            {!c.ativa && <span style={{ color: "var(--text-muted)", fontSize: "0.7rem", flexShrink: 0 }}>(inativa)</span>}
            {c.natureza && c.natureza !== "ambos" && (
              <span style={{ fontSize: "0.62rem", padding: "0.05rem 0.4rem", borderRadius: "999px", flexShrink: 0, border: "1px solid var(--border)", color: "var(--text-muted)" }}>
                {c.natureza === "servico" ? "Serviço" : "Produto"}
              </span>
            )}
            {c.rmca_receita_leite && <span style={badgeRmca}>RMCA · receita leite</span>}
            {c.rmca_custo_alimentacao && <span style={badgeRmca}>RMCA · alimentação</span>}
            {c.pede_vinculo_sanitario_reprodutivo && <span style={badgeRmca}>vínculo sanitário/reprodutivo</span>}
          </button>
          <button className="btn-ghost" style={{ fontSize: "0.7rem", display: "flex", alignItems: "center", gap: "0.3rem", flexShrink: 0 }} onClick={() => abrirEdicao(c)}><Pencil size={12} /> Editar</button>
        </div>
        {editando === c.id && formEdicao}
        {temFilhos && aberto && filhos.map((f) => renderNo(f))}
      </Fragment>
    );
  }

  const raizes = itens ? (filhosDiretos("", itens as any) as unknown as ContaGerencial[]) : [];

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><BookOpen size={16} /> Contas gerenciais</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}><Plus size={14} /> Novo</button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Comece por <strong>Receita (2)</strong> ou <strong>Despesa (3)</strong> e vá clicando para abrir os galhos
        (2.01, depois 2.01.01…). Todas já vêm ativas; clique em “Editar” em qualquer conta para ajustar nome,
        tipo, ativação ou marcação de RMCA. Para cadastrar uma conta nova sem reimportar o CSV, use “Novo”.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
          {campos}
          {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
          <div className="flex items-center gap-2">
            <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}><Check size={14} /> {salvando ? "Salvando…" : "Salvar"}</button>
            <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}><X size={14} /> Cancelar</button>
          </div>
        </div>
      )}

      {itens && (
        <div style={{ maxHeight: "560px", overflowY: "auto", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
          {raizes.length ? raizes.map((c) => renderNo(c)) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", padding: "0.8rem" }}>Nenhuma conta gerencial cadastrada ainda.</p>
          )}
        </div>
      )}
    </div>
  );
}
