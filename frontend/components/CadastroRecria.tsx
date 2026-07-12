"use client";
// Configurações > Cadastro > Recria — parâmetros do Dossiê Zootécnico:
// metas gerenciais, curva de peso-alvo por idade, fases de idade (coorte) e
// janelas de ponto crítico por doença. Pensado para ser simples de operar.
import { useEffect, useState } from "react";
import { Baby, Check, Trash2, Plus } from "lucide-react";
import {
  fetchRecriaMetas, salvarRecriaMetas, fetchRecriaPesoAlvo, salvarRecriaPesoAlvo, excluirRecriaPesoAlvo,
  fetchRecriaFases, criarRecriaFase, excluirRecriaFase, fetchRecriaJanelas, criarRecriaJanela, excluirRecriaJanela,
  type RecriaMetas, type RecriaPesoAlvo, type RecriaFase, type RecriaJanela,
} from "@/lib/api";

const input: React.CSSProperties = { padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem", background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)", width: "100%" };
const lbl: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.15rem" };
const card: React.CSSProperties = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "1rem 1.1rem" };
const secTit: React.CSSProperties = { fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.7rem", display: "flex", alignItems: "center", gap: 6 };

export default function CadastroRecria() {
  return (
    <div style={{ display: "grid", gap: "1.2rem" }}>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", margin: 0 }}>
        Parâmetros do <strong>Dossiê Zootécnico</strong> (aba Recria). Ajuste as metas, a faixa de peso esperada por idade, as fases e as janelas de ponto crítico.
      </p>
      <SecMetas />
      <SecPesoAlvo />
      <SecFases />
      <SecJanelas />
    </div>
  );
}

function SecMetas() {
  const [m, setM] = useState<RecriaMetas | null>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => { fetchRecriaMetas().then(setM).catch(() => {}); }, []);
  if (!m) return null;
  const campo = (k: keyof RecriaMetas, label: string) => (
    <div><label style={lbl}>{label}</label><input type="number" step="0.1" style={input} value={m[k]} onChange={(e) => setM({ ...m, [k]: Number(e.target.value) })} /></div>
  );
  return (
    <div style={card}>
      <div style={secTit}><Baby size={15} /> Metas da recria</div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {campo("idade_parto_meses", "Idade ao parto (meses)")}
        {campo("idade_prenhez_meses", "Idade à prenhez (meses)")}
        {campo("idade_1a_cobertura_meses", "Idade à 1ª cobertura (meses)")}
        {campo("taxa_prenhez_meta", "Meta taxa de prenhez (%)")}
        {campo("desvio_padrao_meta", "Meta desvio-padrão (meses)")}
        {campo("custo_diario_recria", "Custo diário de recria (R$)")}
      </div>
      <div className="flex items-center gap-3 mt-3">
        <button className="btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          onClick={() => { salvarRecriaMetas(m).then(() => setMsg("Metas salvas.")).catch((e) => setMsg(e.message)); }}>
          <Check size={14} /> Salvar metas
        </button>
        {msg && <span style={{ fontSize: "0.8rem", color: "var(--green-light)" }}>{msg}</span>}
      </div>
    </div>
  );
}

function SecPesoAlvo() {
  const [lista, setLista] = useState<RecriaPesoAlvo[]>([]);
  const [form, setForm] = useState<RecriaPesoAlvo>({ mes: 1, peso_min_kg: 0, peso_max_kg: 0 });
  const [erro, setErro] = useState("");
  const carregar = () => fetchRecriaPesoAlvo().then(setLista).catch(() => {});
  useEffect(() => { carregar(); }, []);
  const salvar = () => {
    setErro("");
    salvarRecriaPesoAlvo(form).then(() => { carregar(); }).catch((e) => setErro(e.message));
  };
  return (
    <div style={card}>
      <div style={secTit}>Curva de peso-alvo por idade</div>
      <div className="grid grid-cols-3 md:grid-cols-4 gap-3 items-end mb-3">
        <div><label style={lbl}>Mês de idade</label><input type="number" style={input} value={form.mes} onChange={(e) => setForm({ ...form, mes: Number(e.target.value) })} /></div>
        <div><label style={lbl}>Peso mín. (kg)</label><input type="number" style={input} value={form.peso_min_kg} onChange={(e) => setForm({ ...form, peso_min_kg: Number(e.target.value) })} /></div>
        <div><label style={lbl}>Peso máx. (kg)</label><input type="number" style={input} value={form.peso_max_kg} onChange={(e) => setForm({ ...form, peso_max_kg: Number(e.target.value) })} /></div>
        <button className="btn-primary" onClick={salvar} style={{ display: "inline-flex", alignItems: "center", gap: 6, justifyContent: "center" }}><Plus size={14} /> Salvar mês</button>
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
      <div style={{ overflowX: "auto" }}>
        <table className="fazenda-table">
          <thead><tr><th>Mês</th><th>Peso mín.</th><th>Peso máx.</th><th></th></tr></thead>
          <tbody>
            {lista.map((l) => (
              <tr key={l.mes}>
                <td style={{ fontWeight: 600 }}>{l.mes}º</td><td>{l.peso_min_kg} kg</td><td>{l.peso_max_kg} kg</td>
                <td style={{ textAlign: "right" }}><button className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem" }} onClick={() => excluirRecriaPesoAlvo(l.mes).then(carregar)}><Trash2 size={13} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SecFases() {
  const [lista, setLista] = useState<RecriaFase[]>([]);
  const [form, setForm] = useState<RecriaFase>({ nome: "", dia_min: 0, dia_max: 30, ordem: 0, ativo: true });
  const carregar = () => fetchRecriaFases().then(setLista).catch(() => {});
  useEffect(() => { carregar(); }, []);
  return (
    <div style={card}>
      <div style={secTit}>Fases de idade (agrupamento dos casos)</div>
      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "-0.3rem" }}>Se você não cadastrar nenhuma, o sistema usa faixas padrão.</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 items-end mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={lbl}>Nome da fase</label><input style={input} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: 30–60 dias" /></div>
        <div><label style={lbl}>Dia inicial</label><input type="number" style={input} value={form.dia_min} onChange={(e) => setForm({ ...form, dia_min: Number(e.target.value) })} /></div>
        <div><label style={lbl}>Dia final</label><input type="number" style={input} value={form.dia_max} onChange={(e) => setForm({ ...form, dia_max: Number(e.target.value) })} /></div>
      </div>
      <button className="btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginBottom: "0.7rem" }}
        onClick={() => { if (form.nome.trim()) criarRecriaFase(form).then(() => { setForm({ ...form, nome: "" }); carregar(); }); }}><Plus size={14} /> Adicionar fase</button>
      <div style={{ overflowX: "auto" }}>
        <table className="fazenda-table">
          <thead><tr><th>Fase</th><th>Faixa (dias)</th><th></th></tr></thead>
          <tbody>
            {lista.map((f) => (
              <tr key={f.id}><td style={{ fontWeight: 600 }}>{f.nome}</td><td>{f.dia_min}–{f.dia_max}</td>
                <td style={{ textAlign: "right" }}><button className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem" }} onClick={() => excluirRecriaFase(f.id!).then(carregar)}><Trash2 size={13} /></button></td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SecJanelas() {
  const [lista, setLista] = useState<RecriaJanela[]>([]);
  const [form, setForm] = useState<RecriaJanela>({ doenca: "", dia_min: 0, dia_max: 30, dias_antecedencia: 3, ativo: true });
  const carregar = () => fetchRecriaJanelas().then(setLista).catch(() => {});
  useEffect(() => { carregar(); }, []);
  return (
    <div style={card}>
      <div style={secTit}>Janelas de ponto crítico (por doença)</div>
      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "-0.3rem" }}>Faixa de idade de maior risco de cada doença — base para os alertas preventivos.</p>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={lbl}>Doença</label><input style={input} value={form.doenca} onChange={(e) => setForm({ ...form, doenca: e.target.value })} placeholder="ex.: Diarreia" /></div>
        <div><label style={lbl}>Dia inicial</label><input type="number" style={input} value={form.dia_min} onChange={(e) => setForm({ ...form, dia_min: Number(e.target.value) })} /></div>
        <div><label style={lbl}>Dia final</label><input type="number" style={input} value={form.dia_max} onChange={(e) => setForm({ ...form, dia_max: Number(e.target.value) })} /></div>
        <div><label style={lbl}>Antecedência (dias)</label><input type="number" style={input} value={form.dias_antecedencia} onChange={(e) => setForm({ ...form, dias_antecedencia: Number(e.target.value) })} /></div>
      </div>
      <button className="btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginBottom: "0.7rem" }}
        onClick={() => { if (form.doenca.trim()) criarRecriaJanela(form).then(() => { setForm({ ...form, doenca: "" }); carregar(); }); }}><Plus size={14} /> Adicionar janela</button>
      <div style={{ overflowX: "auto" }}>
        <table className="fazenda-table">
          <thead><tr><th>Doença</th><th>Janela (dias)</th><th>Antecedência</th><th></th></tr></thead>
          <tbody>
            {lista.map((j) => (
              <tr key={j.id}><td style={{ fontWeight: 600 }}>{j.doenca}</td><td>{j.dia_min}–{j.dia_max}</td><td>{j.dias_antecedencia} dias antes</td>
                <td style={{ textAlign: "right" }}><button className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem" }} onClick={() => excluirRecriaJanela(j.id!).then(carregar)}><Trash2 size={13} /></button></td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
