"use client";
import { Fragment, useEffect, useState } from "react";
import { Syringe, Bug, CalendarClock, ClipboardList, Plus, Pencil, AlertTriangle, Check, X, Trash2 } from "lucide-react";
import {
  fetchPrincipiosAtivos, criarPrincipioAtivo, atualizarPrincipioAtivo,
  fetchDoencas, criarDoenca, atualizarDoenca,
  fetchEventosSanitarios, criarEventoSanitario, atualizarEventoSanitario,
  fetchProtocolosSanitarios, criarProtocoloSanitario, atualizarProtocoloSanitario,
  fetchEstoque,
  type ProtocoloEtapa,
} from "@/lib/api";
import { EstoquePicker, type EstoqueItemPicker } from "./EstoquePicker";

const VIAS_APLICACAO = ["Intramamária", "Intramuscular", "Intravenosa", "Subdérmica", "Oral"];

const ABAS = [
  ["principios", "Princípio ativo", Syringe],
  ["doencas", "Doença", Bug],
  ["eventos", "Evento sanitário", CalendarClock],
  ["protocolos", "Protocolo sanitário", ClipboardList],
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
      {aba === "protocolos" && <CadastroProtocolosSanitarios />}
    </div>
  );
}

type Protocolo = {
  id: number; nome: string; doenca_id: number | null; doenca_nome: string | null; eh_mastite: boolean; ativo: boolean;
  etapas: ProtocoloEtapa[];
};
type ProtocoloForm = { nome: string; doenca_id: string; eh_mastite: boolean; ativo: boolean; etapas: ProtocoloEtapa[] };
const etapaVazia = (dia: number): ProtocoloEtapa => ({ dia, produto: "", dosagem: 0, unidade: "ml", via: "" });
const protocoloFormVazio = (): ProtocoloForm => ({ nome: "", doenca_id: "", eh_mastite: false, ativo: true, etapas: [etapaVazia(1)] });

function CadastroProtocolosSanitarios() {
  const [itens, setItens] = useState<Protocolo[] | null>(null);
  const [doencas, setDoencas] = useState<{ id: number; nome: string }[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItemPicker[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<ProtocoloForm>(protocoloFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchProtocolosSanitarios().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchDoencas().then(setDoencas).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
  }, []);

  const abrirNovo = () => { setForm(protocoloFormVazio()); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (p: Protocolo) => {
    setForm({
      nome: p.nome, doenca_id: p.doenca_id ? String(p.doenca_id) : "", eh_mastite: p.eh_mastite, ativo: p.ativo,
      etapas: p.etapas.length ? p.etapas.map((e) => ({ ...e })) : [etapaVazia(1)],
    });
    setEditando(p.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const acrescentarEtapa = () => setForm((f) => ({ ...f, etapas: [...f.etapas, etapaVazia(f.etapas.length + 1)] }));
  const removerEtapa = (idx: number) => setForm((f) => (f.etapas.length > 1 ? { ...f, etapas: f.etapas.filter((_, i) => i !== idx) } : f));
  const atualizarEtapa = (idx: number, patch: Partial<ProtocoloEtapa>) =>
    setForm((f) => ({ ...f, etapas: f.etapas.map((e, i) => (i === idx ? { ...e, ...patch } : e)) }));

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (form.etapas.some((e) => e.dia < 1)) { setMsg("Protocolos sanitários não têm D0 — os dias começam em D1."); return; }
    if (form.etapas.some((e) => !e.produto.trim() || !e.dosagem || Number(e.dosagem) <= 0)) { setMsg("Preencha produto e dosagem em todas as etapas."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = {
        nome: form.nome.trim(), doenca_id: form.doenca_id ? Number(form.doenca_id) : undefined,
        eh_mastite: form.eh_mastite, ativo: form.ativo,
        etapas: form.etapas.map((e) => ({ ...e, dia: Number(e.dia), dosagem: Number(e.dosagem), via: e.via || undefined })),
      };
      if (editando === "novo") await criarProtocoloSanitario(dados);
      else if (typeof editando === "number") await atualizarProtocoloSanitario(editando, dados);
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
        <span className="flex items-center gap-2"><ClipboardList size={16} /> Protocolos sanitários</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Tratamento com múltiplas etapas (produto, dosagem, via e dia de aplicação), a exemplo do tratamento de
        mastite. Os dias começam em D1 — protocolos sanitários não têm D0 (isso é exclusivo do protocolo hormonal
        IATF). Marque "É protocolo de mastite" para habilitar, no lançamento, os campos de CMT, teto afetado e
        classificação (clínica/subclínica/ambiental).
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <FormProtocolo
          form={form} setForm={setForm} doencas={doencas} estoque={estoque} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
          acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
        />
      )}

      {itens && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Nome</th><th>Doença</th><th>Mastite</th><th>Etapas</th><th></th></tr></thead>
            <tbody>
              {itens.map((p) => (
                <Fragment key={p.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{p.nome}{!p.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.doenca_nome || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.eh_mastite ? "Sim" : "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.etapas.map((e) => `D${e.dia}`).join(", ")}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(p)}>
                        <Pencil size={13} /> Editar
                      </button>
                    </td>
                  </tr>
                  {editando === p.id && (
                    <tr><td colSpan={5} style={{ padding: 0 }}>
                      <FormProtocolo
                        form={form} setForm={setForm} doencas={doencas} estoque={estoque} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                        acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
                      />
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo cadastrado ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FormProtocolo({ form, setForm, doencas, estoque, onSalvar, onCancelar, salvando, msg, acrescentarEtapa, removerEtapa, atualizarEtapa }: {
  form: ProtocoloForm; setForm: (f: ProtocoloForm) => void; doencas: { id: number; nome: string }[]; estoque: EstoqueItemPicker[];
  onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
  acrescentarEtapa: () => void; removerEtapa: (idx: number) => void; atualizarEtapa: (idx: number, patch: Partial<ProtocoloEtapa>) => void;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Mastite clínica padrão" /></div>
        <div><label style={labelStyle}>Doença vinculada</label>
          <select style={inputStyle} value={form.doenca_id} onChange={(e) => setForm({ ...form, doenca_id: e.target.value })}>
            <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
          </select></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.eh_mastite} onChange={(e) => setForm({ ...form, eh_mastite: e.target.checked })} /> É protocolo de mastite</label></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>

      <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Etapas (D1, D2, D3...)</p>
      <div className="space-y-2 mb-2">
        {form.etapas.map((e, idx) => (
          <div key={idx} className="grid grid-cols-2 md:grid-cols-6 gap-2 items-end" style={{ background: "var(--surface)", padding: "0.5rem", borderRadius: "6px" }}>
            <div><label style={labelStyle}>Dia (D)</label><input type="number" min={1} style={inputStyle} value={e.dia} onChange={(ev) => atualizarEtapa(idx, { dia: Number(ev.target.value) })} /></div>
            <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Produto</label>
              <EstoquePicker itens={estoque} value={e.produto} onChange={(v) => atualizarEtapa(idx, { produto: v })} /></div>
            <div><label style={labelStyle}>Dosagem</label><input type="number" inputMode="decimal" style={inputStyle} value={e.dosagem} onChange={(ev) => atualizarEtapa(idx, { dosagem: Number(ev.target.value) })} /></div>
            <div><label style={labelStyle}>Unidade</label><input style={inputStyle} value={e.unidade} onChange={(ev) => atualizarEtapa(idx, { unidade: ev.target.value })} placeholder="ml" /></div>
            <div className="flex items-end gap-1">
              <div style={{ flex: 1 }}><label style={labelStyle}>Via</label>
                <select style={inputStyle} value={e.via || ""} onChange={(ev) => atualizarEtapa(idx, { via: ev.target.value })}>
                  <option value="">—</option>{VIAS_APLICACAO.map((v) => <option key={v}>{v}</option>)}
                </select></div>
              {form.etapas.length > 1 && <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => removerEtapa(idx)}><Trash2 size={13} /></button>}
            </div>
          </div>
        ))}
      </div>
      <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", marginBottom: "0.8rem" }} onClick={acrescentarEtapa}>
        <Plus size={14} /> Acrescentar etapa
      </button>

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
