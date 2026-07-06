"use client";
import { useEffect, useMemo, useState } from "react";
import { BarChart3, TrendingUp, TrendingDown, Filter } from "lucide-react";
import { fetchLancamentos, formatBRL } from "@/lib/api";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, Cell,
} from "recharts";

type Lanc = {
  tipo: string; valor: number; centro_custo: string; codigo_conta: string;
  descricao: string; fornecedor: string;
  mes_competencia: string | null; ano_competencia: number | null;
  mes_caixa: string | null; ano_caixa: number | null;
};

const brk = (v: number) => `R$${(v / 1000).toFixed(0)}k`;

export default function FinanceiroPage() {
  const [regs, setRegs] = useState<Lanc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [regime, setRegime] = useState<"competencia" | "caixa">("competencia");
  const [ano, setAno] = useState("");
  const [centro, setCentro] = useState("");

  useEffect(() => {
    fetchLancamentos().then((d) => setRegs(d.lancamentos)).catch((e) => setError(e.message));
  }, []);

  const mesDe = (r: Lanc) => (regime === "competencia" ? r.mes_competencia : r.mes_caixa);
  const anoDe = (r: Lanc) => (regime === "competencia" ? r.ano_competencia : r.ano_caixa);

  const anos = useMemo(() => {
    if (!regs) return [];
    const s = new Set<string>();
    regs.forEach((r) => { const a = anoDe(r); if (a) s.add(String(a)); });
    return Array.from(s).sort();
  }, [regs, regime]);
  const centros = useMemo(() => {
    if (!regs) return [];
    return Array.from(new Set(regs.map((r) => r.centro_custo))).sort();
  }, [regs]);

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((r) =>
      (!ano || String(anoDe(r)) === ano) &&
      (!centro || r.centro_custo === centro) &&
      mesDe(r) !== null
    );
  }, [regs, regime, ano, centro]);

  const receitas = filtrados.filter((r) => r.tipo === "receita").reduce((a, r) => a + r.valor, 0);
  const despesas = filtrados.filter((r) => r.tipo === "despesa").reduce((a, r) => a + r.valor, 0);
  const resultado = receitas - despesas;
  const margem = receitas > 0 ? Math.round((1000 * resultado) / receitas) / 10 : null;

  const porMes = useMemo(() => {
    const by = new Map<string, { mes: string; receita: number; despesa: number }>();
    filtrados.forEach((r) => {
      const m = mesDe(r)!;
      const e = by.get(m) ?? { mes: m, receita: 0, despesa: 0 };
      if (r.tipo === "receita") e.receita += r.valor; else e.despesa += r.valor;
      by.set(m, e);
    });
    return Array.from(by.values()).sort((a, b) => (a.mes < b.mes ? -1 : 1)).slice(-18);
  }, [filtrados, regime]);

  const porCentro = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.filter((r) => r.tipo === "despesa").forEach((r) => by.set(r.centro_custo, (by.get(r.centro_custo) ?? 0) + r.valor));
    return Array.from(by.entries()).map(([centro, valor]) => ({ centro, valor })).sort((a, b) => b.valor - a.valor);
  }, [filtrados]);

  const topCategorias = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.filter((r) => r.tipo === "despesa").forEach((r) => { const k = r.descricao || "(sem descrição)"; by.set(k, (by.get(k) ?? 0) + r.valor); });
    return Array.from(by.entries()).map(([desc, valor]) => ({ desc, valor })).sort((a, b) => b.valor - a.valor).slice(0, 10);
  }, [filtrados]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const tooltipStyle = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text)", fontSize: "0.8rem" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BarChart3 size={22} style={{ color: "var(--dourado)" }} /> Financeiro
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Receitas, despesas e resultado — filtre por regime, ano e centro de custo.</p>
      </div>

      {error && <div className="alert-critico mb-4"><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o CONTA_GERENCIAL</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && (
        <>
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Regime</label>
                <select style={selStyle} value={regime} onChange={(e) => setRegime(e.target.value as any)}>
                  <option value="competencia">Competência</option><option value="caixa">Caixa</option>
                </select></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ano</label>
                <select style={selStyle} value={ano} onChange={(e) => setAno(e.target.value)}>
                  <option value="">Todos</option>{anos.map((a) => <option key={a}>{a}</option>)}
                </select></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Centro de custo</label>
                <select style={selStyle} value={centro} onChange={(e) => setCentro(e.target.value)}>
                  <option value="">Todos</option>{centros.map((c) => <option key={c}>{c}</option>)}
                </select></div>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="kpi-card"><div className="flex items-center gap-2"><TrendingUp size={15} style={{ color: "var(--green-light)" }} /><p className="kpi-label">Receitas</p></div><p className="kpi-value" style={{ fontSize: "1.25rem", color: "var(--green-light)" }}>{formatBRL(receitas)}</p></div>
            <div className="kpi-card"><div className="flex items-center gap-2"><TrendingDown size={15} style={{ color: "var(--red)" }} /><p className="kpi-label">Despesas</p></div><p className="kpi-value" style={{ fontSize: "1.25rem", color: "var(--red)" }}>{formatBRL(despesas)}</p></div>
            <div className="kpi-card"><p className="kpi-label">Resultado</p><p className="kpi-value" style={{ fontSize: "1.25rem", color: resultado >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(resultado)}</p></div>
            <div className="kpi-card"><p className="kpi-label">Margem</p><p className="kpi-value" style={{ fontSize: "1.25rem", color: (margem ?? 0) >= 0 ? "var(--green-light)" : "var(--amber)" }}>{margem === null ? "—" : `${margem}%`}</p></div>
          </div>

          <div className="card mb-4">
            <div className="card-header mb-3">Evolução Mensal (receita × despesa)</div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={porMes} barGap={2}>
                <XAxis dataKey="mes" tick={{ fill: "var(--text-muted)", fontSize: 10 }} tickFormatter={(m) => m.slice(2)} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
                <Bar dataKey="receita" name="Receita" fill="var(--green-light)" radius={[2, 2, 0, 0]} />
                <Bar dataKey="despesa" name="Despesa" fill="var(--red)" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card">
              <div className="card-header mb-3">Despesas por Centro de Custo</div>
              <ResponsiveContainer width="100%" height={Math.max(160, porCentro.length * 48)}>
                <BarChart data={porCentro} layout="vertical" margin={{ left: 8 }}>
                  <XAxis type="number" tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                  <YAxis type="category" dataKey="centro" tick={{ fill: "var(--text-muted)", fontSize: 11 }} width={64} />
                  <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                  <Bar dataKey="valor" name="Despesa" radius={[0, 3, 3, 0]}>
                    {porCentro.map((_, i) => <Cell key={i} fill={["var(--vinho-light, #8B3A56)", "var(--amber)", "var(--blue)"][i % 3]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <div className="card-header mb-3">Top 10 Categorias de Despesa</div>
              <table className="fazenda-table">
                <thead><tr><th>Descrição</th><th style={{ textAlign: "right" }}>Valor</th></tr></thead>
                <tbody>
                  {topCategorias.map((c) => (
                    <tr key={c.desc}>
                      <td style={{ fontSize: "0.8rem" }}>{c.desc}</td>
                      <td style={{ textAlign: "right", color: "var(--red)", fontWeight: 600 }}>{formatBRL(c.valor)}</td>
                    </tr>
                  ))}
                  {!topCategorias.length && <tr><td colSpan={2} style={{ color: "var(--text-muted)" }}>Sem despesas no filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
