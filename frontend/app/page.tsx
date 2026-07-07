"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, Syringe, MilkOff, TrendingDown, Package, HeartPulse } from "lucide-react";
import {
  fetchIndicadores, fetchAgenda, fetchProducao, fetchLancamentos, fetchEstoque, fetchAnimais, formatBRL,
} from "@/lib/api";
import { AreaChart, Area, PieChart, Pie, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";

const SIT_CORES: Record<string, string> = { Prenhes: "var(--green-light)", Vazias: "var(--red)", Inseminadas: "var(--dourado-light)" };

const LACTACAO = ["01", "02", "03"];
const cod = (g: string | null | undefined) => (g && /^\d\d/.test(g) ? g.slice(0, 2) : null);

export default function Home() {
  const [d, setD] = useState<any>(null);
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);

  useEffect(() => {
    Promise.allSettled([
      fetchIndicadores(), fetchAgenda(), fetchProducao(), fetchLancamentos(), fetchEstoque(),
    ]).then(([ind, ag, prod, lanc, est]) => {
      setD({
        ind: ind.status === "fulfilled" ? ind.value : null,
        ag: ag.status === "fulfilled" ? ag.value : null,
        prod: prod.status === "fulfilled" ? prod.value : null,
        lanc: lanc.status === "fulfilled" ? lanc.value.lancamentos : null,
        est: est.status === "fulfilled" ? est.value.itens : null,
      });
    });
    fetchAnimais().then(setAnimais).catch(() => {});
  }, []);

  const abrir = (title: string, filtro: (a: AnimalRow) => boolean) => { if (animais.length) setModal({ title, list: animais.filter(filtro) }); };

  if (!d) return <div className="p-6"><p style={{ color: "var(--text-muted)" }}>Carregando painel…</p></div>;

  const reb = d.ind?.rebanho, rep = d.ind?.reproducao, prod = d.ind?.producao;
  const semDados = !d.ind && !d.ag;

  // Resultado do mês mais recente (competência)
  let resultadoMes: number | null = null, mesLabel = "";
  if (d.lanc?.length) {
    const meses = Array.from(new Set(d.lanc.map((l: any) => l.mes_competencia).filter(Boolean))).sort() as string[];
    const ultimo = meses[meses.length - 1];
    if (ultimo) {
      mesLabel = ultimo;
      const doMes = d.lanc.filter((l: any) => l.mes_competencia === ultimo);
      const r = doMes.filter((l: any) => l.tipo === "receita").reduce((a: number, l: any) => a + l.valor, 0);
      const de = doMes.filter((l: any) => l.tipo === "despesa").reduce((a: number, l: any) => a + l.valor, 0);
      resultadoMes = r - de;
    }
  }

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
  const donutRep = rep ? [
    { nome: "Prenhes", v: rep.prenhes }, { nome: "Vazias", v: rep.vazias }, { nome: "Inseminadas", v: rep.inseminadas },
  ].filter((x) => x.v > 0) : [];

  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text)", fontSize: "0.8rem" };

  const KPI = ({ v, l, c, onClick }: { v: any; l: string; c?: string; onClick?: () => void }) => (
    <div className="kpi-card" onClick={onClick} style={onClick && animais.length ? { cursor: "pointer" } : undefined}>
      <p className="kpi-value" style={{ fontSize: "1.4rem", color: c }}>{v}</p>
      <p className="kpi-label">{l}{onClick && animais.length ? " ›" : ""}</p>
    </div>
  );
  const candidatasList: AnimalRow[] = (d.ag?.candidatas_iatf || []).map((c: any) => ({ numero: c.numero_matriz, sit_rep: c.sit_rep, del_dias: c.del_dias }));

  return (
    <div className="p-6 animate-in">
      <div className="mb-5">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Fazenda Estreito Ponte de Pedra</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Pecuária leiteira · Girolando / Holandês · {new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
        </p>
      </div>

      {semDados && (
        <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload dos CSV</a>.</span></div>
      )}

      {/* Alertas */}
      <div className="flex flex-wrap gap-3 mb-5">
        {implanteFalta && <div className="flex items-center gap-2" style={{ background: "rgba(192,57,43,0.15)", border: "1px solid var(--red)", borderRadius: "8px", padding: "0.5rem 0.9rem", fontSize: "0.82rem" }}><Syringe size={15} style={{ color: "var(--red)" }} /> Implante em falta: {Math.ceil(implante.falta)} p/ IATF</div>}
        {contasPagar > 0 && <div className="flex items-center gap-2" style={{ background: "rgba(217,119,6,0.12)", border: "1px solid var(--amber)", borderRadius: "8px", padding: "0.5rem 0.9rem", fontSize: "0.82rem" }}><TrendingDown size={15} style={{ color: "var(--amber)" }} /> {contasPagar} conta(s) a pagar (10 dias)</div>}
        {!!abaixoMin && abaixoMin > 0 && <div className="flex items-center gap-2" style={{ background: "rgba(192,57,43,0.12)", border: "1px solid var(--red)", borderRadius: "8px", padding: "0.5rem 0.9rem", fontSize: "0.82rem" }}><Package size={15} style={{ color: "var(--red)" }} /> {abaixoMin} item(ns) abaixo do mínimo</div>}
      </div>

      {/* KPIs executivos */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <KPI v={reb?.total ?? "—"} l="Fêmeas no rebanho" onClick={() => abrir("Fêmeas no rebanho", () => true)} />
        <KPI v={reb?.vacas_lactacao ?? "—"} l="Vacas em lactação" onClick={() => abrir("Vacas em lactação", (a) => LACTACAO.includes(cod(a.grupo_primario) || ""))} />
        <KPI v={rep?.taxa_prenhez_pct != null ? `${rep.taxa_prenhez_pct}%` : "—"} l="Fêmeas prenhas" c="var(--green-light)" />
        <KPI v={rep?.taxa_concepcao_pct != null ? `${rep.taxa_concepcao_pct}%` : "—"} l="Concepção / serviço" c="var(--blue)" />
        <KPI v={prod?.producao_total_dia_kg != null ? `${prod.producao_total_dia_kg} kg` : "—"} l="Produção/dia (últ. controle)" c="var(--green-light)" />
        <KPI v={prod?.del_medio ?? "—"} l="DEL médio" />
        <div className="kpi-card" onClick={() => candidatasList.length && setModal({ title: "Candidatas IATF", list: candidatasList })} style={candidatasList.length ? { cursor: "pointer" } : undefined}>
          <p className="kpi-value" style={{ fontSize: "1.4rem", color: "var(--dourado-light)" }}>{d.ag?.totais?.candidatas_iatf ?? "—"}</p>
          <p className="kpi-label">Candidatas IATF{candidatasList.length ? " ›" : ""}</p>
        </div>
        <KPI v={resultadoMes != null ? formatBRL(resultadoMes) : "—"} l={`Resultado ${mesLabel}`} c={resultadoMes != null && resultadoMes >= 0 ? "var(--green-light)" : "var(--amber)"} />
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
          ) : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem controle leiteiro — <a href="/upload" style={{ color: "var(--dourado-light)" }}>suba o CSV</a>.</p>}
        </div>
        <div className="card">
          <div className="card-header mb-2 flex items-center gap-2"><HeartPulse size={14} /> Situação Reprodutiva</div>
          {donutRep.length ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={donutRep} dataKey="v" nameKey="nome" cx="50%" cy="50%" innerRadius={45} outerRadius={75} label={(e: any) => `${e.nome} (${e.v})`} labelLine={false} fontSize={10}
                  style={{ cursor: animais.length ? "pointer" : undefined }}
                  onClick={(e: any) => {
                    const nome = e?.name; if (!nome) return;
                    const f = nome === "Prenhes" ? (a: AnimalRow) => a.sit_rep === "Ges." : nome === "Vazias" ? (a: AnimalRow) => (a.sit_rep || "").startsWith("Vaz.") : (a: AnimalRow) => a.sit_rep === "Ins.";
                    abrir(nome, f);
                  }}>
                  {donutRep.map((s: any, i: number) => <Cell key={i} fill={SIT_CORES[s.nome]} />)}
                </Pie>
                <Tooltip contentStyle={tip} />
              </PieChart>
            </ResponsiveContainer>
          ) : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem dados reprodutivos.</p>}
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
          ) : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum evento nos próximos 7 dias.</p>;
        })()}
      </div>

      {modal && <AnimalModal title={modal.title} animais={modal.list} onClose={() => setModal(null)} />}
    </div>
  );
}
