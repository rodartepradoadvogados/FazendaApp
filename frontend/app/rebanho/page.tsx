"use client";
import { useEffect, useMemo, useState } from "react";
import { Beef, AlertTriangle, Filter, Search, ChevronDown, ChevronRight, ChevronsDown, ChevronsUp, ArrowRightLeft, Sparkles, Skull, ShoppingCart, FileText } from "lucide-react";
import { fetchAnimais, fetchEstratificacaoRebanho, type Estratificacao } from "@/lib/api";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";
import MovimentarAnimais from "@/components/MovimentarAnimais";
import SugestoesMovimentacao from "@/components/SugestoesMovimentacao";
import BaixarAnimal from "@/components/BaixarAnimal";
import ComprarAnimal from "@/components/ComprarAnimal";
import FichaAnimal from "@/components/FichaAnimal";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { TabBar, MultiFiltro } from "@/components/ui";

const COLUNAS_REBANHO = [
  { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo_primario" },
  { header: "Categoria", key: "categoria" }, { header: "Raça", key: "raca" },
  { header: "Sit. Rep.", key: "sit_rep" }, { header: "DEL", key: "del_dias" },
  { header: "Últ. CL (kg)", key: "ult_cl_kg" },
];

type Animal = {
  numero: string; grupo_primario: string | null; categoria_abrev: string | null;
  categoria_completa: string | null; raca: string | null; sit_rep: string | null;
  del_dias: number | null; ult_cl_kg: number | null; diagnostico: string | null;
};

const SIT_CORES: Record<string, string> = {
  "Ges.": "var(--green-light)", "Vaz. apt.": "var(--blue)", "Vaz. atr.": "var(--red)",
  "Vaz. pev": "var(--amber)", "Ins.": "var(--dourado-light)",
};
const LACTACAO = ["01", "02", "03"];
const cod = (g: string | null) => (g && g.length >= 2 && /\d\d/.test(g.slice(0, 2)) ? g.slice(0, 2) : null);

// Estratificação do rebanho por faixa etária + composição das vacas adultas,
// com o indicador de % de vacas em lactação sobre o total.
const ESTRATOS_ROTULO: [string, string, string][] = [
  ["aleitamento_0_3m", "Aleitamento (0–3 m)", "#C6A24A"],
  ["recria_4_11m", "Recria (4–11 m)", "#A9791F"],
  ["recria_12_24m", "Recria (12–24 m)", "#8A6a3a"],
  ["novilhas_acima_24m", "Novilhas (>24 m)", "#7C2740"],
  ["vacas_lactacao", "Vacas em lactação", "#4C7A3C"],
  ["vacas_secas", "Vacas secas", "#B47C1E"],
  ["vacas_pre_parto", "Vacas pré-parto", "#2E5A7C"],
];

function EstratificacaoRebanho() {
  const [d, setD] = useState<Estratificacao | null>(null);
  useEffect(() => { fetchEstratificacaoRebanho().then(setD).catch(() => setD(null)); }, []);
  if (!d || !d.total) return null;
  const dados = ESTRATOS_ROTULO
    .map(([k, label, cor]) => ({ label, cor, n: d.estratos[k] || 0, pct: d.percentuais[k] || 0 }))
    .filter((x) => x.n > 0);
  return (
    <div className="card mb-4">
      <div className="card-header mb-3 flex items-center gap-2"><Beef size={14} /> Composição do rebanho ({d.total} fêmeas)</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
        <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{d.pct_lactacao_sobre_total}%</p><p className="kpi-label">Vacas em lactação / total</p></div>
        <div className="kpi-card"><p className="kpi-value">{d.pct_lactacao_sobre_vacas}%</p><p className="kpi-label">Em lactação / vacas</p></div>
        <div className="kpi-card"><p className="kpi-value">{d.estratos.vacas_lactacao}</p><p className="kpi-label">Vacas em lactação</p></div>
        <div className="kpi-card"><p className="kpi-value">{d.vacas_total}</p><p className="kpi-label">Vacas (adultas)</p></div>
      </div>
      {/* Barra empilhada 100% */}
      <div style={{ display: "flex", height: 26, borderRadius: 8, overflow: "hidden", border: "1px solid var(--border)" }}>
        {dados.map((x) => (
          <div key={x.label} title={`${x.label}: ${x.n} (${x.pct}%)`} style={{ width: `${x.pct}%`, background: x.cor, minWidth: x.pct > 0 ? 2 : 0 }} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2" style={{ fontSize: "0.74rem" }}>
        {dados.map((x) => (
          <span key={x.label} className="flex items-center gap-1">
            <span style={{ width: 10, height: 10, borderRadius: 2, background: x.cor, display: "inline-block" }} /> {x.label}: <strong>{x.n}</strong> ({x.pct}%)
          </span>
        ))}
      </div>
      {(d.estratos as any).sem_data_nasc > 0 && (
        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>{(d.estratos as any).sem_data_nasc} animal(is) sem data de nascimento não entraram nas faixas etárias.</p>
      )}
    </div>
  );
}

function RebanhoVisaoGeral() {
  const [regs, setRegs] = useState<Animal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fGrupo, setFGrupo] = useState<string[]>([]);
  const [fSit, setFSit] = useState<string[]>([]);
  const [busca, setBusca] = useState("");
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const toggle = (g: string) => setAbertos((p) => { const n = new Set(p); n.has(g) ? n.delete(g) : n.add(g); return n; });
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);

  useEffect(() => {
    fetchAnimais().then(setRegs).catch((e) => setError(e.message));
  }, []);

  const opc = (f: (a: Animal) => string | null) => {
    const s = new Set<string>(); (regs ?? []).forEach((a) => { const v = f(a); if (v) s.add(v); });
    return Array.from(s).sort();
  };

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((a) =>
      (fGrupo.length === 0 || (a.grupo_primario ? fGrupo.includes(a.grupo_primario) : false)) &&
      (fSit.length === 0 || (a.sit_rep ? fSit.includes(a.sit_rep) : false)) &&
      (!busca || a.numero.toLowerCase().includes(busca.toLowerCase()))
    );
  }, [regs, fGrupo, fSit, busca]);

  const total = filtrados.length;
  const gestantes = filtrados.filter((a) => a.sit_rep === "Ges.").length;
  const vazias = filtrados.filter((a) => (a.sit_rep || "").startsWith("Vaz.")).length;
  const delLact = filtrados.filter((a) => LACTACAO.includes(cod(a.grupo_primario) || "") && a.del_dias).map((a) => a.del_dias!);
  const delMedio = delLact.length ? Math.round(delLact.reduce((x, y) => x + y, 0) / delLact.length) : null;

  const porGrupo = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => { const g = a.grupo_primario || "(sem grupo)"; by.set(g, (by.get(g) ?? 0) + 1); });
    return Array.from(by.entries()).map(([grupo, n]) => ({ grupo, n })).sort((a, b) => a.grupo.localeCompare(b.grupo));
  }, [filtrados]);

  const porSit = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => { const s = a.sit_rep || "(sem)"; by.set(s, (by.get(s) ?? 0) + 1); });
    return Array.from(by.entries()).map(([sit, n]) => ({ sit, n }));
  }, [filtrados]);

  const grupoLista = useMemo(() => {
    const by = new Map<string, Animal[]>();
    filtrados.forEach((a) => { const g = a.grupo_primario || "(sem grupo)"; (by.get(g) ?? by.set(g, []).get(g)!).push(a); });
    return Array.from(by.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtrados]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text)", fontSize: "0.8rem" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Beef size={22} style={{ color: "var(--dourado)" }} /> Rebanho</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Fêmeas do rebanho — filtre por grupo, situação reprodutiva ou número.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Upload CSV</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && (
        <>
          <EstratificacaoRebanho />
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <MultiFiltro label="Grupo / lote" opcoes={opc((a) => a.grupo_primario)} selecionados={fGrupo} onChange={setFGrupo} />
              <MultiFiltro label="Situação rep." opcoes={opc((a) => a.sit_rep)} selecionados={fSit} onChange={setFSit} />
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Buscar nº</label>
                <div style={{ position: "relative" }}>
                  <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
                  <input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 068" />
                </div></div>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="kpi-card"><p className="kpi-value">{total}</p><p className="kpi-label">Fêmeas (filtro)</p></div>
            <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{gestantes}</p><p className="kpi-label">Gestantes</p></div>
            <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--amber)" }}>{vazias}</p><p className="kpi-label">Vazias</p></div>
            <div className="kpi-card"><p className="kpi-value">{delMedio ?? "—"}</p><p className="kpi-label">DEL médio (lactação)</p></div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div className="card">
              <div className="card-header mb-3">Composição por Grupo <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>(clique para ver os animais)</span></div>
              <ResponsiveContainer width="100%" height={Math.max(200, porGrupo.length * 26)}>
                <BarChart data={porGrupo} layout="vertical" margin={{ left: 8 }}>
                  <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 10 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="grupo" tick={{ fill: "var(--text-muted)", fontSize: 9 }} width={150} />
                  <Tooltip contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                  <Bar dataKey="n" name="Fêmeas" fill="var(--vinho-light, #8B3A56)" radius={[0, 3, 3, 0]} style={{ cursor: "pointer" }}
                    onClick={(e: any) => e?.grupo && setModal({ title: e.grupo, list: filtrados.filter((a) => (a.grupo_primario || "(sem grupo)") === e.grupo) })} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="card">
              <div className="card-header mb-3">Situação Reprodutiva <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>(clique para ver os animais)</span></div>
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={porSit} dataKey="n" nameKey="sit" cx="50%" cy="50%" outerRadius={80} label={(e: any) => `${e.sit} (${e.n})`} labelLine={false} fontSize={10}
                    style={{ cursor: "pointer" }}
                    onClick={(e: any) => { const sit = e?.sit; if (!sit) return; setModal({ title: `Situação: ${sit}`, list: filtrados.filter((a) => (a.sit_rep || "(sem)") === sit) }); }}>
                    {porSit.map((s, i) => <Cell key={i} fill={SIT_CORES[s.sit] || "var(--text-muted)"} />)}
                  </Pie>
                  <Tooltip contentStyle={tip} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card">
            <div className="card-header mb-3 flex items-center justify-between">
              <span>Fêmeas por Grupo</span>
              <div className="flex items-center gap-3">
                <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{total} no filtro</span>
                <ExportarBotoes titulo="Rebanho" nomeArquivoBase="rebanho"
                  colunas={COLUNAS_REBANHO}
                  linhas={filtrados.map((a) => ({ ...a, categoria: a.categoria_abrev || a.categoria_completa }))} />
                {(() => {
                  const todosAbertos = abertos.size === grupoLista.length && grupoLista.length > 0;
                  return (
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                      title={todosAbertos ? "Recolher todos os grupos" : "Expandir todos os grupos"}
                      onClick={() => setAbertos((p) => p.size === grupoLista.length ? new Set() : new Set(grupoLista.map(([g]) => g)))}>
                      {todosAbertos ? <ChevronsUp size={14} /> : <ChevronsDown size={14} />}
                      {todosAbertos ? "Recolher tudo" : "Expandir tudo"}
                    </button>
                  );
                })()}
              </div>
            </div>
            <div className="space-y-2">
              {grupoLista.map(([grupo, lista]) => {
                const aberto = abertos.has(grupo);
                return (
                  <div key={grupo} style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
                    <button onClick={() => toggle(grupo)} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.55rem 0.9rem", background: "var(--surface-2)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                      {aberto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      <span style={{ flex: 1, fontSize: "0.85rem" }}>{grupo}</span>
                      <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)" }}>{lista.length} fêmea{lista.length !== 1 ? "s" : ""}</span>
                    </button>
                    {aberto && (
                      <div className="overflow-x-auto">
                        <table className="fazenda-table" style={{ margin: 0 }}>
                          <thead><tr><th>Nº</th><th>Categoria</th><th>Raça</th><th>Sit. Rep.</th><th style={{ textAlign: "right" }}>DEL</th><th style={{ textAlign: "right" }}>Últ. CL</th></tr></thead>
                          <tbody>
                            {lista.map((a) => (
                              <tr key={a.numero}>
                                <td style={{ fontWeight: 700 }}>{a.numero}</td>
                                <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || a.categoria_completa || "—"}</td>
                                <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.raca || "—"}</td>
                                <td><span style={{ color: SIT_CORES[a.sit_rep || ""] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{a.sit_rep || "—"}</span></td>
                                <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
                                <td style={{ textAlign: "right", fontWeight: 600 }}>{a.ult_cl_kg ? a.ult_cl_kg.toFixed(1) : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
              {!grupoLista.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma fêmea no filtro.</p>}
            </div>
          </div>
        </>
      )}

      {modal && <AnimalModal title={modal.title} animais={modal.list} onClose={() => setModal(null)} />}
    </div>
  );
}

type Aba = "visao" | "sugestoes" | "mover" | "baixar" | "comprar" | "ficha";
const ABAS_VALIDAS: Aba[] = ["visao", "sugestoes", "mover", "baixar", "comprar", "ficha"];

const ABAS_REBANHO = [
  { id: "visao", label: "Rebanho", icon: Beef, title: "Visão geral do rebanho por grupo" },
  { id: "ficha", label: "Ficha do animal", icon: FileText, title: "Ficha completa e editável de um animal" },
  { id: "mover", label: "Movimentar animais", icon: ArrowRightLeft, title: "Transferir animais entre lotes" },
  { id: "comprar", label: "Comprar animal", icon: ShoppingCart, title: "Registrar compra de animal" },
  { id: "baixar", label: "Baixar animal", icon: Skull, title: "Registrar morte/descarte/venda" },
  { id: "sugestoes", label: "Sugestões de movimentação", icon: Sparkles, title: "Sugestões automáticas de movimentação" },
] as const satisfies readonly { id: Aba; label: string; icon: any; title: string }[];

export default function RebanhoPage() {
  const [aba, setAba] = useState<Aba>("visao");
  // key da visão geral: incrementa ao (re)entrar na aba "visao" para refazer o fetch e evitar dados velhos.
  const [visaoKey, setVisaoKey] = useState(0);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const abaParam = params.get("aba") as Aba | null;
    if (abaParam && ABAS_VALIDAS.includes(abaParam)) setAba(abaParam);
  }, []);

  return (
    <div className="px-6 pt-6">
      <TabBar<Aba> abas={ABAS_REBANHO} ativa={aba} onChange={(k) => { if (k === "visao") setVisaoKey((v) => v + 1); setAba(k); }} />
      <div style={{ margin: "0 -1.5rem" }}>
        {aba === "visao" && <RebanhoVisaoGeral key={visaoKey} />}
        {aba === "sugestoes" && <div className="p-6"><SugestoesMovimentacao /></div>}
        {aba === "mover" && <MovimentarAnimais />}
        {aba === "baixar" && <BaixarAnimal />}
        {aba === "comprar" && <ComprarAnimal />}
        {aba === "ficha" && <FichaAnimal />}
      </div>
    </div>
  );
}
