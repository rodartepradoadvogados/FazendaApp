"use client";
import { useEffect, useMemo, useState } from "react";
import { Beef, AlertTriangle, Filter, Search, ChevronDown, ChevronRight } from "lucide-react";
import { fetchAnimais } from "@/lib/api";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";

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

export default function RebanhoPage() {
  const [regs, setRegs] = useState<Animal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fGrupo, setFGrupo] = useState("");
  const [fSit, setFSit] = useState("");
  const [fRaca, setFRaca] = useState("");
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
      (!fGrupo || a.grupo_primario === fGrupo) &&
      (!fSit || a.sit_rep === fSit) &&
      (!fRaca || a.raca === fRaca) &&
      (!busca || a.numero.toLowerCase().includes(busca.toLowerCase()))
    );
  }, [regs, fGrupo, fSit, fRaca, busca]);

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
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Fêmeas do rebanho — filtre por grupo, situação reprodutiva, raça ou número.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Upload CSV</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && (
        <>
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Grupo</label>
                <select style={selStyle} value={fGrupo} onChange={(e) => setFGrupo(e.target.value)}><option value="">Todos</option>{opc((a) => a.grupo_primario).map((o) => <option key={o}>{o}</option>)}</select></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Situação rep.</label>
                <select style={selStyle} value={fSit} onChange={(e) => setFSit(e.target.value)}><option value="">Todas</option>{opc((a) => a.sit_rep).map((o) => <option key={o}>{o}</option>)}</select></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Raça</label>
                <select style={selStyle} value={fRaca} onChange={(e) => setFRaca(e.target.value)}><option value="">Todas</option>{opc((a) => a.raca).map((o) => <option key={o}>{o}</option>)}</select></div>
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
              <div className="card-header mb-3">Composição por Grupo</div>
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
              <div className="card-header mb-3">Situação Reprodutiva</div>
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
                <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                  onClick={() => setAbertos((p) => p.size === grupoLista.length ? new Set() : new Set(grupoLista.map(([g]) => g)))}>
                  {abertos.size === grupoLista.length && grupoLista.length ? "Recolher tudo" : "Expandir tudo"}
                </button>
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
