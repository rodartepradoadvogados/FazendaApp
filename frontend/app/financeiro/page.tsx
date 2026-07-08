"use client";
import { useEffect, useMemo, useState } from "react";
import {
  BarChart3, Filter, Wallet, BookOpen, FileText, Clock, CheckCircle2, Receipt, X, Check, Building2,
} from "lucide-react";
import { fetchLancamentos, marcarPagoFinanceiro, fetchOpcoesFinanceiro, fetchPatrimonio, formatBRL, formatDate } from "@/lib/api";
import {
  ComposedChart, Bar, Line, LineChart, BarChart, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, Cell, CartesianGrid,
} from "recharts";

type Lanc = {
  id: number; numero_lancamento: string | null;
  tipo: string; valor: number; valor_pago: number | null; desconto_acrescimo: number | null;
  centro_custo: string; codigo_conta: string; conta_completa: string;
  descricao: string; fornecedor: string; responsavel: string | null;
  tipo_documento: string | null; numero_documento: string | null; numero_documento_pagamento: string | null;
  conta_bancaria: string | null; entregue: boolean | null;
  parcela_num: number | null; parcela_total: number | null;
  data_competencia: string | null; data_pagamento: string | null; data_vencimento: string | null;
  mes_competencia: string | null; mes_caixa: string | null;
};

type Rel = "fluxo" | "dre" | "livro" | "a_pagar" | "a_receber" | "pagas" | "recebidas" | "extrato" | "patrimonio";
const RELATORIOS: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "fluxo", label: "Fluxo de Caixa", icon: Wallet, desc: "Entradas × saídas por regime de caixa" },
  { id: "dre", label: "DRE Gerencial", icon: FileText, desc: "Resultado por competência" },
  { id: "livro", label: "Livro Caixa", icon: BookOpen, desc: "Lançamentos com saldo acumulado" },
];
const CONTAS: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "a_pagar", label: "Contas a pagar", icon: Clock, desc: "Despesas em aberto (sem data de pagamento)" },
  { id: "a_receber", label: "Contas a receber", icon: Clock, desc: "Receitas em aberto (sem data de recebimento)" },
  { id: "pagas", label: "Contas pagas", icon: CheckCircle2, desc: "Despesas já quitadas" },
  { id: "recebidas", label: "Contas recebidas", icon: CheckCircle2, desc: "Receitas já recebidas" },
  { id: "extrato", label: "Extrato completo", icon: Receipt, desc: "Todos os lançamentos, com ou sem baixa" },
];
const CONTAS_IDS = new Set(CONTAS.map((c) => c.id));
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
  const [rel, setRel] = useState<Rel>("a_pagar");
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [centro, setCentro] = useState("");
  const [contaBanco, setContaBanco] = useState("");
  const [exp, setExp] = useState<Set<string>>(new Set());
  const toggleExp = (k: string) => setExp((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const [contasBancarias, setContasBancarias] = useState<string[]>([]);
  const [baixaAlvo, setBaixaAlvo] = useState<Lanc | null>(null);

  const recarregar = () => fetchLancamentos().then((d) => setRegs(d.lancamentos)).catch((e) => setError(e.message));
  useEffect(() => { recarregar(); fetchOpcoesFinanceiro().then((d) => setContasBancarias(d.contas_bancarias || [])).catch(() => {}); }, []);

  useEffect(() => {
    if (regs && !inicio) {
      const ds = regs.flatMap((r) => [r.data_pagamento, r.data_competencia, r.data_vencimento]).filter(Boolean).sort() as string[];
      if (ds.length) { setInicio(ds[0]); setFim(ds[ds.length - 1]); }
    }
  }, [regs, inicio]);

  const centros = useMemo(() => Array.from(new Set((regs ?? []).map((r) => r.centro_custo))).sort(), [regs]);

  // Base de cada sub-aba de contas: em aberto (sem data de pagamento) ou já quitadas.
  const contasBase = useMemo(() => {
    if (!regs) return [];
    switch (rel) {
      case "a_pagar": return regs.filter((r) => r.tipo === "despesa" && !r.data_pagamento);
      case "a_receber": return regs.filter((r) => r.tipo === "receita" && !r.data_pagamento);
      case "pagas": return regs.filter((r) => r.tipo === "despesa" && r.data_pagamento);
      case "recebidas": return regs.filter((r) => r.tipo === "receita" && r.data_pagamento);
      case "extrato": return regs;
      default: return regs;
    }
  }, [regs, rel]);

  // Data relevante por aba: DRE = competência; a pagar/receber = vencimento; pagas/recebidas = pagamento; fluxo/livro = pagamento.
  const campoData = (r: Lanc) => {
    if (rel === "dre") return r.data_competencia;
    if (rel === "a_pagar" || rel === "a_receber") return r.data_vencimento || r.data_competencia;
    if (rel === "pagas" || rel === "recebidas") return r.data_pagamento;
    if (rel === "extrato") return r.data_pagamento || r.data_vencimento || r.data_competencia;
    return r.data_pagamento;
  };
  const campoMes = (r: Lanc) => (rel === "dre" ? r.mes_competencia : r.mes_caixa);

  const filtrados = useMemo(() => {
    if (CONTAS_IDS.has(rel)) {
      // Sem período definido, mostra tudo — contas em aberto não devem sumir por falta de filtro.
      return contasBase.filter((r) => {
        const d = campoData(r);
        const dentroPeriodo = !inicio || !fim || !d || (d >= inicio && d <= fim);
        return dentroPeriodo && (!centro || r.centro_custo === centro) && (!contaBanco || r.conta_bancaria === contaBanco);
      });
    }
    if (!regs || !inicio || !fim) return [];
    return regs.filter((r) => {
      const d = campoData(r);
      return d && d >= inicio && d <= fim && (!centro || r.centro_custo === centro);
    });
  }, [regs, contasBase, rel, inicio, fim, centro, contaBanco]);

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

  // DRE por conta gerencial — agrupa pela conta do plano de contas, mostrando
  // o NOME da conta (descrição) em vez do código, que é pouco legível.
  const dreContas = useMemo(() => {
    const by = new Map<string, { conta: string; nome: string; codigo: string; receitas: number; despesas: number }>();
    filtrados.forEach((r) => {
      const codigo = r.conta_completa || r.codigo_conta || "";
      const nome = r.descricao || codigo || "(sem conta)";
      const k = codigo || nome;
      const e = by.get(k) ?? { conta: k, nome, codigo, receitas: 0, despesas: 0 };
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
        {/* Seletor de contas */}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Contas</p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
          {CONTAS.map((r) => {
            const ativo = rel === r.id; const Icon = r.icon;
            const n = regs ? (
              r.id === "a_pagar" ? regs.filter((x) => x.tipo === "despesa" && !x.data_pagamento).length :
              r.id === "a_receber" ? regs.filter((x) => x.tipo === "receita" && !x.data_pagamento).length :
              r.id === "pagas" ? regs.filter((x) => x.tipo === "despesa" && x.data_pagamento).length :
              r.id === "recebidas" ? regs.filter((x) => x.tipo === "receita" && x.data_pagamento).length :
              regs.length
            ) : 0;
            return (
              <button key={r.id} onClick={() => setRel(r.id)} className="card" style={{ textAlign: "left", cursor: "pointer", border: ativo ? "1px solid var(--dourado)" : "1px solid var(--border)", background: ativo ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
                <div className="flex items-center gap-2" style={{ color: ativo ? "var(--dourado-light)" : "var(--text)" }}><Icon size={16} /><span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{r.label}</span></div>
                <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>{n} lançamento{n === 1 ? "" : "s"}</p>
              </button>
            );
          })}
        </div>

        {/* Seletor de relatório */}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Relatórios</p>
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

        {/* Patrimônio */}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Patrimônio</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          <button onClick={() => setRel("patrimonio")} className="card" style={{ textAlign: "left", cursor: "pointer", border: rel === "patrimonio" ? "1px solid var(--dourado)" : "1px solid var(--border)", background: rel === "patrimonio" ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
            <div className="flex items-center gap-2" style={{ color: rel === "patrimonio" ? "var(--dourado-light)" : "var(--text)" }}><Building2 size={18} /><span style={{ fontWeight: 700 }}>Patrimônio</span></div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Máquinas, veículos, implementos e terras</p>
          </button>
        </div>

        {rel === "patrimonio" ? <PatrimonioView /> : <>
        {/* Filtros */}
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
          <div className="flex flex-wrap gap-3 items-end">
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Início</label><input type="date" style={inputStyle} value={inicio} onChange={(e) => setInicio(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Fim</label><input type="date" style={inputStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Centro de custo</label>
              <select style={inputStyle} value={centro} onChange={(e) => setCentro(e.target.value)}><option value="">Todos</option>{centros.map((c) => <option key={c}>{c}</option>)}</select></div>
            {CONTAS_IDS.has(rel) && (
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Conta bancária</label>
                <select style={inputStyle} value={contaBanco} onChange={(e) => setContaBanco(e.target.value)}><option value="">Todas</option>{contasBancarias.map((c) => <option key={c}>{c}</option>)}</select></div>
            )}
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", paddingBottom: "0.4rem" }}>
              {!CONTAS_IDS.has(rel) && <>Regime: <strong style={{ color: "var(--dourado-light)" }}>{rel === "dre" ? "competência" : "caixa"}</strong> · </>}
              {filtrados.length} lançamento{filtrados.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        {CONTAS_IDS.has(rel) ? (
          <TabelaContas rel={rel} itens={filtrados} onDarBaixa={setBaixaAlvo} />
        ) : <>
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
          <div className="card-header mb-3">
            {rel === "fluxo" ? "Fluxo Mensal" : rel === "dre" ? "Detalhamento por Conta Gerencial" : "Lançamentos"}
            {rel !== "livro" && <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}> (clique numa linha para ver os lançamentos)</span>}
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: rel === "livro" ? "460px" : undefined }}>
            {rel === "fluxo" && (
              <table className="fazenda-table">
                <thead><tr><th></th><th>Mês</th><th style={{ textAlign: "right" }}>Entradas</th><th style={{ textAlign: "right" }}>Saídas</th><th style={{ textAlign: "right" }}>Saldo</th><th style={{ textAlign: "right" }}>Acumulado</th></tr></thead>
                <tbody>{fluxoMensal.map((m) => {
                  const aberto = exp.has("fluxo:" + m.mes);
                  const itens = aberto ? filtrados.filter((r) => campoMes(r) === m.mes).sort((a, b) => ((a.data_pagamento || "") < (b.data_pagamento || "") ? -1 : 1)) : [];
                  return (
                    <>
                      <tr key={m.mes} onClick={() => toggleExp("fluxo:" + m.mes)} style={{ cursor: "pointer" }}>
                        <td style={{ width: 18, color: "var(--text-muted)" }}>{aberto ? "▾" : "▸"}</td>
                        <td style={{ fontWeight: 600 }}>{m.mes}</td>
                        <td style={{ textAlign: "right", color: "var(--green-light)" }}>{formatBRL(m.entradas)}</td>
                        <td style={{ textAlign: "right", color: "var(--red)" }}>{formatBRL(m.saidas)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: m.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(m.saldo)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: "var(--dourado-light)" }}>{formatBRL(m.acumulado)}</td>
                      </tr>
                      {aberto && itens.map((r, i) => (
                        <tr key={m.mes + ":" + i} style={{ background: "var(--surface-2)" }}>
                          <td></td>
                          <td colSpan={2} style={{ fontSize: "0.75rem" }}>{fmtDia(r.data_pagamento)} · {r.descricao}</td>
                          <td colSpan={2} style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.fornecedor}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem", color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{r.tipo === "receita" ? "+" : "−"}{formatBRL(r.valor)}</td>
                        </tr>
                      ))}
                    </>
                  );
                })}</tbody>
              </table>
            )}
            {rel === "dre" && (<>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                Resultado por <strong>conta gerencial</strong> do seu plano de contas (por competência). Clique numa conta <span style={{ color: "var(--text-muted)" }}>▾</span> para ver os lançamentos.
              </p>
              <table className="fazenda-table">
                <thead><tr><th></th><th>Conta gerencial</th><th style={{ textAlign: "right" }}>Receitas</th><th style={{ textAlign: "right" }}>Despesas</th><th style={{ textAlign: "right" }}>Saldo</th></tr></thead>
                <tbody>{dreContas.map((c) => {
                  const aberto = exp.has("dre:" + c.conta);
                  const itens = aberto ? filtrados.filter((r) => (r.conta_completa || r.codigo_conta || "") === c.conta).sort((a, b) => b.valor - a.valor) : [];
                  return (
                    <>
                      <tr key={c.conta} onClick={() => toggleExp("dre:" + c.conta)} style={{ cursor: "pointer" }}>
                        <td style={{ width: 18, color: "var(--text-muted)" }}>{aberto ? "▾" : "▸"}</td>
                        <td style={{ fontWeight: 600 }}>{c.nome}{c.codigo && c.codigo !== c.nome ? <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginLeft: "0.4rem" }}>{c.codigo}</span> : null}</td>
                        <td style={{ textAlign: "right", color: "var(--green-light)" }}>{c.receitas ? formatBRL(c.receitas) : "—"}</td>
                        <td style={{ textAlign: "right", color: "var(--red)" }}>{c.despesas ? formatBRL(c.despesas) : "—"}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: c.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(c.saldo)}</td>
                      </tr>
                      {aberto && itens.map((r, i) => (
                        <tr key={c.conta + ":" + i} style={{ background: "var(--surface-2)" }}>
                          <td></td>
                          <td colSpan={2} style={{ fontSize: "0.75rem" }}>{fmtDia(r.data_pagamento || r.data_competencia)} <span style={{ color: "var(--text-muted)" }}>· {r.fornecedor || "—"}</span></td>
                          <td colSpan={2} style={{ textAlign: "right", fontSize: "0.78rem", color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{r.tipo === "receita" ? "+" : "−"}{formatBRL(r.valor)}</td>
                        </tr>
                      ))}
                    </>
                  );
                })}</tbody>
              </table>
            </>)}
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
        </>}
      </>}

      {baixaAlvo && <BaixaModal lancamento={baixaAlvo} contasBancarias={contasBancarias} onClose={() => setBaixaAlvo(null)} onSalvo={() => { setBaixaAlvo(null); recarregar(); }} />}
    </div>
  );
}

type ItemPatrimonio = {
  id: number; tipo: string | null; nome: string; numero: string | null;
  atividade_cultura: string | null; placa: string | null; data_imobilizacao: string | null;
  metodo_depreciacao: string | null; vida_util: string | null; valor_residual: number | null;
  quantidade: number | null; unidade: string | null; valor_total: number | null; data_baixa: string | null;
};

function PatrimonioView() {
  const [dados, setDados] = useState<{ itens: ItemPatrimonio[]; total: number; valor_total: number } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => { fetchPatrimonio().then(setDados).catch((e) => setErro(e.message)); }, []);

  if (erro) return <div className="alert-critico"><span>Sem dados: {erro}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o LISTA_DE_PATRIMONIO.csv</a>.</span></div>;
  if (!dados) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;
  if (!dados.itens.length) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
        <Building2 size={38} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
        <p style={{ color: "var(--text-muted)" }}>Nenhum item de patrimônio no banco.</p>
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
          Suba o <strong>LISTA_DE_PATRIMONIO.csv</strong> na tela de <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Upload</a>.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
        <KPI v={String(dados.total)} l="Itens" />
        <KPI v={formatBRL(dados.valor_total)} l="Valor total (ativo)" c="var(--dourado-light)" />
        <KPI v={String(dados.itens.filter((i) => i.data_baixa).length)} l="Com baixa" c="var(--text-muted)" />
      </div>
      <div className="card">
        <div className="card-header mb-3">Bens</div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <th>Tipo</th><th>Nome</th><th>Nº</th><th>Placa</th><th>Imobilização</th>
                <th>Depreciação</th><th>Vida útil</th><th style={{ textAlign: "right" }}>Vlr. residual</th>
                <th style={{ textAlign: "right" }}>Qtd.</th><th style={{ textAlign: "right" }}>Vlr. total</th><th>Baixa</th>
              </tr>
            </thead>
            <tbody>
              {dados.itens.map((i) => (
                <tr key={i.id} style={i.data_baixa ? { opacity: 0.55 } : undefined}>
                  <td style={{ fontSize: "0.78rem" }}>{i.tipo || "—"}</td>
                  <td style={{ fontWeight: 600, fontSize: "0.83rem" }}>{i.nome}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.numero || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.placa || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.data_imobilizacao ? formatDate(i.data_imobilizacao) : "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.metodo_depreciacao || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.vida_util || "—"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{i.valor_residual != null ? formatBRL(i.valor_residual) : "—"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{i.quantidade ?? "—"} {i.unidade || ""}</td>
                  <td style={{ textAlign: "right", fontWeight: 600, fontSize: "0.83rem" }}>{i.valor_total != null ? formatBRL(i.valor_total) : "—"}</td>
                  <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{i.data_baixa ? formatDate(i.data_baixa) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function TabelaContas({ rel, itens, onDarBaixa }: { rel: Rel; itens: Lanc[]; onDarBaixa: (l: Lanc) => void }) {
  const emAberto = rel === "a_pagar" || rel === "a_receber";
  const total = itens.reduce((a, r) => a + r.valor, 0);
  const totalPago = itens.reduce((a, r) => a + (r.valor_pago ?? 0), 0);
  const totalDesconto = itens.reduce((a, r) => a + (r.desconto_acrescimo ?? 0), 0);
  const hoje = new Date().toISOString().slice(0, 10);

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <KPI v={String(itens.length)} l="Lançamentos" />
        <KPI v={formatBRL(total)} l={emAberto ? "Valor em aberto" : "Valor total"} c={rel === "a_pagar" || rel === "pagas" ? "var(--red)" : rel === "extrato" ? undefined : "var(--green-light)"} />
        {!emAberto && rel !== "extrato" && <KPI v={formatBRL(totalPago)} l="Valor pago/recebido" c="var(--dourado-light)" />}
        {!emAberto && rel !== "extrato" && <KPI v={formatBRL(totalDesconto)} l="Desconto/acréscimo" c={totalDesconto <= 0 ? "var(--green-light)" : "var(--amber)"} />}
      </div>
      <div className="card">
        <div className="card-header mb-3">Lançamentos</div>
        <div className="overflow-x-auto" style={{ maxHeight: "520px" }}>
          <table className="fazenda-table">
            <thead>
              <tr>
                <th>Nº lanç.</th><th>{emAberto ? "Vencimento" : "Data"}</th><th>Descrição</th><th>Fornecedor/Cliente</th>
                <th>Centro custo</th><th>Documento</th><th style={{ textAlign: "right" }}>Valor</th>
                {!emAberto && <th style={{ textAlign: "right" }}>Pago</th>}
                {!emAberto && <th>Conta bancária</th>}
                {emAberto && <th></th>}
              </tr>
            </thead>
            <tbody>
              {itens.map((r) => {
                const vencido = emAberto && r.data_vencimento && r.data_vencimento < hoje;
                return (
                  <tr key={r.id}>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.numero_lancamento}{r.parcela_total && r.parcela_total > 1 ? ` (${r.parcela_num}/${r.parcela_total})` : ""}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem", color: vencido ? "var(--red)" : undefined, fontWeight: vencido ? 700 : undefined }}>
                      {fmtDia(emAberto ? r.data_vencimento : (r.data_pagamento || r.data_vencimento))}{vencido ? " ⚠" : ""}
                    </td>
                    <td style={{ fontSize: "0.78rem" }}>{r.descricao || "—"}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{r.fornecedor || "—"}</td>
                    <td style={{ fontSize: "0.75rem" }}>{r.centro_custo}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.tipo_documento ? `${r.tipo_documento} ` : ""}{r.numero_documento || ""}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{formatBRL(r.valor)}</td>
                    {!emAberto && <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{r.valor_pago != null ? formatBRL(r.valor_pago) : "—"}</td>}
                    {!emAberto && <td style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{r.conta_bancaria || "—"}</td>}
                    {emAberto && <td><button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => onDarBaixa(r)}>Dar baixa</button></td>}
                  </tr>
                );
              })}
              {!itens.length && <tr><td colSpan={10} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Nenhum lançamento nesta aba.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function BaixaModal({ lancamento, contasBancarias, onClose, onSalvo }: { lancamento: Lanc; contasBancarias: string[]; onClose: () => void; onSalvo: () => void }) {
  const [dataPagamento, setDataPagamento] = useState(new Date().toISOString().slice(0, 10));
  const [valorPago, setValorPago] = useState(String(lancamento.valor));
  const [contaBancaria, setContaBancaria] = useState("");
  const [numeroDocPagamento, setNumeroDocPagamento] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
  const diferenca = Math.round((Number(valorPago) - lancamento.valor) * 100) / 100;
  const recebendo = lancamento.tipo === "receita";

  async function confirmar() {
    if (diferenca !== 0 && !confirmando) { setConfirmando(true); return; }
    setSalvando(true); setErro(null);
    try {
      await marcarPagoFinanceiro(lancamento.id, {
        data_pagamento: dataPagamento, valor_pago: Number(valorPago) || 0,
        conta_bancaria: contaBancaria || undefined, numero_documento_pagamento: numeroDocPagamento || undefined,
      });
      onSalvo();
    } catch (e: any) {
      setErro(e.message || "Erro ao dar baixa");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70, padding: "1rem" }}>
      <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "440px", maxWidth: "95vw" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Dar baixa — {recebendo ? "recebimento" : "pagamento"}</div>
          <button onClick={onClose} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
        </div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>{lancamento.descricao} · <strong style={{ color: "var(--text)" }}>{formatBRL(lancamento.valor)}</strong></p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Data de {recebendo ? "recebimento" : "pagamento"}</label>
            <input type="date" style={inputStyle} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Valor {recebendo ? "recebido" : "pago"} (R$)</label>
            <input type="number" inputMode="decimal" style={inputStyle} value={valorPago} onChange={(e) => setValorPago(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Conta bancária</label>
            <select style={inputStyle} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
              <option value="">Selecione…</option>{contasBancarias.map((c) => <option key={c}>{c}</option>)}
            </select></div>
          <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Nº documento de pagamento</label>
            <input style={inputStyle} value={numeroDocPagamento} onChange={(e) => setNumeroDocPagamento(e.target.value)} /></div>
        </div>
        {diferenca !== 0 && (
          <p style={{ fontSize: "0.78rem", marginTop: "0.6rem", color: diferenca < 0 ? "var(--green-light)" : "var(--amber)" }}>
            {diferenca < 0 ? `Desconto de ${formatBRL(Math.abs(diferenca))}` : `Acréscimo de ${formatBRL(diferenca)}`} em relação ao valor do lançamento.
          </p>
        )}
        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}
        <div className="flex items-center gap-3 mt-4">
          <button className="btn-primary" onClick={confirmar} disabled={salvando}>
            <Check size={14} /> {confirmando ? "Confirmar mesmo com diferença" : salvando ? "Salvando…" : "Confirmar baixa"}
          </button>
          <button className="btn-ghost" onClick={onClose}>Cancelar</button>
        </div>
      </div>
    </div>
  );
}
