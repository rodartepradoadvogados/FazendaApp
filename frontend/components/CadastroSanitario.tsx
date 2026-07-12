"use client";
import { Fragment, useEffect, useState } from "react";
import { Syringe, Bug, CalendarClock, ClipboardList, Plus, Pencil, AlertTriangle, Check, X, Trash2, Search } from "lucide-react";
import {
  fetchPrincipiosAtivos, criarPrincipioAtivo, atualizarPrincipioAtivo,
  fetchDoencas, criarDoenca, atualizarDoenca,
  fetchEventosSanitarios, criarEventoSanitario, atualizarEventoSanitario,
  fetchProtocolosSanitarios, criarProtocoloSanitario, atualizarProtocoloSanitario,
  fetchEstoque, fetchLotes,
  type ProtocoloEtapa, type EventoSanitarioPayload,
} from "@/lib/api";
import { EstoquePicker, type EstoqueItemPicker } from "./EstoquePicker";
import { VIAS_APLICACAO } from "@/lib/constants";
import { CLASSIFICACOES_MEDICAMENTO } from "@/lib/api";

const CRITERIOS: [string, string][] = [
  ["medicamento", "Medicamento"],
  ["principio_ativo", "Princípio ativo"],
  ["classificacao", "Classificação"],
];

// Unidades para a etapa do protocolo — restringidas às compatíveis com a
// unidade de estoque do produto (para a baixa automática funcionar). Sem
// produto/estoque, oferece a lista padrão.
const UNIDADES_PADRAO = ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"];
const GRUPOS_UNIDADE = [["ml", "unidade", "dose"], ["L", "kg"]];
const unidadesCompat = (u?: string | null): string[] =>
  !u ? UNIDADES_PADRAO : (GRUPOS_UNIDADE.find((g) => g.includes(u)) || [u]);

const ABAS = [
  ["principios", "Princípio ativo", Syringe],
  ["doencas", "Doença", Bug],
  ["eventos", "Evento sanitário", CalendarClock],
  ["protocolos", "Protocolo sanitário", ClipboardList],
] as const;

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

// Normaliza texto para busca insensível a maiúsculas e acentos.
const normalizar = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

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
      {aba === "eventos" && <CadastroEventosSanitarios />}
      {aba === "protocolos" && <CadastroProtocolosSanitarios />}
    </div>
  );
}

type Protocolo = {
  id: number; nome: string; doenca_id: number | null; doenca_nome: string | null; eh_mastite: boolean; ativo: boolean;
  etapas: ProtocoloEtapa[];
};
type ProtocoloForm = { nome: string; doenca_id: string; eh_mastite: boolean; ativo: boolean; etapas: ProtocoloEtapa[] };
const etapaVazia = (dia: number): ProtocoloEtapa => ({ dia, criterio_tipo: "medicamento", produto: "", dosagem: 0, unidade: "ml", via: "" });
const protocoloFormVazio = (): ProtocoloForm => ({ nome: "", doenca_id: "", eh_mastite: false, ativo: true, etapas: [etapaVazia(1)] });

function CadastroProtocolosSanitarios() {
  const [itens, setItens] = useState<Protocolo[] | null>(null);
  const [doencas, setDoencas] = useState<{ id: number; nome: string }[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItemPicker[]>([]);
  const [principios, setPrincipios] = useState<{ id: number; nome: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<ProtocoloForm>(protocoloFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  const carregar = () => fetchProtocolosSanitarios().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchDoencas().then(setDoencas).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
    fetchPrincipiosAtivos().then(setPrincipios).catch(() => {});
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

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((p) =>
    !termoBusca || normalizar(`${p.nome} ${p.doenca_nome ?? ""}`).includes(termoBusca)
  );

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
          form={form} setForm={setForm} doencas={doencas} estoque={estoque} principios={principios} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
          acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
        />
      )}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar protocolo…" title="Buscar por nome ou doença" />
          </div>
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Nome</th><th>Doença</th><th>Mastite</th><th>Etapas</th><th></th></tr></thead>
            <tbody>
              {filtrados.map((p) => (
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
                        form={form} setForm={setForm} doencas={doencas} estoque={estoque} principios={principios} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                        acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
                      />
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo cadastrado ainda.</td></tr>}
              {!!itens.length && !filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
      )}
    </div>
  );
}

function FormProtocolo({ form, setForm, doencas, estoque, principios, onSalvar, onCancelar, salvando, msg, acrescentarEtapa, removerEtapa, atualizarEtapa }: {
  form: ProtocoloForm; setForm: (f: ProtocoloForm) => void; doencas: { id: number; nome: string }[]; estoque: EstoqueItemPicker[];
  principios: { id: number; nome: string }[];
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
          <div key={idx} className="grid grid-cols-2 md:grid-cols-7 gap-2 items-end" style={{ background: "var(--surface)", padding: "0.5rem", borderRadius: "6px" }}>
            <div><label style={labelStyle}>Dia (D)</label><input type="number" min={1} style={inputStyle} value={e.dia} onChange={(ev) => atualizarEtapa(idx, { dia: Number(ev.target.value) })} /></div>
            <div><label style={labelStyle}>Definir por</label>
              <select style={inputStyle} value={e.criterio_tipo || "medicamento"} onChange={(ev) => atualizarEtapa(idx, { criterio_tipo: ev.target.value, produto: "" })}>
                {CRITERIOS.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
              </select></div>
            <div style={{ gridColumn: "span 2" }}>
              <label style={labelStyle}>{(e.criterio_tipo || "medicamento") === "medicamento" ? "Medicamento" : (e.criterio_tipo === "principio_ativo" ? "Princípio ativo" : "Classificação")}</label>
              {(e.criterio_tipo || "medicamento") === "medicamento" ? (
                <EstoquePicker itens={estoque} value={e.produto} onChange={(v) => atualizarEtapa(idx, { produto: v })} />
              ) : e.criterio_tipo === "principio_ativo" ? (
                <select style={inputStyle} value={e.produto} onChange={(ev) => atualizarEtapa(idx, { produto: ev.target.value })}>
                  <option value="">Selecione…</option>{principios.map((p) => <option key={p.id} value={p.nome}>{p.nome}</option>)}
                </select>
              ) : (
                <select style={inputStyle} value={e.produto} onChange={(ev) => atualizarEtapa(idx, { produto: ev.target.value })}>
                  <option value="">Selecione…</option>{CLASSIFICACOES_MEDICAMENTO.map((cl) => <option key={cl} value={cl}>{cl}</option>)}
                </select>
              )}
            </div>
            <div><label style={labelStyle}>Dosagem</label><input type="number" inputMode="decimal" style={inputStyle} value={e.dosagem} onChange={(ev) => atualizarEtapa(idx, { dosagem: Number(ev.target.value) })} /></div>
            <div><label style={labelStyle}>Unidade</label>
              {(() => {
                const un = unidadesCompat(estoque.find((it) => it.nome === e.produto)?.unidade);
                return (
                  <select style={inputStyle} value={e.unidade} onChange={(ev) => atualizarEtapa(idx, { unidade: ev.target.value })}>
                    {!un.includes(e.unidade) && e.unidade && <option value={e.unidade}>{e.unidade}</option>}
                    {!e.unidade && <option value="">—</option>}
                    {un.map((u) => <option key={u} value={u}>{u}</option>)}
                  </select>
                );
              })()}
            </div>
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

// ─────────────────────── Evento sanitário (cadastro rico) ───────────────────────
const FREQ_UNIDADES = [["dias", "dia(s)"], ["meses", "mês(es)"], ["anos", "ano(s)"]] as const;
const GATILHOS: [string, string][] = [
  ["nascimento", "Nascimento (quando a cria nasce)"],
  ["entrada_lote", "Entrada num lote (ex.: pré-parto)"],
  ["novilha_apta", "Novilha atingir certa idade"],
  ["secagem", "Secagem"],
  ["parto", "Parto"],
];
const GATILHO_LABEL: Record<string, string> = Object.fromEntries(GATILHOS);

type EventoSanitarioRow = EventoSanitarioPayload & { id: number; doenca_nome?: string | null; proxima_ocorrencia?: string | null };
type EventoForm = {
  nome: string; ativo: boolean; tipo_agendamento: "nenhum" | "epoca" | "evento";
  categoria_alvo: string; doenca_id: string;
  data_primeiro: string; frequencia_valor: string; frequencia_unidade: string;
  gatilho: string; gatilho_lote: string; gatilho_idade_meses: string; offset_dias: string;
  produto_padrao: string; dose_padrao: string; unidade_padrao: string; via_padrao: string;
};
const eventoFormVazio = (): EventoForm => ({
  nome: "", ativo: true, tipo_agendamento: "nenhum", categoria_alvo: "", doenca_id: "",
  data_primeiro: "", frequencia_valor: "", frequencia_unidade: "meses",
  gatilho: "nascimento", gatilho_lote: "", gatilho_idade_meses: "", offset_dias: "",
  produto_padrao: "", dose_padrao: "", unidade_padrao: "", via_padrao: "",
});

function CadastroEventosSanitarios() {
  const [itens, setItens] = useState<EventoSanitarioRow[] | null>(null);
  const [doencas, setDoencas] = useState<{ id: number; nome: string }[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItemPicker[]>([]);
  const [lotes, setLotes] = useState<{ codigo: string; nome?: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<EventoForm>(eventoFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  const carregar = () => fetchEventosSanitarios().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchDoencas().then(setDoencas).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
    fetchLotes().then(setLotes).catch(() => {});
  }, []);

  const abrirNovo = () => { setForm(eventoFormVazio()); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (e: EventoSanitarioRow) => {
    setForm({
      nome: e.nome, ativo: e.ativo ?? true, tipo_agendamento: (e.tipo_agendamento as any) || "nenhum",
      categoria_alvo: e.categoria_alvo || "", doenca_id: e.doenca_id ? String(e.doenca_id) : "",
      data_primeiro: e.data_primeiro || "", frequencia_valor: e.frequencia_valor ? String(e.frequencia_valor) : "",
      frequencia_unidade: e.frequencia_unidade || "meses", gatilho: e.gatilho || "nascimento",
      gatilho_lote: e.gatilho_lote || "", gatilho_idade_meses: e.gatilho_idade_meses ? String(e.gatilho_idade_meses) : "",
      offset_dias: e.offset_dias ? String(e.offset_dias) : "",
      produto_padrao: e.produto_padrao || "", dose_padrao: e.dose_padrao != null ? String(e.dose_padrao) : "",
      unidade_padrao: e.unidade_padrao || "", via_padrao: e.via_padrao || "",
    });
    setEditando(e.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    const dados: EventoSanitarioPayload = {
      nome: form.nome.trim(), ativo: form.ativo, tipo_agendamento: form.tipo_agendamento,
      categoria_alvo: form.categoria_alvo.trim() || null, doenca_id: form.doenca_id ? Number(form.doenca_id) : null,
      data_primeiro: form.tipo_agendamento === "epoca" && form.data_primeiro ? form.data_primeiro : null,
      frequencia_valor: form.tipo_agendamento === "epoca" && form.frequencia_valor ? Number(form.frequencia_valor) : null,
      frequencia_unidade: form.tipo_agendamento === "epoca" ? form.frequencia_unidade : null,
      gatilho: form.tipo_agendamento === "evento" ? form.gatilho : null,
      gatilho_lote: form.tipo_agendamento === "evento" && form.gatilho === "entrada_lote" ? form.gatilho_lote || null : null,
      gatilho_idade_meses: form.tipo_agendamento === "evento" && form.gatilho === "novilha_apta" && form.gatilho_idade_meses ? Number(form.gatilho_idade_meses) : null,
      offset_dias: form.tipo_agendamento === "evento" && form.offset_dias ? Number(form.offset_dias) : null,
      produto_padrao: form.produto_padrao.trim() || null, dose_padrao: form.dose_padrao ? Number(form.dose_padrao) : null,
      unidade_padrao: form.unidade_padrao || null, via_padrao: form.via_padrao || null,
    };
    setSalvando(true); setMsg(null);
    try {
      if (editando === "novo") await criarEventoSanitario(dados);
      else if (typeof editando === "number") await atualizarEventoSanitario(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) { setMsg(e.message || "Erro ao salvar"); }
    finally { setSalvando(false); }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((e) => !termoBusca || normalizar(e.nome).includes(termoBusca));
  const unidadesProduto = unidadesCompat(estoque.find((it) => it.nome === form.produto_padrao)?.unidade);

  const rotuloAgendamento = (e: EventoSanitarioRow) => {
    if (e.tipo_agendamento === "epoca")
      return `A cada ${e.frequencia_valor} ${FREQ_UNIDADES.find((f) => f[0] === e.frequencia_unidade)?.[1] || e.frequencia_unidade}`;
    if (e.tipo_agendamento === "evento")
      return `Por evento: ${GATILHO_LABEL[e.gatilho || ""] || e.gatilho}${e.gatilho === "entrada_lote" && e.gatilho_lote ? ` (${e.gatilho_lote})` : ""}`;
    return "—";
  };

  const formEl = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome do evento</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder='ex.: "Vacina pré-parto", "Vermífugo"' /></div>
        <div><label style={labelStyle}>Doença combatida</label>
          <select style={inputStyle} value={form.doenca_id} onChange={(e) => setForm({ ...form, doenca_id: e.target.value })}>
            <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
          </select></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>

      <label style={labelStyle}>Quando repetir</label>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        {([["nenhum", "Só o nome"], ["epoca", "Por época (recorrência)"], ["evento", "Por evento de vida"]] as const).map(([v, lbl]) => (
          <button key={v} type="button" onClick={() => setForm({ ...form, tipo_agendamento: v })}
            style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
              border: "1px solid " + (form.tipo_agendamento === v ? "var(--dourado)" : "var(--border)"),
              background: form.tipo_agendamento === v ? "rgba(94,26,46,0.4)" : "transparent",
              color: form.tipo_agendamento === v ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: form.tipo_agendamento === v ? 700 : 500 }}>
            {lbl}
          </button>
        ))}
      </div>

      {form.tipo_agendamento === "epoca" && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyle}>Data do 1º evento</label>
            <input type="date" style={inputStyle} value={form.data_primeiro} onChange={(e) => setForm({ ...form, data_primeiro: e.target.value })} /></div>
          <div><label style={labelStyle}>A cada</label>
            <input type="number" min={1} style={inputStyle} value={form.frequencia_valor} onChange={(e) => setForm({ ...form, frequencia_valor: e.target.value })} placeholder="6" /></div>
          <div><label style={labelStyle}>Período</label>
            <select style={inputStyle} value={form.frequencia_unidade} onChange={(e) => setForm({ ...form, frequencia_unidade: e.target.value })}>
              {FREQ_UNIDADES.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
            </select></div>
          <div><label style={labelStyle}>Categoria-alvo (opcional)</label>
            <input style={inputStyle} value={form.categoria_alvo} onChange={(e) => setForm({ ...form, categoria_alvo: e.target.value })} placeholder="ex.: Bezerras" /></div>
        </div>
      )}

      {form.tipo_agendamento === "evento" && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Gatilho</label>
            <select style={inputStyle} value={form.gatilho} onChange={(e) => setForm({ ...form, gatilho: e.target.value })}>
              {GATILHOS.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
            </select></div>
          {form.gatilho === "entrada_lote" && (
            <div><label style={labelStyle}>Lote</label>
              <select style={inputStyle} value={form.gatilho_lote} onChange={(e) => setForm({ ...form, gatilho_lote: e.target.value })}>
                <option value="">Selecione…</option>
                {lotes.map((l) => <option key={l.codigo} value={l.codigo}>{l.codigo}{l.nome ? ` — ${l.nome}` : ""}</option>)}
              </select></div>
          )}
          {form.gatilho === "novilha_apta" && (
            <div><label style={labelStyle}>Idade-alvo (meses)</label>
              <input type="number" min={1} style={inputStyle} value={form.gatilho_idade_meses} onChange={(e) => setForm({ ...form, gatilho_idade_meses: e.target.value })} placeholder="ex.: 13" /></div>
          )}
          <div><label style={labelStyle}>Dias após o gatilho</label>
            <input type="number" min={0} style={inputStyle} value={form.offset_dias} onChange={(e) => setForm({ ...form, offset_dias: e.target.value })} placeholder="0" /></div>
        </div>
      )}

      {form.tipo_agendamento !== "nenhum" && (
        <>
          <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Medicamento padrão (editável na hora da baixa)</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Produto</label>
              <EstoquePicker itens={estoque} value={form.produto_padrao} onChange={(v) => setForm({ ...form, produto_padrao: v, unidade_padrao: unidadesCompat(estoque.find((it) => it.nome === v)?.unidade)[0] || form.unidade_padrao })} /></div>
            <div><label style={labelStyle}>Dose</label>
              <input type="number" inputMode="decimal" style={inputStyle} value={form.dose_padrao} onChange={(e) => setForm({ ...form, dose_padrao: e.target.value })} /></div>
            <div><label style={labelStyle}>Unidade</label>
              <select style={inputStyle} value={form.unidade_padrao} onChange={(e) => setForm({ ...form, unidade_padrao: e.target.value })}>
                <option value="">—</option>
                {!unidadesProduto.includes(form.unidade_padrao) && form.unidade_padrao && <option value={form.unidade_padrao}>{form.unidade_padrao}</option>}
                {unidadesProduto.map((u) => <option key={u} value={u}>{u}</option>)}
              </select></div>
            <div><label style={labelStyle}>Via</label>
              <select style={inputStyle} value={form.via_padrao} onChange={(e) => setForm({ ...form, via_padrao: e.target.value })}>
                <option value="">—</option>{VIAS_APLICACAO.map((v) => <option key={v}>{v}</option>)}
              </select></div>
          </div>
        </>
      )}

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
        <span className="flex items-center gap-2"><CalendarClock size={16} /> Eventos sanitários</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Nome da vacina/manejo do calendário sanitário. Defina <strong>quando repetir</strong> — por época (a cada X dias/meses)
        ou por evento de vida (nascimento, entrada num lote como pré-parto, aptidão de novilha…) — e o medicamento padrão.
        Isso alimenta a <strong>Agenda</strong>: ao dar baixa, a aplicação e a saída de estoque são geradas (com o remédio editável na hora).
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && formEl}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar evento sanitário…" />
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Nome</th><th>Agendamento</th><th>Medicamento padrão</th><th>Próxima</th><th></th></tr></thead>
              <tbody>
                {filtrados.map((e) => (
                  <Fragment key={e.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{e.nome}{!e.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                      <td style={{ fontSize: "0.78rem" }}>{rotuloAgendamento(e)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{e.produto_padrao ? `${e.produto_padrao}${e.dose_padrao != null ? ` — ${e.dose_padrao} ${e.unidade_padrao || ""}` : ""}` : "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--dourado-light)" }}>{e.proxima_ocorrencia ? new Date(e.proxima_ocorrencia + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td style={{ textAlign: "right" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(e)}>
                          <Pencil size={13} /> Editar
                        </button>
                      </td>
                    </tr>
                    {editando === e.id && <tr><td colSpan={5} style={{ padding: 0 }}>{formEl}</td></tr>}
                  </Fragment>
                ))}
                {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum evento sanitário cadastrado ainda.</td></tr>}
                {!!itens.length && !filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
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
  const [busca, setBusca] = useState("");

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

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((i) => !termoBusca || normalizar(i.nome).includes(termoBusca));

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
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder={`Buscar em ${titulo.toLowerCase()}…`} title="Buscar por nome" />
          </div>
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Nome</th><th></th></tr></thead>
            <tbody>
              {filtrados.map((i) => (
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
              {!!itens.length && !filtrados.length && <tr><td colSpan={2} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
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
