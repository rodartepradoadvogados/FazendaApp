"use client";
import { useEffect, useMemo, useState } from "react";
import { BarChart3, TrendingUp, TrendingDown, Filter, Wallet, BookOpen, FileText } from "lucide-react";
import { fetchLancamentos, formatBRL } from "@/lib/api";
import {
  ComposedChart, Bar, Line, LineChart, BarChart, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, Cell, CartesianGrid,
} from "recharts";

type Lanc = {
  tipo: string; valor: number; centro_custo: string; codigo_conta: string; conta_completa: string;
  descricao: string; fornecedor: string;
  data_competencia: string | null; data_pagamento: string | null;
  mes_competencia: string | null; mes_caixa: string | null;
};

type Rel = "fluxo" | "dre" | "livro";
const RELATORIOS: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "fluxo", label: "Fluxo de Caixa", icon: Wallet, desc: "Entradas × saídas por regime de caixa" },
  { id: "dre", label: "DRE Gerencial", icon: FileText, desc: "Resultado por competência" },
  { id: "livro", label: "Livro Caixa", icon: BookOpen, desc: "Lançamentos com saldo acumulado" },
];
const brk = (v: number) => `R$${(v / 1000).toFixed(0)}k`;
const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text)", fontSize: "0.8rem" };
const fmtMes = (m: string) => m?.slice(2) ?? "";
const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");

function KPI({ v, l, c }: { v: string; l: string; c?: string }) {
  return <div className="kpi-card"><p className="kpi-value" style={{ fontSize: "1.25rem", color: c }}>{v}</p><p className="kpi-label">{l}</p></div>;
}

export default function FinanceiroPage() {
  const [regs, setRegs] = useState<Lanc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rel, setRel] = useState<Rel>("fluxo");
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [centro, setCentro] = useState("");

  useEffect(() => { fetchLancamentos().then((d) => setRegs(d.lancamentos)).catch((e) => setError(e.message)); }, []);

  useEffect(() => {
    if (regs && !inicio) {
      const ds = regs.flatMap((r) => [r.data_pagamento, r.data_competencia]).filter(Boolean).sort() as string[];
      if (ds.length) { setInicio(ds[0]); setFim(ds[ds.length - 1]); }
    }
  }, [regs, inicio]);

  const centros = useMemo(() => Array.from(new Set((regs ?? []).map((r) => r.centro_custo))).sort(), [regs]);

  // Data relevante ao relatório: DRE = competência; fluxo/livro = pagamento.
  const campoData = (r: Lanc) => (rel === "dre" ? r.data_competencia : r.data_pagamento);
  const campoMes = (r: Lanc) => (rel === "dre" ? r.mes_competencia : r.mes_caixa);

  const filtrados = useMemo(() => {
    if (!regs || !inicio || !fim) return [];
    return regs.filter((r) => {
      const d = campoData(r);
      return d && d >= inicio && d <= fim && (!centro || r.centro_custo === centro);
    });
  }, [regs, rel, inicio, fim, centro]);

  const receitas = filtrados.filter((r) => r.tipo === "receita").reduce((a, r) => a + r.valor, 0);
  const despesas = filtrados.filter((r) => r.tipo === "despesa").reduce((a, r) => a + r.valor, 0);
  const resultado = receitas - despesas;

  // Fluxo de caixa mensal (com saldo acumulado)
  const fluxoMensal = useMemo(() => {
    const by = new Map<string, { mes: string; entradas: number; saidas: number }>();
    filtrados.forEach((r) => {
      const m = campoMes(r); if (!m) return;
      const e = by.get(m) ?? { mes: m, entradas: 0, saidas: 0 };
      if (r.tipo === "receita") e.entradas += r.valor; else e.saidas += r.valor;
      by.set(m, e);
    });
    let acc = 0;
    return Array.from(by.values()).sort((a, b) => a.mes.localeCompare(b.mes)).map((x) => {
      acc += x.entradas - x.saidas;
      return { ...x, saldo: x.entradas - x.saidas, acumulado: Math.round(acc) };
    });
  }, [filtrados, rel]);

  // DRE por conta gerencial (nível 1)
  const dreContas = useMemo(() => {
    const by = new Map<string, { conta: string; receitas: number; despesas: number }>();
    filtrados.forEach((r) => {
      const k = r.codigo_conta || "(sem conta)";
      const e = by.get(k) ?? { conta: k, receitas: 0, despesas: 0 };
      if (r.tipo === "receita") e.receitas += r.valor; else e.despesas += r.valor;
      by.set(k, e);
    });
    return Array.from(by.values()).map((x) => ({ ...x, saldo: x.receitas - x.despesas })).sort((a, b) => (b.receitas + b.despesas) - (a.receitas + a.despesas));
  }, [filtrados]);

  // Livro caixa (cronológico com saldo acumulado)
  const livro = useMemo(() => {
    let acc = 0;
    return [...filtrados].filter((r) => r.data_pagamento).sort((a, b) => (a.data_pagamento! < b.data_pagamento! ? -1 : 1)).map((r) => {
      const entrada = r.tipo === "receita" ? r.valor : 0;
      const saida = r.tipo === "despesa" ? r.valor : 0;
      acc += entrada - saida;
      return { data: r.data_pagamento, descricao: r.descricao, fornecedor: r.fornecedor, entrada, saida, saldo: Math.round(acc) };
    });
  }, [filtrados]);

  const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><BarChart3 size={22} style={{ color: "var(--dourado)" }} /> Financeiro</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Escolha o relatório, o período e o centro de custo — indicadores, consolidado e gráfico.</p>
      </div>

      {error && <div className="alert-critico mb-4"><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o CONTA_GERENCIAL</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && regs.length === 0 && !error && (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <BarChart3 size={38} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
          <p style={{ color: "var(--text-muted)" }}>Nenhum lançamento financeiro no banco.</p>
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
            Suba o <strong>CONTA_GERENCIAL.csv</strong> na tela de <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Upload</a>.
            Se você já subiu e sumiu, o banco de produção não está persistindo — confira o Postgres no Railway.
          </p>
        </div>
      )}

      {regs && regs.length > 0 && <>
        {/* Seletor de relatório */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          {RELATORIOS.map((r) => {
            const ativo = rel === r.id; const Icon = r.icon;
            return (
              <button key={r.id} onClick={() => setRel(r.id)} className="card" style={{ textAlign: "left", cursor: "pointer", border: ativo ? "1px solid var(--dourado)" : "1px solid var(--border)", background: ativo ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
                <div className="flex items-center gap-2" style={{ color: ativo ? "var(--dourado-light)" : "var(--text)" }}><Icon size={18} /><span style={{ fontWeight: 700 }}>{r.label}</span></div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>{r.desc}</p>
              </button>
            );
          })}
        </div>

        {/* Filtros */}
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
          <div className="flex flex-wrap gap-3 items-end">
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Início</label><input type="date" style={inputStyle} value={inicio} onChange={(e) => setInicio(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Fim</label><input type="date" style={inputStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Centro de custo</label>
              <select style={inputStyle} value={centro} onChange={(e) => setCentro(e.target.value)}><option value="">Todos</option>{centros.map((c) => <option key={c}>{c}</option>)}</select></div>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", paddingBottom: "0.4rem" }}>
              Regime: <strong style={{ color: "var(--dourado-light)" }}>{rel === "dre" ? "competência" : "caixa"}</strong> · {filtrados.length} lançamentos
            </span>
          </div>
        </div>

        {/* Indicadores consolidados */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          {rel === "fluxo" && <>
            <KPI v={formatBRL(receitas)} l="Entradas" c="var(--green-light)" />
            <KPI v={formatBRL(despesas)} l="Saídas" c="var(--red)" />
            <KPI v={formatBRL(resultado)} l="Saldo do período" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
            <KPI v={fluxoMensal.length ? formatBRL(fluxoMensal[fluxoMensal.length - 1].acumulado) : "—"} l="Saldo acumulado" c="var(--dourado-light)" />
          </>}
          {rel === "dre" && <>
            <KPI v={formatBRL(receitas)} l="Receita" c="var(--green-light)" />
            <KPI v={formatBRL(despesas)} l="Despesa" c="var(--red)" />
            <KPI v={formatBRL(resultado)} l="Resultado" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
            <KPI v={receitas > 0 ? `${Math.round((1000 * resultado) / receitas) / 10}%` : "—"} l="Margem" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
          </>}
          {rel === "livro" && <>
            <KPI v={formatBRL(receitas)} l="Entradas" c="var(--green-light)" />
            <KPI v={formatBRL(despesas)} l="Saídas" c="var(--red)" />
            <KPI v={formatBRL(resultado)} l="Saldo final" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
            <KPI v={String(livro.length)} l="Lançamentos" />
          </>}
        </div>

        {/* Gráfico do consolidado */}
        <div className="card mb-4">
          <div className="card-header mb-3">{rel === "fluxo" ? "Fluxo de Caixa (entradas × saídas × acumulado)" : rel === "dre" ? "Receita × Despesa × Resultado" : "Saldo Acumulado"}</div>
          {rel === "fluxo" && (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={fluxoMensal}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="mes" tickFormatter={fmtMes} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tip} />
                <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
                <Bar dataKey="entradas" name="Entradas" fill="var(--green-light)" radius={[2, 2, 0, 0]} />
                <Bar dataKey="saidas" name="Saídas" fill="var(--red)" radius={[2, 2, 0, 0]} />
                <Line type="monotone" dataKey="acumulado" name="Acumulado" stroke="var(--dourado-light)" strokeWidth={2} dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
          {rel === "dre" && (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={[{ n: "Receita", v: receitas, f: "var(--green-light)" }, { n: "Despesa", v: despesas, f: "var(--red)" }, { n: "Resultado", v: Math.abs(resultado), f: resultado >= 0 ? "var(--dourado)" : "var(--amber)" }]}>
                <XAxis dataKey="n" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="v" barSize={70}>{[0, 1, 2].map((i) => <Cell key={i} fill={["var(--green-light)", "var(--red)", resultado >= 0 ? "var(--dourado)" : "var(--amber)"][i]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          {rel === "livro" && (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={livro.filter((_, i) => i % Math.ceil(livro.length / 150 || 1) === 0)}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="data" tickFormatter={(d) => (d ? d.slice(5) : "")} tick={{ fill: "var(--text-muted)", fontSize: 9 }} minTickGap={30} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} labelFormatter={(d: any) => fmtDia(d as string)} contentStyle={tip} />
                <Line type="monotone" dataKey="saldo" name="Saldo acumulado" stroke="var(--dourado-light)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Detalhamento do relatório */}
        <div className="card">
          <div className="card-header mb-3">{rel === "fluxo" ? "Fluxo Mensal" : rel === "dre" ? "Detalhamento por Conta Gerencial" : "Lançamentos"}</div>
          <div className="overflow-x-auto" style={{ maxHeight: rel === "livro" ? "460px" : undefined }}>
            {rel === "fluxo" && (
              <table className="fazenda-table">
                <thead><tr><th>Mês</th><th style={{ textAlign: "right" }}>Entradas</th><th style={{ textAlign: "right" }}>Saídas</th><th style={{ textAlign: "right" }}>Saldo</th><th style={{ textAlign: "right" }}>Acumulado</th></tr></thead>
                <tbody>{fluxoMensal.map((m) => (
                  <tr key={m.mes}>
                    <td style={{ fontWeight: 600 }}>{m.mes}</td>
                    <td style={{ textAlign: "right", color: "var(--green-light)" }}>{formatBRL(m.entradas)}</td>
                    <td style={{ textAlign: "right", color: "var(--red)" }}>{formatBRL(m.saidas)}</td>
                    <td style={{ textAlign: "right", fontWeight: 700, color: m.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(m.saldo)}</td>
                    <td style={{ textAlign: "right", fontWeight: 700, color: "var(--dourado-light)" }}>{formatBRL(m.acumulado)}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
            {rel === "dre" && (
              <table className="fazenda-table">
                <thead><tr><th>Conta (nível 1)</th><th style={{ textAlign: "right" }}>Receitas</th><th style={{ textAlign: "right" }}>Despesas</th><th style={{ textAlign: "right" }}>Saldo</th></tr></thead>
                <tbody>{dreContas.map((c) => (
                  <tr key={c.conta}>
                    <td style={{ fontWeight: 600 }}>{c.conta}</td>
                    <td style={{ textAlign: "right", color: "var(--green-light)" }}>{c.receitas ? formatBRL(c.receitas) : "—"}</td>
                    <td style={{ textAlign: "right", color: "var(--red)" }}>{c.despesas ? formatBRL(c.despesas) : "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 700, color: c.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(c.saldo)}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
            {rel === "livro" && (
              <table className="fazenda-table">
                <thead><tr><th>Data</th><th>Descrição</th><th>Fornecedor/Cliente</th><th style={{ textAlign: "right" }}>Entrada</th><th style={{ textAlign: "right" }}>Saída</th><th style={{ textAlign: "right" }}>Saldo</th></tr></thead>
                <tbody>{livro.slice(0, 500).map((l, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{fmtDia(l.data)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{l.descricao}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{l.fornecedor}</td>
                    <td style={{ textAlign: "right", color: "var(--green-light)" }}>{l.entrada ? formatBRL(l.entrada) : ""}</td>
                    <td style={{ textAlign: "right", color: "var(--red)" }}>{l.saida ? formatBRL(l.saida) : ""}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: l.saldo >= 0 ? "var(--dourado-light)" : "var(--amber)" }}>{formatBRL(l.saldo)}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
            {rel === "livro" && livro.length > 500 && <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>Mostrando 500 de {livro.length} — refine o período.</p>}
          </div>
        </div>
      </>}
    </div>
  );
}
