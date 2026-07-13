"use client";
// Configurações > Cadastro > Alimentação — onde o veterinário/nutricionista
// cadastra a dieta dos animais. Duas visões:
//   • "Cadastrar nova dieta": por lote, mostra o contexto (nº/nome, nº de
//     animais, última dieta, último controle leiteiro de cada animal e um
//     resumo — DEL médio, média do CL, data do CL) e permite lançar os
//     produtos com cálculo automático (total/dia, total/trato, por cabeça e o
//     somatório de kg do vagão). Datas de início e provável fim. Um único botão
//     salva todas as dietas configuradas.
//   • "Visualizar dietas": lista as dietas lançadas e abre a apresentação como
//     o funcionário a vê (produtos, por cabeça, total/dia, total/trato e kg no
//     vagão).
// Ao salvar uma nova dieta num lote que já tem dieta ativa, pergunta se deseja
// encerrar a atual na data de início da nova.
import { Fragment, useEffect, useMemo, useState } from "react";
import { Plus, Trash2, Wheat, ClipboardList, ChevronDown, ChevronRight, Percent } from "lucide-react";
import {
  fetchLotes, fetchAlimentosPadrao, fetchContextoDieta, fetchDietas, fetchApresentacaoDieta,
  criarDieta, fetchMateriaSeca, salvarMateriaSeca, type ContextoDieta, type ApresentacaoDieta,
} from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";
import { TabelaNutricionalBotao } from "./TabelaNutricional";

const NUM_TRATOS = 2;
const UNIDADES = ["kg", "g", "L", "ml", "unidade", "dose", "saca 30kg", "saca 60kg"];

type LoteRow = { codigo: string; nome?: string | null; rotulo?: string; qtd_animais?: number };
type ItemForm = { alimento: string; quantidade: string; unidade: string; base: string };
type LoteForm = { responsavel: string; dataAbertura: string; dataPrevista: string; baseQuantidade: string; itens: ItemForm[] };

const hoje = () => new Date().toISOString().slice(0, 10);
const itemVazio = (): ItemForm => ({ alimento: "", quantidade: "", unidade: "kg", base: "MN" });
const formVazio = (): LoteForm => ({ responsavel: "Alexandre Scarpa (consultor)", dataAbertura: hoje(), dataPrevista: "", baseQuantidade: "total", itens: [itemVazio()] });

function num(v?: number | null, casas = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}
function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

const input: React.CSSProperties = {
  width: "100%", padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem",
  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem", display: "block" };

export default function CadastroAlimentacao() {
  const [aba, setAba] = useState<"nova" | "ver" | "ms">("nova");
  return (
    <div>
      <div className="flex items-center justify-between mb-3" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
          {([["nova", "Cadastrar nova dieta", Wheat], ["ver", "Visualizar dietas", ClipboardList], ["ms", "Matéria seca", Percent]] as const).map(([id, label, Icon]) => (
            <button key={id} onClick={() => setAba(id)}
              style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.35rem 0.85rem", borderRadius: 999, cursor: "pointer",
                border: "1px solid " + (aba === id ? "var(--dourado)" : "var(--border)"),
                background: aba === id ? "rgba(94,26,46,0.4)" : "transparent",
                color: aba === id ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: aba === id ? 700 : 500 }}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
        <TabelaNutricionalBotao />
      </div>
      {aba === "nova" ? <CadastrarNovaDieta /> : aba === "ver" ? <VisualizarDietas /> : <MateriaSeca />}
    </div>
  );
}

// ─────────────────────────── Matéria seca (ingredientes padrão) ───────────────
function MateriaSeca() {
  const [itens, setItens] = useState<{ nome: string; ms_pct: number | null }[]>([]);
  const [salvando, setSalvando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  useEffect(() => { fetchMateriaSeca().then(setItens).catch(() => {}); }, []);
  const patch = (nome: string, ms: string) => setItens((p) => p.map((i) => (i.nome === nome ? { ...i, ms_pct: ms === "" ? null : Number(ms) } : i)));
  async function salvar(nome: string, ms: number | null) {
    setSalvando(nome); setAviso(null);
    try { await salvarMateriaSeca({ nome, ms_pct: ms }); setAviso(`Matéria seca de ${nome} salva.`); }
    catch (e: any) { setAviso(e.message || "Erro ao salvar."); }
    finally { setSalvando(null); }
  }
  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        % de matéria seca (MS) de cada ingrediente padrão — usada para converter entre matéria natural e matéria seca nas dietas. Edite e salve.
      </p>
      <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", maxWidth: "36rem" }}>
        {itens.map((i) => (
          <div key={i.nome} className="flex items-center gap-3" style={{ padding: "0.5rem 0.7rem", borderBottom: "1px solid var(--border)" }}>
            <span style={{ flex: 1, fontSize: "0.85rem" }}>{i.nome}</span>
            <input type="number" inputMode="decimal" step="0.01" style={{ ...input, width: "6rem" }} value={i.ms_pct ?? ""} onChange={(e) => patch(i.nome, e.target.value)} placeholder="% MS" />
            <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>%</span>
            <button className="btn-primary" style={{ fontSize: "0.75rem", padding: "0.3rem 0.7rem" }} disabled={salvando === i.nome} onClick={() => salvar(i.nome, i.ms_pct)}>
              {salvando === i.nome ? "…" : "Salvar"}
            </button>
          </div>
        ))}
        {!itens.length && <p style={{ padding: "0.8rem", color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando ingredientes…</p>}
      </div>
      {aviso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{aviso}</p>}
    </div>
  );
}

// ─────────────────────────── Cadastrar nova dieta ───────────────────────────
function CadastrarNovaDieta() {
  const [lotes, setLotes] = useState<LoteRow[]>([]);
  const [alimentos, setAlimentos] = useState<string[]>([]);
  const [contextos, setContextos] = useState<Record<number, ContextoDieta | null>>({});
  const [forms, setForms] = useState<Record<number, LoteForm>>({});
  const [aberto, setAberto] = useState<Set<number>>(new Set());
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  useEffect(() => {
    fetchLotes().then((ls: LoteRow[]) => setLotes(ls.filter((l) => /^\d\d/.test(l.codigo)))).catch((e) => setErro(e.message));
    fetchAlimentosPadrao().then(setAlimentos).catch(() => {});
  }, []);

  const loteNum = (l: LoteRow) => Number(l.codigo.slice(0, 2));

  function toggle(lote: number) {
    setAberto((prev) => {
      const n = new Set(prev);
      if (n.has(lote)) n.delete(lote);
      else {
        n.add(lote);
        if (!(lote in contextos)) {
          setContextos((c) => ({ ...c, [lote]: null }));
          fetchContextoDieta(lote).then((ctx) => setContextos((c) => ({ ...c, [lote]: ctx }))).catch(() => setContextos((c) => ({ ...c, [lote]: null })));
        }
        if (!(lote in forms)) setForms((f) => ({ ...f, [lote]: formVazio() }));
      }
      return n;
    });
  }

  const patchForm = (lote: number, patch: Partial<LoteForm>) => setForms((f) => ({ ...f, [lote]: { ...(f[lote] || formVazio()), ...patch } }));
  const patchItem = (lote: number, idx: number, patch: Partial<ItemForm>) => setForms((f) => {
    const cur = f[lote] || formVazio();
    const itens = cur.itens.map((it, i) => (i === idx ? { ...it, ...patch } : it));
    return { ...f, [lote]: { ...cur, itens } };
  });
  const addItem = (lote: number) => setForms((f) => { const cur = f[lote] || formVazio(); return { ...f, [lote]: { ...cur, itens: [...cur.itens, itemVazio()] } }; });
  const delItem = (lote: number, idx: number) => setForms((f) => { const cur = f[lote] || formVazio(); return { ...f, [lote]: { ...cur, itens: cur.itens.length > 1 ? cur.itens.filter((_, i) => i !== idx) : cur.itens } }; });

  // Lotes com ao menos um item válido (pronto para salvar).
  const lotesPreenchidos = useMemo(() => {
    return lotes.map(loteNum).filter((ln) => {
      const f = forms[ln];
      return f && f.itens.some((it) => it.alimento && Number(it.quantidade) > 0);
    });
  }, [lotes, forms]);

  async function salvarTudo() {
    setErro(null); setSucesso(null);
    if (!lotesPreenchidos.length) { setErro("Configure ao menos um lote com um produto e quantidade."); return; }
    setSalvando(true);
    const salvos: number[] = [];
    const falhas: string[] = [];
    try {
      for (const ln of lotesPreenchidos) {
        const f = forms[ln]!;
        const itensValidos = f.itens.filter((it) => it.alimento && Number(it.quantidade) > 0);
        if (!f.dataAbertura) { falhas.push(`Lote ${ln}: informe a data de início.`); continue; }
        // Se já há dieta ativa, pergunta se deseja encerrá-la na data de início.
        let encerrar = false;
        if (contextos[ln]?.ultima_dieta) {
          encerrar = window.confirm(`O lote ${ln} já tem uma dieta ativa. Deseja encerrar a dieta atual na data de início desta nova dieta (${formatDate(f.dataAbertura)})?`);
          if (!encerrar) { falhas.push(`Lote ${ln}: não salvo (dieta ativa mantida).`); continue; }
        }
        try {
          await criarDieta({
            lote: ln, responsavel: f.responsavel || undefined, data_abertura: f.dataAbertura, base_quantidade: f.baseQuantidade,
            data_prevista_encerramento: f.dataPrevista || undefined,
            itens: itensValidos.map((it) => ({ alimento: it.alimento, quantidade: Number(it.quantidade), unidade: it.unidade, base: it.base })),
            encerrar_anterior: encerrar,
          });
          salvos.push(ln);
        } catch (e: any) {
          falhas.push(`Lote ${ln}: ${e.message || "erro ao salvar"}`);
        }
      }
      if (salvos.length) {
        setSucesso(`Dieta salva para ${salvos.length === 1 ? "o lote" : "os lotes"} ${salvos.join(", ")}.`);
        // Limpa os lotes salvos e recarrega seus contextos.
        setForms((f) => { const n = { ...f }; salvos.forEach((ln) => delete n[ln]); return n; });
        setAberto((prev) => { const n = new Set(prev); salvos.forEach((ln) => n.delete(ln)); return n; });
        salvos.forEach((ln) => fetchContextoDieta(ln).then((ctx) => setContextos((c) => ({ ...c, [ln]: ctx }))).catch(() => {}));
      }
      if (falhas.length) setErro(falhas.join(" · "));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
        Abra cada lote para ver o rebanho, a última dieta e o último controle leiteiro, e lançar a nova dieta.
        A <strong>quantidade</strong> de cada produto é o total do lote por dia — o sistema calcula sozinho por cabeça,
        por trato ({NUM_TRATOS} tratos/dia) e o total de kg no vagão. Ao final, um único botão salva todos os lotes.
      </p>

      <datalist id="alimentos-cad-dieta">{alimentos.map((a) => <option key={a} value={a} />)}</datalist>

      <div className="space-y-2">
        {lotes.map((l) => {
          const ln = loteNum(l);
          const isOpen = aberto.has(ln);
          const ctx = contextos[ln];
          const f = forms[ln];
          const nAnimais = ctx?.qtd_animais ?? l.qtd_animais ?? 0;
          const vagaoKg = f ? f.itens.reduce((s, it) => (["kg", "g"].includes(it.unidade) ? s + (Number(it.quantidade) || 0) : s), 0) : 0;
          const preenchido = lotesPreenchidos.includes(ln);
          return (
            <div key={l.codigo} style={{ border: "1px solid " + (preenchido ? "var(--dourado)" : "var(--border)"), borderRadius: 10, overflow: "hidden" }}>
              <button onClick={() => toggle(ln)}
                style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem",
                  padding: "0.7rem 0.9rem", background: "var(--surface-2)", border: "none", cursor: "pointer", color: "var(--text)", textAlign: "left" }}>
                <span className="flex items-center gap-2" style={{ fontWeight: 700 }}>
                  {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  Lote {ln}{l.nome ? ` · ${l.nome}` : ""}
                </span>
                <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", flexShrink: 0 }}>
                  {nAnimais} {nAnimais === 1 ? "animal" : "animais"}{preenchido ? " · pronto p/ salvar" : ""}
                </span>
              </button>

              {isOpen && (
                <div style={{ padding: "0.9rem" }}>
                  {ctx === undefined || ctx === null ? (
                    <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{ln in contextos ? "Carregando contexto do lote…" : ""}</p>
                  ) : (
                    <ContextoLoteBox ctx={ctx} />
                  )}

                  {/* ── Lançamento da nova dieta ── */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
                    <div>
                      <label style={lbl}>Responsável (nutricionista)</label>
                      <select style={input} value={f?.responsavel || ""} onChange={(e) => patchForm(ln, { responsavel: e.target.value })}>
                        <option value="">—</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
                      </select>
                    </div>
                    <div>
                      <label style={lbl}>Data de início</label>
                      <input type="date" style={input} value={f?.dataAbertura || ""} onChange={(e) => patchForm(ln, { dataAbertura: e.target.value })} />
                    </div>
                    <div>
                      <label style={lbl}>Provável data de fim</label>
                      <input type="date" style={input} value={f?.dataPrevista || ""} onChange={(e) => patchForm(ln, { dataPrevista: e.target.value })} />
                    </div>
                    <div>
                      <label style={lbl}>Quantidades informadas</label>
                      <select style={input} value={f?.baseQuantidade || "total"} onChange={(e) => patchForm(ln, { baseQuantidade: e.target.value })}>
                        <option value="total">Total do lote/dia</option>
                        <option value="animal">Por animal/dia</option>
                      </select>
                    </div>
                  </div>

                  <div className="space-y-2 mt-3">
                    {(f?.itens || []).map((it, idx) => {
                      const q = Number(it.quantidade) || 0;
                      const porCab = nAnimais ? q / nAnimais : null;
                      const porTrato = q / NUM_TRATOS;
                      return (
                        <div key={idx} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "0.6rem", position: "relative" }}>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                            <div>
                              <label style={lbl}>Produto {idx + 1}</label>
                              <input style={input} list="alimentos-cad-dieta" value={it.alimento} onChange={(e) => patchItem(ln, idx, { alimento: e.target.value })} placeholder="ex.: Silagem de milho" />
                            </div>
                            <div>
                              <label style={lbl}>{f?.baseQuantidade === "animal" ? "Quantidade por animal/dia" : "Quantidade total/dia (lote)"}</label>
                              <input type="number" inputMode="decimal" style={input} value={it.quantidade} onChange={(e) => patchItem(ln, idx, { quantidade: e.target.value })} />
                            </div>
                            <div>
                              <label style={lbl}>Unidade</label>
                              <select style={input} value={it.unidade} onChange={(e) => patchItem(ln, idx, { unidade: e.target.value })}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select>
                            </div>
                            <div>
                              <label style={lbl}>Base</label>
                              <select style={input} value={it.base} onChange={(e) => patchItem(ln, idx, { base: e.target.value })}>
                                <option value="MN">Matéria natural (MN)</option>
                                <option value="MS">Matéria seca (MS)</option>
                              </select>
                            </div>
                          </div>
                          {/* Cálculo automático enquanto edita */}
                          <div className="flex items-center gap-4 mt-2" style={{ flexWrap: "wrap", fontSize: "0.76rem" }}>
                            <span style={{ color: "var(--green-light)", fontWeight: 700 }}>{num(porTrato)} {it.unidade}/trato</span>
                            <span style={{ color: "var(--amber)", fontWeight: 600 }}>{num(q)} {it.unidade}/dia</span>
                            <span style={{ color: "var(--text-muted)" }}>{porCab != null ? `${num(porCab, 3)} ${it.unidade}/cab` : "—/cab"}</span>
                          </div>
                          {(f?.itens.length || 0) > 1 && (
                            <button onClick={() => delItem(ln, idx)} title="Remover produto" aria-label="Remover produto" className="btn-ghost"
                              style={{ position: "absolute", top: "0.4rem", right: "0.4rem", color: "var(--red)" }}><Trash2 size={13} /></button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex items-center justify-between mt-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                    <button onClick={() => addItem(ln)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.78rem" }}><Plus size={14} /> Acrescentar produto</button>
                    <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>
                      Vagão: <span style={{ color: "var(--dourado-light)" }}>{num(vagaoKg)} kg/dia</span>
                      <span style={{ color: "var(--text-muted)", fontWeight: 500 }}> · {num(vagaoKg / NUM_TRATOS)} kg/trato</span>
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {!lotes.length && <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Nenhum lote cadastrado.</p>}
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.8rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.8rem" }}>{sucesso}</p>}

      <div className="mt-4" style={{ position: "sticky", bottom: 0, paddingTop: "0.5rem" }}>
        <button className="btn-primary" onClick={salvarTudo} disabled={salvando || !lotesPreenchidos.length}>
          {salvando ? "Salvando…" : `Salvar ${lotesPreenchidos.length || ""} ${lotesPreenchidos.length === 1 ? "dieta" : "dietas"}`.trim()}
        </button>
      </div>
    </div>
  );
}

function ContextoLoteBox({ ctx }: { ctx: ContextoDieta }) {
  const [verAnimais, setVerAnimais] = useState(false);
  return (
    <div style={{ background: "var(--surface-2)", borderRadius: 8, padding: "0.75rem" }}>
      {/* Relatório simplificado */}
      <div className="grid grid-cols-3 gap-2" style={{ marginBottom: "0.6rem" }}>
        <Metrica titulo="DEL médio hoje" valor={ctx.del_medio != null ? `${ctx.del_medio} d` : "—"} />
        <Metrica titulo="Média no último CL" valor={ctx.media_cl != null ? `${num(ctx.media_cl, 1)} kg` : "—"} />
        <Metrica titulo="Data do último CL" valor={formatDate(ctx.data_ult_cl)} />
      </div>

      {/* Última dieta */}
      <div style={{ marginBottom: "0.5rem" }}>
        <div style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
          Última dieta{ctx.ultima_dieta ? ` (desde ${formatDate(ctx.ultima_dieta.data_abertura)})` : ""}
        </div>
        {ctx.ultima_dieta && ctx.ultima_dieta.itens.length ? (
          <div className="flex flex-wrap gap-2">
            {ctx.ultima_dieta.itens.map((it, i) => (
              <span key={i} style={{ fontSize: "0.74rem", padding: "0.15rem 0.5rem", borderRadius: 6, background: "var(--surface)", border: "1px solid var(--border)" }}>
                <strong>{it.alimento}</strong>: {num(it.total_dia)} {it.unidade}/dia{it.por_cabeca != null ? ` · ${num(it.por_cabeca, 3)}/cab` : ""}
              </span>
            ))}
          </div>
        ) : <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Sem dieta ativa registrada.</span>}
      </div>

      {/* Último controle leiteiro de cada animal (expansível) */}
      <button onClick={() => setVerAnimais((v) => !v)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.76rem" }}>
        {verAnimais ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Último controle leiteiro por animal ({ctx.animais.length})
      </button>
      {verAnimais && (
        <div className="overflow-x-auto mt-1">
          <table className="fazenda-table" style={{ fontSize: "0.74rem", margin: 0 }}>
            <thead><tr><th>Animal</th><th style={{ textAlign: "right" }}>DEL</th><th style={{ textAlign: "right" }}>Último CL</th><th style={{ textAlign: "right" }}>Data</th></tr></thead>
            <tbody>
              {ctx.animais.map((a) => (
                <tr key={a.numero}>
                  <td style={{ fontWeight: 600 }}>{a.numero}</td>
                  <td style={{ textAlign: "right" }}>{a.del_dias != null ? `${a.del_dias} d` : "—"}</td>
                  <td style={{ textAlign: "right" }}>{a.ult_cl_kg != null ? `${num(a.ult_cl_kg, 1)} kg` : "—"}</td>
                  <td style={{ textAlign: "right" }}>{formatDate(a.data_ult_leite)}</td>
                </tr>
              ))}
              {!ctx.animais.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", textAlign: "center" }}>Nenhum animal no lote.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Metrica({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "0.45rem 0.55rem" }}>
      <div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{titulo}</div>
      <div style={{ fontSize: "0.95rem", fontWeight: 800 }}>{valor}</div>
    </div>
  );
}

// ─────────────────────────── Visualizar dietas ───────────────────────────
type DietaRow = { id: number; lote: number; responsavel?: string | null; data_abertura: string; data_prevista_encerramento?: string | null; data_efetivo_encerramento?: string | null; ativa: boolean };

function VisualizarDietas() {
  const [dietas, setDietas] = useState<DietaRow[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aberta, setAberta] = useState<number | null>(null);
  const [apres, setApres] = useState<Record<number, ApresentacaoDieta | null>>({});

  useEffect(() => { fetchDietas().then(setDietas).catch((e) => setErro(e.message)); }, []);

  function toggle(id: number) {
    setAberta((cur) => (cur === id ? null : id));
    if (aberta !== id && !(id in apres)) {
      setApres((a) => ({ ...a, [id]: null }));
      fetchApresentacaoDieta(id).then((d) => setApres((a) => ({ ...a, [id]: d }))).catch(() => setApres((a) => ({ ...a, [id]: null })));
    }
  }

  if (erro) return <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>;
  if (!dietas) return <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>;

  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table">
        <thead><tr><th></th><th>Lote</th><th>Responsável</th><th>Início</th><th>Provável fim</th><th>Situação</th></tr></thead>
        <tbody>
          {dietas.map((d) => (
            <Fragment key={d.id}>
              <tr onClick={() => toggle(d.id)} style={{ cursor: "pointer" }}>
                <td>{aberta === d.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</td>
                <td style={{ fontWeight: 700 }}>{d.lote}</td>
                <td style={{ fontSize: "0.78rem" }}>{d.responsavel || "—"}</td>
                <td style={{ fontSize: "0.78rem" }}>{formatDate(d.data_abertura)}</td>
                <td style={{ fontSize: "0.78rem" }}>{formatDate(d.data_prevista_encerramento)}</td>
                <td>
                  <span style={{ fontSize: "0.72rem", fontWeight: 700, color: d.ativa ? "var(--green-light)" : "var(--text-muted)" }}>
                    {d.ativa ? "Ativa" : `Encerrada em ${formatDate(d.data_efetivo_encerramento)}`}
                  </span>
                </td>
              </tr>
              {aberta === d.id && (
                <tr><td colSpan={6} style={{ padding: 0 }}>
                  <div style={{ background: "var(--surface-2)", padding: "0.85rem" }}>
                    {apres[d.id] === null ? <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Carregando apresentação…</p> : apres[d.id] && <ApresentacaoBox a={apres[d.id]!} />}
                  </div>
                </td></tr>
              )}
            </Fragment>
          ))}
          {!dietas.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma dieta lançada ainda.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function ApresentacaoBox({ a }: { a: ApresentacaoDieta }) {
  return (
    <div>
      <div style={{ fontSize: "0.8rem", marginBottom: "0.5rem" }}>
        <strong>Lote {a.lote}{a.nome ? ` · ${a.nome}` : ""}</strong> — {a.qtd_animais} {a.qtd_animais === 1 ? "animal" : "animais"} · {a.num_tratos} tratos/dia
      </div>
      <table className="fazenda-table" style={{ margin: 0 }}>
        <thead><tr>
          <th>Produto</th>
          <th style={{ textAlign: "right" }}>Por cabeça/dia</th>
          <th style={{ textAlign: "right" }}>Total/dia</th>
          <th style={{ textAlign: "right" }}>Total/trato</th>
        </tr></thead>
        <tbody>
          {a.itens.map((it, i) => (
            <tr key={i}>
              <td style={{ fontWeight: 700 }}>{it.alimento}</td>
              <td style={{ textAlign: "right" }}>{it.por_cabeca != null ? `${num(it.por_cabeca, 3)} ${it.unidade}` : "—"}</td>
              <td style={{ textAlign: "right", color: "var(--amber)", fontWeight: 600 }}>{num(it.total_dia)} {it.unidade}</td>
              <td style={{ textAlign: "right", color: "var(--green-light)", fontWeight: 700 }}>{num(it.total_trato)} {it.unidade}</td>
            </tr>
          ))}
          {!a.itens.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Sem produtos.</td></tr>}
        </tbody>
      </table>
      <div style={{ marginTop: "0.6rem", fontSize: "0.85rem", fontWeight: 700 }}>
        Somatório no vagão: <span style={{ color: "var(--dourado-light)" }}>{num(a.vagao_kg_dia)} kg/dia</span>
        <span style={{ color: "var(--text-muted)", fontWeight: 500 }}> · {num(a.vagao_kg_trato)} kg por trato</span>
      </div>
    </div>
  );
}
