"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, MilkOff, TrendingDown, HeartPulse, Gauge as GaugeIcon, ChevronDown, ChevronRight, Target, RefreshCw, Skull, Calendar, Newspaper } from "lucide-react";
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

// Esqueleto de carregamento — mesmo formato das seções reais da Capa (Hoje +
// grade de KPI), em vez do texto solto "Carregando painel…" (achado da
// crítica, ver docs/agents/design-implementation.md §5, por-secao.html).
function PainelSkeleton() {
  return (
    <div className="p-6">
      <div className="skeleton" style={{ height: "1.6rem", width: "18rem", marginBottom: "0.5rem" }} />
      <div className="skeleton" style={{ height: "0.9rem", width: "22rem", marginBottom: "1.6rem" }} />
      <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem", marginBottom: "1.4rem" }}>
        {[0, 1].map((i) => (
          <div key={i} className="card" style={{ padding: "0.75rem 0.95rem", borderLeft: "4px solid var(--border)" }}>
            <div className="skeleton" style={{ height: "0.9rem", width: "60%", marginBottom: "0.4rem" }} />
            <div className="skeleton" style={{ height: "0.7rem", width: "35%" }} />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="kpi-card" style={{ borderLeftColor: "var(--border)" }}>
            <div className="skeleton" style={{ width: 28, height: 28, borderRadius: "50%", marginBottom: "0.5rem" }} />
            <div className="skeleton" style={{ height: "1.5rem", width: "70%", marginBottom: "0.4rem" }} />
            <div className="skeleton" style={{ height: "0.6rem", width: "50%" }} />
          </div>
        ))}
      </div>
    </div>
  );
}

// Erro por seção — nomeia o que falhou e oferece retry ali mesmo, em vez de
// um banner genérico pra página inteira (docs/agents/design-implementation.md
// §5, por-secao.html).
function ErroSecao({ mensagem, detalhe, onRetry }: { mensagem: string; detalhe: string; onRetry: () => void }) {
  return (
    <div className="mb-4" style={{ background: "color-mix(in srgb, var(--red) 8%, var(--surface))", border: "1px dashed var(--red)", borderRadius: "var(--r)", padding: "0.8rem 1rem", display: "flex", alignItems: "flex-start", gap: "0.7rem" }}>
      <AlertTriangle size={18} style={{ color: "var(--red)", flexShrink: 0, marginTop: "0.1rem" }} />
      <div style={{ flex: 1 }}>
        <p style={{ fontSize: "0.86rem", fontWeight: 700, color: "var(--text)" }}>{mensagem}</p>
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{detalhe}</p>
      </div>
      <button onClick={onRetry} className="btn-ghost" style={{ flexShrink: 0, fontSize: "0.78rem" }}>↻ Tentar novamente</button>
    </div>
  );
}

// Seta de tendência — hoje vs. o mesmo indicador recalculado 7 dias atrás
// (mesmo endpoint real, /indicadores e /agenda aceitam `data` de referência
// e recalculam de verdade a partir dos registros — não é série fabricada,
// ver docs/agents/design-implementation.md §5, meta-batida.html). Some
// silenciosamente se o comparativo não carregou — é um extra, não bloqueia nada.
function Delta({ atual, anterior, sufixo = "", casasDecimais = 0 }: { atual: number | null | undefined; anterior: number | null | undefined; sufixo?: string; casasDecimais?: number }) {
  if (atual == null || anterior == null) return null;
  const diff = Number((atual - anterior).toFixed(casasDecimais));
  if (diff === 0) return <span style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", marginLeft: "0.35rem" }}>▬</span>;
  const subiu = diff > 0;
  return (
    <span style={{ fontSize: "0.72rem", fontWeight: 700, color: subiu ? "var(--green-light)" : "var(--red)", marginLeft: "0.35rem" }} title="Comparado a 7 dias atrás">
      {subiu ? "▲" : "▼"} {subiu ? "+" : ""}{diff}{sufixo}
    </span>
  );
}

export default function Home() {
  const [d, setD] = useState<any>(null);
  // Comparativo de 7 dias — recalculado de verdade pelo backend (data_ref),
  // nunca fabricado no cliente (achado da crítica original: inventar
  // tendência seria mentir pro dono da fazenda).
  const [dAnterior, setDAnterior] = useState<any>(null);
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);
  const [benchAberto, setBenchAberto] = useState(false);
  const [catRep, setCatRep] = useState<"todas" | "vaca" | "novilha">("todas");
  const [recarregando, setRecarregando] = useState(false);
  // Por fonte (não um booleano só): cada seção mostra seu próprio erro,
  // nomeando o que falhou, em vez de um banner genérico de página inteira
  // (achado da crítica, ver docs/agents/design-implementation.md §5,
  // por-secao.html). "Tentar novamente" recarrega tudo — as 5 fontes já
  // saem juntas do mesmo Promise.allSettled, então isolar o retry por fonte
  // exigiria separar essa orquestração; o que se resolve aqui é a seção
  // errada não mais escondendo QUAL fonte falhou.
  const [errosFonte, setErrosFonte] = useState<{ ind?: boolean; ag?: boolean; prod?: boolean; resMes?: boolean; est?: boolean }>({});

  const [baixas, setBaixas] = useState<any[]>([]);
  const [desdeDescarte, setDesdeDescarte] = useState(() => `${new Date().getFullYear()}-01-01`);
  const [modalDescartados, setModalDescartados] = useState<{ title: string; list: any[] } | null>(null);
  const ordDescartados = useOrdenacao(modalDescartados?.list ?? []);
  // Nota informativa simples (distinta de matéria de blog) — atualizável só
  // pelo dono da plataforma; some quando não há nenhuma ativa.
  const [nota, setNota] = useState<NotaCapa | null>(null);
  const [notaFechada, setNotaFechada] = useState(false);
  // Streak de sanidade (meta-batida.html): dias desde a última baixa registrada.
  const datasBaixa = baixas.map((b: any) => b.data_baixa).filter(Boolean).sort();
  const diasSemBaixa = datasBaixa.length
    ? Math.max(0, Math.floor((Date.now() - new Date(datasBaixa[datasBaixa.length - 1] + "T00:00:00").getTime()) / 86400000))
    : null;
  // Sheen do card de meta batida (exceção aprovada ao DESIGN.md — ver
  // docs/agents/design-implementation.md §5, meta-batida.html, variante Ousada).
  const [metaSheen, setMetaSheen] = useState(false);
  const reduzMovimento = typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  const carregar = () => {
    setRecarregando(true);
    fetchNotaCapa().then(setNota).catch(() => {});
    Promise.allSettled([
      fetchIndicadores(), fetchAgenda(), fetchProducao(), fetchResultadoMesRecente(), fetchEstoque(),
    ]).then(([ind, ag, prod, resMes, est]) => {
      setErrosFonte({
        ind: ind.status === "rejected", ag: ag.status === "rejected", prod: prod.status === "rejected",
        resMes: resMes.status === "rejected", est: est.status === "rejected",
      });
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

    // Comparativo de 7 dias atrás — mesmo endpoint real recalculado com
    // `data` de referência passada. Não-bloqueante e silencioso: se falhar,
    // as setas de tendência simplesmente não aparecem, sem afetar o resto
    // da Capa (docs/agents/design-implementation.md §5, meta-batida.html).
    const seteDiasAtras = new Date();
    seteDiasAtras.setDate(seteDiasAtras.getDate() - 7);
    const dataAnteriorStr = seteDiasAtras.toISOString().slice(0, 10);
    Promise.allSettled([fetchIndicadores(dataAnteriorStr), fetchAgenda(dataAnteriorStr)])
      .then(([indAnt, agAnt]) => {
        setDAnterior({
          ind: indAnt.status === "fulfilled" ? indAnt.value : null,
          ag: agAnt.status === "fulfilled" ? agAnt.value : null,
        });
      });
  };

  useEffect(() => { carregar(); }, []);

  // Passa o brilho uma vez quando o streak de sanidade aparece (reduced-motion desliga).
  useEffect(() => {
    if (reduzMovimento || diasSemBaixa == null) return;
    const t = requestAnimationFrame(() => setMetaSheen(true));
    return () => cancelAnimationFrame(t);
  }, [reduzMovimento, diasSemBaixa]);

  const abrir = (title: string, filtro: (a: AnimalRow) => boolean) => { if (animais.length) setModal({ title, list: animais.filter(filtro) }); };

  if (!d) return <PainelSkeleton />;

  const reb = d.ind?.rebanho, rep = d.ind?.reproducao, prod = d.ind?.producao;
  // Comparativo de 7 dias — mesma forma dos valores atuais, calculada sobre
  // o recálculo real do backend (ver `carregar`, acima).
  const rebAnt = dAnterior?.ind?.rebanho, repAnt = dAnterior?.ind?.reproducao, prodAnt = dAnterior?.ind?.producao;
  const candidatasIatfAnt: number | null = dAnterior?.ag?.totais?.candidatas_iatf ?? null;
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

  // Módulo "Hoje" — agenda do dia com severidade real (crítico/atenção/rotina),
  // a partir dos sinais que já existem (implante, estoque, contas, eventos).
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
  const hojeLimite = new Date(hoje); hojeLimite.setDate(hojeLimite.getDate() + 7);
  const eventosProximos = (d.ag?.eventos || [])
    .filter((e: any) => { const dt = new Date(e.data + "T00:00:00"); return dt >= hoje && dt <= hojeLimite; })
    .slice(0, 5);
  const hojeItems: { sev: "critico" | "atencao" | "rotina"; titulo: string; meta?: string }[] = [
    ...(implanteFalta ? [{ sev: "critico" as const, titulo: "Estoque de implante insuficiente para IATF", meta: `Faltam ${Math.ceil(implante.falta)} doses` }] : []),
    ...(!!abaixoMin && abaixoMin > 0 ? [{ sev: "critico" as const, titulo: `${abaixoMin} item(ns) de estoque abaixo do mínimo`, meta: "Reposição recomendada" }] : []),
    ...(contasPagar > 0 ? [{ sev: "atencao" as const, titulo: `${contasPagar} conta(s) vencem nos próximos 10 dias`, meta: "Contas a pagar" }] : []),
    ...eventosProximos.map((ev: any) => ({
      sev: "rotina" as const,
      titulo: ev.descricao,
      meta: new Date(ev.data + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }),
    })),
  ];

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
  const Secao = ({ cor, label }: { cor: string; label: string }) => (
    <div style={{ fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--text-muted)", margin: "1.4rem 0 0.6rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: cor, display: "inline-block" }} />
      {label}
      <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
    </div>
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

      {semDados && (
        <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importe os dados</a>.</span></div>
      )}

      {(errosFonte.ag || errosFonte.est) && (
        <ErroSecao
          mensagem="Não foi possível carregar a agenda do dia"
          detalhe="Falha ao consultar agenda/estoque — os outros módulos abaixo não foram afetados."
          onRetry={carregar}
        />
      )}

      {/* Módulo "Hoje" — agenda do dia com severidade real, promovida ao topo
          (docs/agents/design-implementation.md §5, Frente 1, hoje-primeiro.html). */}
      <div className="mb-5 animate-in" style={{ animationDelay: "0ms" }}>
        <div style={{ fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--text-muted)", margin: "0 0 0.6rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          Hoje<span style={{ flex: 1, height: 1, background: "var(--border)" }} />
        </div>
        {hojeItems.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
            {hojeItems.map((item, i) => {
              const SEV = {
                critico: { label: "Crítico", cor: "var(--red)", Icon: AlertTriangle },
                atencao: { label: "Atenção", cor: "var(--amber)", Icon: TrendingDown },
                rotina: { label: "Hoje", cor: "var(--vinho-light)", Icon: Calendar },
              }[item.sev];
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.8rem", padding: "0.75rem 0.95rem", background: "var(--surface)", border: "1px solid var(--border)", borderLeft: `4px solid ${SEV.cor}`, borderRadius: "var(--r)", boxShadow: "var(--shadow)" }}>
                  <span style={{ fontSize: "0.62rem", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", flexShrink: 0, width: "64px", color: SEV.cor }}>{SEV.label}</span>
                  <SEV.Icon size={20} style={{ flexShrink: 0, color: SEV.cor }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text)" }}>{item.titulo}</div>
                    {item.meta && <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.1rem" }}>{item.meta}</div>}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Nada pendente para hoje.</p>
        )}
      </div>

      {/* KPIs executivos, agrupados por assunto (hoje-primeiro.html) */}
      {errosFonte.ind && (
        <ErroSecao
          mensagem="Não foi possível carregar os indicadores do rebanho"
          detalhe="Falha ao consultar /indicadores — Hoje e Financeiro não foram afetados."
          onRetry={carregar}
        />
      )}
      <div className="animate-in" style={{ animationDelay: "60ms" }}>
      <Secao cor="var(--vinho-light)" label="Rebanho" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <KPI v={reb?.total ?? "—"} l="Fêmeas no rebanho" cat="geral" onClick={() => abrir("Fêmeas no rebanho", () => true)} />
        <KPI v={<>{reb?.vacas_lactacao ?? "—"}<Delta atual={reb?.vacas_lactacao} anterior={rebAnt?.vacas_lactacao} /></>} l="Vacas em lactação · 7 dias" cat="geral" onClick={() => abrir("Vacas em lactação", (a) => LACTACAO.includes(cod(a.grupo_primario) || ""))} />
        {/* Exceção aprovada ao DESIGN.md (No-Lift / sem gradiente): o card de
            meta batida (Sanidade) ganha elevação 3px + sombra dourada + sheen,
            só aqui — docs/agents/design-implementation.md §5, meta-batida.html
            (variante Ousada). Não estender a outros componentes. */}
        {diasSemBaixa != null && (
          <div className="kpi-card" style={{ position: "relative", overflow: "hidden", ["--kpi-c" as any]: "var(--cat-sanidade)", transform: metaSheen ? "translateY(-3px)" : undefined, boxShadow: metaSheen ? "0 10px 24px rgba(138,109,47,.28), var(--shadow)" : undefined, transition: reduzMovimento ? "none" : "transform .5s ease, box-shadow .5s ease" }}>
            <div style={{ position: "absolute", top: 0, left: metaSheen ? "130%" : "-60%", width: "40%", height: "100%", background: "linear-gradient(75deg, transparent, rgba(255,255,255,.55), transparent)", transform: "skewX(-18deg)", transition: reduzMovimento ? "none" : "left 1.1s ease", pointerEvents: "none" }} />
            <span style={{ position: "absolute", top: "0.7rem", right: "0.7rem", fontSize: "0.6rem", fontWeight: 700, letterSpacing: "0.08em", color: "var(--vinho-dark)", background: "color-mix(in srgb, var(--dourado-light) 30%, transparent)", border: "1px solid var(--dourado)", borderRadius: "999px", padding: "0.15rem 0.55rem" }}>META</span>
            <div className="kpi-chip"><HeartPulse size={15} /></div>
            <p className="kpi-value" style={{ fontSize: "1.4rem", color: "var(--dourado)" }}>{diasSemBaixa}<span style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-muted)", marginLeft: "0.3rem" }}>dias sem baixa</span></p>
            <p className="kpi-label">Sanidade · meta: zero baixas por doença</p>
          </div>
        )}
      </div>

      <Secao cor="var(--cat-reproducao)" label="Reprodução" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <KPI v={<>{rep?.taxa_prenhez_pct != null ? `${rep.taxa_prenhez_pct}%` : "—"}<Delta atual={rep?.taxa_prenhez_pct} anterior={repAnt?.taxa_prenhez_pct} sufixo="pp" casasDecimais={1} /></>} l="Fêmeas prenhas · 7 dias" cat="reprodutivo" />
        <KPI v={<>{rep?.taxa_concepcao_pct != null ? `${rep.taxa_concepcao_pct}%` : "—"}<Delta atual={rep?.taxa_concepcao_pct} anterior={repAnt?.taxa_concepcao_pct} sufixo="pp" casasDecimais={1} /></>} l="Concepção / serviço · 7 dias" cat="reprodutivo" />
        <KPI v={<>{d.ag?.totais?.candidatas_iatf ?? "—"}<Delta atual={d.ag?.totais?.candidatas_iatf} anterior={candidatasIatfAnt} /></>} l="Candidatas IATF · 7 dias" cat="reprodutivo"
          podeClicar={candidatasList.length > 0}
          onClick={() => setModal({ title: "Candidatas IATF", list: candidatasList })} />
      </div>

      <Secao cor="var(--blue)" label="Produção" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        <KPI v={<>{prod?.producao_total_dia_kg != null ? `${prod.producao_total_dia_kg} kg` : "—"}<Delta atual={prod?.producao_total_dia_kg} anterior={prodAnt?.producao_total_dia_kg} sufixo="kg" casasDecimais={1} /></>} l="Produção/dia (últ. controle) · 7 dias" cat="producao" />
        <KPI v={prod?.del_medio ?? "—"} l="DEL médio" cat="producao" />
      </div>
      </div>

      {errosFonte.resMes && podeModulo("financeiro") && (
        <ErroSecao
          mensagem="Não foi possível carregar o resultado do mês"
          detalhe="Falha ao consultar /financeiro/resultado-mes-recente — os demais indicadores não foram afetados."
          onRetry={carregar}
        />
      )}
      <div className="animate-in" style={{ animationDelay: "120ms" }}>
      <Secao cor="var(--cat-financeiro)" label="Financeiro" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
        {/* Some por completo (não só o valor) para quem não tem o módulo
            Financeiro contratado — antes o card ficava sempre visível, com
            "—" no lugar do valor, revelando uma métrica paga a quem nunca
            comprou o módulo (ver auditoria de planos). */}
        {podeModulo("financeiro") && (
          <KPI v={resultadoMes != null ? formatBRL(resultadoMes) : "—"} l={`Resultado ${mesLabel}`} cat="financeiro" c={resultadoMes != null && resultadoMes >= 0 ? "var(--green-light)" : "var(--red)"} />
        )}
      </div>
      </div>

      {/* Medidores reprodutivos (modelo velocímetro) */}
      <div className="card mb-5 animate-in" style={{ animationDelay: "180ms" }}>
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5 animate-in" style={{ animationDelay: "240ms" }}>
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
