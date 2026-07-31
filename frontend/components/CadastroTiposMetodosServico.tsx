"use client";
import { Fragment, useEffect, useState } from "react";
import { Heart, Plus, Pencil, AlertTriangle, Check, X } from "lucide-react";
import {
  fetchTiposServico, criarTipoServico, atualizarTipoServico,
  fetchMetodosServico, criarMetodoServico, atualizarMetodoServico, type MetodoServico,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

type Tipo = { id: number; nome: string; ativo: boolean };

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

export default function CadastroTiposMetodosServico() {
  const [tipos, setTipos] = useState<Tipo[] | null>(null);
  const [metodos, setMetodos] = useState<MetodoServico[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const carregar = () => {
    fetchTiposServico().then(setTipos).catch((e) => setError(e.message));
    fetchMetodosServico().then(setMetodos).catch((e) => setError(e.message));
  };
  useEffect(() => { carregar(); }, []);

  return (
    <div className="space-y-4">
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
        Vocabulário do lançamento de Serviço/Inseminação (Lançamentos › Reprodutivo). Cada método pertence a um
        tipo de serviço — "Monta Natural" é puxado automaticamente quando o tipo é Cobertura; "IA em cio natural"
        e "IATF" quando o tipo é IA.
      </p>
      {error && <div className="alert-critico"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}

      <CardTipos tipos={tipos} onSalvo={carregar} />
      <CardMetodos metodos={metodos} tipos={tipos} onSalvo={carregar} />
    </div>
  );
}

function CardTipos({ tipos, onSalvo }: { tipos: Tipo[] | null; onSalvo: () => void }) {
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<{ nome: string; ativo: boolean }>({ nome: "", ativo: true });
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const abrirNovo = () => { setForm({ nome: "", ativo: true }); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (t: Tipo) => { setForm({ nome: t.nome, ativo: t.ativo }); setEditando(t.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(tipos ?? []);

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = { nome: form.nome.trim(), ativo: form.ativo };
      if (editando === "novo") await criarTipoServico(dados);
      else if (typeof editando === "number") await atualizarTipoServico(editando, dados);
      setEditando(null);
      onSalvo();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Heart size={16} /> Tipos de serviço</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      {editando === "novo" && <FormTipo form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />}
      {!tipos && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {tipos && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} /><th></th></tr></thead>
            <tbody>
              {linhasOrdenadas.map((t) => (
                <Fragment key={t.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{t.nome}{!t.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(t)}>
                        <Pencil size={13} /> Editar
                      </button>
                    </td>
                  </tr>
                  {editando === t.id && (
                    <tr><td colSpan={2} style={{ padding: 0 }}>
                      <FormTipo form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!tipos.length && <tr><td colSpan={2} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum tipo cadastrado ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FormTipo({ form, setForm, onSalvar, onCancelar, salvando, msg }: {
  form: { nome: string; ativo: boolean }; setForm: (f: { nome: string; ativo: boolean }) => void;
  onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
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

type FormMetodo = { nome: string; tipo_servico_id: string; ativo: boolean };

function CardMetodos({ metodos, tipos, onSalvo }: { metodos: MetodoServico[] | null; tipos: Tipo[] | null; onSalvo: () => void }) {
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<FormMetodo>({ nome: "", tipo_servico_id: "", ativo: true });
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const abrirNovo = () => { setForm({ nome: "", tipo_servico_id: tipos?.[0] ? String(tipos[0].id) : "", ativo: true }); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (m: MetodoServico) => { setForm({ nome: m.nome, tipo_servico_id: String(m.tipo_servico_id), ativo: m.ativo }); setEditando(m.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(metodos ?? []);

  // Cobertura só faz sentido com Monta Natural — pré-preenche o nome quando o
  // usuário escolhe esse tipo num método novo, para não digitar à toa.
  const escolherTipo = (tipoId: string) => {
    const tipo = tipos?.find((t) => String(t.id) === tipoId);
    setForm((f) => ({
      ...f, tipo_servico_id: tipoId,
      nome: !f.nome && tipo?.nome === "Cobertura" ? "Monta Natural" : f.nome,
    }));
  };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (!form.tipo_servico_id) { setMsg("Selecione o tipo de serviço."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = { nome: form.nome.trim(), tipo_servico_id: Number(form.tipo_servico_id), ativo: form.ativo };
      if (editando === "novo") await criarMetodoServico(dados);
      else if (typeof editando === "number") await atualizarMetodoServico(editando, dados);
      setEditando(null);
      onSalvo();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const FormMetodoBox = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div>
          <label style={labelStyle}>Tipo de serviço</label>
          <select style={inputStyle} value={form.tipo_servico_id} onChange={(e) => escolherTipo(e.target.value)}>
            <option value="">Selecione…</option>
            {(tipos ?? []).map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
          </select>
        </div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>
      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Heart size={16} /> Métodos</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo} disabled={!tipos?.length}>
          <Plus size={14} /> Novo
        </button>
      </div>
      {editando === "novo" && FormMetodoBox}
      {!metodos && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {metodos && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} /><ThOrdenavel label="Tipo de serviço" campo="tipo_servico_nome" coluna={coluna} dir={dir} ordenar={ordenar} /><th></th></tr></thead>
            <tbody>
              {linhasOrdenadas.map((m) => (
                <Fragment key={m.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{m.nome}{!m.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ fontSize: "0.82rem" }}>{m.tipo_servico_nome ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(m)}>
                        <Pencil size={13} /> Editar
                      </button>
                    </td>
                  </tr>
                  {editando === m.id && (
                    <tr><td colSpan={3} style={{ padding: 0 }}>{FormMetodoBox}</td></tr>
                  )}
                </Fragment>
              ))}
              {!metodos.length && <tr><td colSpan={3} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum método cadastrado ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
