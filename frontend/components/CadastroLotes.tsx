"use client";
import { Fragment, useEffect, useState } from "react";
import { Layers, Plus, Pencil, AlertTriangle, Check, X } from "lucide-react";
import { fetchLotes, criarLote, atualizarLote } from "@/lib/api";

type Lote = {
  id: number; codigo: string; nome: string; rotulo: string; qtd_animais: number;
  del_min: number | null; del_max: number | null; producao_min: number | null; producao_max: number | null;
};

type Form = {
  codigo: string; nome: string; del_min: string; del_max: string; producao_min: string; producao_max: string;
};

const formVazio: Form = { codigo: "", nome: "", del_min: "", del_max: "", producao_min: "", producao_max: "" };

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

export default function CadastroLotes() {
  const [lotes, setLotes] = useState<Lote[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchLotes().then(setLotes).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (l: Lote) => {
    setForm({
      codigo: l.codigo, nome: l.nome,
      del_min: l.del_min?.toString() ?? "", del_max: l.del_max?.toString() ?? "",
      producao_min: l.producao_min?.toString() ?? "", producao_max: l.producao_max?.toString() ?? "",
    });
    setEditando(l.id);
    setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.codigo.trim() || !form.nome.trim()) { setMsg("Código e nome são obrigatórios."); return; }
    const dados = {
      codigo: form.codigo.trim(),
      nome: form.nome.trim(),
      del_min: form.del_min === "" ? null : Number(form.del_min),
      del_max: form.del_max === "" ? null : Number(form.del_max),
      producao_min: form.producao_min === "" ? null : Number(form.producao_min),
      producao_max: form.producao_max === "" ? null : Number(form.producao_max),
    };
    setSalvando(true);
    setMsg(null);
    try {
      if (editando === "novo") await criarLote(dados);
      else if (typeof editando === "number") await atualizarLote(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar lote");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Layers size={22} style={{ color: "var(--dourado)" }} /> Cadastro de lotes</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Crie e edite os lotes de manejo. As faixas de DEL e de produção definidas aqui vão orientar as futuras
          sugestões automáticas de movimentação entre lotes.
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!lotes && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {lotes && (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span>Lotes cadastrados</span>
            <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
              <Plus size={14} /> Novo lote
            </button>
          </div>

          {editando === "novo" && (
            <FormLote form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
          )}

          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead>
                <tr>
                  <th>Código</th><th>Nome</th><th style={{ textAlign: "right" }}>Animais</th>
                  <th style={{ textAlign: "right" }}>DEL mín.</th><th style={{ textAlign: "right" }}>DEL máx.</th>
                  <th style={{ textAlign: "right" }}>Produção mín. (kg)</th><th style={{ textAlign: "right" }}>Produção máx. (kg)</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {lotes.map((l) => (
                  <Fragment key={l.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{l.codigo}</td>
                      <td>{l.nome}</td>
                      <td style={{ textAlign: "right" }}>{l.qtd_animais}</td>
                      <td style={{ textAlign: "right" }}>{l.del_min ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.del_max ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.producao_min ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.producao_max ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(l)}>
                          <Pencil size={13} /> Editar
                        </button>
                      </td>
                    </tr>
                    {editando === l.id && (
                      <tr>
                        <td colSpan={8} style={{ padding: 0 }}>
                          <FormLote form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {!lotes.length && !editando && (
                  <tr><td colSpan={8} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum lote cadastrado ainda.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function FormLote({ form, setForm, onSalvar, onCancelar, salvando, msg }: {
  form: Form; setForm: (f: Form) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-3">
        <div><label style={labelStyle}>Código</label>
          <input style={inputStyle} value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} placeholder="ex.: 01" /></div>
        <div><label style={labelStyle}>Nome</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Alta" /></div>
        <div><label style={labelStyle}>DEL de</label>
          <input type="number" style={inputStyle} value={form.del_min} onChange={(e) => setForm({ ...form, del_min: e.target.value })} /></div>
        <div><label style={labelStyle}>DEL até</label>
          <input type="number" style={inputStyle} value={form.del_max} onChange={(e) => setForm({ ...form, del_max: e.target.value })} /></div>
        <div><label style={labelStyle}>Produção de (kg)</label>
          <input type="number" style={inputStyle} value={form.producao_min} onChange={(e) => setForm({ ...form, producao_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Produção até (kg)</label>
          <input type="number" style={inputStyle} value={form.producao_max} onChange={(e) => setForm({ ...form, producao_max: e.target.value })} /></div>
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
