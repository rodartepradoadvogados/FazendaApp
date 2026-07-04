"use client";
import { useEffect, useState } from "react";
import { BarChart3, TrendingDown, TrendingUp } from "lucide-react";
import { fetchDRE, formatBRL, firstDayOfMonth, today } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

export default function FinanceiroPage() {
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());
  const [regime, setRegime] = useState("competencia");
  const [dre, setDre] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const carregar = async () => {
    setLoading(true); setError("");
    try { setDre(await fetchDRE({ data_inicio: inicio, data_fim: fim, regime })); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { carregar(); }, []);

  const chartData = dre
    ? [
        { name: "Receitas", valor: dre.receitas_total, fill: "var(--green)" },
        { name: "Despesas", valor: dre.despesas_total, fill: "var(--red)" },
        { name: "Resultado", valor: Math.abs(dre.resultado), fill: dre.resultado >= 0 ? "var(--dourado)" : "var(--amber)" },
      ]
    : [];

  return (
    <div className="p-6 animate-in">
      <div className="mb-6 flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 size={22} style={{ color: "var(--dourado)" }} />
            Financeiro
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            DRE — Demonstrativo de Resultado
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <input type="date" value={inicio} onChange={e => setInicio(e.target.value)}
            style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.4rem 0.75rem", color: "var(--text)", fontSize: "0.875rem" }} />
          <input type="date" value={fim} onChange={e => setFim(e.target.value)}
            style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.4rem 0.75rem", color: "var(--text)", fontSize: "0.875rem" }} />
          <select value={regime} onChange={e => setRegime(e.target.value)}
            style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.4rem 0.75rem", color: "var(--text)", fontSize: "0.875rem" }}>
            <option value="competencia">Competência</option>
            <option value="caixa">Caixa</option>
          </select>
          <button onClick={carregar} className="btn-primary">Calcular</button>
        </div>
      </div>

      {error && <div className="alert-critico mb-4">{error}</div>}

      {dre && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="kpi-card">
              <div className="flex items-center gap-2">
                <TrendingUp size={16} style={{ color: "var(--green-light)" }} />
                <p className="kpi-label">Receitas</p>
              </div>
              <p className="kpi-value" style={{ fontSize: "1.5rem", color: "var(--green-light)" }}>
                {formatBRL(dre.receitas_total)}
              </p>
            </div>
            <div className="kpi-card">
              <div className="flex items-center gap-2">
                <TrendingDown size={16} style={{ color: "var(--red)" }} />
                <p className="kpi-label">Despesas</p>
              </div>
              <p className="kpi-value" style={{ fontSize: "1.5rem", color: "var(--red)" }}>
                {formatBRL(dre.despesas_total)}
              </p>
            </div>
            <div className="kpi-card">
              <p className="kpi-label">Resultado</p>
              <p className="kpi-value" style={{ fontSize: "1.5rem", color: dre.resultado >= 0 ? "var(--green-light)" : "var(--amber)" }}>
                {formatBRL(dre.resultado)}
              </p>
              <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Regime: {regime}
              </p>
            </div>
          </div>

          {/* Gráfico */}
          <div className="card mb-6">
            <div className="card-header mb-4">Visão Geral</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} barSize={60}>
                <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
                <YAxis tickFormatter={v => `R$${(v/1000).toFixed(0)}k`} tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <Tooltip
                  formatter={(v: any) => formatBRL(Number(v))}
                  contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text)" }}
                />
                <Bar dataKey="valor">
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Detalhes por conta */}
          {dre.por_conta && Object.keys(dre.por_conta).length > 0 && (
            <div className="card">
              <div className="card-header mb-3">Detalhamento por Conta</div>
              <table className="fazenda-table">
                <thead>
                  <tr>
                    <th>Conta Nível 1</th>
                    <th style={{ textAlign: "right" }}>Receitas</th>
                    <th style={{ textAlign: "right" }}>Despesas</th>
                    <th style={{ textAlign: "right" }}>Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(dre.por_conta).map(([conta, dados]: any) => {
                    const saldo = dados.receitas - dados.despesas;
                    return (
                      <tr key={conta}>
                        <td><strong>{conta}</strong> — <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{dados.descricao}</span></td>
                        <td style={{ textAlign: "right", color: "var(--green-light)" }}>{formatBRL(dados.receitas)}</td>
                        <td style={{ textAlign: "right", color: "var(--red)" }}>{formatBRL(dados.despesas)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(saldo)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {loading && (
        <div style={{ textAlign: "center", padding: "4rem", color: "var(--text-muted)" }}>
          Calculando DRE...
        </div>
      )}
    </div>
  );
}
