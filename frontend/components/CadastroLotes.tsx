"use client";
import { Fragment, useEffect, useState } from "react";
import { Layers, Plus, Pencil, AlertTriangle, Check, X, Users, CalendarClock, ArrowUpRight, Power, PowerOff } from "lucide-react";
import {
  fetchLotes, criarLote, atualizarLote, previewCriteriosLote, fetchAnimais, fetchCategoriasManejo, criarMovimentacao,
  fetchParametroAgendamentoMovimentacao, salvarParametroAgendamentoMovimentacao, type ParametroAgendamentoMovimentacao,
  type CategoriaManejo,
} from "@/lib/api";
import { Modal } from "@/components/Modal";

const DIAS_SEMANA = [
  { v: 0, l: "Segunda" }, { v: 1, l: "Terça" }, { v: 2, l: "Quarta" }, { v: 3, l: "Quinta" },
  { v: 4, l: "Sexta" }, { v: 5, l: "Sábado" }, { v: 6, l: "Domingo" },
];

type Lote = {
  id: number; codigo: string; nome: string; rotulo: string; qtd_animais: number;
  del_min: number | null; del_max: number | null; producao_min: number | null; producao_max: number | null;
  status_lactacao: string | null; situacao_reprodutiva: string | null; categorias: string | null; pre_parto: boolean | null;
  peso_min: number | null; peso_max: number | null;
  dias_para_parto_min: number | null; dias_para_parto_max: number | null;
  dias_gestacao_min: number | null; dias_gestacao_max: number | null;
  dias_desde_servico_min: number | null; dias_desde_servico_max: number | null;
  em_tratamento: boolean | null; idade_dias_min: number | null; idade_dias_max: number | null;
  novilhas_inseminadas: boolean | null; novilhas_gestantes: boolean | null;
  categoria_manejo_ids: string | null; excluir_da_sugestao: boolean; ativo: boolean;
};

type Form = {
  codigo: string; nome: string; del_min: string; del_max: string; producao_min: string; producao_max: string;
  status_lactacao: string; situacao_reprodutiva: string; categorias: string[]; pre_parto: boolean;
  peso_min: string; peso_max: string;
  dias_para_parto_min: string; dias_para_parto_max: string;
  dias_gestacao_min: string; dias_gestacao_max: string;
  dias_desde_servico_min: string; dias_desde_servico_max: string;
  em_tratamento: boolean; idade_dias_min: string; idade_dias_max: string;
  novilhas_inseminadas: boolean; novilhas_gestantes: boolean;
  categoria_manejo_ids: number[];
  excluir_da_sugestao: boolean;
};

const formVazio: Form = {
  codigo: "", nome: "", del_min: "", del_max: "", producao_min: "", producao_max: "",
  status_lactacao: "", situacao_reprodutiva: "", categorias: [], pre_parto: false,
  peso_min: "", peso_max: "", dias_para_parto_min: "", dias_para_parto_max: "",
  dias_gestacao_min: "", dias_gestacao_max: "", dias_desde_servico_min: "", dias_desde_servico_max: "",
  em_tratamento: false, idade_dias_min: "", idade_dias_max: "",
  novilhas_inseminadas: false, novilhas_gestantes: false, categoria_manejo_ids: [],
  excluir_da_sugestao: false,
};

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

const rotuloSituacaoProdutiva = (v: string | null) => (v === "lactacao" ? "Em lactação" : v === "seca" ? "Seca" : "Ambas");
const rotuloSituacaoReprodutiva = (v: string | null) => (v === "vazia" ? "Vazia" : v === "inseminada" ? "Inseminada" : v === "prenha" ? "Prenha" : "Qualquer");
const rotuloCategorias = (v: string | null) => (v ? v.split(",").map((c) => c.trim()).filter(Boolean).map((c) => c[0].toUpperCase() + c.slice(1)).join(", ") : "—");

// Monta o payload que a API espera a partir do form (strings vazias -> null).
function paraPayload(form: Form, ativo: boolean = true) {
  const n = (v: string) => (v === "" ? null : Number(v));
  return {
    codigo: form.codigo.trim(),
    nome: form.nome.trim(),
    del_min: n(form.del_min), del_max: n(form.del_max),
    producao_min: n(form.producao_min), producao_max: n(form.producao_max),
    status_lactacao: form.status_lactacao || null,
    situacao_reprodutiva: form.situacao_reprodutiva || null,
    categorias: form.categorias.length ? form.categorias.join(",") : null,
    pre_parto: form.pre_parto || null,
    peso_min: n(form.peso_min), peso_max: n(form.peso_max),
    dias_para_parto_min: n(form.dias_para_parto_min), dias_para_parto_max: n(form.dias_para_parto_max),
    dias_gestacao_min: n(form.dias_gestacao_min), dias_gestacao_max: n(form.dias_gestacao_max),
    dias_desde_servico_min: n(form.dias_desde_servico_min), dias_desde_servico_max: n(form.dias_desde_servico_max),
    em_tratamento: form.em_tratamento || null,
    idade_dias_min: n(form.idade_dias_min), idade_dias_max: n(form.idade_dias_max),
    novilhas_inseminadas: form.novilhas_inseminadas || null,
    novilhas_gestantes: form.novilhas_gestantes || null,
    categoria_manejo_ids: form.categoria_manejo_ids.length ? form.categoria_manejo_ids.join(",") : null,
    excluir_da_sugestao: form.excluir_da_sugestao,
    ativo,
  };
}

// Reconstrói o payload completo a partir de um lote já cadastrado (para
// PUT parciais como inativar/reativar, que precisam reenviar tudo — o
// endpoint não faz patch, ele substitui os critérios inteiros).
function payloadDoLote(l: Lote, overrides: Partial<ReturnType<typeof paraPayload>> = {}) {
  return {
    codigo: l.codigo, nome: l.nome,
    del_min: l.del_min, del_max: l.del_max,
    producao_min: l.producao_min, producao_max: l.producao_max,
    status_lactacao: l.status_lactacao, situacao_reprodutiva: l.situacao_reprodutiva,
    categorias: l.categorias, pre_parto: l.pre_parto,
    peso_min: l.peso_min, peso_max: l.peso_max,
    dias_para_parto_min: l.dias_para_parto_min, dias_para_parto_max: l.dias_para_parto_max,
    dias_gestacao_min: l.dias_gestacao_min, dias_gestacao_max: l.dias_gestacao_max,
    dias_desde_servico_min: l.dias_desde_servico_min, dias_desde_servico_max: l.dias_desde_servico_max,
    em_tratamento: l.em_tratamento,
    idade_dias_min: l.idade_dias_min, idade_dias_max: l.idade_dias_max,
    novilhas_inseminadas: l.novilhas_inseminadas, novilhas_gestantes: l.novilhas_gestantes,
    categoria_manejo_ids: l.categoria_manejo_ids,
    excluir_da_sugestao: l.excluir_da_sugestao,
    ativo: l.ativo,
    ...overrides,
  };
}

export default function CadastroLotes() {
  const [lotes, setLotes] = useState<Lote[] | null>(null);
  const [categorias, setCategorias] = useState<CategoriaManejo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [parametroAgendamento, setParametroAgendamento] = useState<ParametroAgendamentoMovimentacao | null>(null);
  const [salvandoAgendamento, setSalvandoAgendamento] = useState(false);
  const [animaisQueAtendem, setAnimaisQueAtendem] = useState<string[] | null>(null); // popup da seta
  const [inativandoLote, setInativandoLote] = useState<Lote | null>(null); // assistente de transferência

  const carregar = () => fetchLotes({ incluirInativos: true }).then(setLotes).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);
  useEffect(() => { fetchParametroAgendamentoMovimentacao().then(setParametroAgendamento).catch(() => {}); }, []);
  useEffect(() => { fetchCategoriasManejo().then((c) => setCategorias(c.filter((x) => x.ativo))).catch(() => {}); }, []);

  async function salvarAgendamento(novo: ParametroAgendamentoMovimentacao) {
    setParametroAgendamento(novo);
    setSalvandoAgendamento(true);
    try {
      await salvarParametroAgendamentoMovimentacao(novo);
    } catch {
      // silencioso — o select volta ao valor salvo no próximo carregamento
    } finally {
      setSalvandoAgendamento(false);
    }
  }

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (l: Lote) => {
    setForm({
      codigo: l.codigo, nome: l.nome,
      del_min: l.del_min?.toString() ?? "", del_max: l.del_max?.toString() ?? "",
      producao_min: l.producao_min?.toString() ?? "", producao_max: l.producao_max?.toString() ?? "",
      status_lactacao: l.status_lactacao ?? "", situacao_reprodutiva: l.situacao_reprodutiva ?? "",
      categorias: l.categorias ? l.categorias.split(",") : [],
      pre_parto: !!l.pre_parto,
      peso_min: l.peso_min?.toString() ?? "", peso_max: l.peso_max?.toString() ?? "",
      dias_para_parto_min: l.dias_para_parto_min?.toString() ?? "", dias_para_parto_max: l.dias_para_parto_max?.toString() ?? "",
      dias_gestacao_min: l.dias_gestacao_min?.toString() ?? "", dias_gestacao_max: l.dias_gestacao_max?.toString() ?? "",
      dias_desde_servico_min: l.dias_desde_servico_min?.toString() ?? "", dias_desde_servico_max: l.dias_desde_servico_max?.toString() ?? "",
      em_tratamento: !!l.em_tratamento,
      idade_dias_min: l.idade_dias_min?.toString() ?? "", idade_dias_max: l.idade_dias_max?.toString() ?? "",
      novilhas_inseminadas: !!l.novilhas_inseminadas, novilhas_gestantes: !!l.novilhas_gestantes,
      categoria_manejo_ids: l.categoria_manejo_ids ? l.categoria_manejo_ids.split(",").map(Number).filter((n) => !Number.isNaN(n)) : [],
      excluir_da_sugestao: !!l.excluir_da_sugestao,
    });
    setEditando(l.id);
    setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.codigo.trim() || !form.nome.trim()) { setMsg("Código e nome são obrigatórios."); return; }
    // Preserva o ativo atual do lote em edição — este formulário mexe só nos
    // critérios; ativar/inativar é uma ação própria (botão na tabela).
    const loteAtual = typeof editando === "number" ? lotes?.find((l) => l.id === editando) : null;
    const dados = paraPayload(form, loteAtual ? loteAtual.ativo : true);
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

  async function abrirPreviewCompleto() {
    // Reaproveita a mesma prévia do form (só que aqui mostra a lista, não só o total).
    const r = await previewCriteriosLote(paraPayload(form));
    setAnimaisQueAtendem(r.animais || []);
  }

  async function inativar(lote: Lote) {
    if (!lote.qtd_animais) {
      await atualizarLote(lote.id, payloadDoLote(lote, { ativo: false }));
      await carregar();
      return;
    }
    setInativandoLote(lote);
  }
  async function reativar(lote: Lote) {
    await atualizarLote(lote.id, payloadDoLote(lote, { ativo: true }));
    await carregar();
  }

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

      {parametroAgendamento && (
        <div className="card mb-4">
          <div className="card-header mb-2 flex items-center gap-2">
            <CalendarClock size={16} style={{ color: "var(--dourado)" }} /> Agendamento das sugestões de movimentação
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Após um animal atingir o critério de mudança de lote (acima), a sugestão de troca aparece na Agenda:
          </p>
          <div className="flex items-center gap-4" style={{ flexWrap: "wrap" }}>
            <label className="flex items-center gap-2" style={{ fontSize: "0.82rem" }}>
              <input
                type="radio" checked={parametroAgendamento.modo === "na_data_parametro"}
                onChange={() => salvarAgendamento({ ...parametroAgendamento, modo: "na_data_parametro" })}
              />
              No próprio dia em que o animal passa a atender o parâmetro
            </label>
            <label className="flex items-center gap-2" style={{ fontSize: "0.82rem" }}>
              <input
                type="radio" checked={parametroAgendamento.modo === "dia_fixo_semana"}
                onChange={() => salvarAgendamento({ ...parametroAgendamento, modo: "dia_fixo_semana" })}
              />
              Em um dia fixo da semana
            </label>
            {parametroAgendamento.modo === "dia_fixo_semana" && (
              <select
                style={inputStyle} value={parametroAgendamento.dia_semana}
                onChange={(e) => salvarAgendamento({ ...parametroAgendamento, dia_semana: Number(e.target.value) })}
              >
                {DIAS_SEMANA.map((d) => <option key={d.v} value={d.v}>{d.l}</option>)}
              </select>
            )}
            {salvandoAgendamento && <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Salvando…</span>}
          </div>
        </div>
      )}

      {lotes && (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span>Lotes cadastrados</span>
            <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
              <Plus size={14} /> Novo lote
            </button>
          </div>

          {editando === "novo" && (
            <FormLote form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
              categorias={categorias} onAbrirPreviewCompleto={abrirPreviewCompleto} />
          )}

          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead>
                <tr>
                  {/* Ações à ESQUERDA — com a tabela larga demais pra caber
                      inteira na tela de um notebook, um botão só à direita
                      ficava escondido atrás da rolagem e parecia que não
                      dava pra editar. */}
                  <th></th>
                  <th>Código</th><th>Nome</th><th style={{ textAlign: "right" }}>Animais</th>
                  <th style={{ textAlign: "right" }}>Dias pós-parto mín.</th><th style={{ textAlign: "right" }}>Dias pós-parto máx.</th>
                  <th style={{ textAlign: "right" }}>Produção mín. (L)</th><th style={{ textAlign: "right" }}>Produção máx. (L)</th>
                  <th>Situação produtiva</th><th>Situação reprodutiva</th><th>Categoria</th>
                  <th style={{ textAlign: "right" }}>Falt. parto de</th><th style={{ textAlign: "right" }}>Falt. parto até</th>
                  <th style={{ textAlign: "right" }}>Peso de (kg)</th><th style={{ textAlign: "right" }}>Peso até (kg)</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {lotes.map((l) => (
                  <Fragment key={l.id}>
                    <tr style={!l.ativo ? { opacity: 0.55 } : undefined}>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <div className="flex items-center gap-1">
                          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(l)} title="Editar critérios do lote">
                            <Pencil size={13} /> Editar
                          </button>
                          {l.ativo ? (
                            <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--red)" }} onClick={() => inativar(l)} title="Inativar lote">
                              <PowerOff size={13} />
                            </button>
                          ) : (
                            <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--green-light)" }} onClick={() => reativar(l)} title="Reativar lote">
                              <Power size={13} />
                            </button>
                          )}
                        </div>
                      </td>
                      <td style={{ fontWeight: 700 }}>{l.codigo}</td>
                      <td>{l.nome}</td>
                      <td style={{ textAlign: "right" }}>{l.qtd_animais}</td>
                      <td style={{ textAlign: "right" }}>{l.del_min ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.del_max ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.producao_min ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.producao_max ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{rotuloSituacaoProdutiva(l.status_lactacao)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{rotuloSituacaoReprodutiva(l.situacao_reprodutiva)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{rotuloCategorias(l.categorias)}</td>
                      <td style={{ textAlign: "right" }}>{l.dias_para_parto_min ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.dias_para_parto_max ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.peso_min ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.peso_max ?? "—"}</td>
                      <td style={{ fontSize: "0.75rem" }}>
                        {l.ativo
                          ? <span style={{ color: "var(--green-light)" }}>Ativo</span>
                          : <span style={{ color: "var(--red)" }}>Inativo</span>}
                      </td>
                    </tr>
                    {editando === l.id && (
                      <tr>
                        <td colSpan={16} style={{ padding: 0 }}>
                          <FormLote form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                            categorias={categorias} onAbrirPreviewCompleto={abrirPreviewCompleto} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {!lotes.length && !editando && (
                  <tr><td colSpan={16} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum lote cadastrado ainda.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {animaisQueAtendem && (
        <Modal title={`${animaisQueAtendem.length} animal(is) que atendem aos critérios hoje`} onClose={() => setAnimaisQueAtendem(null)} width="420px">
          {animaisQueAtendem.length ? (
            <table className="fazenda-table">
              <thead><tr><th>Nº do animal</th></tr></thead>
              <tbody>{animaisQueAtendem.map((n) => <tr key={n}><td style={{ fontWeight: 700 }}>{n}</td></tr>)}</tbody>
            </table>
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum animal atende a esses critérios hoje.</p>
          )}
        </Modal>
      )}

      {inativandoLote && (
        <InativarLoteWizard
          lote={inativandoLote}
          lotesDestino={lotes?.filter((l) => l.ativo && l.id !== inativandoLote.id) || []}
          onFechar={() => setInativandoLote(null)}
          onConcluido={async () => { setInativandoLote(null); await carregar(); }}
        />
      )}
    </div>
  );
}

function FormLote({ form, setForm, onSalvar, onCancelar, salvando, msg, categorias, onAbrirPreviewCompleto }: {
  form: Form; setForm: (f: Form) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
  categorias: CategoriaManejo[]; onAbrirPreviewCompleto: () => void;
}) {
  const [preview, setPreview] = useState<{ total: number; animais: string[] } | null>(null);
  const [carregandoPreview, setCarregandoPreview] = useState(false);
  const [categoriasAbertas, setCategoriasAbertas] = useState(false);

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
  const toggleCategoriaManejo = (id: number) => setForm({
    ...form, categoria_manejo_ids: form.categoria_manejo_ids.includes(id)
      ? form.categoria_manejo_ids.filter((x) => x !== id) : [...form.categoria_manejo_ids, id],
  });
  const nomesCategoriaManejo = form.categoria_manejo_ids
    .map((id) => categorias.find((c) => c.id === id)?.nome)
    .filter(Boolean)
    .join(", ");

  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-3">
        <div><label style={labelStyle}>Código</label>
          <input style={inputStyle} value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} placeholder="ex.: 01" /></div>
        <div><label style={labelStyle}>Nome</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Alta" /></div>
        <div><label style={labelStyle}>Dias pós-parto de</label>
          <input type="number" style={inputStyle} value={form.del_min} onChange={(e) => setForm({ ...form, del_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Dias pós-parto até</label>
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
        <div><label style={labelStyle}>Situação produtiva</label>
          <select style={inputStyle} value={form.status_lactacao} onChange={(e) => setForm({ ...form, status_lactacao: e.target.value })}>
            <option value="">Qualquer</option>
            <option value="lactacao">Em lactação</option>
            <option value="seca">Seca</option>
          </select></div>
        <div><label style={labelStyle}>Situação reprodutiva</label>
          <select style={inputStyle} value={form.situacao_reprodutiva} onChange={(e) => setForm({ ...form, situacao_reprodutiva: e.target.value })}>
            <option value="">Qualquer</option>
            <option value="vazia">Vazia</option>
            <option value="inseminada">Inseminada</option>
            <option value="prenha">Prenha</option>
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
          <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>Bezerro macho conta junto de "bezerra" até a venda. Só restringe — sozinha não gera sugestão automática.</p>
        </div>
        <div><label style={labelStyle}>Faltando p/ parto — de (dias)</label>
          <input type="number" style={inputStyle} value={form.dias_para_parto_min} onChange={(e) => setForm({ ...form, dias_para_parto_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Faltando p/ parto — até (dias)</label>
          <input type="number" style={inputStyle} value={form.dias_para_parto_max} onChange={(e) => setForm({ ...form, dias_para_parto_max: e.target.value })} /></div>
        <div><label style={labelStyle}>Peso de (kg)</label>
          <input type="number" style={inputStyle} value={form.peso_min} onChange={(e) => setForm({ ...form, peso_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Peso até (kg)</label>
          <input type="number" style={inputStyle} value={form.peso_max} onChange={(e) => setForm({ ...form, peso_max: e.target.value })} /></div>
        <div><label style={labelStyle}>Dias de gestação de</label>
          <input type="number" style={inputStyle} value={form.dias_gestacao_min} onChange={(e) => setForm({ ...form, dias_gestacao_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Dias de gestação até</label>
          <input type="number" style={inputStyle} value={form.dias_gestacao_max} onChange={(e) => setForm({ ...form, dias_gestacao_max: e.target.value })} /></div>
        <div><label style={labelStyle}>Dias desde o último serviço — de</label>
          <input type="number" style={inputStyle} value={form.dias_desde_servico_min} onChange={(e) => setForm({ ...form, dias_desde_servico_min: e.target.value })} /></div>
        <div><label style={labelStyle}>Dias desde o último serviço — até</label>
          <input type="number" style={inputStyle} value={form.dias_desde_servico_max} onChange={(e) => setForm({ ...form, dias_desde_servico_max: e.target.value })} /></div>
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
      <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "-0.5rem" }}>
        Pré-parto, Em tratamento, Novilhas inseminadas e Novilhas gestantes só restringem — sozinhas não geram sugestão automática.
      </p>

      <div className="mb-3">
        <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", cursor: "pointer" }}
          title="Mesmo que os critérios acima batam com algum animal, este lote nunca aparece nas sugestões automáticas de movimentação — útil para enfermaria, quarentena, venda etc., onde a troca de lote deve continuar sempre manual.">
          <input type="checkbox" checked={form.excluir_da_sugestao} onChange={(e) => setForm({ ...form, excluir_da_sugestao: e.target.checked })} />
          Não considerar este lote nas sugestões automáticas de movimentação
        </label>
      </div>

      <div className="mb-3">
        <label style={labelStyle}>Categoria(s) de manejo vinculada(s) (Configurações &gt; Cadastro &gt; Categorias) — inclui só as marcadas; se nenhuma marcada, não restringe. Só restringe — sozinha não gera sugestão automática.</label>
        <button type="button" onClick={() => setCategoriasAbertas(true)} style={{ ...inputStyle, textAlign: "left", cursor: "pointer", color: nomesCategoriaManejo ? "var(--text)" : "var(--text-muted)" }}>
          {nomesCategoriaManejo || "Selecionar categoria(s)…"}
        </button>
        {categoriasAbertas && (
          <div onClick={() => setCategoriasAbertas(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 90, padding: "1rem" }}>
            <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "480px", maxWidth: "96vw", maxHeight: "80vh", display: "flex", flexDirection: "column" }}>
              <div className="flex items-center justify-between mb-3">
                <div className="card-header" style={{ margin: 0 }}>Categorias de manejo</div>
                <button onClick={() => setCategoriasAbertas(false)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
              </div>
              <div style={{ overflowY: "auto" }}>
                {!categorias.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma categoria cadastrada em Configurações &gt; Cadastro &gt; Categorias.</p>}
                {categorias.map((c) => (
                  <label key={c.id} className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.4rem 0.2rem", cursor: "pointer" }}>
                    <input type="checkbox" checked={form.categoria_manejo_ids.includes(c.id!)} onChange={() => toggleCategoriaManejo(c.id!)} />
                    {c.nome}
                  </label>
                ))}
              </div>
              <div className="flex justify-end mt-3">
                <button onClick={() => setCategoriasAbertas(false)} className="btn-primary" style={{ fontSize: "0.82rem" }}>Concluir</button>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 mb-3" style={{ fontSize: "0.8rem", color: "var(--dourado-light)" }}>
        <Users size={14} />
        {carregandoPreview ? "Calculando…" : preview ? `${preview.total} animal(is) do rebanho atende(m) a esses critérios hoje.` : "—"}
        {preview && preview.total > 0 && (
          <button type="button" onClick={onAbrirPreviewCompleto} title="Ver quais animais atendem" aria-label="Ver quais animais atendem"
            className="btn-ghost" style={{ padding: "0.15rem 0.3rem", display: "flex" }}>
            <ArrowUpRight size={14} />
          </button>
        )}
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

type AnimalDoLote = { numero: string; grupo_primario: string | null };

// Janela suspensa disparada ao inativar um lote não-vazio: pergunta pra onde
// vão os animais que estão nele. Só pergunta "em lote ou individual" quando
// há mais de um animal — com um só, não há ambiguidade nenhuma.
function InativarLoteWizard({ lote, lotesDestino, onFechar, onConcluido }: {
  lote: Lote; lotesDestino: Lote[]; onFechar: () => void; onConcluido: () => void;
}) {
  const [animais, setAnimais] = useState<AnimalDoLote[] | null>(null);
  const [modo, setModo] = useState<"lote" | "individual" | null>(null);
  const [destinoUnico, setDestinoUnico] = useState("");
  const [destinoPorAnimal, setDestinoPorAnimal] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchAnimais({ grupo: lote.rotulo }).then((r: AnimalDoLote[]) => {
      setAnimais(r);
      if (r.length === 1) setModo("individual"); // pula a pergunta lote/individual
    }).catch((e: any) => setErro(e.message || "Erro ao carregar os animais do lote"));
  }, [lote.rotulo]);

  const confirmar = async () => {
    if (!animais) return;
    if (modo === "lote" && !destinoUnico) { setErro("Selecione o lote de destino."); return; }
    if (modo === "individual" && animais.some((a) => !destinoPorAnimal[a.numero])) { setErro("Selecione o lote de destino para todos os animais."); return; }

    setErro(null);
    setSalvando(true);
    try {
      const hoje = new Date().toISOString().slice(0, 10);
      if (modo === "lote") {
        await criarMovimentacao({
          data_movimento: hoje, motivo: "Inativação de lote", lote_destino_codigo: destinoUnico,
          animais: animais.map((a) => a.numero),
        });
      } else {
        // Agrupa por destino pra minimizar chamadas (1 por lote de destino escolhido).
        const porDestino = new Map<string, string[]>();
        for (const a of animais) {
          const dest = destinoPorAnimal[a.numero];
          porDestino.set(dest, [...(porDestino.get(dest) || []), a.numero]);
        }
        for (const [destino, numeros] of porDestino) {
          await criarMovimentacao({ data_movimento: hoje, motivo: "Inativação de lote", lote_destino_codigo: destino, animais: numeros });
        }
      }
      await atualizarLote(lote.id, payloadDoLote(lote, { ativo: false }));
      onConcluido();
    } catch (e: any) {
      setErro(e.message || "Erro ao transferir os animais");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <Modal title={`Inativar lote ${lote.rotulo}`} onClose={onFechar} width="560px">
      {!animais ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
      ) : (
        <>
          <p style={{ fontSize: "0.85rem", marginBottom: "0.75rem" }}>
            Este lote ainda tem <strong>{animais.length}</strong> animal(is). Pra onde eles devem ir antes de inativar?
          </p>

          {animais.length > 1 && modo === null && (
            <div className="flex flex-col gap-2 mb-3">
              <button className="btn-ghost" style={{ textAlign: "left", padding: "0.6rem 0.8rem" }} onClick={() => setModo("lote")}>
                Mover todos para o mesmo lote
              </button>
              <button className="btn-ghost" style={{ textAlign: "left", padding: "0.6rem 0.8rem" }} onClick={() => setModo("individual")}>
                Escolher o lote de destino individualmente
              </button>
            </div>
          )}

          {modo === "lote" && (
            <div className="mb-3">
              <label style={labelStyle}>Lote de destino (todos os {animais.length} animais)</label>
              <select style={inputStyle} value={destinoUnico} onChange={(e) => setDestinoUnico(e.target.value)}>
                <option value="">Selecione…</option>
                {lotesDestino.map((l) => <option key={l.id} value={l.codigo}>{l.rotulo}</option>)}
              </select>
            </div>
          )}

          {modo === "individual" && (
            <div className="overflow-x-auto mb-3">
              <table className="fazenda-table">
                <thead><tr><th>Nº do animal</th><th>Lote atual</th><th>Lote de destino</th></tr></thead>
                <tbody>
                  {animais.map((a) => (
                    <tr key={a.numero}>
                      <td style={{ fontWeight: 700 }}>{a.numero}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{a.grupo_primario || "—"}</td>
                      <td>
                        <select style={inputStyle} value={destinoPorAnimal[a.numero] || ""}
                          onChange={(e) => setDestinoPorAnimal((p) => ({ ...p, [a.numero]: e.target.value }))}>
                          <option value="">Selecione…</option>
                          {lotesDestino.map((l) => <option key={l.id} value={l.codigo}>{l.rotulo}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}

          {modo !== null && (
            <div className="flex items-center justify-end gap-2">
              <button className="btn-ghost" onClick={onFechar} disabled={salvando}>Cancelar</button>
              <button className="btn-primary" onClick={confirmar} disabled={salvando}>
                {salvando ? "Movendo e inativando…" : "Transferir e inativar o lote"}
              </button>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
