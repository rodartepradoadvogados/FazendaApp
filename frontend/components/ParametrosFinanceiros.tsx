"use client";
import { Fragment, useEffect, useState } from "react";
import { Wallet, Landmark, Tags, BookOpen, Plus, Pencil, AlertTriangle, Check, X } from "lucide-react";
import {
  fetchContasCorrentes, criarContaCorrente, atualizarContaCorrente,
  fetchCentrosCusto, criarCentroCusto, atualizarCentroCusto,
  fetchPlanoContas, criarContaGerencial, atualizarContaGerencial,
} from "@/lib/api";

const ABAS = [
  ["contas", "Conta corrente", Landmark],
  ["centros", "Centro de custo", Tags],
  ["gerenciais", "Conta gerencial", BookOpen],
] as const;

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

export default function ParametrosFinanceiros() {
  const [aba, setAba] = useState<(typeof ABAS)[number][0]>("contas");

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

      {aba === "contas" && <ContasCorrentes />}
      {aba === "centros" && <CentrosCusto />}
      {aba === "gerenciais" && <ContasGerenciais />}
    </div>
  );
}

// ---------------------------------------------------------------------------
type ContaCorrente = { id: number; banco: string; agencia: string; numero_conta: string; ativo: boolean; rotulo: string };
type FormConta = { banco: string; agencia: string; numero_conta: string; ativo: boolean };
const formContaVazio: FormConta = { banco: "", agencia: "", numero_conta: "", ativo: true };

function ContasCorrentes() {
  const [itens, setItens] = useState<ContaCorrente[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<FormConta>(formContaVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchContasCorrentes().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

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

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Landmark size={16} /> Contas correntes</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
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
            <thead><tr><th>Banco</th><th>Agência</th><th>Nº da conta</th><th></th></tr></thead>
            <tbody>
              {itens.map((c) => (
                <Fragment key={c.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{c.banco}{!c.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativa)</span>}</td>
                    <td style={{ fontSize: "0.78rem" }}>{c.agencia}</td>
                    <td style={{ fontSize: "0.78rem" }}>{c.numero_conta}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(c)}><Pencil size={13} /> Editar</button>
                    </td>
                  </tr>
                  {editando === c.id && (
                    <tr><td colSpan={4} style={{ padding: 0 }}>
                      <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", margin: "0.5rem 0" }}>
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
              {!itens.length && !editando && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma conta corrente cadastrada ainda.</td></tr>}
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
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
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
          <thead><tr><th>Nome</th><th></th></tr></thead>
          <tbody>
            {itens.map((c) => (
              <Fragment key={c.id}>
                <tr>
                  <td style={{ fontWeight: 700 }}>{c.nome}{!c.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(c)}><Pencil size={13} /> Editar</button>
                  </td>
                </tr>
                {editando === c.id && (
                  <tr><td colSpan={2} style={{ padding: 0 }}>
                    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", margin: "0.5rem 0" }}>
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
type ContaGerencial = {
  id: number; codigo: string; nome: string; ativa: boolean; tipo_fixo_variavel: string | null;
  rmca_receita_leite: boolean | null; rmca_custo_alimentacao: boolean | null;
};
type FormGerencial = {
  codigo: string; nome: string; ativa: boolean; tipo_fixo_variavel: string;
  rmca_receita_leite: boolean; rmca_custo_alimentacao: boolean;
};
const formGerencialVazio: FormGerencial = {
  codigo: "", nome: "", ativa: true, tipo_fixo_variavel: "",
  rmca_receita_leite: false, rmca_custo_alimentacao: false,
};

function ContasGerenciais() {
  const [itens, setItens] = useState<ContaGerencial[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<FormGerencial>(formGerencialVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchPlanoContas().then((c: ContaGerencial[]) => setItens([...c].sort((a, b) => a.codigo.localeCompare(b.codigo)))).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const abrirNovo = () => { setForm(formGerencialVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (c: ContaGerencial) => {
    setForm({
      codigo: c.codigo, nome: c.nome, ativa: c.ativa, tipo_fixo_variavel: c.tipo_fixo_variavel ?? "",
      rmca_receita_leite: c.rmca_receita_leite ?? false, rmca_custo_alimentacao: c.rmca_custo_alimentacao ?? false,
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.rmca_receita_leite} onChange={(e) => setForm({ ...form, rmca_receita_leite: e.target.checked })} /> Conta de receita do leite (indicador RMCA)</label>
        <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.rmca_custo_alimentacao} onChange={(e) => setForm({ ...form, rmca_custo_alimentacao: e.target.checked })} /> Conta de custo com alimentação (indicador RMCA)</label>
      </div>
    </>
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><BookOpen size={16} /> Contas gerenciais</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}><Plus size={14} /> Novo</button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        A maioria já vem do plano de contas importado (CSV) — aqui dá pra cadastrar uma conta nova sem precisar reimportar a planilha inteira.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
          {campos}
          {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
          <div className="flex items-center gap-2">
            <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}><Check size={14} /> {salvando ? "Salvando…" : "Salvar"}</button>
            <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}><X size={14} /> Cancelar</button>
          </div>
        </div>
      )}

      {itens && (
        <div className="overflow-x-auto" style={{ maxHeight: "520px" }}>
          <table className="fazenda-table">
            <thead><tr><th>Código</th><th>Nome</th><th>Tipo</th><th>RMCA</th><th></th></tr></thead>
            <tbody>
              {itens.map((c) => (
                <Fragment key={c.id}>
                  <tr>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{c.codigo}</td>
                    <td style={{ fontWeight: 700 }}>{c.nome}{!c.ativa && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativa)</span>}</td>
                    <td style={{ fontSize: "0.78rem" }}>{c.tipo_fixo_variavel || "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--dourado-light)" }}>
                      {c.rmca_receita_leite ? "Receita leite" : c.rmca_custo_alimentacao ? "Custo alimentação" : "—"}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(c)}><Pencil size={13} /> Editar</button>
                    </td>
                  </tr>
                  {editando === c.id && (
                    <tr><td colSpan={5} style={{ padding: 0 }}>
                      <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", margin: "0.5rem 0" }}>
                        {campos}
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
              {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma conta gerencial cadastrada ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
