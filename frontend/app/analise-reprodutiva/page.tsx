"use client";
import { useEffect, useMemo, useState } from "react";
import { HeartPulse, AlertTriangle, Filter } from "lucide-react";
import { fetchServicosAnalise } from "@/lib/api";

type Reg = {
  numero: string; raca: string; categoria: string;
  ordem_parto: number | null; ordem_tentativa: number | null;
  tipo_servico: string; protocolo: string; inseminador: string;
  ano: number | null; mes: string | null; data: string | null; del_servico: number | null;
  diagnostico: string | null; diagnosticado: boolean; positivo: boolean; perda: boolean;
};

// Dimensões que o usuário pode usar para filtrar e para quebrar os gráficos.
const DIMENSOES: { key: keyof Reg; label: string }[] = [
  { key: "ano", label: "Ano" },
  { key: "raca", label: "Raça" },
  { key: "tipo_servico", label: "Tipo de serviço" },
  { key: "inseminador", label: "Inseminador" },
  { key: "ordem_parto", label: "Ordem de parto" },
  { key: "ordem_tentativa", label: "Ordem de tentativa" },
];

function opcoes(regs: Reg[], key: keyof Reg): string[] {
  const s = new Set<string>();
  regs.forEach((r) => { const v = r[key]; if (v !== null && v !== undefined && v !== "") s.add(String(v)); });
  return Array.from(s).sort((a, b) => (isNaN(+a) || isNaN(+b) ? a.localeCompare(b) : +a - +b));
}

function taxa(regs: Reg[]) {
  const diag = regs.filter((r) => r.diagnosticado).length;
  const pos = regs.filter((r) => r.positivo).length;
  return { diag, pos, pct: diag ? Math.round((1000 * pos) / diag) / 10 : null };
}

// Gráfico combo: colunas = serviços diagnosticados, linha = taxa de concepção (%).
function ComboChart({ dados }: { dados: { mes: string; diag: number; pct: number | null }[] }) {
  const W = 760, H = 260, m = { t: 16, r: 44, b: 46, l: 40 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const maxDiag = Math.max(1, ...dados.map((d) => d.diag));
  const bw = dados.length ? (iw / dados.length) * 0.6 : 0;
  const x = (i: number) => m.l + (iw / Math.max(1, dados.length)) * (i + 0.5);
  const yBar = (v: number) => m.t + ih - (v / maxDiag) * ih;
  const yPct = (v: number) => m.t + ih - (v / 100) * ih;
  const pts = dados.map((d, i) => (d.pct === null ? null : `${x(i)},${yPct(d.pct)}`)).filter(Boolean) as string[];

  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ minWidth: 520 }} role="img">
        {[0, 25, 50, 75, 100].map((g) => (
          <g key={g}>
            <line x1={m.l} x2={W - m.r} y1={yPct(g)} y2={yPct(g)} stroke="var(--border)" strokeWidth="1" />
            <text x={W - m.r + 6} y={yPct(g) + 3} fontSize="9" fill="var(--text-muted)">{g}%</text>
          </g>
        ))}
        {dados.map((d, i) => (
          <rect key={i} x={x(i) - bw / 2} y={yBar(d.diag)} width={bw} height={m.t + ih - yBar(d.diag)}
            fill="var(--blue)" opacity="0.55" rx="2">
            <title>{d.mes}: {d.diag} serviços{d.pct !== null ? `, ${d.pct}% concepção` : ""}</title>
          </rect>
        ))}
        {pts.length > 1 && <polyline points={pts.join(" ")} fill="none" stroke="var(--dourado-light)" strokeWidth="2" />}
        {dados.map((d, i) => d.pct === null ? null : (
          <circle key={i} cx={x(i)} cy={yPct(d.pct)} r="3" fill="var(--dourado-light)"><title>{d.mes}: {d.pct}%</title></circle>
        ))}
        {dados.map((d, i) => (
          <text key={i} x={x(i)} y={H - m.b + 14} fontSize="8" fill="var(--text-muted)" textAnchor="middle"
            transform={`rotate(45 ${x(i)} ${H - m.b + 14})`}>{d.mes.slice(2)}</text>
        ))}
      </svg>
      <div style={{ display: "flex", gap: "1rem", fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
        <span><span style={{ color: "var(--blue)" }}>▬</span> serviços diagnosticados</span>
        <span><span style={{ color: "var(--dourado-light)" }}>▬</span> taxa de concepção</span>
      </div>
    </div>
  );
}

export default function AnaliseReprodutivaPage() {
  const [regs, setRegs] = useState<Reg[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filtros, setFiltros] = useState<Record<string, string>>({});
  const [dimensao, setDimensao] = useState<keyof Reg>("raca");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");

  useEffect(() => {
    fetchServicosAnalise()
      .then((d) => setRegs(d.servicos))
      .catch((e) => setError(e.message));
  }, []);

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((r) =>
      (!ini || (r.data ? r.data >= ini : false)) &&
      (!fim || (r.data ? r.data <= fim : false)) &&
      DIMENSOES.every(({ key }) => {
        const f = filtros[key as string];
        return !f || String(r[key]) === f;
      }));
  }, [regs, filtros, ini, fim]);

  const kpi = taxa(filtrados);
  const perdas = filtrados.filter((r) => r.perda).length;

  const serieMes = useMemo(() => {
    const byMes = new Map<string, Reg[]>();
    filtrados.forEach((r) => { if (r.mes) { (byMes.get(r.mes) ?? byMes.set(r.mes, []).get(r.mes)!).push(r); } });
    return Array.from(byMes.keys()).sort().slice(-18).map((mes) => {
      const t = taxa(byMes.get(mes)!);
      return { mes, diag: t.diag, pct: t.pct };
    });
  }, [filtrados]);

  const quebra = useMemo(() => {
    const by = new Map<string, Reg[]>();
    filtrados.forEach((r) => {
      const k = String(r[dimensao] ?? "—");
      (by.get(k) ?? by.set(k, []).get(k)!).push(r);
    });
    return Array.from(by.entries())
      .map(([k, arr]) => ({ k, ...taxa(arr), n: arr.length }))
      .filter((x) => x.diag > 0)
      .sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0));
  }, [filtrados, dimensao]);

  const selStyle: React.CSSProperties = {
    background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
    borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <HeartPulse size={22} style={{ color: "var(--dourado-light)" }} />
          Análise Reprodutiva
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Taxa de concepção e perda de prenhez — filtre e cruze por qualquer dimensão.
        </p>
      </div>

      {error && (
        <div className="alert-critico mb-4">
          <AlertTriangle size={18} />
          <span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload do reprodutivo</a>.</span>
        </div>
      )}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && (
        <>
          {/* Filtros */}
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              <div>
                <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Período — de</label>
                <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} />
              </div>
              <div>
                <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>até</label>
                <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} />
              </div>
              {DIMENSOES.map(({ key, label }) => (
                <div key={key as string}>
                  <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>{label}</label>
                  <select style={selStyle} value={filtros[key as string] ?? ""}
                    onChange={(e) => setFiltros((p) => ({ ...p, [key as string]: e.target.value }))}>
                    <option value="">Todos</option>
                    {opcoes(regs, key).map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
              ))}
            </div>
            {Object.values(filtros).some(Boolean) && (
              <button onClick={() => setFiltros({})} className="btn-ghost" style={{ marginTop: "0.75rem", fontSize: "0.75rem" }}>
                Limpar filtros
              </button>
            )}
          </div>

          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{kpi.pct === null ? "—" : `${kpi.pct}%`}</p><p className="kpi-label">Taxa de concepção</p></div>
            <div className="kpi-card"><p className="kpi-value">{kpi.diag}</p><p className="kpi-label">Serviços diagnosticados</p></div>
            <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--blue)" }}>{kpi.pos}</p><p className="kpi-label">Positivos</p></div>
            <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--amber)" }}>{perdas}</p><p className="kpi-label">Perdas de prenhez</p></div>
          </div>

          {/* Combo por mês */}
          <div className="card mb-4">
            <div className="card-header mb-2">Concepção por Mês (serviços × taxa)</div>
            {serieMes.length ? <ComboChart dados={serieMes} /> : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem serviços no filtro atual.</p>}
          </div>

          {/* Quebra por dimensão */}
          <div className="card">
            <div className="card-header mb-3 flex items-center gap-2" style={{ flexWrap: "wrap" }}>
              <span>Concepção por</span>
              <select style={{ ...selStyle, width: "auto" }} value={dimensao as string} onChange={(e) => setDimensao(e.target.value as keyof Reg)}>
                {DIMENSOES.map((d) => <option key={d.key as string} value={d.key as string}>{d.label}</option>)}
              </select>
            </div>
            <div className="space-y-2">
              {quebra.map((row) => (
                <div key={row.k} className="flex items-center gap-3">
                  <span style={{ fontSize: "0.78rem", minWidth: "9rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{row.k}</span>
                  <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: "4px", height: "18px", overflow: "hidden" }}>
                    <div style={{ width: `${row.pct ?? 0}%`, height: "100%", background: "var(--green-light)", minWidth: "2px" }} />
                  </div>
                  <span style={{ fontSize: "0.78rem", fontWeight: 700, minWidth: "8.5rem", textAlign: "right" }}>
                    {row.pct}% <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>({row.pos}/{row.diag})</span>
                  </span>
                </div>
              ))}
              {!quebra.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem dados diagnosticados no filtro atual.</p>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
