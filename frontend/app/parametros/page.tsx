"use client";
import { Fragment, useEffect, useState } from "react";
import { SlidersHorizontal, AlertTriangle, Info, Pencil, Check, Loader2, Milk, Plus, X } from "lucide-react";
import { API, authFetch, atualizarParametro, ehAdmin, fetchParametros } from "@/lib/api";
import CadastroMotivosVenda from "@/components/CadastroMotivosVenda";
import ManualFazendaParametros from "@/components/ManualFazendaParametros";

type Item = { chave: string; label: string; valor: number | string | boolean | null; unidade: string | null; tipo?: string };
type Grupo = { titulo: string; itens: Item[] };

export default function ParametrosPage() {
  const [grupos, setGrupos] = useState<Record<string, Grupo> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<Set<string>>(new Set());
  const [valores, setValores] = useState<Record<string, number | string | boolean>>({});
  const [salvando, setSalvando] = useState<string | null>(null);
  const [salvoOk, setSalvoOk] = useState<string | null>(null);
  const podeEditar = ehAdmin();

  const carregar = () => fetchParametros().then((d) => setGrupos(d.grupos)).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const concluirEdicao = async (id: string, g: Grupo) => {
    const alterados = g.itens.filter((it) => it.chave in valores && valores[it.chave] !== it.valor);
    setEditando((p) => { const s = new Set(p); s.delete(id); return s; });
    if (!alterados.length) return;
    setSalvando(id);
    try {
      for (const it of alterados) {
        await atualizarParametro(it.chave, valores[it.chave]);
      }
      await carregar();
      setSalvoOk(id);
      setTimeout(() => setSalvoOk(null), 2000);
    } catch (e: any) {
      setError(e.message || "Erro ao salvar parâmetro");
    } finally {
      setSalvando(null);
    }
  };

  const inputStyle = {
    width: "5rem", textAlign: "right" as const, background: "var(--surface-2)", color: "var(--text)",
    border: "1px solid var(--border)", borderRadius: "6px", padding: "0.2rem 0.4rem", fontSize: "0.82rem",
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <SlidersHorizontal size={22} style={{ color: "var(--dourado-light)" }} /> Parâmetros da Fazenda
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Metas e configurações de manejo que orientam os indicadores, a agenda e os relatórios (faixas verde/vermelha, previsões e alertas).
        </p>
      </div>

      <div className="card mb-4" style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", background: "rgba(94,26,46,0.18)" }}>
        <Info size={16} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Estes são os valores de referência atuais da fazenda. Servem de base para as metas dos medidores da capa e para as regras da agenda.
          {podeEditar
            ? " O valor salvo passa a valer para todos os relatórios, agenda e alertas."
            : " Somente administradores podem editar."}
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{error}</span></div>}
      {!grupos && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {grupos && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Object.entries(grupos).map(([id, g]) => {
            const edit = editando.has(id);
            return (
            <div key={id} className="card">
              <div className="card-header mb-3 flex items-center justify-between">
                <span>{g.titulo}</span>
                {podeEditar && (
                  <button
                    onClick={() => edit ? concluirEdicao(id, g) : setEditando((p) => new Set(p).add(id))}
                    disabled={salvando === id}
                    title={edit ? "Concluir" : "Editar"}
                    style={{ background: "none", border: "none", color: "var(--dourado-light)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem" }}>
                    {salvando === id ? <><Loader2 size={13} className="animate-spin" /> Salvando…</>
                      : edit ? <><Check size={13} /> Concluir</> : <><Pencil size={13} /> Editar</>}
                  </button>
                )}
              </div>
              <table className="fazenda-table">
                <tbody>
                  {g.itens.map((it) => {
                    const valorAtual = valores[it.chave] ?? it.valor;
                    return (
                    <tr key={it.chave}>
                      <td style={{ fontSize: "0.82rem" }}>{it.label}</td>
                      <td style={{ textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>
                        {edit && it.tipo === "bool" ? (
                          <select value={String(valorAtual)} onChange={(e) => setValores((p) => ({ ...p, [it.chave]: e.target.value === "true" }))}
                            style={inputStyle}>
                            <option value="true">Sim</option>
                            <option value="false">Não</option>
                          </select>
                        ) : edit && it.tipo === "date" ? (
                          <input type="date" defaultValue={String(valorAtual ?? "")}
                            onChange={(e) => setValores((p) => ({ ...p, [it.chave]: e.target.value }))}
                            style={inputStyle} />
                        ) : edit ? (
                          <input type="number" defaultValue={Number(valorAtual)}
                            onChange={(e) => setValores((p) => ({ ...p, [it.chave]: Number(e.target.value) }))}
                            style={inputStyle} />
                        ) : it.tipo === "bool" ? (
                          <>{valorAtual ? "Sim" : "Não"}</>
                        ) : (
                          <>{String(valorAtual)}</>
                        )}
                        {it.unidade && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginLeft: "0.25rem" }}>{it.unidade}</span>}
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
              {salvoOk === id && <p style={{ fontSize: "0.68rem", color: "var(--verde, #2f9e5c)", marginTop: "0.5rem" }}>Salvo — já vale para relatórios, agenda e alertas.</p>}
            </div>
            );
          })}
        </div>
      )}

      <div className="mt-4">
        <ManualFazendaParametros podeEditar={podeEditar} />
      </div>

      <div className="mt-4">
        <CadastroMotivosVenda />
      </div>

      <div className="mt-4">
        <CadastroFaixasBonificacaoQualidade podeEditar={podeEditar} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Faixas de bonificação/penalização por qualidade do leite (#548) — cada
// laticínio define sua própria tabela de faixas de CCS/CBT/gordura/proteína
// (não existe padrão nacional único), por isso fica 100% configurável aqui
// em vez de hardcodada — usada em Produção > Qualidade do leite para estimar
// o ajuste (R$/litro) de cada lançamento.
// ---------------------------------------------------------------------------
type FaixaBonificacao = {
  id: number; indicador: string; valor_min: number | null; valor_max: number | null;
  ajuste_por_litro: number; ativo: boolean; observacao: string | null;
};
type FaixaForm = {
  indicador: string; valor_min: string; valor_max: string; ajuste_por_litro: string; ativo: boolean; observacao: string;
};
const FORM_FAIXA_VAZIO: FaixaForm = { indicador: "ccs", valor_min: "", valor_max: "", ajuste_por_litro: "", ativo: true, observacao: "" };

const INDICADORES_FAIXA: { value: string; label: string; unidade: string }[] = [
  { value: "ccs", label: "CCS", unidade: "mil céls./mL" },
  { value: "cbt", label: "CBT", unidade: "mil UFC/mL" },
  { value: "gordura_pct", label: "Gordura", unidade: "%" },
  { value: "proteina_pct", label: "Proteína", unidade: "%" },
];
const labelIndicador = (v: string) => INDICADORES_FAIXA.find((i) => i.value === v)?.label ?? v;
const unidadeIndicador = (v: string) => INDICADORES_FAIXA.find((i) => i.value === v)?.unidade ?? "";

async function listarFaixasBonificacao(): Promise<{ faixas: FaixaBonificacao[] }> {
  const res = await authFetch(`${API}/producao/faixas-bonificacao-qualidade`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Erro ao carregar faixas de bonificação: ${res.status}`);
  return res.json();
}
async function salvarFaixaBonificacao(id: number | "novo", dados: Record<string, unknown>) {
  const url = id === "novo"
    ? `${API}/producao/faixas-bonificacao-qualidade`
    : `${API}/producao/faixas-bonificacao-qualidade/${id}`;
  const res = await authFetch(url, {
    method: id === "novo" ? "POST" : "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao salvar faixa de bonificação"); }
  return res.json();
}
async function excluirFaixaBonificacao(id: number) {
  const res = await authFetch(`${API}/producao/faixas-bonificacao-qualidade/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erro ao excluir faixa de bonificação"); }
  return res.json();
}

function CadastroFaixasBonificacaoQualidade({ podeEditar }: { podeEditar: boolean }) {
  const [faixas, setFaixas] = useState<FaixaBonificacao[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<FaixaForm>(FORM_FAIXA_VAZIO);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => listarFaixasBonificacao().then((d) => setFaixas(d.faixas)).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const abrirNovo = () => { setForm(FORM_FAIXA_VAZIO); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (f: FaixaBonificacao) => {
    setForm({
      indicador: f.indicador, valor_min: f.valor_min == null ? "" : String(f.valor_min),
      valor_max: f.valor_max == null ? "" : String(f.valor_max), ajuste_por_litro: String(f.ajuste_por_litro),
      ativo: f.ativo, observacao: f.observacao ?? "",
    });
    setEditando(f.id);
    setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (form.ajuste_por_litro.trim() === "" || isNaN(Number(form.ajuste_por_litro))) {
      setMsg("Informe o ajuste em R$/litro (pode ser negativo, para penalização)."); return;
    }
    if (form.valor_min !== "" && form.valor_max !== "" && Number(form.valor_min) > Number(form.valor_max)) {
      setMsg("Valor mínimo não pode ser maior que o valor máximo."); return;
    }
    setSalvando(true); setMsg(null);
    try {
      const dados = {
        indicador: form.indicador,
        valor_min: form.valor_min === "" ? null : Number(form.valor_min),
        valor_max: form.valor_max === "" ? null : Number(form.valor_max),
        ajuste_por_litro: Number(form.ajuste_por_litro),
        ativo: form.ativo,
        observacao: form.observacao.trim() || null,
      };
      await salvarFaixaBonificacao(editando as number | "novo", dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const excluir = async (f: FaixaBonificacao) => {
    if (!confirm(`Excluir a faixa de ${labelIndicador(f.indicador)} (${f.valor_min ?? "—"} a ${f.valor_max ?? "—"})?`)) return;
    setError(null);
    try {
      await excluirFaixaBonificacao(f.id);
      await carregar();
    } catch (e: any) {
      setError(e.message || "Erro ao excluir");
    }
  };

  const FormFaixa = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3">
        <div>
          <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Indicador</label>
          <select style={{ ...selectStyleFaixa }} value={form.indicador} onChange={(e) => setForm({ ...form, indicador: e.target.value })}>
            {INDICADORES_FAIXA.map((i) => <option key={i.value} value={i.value}>{i.label} ({i.unidade})</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De (mín., vazio = sem limite)</label>
          <input type="number" style={selectStyleFaixa} value={form.valor_min} onChange={(e) => setForm({ ...form, valor_min: e.target.value })} />
        </div>
        <div>
          <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até (máx., vazio = sem limite)</label>
          <input type="number" style={selectStyleFaixa} value={form.valor_max} onChange={(e) => setForm({ ...form, valor_max: e.target.value })} />
        </div>
        <div>
          <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ajuste (R$/litro, negativo = desconto)</label>
          <input type="number" step="0.001" style={selectStyleFaixa} value={form.ajuste_por_litro} onChange={(e) => setForm({ ...form, ajuste_por_litro: e.target.value })} />
        </div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativa</label></div>
      </div>
      <div className="mb-3">
        <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Observação (opcional)</label>
        <input style={{ ...selectStyleFaixa, width: "100%" }} value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} placeholder="Ex.: tabela do laticínio X, vigente a partir de 07/2026" />
      </div>
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
        <span className="flex items-center gap-2"><Milk size={16} /> Faixas de bonificação/penalização — qualidade do leite</span>
        {podeEditar && (
          <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
            <Plus size={14} /> Nova faixa
          </button>
        )}
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Cada laticínio define sua própria tabela de bonificação — cadastre aqui as faixas de CCS, CBT, gordura e proteína
        do seu comprador para que Produção &gt; Qualidade do leite calcule o ajuste estimado (R$/litro) de cada coleta.
        {!podeEditar && " Somente administradores podem cadastrar ou editar faixas."}
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!faixas && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {podeEditar && editando === "novo" && FormFaixa}

      {faixas && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Indicador</th><th>Faixa</th><th>Ajuste (R$/litro)</th><th>Observação</th><th></th></tr></thead>
            <tbody>
              {faixas.map((f) => (
                <Fragment key={f.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{labelIndicador(f.indicador)}{!f.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativa)</span>}</td>
                    <td style={{ fontSize: "0.82rem" }}>{f.valor_min ?? "—"} a {f.valor_max ?? "—"} {unidadeIndicador(f.indicador)}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: f.ajuste_por_litro < 0 ? "var(--red)" : "var(--green-light)" }}>
                      {f.ajuste_por_litro.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 3, maximumFractionDigits: 4 })}
                    </td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{f.observacao ?? "—"}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {podeEditar && (
                        <>
                          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(f)}>
                            <Pencil size={13} /> Editar
                          </button>
                          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", color: "var(--red)", marginLeft: "0.5rem" }} onClick={() => excluir(f)}>
                            <X size={13} /> Excluir
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                  {editando === f.id && podeEditar && (
                    <tr><td colSpan={5} style={{ padding: 0 }}>{FormFaixa}</td></tr>
                  )}
                </Fragment>
              ))}
              {!faixas.length && (
                <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  Nenhuma faixa de bonificação cadastrada ainda — os lançamentos de Qualidade do leite não terão ajuste estimado até que ao menos uma faixa seja cadastrada aqui.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const selectStyleFaixa: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
