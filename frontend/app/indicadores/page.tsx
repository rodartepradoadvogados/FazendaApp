"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, TrendingUp, HeartPulse, Milk, BarChart3, Target, RefreshCw, LineChart, Baby } from "lucide-react";
import { fetchIndicadores, fetchAnimais, podeModulo, type IndicadoresResposta } from "@/lib/api";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";
import RelatoriosGerenciais from "@/components/RelatoriosGerenciais";
import RelatorioBezerras from "@/components/RelatorioBezerras";
import NaoConformidades from "@/components/NaoConformidades";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { Indicador } from "@/components/ui";

function pct(v: number | null | undefined) { return v === null || v === undefined ? "—" : `${v}%`; }
function num(v: number | null | undefined, suf = "") { return v === null || v === undefined ? "—" : `${v}${suf}`; }
const cod = (g: string | null | undefined) => (g && /^\d\d/.test(g) ? g.slice(0, 2) : null);
const LACTACAO = ["01", "02", "03"];

export function IndicadoresGerais() {
  const [ind, setInd] = useState<IndicadoresResposta | null>(null);
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

  // O rótulo do card leva a data do controle junto: sem ela, "produção do dia"
  // é uma frase que não diz de qual dia — e é a falta dessa data que escondia
  // a vaca controlada em março entrando na mesma soma de quem foi ordenhada
  // ontem.
  const dataControleLabel = prod?.data_controle
    ? new Date(prod.data_controle + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })
    : null;
  const rotuloProducaoDia = dataControleLabel ? `Produção do dia · ${dataControleLabel}` : "Produção do dia · sem controle lançado";
  const tituloModalControleDia = dataControleLabel ? `Controle leiteiro — ${dataControleLabel}` : "Controle leiteiro do dia";

  // Cada linha abre a lista que o próprio backend contou (`*_nums`), e não um
  // refiltro do `sit_rep` congelado do CSV: o número do card e a lista que ele
  // abre passam a vir da mesma conta, inclusive no recorte vaca/novilha (que
  // no backend sai do registro de Parto, não de `data_ult_parto`).
  const linhasRep = useMemo(() => [
    { label: "Fêmeas aptas", v: repSel?.aptas, cor: undefined, nums: repSel?.aptas_nums },
    { label: "Prenhes", v: repSel?.prenhes, cor: "var(--green-light)", nums: repSel?.prenhes_nums },
    { label: "Vazias", v: repSel?.vazias, cor: "var(--amber)", nums: repSel?.vazias_nums },
    { label: "Inseminadas (aguard. diagnóstico)", v: repSel?.inseminadas, cor: "var(--blue)", nums: repSel?.inseminadas_nums },
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

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importe os dados</a>.</span></div>}
      {!ind && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {ind && <>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Indicador categoria="reprodutivo" cor="var(--green-light)" valor={pct(rep?.taxa_prenhez_pct)}
            rotulo={<>Fêmeas prenhas<span style={{ ...legenda, display: "block" }}>% do rebanho no programa reprodutivo, hoje</span></>}
            onClick={() => abrirNums("Fêmeas prenhas", rep?.prenhes_programa_nums)} />
          <Indicador categoria="reprodutivo" cor="var(--blue)" valor={pct(rep?.taxa_concepcao_pct)}
            rotulo={<>Concepção / serviço<span style={{ ...legenda, display: "block" }}>serviços desde {desdeLabel}</span></>} />
          <Indicador categoria="reprodutivo" cor="var(--amber)" valor={num(rep?.iep_meses, " m")}
            rotulo={<>IEP médio<span style={{ ...legenda, display: "block" }}>todo o histórico</span></>} />
          <Indicador categoria="reprodutivo" cor="var(--dourado-light)" valor={pct(rep?.perc_vazias_pct)}
            rotulo={<>Vazias<span style={{ ...legenda, display: "block" }}>situação atual</span></>}
            onClick={() => abrirNums("Vazias", rep?.vazias_programa_nums)} />
        </div>

        {/* Produção do dia é o número que o dono olha primeiro todo dia — vira a
            âncora da tela em vez de disputar o mesmo tamanho dos outros 3 dados
            de produção, que continuam do lado, só menores. O card abre a
            própria lista que ele soma (`controle_nums`, via abrirNums — o
            mesmo mecanismo dos cards reprodutivos), então os dois números
            nunca mais divergem por construção. */}
        <div className="card mb-6" style={{ padding: "1.1rem 1.4rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "2.2rem", flexWrap: "wrap" }}>
            <div style={{ cursor: "pointer" }} onClick={() => abrirNums(tituloModalControleDia, prod?.controle_nums)}>
              <div style={{ fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                <Milk size={13} /> {rotuloProducaoDia}
              </div>
              <div style={{ fontFamily: "var(--font-heading)", fontSize: "3rem", fontWeight: 800, lineHeight: 1, color: "var(--green-light)", marginTop: "0.25rem", fontVariantNumeric: "tabular-nums" }}>
                {dataControleLabel ? num(prod?.producao_total_dia_kg, " kg") : "—"}
              </div>
              {/* Cobertura: o número sozinho esconde se faltou ordenhar alguém
                  antes de o dono concluir que a produção caiu. */}
              {dataControleLabel && (
                <div style={legenda}>{num(prod?.vacas_no_controle)} de {num(prod?.vacas_lactacao)} lactantes</div>
              )}
            </div>
            <div style={{ flex: 1, display: "flex", justifyContent: "flex-end", gap: "2rem", flexWrap: "wrap" }}>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: "1.15rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{num(prod?.producao_media_kg, " kg")}</div>
                <div style={{ fontSize: "0.64rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Média/vaca</div>
              </div>
              <div style={{ textAlign: "right", ...clickable }} onClick={() => abrir("Vacas em lactação atual", (a) => LACTACAO.includes(cod(a.grupo_primario) || "") )}>
                <div style={{ fontSize: "1.15rem", fontWeight: 700, fontVariantNumeric: "tabular-nums", color: animais.length ? "var(--dourado-light)" : undefined }}>{num(reb?.vacas_lactacao)}</div>
                <div style={{ fontSize: "0.64rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Em lactação</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: "1.15rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{num(prod?.del_medio)}</div>
                <div style={{ fontSize: "0.64rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>DEL médio{prod?.del_medio != null ? ` · de ${prod.del_medio_animais}` : ""}</div>
              </div>
            </div>
          </div>
          {/* Acumulado antigo (último controle de CADA vaca, qualquer data) —
              não pode simplesmente sumir da tela quando o significado do card
              muda, senão quem olhava esse número perde a referência sem aviso. */}
          {!!prod?.ultimo_por_animal && prod.ultimo_por_animal.producao_total_kg > 0 && (
            <div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>
              Acumulado do último controle de cada vaca: {num(prod.ultimo_por_animal.producao_total_kg, " kg")}
              {prod.ultimo_por_animal.congelado > 0 && (
                <>
                  {" — "}
                  <span style={{ cursor: "pointer", textDecoration: "underline" }}
                    onClick={() => abrirNums("Ainda no valor congelado do CSV importado", prod.ultimo_por_animal.congelado_nums)}>
                    {prod.ultimo_por_animal.congelado} ainda do CSV importado
                  </span>
                </>
              )}
            </div>
          )}
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
                  <tr key={r.label} onClick={() => abrirNums(r.label, r.nums)} style={clickable} className={animais.length ? "row-clickable" : ""}>
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
                <div key={grupo} className={"flex items-center gap-2" + (animais.length ? " row-clickable" : "")} onClick={() => abrir(grupo, (a) => (a.grupo_primario || "(sem grupo)") === grupo)} style={{ ...clickable, padding: "0.15rem 0.25rem", borderRadius: "var(--r-sm)" }}>
                  <span style={{ fontSize: "0.72rem", color: animais.length ? "var(--dourado-light)" : "var(--text-muted)", minWidth: "11rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{grupo}</span>
                  <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: "var(--r-sm)", height: "14px", overflow: "hidden" }}>
                    <div style={{ width: `${(n / maxGrupo) * 100}%`, height: "100%", background: "var(--vinho-light, #416180)", minWidth: "2px" }} />
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

// "Indicadores do Rebanho" (IndicadoresGerais) virou sub-aba de Rebanho — não
// fica mais aqui em Análise. Ver frontend/app/rebanho/page.tsx.
// "Relatório personalizado" migrou para a aba Relatórios (ver
// frontend/app/analise-relatorios/page.tsx) — não fica mais aqui.
type Aba = "gerencial" | "naoconformidades" | "bezerras";

export default function IndicadoresPage() {
  const router = useRouter();
  const vePermiteGerencial = podeModulo("reproducao");
  const vePermiteRecria = podeModulo("recria");
  const [aba, setAba] = useState<Aba>(vePermiteGerencial ? "gerencial" : "bezerras");

  // Recria virou sub-aba de Indicadores (deixou de ter item próprio na
  // Sidebar) — mas o Dossiê Zootécnico continua sendo sua própria página
  // (rota /recria), então o clique nesse item navega em vez de trocar `aba`.
  const subNavTree: SubNavNode[] = useMemo(() => {
    const tree: SubNavNode[] = [];
    if (vePermiteGerencial) tree.push({ id: "gerencial", label: "Indicadores Gerais", icon: LineChart });
    // Visão única do que está fora da meta em reprodução, recria, financeiro
    // e manejo — reaproveita os mesmos cálculos das telas de origem, ver
    // GET /nao-conformidades (backend/fazenda/api/routers/nao_conformidades.py).
    if (vePermiteGerencial) tree.push({ id: "naoconformidades", label: "Não Conformidades", icon: AlertTriangle });
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
      {aba === "gerencial" && vePermiteGerencial && <div className="p-6 animate-in"><RelatoriosGerenciais /></div>}
      {aba === "naoconformidades" && vePermiteGerencial && <div className="p-6 animate-in"><NaoConformidades /></div>}
      {aba === "bezerras" && <RelatorioBezerras />}
    </>
  );
}
