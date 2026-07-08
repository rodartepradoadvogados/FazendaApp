"use client";
import { Fragment, useEffect, useState } from "react";
import { Layers, Plus, Pencil, AlertTriangle, Check, X, Users } from "lucide-react";
import { fetchLotes, criarLote, atualizarLote, previewCriteriosLote } from "@/lib/api";

type Lote = {
  id: number; codigo: string; nome: string; rotulo: string; qtd_animais: number;
  del_min: number | null; del_max: number | null; producao_min: number | null; producao_max: number | null;
  status_lactacao: string | null; categorias: string | null; pre_parto: boolean | null;
  peso_min: number | null; peso_max: number | null;
  dias_para_parto_min: number | null; dias_para_parto_max: number | null;
  em_tratamento: boolean | null; idade_dias_min: number | null; idade_dias_max: number | null;
  novilhas_inseminadas: boolean | null; novilhas_gestantes: boolean | null;
};

type Form = {
  codigo: string; nome: string; del_min: string; del_max: string; producao_min: string; producao_max: string;
  status_lactacao: string; categorias: string[]; pre_parto: boolean;
  peso_min: string; peso_max: string;
  dias_para_parto_min: string; dias_para_parto_max: string;
  em_tratamento: boolean; idade_dias_min: string; idade_dias_max: string;
  novilhas_inseminadas: boolean; novilhas_gestantes: boolean;
};

const formVazio: Form = {
  codigo: "", nome: "", del_min: "", del_max: "", producao_min: "", producao_max: "",
  status_lactacao: "", categorias: [], pre_parto: false,
  peso_min: "", peso_max: "", dias_para_parto_min: "", dias_para_parto_max: "",
  em_tratamento: false, idade_dias_min: "", idade_dias_max: "",
  novilhas_inseminadas: false, novilhas_gestantes: false,
};

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

// Monta o payload que a API espera a partir do form (strings vazias -> null).
function paraPayload(form: Form) {
  const n = (v: string) => (v === "" ? null : Number(v));
  return {
    codigo: form.codigo.trim(),
    nome: form.nome.trim(),
    del_min: n(form.del_min), del_max: n(form.del_max),
    producao_min: n(form.producao_min), producao_max: n(form.producao_max),
    status_lactacao: form.status_lactacao || null,
    categorias: form.categorias.length ? form.categorias.join(",") : null,
    pre_parto: form.pre_parto || null,
    peso_min: n(form.peso_min), peso_max: n(form.peso_max),
    dias_para_parto_min: n(form.dias_para_parto_min), dias_para_parto_max: n(form.dias_para_parto_max),
    em_tratamento: form.em_tratamento || null,
    idade_dias_min: n(form.idade_dias_min), idade_dias_max: n(form.idade_dias_max),
    novilhas_inseminadas: form.novilhas_inseminadas || null,
    novilhas_gestantes: form.novilhas_gestantes || null,
  };
}

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
      status_lactacao: l.status_lactacao ?? "",
      categorias: l.categorias ? l.categorias.split(",") : [],
      pre_parto: !!l.pre_parto,
      peso_min: l.peso_min?.toString() ?? "", peso_max: l.peso_max?.toString() ?? "",
      dias_para_parto_min: l.dias_para_parto_min?.toString() ?? "", dias_para_parto_max: l.dias_para_parto_max?.toString() ?? "",
      em_tratamento: !!l.em_tratamento,
      idade_dias_min: l.idade_dias_min?.toString() ?? "", idade_dias_max: l.idade_dias_max?.toString() ?? "",
      novilhas_inseminadas: !!l.novilhas_inseminadas, novilhas_gestantes: !!l.novilhas_gestantes,
    });
    setEditando(l.id);
    setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.codigo.trim() || !form.nome.trim()) { setMsg("Código e nome são obrigatórios."); return; }
    const dados = paraPayload(form);
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
          Crie e edite os lotes de manejo. Os critérios cumulativos definidos aqui (E lógico entre os marcados) vão
          orientar as futuras sugestões automáticas de movimentação entre lotes.
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
                  <th style={{ textAlign: "right" }}>Produção mín. (L)</th><th style={{ textAlign: "right" }}>Produção máx. (L)</th>
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
  const [preview, setPreview] = useState<{ total: number; animais: string[] } | null>(null);
  const [carregandoPreview, setCarregandoPreview] = useState(false);

  useEffect(() => {
    setCarregandoPreview(true);
    const h = setTimeout(() => {
      previewCriteriosLote(paraPayload(form)).then(setPreview).catch(() => setPreview(null)).finally(() => setCarregandoPreview(false));
    }, 300);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(form)]);

  const toggleCategoria = (c: string) => setForm({
    ...form, categorias: form.categorias.includes(c) ? form.categorias.filter((x) => x !== c) : [...form.categorias, c],
  });

  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-3">
        <div><label style={labelStyle}>Código</label>
          <input style={inputStyle} value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} placeholder="ex.: 01" /></div>
        <div><label style={labelStyle}>Nome</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Alta" /></div>
        <div><label style={labelStyle}>DEL de</label>
          <input type="number" style={inputStyle} value={form.del_min} onChange={(e) => setForm({ ...form, del_min: e.target.value })} /></div>
        <div><label style={labelStyle}>DEL até (após o parto)</label>
          <input type="number" style={inputStyle} value={form.del_max} onChange={(e) => setForm({ ...form, del_max: e.target.value })} /></div>
        <div><label style={labelStyle}>Produção de (L)</label>
          <input type="number" style={inputStyle} value={form.producao_min} onChange={(e) => setForm({ ...form, producao_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Produção até (L)</label>
          <input type="number" style={inputStyle} value={form.producao_max} onChange={(e) => setForm({ ...form, producao_max: e.target.value })} /></div>
      </div>

      <div className="card-header mb-2" style={{ fontSize: "0.75rem", padding: 0, background: "none", color: "var(--dourado-light)" }}>
        Critérios de seleção (cumulativos — todos os marcados/preenchidos precisam ser atendidos)
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-3">
        <div><label style={labelStyle}>Em lactação ou seca</label>
          <select style={inputStyle} value={form.status_lactacao} onChange={(e) => setForm({ ...form, status_lactacao: e.target.value })}>
            <option value="">Qualquer</option>
            <option value="lactacao">Em lactação</option>
            <option value="seca">Seca</option>
          </select></div>
        <div>
          <label style={labelStyle}>Categoria</label>
          <div className="flex items-center gap-2" style={{ paddingTop: "0.35rem" }}>
            {["vaca", "novilha", "bezerra"].map((c) => (
              <label key={c} className="flex items-center gap-1" style={{ fontSize: "0.75rem", textTransform: "capitalize" }}>
                <input type="checkbox" checked={form.categorias.includes(c)} onChange={() => toggleCategoria(c)} /> {c}
              </label>
            ))}
          </div>
        </div>
        <div><label style={labelStyle}>Faltando p/ parto — de (dias)</label>
          <input type="number" style={inputStyle} value={form.dias_para_parto_min} onChange={(e) => setForm({ ...form, dias_para_parto_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Faltando p/ parto — até (dias)</label>
          <input type="number" style={inputStyle} value={form.dias_para_parto_max} onChange={(e) => setForm({ ...form, dias_para_parto_max: e.target.value })} /></div>
        <div><label style={labelStyle}>Peso de (kg)</label>
          <input type="number" style={inputStyle} value={form.peso_min} onChange={(e) => setForm({ ...form, peso_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Peso até (kg)</label>
          <input type="number" style={inputStyle} value={form.peso_max} onChange={(e) => setForm({ ...form, peso_max: e.target.value })} /></div>
        <div><label style={labelStyle}>Idade de (dias de vida)</label>
          <input type="number" style={inputStyle} value={form.idade_dias_min} onChange={(e) => setForm({ ...form, idade_dias_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Idade até (dias de vida)</label>
          <input type="number" style={inputStyle} value={form.idade_dias_max} onChange={(e) => setForm({ ...form, idade_dias_max: e.target.value })} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.pre_parto} onChange={(e) => setForm({ ...form, pre_parto: e.target.checked })} /> Pré-parto</label></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.em_tratamento} onChange={(e) => setForm({ ...form, em_tratamento: e.target.checked })} /> Em tratamento</label></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.novilhas_inseminadas} onChange={(e) => setForm({ ...form, novilhas_inseminadas: e.target.checked })} /> Novilhas inseminadas</label></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.novilhas_gestantes} onChange={(e) => setForm({ ...form, novilhas_gestantes: e.target.checked })} /> Novilhas gestantes</label></div>
      </div>

      <div className="flex items-center gap-2 mb-3" style={{ fontSize: "0.8rem", color: "var(--dourado-light)" }}>
        <Users size={14} />
        {carregandoPreview ? "Calculando…" : preview ? `${preview.total} animal(is) do rebanho atende(m) a esses critérios hoje.` : "—"}
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
