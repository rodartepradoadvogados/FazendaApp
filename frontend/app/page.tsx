"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, Syringe, MilkOff, TrendingDown, Package, HeartPulse, Gauge as GaugeIcon, ChevronDown, ChevronRight, Target, RefreshCw, Skull, Calendar, Newspaper } from "lucide-react";
import {
  fetchIndicadores, fetchAgenda, fetchProducao, fetchResultadoMesRecente, fetchEstoque, fetchAnimais, fetchBaixas, formatBRL,
  fetchNotaCapa, podeModulo, type NotaCapa,
} from "@/lib/api";
import { AreaChart, Area, PieChart, Pie, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";
import { OnboardingChecklist } from "@/components/OnboardingChecklist";
import { Gauge } from "@/components/Gauge";
import { Indicador, EstadoVazio } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

const SIT_CORES: Record<string, string> = {
  Prenhes: "var(--green-light)", Inseminadas: "var(--dourado-light)",
  PEV: "var(--amber)", "A inseminar": "var(--blue)", Vazias: "var(--red)",
};

const LACTACAO = ["01", "02", "03"];
const cod = (g: string | null | undefined) => (g && /^\d\d/.test(g) ? g.slice(0, 2) : null);

// "Descartados" = baixas definitivas cujo tipo é descarte (não conta morte nem venda simples).
const TIPOS_DESCARTE = ["descarte_voluntario", "descarte_involuntario"];
const LABEL_TIPO_BAIXA: Record<string, string> = { descarte_voluntario: "Descarte voluntário", descarte_involuntario: "Descarte involuntário" };
const LABEL_MOTIVO_BAIXA: Record<string, string> = {
  venda: "Venda", abate: "Abate", acidente: "Acidente", doenca: "Doença", macho: "Macho", outros: "Outros",
};

export default function Home() {
  const [d, setD] = useState<any>(null);
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);
  const [benchAberto, setBenchAberto] = useState(false);
  const [catRep, setCatRep] = useState<"todas" | "vaca" | "novilha">("todas");
  const [recarregando, setRecarregando] = useState(false);
  // Quando qualquer fetch falha, alguns cards mostram "—"; sinalizamos isso num banner.
  const [erroCarga, setErroCarga] = useState(false);

  const [baixas, setBaixas] = useState<any[]>([]);
  const [desdeDescarte, setDesdeDescarte] = useState(() => `${new Date().getFullYear()}-01-01`);
  const [modalDescartados, setModalDescartados] = useState<{ title: string; list: any[] } | null>(null);
  const ordDescartados = useOrdenacao(modalDescartados?.list ?? []);
  // Nota informativa simples (distinta de matéria de blog) — atualizável só
  // pelo dono da plataforma; some quando não há nenhuma ativa.
  const [nota, setNota] = useState<NotaCapa | null>(null);
  const [notaFechada, setNotaFechada] = useState(false);

  const carregar = () => {
    setRecarregando(true);
    fetchNotaCapa().then(setNota).catch(() => {});
    Promise.allSettled([
      fetchIndicadores(), fetchAgenda(), fetchProducao(), fetchResultadoMesRecente(), fetchEstoque(),
    ]).then(([ind, ag, prod, resMes, est]) => {
      setErroCarga([ind, ag, prod, resMes, est].some((r) => r.status === "rejected"));
      setD({
        ind: ind.status === "fulfilled" ? ind.value : null,
        ag: ag.status === "fulfilled" ? ag.value : null,
        prod: prod.status === "fulfilled" ? prod.value : null,
        // Só {mes, resultado} — antes vinha o extrato financeiro completo
        // (fetchLancamentos) e a Capa recalculava isso no cliente; ver
        // GET /financeiro/resultado-mes-recente.
        resMes: resMes.status === "fulfilled" ? resMes.value : null,
        est: est.status === "fulfilled" ? est.value.itens : null,
      });
    }).finally(() => setRecarregando(false));
    fetchAnimais().then(setAnimais).catch(() => {});
    fetchBaixas().then(setBaixas).catch(() => {});
  };

  useEffect(() => { carregar(); }, []);

  const abrir = (title: string, filtro: (a: AnimalRow) => boolean) => { if (animais.length) setModal({ title, list: animais.filter(filtro) }); };

  if (!d) return <div className="p-6"><p style={{ color: "var(--text-muted)" }}>Carregando painel…</p></div>;

  const reb = d.ind?.rebanho, rep = d.ind?.reproducao, prod = d.ind?.producao;
  const semDados = !d.ind && !d.ag;

  // Benchmark reprodutivo (nosso valor × meta × média do país), por categoria.
  const benchCats: any = d.ind?.benchmark_categorias || { todas: d.ind?.benchmark || [] };
  const bench: any[] = benchCats[catRep] || benchCats.todas || [];
  const bm = (k: string) => bench.find((b) => b.chave === k) || {};
  const fmtBench = (b: any) => (b?.valor == null ? "—" : `${b.valor}${b.unidade ? (b.unidade === "%" ? "%" : " " + b.unidade) : ""}`);

  // Resultado do mês mais recente (competência) — já vem pronto do backend
  // (GET /financeiro/resultado-mes-recente), sem precisar do extrato
  // financeiro completo no cliente.
  const resultadoMes: number | null = d.resMes?.resultado ?? null;
  const mesLabel: string = d.resMes?.mes ?? "";

  const abaixoMin = d.est ? d.est.filter((i: any) => i.abaixo_minimo === true).length : null;
  const implante = d.ag?.hormonios_check?.find((h: any) => h.nome?.toLowerCase().includes("implante") || h.nome?.toLowerCase().includes("sincrogest"));
  const implanteFalta = implante && !implante.suficiente;
  const contasPagar = d.ag?.totais?.contas_a_pagar ?? 0;

  const serieProd = (d.prod?.serie_temporal || []).slice(-12).map((s: any) => ({
    mes: s.data ? new Date(s.data + "T00:00:00").toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }).replace(".", "") : "",
    kg: s.media_kg,
  }));
  const kgs = serieProd.map((s: any) => s.kg).filter((v: any) => v != null) as number[];
  const kgMin = kgs.length ? Math.floor(Math.min(...kgs) - 1) : 0;
  const kgMax = kgs.length ? Math.ceil(Math.max(...kgs) + 1) : 30;
  const repCats: any = d.ind?.reproducao_categorias || { todas: rep };
  const repSel: any = repCats[catRep] || rep;
  const donutRep = repSel ? [
    { nome: "Prenhes", v: repSel.prenhes }, { nome: "Inseminadas", v: repSel.inseminadas },
    { nome: "PEV", v: repSel.pev }, { nome: "A inseminar", v: repSel.a_inseminar },
    { nome: "Vazias", v: repSel.nao_classificadas },
  ].filter((x) => x.v > 0) : [];

  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" };

  const KPI = ({ v, l, c, cat, onClick, podeClicar }: { v: any; l: string; c?: string; cat?: "geral" | "reprodutivo" | "producao" | "financeiro"; onClick?: () => void; podeClicar?: boolean }) => (
    <Indicador
      valor={v} rotulo={l} categoria={cat} cor={c}
      onClick={onClick} podeClicar={podeClicar ?? animais.length > 0}
      extra={onClick ? <Target size={11} style={{ color: "var(--dourado-light)" }} /> : null}
    />
  );
  const candidatasList: AnimalRow[] = (d.ag?.candidatas_iatf || []).map((c: any) => ({ numero: c.numero_matriz, sit_rep: c.sit_rep, del_dias: c.del_dias }));
  const aDescartarList: AnimalRow[] = animais.filter((a) => a.a_descartar);
  const descartadosList = baixas.filter((b) => TIPOS_DESCARTE.includes(b.tipo_baixa) && (!desdeDescarte || b.data_baixa >= desdeDescarte));

  return (
    <div className="p-6 animate-in">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Fazenda Estreito Ponte de Pedra</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Pecuária leiteira · Girolando / Holandês · {new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Botão Manual da Fazenda mudou para o topo fixo (junto do News) —
              ver AuthShell.tsx — para nunca mais sobrepor outro botão fixo. */}
          <button onClick={carregar} className="btn-ghost" title="Recarregar dados" disabled={recarregando}>
            <RefreshCw size={16} className={recarregando ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <OnboardingChecklist />

      {nota && !notaFechada && (
        <div className="mb-4" style={{ background: "var(--surface-2)", border: "1px solid var(--dourado)", borderRadius: "var(--r-sm)", padding: "0.7rem 1rem", display: "flex", alignItems: "flex-start", gap: "0.7rem" }}>
          <Newspaper size={16} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text)" }}>{nota.titulo}</p>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{nota.texto}</p>
          </div>
          <button onClick={() => setNotaFechada(true)} className="btn-ghost" aria-label="Fechar nota" style={{ padding: "0.2rem" }}>✕</button>
        </div>
      )}

      {erroCarga && (
        <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Alguns dados não puderam ser carregados.</span></div>
      )}

      {semDados && (
        <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importe os dados</a>.</span></div>
      )}

      {/* Alertas */}
      <div className="flex flex-wrap gap-3 mb-5">
        {implanteFalta && <div className="flex items-center gap-2" style={{ background: "rgba(192,57,43,0.15)", border: "1px solid var(--red)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.9rem", fontSize: "0.82rem" }}><Syringe size={15} style={{ color: "var(--red)" }} /> Implante em falta: {Math.ceil(implante.falta)} p/ IATF</div>}
        {contasPagar > 0 && <div className="flex items-center gap-2" style={{ background: "rgba(217,119,6,0.12)", border: "1px solid var(--amber)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.9rem", fontSize: "0.82rem" }}><TrendingDown size={15} style={{ color: "var(--amber)" }} /> {contasPagar} conta(s) a pagar (10 dias)</div>}
        {!!abaixoMin && abaixoMin > 0 && <div className="flex items-center gap-2" style={{ background: "rgba(192,57,43,0.12)", border: "1px solid var(--red)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.9rem", fontSize: "0.82rem" }}><Package size={15} style={{ color: "var(--red)" }} /> {abaixoMin} item(ns) abaixo do mínimo</div>}
      </div>

      {/* KPIs executivos */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <KPI v={reb?.total ?? "—"} l="Fêmeas no rebanho" cat="geral" onClick={() => abrir("Fêmeas no rebanho", () => true)} />
        <KPI v={reb?.vacas_lactacao ?? "—"} l="Vacas em lactação" cat="geral" onClick={() => abrir("Vacas em lactação", (a) => LACTACAO.includes(cod(a.grupo_primario) || ""))} />
        <KPI v={rep?.taxa_prenhez_pct != null ? `${rep.taxa_prenhez_pct}%` : "—"} l="Fêmeas prenhas" cat="reprodutivo" />
        <KPI v={rep?.taxa_concepcao_pct != null ? `${rep.taxa_concepcao_pct}%` : "—"} l="Concepção / serviço" cat="reprodutivo" />
        <KPI v={prod?.producao_total_dia_kg != null ? `${prod.producao_total_dia_kg} kg` : "—"} l="Produção/dia (últ. controle)" cat="producao" />
        <KPI v={prod?.del_medio ?? "—"} l="DEL médio" cat="producao" />
        <KPI v={d.ag?.totais?.candidatas_iatf ?? "—"} l="Candidatas IATF" cat="reprodutivo"
          podeClicar={candidatasList.length > 0}
          onClick={() => setModal({ title: "Candidatas IATF", list: candidatasList })} />
        {/* Some por completo (não só o valor) para quem não tem o módulo
            Financeiro contratado — antes o card ficava sempre visível, com
            "—" no lugar do valor, revelando uma métrica paga a quem nunca
            comprou o módulo (ver auditoria de planos). */}
        {podeModulo("financeiro") && (
          <KPI v={resultadoMes != null ? formatBRL(resultadoMes) : "—"} l={`Resultado ${mesLabel}`} cat="financeiro" c={resultadoMes != null && resultadoMes >= 0 ? "var(--green-light)" : "var(--amber)"} />
        )}
      </div>

      {/* Medidores reprodutivos (modelo velocímetro) */}
      <div className="card mb-5">
        <div className="card-header mb-3 flex flex-wrap items-center gap-2"><GaugeIcon size={15} /> Eficiência Reprodutiva
          <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>· desde {rep?.concepcao_desde ? new Date(rep.concepcao_desde + "T00:00:00").toLocaleDateString("pt-BR") : "01/01/2026"} · Prenhez = Serviço × Concepção</span>
          <div style={{ marginLeft: "auto", display: "flex", gap: "0.25rem" }}>
            {([["todas", "Todas"], ["vaca", "Vacas"], ["novilha", "Novilhas"]] as const).map(([k, lbl]) => (
              <button key={k} onClick={() => setCatRep(k)} title={`Ver eficiência reprodutiva — ${lbl}`}
                style={{ fontSize: "0.7rem", padding: "0.2rem 0.6rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (catRep === k ? "var(--dourado)" : "var(--border)"),
                  background: catRep === k ? "var(--dourado)" : "transparent",
                  color: catRep === k ? "#1a1a1a" : "var(--text-muted)", fontWeight: catRep === k ? 700 : 400 }}>
                {lbl}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Gauge titulo="Taxa de Serviço" value={bm("taxa_servico").valor} meta={bm("taxa_servico").meta} mediaPais={bm("taxa_servico").media_pais} maiorMelhor={bm("taxa_servico").maior_melhor ?? true} />
          <Gauge titulo="Taxa de Concepção" value={bm("taxa_concepcao").valor} meta={bm("taxa_concepcao").meta} mediaPais={bm("taxa_concepcao").media_pais} maiorMelhor={bm("taxa_concepcao").maior_melhor ?? true} />
          <Gauge titulo="Taxa de Prenhez" value={bm("taxa_prenhez_ciclo").valor} meta={bm("taxa_prenhez_ciclo").meta} mediaPais={bm("taxa_prenhez_ciclo").media_pais} maiorMelhor={bm("taxa_prenhez_ciclo").maior_melhor ?? true} />
        </div>
        {/* Linha expansível: painel completo de benchmark */}
        <button onClick={() => setBenchAberto((v) => !v)}
          style={{ marginTop: "0.6rem", width: "100%", display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.2rem", background: "none", border: "none", borderTop: "1px solid var(--border)", color: "var(--dourado-light)", cursor: "pointer", fontSize: "0.8rem", fontWeight: 600 }}>
          {benchAberto ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          Comparar com metas e média do país <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>· {catRep === "todas" ? "todas as fêmeas" : catRep === "vaca" ? "vacas" : "novilhas"}</span>
        </button>
        {benchAberto && (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ marginTop: "0.4rem" }}>
              <thead><tr><th>Indicador</th><th style={{ textAlign: "right" }}>Nosso</th><th style={{ textAlign: "right" }}>Meta</th><th style={{ textAlign: "right" }}>Média país</th></tr></thead>
              <tbody>
                {bench.map((b: any) => {
                  const ok = b.valor != null && b.meta != null && (b.maior_melhor ? b.valor >= b.meta : b.valor <= b.meta);
                  return (
                    <tr key={b.chave}>
                      <td>{b.label}</td>
                      <td style={{ textAlign: "right", fontWeight: 700, color: b.valor == null ? "var(--text-muted)" : ok ? "var(--green-light)" : "var(--amber)" }}>{fmtBench(b)}</td>
                      <td style={{ textAlign: "right", color: "var(--text-muted)" }}>{b.meta != null ? `${b.meta}${b.unidade === "%" ? "%" : b.unidade ? " " + b.unidade : ""}` : "—"}</td>
                      <td style={{ textAlign: "right", color: "var(--text-muted)" }}>{b.media_pais != null ? `${b.media_pais}${b.unidade === "%" ? "%" : b.unidade ? " " + b.unidade : ""}` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p style={{ fontSize: "0.66rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
              Estimativas a partir dos serviços e diagnósticos carregados. Metas ajustáveis em <a href="/parametros" style={{ color: "var(--dourado-light)" }}>Parâmetros</a>.
            </p>
          </div>
        )}
      </div>

      {/* Gráficos */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
        <div className="card">
          <div className="card-header mb-2">Produção do Rebanho (média kg/vaca por mês)</div>
          {serieProd.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={serieProd} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradProd" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--green-light)" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="var(--green-light)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="mes" tick={{ fill: "var(--text-muted)", fontSize: 10 }} tickMargin={6} axisLine={false} tickLine={false} />
                <YAxis width={38} domain={[kgMin, kgMax]} tick={{ fill: "var(--text-muted)", fontSize: 10 }} axisLine={false} tickLine={false} unit=" kg" />
                <Tooltip contentStyle={tip} formatter={(v: any) => [`${v} kg`, "Média/vaca"]} labelStyle={{ color: "var(--text-muted)" }} />
                <Area type="monotone" dataKey="kg" stroke="var(--green-light)" strokeWidth={2.5} fill="url(#gradProd)" dot={{ r: 3, fill: "var(--green-light)", strokeWidth: 0 }} activeDot={{ r: 5 }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : <EstadoVazio icon={MilkOff}>Sem controle leiteiro ainda — <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)" }}>importe os dados</a> para ver o gráfico aqui.</EstadoVazio>}
        </div>
        <div className="card">
          <div className="card-header mb-2 flex flex-wrap items-center gap-2"><HeartPulse size={14} /> Situação Reprodutiva{animais.length ? <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>(clique para ver os animais)</span> : null}
            <div style={{ marginLeft: "auto", display: "flex", gap: "0.25rem" }}>
              {([["todas", "Todas"], ["vaca", "Vacas"], ["novilha", "Novilhas"]] as const).map(([k, lbl]) => (
                <button key={k} onClick={() => setCatRep(k)} title={`Ver situação reprodutiva — ${lbl}`}
                  style={{ fontSize: "0.7rem", padding: "0.2rem 0.6rem", borderRadius: "999px", cursor: "pointer",
                    border: "1px solid " + (catRep === k ? "var(--dourado)" : "var(--border)"),
                    background: catRep === k ? "var(--dourado)" : "transparent",
                    color: catRep === k ? "#1a1a1a" : "var(--text-muted)", fontWeight: catRep === k ? 700 : 400 }}>
                  {lbl}
                </button>
              ))}
            </div>
          </div>
          {repSel ? (
            <div className="grid grid-cols-3 gap-2 mb-2">
              {([
                ["Aptas", repSel.aptas, (a: AnimalRow) => (repSel.aptas_nums || []).includes(a.numero)],
                ["Inseminadas", repSel.inseminadas, (a: AnimalRow) => a.sit_rep === "Ins." && (catRep === "todas" ? true : catRep === "vaca" ? !!a.data_ult_parto : !a.data_ult_parto)],
                ["Gestantes", repSel.prenhes, (a: AnimalRow) => a.sit_rep === "Ges." && (catRep === "todas" ? true : catRep === "vaca" ? !!a.data_ult_parto : !a.data_ult_parto)],
              ] as const).map(([l, v, f]) => (
                <KPI key={l} l={l} v={v} cat="reprodutivo" onClick={() => abrir(l, f)} />
              ))}
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-2 mb-2" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.5rem" }}>
            <KPI l="A descartar (atual)" v={aDescartarList.length} cat="geral" c="var(--amber)"
              podeClicar={aDescartarList.length > 0}
              onClick={() => setModal({ title: "A descartar (atual)", list: aDescartarList })} />
            <div className="kpi-card" style={{ cursor: descartadosList.length ? "pointer" : undefined, ["--kpi-c" as any]: "var(--red)" }}>
              <div className="kpi-chip"><Skull size={14} /></div>
              <p className="kpi-value" style={{ fontSize: "1.4rem", color: "var(--red)" }}
                onClick={() => descartadosList.length && setModalDescartados({ title: "Descartados", list: descartadosList })}>
                {descartadosList.length}
              </p>
              <p className="kpi-label flex items-center gap-1 flex-wrap">
                Descartados
                <span style={{ fontSize: "0.68rem" }}>desde</span>
                <input type="date" value={desdeDescarte} onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setDesdeDescarte(e.target.value)}
                  style={{ fontSize: "0.68rem", padding: "0.05rem 0.25rem", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }} />
              </p>
            </div>
          </div>
          {donutRep.length ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={donutRep} dataKey="v" nameKey="nome" cx="50%" cy="50%" innerRadius={45} outerRadius={75} label={(e: any) => `${e.nome} (${e.v})`} labelLine={false} fontSize={10}
                  style={{ cursor: animais.length ? "pointer" : undefined }}
                  onClick={(e: any) => {
                    const nome = e?.name; if (!nome) return;
                    const porCategoria = (a: AnimalRow) => catRep === "todas" ? true : catRep === "vaca" ? !!a.data_ult_parto : !a.data_ult_parto;
                    const f = nome === "Prenhes"
                      ? (a: AnimalRow) => a.sit_rep === "Ges." && porCategoria(a)
                      : nome === "Inseminadas"
                      ? (a: AnimalRow) => a.sit_rep === "Ins." && porCategoria(a)
                      : nome === "PEV"
                      ? (a: AnimalRow) => a.sit_rep === "Vaz. pev" && porCategoria(a)
                      : nome === "A inseminar"
                      ? (a: AnimalRow) => (a.sit_rep === "Vaz. apt." || a.sit_rep === "Vaz. atr.") && porCategoria(a)
                      : (a: AnimalRow) => !["Ges.", "Ins.", "Vaz. pev", "Vaz. apt.", "Vaz. atr."].includes((a.sit_rep || "")) && porCategoria(a);
                    abrir(nome, f);
                  }}>
                  {donutRep.map((s: any, i: number) => <Cell key={i} fill={SIT_CORES[s.nome]} />)}
                </Pie>
                <Tooltip contentStyle={tip} />
              </PieChart>
            </ResponsiveContainer>
          ) : <EstadoVazio icon={HeartPulse}>Sem dados reprodutivos ainda — assim que houver lançamentos, o gráfico aparece aqui.</EstadoVazio>}
        </div>
      </div>

      {/* Próximos eventos */}
      <div className="card">
        <div className="card-header mb-3">Próximos Eventos (7 dias)</div>
        {(() => {
          const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
          const limite = new Date(hoje); limite.setDate(limite.getDate() + 7);
          const evs = (d.ag?.eventos || []).filter((e: any) => { const dt = new Date(e.data + "T00:00:00"); return dt >= hoje && dt <= limite; }).slice(0, 10);
          return evs.length ? (
            <div className="space-y-2">
              {evs.map((ev: any, i: number) => (
                <div key={i} className="flex items-start gap-3 py-1">
                  <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", minWidth: "4.5rem" }}>{new Date(ev.data + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}</span>
                  <span style={{ fontSize: "0.82rem", color: "var(--text)" }}>{ev.numero_animal ? <strong>{ev.numero_animal} · </strong> : null}{ev.descricao}</span>
                </div>
              ))}
            </div>
          ) : <EstadoVazio icon={Calendar}>Nenhum evento nos próximos 7 dias.</EstadoVazio>;
        })()}
      </div>

      {modal && <AnimalModal title={modal.title} animais={modal.list} onClose={() => setModal(null)} />}
      {modalDescartados && (
        <div onClick={() => setModalDescartados(null)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "680px", maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>
                {modalDescartados.title} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({modalDescartados.list.length})</span>
              </div>
              <button onClick={() => setModalDescartados(null)} className="btn-ghost" aria-label="Fechar">✕</button>
            </div>
            <div style={{ overflowY: "auto" }}>
              <table className="fazenda-table">
                <thead>
                  <tr>
                    <ThOrdenavel label="Nº" campo="numero_animal" coluna={ordDescartados.coluna} dir={ordDescartados.dir} ordenar={ordDescartados.ordenar} />
                    <ThOrdenavel label="Tipo" campo="tipo_baixa" coluna={ordDescartados.coluna} dir={ordDescartados.dir} ordenar={ordDescartados.ordenar} />
                    <ThOrdenavel label="Motivo" campo="motivo" coluna={ordDescartados.coluna} dir={ordDescartados.dir} ordenar={ordDescartados.ordenar} />
                    <ThOrdenavel label="Data" campo="data_baixa" coluna={ordDescartados.coluna} dir={ordDescartados.dir} ordenar={ordDescartados.ordenar} />
                    <ThOrdenavel label="Valor" campo="valor" coluna={ordDescartados.coluna} dir={ordDescartados.dir} ordenar={ordDescartados.ordenar} alinhar="right" />
                    <ThOrdenavel label="Cliente" campo="cliente" coluna={ordDescartados.coluna} dir={ordDescartados.dir} ordenar={ordDescartados.ordenar} />
                  </tr>
                </thead>
                <tbody>
                  {ordDescartados.linhasOrdenadas.map((b: any) => (
                    <tr key={b.id}>
                      <td style={{ fontWeight: 700 }}>{b.numero_animal}</td>
                      <td style={{ fontSize: "0.8rem" }}>{LABEL_TIPO_BAIXA[b.tipo_baixa] || b.tipo_baixa}</td>
                      <td style={{ fontSize: "0.8rem" }}>{LABEL_MOTIVO_BAIXA[b.motivo] || b.motivo}</td>
                      <td style={{ fontSize: "0.8rem" }}>{b.data_baixa}</td>
                      <td style={{ textAlign: "right" }}>{b.valor != null ? formatBRL(b.valor) : "—"}</td>
                      <td style={{ fontSize: "0.8rem" }}>{b.cliente || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
