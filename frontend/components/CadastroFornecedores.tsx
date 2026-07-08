"use client";
import { Fragment, useEffect, useState } from "react";
import { Truck, Plus, Pencil, AlertTriangle, Check, X } from "lucide-react";
import { fetchFornecedores, criarFornecedor, atualizarFornecedor } from "@/lib/api";

type Fornecedor = {
  id: number; nome: string; tipo: string; cnpj_cpf: string | null; telefone: string | null;
  email: string | null; observacoes: string | null; ativo: boolean;
};
type Form = { nome: string; tipo: string; cnpj_cpf: string; telefone: string; email: string; observacoes: string; ativo: boolean };
const formVazio: Form = { nome: "", tipo: "fornecedor", cnpj_cpf: "", telefone: "", email: "", observacoes: "", ativo: true };

const TIPOS = [
  { v: "fornecedor", l: "Fornecedor" },
  { v: "fabricante", l: "Fabricante" },
  { v: "cliente", l: "Cliente" },
];

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

function paraPayload(f: Form) {
  const s = (v: string) => (v.trim() === "" ? undefined : v.trim());
  return { nome: f.nome.trim(), tipo: f.tipo, cnpj_cpf: s(f.cnpj_cpf), telefone: s(f.telefone), email: s(f.email), observacoes: s(f.observacoes), ativo: f.ativo };
}

export default function CadastroFornecedores() {
  const [itens, setItens] = useState<Fornecedor[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchFornecedores().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (f: Fornecedor) => {
    setForm({ nome: f.nome, tipo: f.tipo, cnpj_cpf: f.cnpj_cpf ?? "", telefone: f.telefone ?? "", email: f.email ?? "", observacoes: f.observacoes ?? "", ativo: f.ativo });
    setEditando(f.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = paraPayload(form);
      if (editando === "novo") await criarFornecedor(dados);
      else if (typeof editando === "number") await atualizarFornecedor(editando, dados);
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
        <span className="flex items-center gap-2"><Truck size={16} /> Fornecedores, fabricantes e clientes</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />}

      {itens && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Nome</th><th>Tipo</th><th>CNPJ/CPF</th><th>Telefone</th><th>Email</th><th></th></tr></thead>
            <tbody>
              {itens.map((f) => (
                <Fragment key={f.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{f.nome}{!f.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ textTransform: "capitalize" }}>{f.tipo}</td>
                    <td style={{ fontSize: "0.78rem" }}>{f.cnpj_cpf || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{f.telefone || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{f.email || "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(f)}>
                        <Pencil size={13} /> Editar
                      </button>
                    </td>
                  </tr>
                  {editando === f.id && (
                    <tr><td colSpan={6} style={{ padding: 0 }}>
                      <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum fornecedor cadastrado ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FormItem({ form, setForm, onSalvar, onCancelar, salvando, msg }: {
  form: Form; setForm: (f: Form) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div><label style={labelStyle}>Tipo</label>
          <select style={inputStyle} value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })}>
            {TIPOS.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
          </select></div>
        <div><label style={labelStyle}>CNPJ/CPF</label><input style={inputStyle} value={form.cnpj_cpf} onChange={(e) => setForm({ ...form, cnpj_cpf: e.target.value })} /></div>
        <div><label style={labelStyle}>Telefone</label><input style={inputStyle} value={form.telefone} onChange={(e) => setForm({ ...form, telefone: e.target.value })} /></div>
        <div><label style={labelStyle}>Email</label><input style={inputStyle} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
        <div style={{ gridColumn: "1 / -1" }}><label style={labelStyle}>Observações</label>
          <textarea style={{ ...inputStyle, minHeight: "2.4rem" }} value={form.observacoes} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} /></div>
      </div>
      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onSalvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}
