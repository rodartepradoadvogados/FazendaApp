"use client";
import { useEffect, useMemo, useState } from "react";
import { Heart, AlertTriangle, Filter, Search } from "lucide-react";
import { fetchServicosAnalise } from "@/lib/api";

type Serv = {
  numero: string; raca: string; categoria: string;
  ordem_parto: number | null; ordem_tentativa: number | null;
  tipo_servico: string; touro: string; metodo_ia?: string;
  data: string | null; del_servico: number | null;
  diagnostico: string | null; diagnosticado: boolean; positivo: boolean; perda: boolean;
};

const DIAG_COR: Record<string, string> = { POSITIVO: "var(--green-light)", NEGATIVO: "var(--red)", ABERTO: "var(--amber)" };
const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
const isoOf = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const ddmm = (d: Date) => d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

export default function ReproducaoPage() {
  const [regs, setRegs] = useState<Serv[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [animal, setAnimal] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [ordemParto, setOrdemParto] = useState("");
  const [tipo, setTipo] = useState("");
  const [diag, setDiag] = useState("");
  // Filtro por DATA (de/até) OU por CICLO reprodutivo (janelas de 21 dias).
  const [modo, setModo] = useState<"data" | "ciclo">("data");
  const [cicloSel, setCicloSel] = useState<"2" | "3" | "esp">("2");
  const [cicloIdx, setCicloIdx] = useState(0);

  useEffect(() => { fetchServicosAnalise().then((d) => setRegs(d.servicos)).catch((e) => setError(e.message)); }, []);

  // Ciclos de 21 dias ancorados na data de serviço mais recente (proxy da última
  // visita reprodutiva/implante, até termos as datas de implante lançadas).
  const ciclos = useMemo(() => {
    const datas = (regs ?? []).map((s) => s.data).filter(Boolean).sort() as string[];
    if (!datas.length) return [] as { idx: number; ini: Date; fim: Date }[];
    const anchor = new Date(datas[datas.length - 1] + "T00:00:00");
    const primeiro = new Date(datas[0] + "T00:00:00");
    const arr: { idx: number; ini: Date; fim: Date }[] = [];
    for (let i = 0; i < 80; i++) {
      const fimC = new Date(anchor); fimC.setDate(fimC.getDate() - 21 * i);
      const iniC = new Date(fimC); iniC.setDate(iniC.getDate() - 20);
      arr.push({ idx: i, ini: iniC, fim: fimC });
      if (iniC <= primeiro) break;
    }
    return arr;
  }, [regs]);

  const janelas = useMemo(() => {
    if (modo !== "ciclo" || !ciclos.length) return null;
    const sel = cicloSel === "2" ? ciclos.slice(0, 2) : cicloSel === "3" ? ciclos.slice(0, 3) : ciclos.filter((c) => c.idx === cicloIdx);
    return sel.map((c) => [isoOf(c.ini), isoOf(c.fim)] as [string, string]);
  }, [modo, ciclos, cicloSel, cicloIdx]);

  const opc = (f: (s: Serv) => string | null) => {
    const set = new Set<string>(); (regs ?? []).forEach((s) => { const v = f(s); if (v) set.add(v); });
    return Array.from(set).sort((a, b) => (isNaN(+a) || isNaN(+b) ? a.localeCompare(b) : +a - +b));
  };

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((s) =>
      (!animal || s.numero.toLowerCase().includes(animal.toLowerCase())) &&
      (modo === "data"
        ? (!ini || (s.data ? s.data >= ini : false)) && (!fim || (s.data ? s.data <= fim : false))
        : (!janelas || (s.data ? janelas.some(([a, b]) => s.data! >= a && s.data! <= b) : false))) &&
      (!ordemParto || String(s.ordem_parto) === ordemParto) &&
      (!tipo || s.tipo_servico === tipo) &&
      (!diag || (s.diagnostico || "ABERTO") === diag)
    ).sort((a, b) => ((a.data || "") < (b.data || "") ? 1 : -1));
  }, [regs, animal, ini, fim, ordemParto, tipo, diag, modo, janelas]);

  const diagnosticados = filtrados.filter((s) => s.diagnosticado).length;
  const positivos = filtrados.filter((s) => s.positivo).length;
  const taxa = diagnosticados ? Math.round((1000 * positivos) / diagnosticados) / 10 : null;
  const perdas = filtrados.filter((s) => s.perda).length;

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Heart size={22} style={{ color: "var(--dourado)" }} /> Reprodução</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Serviços por animal — filtre por data ou por ciclo reprodutivo (21 dias), ordem de parto/tentativa, tipo e diagnóstico.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o reprodutivo</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && <>
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
          {/* Alternância: por data (de/até) OU por ciclo reprodutivo (21 dias). */}
          <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
            {([["data", "Por data"], ["ciclo", "Por ciclo (21 dias)"]] as const).map(([k, t]) => (
              <button key={k} onClick={() => setModo(k)}
                style={{ fontSize: "0.72rem", padding: "0.25rem 0.7rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (modo === k ? "var(--dourado)" : "var(--border)"),
                  background: modo === k ? "var(--dourado)" : "transparent",
                  color: modo === k ? "#1a1a1a" : "var(--text-muted)", fontWeight: modo === k ? 700 : 400 }}>{t}</button>
            ))}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
              <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={animal} onChange={(e) => setAnimal(e.target.value)} placeholder="ex.: 068" /></div></div>
            {modo === "data" ? (
              <>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label><input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label><input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
              </>
            ) : (
              <>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ciclo</label>
                  <select style={selStyle} value={cicloSel} onChange={(e) => setCicloSel(e.target.value as any)}>
                    <option value="2">Últimos 2 ciclos</option>
                    <option value="3">Últimos 3 ciclos</option>
                    <option value="esp">Ciclo específico</option>
                  </select></div>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Qual ciclo</label>
                  <select style={selStyle} value={cicloIdx} disabled={cicloSel !== "esp"} onChange={(e) => setCicloIdx(Number(e.target.value))}>
                    {ciclos.map((c) => <option key={c.idx} value={c.idx}>{c.idx === 0 ? "Atual" : `${c.idx + 1}º`} ({ddmm(c.ini)}–{ddmm(c.fim)})</option>)}
                  </select></div>
              </>
            )}
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ordem de parto</label>
              <select style={selStyle} value={ordemParto} onChange={(e) => setOrdemParto(e.target.value)}><option value="">Todas</option>{opc((s) => s.ordem_parto === null ? null : String(s.ordem_parto)).map((o) => <option key={o}>{o}</option>)}</select></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Tipo</label>
              <select style={selStyle} value={tipo} onChange={(e) => setTipo(e.target.value)}><option value="">Todos</option>{opc((s) => s.tipo_servico).map((o) => <option key={o}>{o}</option>)}</select></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Diagnóstico</label>
              <select style={selStyle} value={diag} onChange={(e) => setDiag(e.target.value)}><option value="">Todos</option>{["POSITIVO", "NEGATIVO", "ABERTO"].map((o) => <option key={o}>{o}</option>)}</select></div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="kpi-card"><p className="kpi-value">{filtrados.length}</p><p className="kpi-label">Serviços</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{positivos}</p><p className="kpi-label">Prenhezes</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--blue)" }}>{taxa === null ? "—" : `${taxa}%`}</p><p className="kpi-label">Concepção / serviço</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--amber)" }}>{perdas}</p><p className="kpi-label">Perdas de prenhez</p></div>
        </div>

        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between"><span>Serviços</span><span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span></div>
          <div className="overflow-x-auto" style={{ maxHeight: "560px" }}>
            <table className="fazenda-table">
              <thead><tr><th>Matriz</th><th>Data serviço</th><th>Tipo</th><th>Diagnóstico</th><th style={{ textAlign: "right" }}>Ord. parto</th><th style={{ textAlign: "right" }}>Tentativa</th><th style={{ textAlign: "right" }}>DEL</th><th>Touro</th></tr></thead>
              <tbody>
                {filtrados.slice(0, 500).map((s, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 700 }}>{s.numero}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(s.data)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{s.tipo_servico}</td>
                    <td><span style={{ color: DIAG_COR[s.diagnostico || "ABERTO"] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{s.diagnostico || "ABERTO"}</span></td>
                    <td style={{ textAlign: "right" }}>{s.ordem_parto ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>{s.ordem_tentativa ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>{s.del_servico ?? "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{s.touro}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtrados.length > 500 && <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>Mostrando 500 de {filtrados.length} — refine os filtros.</p>}
          </div>
        </div>
      </>}
    </div>
  );
}
