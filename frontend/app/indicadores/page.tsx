"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, TrendingUp, HeartPulse, Milk, BarChart3, Target, RefreshCw, Gauge, LineChart, Baby, Sparkles } from "lucide-react";
import { fetchIndicadores, fetchAnimais, podeModulo } from "@/lib/api";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";
import RelatoriosGerenciais from "@/components/RelatoriosGerenciais";
import RelatorioPersonalizado from "@/components/RelatorioPersonalizado";
import RelatorioBezerras from "@/components/RelatorioBezerras";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";

function pct(v: number | null | undefined) { return v === null || v === undefined ? "—" : `${v}%`; }
function num(v: number | null | undefined, suf = "") { return v === null || v === undefined ? "—" : `${v}${suf}`; }
const cod = (g: string | null | undefined) => (g && /^\d\d/.test(g) ? g.slice(0, 2) : null);

function IndicadoresGerais() {
  const [ind, setInd] = useState<any>(null);
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [recarregando, setRecarregando] = useState(false);
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);
  const [catRep, setCatRep] = useState<"todas" | "vaca" | "novilha">("todas");

  const carregar = () => {
    setRecarregando(true);
    fetchIndicadores().then((v) => { setInd(v); setError(null); }).catch((e) => setError(e.message)).finally(() => setRecarregando(false));
    fetchAnimais().then(setAnimais).catch(() => {});
  };

  useEffect(() => { carregar(); }, []);

  const reb = ind?.rebanho, rep = ind?.reproducao, prod = ind?.producao;
  const repCats: any = ind?.reproducao_categorias || { todas: rep };
  const repSel: any = repCats[catRep] || rep;
  const grupos: [string, number][] = reb ? Object.entries(reb.distribuicao_grupos) : [];
  const maxGrupo = grupos.reduce((m, [, n]) => Math.max(m, n), 0) || 1;

  // Drill-down: abre a lista de animais por trás de um número
  const abrir = (title: string, filtro: (a: AnimalRow) => boolean) => {
    if (!animais.length) return;
    setModal({ title, list: animais.filter(filtro) });
  };
  const abrirNums = (title: string, nums?: string[] | null) => {
    // Sempre abre o modal, mesmo sem números (o AnimalModal exibe "Nenhum animal.").
    const set = new Set(nums || []);
    setModal({ title, list: animais.filter((a) => set.has(a.numero)) });
  };
  const clickable: React.CSSProperties = animais.length ? { cursor: "pointer" } : {};
  const dica = animais.length ? " (clique para ver as fêmeas)" : "";
  // Ícone-alvo indica que clicar abre a lista de fêmeas por trás do número.
  const alvo = animais.length ? <Target size={13} style={{ color: "var(--dourado-light)" }} /> : null;
  // Observação/subtítulo do KPI: fonte menor que o título (kpi-label = 0.75rem).
  const legenda: React.CSSProperties = { fontSize: "0.6rem", color: "var(--text-muted)", marginTop: "0.3rem", textTransform: "none", letterSpacing: 0, opacity: 0.85 };
  const desdeLabel = rep?.concepcao_desde
    ? new Date(rep.concepcao_desde + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" })
    : "01/01/2026";

  const porCategoria = (a: AnimalRow) => catRep === "todas" ? true : catRep === "vaca" ? !!a.data_ult_parto : !a.data_ult_parto;
  const linhasRep = useMemo(() => [
    { label: "Fêmeas aptas", v: repSel?.aptas, cor: undefined, nums: repSel?.aptas_nums },
    { label: "Prenhes", v: repSel?.prenhes, cor: "var(--green-light)", f: (a: AnimalRow) => a.sit_rep === "Ges." && porCategoria(a) },
    { label: "Vazias", v: repSel?.vazias, cor: "var(--amber)", f: (a: AnimalRow) => (a.sit_rep || "").startsWith("Vaz.") && porCategoria(a) },
    { label: "Inseminadas (aguard. diagnóstico)", v: repSel?.inseminadas, cor: "var(--blue)", f: (a: AnimalRow) => a.sit_rep === "Ins." && porCategoria(a) },
  ], [repSel, catRep]);

  return (
    <div className="p-6 animate-in">
      <div className="mb-6 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><BarChart3 size={22} style={{ color: "var(--dourado-light)" }} /> Indicadores do Rebanho</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Composição, eficiência reprodutiva e produção — clique nos números para ver as fêmeas.</p>
        </div>
        <button onClick={carregar} className="btn-ghost" title="Recarregar dados" disabled={recarregando}>
          <RefreshCw size={16} className={recarregando ? "animate-spin" : ""} />
        </button>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload dos CSV</a>.</span></div>}
      {!ind && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {ind && <>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{pct(rep?.taxa_prenhez_pct)}</p><p className="kpi-label">Fêmeas prenhas</p><p style={legenda}>% das fêmeas aptas, hoje</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--blue)" }}>{pct(rep?.taxa_concepcao_pct)}</p><p className="kpi-label">Concepção / serviço</p><p style={legenda}>serviços desde {desdeLabel}</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--amber)" }}>{num(rep?.iep_meses, " m")}</p><p className="kpi-label">IEP médio</p><p style={legenda}>todo o histórico</p></div>
          <div className="kpi-card"><p className="kpi-value">{pct(rep?.perc_vazias_pct)}</p><p className="kpi-label">Vazias</p><p style={legenda}>situação atual</p></div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{num(prod?.producao_total_dia_kg, " kg")}</p><p className="kpi-label">Produção/dia (últ. controle)</p><Milk size={18} style={{ color: "var(--text-muted)", marginTop: "0.4rem" }} /></div>
          <div className="kpi-card"><p className="kpi-value">{num(prod?.producao_media_kg, " kg")}</p><p className="kpi-label">Média por vaca</p></div>
          <div className="kpi-card"><p className="kpi-value">{num(prod?.del_medio)}</p><p className="kpi-label">DEL médio (dias)</p></div>
          <div className="kpi-card"><p className="kpi-value">{num(reb?.vacas_lactacao)}</p><p className="kpi-label">Vacas em lactação atual</p></div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card">
            <div className="card-header mb-3 flex flex-wrap items-center gap-2"><HeartPulse size={14} /> Situação Reprodutiva {alvo}<span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>{dica}</span>
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
            <table className="fazenda-table">
              <tbody>
                {linhasRep.map((r: any) => (
                  <tr key={r.label} onClick={() => r.nums !== undefined ? abrirNums(r.label, r.nums) : abrir(r.label, r.f)} style={clickable} className={animais.length ? "row-clickable" : ""}>
                    <td style={{ color: animais.length ? "var(--dourado-light)" : undefined }}>{r.label}</td>
                    <td style={{ fontWeight: 700, textAlign: "right", color: r.cor }}>{num(r.v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="card-header mt-4 mb-2 flex items-center gap-2"><TrendingUp size={14} /> Partos previstos {alvo}</div>
            <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: "0.4rem" }}>A coluna à direita é a <strong>quantidade de fêmeas</strong> com parto previsto no período{dica}.</p>
            <table className="fazenda-table">
              <tbody>
                {[
                  { label: "Próximos 30 dias", key: "em_30_dias" },
                  { label: "Próximos 60 dias", key: "em_60_dias" },
                  { label: "Próximos 90 dias", key: "em_90_dias" },
                ].map((r) => (
                  <tr key={r.key} onClick={() => abrirNums(`Partos previstos — ${r.label.toLowerCase()}`, rep?.partos_previstos_nums?.[r.key])} style={clickable} className={animais.length ? "row-clickable" : ""}>
                    <td style={{ color: animais.length ? "var(--dourado-light)" : undefined }}>{r.label}</td>
                    <td style={{ fontWeight: 700, textAlign: "right" }}>{num(rep?.partos_previstos?.[r.key])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <div className="card-header mb-3 flex items-center gap-2">Composição do Rebanho ({num(reb?.total)} fêmeas) {alvo}<span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>{dica}</span></div>
            <div className="space-y-1.5">
              {grupos.map(([grupo, n]) => (
                <div key={grupo} className={"flex items-center gap-2" + (animais.length ? " row-clickable" : "")} onClick={() => abrir(grupo, (a) => (a.grupo_primario || "(sem grupo)") === grupo)} style={{ ...clickable, padding: "0.15rem 0.25rem", borderRadius: "4px" }}>
                  <span style={{ fontSize: "0.72rem", color: animais.length ? "var(--dourado-light)" : "var(--text-muted)", minWidth: "11rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{grupo}</span>
                  <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: "4px", height: "14px", overflow: "hidden" }}>
                    <div style={{ width: `${(n / maxGrupo) * 100}%`, height: "100%", background: "var(--vinho-light, #8B3A56)", minWidth: "2px" }} />
                  </div>
                  <span style={{ fontSize: "0.75rem", fontWeight: 700, minWidth: "1.6rem", textAlign: "right" }}>{n}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </>}

      {modal && <AnimalModal title={modal.title} animais={modal.list} onClose={() => setModal(null)} />}
    </div>
  );
}

type Aba = "gerais" | "gerencial" | "personalizado" | "bezerras";

export default function IndicadoresPage() {
  const router = useRouter();
  const [aba, setAba] = useState<Aba>("gerais");
  const vePermiteGerencial = podeModulo("reproducao");
  const vePermiteRecria = podeModulo("recria");

  // Recria virou sub-aba de Indicadores (deixou de ter item próprio na
  // Sidebar) — mas o Dossiê Zootécnico continua sendo sua própria página
  // (rota /recria), então o clique nesse item navega em vez de trocar `aba`.
  const subNavTree: SubNavNode[] = useMemo(() => {
    const tree: SubNavNode[] = [{ id: "gerais", label: "Gerais", icon: Gauge }];
    if (vePermiteGerencial) tree.push({ id: "gerencial", label: "Relatórios gerenciais", icon: LineChart });
    tree.push({ id: "personalizado", label: "Relatório personalizado", icon: Sparkles });
    tree.push({ id: "bezerras", label: "Relatório de bezerras", icon: Baby });
    if (vePermiteRecria) tree.push({ id: "recria", label: "Recria", icon: Baby });
    return tree;
  }, [vePermiteGerencial, vePermiteRecria]);
  useSubNavRegister(useMemo(() => ({
    tree: subNavTree, activeId: aba,
    onSelect: (id: string) => (id === "recria" ? router.push("/recria") : setAba(id as Aba)),
  }), [subNavTree, aba, router]));

  return (
    <>
      {aba === "gerais" && <IndicadoresGerais />}
      {aba === "gerencial" && vePermiteGerencial && <div className="p-6 animate-in"><RelatoriosGerenciais /></div>}
      {aba === "personalizado" && <RelatorioPersonalizado />}
      {aba === "bezerras" && <RelatorioBezerras />}
    </>
  );
}
