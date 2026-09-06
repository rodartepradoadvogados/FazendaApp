"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Syringe, MilkOff, TrendingDown, Package, HeartPulse, Target, RefreshCw, Skull, Newspaper, Search, CheckCircle2, ArrowRight, Plus } from "lucide-react";
import {
  fetchIndicadores, fetchAgenda, fetchProducao, fetchResultadoMesRecente, fetchEstoque, fetchAnimais, fetchBaixas, formatBRL,
  fetchNotaCapa, podeModulo, today, getToken, type NotaCapa, type IndicadoresReproducao, type ReproducaoCategoria,
} from "@/lib/api";
import { cartao } from "@/lib/cartaoDrillDown";
import { AreaChart, Area, PieChart, Pie, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";
import { OnboardingChecklist } from "@/components/OnboardingChecklist";
import { Indicador, EstadoVazio } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { NewsButton } from "@/components/NewsButton";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { NotificationBell } from "@/components/NotificationBell";
import { ManualFazendaButton } from "@/components/ManualFazendaModal";
import { LandingPublica } from "@/components/landing/LandingPublica";
import { ehAppDeCampo } from "@/lib/nativo";

const SIT_CORES: Record<string, string> = {
  Prenhes: "var(--green-light)", Inseminadas: "var(--dourado-light)",
  "Em protocolo": "var(--vinho-light, #416180)",
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

// A Capa (dashboard) propriamente dita — só renderizada para quem está
// logado. Ver Home() no fim do arquivo, que decide entre esta e a landing
// pública (T8); a divisão em dois componentes existe só por isso, nenhuma
// lógica interna da Capa mudou.
function Capa() {
  const [d, setD] = useState<any>(null);
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);
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

  // Busca rápida por nº de animal (⌘K/Ctrl+K foca o campo) — redesign T1,
  // cabeçalho da Capa. Reaproveita o AnimalModal já usado nos outros
  // drill-downs desta tela; não é uma busca global do site (telas, ajuda
  // etc.), só animais, que é o que se procura com mais urgência no dia a dia.
  const [busca, setBusca] = useState("");
  const buscaRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        buscaRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const buscarAnimal = (e: React.FormEvent) => {
    e.preventDefault();
    const termo = busca.trim().toLowerCase();
    if (!termo || !animais.length) return;
    const achados = animais.filter((a) => a.numero.toLowerCase().includes(termo));
    setModal({ title: `Busca — "${busca.trim()}"`, list: achados });
  };

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
  // Drill-down pela lista de números que o BACKEND contou — o número do card e
  // a lista que ele abre saem da mesma conta (mesmo padrão de `aptas_nums`).
  // Com isso o recorte vaca/novilha também é o do backend (registro de Parto),
  // e não `data_ult_parto` do CSV.
  const abrirNums = (title: string, nums?: string[] | null) => {
    if (!animais.length) return;
    const set = new Set(nums || []);
    setModal({ title, list: animais.filter((a) => set.has(a.numero)) });
  };

  if (!d) return <div className="p-6"><p style={{ color: "var(--text-muted)" }}>Carregando painel…</p></div>;

  const reb = d.ind?.rebanho, prod = d.ind?.producao;
  const rep = d.ind?.reproducao as IndicadoresReproducao | undefined;
  const semDados = !d.ind && !d.ag;

  // Benchmark reprodutivo (nosso valor × meta × média do país), por categoria
  // — o comparativo completo (medidores + tabela de meta/média do país) migrou
  // para Indicadores (redesign T1); aqui só lê os dois valores que viraram
  // KPI ("Prenhez/21d" e "Taxa de serviço").
  const benchCats: any = d.ind?.benchmark_categorias || { todas: d.ind?.benchmark || [] };
  const bench: any[] = benchCats[catRep] || benchCats.todas || [];
  const bm = (k: string) => bench.find((b) => b.chave === k) || {};

  // Resultado do mês mais recente (competência) — já vem pronto do backend
  // (GET /financeiro/resultado-mes-recente), sem precisar do extrato
  // financeiro completo no cliente.
  const resultadoMes: number | null = d.resMes?.resultado ?? null;
  const mesLabel: string = d.resMes?.mes ?? "";

  const abaixoMin = d.est ? d.est.filter((i: any) => i.abaixo_minimo === true).length : null;
  const implante = d.ag?.hormonios_check?.find((h: any) => h.nome?.toLowerCase().includes("implante") || h.nome?.toLowerCase().includes("sincrogest"));
  const implanteFalta = implante && !implante.suficiente;
  const contasPagar = d.ag?.totais?.contas_a_pagar ?? 0;

  // Bloco "Hoje" (redesign T1, mockup 1b): tudo que precisa ser feito hoje —
  // o que já está atrasado (data < hoje) mais o que vence hoje — mesma fonte
  // que a Agenda usa (d.ag.eventos), só um recorte mais curto pra Capa. Ação
  // de fato (marcar realizado etc.) continua só na Agenda — aqui é resumo +
  // atalho, não duplica a lógica de baixa por tipo de evento.
  const hoje = today();
  const eventosAtivos: any[] = (d.ag?.eventos || []).filter((e: any) => !e.comunicado);
  const tarefasAtrasadas = eventosAtivos.filter((e: any) => e.data < hoje);
  const tarefasDeHoje = eventosAtivos.filter((e: any) => e.data === hoje);
  const tarefasHoje = [...tarefasAtrasadas, ...tarefasDeHoje];
  const TAREFAS_VISIVEIS = 4;

  const serieProd = (d.prod?.serie_temporal || []).slice(-12).map((s: any) => ({
    mes: s.data ? new Date(s.data + "T00:00:00").toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }).replace(".", "") : "",
    kg: s.media_kg,
  }));
  const kgs = serieProd.map((s: any) => s.kg).filter((v: any) => v != null) as number[];
  const kgMin = kgs.length ? Math.floor(Math.min(...kgs) - 1) : 0;
  const kgMax = kgs.length ? Math.ceil(Math.max(...kgs) + 1) : 30;
  // Mesma rede de segurança de app/indicadores/page.tsx: sem
  // `reproducao_categorias` (payload de cache antigo), cai de volta no bloco
  // `reproducao`, que não tem todos os `_nums` de `ReproducaoCategoria` — o
  // cast só nomeia essa lacuna pré-existente.
  const repSel = (d.ind?.reproducao_categorias?.[catRep] || rep) as ReproducaoCategoria | undefined;
  // As 6 fatias são uma partição do rebanho da categoria (por isso somam o
  // total): "Em protocolo" entrou justamente porque não cabia em nenhuma das
  // outras — sem ela o donut ficava faltando animais.
  const donutRep = repSel ? [
    { nome: "Prenhes", v: repSel.prenhes, nums: repSel.prenhes_nums },
    { nome: "Inseminadas", v: repSel.inseminadas, nums: repSel.inseminadas_nums },
    { nome: "Em protocolo", v: repSel.em_protocolo, nums: repSel.em_protocolo_nums },
    { nome: "PEV", v: repSel.pev, nums: repSel.pev_nums },
    { nome: "A inseminar", v: repSel.a_inseminar, nums: repSel.a_inseminar_nums },
    { nome: "Vazias", v: repSel.nao_classificadas, nums: repSel.nao_classificadas_nums },
  ].filter((x) => x.v > 0) : [];

  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" };

  const KPI = ({ v, l, c, cat, onClick, podeClicar }: { v: any; l: string; c?: string; cat?: "geral" | "reprodutivo" | "producao" | "financeiro"; onClick?: () => void; podeClicar?: boolean }) => (
    <Indicador
      valor={v} rotulo={l} categoria={cat} cor={c}
      onClick={onClick} podeClicar={podeClicar ?? animais.length > 0}
      extra={onClick ? <Target size={11} style={{ color: "var(--dourado-light)" }} /> : null}
    />
  );
  const candidatasList: AnimalRow[] = (d.ag?.candidatas_iatf || []).map((c: any) => ({ numero: c.numero_matriz, sit_rep: c.estado_rotulo || c.sit_rep, del_dias: c.del_dias }));
  const aDescartarList: AnimalRow[] = animais.filter((a) => a.a_descartar);
  const descartadosList = baixas.filter((b) => TIPOS_DESCARTE.includes(b.tipo_baixa) && (!desdeDescarte || b.data_baixa >= desdeDescarte));

  return (
    <div className="p-6 animate-in">
      {/* Cabeçalho: título/subtítulo + busca/News/tema/sino no fluxo normal —
          redesign T1 (mockup 1b). Nas demais telas esses três últimos
          continuam fixos no topo (ver AuthShell.tsx); só aqui saem do
          position:fixed, porque a Capa é a única com esse cabeçalho próprio
          logo abaixo do topo (nas outras, SubNavTabs/o cabeçalho de cada
          página fica mais abaixo e continua precisando da faixa fixa). */}
      <div className="mb-5 flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Fazenda Estreito Ponte de Pedra</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Pecuária leiteira · Girolando / Holandês · {new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <form onSubmit={buscarAnimal} className="flex items-center gap-2"
            style={{ border: "1px solid var(--border-strong)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", minWidth: "180px", background: "var(--surface)" }}>
            <Search size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
            <input ref={buscaRef} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar animal…"
              style={{ border: "none", background: "none", outline: "none", fontSize: "0.78rem", color: "var(--text)", width: "100%" }} />
            <span style={{ fontSize: "0.62rem", fontWeight: 600, border: "1px solid var(--border)", borderRadius: "4px", padding: "0.05rem 0.3rem", color: "var(--text-muted)", flexShrink: 0 }}>⌘K</span>
          </form>
          <ManualFazendaButton />
          <NewsButton />
          <ThemeSwitcher />
          <NotificationBell />
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

      {/* Bloco "Hoje" (redesign T1, mockup 1b): abre pela tarefa do dia em vez
          do módulo — tarefas de hoje/atrasadas à esquerda (mesma fonte que a
          Agenda usa), "Fora do esperado" (os 3 alertas que antes eram uma
          faixa solta) à direita. Ação de cada item continua só na Agenda. */}
      <div className="card mb-5" style={{ borderLeft: "3px solid var(--vinho)", padding: 0 }}>
        <div className="flex items-center gap-3 flex-wrap" style={{ padding: "0.7rem 0.9rem", borderBottom: "1px solid var(--border)" }}>
          <span className="card-header" style={{ margin: 0 }}>Hoje</span>
          <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-muted)" }}>
            {tarefasHoje.length} tarefa{tarefasHoje.length === 1 ? "" : "s"}
            {tarefasAtrasadas.length > 0 && <> · <span style={{ color: "var(--red)" }}>{tarefasAtrasadas.length} atrasada{tarefasAtrasadas.length === 1 ? "" : "s"}</span></>}
          </span>
          <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem" }}>
            <a href="/agenda" className="btn-ghost" style={{ fontSize: "0.78rem", padding: "0.35rem 0.7rem" }}>Ver agenda completa</a>
            <a href="/lancamentos" className="btn-ghost" style={{ fontSize: "0.78rem", padding: "0.35rem 0.7rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}><Plus size={13} /> Lançar</a>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-[1fr_236px]">
          <div style={{ padding: "0.6rem 0.9rem", display: "flex", flexDirection: "column", gap: "0.4rem", borderRight: "1px solid var(--border)" }}>
            {tarefasHoje.length ? (
              <>
                {tarefasHoje.slice(0, TAREFAS_VISIVEIS).map((ev: any, i: number) => {
                  const atrasado = ev.data < hoje;
                  return (
                    <a key={ev.id ?? i} href="/agenda"
                      className="flex items-center gap-3"
                      style={{ padding: "0.5rem 0.6rem", border: "1px solid var(--border)", borderLeft: `3px solid ${atrasado ? "var(--red)" : "var(--dourado)"}`, borderRadius: "var(--r-sm)", textDecoration: "none" }}>
                      <span style={{ flex: 1 }}>
                        <span style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--text)" }}>{ev.numero_animal ? `${ev.numero_animal} · ` : ""}{ev.descricao}</span>
                        <span style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                          {ev.categoria}{atrasado ? ` · atrasado desde ${new Date(ev.data + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}` : ""}
                        </span>
                      </span>
                      <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--dourado-light)", display: "flex", alignItems: "center", gap: "0.2rem", flexShrink: 0 }}>Abrir <ArrowRight size={12} /></span>
                    </a>
                  );
                })}
                {tarefasHoje.length > TAREFAS_VISIVEIS && (
                  <a href="/agenda" style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--vinho, var(--dourado-light))", paddingLeft: "0.2rem" }}>
                    + {tarefasHoje.length - TAREFAS_VISIVEIS} tarefa{tarefasHoje.length - TAREFAS_VISIVEIS === 1 ? "" : "s"} de hoje
                  </a>
                )}
              </>
            ) : (
              <EstadoVazio icon={CheckCircle2}>Nada pendente para hoje.</EstadoVazio>
            )}
          </div>
          <div style={{ padding: "0.6rem 0.9rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            <span className="card-header" style={{ fontSize: "0.66rem", margin: 0 }}>Fora do esperado</span>
            {implanteFalta && (
              <div className="flex items-start gap-2" style={{ background: "rgba(168,52,28,0.08)", borderLeft: "3px solid var(--red)", padding: "0.45rem 0.5rem", fontSize: "0.76rem" }}>
                <Syringe size={13} style={{ color: "var(--red)", marginTop: "0.1rem", flexShrink: 0 }} /> Implante em falta: {Math.ceil(implante.falta)} p/ IATF
              </div>
            )}
            {contasPagar > 0 && (
              <div className="flex items-start gap-2" style={{ background: "rgba(185,131,31,0.1)", borderLeft: "3px solid var(--amber)", padding: "0.45rem 0.5rem", fontSize: "0.76rem" }}>
                <TrendingDown size={13} style={{ color: "var(--amber)", marginTop: "0.1rem", flexShrink: 0 }} /> {contasPagar} conta(s) a pagar (10 dias)
              </div>
            )}
            {!!abaixoMin && abaixoMin > 0 && (
              <div className="flex items-start gap-2" style={{ background: "rgba(168,52,28,0.08)", borderLeft: "3px solid var(--red)", padding: "0.45rem 0.5rem", fontSize: "0.76rem" }}>
                <Package size={13} style={{ color: "var(--red)", marginTop: "0.1rem", flexShrink: 0 }} /> {abaixoMin} item(ns) abaixo do mínimo
              </div>
            )}
            {!implanteFalta && !(contasPagar > 0) && !(!!abaixoMin && abaixoMin > 0) && (
              <span style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>Nada fora do esperado.</span>
            )}
          </div>
        </div>
      </div>

      {/* KPIs executivos — 12 no total, em duas grades de 6 (redesign T1): a
          primeira é a visão geral que já existia; a segunda promove pra cima
          os 3 números que antes só apareciam dentro do card de medidores
          (Prenhez/21d, Taxa de serviço, IEP médio) e o descarte, que antes
          vinha só dentro do card de Situação Reprodutiva. O card de medidores
          em si (com meta/média do país) migrou para Indicadores. */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-2">
        <KPI v={reb?.total ?? "—"} l="Fêmeas no rebanho" cat="geral" onClick={() => abrir("Fêmeas no rebanho", () => true)} />
        <KPI v={reb?.vacas_lactacao ?? "—"} l="Vacas em lactação" cat="geral" onClick={() => abrir("Vacas em lactação", (a) => LACTACAO.includes(cod(a.grupo_primario) || ""))} />
        <KPI v={rep?.taxa_prenhez_pct != null ? `${rep.taxa_prenhez_pct}%` : "—"} l="Fêmeas prenhas" cat="reprodutivo" />
        <KPI v={rep?.taxa_concepcao_pct != null ? `${rep.taxa_concepcao_pct}%` : "—"} l="Concepção / serviço" cat="reprodutivo" />
        <KPI v={prod?.producao_total_dia_kg != null ? `${prod.producao_total_dia_kg} kg` : "—"} l="Produção/dia (últ. controle)" cat="producao" />
        <KPI v={prod?.del_medio ?? "—"} l="DEL médio" cat="producao" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-5">
        <KPI v={d.ag?.totais?.candidatas_iatf ?? "—"} l="Candidatas IATF" cat="reprodutivo"
          podeClicar={candidatasList.length > 0}
          onClick={() => setModal({ title: "Candidatas IATF", list: candidatasList })} />
        <KPI v={bm("taxa_prenhez_ciclo").valor != null ? `${bm("taxa_prenhez_ciclo").valor}%` : "—"} l="Prenhez / 21 dias" cat="reprodutivo" podeClicar={false} />
        <KPI v={bm("taxa_servico").valor != null ? `${bm("taxa_servico").valor}%` : "—"} l="Taxa de serviço" cat="reprodutivo" podeClicar={false} />
        <KPI v={rep?.iep_meses ?? "—"} l="IEP médio (meses)" cat="reprodutivo" podeClicar={false} />
        <KPI v={descartadosList.length} l={`Descartadas ${new Date(desdeDescarte + "T00:00:00").getFullYear()}`} cat="geral" c="var(--red)"
          podeClicar={descartadosList.length > 0}
          onClick={() => setModalDescartados({ title: "Descartados", list: descartadosList })} />
        {/* Some por completo (não só o valor) para quem não tem o módulo
            Financeiro contratado — antes o card ficava sempre visível, com
            "—" no lugar do valor, revelando uma métrica paga a quem nunca
            comprou o módulo (ver auditoria de planos). */}
        {podeModulo("financeiro") && (
          <KPI v={resultadoMes != null ? formatBRL(resultadoMes) : "—"} l={`Resultado ${mesLabel}`} cat="financeiro" c={resultadoMes != null && resultadoMes >= 0 ? "var(--green-light)" : "var(--amber)"} />
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
              {/* Cada card é um Cartao (lib/cartaoDrillDown.ts): valor e `nums`
                  saem das duas chaves do MESMO `repSel`, tipadas contra
                  `ReproducaoCategoria` — não compila se `nums` apontar para
                  um campo que não existe nesse objeto. */}
              {[
                cartao({ origem: repSel, titulo: "Aptas", conta: "aptas", nums: "aptas_nums" }),
                cartao({ origem: repSel, titulo: "Inseminadas", conta: "inseminadas", nums: "inseminadas_nums" }),
                cartao({ origem: repSel, titulo: "Gestantes", conta: "prenhes", nums: "prenhes_nums" }),
              ].map((c) => (
                <KPI key={c.titulo} l={c.titulo} v={c.valor} cat="reprodutivo" onClick={() => abrirNums(c.titulo, c.nums)} />
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
                    abrirNums(nome, donutRep.find((s: any) => s.nome === nome)?.nums);
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

// Porta de entrada "/" (T8): visitante sem login vê a landing pública, quem
// já está logado vai direto para a Capa — exatamente como antes. AuthShell
// (ver components/AuthShell.tsx::ROTA_PUBLICA) já garante que esta função só
// é chamada depois que a sessão foi checada (nunca durante o "Carregando…"
// nem no servidor) — então getToken() aqui é seguro e não repete a checagem
// de auth: reaproveita o mesmo helper que o próprio AuthShell usa, sem
// contexto/hook novo.
export default function Home() {
  // O manifesto do PWA abre em "/" (ver app/manifest.ts) — o padrão do
  // aplicativo instalado passou a ser o SITE COMPLETO, porque instalar no
  // notebook e cair na casca de celular era o comportamento errado.
  // Aparelho de campo (app nativo, ou PWA instalado numa tela pequena) segue
  // para /app aqui, na abertura, em vez de o manifesto decidir isso por todo
  // mundo. Site aberto no navegador do celular NÃO entra aqui: continua
  // sendo o site, como sempre foi (ver lib/nativo.ts::ehAppDeCampo).
  const router = useRouter();
  useEffect(() => {
    if (!getToken()) return;
    ehAppDeCampo().then((campo) => { if (campo) router.replace("/app"); });
  }, [router]);

  return getToken() ? <Capa /> : <LandingPublica />;
}
