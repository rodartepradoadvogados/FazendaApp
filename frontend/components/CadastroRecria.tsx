"use client";
// Configurações > Cadastro > Recria — parâmetros do Dossiê Zootécnico:
// metas gerenciais, curva de peso-alvo por idade, fases de idade (coorte) e
// janelas de ponto crítico por doença. Pensado para ser simples de operar.
import { useEffect, useState } from "react";
import { Baby, Check, Trash2, Plus } from "lucide-react";
import {
  fetchRecriaMetas, salvarRecriaMetas, fetchRecriaPesoAlvo, salvarRecriaPesoAlvo, excluirRecriaPesoAlvo,
  fetchRecriaFases, criarRecriaFase, excluirRecriaFase, fetchRecriaJanelas, criarRecriaJanela, excluirRecriaJanela,
  fetchRecriaBenchmark, salvarRecriaBenchmark,
  fetchCategoriasManejo, criarCategoriaManejo, atualizarCategoriaManejo, excluirCategoriaManejo, fetchComposicaoCategorias,
  type RecriaMetas, type RecriaPesoAlvo, type RecriaFase, type RecriaJanela, type RecriaBenchmark, type CategoriaManejo,
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
      <SecCategorias />
      <SecMetas />
      <SecPesoAlvo />
      <SecFases />
      <SecJanelas />
      <SecBenchmark />
    </div>
  );
}

function SecBenchmark() {
  const [lista, setLista] = useState<RecriaBenchmark[]>([]);
  const [msg, setMsg] = useState("");
  const carregar = () => fetchRecriaBenchmark().then(setLista).catch(() => {});
  useEffect(() => { carregar(); }, []);
  const set = (i: number, campo: keyof RecriaBenchmark, valor: any) =>
    setLista((ls) => ls.map((b, k) => (k === i ? { ...b, [campo]: valor === "" ? null : Number(valor) } : b)));
  return (
    <div style={card}>
      <div style={secTit}>Benchmark externo (Alta CRIA)</div>
      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "-0.3rem" }}>Percentis do setor por indicador e o valor atual da fazenda. Já vem preenchido com a Alta CRIA 2026.</p>
      <div style={{ overflowX: "auto" }}>
        <table className="fazenda-table">
          <thead><tr><th>Indicador</th><th>TOP 5%</th><th>TOP 25%</th><th>TOP 50%</th><th>TOP 75%</th><th>Fazenda</th><th></th></tr></thead>
          <tbody>
            {lista.map((b, i) => (
              <tr key={b.indicador}>
                <td style={{ fontWeight: 600, fontSize: "0.78rem" }}>{b.indicador} <span style={{ color: "var(--text-muted)" }}>({b.unidade})</span></td>
                <td><input type="number" style={{ ...input, width: 70 }} value={b.top5 ?? ""} onChange={(e) => set(i, "top5", e.target.value)} /></td>
                <td><input type="number" style={{ ...input, width: 70 }} value={b.top25 ?? ""} onChange={(e) => set(i, "top25", e.target.value)} /></td>
                <td><input type="number" style={{ ...input, width: 70 }} value={b.top50 ?? ""} onChange={(e) => set(i, "top50", e.target.value)} /></td>
                <td><input type="number" style={{ ...input, width: 70 }} value={b.top75 ?? ""} onChange={(e) => set(i, "top75", e.target.value)} /></td>
                <td><input type="number" style={{ ...input, width: 70 }} value={b.valor_fazenda ?? ""} onChange={(e) => set(i, "valor_fazenda", e.target.value)} /></td>
                <td><button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--dourado)" }}
                  onClick={() => salvarRecriaBenchmark(b).then(() => { setMsg(`${b.indicador} salvo.`); carregar(); }).catch((e) => setMsg(e.message))}>Salvar</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {msg && <p style={{ fontSize: "0.8rem", color: "var(--green-light)", marginTop: "0.5rem" }}>{msg}</p>}
    </div>
  );
}

const CATEGORIA_VAZIA: CategoriaManejo = {
  nome: "", dia_min: 0, dia_max: null, peso_min_kg: null, peso_max_kg: null, usa_status_reprodutivo: false,
  situacao_reprodutiva: null, situacao_produtiva: null,
  dias_gestacao_min: null, dias_gestacao_max: null,
  dias_desde_servico_min: null, dias_desde_servico_max: null,
  dias_para_parto_min: null, dias_para_parto_max: null,
  dias_pos_parto_min: null, dias_pos_parto_max: null,
  ordem: 0, ativo: true,
};

// Modelos prontos pedidos pela fazenda — clique para carregar no formulário
// acima (dá pra ajustar antes de salvar). Já vêm semeados no backend na
// primeira execução; os botões servem para recriar ou usar de referência.
const PRESETS_CATEGORIA: { label: string; descricao: string; dados: Partial<CategoriaManejo> }[] = [
  { label: "Recria atrasada", descricao: "≥ 391 dias de vida e < 370 kg", dados: { nome: "Recria atrasada", dia_min: 391, peso_max_kg: 369.99 } },
  { label: "Prenha", descricao: "Do diagnóstico positivo até o parto", dados: { nome: "Prenha", situacao_reprodutiva: "prenha" } },
  { label: "Em lactação", descricao: "Do parto até 61 dias faltando para o próximo parto", dados: { nome: "Em lactação", situacao_produtiva: "lactacao" } },
  { label: "Seca", descricao: "Entre 60 e 30 dias para o parto", dados: { nome: "Seca", dias_para_parto_min: 30, dias_para_parto_max: 60 } },
  { label: "Pré-parto", descricao: "30 dias ou menos para o parto", dados: { nome: "Pré-parto", dias_para_parto_max: 30 } },
  { label: "Pós-parto - PEV", descricao: "Do parto até 45 dias após o parto", dados: { nome: "Pós-parto - PEV", dias_pos_parto_max: 45 } },
  { label: "Liberada/apta", descricao: "Mais de 45 dias após o parto, vazia e não inseminada", dados: { nome: "Liberada/apta", situacao_reprodutiva: "vazia", dias_pos_parto_min: 46 } },
  { label: "Vazia atrasada", descricao: "Vazia, > 45 dias pós-parto e ≥ 30 dias sem novo serviço", dados: { nome: "Vazia atrasada", situacao_reprodutiva: "vazia", dias_pos_parto_min: 46, dias_desde_servico_min: 30 } },
  { label: "Inseminada", descricao: "Entre a data do serviço/monta e o diagnóstico reprodutivo", dados: { nome: "Inseminada", situacao_reprodutiva: "inseminada" } },
];

function SecCategorias() {
  const [lista, setLista] = useState<CategoriaManejo[]>([]);
  const [comp, setComp] = useState<{ categoria: string; n: number }[]>([]);
  const [form, setForm] = useState<CategoriaManejo>(CATEGORIA_VAZIA);
  const [editId, setEditId] = useState<number | null>(null);
  const carregar = () => { fetchCategoriasManejo().then(setLista).catch(() => {}); fetchComposicaoCategorias().then((d) => setComp(d.composicao)).catch(() => {}); };
  useEffect(() => { carregar(); }, []);
  const num = (v: string): number | null => v === "" ? null : Number(v);
  const salvar = () => {
    if (!form.nome.trim()) return;
    const p = editId ? atualizarCategoriaManejo(editId, form) : criarCategoriaManejo(form);
    p.then(() => { setForm({ ...CATEGORIA_VAZIA, ordem: lista.length }); setEditId(null); carregar(); });
  };
  const usarPreset = (dados: Partial<CategoriaManejo>) => { setEditId(null); setForm({ ...CATEGORIA_VAZIA, ordem: lista.length, ...dados }); };
  const resumoCriterios = (c: CategoriaManejo): string => {
    const partes: string[] = [];
    if (c.situacao_reprodutiva) partes.push(`sit. reprod.: ${c.situacao_reprodutiva}`);
    if (c.situacao_produtiva) partes.push(`sit. prod.: ${c.situacao_produtiva}`);
    if (c.dias_gestacao_min != null || c.dias_gestacao_max != null) partes.push(`gestação ${c.dias_gestacao_min ?? 0}–${c.dias_gestacao_max ?? "∞"}d`);
    if (c.dias_desde_servico_min != null || c.dias_desde_servico_max != null) partes.push(`desde serviço ${c.dias_desde_servico_min ?? 0}–${c.dias_desde_servico_max ?? "∞"}d`);
    if (c.dias_para_parto_min != null || c.dias_para_parto_max != null) partes.push(`p/ parto ${c.dias_para_parto_min ?? 0}–${c.dias_para_parto_max ?? "∞"}d`);
    if (c.dias_pos_parto_min != null || c.dias_pos_parto_max != null) partes.push(`pós-parto ${c.dias_pos_parto_min ?? 0}–${c.dias_pos_parto_max ?? "∞"}d`);
    return partes.join(" · ") || "—";
  };
  return (
    <div style={card}>
      <div style={secTit}><Baby size={15} /> Parâmetros de categoria</div>
      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "-0.3rem" }}>
        Cada categoria classifica o animal automaticamente cruzando idade, peso e (opcionalmente) situação reprodutiva/produtiva, dias de gestação, dias desde o último serviço, dias para o parto provável e dias pós-parto. Deixe um critério em branco para não filtrar por ele.
      </p>

      <p style={{ ...lbl, marginTop: "0.6rem" }}>Modelos prontos (clique para carregar no formulário abaixo)</p>
      <div className="flex flex-wrap gap-2 mb-3">
        {PRESETS_CATEGORIA.map((p) => (
          <button key={p.label} type="button" className="btn-ghost" title={p.descricao}
            style={{ fontSize: "0.74rem", border: "1px solid var(--border)", borderRadius: 999, padding: "0.3rem 0.7rem" }}
            onClick={() => usarPreset(p.dados)}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-2 items-end mb-2">
        <div style={{ gridColumn: "span 2" }}><label style={lbl}>Nome</label><input style={input} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Recria 1" /></div>
        <div><label style={lbl}>Dia mín.</label><input type="number" style={input} value={form.dia_min} onChange={(e) => setForm({ ...form, dia_min: Number(e.target.value) })} /></div>
        <div><label style={lbl}>Dia máx.</label><input type="number" style={input} value={form.dia_max ?? ""} onChange={(e) => setForm({ ...form, dia_max: num(e.target.value) })} placeholder="∞" /></div>
        <div><label style={lbl}>Peso mín. (kg)</label><input type="number" style={input} value={form.peso_min_kg ?? ""} onChange={(e) => setForm({ ...form, peso_min_kg: num(e.target.value) })} /></div>
        <div><label style={lbl}>Peso máx. (kg)</label><input type="number" style={input} value={form.peso_max_kg ?? ""} onChange={(e) => setForm({ ...form, peso_max_kg: num(e.target.value) })} /></div>
      </div>

      <p style={{ ...lbl, marginTop: "0.3rem" }}>Critérios adicionais (opcionais)</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 items-end mb-2">
        <div>
          <label style={lbl}>Situação reprodutiva</label>
          <select style={input} value={form.situacao_reprodutiva ?? ""} onChange={(e) => setForm({ ...form, situacao_reprodutiva: (e.target.value || null) as CategoriaManejo["situacao_reprodutiva"] })}>
            <option value="">— não filtra —</option>
            <option value="vazia">Vazia</option>
            <option value="inseminada">Inseminada</option>
            <option value="prenha">Prenha</option>
          </select>
        </div>
        <div>
          <label style={lbl}>Situação produtiva</label>
          <select style={input} value={form.situacao_produtiva ?? ""} onChange={(e) => setForm({ ...form, situacao_produtiva: (e.target.value || null) as CategoriaManejo["situacao_produtiva"] })}>
            <option value="">— não filtra —</option>
            <option value="lactacao">Em lactação</option>
            <option value="seca">Seca</option>
          </select>
        </div>
        <div><label style={lbl}>Dias de gestação mín.</label><input type="number" style={input} value={form.dias_gestacao_min ?? ""} onChange={(e) => setForm({ ...form, dias_gestacao_min: num(e.target.value) })} /></div>
        <div><label style={lbl}>Dias de gestação máx.</label><input type="number" style={input} value={form.dias_gestacao_max ?? ""} onChange={(e) => setForm({ ...form, dias_gestacao_max: num(e.target.value) })} /></div>
        <div><label style={lbl}>Dias desde último serviço mín.</label><input type="number" style={input} value={form.dias_desde_servico_min ?? ""} onChange={(e) => setForm({ ...form, dias_desde_servico_min: num(e.target.value) })} /></div>
        <div><label style={lbl}>Dias desde último serviço máx.</label><input type="number" style={input} value={form.dias_desde_servico_max ?? ""} onChange={(e) => setForm({ ...form, dias_desde_servico_max: num(e.target.value) })} /></div>
        <div><label style={lbl}>Dias para o parto provável mín.</label><input type="number" style={input} value={form.dias_para_parto_min ?? ""} onChange={(e) => setForm({ ...form, dias_para_parto_min: num(e.target.value) })} /></div>
        <div><label style={lbl}>Dias para o parto provável máx.</label><input type="number" style={input} value={form.dias_para_parto_max ?? ""} onChange={(e) => setForm({ ...form, dias_para_parto_max: num(e.target.value) })} /></div>
        <div><label style={lbl}>Dias pós-parto mín.</label><input type="number" style={input} value={form.dias_pos_parto_min ?? ""} onChange={(e) => setForm({ ...form, dias_pos_parto_min: num(e.target.value) })} /></div>
        <div><label style={lbl}>Dias pós-parto máx.</label><input type="number" style={input} value={form.dias_pos_parto_max ?? ""} onChange={(e) => setForm({ ...form, dias_pos_parto_max: num(e.target.value) })} /></div>
        <div><label style={lbl}>Ordem de prioridade</label><input type="number" style={input} value={form.ordem} onChange={(e) => setForm({ ...form, ordem: Number(e.target.value) })} /></div>
      </div>

      <label className="flex items-center gap-2 mb-2" style={{ fontSize: "0.8rem" }}>
        <input type="checkbox" checked={form.usa_status_reprodutivo} onChange={(e) => setForm({ ...form, usa_status_reprodutivo: e.target.checked })} /> Categoria de aptidão legada (usa status reprodutivo Apta/Inseminada/Gestante)
      </label>
      <div className="flex items-center gap-2 mb-3">
        <button className="btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: 6 }} onClick={salvar}><Check size={14} /> {editId ? "Salvar" : "Adicionar categoria"}</button>
        {editId && <button className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={() => { setEditId(null); setForm(CATEGORIA_VAZIA); }}>Cancelar</button>}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="fazenda-table">
          <thead><tr><th>Categoria</th><th>Idade (dias)</th><th>Peso (kg)</th><th>Outros critérios</th><th>Animais hoje</th><th></th></tr></thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.id}>
                <td style={{ fontWeight: 600 }}>{c.nome}</td>
                <td>{c.dia_min}–{c.dia_max ?? "∞"}</td>
                <td>{c.peso_min_kg ?? "—"}{c.peso_max_kg ? `–${c.peso_max_kg}` : ""}</td>
                <td style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{c.usa_status_reprodutivo ? "Aptidão legada (Apta/Inseminada/Gestante)" : resumoCriterios(c)}</td>
                <td>{comp.filter((x) => x.categoria === c.nome || (c.usa_status_reprodutivo && ["Apta", "Inseminada", "Gestante"].includes(x.categoria))).reduce((a, b) => a + b.n, 0) || 0}</td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => { setEditId(c.id!); setForm(c); }}>Editar</button>
                  <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => excluirCategoriaManejo(c.id!).then(carregar)}><Trash2 size={13} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {comp.length > 0 && (
        <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Composição atual: {comp.map((x) => `${x.categoria} (${x.n})`).join(" · ")}
        </p>
      )}
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
