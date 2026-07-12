"use client";
import { Fragment, useEffect, useState } from "react";
import { Dna, Plus, Pencil, Trash2, AlertTriangle, Check, X, Search } from "lucide-react";
import { fetchEstoqueSemen, criarEstoqueSemen, atualizarEstoqueSemen, excluirEstoqueSemen } from "@/lib/api";

type Semen = {
  id: number; touro_nome: string; codigo: string | null; naab: string | null; central: string | null;
  tipo: string; doses: number; observacao: string | null; ativo: boolean;
};
type Form = { touro_nome: string; codigo: string; naab: string; central: string; tipo: string; doses: string; observacao: string };
const formVazio: Form = { touro_nome: "", codigo: "", naab: "", central: "", tipo: "convencional", doses: "", observacao: "" };

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const cellInputStyle: React.CSSProperties = { ...inputStyle, padding: "0.25rem 0.4rem", fontSize: "0.78rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

// Normaliza texto para busca insensível a maiúsculas e acentos.
const normalizar = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

// Mesmos limiares do relatório de manejo → Estoque de sêmen.
// Convencional: <15 vermelho, 15–25 amarelo, >25 verde.
// Sexado:       <5 vermelho, 5–15 amarelo, >15 verde.
// Mínimos por categoria (iguais aos do backend: convencional 20, sexado 5).
// Touro da fazenda é monta natural — não conta dose.
function nivelDoses(tipo: string, doses: number): { cor: string; rotulo: string } {
  if (tipo === "fazenda") return { cor: "var(--text-muted)", rotulo: "monta natural" };
  if (tipo === "sexado") {
    if (doses < 5) return { cor: "var(--red)", rotulo: "abaixo do mínimo (5)" };
    if (doses <= 10) return { cor: "var(--amber)", rotulo: "estoque médio" };
    return { cor: "var(--green-light)", rotulo: "estoque bom" };
  }
  if (doses < 20) return { cor: "var(--red)", rotulo: "abaixo do mínimo (20)" };
  if (doses <= 30) return { cor: "var(--amber)", rotulo: "estoque médio" };
  return { cor: "var(--green-light)", rotulo: "estoque bom" };
}

function paraPayload(f: Form) {
  const s = (v: string) => (v.trim() === "" ? undefined : v.trim());
  return {
    touro_nome: f.touro_nome.trim(),
    codigo: s(f.codigo),
    naab: s(f.naab),
    central: s(f.central),
    tipo: f.tipo,
    doses: Number(f.doses) || 0,
    observacao: s(f.observacao),
  };
}

export default function CadastroEstoqueSemen() {
  const [itens, setItens] = useState<Semen[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  // Formulário fixo de inclusão no topo.
  const [novo, setNovo] = useState<Form>(formVazio);
  const [salvandoNovo, setSalvandoNovo] = useState(false);
  const [msgNovo, setMsgNovo] = useState<{ texto: string; ok: boolean } | null>(null);

  // Edição inline de uma linha.
  const [editId, setEditId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<Form>(formVazio);
  const [salvandoEdit, setSalvandoEdit] = useState(false);
  const [msgEdit, setMsgEdit] = useState<string | null>(null);

  const carregar = () => fetchEstoqueSemen().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const adicionar = async () => {
    if (!novo.touro_nome.trim()) { setMsgNovo({ texto: "Nome do touro é obrigatório.", ok: false }); return; }
    setSalvandoNovo(true); setMsgNovo(null);
    try {
      await criarEstoqueSemen(paraPayload(novo));
      setNovo(formVazio);
      setMsgNovo({ texto: "Touro cadastrado com sucesso.", ok: true });
      await carregar();
    } catch (e: any) {
      setMsgNovo({ texto: e.message || "Erro ao salvar", ok: false });
    } finally {
      setSalvandoNovo(false);
    }
  };

  const abrirEdicao = (s: Semen) => {
    setEditForm({
      touro_nome: s.touro_nome, codigo: s.codigo ?? "", naab: s.naab ?? "", central: s.central ?? "",
      tipo: s.tipo, doses: String(s.doses ?? ""), observacao: s.observacao ?? "",
    });
    setEditId(s.id); setMsgEdit(null);
  };
  const cancelarEdicao = () => { setEditId(null); setMsgEdit(null); };

  const salvarEdicao = async (original: Semen) => {
    if (!editForm.touro_nome.trim()) { setMsgEdit("Nome do touro é obrigatório."); return; }
    setSalvandoEdit(true); setMsgEdit(null);
    try {
      // Preserva observação e status ativo caso não editados nas colunas visíveis.
      await atualizarEstoqueSemen(original.id, { ...paraPayload(editForm), ativo: original.ativo });
      setEditId(null);
      await carregar();
    } catch (e: any) {
      setMsgEdit(e.message || "Erro ao salvar");
    } finally {
      setSalvandoEdit(false);
    }
  };

  const excluir = async (s: Semen) => {
    if (!window.confirm(`Excluir o touro "${s.touro_nome}" do estoque de sêmen?`)) return;
    try {
      await excluirEstoqueSemen(s.id);
      await carregar();
    } catch (e: any) {
      setError(e.message || "Erro ao excluir");
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((s) =>
    !termoBusca || normalizar(`${s.touro_nome} ${s.codigo ?? ""} ${s.naab ?? ""} ${s.central ?? ""} ${s.observacao ?? ""}`).includes(termoBusca)
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center gap-2">
        <Dna size={16} /> Estoque de sêmen
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Cadastre aqui os touros e as doses disponíveis. Alimenta o relatório de manejo → Estoque de sêmen.
      </p>

      {/* Formulário de inclusão */}
      <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div><label style={labelStyle}>Touro</label>
            <input style={inputStyle} value={novo.touro_nome} title="Nome do touro" placeholder="Nome do touro"
              onChange={(e) => setNovo({ ...novo, touro_nome: e.target.value })} /></div>
          <div><label style={labelStyle}>Código</label>
            <input style={inputStyle} value={novo.codigo} title="Código de registro do touro"
              onChange={(e) => setNovo({ ...novo, codigo: e.target.value })} /></div>
          <div><label style={labelStyle}>NAAB</label>
            <input style={inputStyle} value={novo.naab} title="Código NAAB do touro (ex.: 7HO12345)" placeholder="Ex.: 7HO12345"
              onChange={(e) => setNovo({ ...novo, naab: e.target.value })} /></div>
          <div><label style={labelStyle}>Central</label>
            <input style={inputStyle} value={novo.central} title="Central de genética — ex.: ABS, Alta, Semex" placeholder="Ex.: ABS, Alta, Semex"
              onChange={(e) => setNovo({ ...novo, central: e.target.value })} /></div>
          <div><label style={labelStyle}>Tipo</label>
            <select style={inputStyle} value={novo.tipo} title="Tipo de sêmen" onChange={(e) => setNovo({ ...novo, tipo: e.target.value })}>
              <option value="convencional">Convencional</option>
              <option value="sexado">Sexado</option>
              <option value="fazenda">Touro da fazenda (monta natural)</option>
            </select></div>
          <div><label style={labelStyle}>Doses</label>
            <input style={inputStyle} type="number" min={0} value={novo.doses} title="Quantidade de doses disponíveis"
              onChange={(e) => setNovo({ ...novo, doses: e.target.value })} /></div>
          <div style={{ gridColumn: "1 / -1" }}><label style={labelStyle}>Observação</label>
            <input style={inputStyle} value={novo.observacao} title="Observação (opcional)"
              onChange={(e) => setNovo({ ...novo, observacao: e.target.value })} /></div>
        </div>
        {msgNovo && <p style={{ color: msgNovo.ok ? "var(--green-light)" : "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msgNovo.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
          onClick={adicionar} disabled={salvandoNovo} title="Cadastrar touro e doses no estoque de sêmen">
          <Plus size={14} /> {salvandoNovo ? "Salvando…" : "Adicionar"}
        </button>
      </div>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar touro…" title="Buscar por touro, código, central ou observação" />
          </div>
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Touro</th><th>Código</th><th>NAAB</th><th>Central</th><th>Tipo</th><th>Doses</th><th></th></tr></thead>
            <tbody>
              {filtrados.map((s) => {
                const emEdicao = editId === s.id;
                const nivel = nivelDoses(s.tipo, s.doses);
                return (
                  <Fragment key={s.id}>
                    {emEdicao ? (
                      <tr>
                        <td><input style={cellInputStyle} value={editForm.touro_nome} title="Nome do touro"
                          onChange={(e) => setEditForm({ ...editForm, touro_nome: e.target.value })} /></td>
                        <td><input style={cellInputStyle} value={editForm.codigo} title="Código do touro"
                          onChange={(e) => setEditForm({ ...editForm, codigo: e.target.value })} /></td>
                        <td><input style={cellInputStyle} value={editForm.naab} title="Código NAAB do touro"
                          onChange={(e) => setEditForm({ ...editForm, naab: e.target.value })} /></td>
                        <td><input style={cellInputStyle} value={editForm.central} title="Central de genética"
                          onChange={(e) => setEditForm({ ...editForm, central: e.target.value })} /></td>
                        <td><select style={cellInputStyle} value={editForm.tipo} title="Tipo de sêmen"
                          onChange={(e) => setEditForm({ ...editForm, tipo: e.target.value })}>
                          <option value="convencional">Convencional</option>
                          <option value="sexado">Sexado</option>
                        </select></td>
                        <td><input style={{ ...cellInputStyle, width: "5rem" }} type="number" min={0} value={editForm.doses} title="Doses disponíveis"
                          onChange={(e) => setEditForm({ ...editForm, doses: e.target.value })} /></td>
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          <button className="btn-primary" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", marginRight: "0.35rem" }}
                            onClick={() => salvarEdicao(s)} disabled={salvandoEdit} title="Salvar alterações">
                            <Check size={13} /> {salvandoEdit ? "Salvando…" : "Salvar"}
                          </button>
                          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                            onClick={cancelarEdicao} title="Cancelar">
                            <X size={13} /> Cancelar
                          </button>
                        </td>
                      </tr>
                    ) : (
                      <tr>
                        <td style={{ fontWeight: 700 }} title={s.observacao || undefined}>
                          {s.touro_nome}{!s.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}
                        </td>
                        <td style={{ fontSize: "0.78rem" }}>{s.codigo || "—"}</td>
                        <td style={{ fontSize: "0.78rem" }}>{s.naab || "—"}</td>
                        <td style={{ fontSize: "0.78rem" }}>{s.central || "—"}</td>
                        <td style={{ textTransform: "capitalize" }}>{s.tipo === "sexado" ? "Sexado" : "Convencional"}</td>
                        <td>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
                            title={`${s.doses} dose(s) — ${nivel.rotulo} (${s.tipo === "sexado" ? "Sexado" : "Convencional"})`}>
                            <span style={{ width: "0.55rem", height: "0.55rem", borderRadius: "999px", background: nivel.cor, display: "inline-block" }} />
                            <span style={{ color: nivel.cor, fontWeight: 700 }}>{s.doses}</span>
                          </span>
                        </td>
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", marginRight: "0.35rem" }}
                            onClick={() => abrirEdicao(s)} title="Editar">
                            <Pencil size={13} /> Editar
                          </button>
                          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", color: "var(--red)" }}
                            onClick={() => excluir(s)} title="Excluir">
                            <Trash2 size={13} /> Excluir
                          </button>
                        </td>
                      </tr>
                    )}
                    {emEdicao && msgEdit && (
                      <tr><td colSpan={7} style={{ color: "var(--red)", fontSize: "0.78rem", paddingTop: 0 }}>{msgEdit}</td></tr>
                    )}
                  </Fragment>
                );
              })}
              {!itens.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum touro cadastrado ainda.</td></tr>}
              {!!itens.length && !filtrados.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
      )}
    </div>
  );
}
