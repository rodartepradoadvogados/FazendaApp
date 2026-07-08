"use client";
import { Fragment, useEffect, useState } from "react";
import { Syringe, Bug, CalendarClock, Plus, Pencil, AlertTriangle, Check, X } from "lucide-react";
import {
  fetchPrincipiosAtivos, criarPrincipioAtivo, atualizarPrincipioAtivo,
  fetchDoencas, criarDoenca, atualizarDoenca,
  fetchEventosSanitarios, criarEventoSanitario, atualizarEventoSanitario,
} from "@/lib/api";

const ABAS = [
  ["principios", "Princípio ativo", Syringe],
  ["doencas", "Doença", Bug],
  ["eventos", "Evento sanitário", CalendarClock],
] as const;

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

export default function CadastroSanitario() {
  const [aba, setAba] = useState<(typeof ABAS)[number][0]>("principios");

  return (
    <div>
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

      {aba === "principios" && (
        <ListaNomeAtivo
          titulo="Princípios ativos" icone={Syringe}
          descricao='Usado para classificar produtos no calendário sanitário — ex.: "Ivermectina", "Cepa RB51".'
          fetchFn={fetchPrincipiosAtivos} criarFn={criarPrincipioAtivo} atualizarFn={atualizarPrincipioAtivo}
          semRegistros="Nenhum princípio ativo cadastrado ainda."
        />
      )}
      {aba === "doencas" && (
        <ListaNomeAtivo
          titulo="Doenças" icone={Bug}
          descricao="O que cada evento do calendário sanitário visa combater."
          fetchFn={fetchDoencas} criarFn={criarDoenca} atualizarFn={atualizarDoenca}
          semRegistros="Nenhuma doença cadastrada ainda."
        />
      )}
      {aba === "eventos" && (
        <ListaNomeAtivo
          titulo="Eventos sanitários" icone={CalendarClock}
          descricao='Nome do protocolo/vacina do calendário sanitário — ex.: "Vermífugo", "Brucelose B19".'
          fetchFn={fetchEventosSanitarios} criarFn={criarEventoSanitario} atualizarFn={atualizarEventoSanitario}
          semRegistros="Nenhum evento sanitário cadastrado ainda."
        />
      )}
    </div>
  );
}

type Item = { id: number; nome: string; ativo: boolean };
type Form = { nome: string; ativo: boolean };
const formVazio: Form = { nome: "", ativo: true };

function ListaNomeAtivo({ titulo, icone: Icone, descricao, fetchFn, criarFn, atualizarFn, semRegistros }: {
  titulo: string; icone: any; descricao: string; semRegistros: string;
  fetchFn: () => Promise<Item[]>;
  criarFn: (dados: { nome: string; ativo?: boolean }) => Promise<Item>;
  atualizarFn: (id: number, dados: { nome: string; ativo: boolean }) => Promise<Item>;
}) {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchFn().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (i: Item) => { setForm({ nome: i.nome, ativo: i.ativo }); setEditando(i.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = { nome: form.nome.trim(), ativo: form.ativo };
      if (editando === "novo") await criarFn(dados);
      else if (typeof editando === "number") await atualizarFn(editando, dados);
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
        <span className="flex items-center gap-2"><Icone size={16} /> {titulo}</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>{descricao}</p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />}

      {itens && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Nome</th><th></th></tr></thead>
            <tbody>
              {itens.map((i) => (
                <Fragment key={i.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{i.nome}{!i.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(i)}>
                        <Pencil size={13} /> Editar
                      </button>
                    </td>
                  </tr>
                  {editando === i.id && (
                    <tr><td colSpan={2} style={{ padding: 0 }}>
                      <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={2} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{semRegistros}</td></tr>}
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
