"use client";
import { Fragment, useEffect, useState } from "react";
import { GitBranch, Plus, Pencil, AlertTriangle, Check, X } from "lucide-react";
import {
  fetchRacas, criarRaca, atualizarRaca,
  fetchGrausSangue, criarGrauSangue, atualizarGrauSangue,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

type Raca = { id: number; nome: string; nota: string | null; ativo: boolean };
type RacaForm = { nome: string; nota: string; ativo: boolean };
const racaFormVazio: RacaForm = { nome: "", nota: "", ativo: true };

type Grau = { id: number; nome: string; fracao_holandes: number | null; nota: string | null; ativo: boolean };
type GrauForm = { nome: string; fracao_holandes: string; nota: string; ativo: boolean };
const grauFormVazio: GrauForm = { nome: "", fracao_holandes: "", nota: "", ativo: true };

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

export default function CadastroRacas() {
  const [sub, setSub] = useState<"racas" | "graus">("racas");
  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><GitBranch size={16} /> Raças e grau de sangue</span>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Vocabulário usado no cadastro do animal. O grau de sangue tem uma fração de sangue Holandês (escala
        Holandês x Gir) — quando preenchida, o parto calcula automaticamente o grau de sangue da cria a partir
        da mãe e do touro/sêmen usado no serviço que gerou a gestação (sempre editável depois na ficha do animal).
      </p>
      <div className="flex gap-2 mb-3">
        <button className={sub === "racas" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.78rem" }} onClick={() => setSub("racas")}>Raças</button>
        <button className={sub === "graus" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.78rem" }} onClick={() => setSub("graus")}>Grau de sangue</button>
      </div>
      {sub === "racas" ? <RacasTab /> : <GrausTab />}
    </div>
  );
}

function RacasTab() {
  const [itens, setItens] = useState<Raca[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<RacaForm>(racaFormVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchRacas().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(itens ?? []);

  const abrirNovo = () => { setForm(racaFormVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (r: Raca) => { setForm({ nome: r.nome, nota: r.nota || "", ativo: r.ativo }); setEditando(r.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = { nome: form.nome.trim(), nota: form.nota.trim() || null, ativo: form.ativo };
      if (editando === "novo") await criarRaca(dados);
      else if (typeof editando === "number") await atualizarRaca(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <>
      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      <div className="flex justify-end mb-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Nova raça
        </button>
      </div>
      {editando === "novo" && <RacaFormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />}
      {itens && (
        <div className="overflow-x-auto">
        <table className="fazenda-table">
          <thead><tr><ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} /><th></th></tr></thead>
          <tbody>
            {linhasOrdenadas.map((r) => (
              <Fragment key={r.id}>
                <tr>
                  <td>
                    <div style={{ fontWeight: 700 }}>{r.nome}{!r.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</div>
                    {r.nota && <div style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginTop: "0.15rem" }}>{r.nota}</div>}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(r)}>
                      <Pencil size={13} /> Editar
                    </button>
                  </td>
                </tr>
                {editando === r.id && (
                  <tr><td colSpan={2} style={{ padding: 0 }}>
                    <RacaFormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
                  </td></tr>
                )}
              </Fragment>
            ))}
            {!itens.length && <tr><td colSpan={2} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma raça cadastrada ainda.</td></tr>}
          </tbody>
        </table>
        </div>
      )}
    </>
  );
}

function RacaFormItem({ form, setForm, onSalvar, onCancelar, salvando, msg }: {
  form: RacaForm; setForm: (f: RacaForm) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>
      <div className="mb-3">
        <label style={labelStyle}>Nota (texto didático mostrado no seletor)</label>
        <textarea style={{ ...inputStyle, minHeight: "3.2rem", resize: "vertical" }} value={form.nota}
          onChange={(e) => setForm({ ...form, nota: e.target.value })} placeholder="ex.: raça leiteira originária da Índia, muito rústica e resistente ao calor…" />
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

function GrausTab() {
  const [itens, setItens] = useState<Grau[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<GrauForm>(grauFormVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchGrausSangue().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(itens ?? []);

  const abrirNovo = () => { setForm(grauFormVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (g: Grau) => { setForm({ nome: g.nome, fracao_holandes: g.fracao_holandes == null ? "" : String(g.fracao_holandes), nota: g.nota || "", ativo: g.ativo }); setEditando(g.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    const fracao = form.fracao_holandes.trim() === "" ? null : Number(form.fracao_holandes.replace(",", "."));
    if (fracao !== null && (Number.isNaN(fracao) || fracao < 0 || fracao > 1)) { setMsg("Fração de Holandês deve ser um número entre 0 e 1 (ex.: 0,75)."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = { nome: form.nome.trim(), fracao_holandes: fracao, nota: form.nota.trim() || null, ativo: form.ativo };
      if (editando === "novo") await criarGrauSangue(dados);
      else if (typeof editando === "number") await atualizarGrauSangue(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <>
      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      <div className="flex justify-end mb-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo grau de sangue
        </button>
      </div>
      {editando === "novo" && <GrauFormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />}
      {itens && (
        <div className="overflow-x-auto">
        <table className="fazenda-table">
          <thead><tr><ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} /><ThOrdenavel label="Fração de sangue Holandês" campo="fracao_holandes" coluna={coluna} dir={dir} ordenar={ordenar} /><th></th></tr></thead>
          <tbody>
            {linhasOrdenadas.map((g) => (
              <Fragment key={g.id}>
                <tr>
                  <td>
                    <div style={{ fontWeight: 700 }}>{g.nome}{!g.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</div>
                    {g.nota && <div style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginTop: "0.15rem" }}>{g.nota}</div>}
                  </td>
                  <td>{g.fracao_holandes == null ? <span style={{ color: "var(--text-muted)" }}>não calculável</span> : `${Math.round(g.fracao_holandes * 100)}%`}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(g)}>
                      <Pencil size={13} /> Editar
                    </button>
                  </td>
                </tr>
                {editando === g.id && (
                  <tr><td colSpan={3} style={{ padding: 0 }}>
                    <GrauFormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
                  </td></tr>
                )}
              </Fragment>
            ))}
            {!itens.length && <tr><td colSpan={3} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum grau de sangue cadastrado ainda.</td></tr>}
          </tbody>
        </table>
        </div>
      )}
    </>
  );
}

function GrauFormItem({ form, setForm, onSalvar, onCancelar, salvando, msg }: {
  form: GrauForm; setForm: (f: GrauForm) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder='ex.: "3/4 Holandês"' /></div>
        <div>
          <label style={labelStyle}>Fração de sangue Holandês (0 a 1)</label>
          <input style={inputStyle} value={form.fracao_holandes} onChange={(e) => setForm({ ...form, fracao_holandes: e.target.value })} placeholder="ex.: 0,75 — vazio = só rótulo, sem cálculo" />
        </div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>
      <div className="mb-3">
        <label style={labelStyle}>Nota (texto didático mostrado no seletor)</label>
        <textarea style={{ ...inputStyle, minHeight: "3.2rem", resize: "vertical" }} value={form.nota}
          onChange={(e) => setForm({ ...form, nota: e.target.value })} placeholder="ex.: 50% Holandês e 50% Gir — primeira geração (F1) do cruzamento Girolando…" />
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
