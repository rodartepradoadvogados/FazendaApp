"use client";
// Configurações > Cadastro > Pesagem do rebanho — acompanhamento da evolução de
// peso: cadastra a periodicidade de pesagem por fase (idade), num dia fixo da
// semana. Alimenta a Agenda dos funcionários com o lembrete no dia certo.
import { useEffect, useState } from "react";
import { Scale, Plus, Trash2, Check, X } from "lucide-react";
import {
  fetchAgendamentosPesagem, criarAgendamentoPesagem, atualizarAgendamentoPesagem, excluirAgendamentoPesagem,
  type AgendamentoPesagem,
} from "@/lib/api";

const DIAS_SEMANA = [
  { v: 0, l: "Segunda" }, { v: 1, l: "Terça" }, { v: 2, l: "Quarta" }, { v: 3, l: "Quinta" },
  { v: 4, l: "Sexta" }, { v: 5, l: "Sábado" }, { v: 6, l: "Domingo" },
];
const hoje = () => new Date().toISOString().slice(0, 10);

const input: React.CSSProperties = {
  padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem",
  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)", width: "100%",
};
const lbl: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.15rem" };

type Form = {
  nome: string; idade_min_dias: string; idade_max_dias: string;
  frequencia_valor: string; frequencia_unidade: string; dia_semana: number; data_referencia: string; ativo: boolean;
};
const vazio = (): Form => ({ nome: "", idade_min_dias: "", idade_max_dias: "", frequencia_valor: "15", frequencia_unidade: "dias", dia_semana: 1, data_referencia: hoje(), ativo: true });

// Modelos rápidos (as fases que o usuário citou).
const MODELOS: { nome: string; f: Partial<Form> }[] = [
  { nome: "Bezerras até desmama — 15/15 dias, terça", f: { nome: "Bezerras até desmama", idade_min_dias: "0", idade_max_dias: "90", frequencia_valor: "15", frequencia_unidade: "dias", dia_semana: 1 } },
  { nome: "Desmama — mensal, terça", f: { nome: "Desmama", idade_min_dias: "91", idade_max_dias: "240", frequencia_valor: "1", frequencia_unidade: "meses", dia_semana: 1 } },
  { nome: "Recria — a cada 2 meses, terça", f: { nome: "Recria", idade_min_dias: "241", idade_max_dias: "760", frequencia_valor: "2", frequencia_unidade: "meses", dia_semana: 1 } },
];

export default function CadastroPesagem() {
  const [lista, setLista] = useState<AgendamentoPesagem[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(vazio());
  const [editId, setEditId] = useState<number | null>(null);
  const [salvando, setSalvando] = useState(false);

  const carregar = () => fetchAgendamentosPesagem().then(setLista).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  const patch = (p: Partial<Form>) => setForm((f) => ({ ...f, ...p }));
  const editar = (a: AgendamentoPesagem) => {
    setEditId(a.id);
    setForm({
      nome: a.nome, idade_min_dias: a.idade_min_dias?.toString() ?? "", idade_max_dias: a.idade_max_dias?.toString() ?? "",
      frequencia_valor: String(a.frequencia_valor), frequencia_unidade: a.frequencia_unidade, dia_semana: a.dia_semana,
      data_referencia: a.data_referencia, ativo: a.ativo,
    });
  };
  const cancelar = () => { setEditId(null); setForm(vazio()); };

  async function salvar() {
    setErro(null);
    if (!form.nome.trim()) { setErro("Informe o nome da fase."); return; }
    setSalvando(true);
    const dados = {
      nome: form.nome.trim(), ativo: form.ativo,
      idade_min_dias: form.idade_min_dias === "" ? null : Number(form.idade_min_dias),
      idade_max_dias: form.idade_max_dias === "" ? null : Number(form.idade_max_dias),
      frequencia_valor: Number(form.frequencia_valor) || 1, frequencia_unidade: form.frequencia_unidade,
      dia_semana: form.dia_semana, data_referencia: form.data_referencia,
    };
    try {
      if (editId) await atualizarAgendamentoPesagem(editId, dados);
      else await criarAgendamentoPesagem(dados);
      cancelar(); carregar();
    } catch (e: any) { setErro(e.message); } finally { setSalvando(false); }
  }

  async function excluir(id: number) {
    if (!window.confirm("Excluir este agendamento de pesagem?")) return;
    try { await excluirAgendamentoPesagem(id); carregar(); } catch (e: any) { setErro(e.message); }
  }

  const descreveFreq = (a: AgendamentoPesagem) =>
    `a cada ${a.frequencia_valor} ${a.frequencia_unidade === "meses" ? (a.frequencia_valor === 1 ? "mês" : "meses") : "dias"}, ${DIAS_SEMANA.find((d) => d.v === a.dia_semana)?.l.toLowerCase()}`;
  const descreveIdade = (a: AgendamentoPesagem) =>
    a.idade_min_dias == null && a.idade_max_dias == null ? "todas as idades"
      : `${a.idade_min_dias ?? 0}–${a.idade_max_dias ?? "∞"} dias de idade`;

  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
        Acompanhamento da evolução de peso do rebanho. Cadastre a periodicidade de pesagem por fase (faixa de idade),
        num dia fixo da semana — os funcionários recebem o lembrete na <strong>Agenda</strong> no dia da pesagem.
      </p>

      {/* Modelos rápidos */}
      <div className="flex flex-wrap gap-2 mb-3">
        {MODELOS.map((m) => (
          <button key={m.nome} className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={() => { setEditId(null); setForm({ ...vazio(), ...m.f } as Form); }}>
            + {m.nome}
          </button>
        ))}
      </div>

      {/* Formulário */}
      <div className="card mb-4">
        <div className="card-header mb-2 flex items-center gap-2"><Scale size={15} /> {editId ? "Editar fase" : "Nova fase de pesagem"}</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div style={{ gridColumn: "span 2" }}><label style={lbl}>Nome da fase</label>
            <input style={input} value={form.nome} onChange={(e) => patch({ nome: e.target.value })} placeholder="ex.: Bezerras até desmama" /></div>
          <div><label style={lbl}>Idade mín. (dias)</label><input type="number" style={input} value={form.idade_min_dias} onChange={(e) => patch({ idade_min_dias: e.target.value })} placeholder="0" /></div>
          <div><label style={lbl}>Idade máx. (dias)</label><input type="number" style={input} value={form.idade_max_dias} onChange={(e) => patch({ idade_max_dias: e.target.value })} placeholder="90" /></div>
          <div><label style={lbl}>A cada</label><input type="number" style={input} value={form.frequencia_valor} onChange={(e) => patch({ frequencia_valor: e.target.value })} /></div>
          <div><label style={lbl}>Unidade</label>
            <select style={input} value={form.frequencia_unidade} onChange={(e) => patch({ frequencia_unidade: e.target.value })}>
              <option value="dias">dias</option><option value="meses">meses</option>
            </select></div>
          <div><label style={lbl}>Dia da semana</label>
            <select style={input} value={form.dia_semana} onChange={(e) => patch({ dia_semana: Number(e.target.value) })}>
              {DIAS_SEMANA.map((d) => <option key={d.v} value={d.v}>{d.l}</option>)}
            </select></div>
          <div><label style={lbl}>1ª pesagem (referência)</label><input type="date" style={input} value={form.data_referencia} onChange={(e) => patch({ data_referencia: e.target.value })} /></div>
        </div>
        <div className="flex items-center gap-3 mt-3">
          <label className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}><input type="checkbox" checked={form.ativo} onChange={(e) => patch({ ativo: e.target.checked })} /> Ativo</label>
          <button className="btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }} onClick={salvar} disabled={salvando}>
            <Check size={14} /> {salvando ? "Salvando…" : editId ? "Salvar alterações" : "Adicionar fase"}
          </button>
          {editId && <button className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={cancelar}><X size={13} /> Cancelar</button>}
        </div>
        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      </div>

      {/* Lista */}
      {!lista ? <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p> : lista.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma fase de pesagem cadastrada. Use um modelo rápido acima para começar.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Fase</th><th>Alvo (idade)</th><th>Periodicidade</th><th>Situação</th><th></th></tr></thead>
            <tbody>
              {lista.map((a) => (
                <tr key={a.id}>
                  <td style={{ fontWeight: 700 }}>{a.nome}</td>
                  <td style={{ fontSize: "0.8rem" }}>{descreveIdade(a)}</td>
                  <td style={{ fontSize: "0.8rem" }}>{descreveFreq(a)}</td>
                  <td><span style={{ fontSize: "0.72rem", fontWeight: 700, color: a.ativo ? "var(--green-light)" : "var(--text-muted)" }}>{a.ativo ? "Ativo" : "Inativo"}</span></td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => editar(a)}>Editar</button>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => excluir(a.id)}><Trash2 size={13} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
