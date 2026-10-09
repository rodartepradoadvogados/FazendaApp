"use client";
// Relatórios › Caixa › Fluxo de caixa — "Para onde foi o dinheiro?"
// Realizado × previsto, mês a mês: os números vêm de GET
// /financeiro/fluxo-caixa-mensal (o dinheiro que passou no banco; com a flag
// das regras novas desligada, os mesmos do Fluxo de caixa antigo). A tela só
// alinha a comparação, desenha as barras com a linha do ano anterior (ou o
// resumo numérico, com menos de 3 meses) e abre o mês dia a dia e por conta.
import { useEffect, useMemo, useState } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";
import { fetchFluxoCaixaMensal } from "@/lib/apiRelatoriosCaixa";
import {
  ESTADO_INICIAL, anoAnterior, brl, delta, deslocar, fimDoMes, formatarDelta, mesCurto, mesLongo, pctSinal, periodoDe, periodoPadrao,
} from "@/lib/relatorioContexto";
import { fraseFluxo, linhasFluxo, temMovimento, usaResumoNumerico, type RespostaFluxo } from "@/lib/relatorioFluxo";
import type { LinhaRelatorio, RelatorioParaExportar } from "@/lib/export";
import { Conferencia, NotasMetodo, PainelGrafico, RelatorioShell, VazioQueEnsina, type KpiDef } from "./RelatorioShell";
import { BarrasMensais, CSS_CAIXA, LegendaBarras, type SerieBarras } from "./graficosCaixa";
import { useContextoRelatorio, useDetalheNaUrl, type TravasContexto } from "./useContextoRelatorio";
import type { PropsRelatorio } from "./comum";

const SITUACAO = { realizado: "", em_curso: "em curso", projetado: "projetado" } as const;
const brl0 = (v: number) => brl(v, 0);

export default function FluxoCaixaView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const [det, abrirDet] = useDetalheNaUrl("det");
  const mesDet = /^\d{4}-\d{2}$/.test(det) ? det : "";
  const travas: TravasContexto = useMemo(() => ({
    reg: "caixa", cmpOrcado: false,
    ...(mesDet ? { rotuloPeriodo: mesLongo(mesDet) } : {}),
    porque: "Fluxo de caixa é o dinheiro que passou no banco: sempre pelo dia do pagamento.",
  }), [mesDet]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const { periodo, comparacao, efetivo } = ctx;

  const [dados, setDados] = useState<RespostaFluxo | null>(null);
  const [dadosCmp, setDadosCmp] = useState<RespostaFluxo | null>(null);
  const [dadosAnt, setDadosAnt] = useState<RespostaFluxo | null>(null);
  const [respMes, setRespMes] = useState<{ mes: string; r: RespostaFluxo } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  // Gráfico e tabela se respondem: o mês sob o mouse/foco de um destaca o mesmo mês no outro.
  const [mesSobre, setMesSobre] = useState<string | null>(null);
  const cmpPeriodo = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const ant = anoAnterior(periodo);
  const centroApi = efetivo.cc === "todos" ? null : efetivo.cc;

  useEffect(() => {
    let vivo = true;
    const ler = (ini: string, fim: string) => fetchFluxoCaixaMensal({ data_inicio: ini, data_fim: fim, centro_custo: centroApi, hoje });
    Promise.all([
      ler(periodo.ini, periodo.fim),
      cmpPeriodo ? ler(cmpPeriodo.ini, cmpPeriodo.fim) : Promise.resolve(null),
      ler(ant.ini, ant.fim).catch(() => null),
    ]).then(([a, b, c]) => { if (vivo) { setDados(a); setDadosCmp(b); setDadosAnt(c); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [periodo.ini, periodo.fim, cmpPeriodo?.ini, cmpPeriodo?.fim, ant.ini, ant.fim, centroApi, hoje, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!mesDet) return;
    let vivo = true;
    fetchFluxoCaixaMensal({ data_inicio: `${mesDet}-01`, data_fim: fimDoMes(mesDet), centro_custo: centroApi, hoje, por_dia: true })
      .then((d) => { if (vivo) setRespMes({ mes: mesDet, r: d }); }).catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [mesDet, centroApi, hoje, tentativa]);

  // O dia a dia do mês aberto (?det=AAAA-MM); a resposta de outro mês não vale.
  const dadosMes = mesDet && respMes?.mes === mesDet ? respMes.r : null;
  const rotuloCmp = cmpPeriodo ? comparacao!.rotulo : null;
  const linhas = useMemo(() => linhasFluxo(dados, cmpPeriodo ? dadosCmp : null, dadosAnt), [dados, dadosCmp, dadosAnt, cmpPeriodo]);
  const resumoNum = usaResumoNumerico(dados);
  const t = dados?.totais;
  const tq = cmpPeriodo ? dadosCmp?.totais ?? null : null;
  const estado = !dados && !erro ? "carregando" : erro && !dados ? "erro" : !temMovimento(dados) ? "vazio" : (mesDet && !dadosMes) ? "carregando" : "ok";
  const nMeses = Math.max(1, dados?.meses.length ?? 1), nMesesCmp = Math.max(1, dadosCmp?.meses.length ?? 1);

  const consultas = (ini: string, fim: string, origem: string, conta?: { codigo: string | null; nome: string }) => props.onConsultas({
    de: ini, ate: fim, periodoPor: "pagamento", origem,
    ...(efetivo.cc !== "todos" ? { centro: efetivo.cc } : {}),
    ...(conta?.codigo ? { conta: conta.codigo, contaNome: conta.nome } : {}),
  });

  const kpis: KpiDef[] = t ? [
    { chave: "sobra", rotulo: "Sobrou no caixa", valor: t.sobra, cmp: tq?.sobra ?? null, formato: "brl0", bom: "sobe", negativoEmVermelho: true,
      sub: "Entradas − saídas que já passaram no banco (sem transferências entre contas próprias)" },
    { chave: "entradas", rotulo: "Entradas", valor: t.entradas, cmp: tq?.entradas ?? null, formato: "brl0", bom: "sobe",
      sub: "Depósito do leite, vendas, empréstimos e aportes recebidos", onAbrir: () => consultas(periodo.ini, periodo.fim, "Fluxo de caixa › Entradas") },
    { chave: "saidas", rotulo: "Saídas", valor: t.saidas, cmp: tq?.saidas ?? null, formato: "brl0", bom: "neutro",
      sub: "Inclui investimentos, parcelas e retiradas — dinheiro que saiu", onAbrir: () => consultas(periodo.ini, periodo.fim, "Fluxo de caixa › Saídas") },
    { chave: "media", rotulo: "Sobra média por mês", valor: Math.round((t.sobra / nMeses) * 100) / 100, cmp: tq ? Math.round((tq.sobra / nMesesCmp) * 100) / 100 : null,
      formato: "brl0", bom: "sobe", negativoEmVermelho: true,
      sub: t.previsto_entradas || t.previsto_saidas ? `Ainda previsto: +${brl0(t.previsto_entradas)} e −${brl0(t.previsto_saidas)}` : `${nMeses} ${nMeses === 1 ? "mês" : "meses"} no período` },
  ] : [];

  const series: SerieBarras[] = [
    { nome: "Entradas", estilo: "entra", valores: linhas.map((l) => l.entradas) },
    { nome: "Saídas", estilo: "sai", valores: linhas.map((l) => l.saidas) },
    { nome: "Sobra do mês", estilo: "resultado", valores: linhas.map((l) => l.sobra) },
  ];
  const temLinhaAnt = linhas.some((l) => l.anoAnterior != null);

  const exportar = (): RelatorioParaExportar | null => {
    if (!dados || !t) return null;
    const contexto = { periodo: mesDet ? mesLongo(mesDet) : periodo.label, comparacao: mesDet ? null : cmpPeriodo?.label ?? null, regime: "pelo dia do pagamento (caixa)", centro: efetivo.cc === "todos" ? "todos os centros" : efetivo.cc };
    if (mesDet && dadosMes) {
      const ls: LinhaRelatorio[] = (dadosMes.dias ?? []).map((d) => ({ valores: [d.data.split("-").reverse().join("/"), d.entradas + d.previsto_entradas, d.saidas + d.previsto_saidas, d.sobra, d.acumulado] }));
      ls.push({ valores: ["Total do mês", dadosMes.totais.entradas + dadosMes.totais.previsto_entradas, dadosMes.totais.saidas + dadosMes.totais.previsto_saidas, dadosMes.totais.sobra_prevista, null], total: true });
      return { titulo: `Fluxo de caixa — ${mesLongo(mesDet)}`, pergunta: "Para onde foi o dinheiro?", contexto,
        colunas: [{ header: "Dia", tipo: "texto" }, { header: "Entradas", tipo: "brl" }, { header: "Saídas", tipo: "brl" }, { header: "Sobra do dia", tipo: "brl" }, { header: "Acumulado no mês", tipo: "brl" }],
        linhas: ls, nomeArquivoBase: "fluxo_de_caixa_dia_a_dia", notas: ["Dias com valor previsto (em aberto ou agendado) somam o previsto."] };
    }
    const comCmp = !!rotuloCmp;
    const ls: LinhaRelatorio[] = linhas.map((l) => {
      const d = comCmp ? delta(l.sobra, l.cmpSobra) : null;
      return { valores: [`${mesLongo(l.competencia)}${SITUACAO[l.situacao] ? ` (${SITUACAO[l.situacao]})` : ""}`, l.entradas, l.saidas, l.sobra,
        ...(comCmp ? [l.cmpSobra, d ? d.abs : null] : [])] };
    });
    ls.push({ valores: ["Total do período", t.entradas + t.previsto_entradas, t.saidas + t.previsto_saidas, t.sobra_prevista, ...(comCmp ? [tq ? tq.sobra_prevista : null, tq ? t.sobra_prevista - tq.sobra_prevista : null] : [])], total: true });
    return {
      titulo: "Fluxo de caixa", pergunta: "Para onde foi o dinheiro?", contexto,
      colunas: [{ header: "Mês", tipo: "texto" }, { header: "Entradas", tipo: "brl" }, { header: "Saídas", tipo: "brl" }, { header: "Sobrou", tipo: "brl" },
        ...(comCmp ? [{ header: `Sobrou em ${rotuloCmp}`, tipo: "brl" as const }, { header: "Δ", tipo: "brl" as const }] : [])],
      linhas: ls, nomeArquivoBase: "fluxo_de_caixa",
      notas: [
        "Sempre pelo dia em que o dinheiro passou no banco. Mês em curso ou futuro soma o que ainda está previsto (em aberto pelo vencimento e pagamentos agendados).",
        `Realizado: entradas ${brl(t.entradas)}, saídas ${brl(t.saidas)}, sobra ${brl(t.sobra)}.`,
        dados.regras_v2 ? "" : "Regras antigas: data de pagamento e valor pago, como no Fluxo de caixa anterior.",
      ].filter(Boolean),
    };
  };

  const vazioUi = (
    <VazioQueEnsina titulo={`Nenhum dinheiro passou no banco em ${periodo.label}`}
      texto={<>O fluxo de caixa junta o que foi pago e recebido no período{efetivo.cc !== "todos" ? ` no centro ${efetivo.cc}` : ""}, e o que ainda vence até o fim dele. Nada caiu aqui:</>}
      itens={[
        { texto: "Pagamentos e recebimentos com data de pagamento no período", pronto: false, acao: <a href="/financeiro?sub=a_pagar">Dar baixa numa conta</a> },
        { texto: "Conta bancária informada na baixa", pronto: true },
      ]}
      acoes={<>
        <button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>
        {efetivo.cc !== "todos" && <button type="button" className="rl-btn" onClick={() => ctx.mudar({ cc: "todos" })}>Ver todos os centros</button>}
      </>} />
  );

  const frase = dados && t && !mesDet ? fraseFluxo({ periodo, r: dados, cmp: tq ? dadosCmp : null, rotuloCmp, brl: brl0, delta: (a, b) => delta(a, b, "sobe") }) : [];
  const opcoesMaiores = [periodoPadrao("t", hoje), periodoDe(`a:${hoje.slice(0, 4)}`)!, periodoPadrao("s", hoje)];

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Caixa" nome="Fluxo de caixa" pergunta="Para onde foi o dinheiro?"
      onIrGrupo={props.onIrGrupo} niveis={mesDet ? [{ rotulo: mesLongo(mesDet) }] : []} onVoltarNivel={() => abrirDet("")}
      estado={estado} erro={erro} onTentarDeNovo={() => { setErro(null); setTentativa((x) => x + 1); }} vazio={vazioUi}
      frase={frase} kpis={mesDet ? undefined : kpis} exportar={exportar}
      avisos={dados && dados.avisos.length > 0 && !mesDet ? <div className="rl-aviso info" role="status"><div>{dados.avisos.map((a) => <p key={a} style={{ margin: 0 }}>{a}</p>)}</div></div> : null}>
      <style>{CSS_CAIXA}</style>
      {!mesDet && dados && t && (<>
        {resumoNum ? (
          <section className="rl-painel" aria-labelledby="rl-fx-res">
            <h3 className="rl-tit" id="rl-fx-res">Resumo do período</h3>
            <dl style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: ".35rem 1.2rem", margin: 0, maxWidth: 560, fontSize: ".92rem" }}>
              <dt>Entradas</dt><dd style={{ margin: 0, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{brl(t.entradas)}</dd>
              <dt>Saídas</dt><dd style={{ margin: 0, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{brl(-t.saidas)}</dd>
              <dt style={{ fontWeight: 700, borderTop: "1px solid var(--border)", paddingTop: ".35rem" }}>Sobrou no caixa</dt>
              <dd style={{ margin: 0, textAlign: "right", fontWeight: 700, borderTop: "1px solid var(--border)", paddingTop: ".35rem", color: t.sobra < 0 ? "var(--st-venc-fg)" : undefined, fontVariantNumeric: "tabular-nums" }}>{brl(t.sobra)}</dd>
              {(t.previsto_entradas > 0 || t.previsto_saidas > 0) && (<>
                <dt>Ainda previsto até o fim do período</dt>
                <dd style={{ margin: 0, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>+{brl(t.previsto_entradas)} · −{brl(t.previsto_saidas)}</dd>
              </>)}
              {tq && rotuloCmp && (<><dt>O mesmo em {rotuloCmp}</dt><dd style={{ margin: 0, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{brl(tq.sobra)}</dd></>)}
            </dl>
            <p style={{ margin: ".8rem 0 .5rem", fontSize: ".82rem", color: "var(--text-muted)" }}>Com menos de 3 meses com movimento, um gráfico de barras engana mais do que ajuda. Para ver a tendência, escolha um período maior:</p>
            <div className="rl-acoes rl-noprint">
              {opcoesMaiores.map((p) => <button key={p.cod} type="button" className="rl-btn" onClick={() => ctx.mudar({ per: p.cod })}>{p.label.charAt(0).toUpperCase() + p.label.slice(1)}</button>)}
            </div>
          </section>
        ) : (
          <PainelGrafico titulo="Entradas, saídas e sobra de cada mês"
            legenda={<LegendaBarras series={series} linha={temLinhaAnt ? "Sobra do mesmo mês do ano anterior" : null} projetado={linhas.some((l) => l.previsto)} />}
            tabela={{ cabecalho: ["Mês", "Entradas", "Saídas", "Sobra", "Ano anterior"], linhas: linhas.map((l) => [
              `${mesLongo(l.competencia)}${l.previsto ? " (com o previsto)" : ""}`, brl(l.entradas), brl(l.saidas), brl(l.sobra), l.anoAnterior != null ? brl(l.anoAnterior) : "—",
            ]) }}>
            <BarrasMensais rotulos={linhas.map((l) => mesCurto(l.competencia))} series={series}
              linha={temLinhaAnt ? { nome: "Mesmo mês do ano anterior", valores: linhas.map((l) => l.anoAnterior) } : null}
              projetado={linhas.map((l) => l.previsto)} onAbrir={(i) => abrirDet(linhas[i].competencia)}
              selecionado={mesSobre ? linhas.findIndex((l) => l.competencia === mesSobre) : null} aoPassar={(i) => setMesSobre(i == null ? null : linhas[i]?.competencia ?? null)}
              rotuloAbrir={(i) => `${mesLongo(linhas[i].competencia)}: entradas ${brl(linhas[i].entradas)}, saídas ${brl(linhas[i].saidas)}, sobra ${brl(linhas[i].sobra)}. Abrir o mês dia a dia`}
              descricao={`Fluxo de caixa mensal de ${periodo.label}: ${linhas.length} meses, sobra total ${brl0(t.sobra_prevista)}.`} />
          </PainelGrafico>
        )}

        <section className="rl-painel" aria-labelledby="rl-fx-tab">
          <h3 className="rl-tit" id="rl-fx-tab">Mês a mês</h3>
          <div className="rl-tw">
            <table className="fazenda-table rl-tab">
              <caption className="rl-sr">Fluxo de caixa mês a mês — {periodo.label}</caption>
              <thead><tr>
                <th scope="col">Mês</th><th scope="col" className="r rl-cx-larga">Entradas</th><th scope="col" className="r rl-cx-larga">Saídas</th><th scope="col" className="r">Sobrou</th>
                {rotuloCmp && <th scope="col" className="r">{rotuloCmp}</th>}{rotuloCmp && <th scope="col" className="r">Δ</th>}{rotuloCmp && <th scope="col" className="r rl-opc">Δ%</th>}
              </tr></thead>
              <tbody>
                {linhas.map((l) => {
                  const d = rotuloCmp ? delta(l.sobra, l.cmpSobra, "sobe") : null;
                  return (
                    <tr key={l.competencia} className={`clic${mesSobre === l.competencia ? " dest" : ""}`}
                      onMouseEnter={() => setMesSobre(l.competencia)} onMouseLeave={() => setMesSobre(null)}
                      onClick={(e) => { if (!(e.target as HTMLElement).closest("button")) abrirDet(l.competencia); }}>
                      <td>
                        <button type="button" className="rl-linkbtn" onClick={() => abrirDet(l.competencia)} aria-label={`${mesLongo(l.competencia)}: abrir dia a dia`}
                          onFocus={() => setMesSobre(l.competencia)} onBlur={() => setMesSobre(null)}>{mesLongo(l.competencia)}<ChevronRight size={14} aria-hidden /></button>
                        {SITUACAO[l.situacao] && <span className="rl-selo" style={{ marginLeft: ".4rem" }}>{SITUACAO[l.situacao]}</span>}
                        {l.previsto && <span className="sub">com o previsto em aberto e agendado</span>}
                        {rotuloCmp && l.cmpCompetencia && <span className="sub">vs {mesCurto(l.cmpCompetencia)}</span>}
                        <span className="sub rl-cx-estreita">entrou {brl(l.entradas)} · saiu {brl(l.saidas)}</span>
                      </td>
                      <td className="r rl-cx-larga">{brl(l.entradas)}</td>
                      <td className="r rl-cx-larga">{brl(l.saidas)}</td>
                      <td className={`r${l.sobra < 0 ? " neg" : ""}`}><b>{brl(l.sobra)}</b></td>
                      {rotuloCmp && <td className="r mut">{l.cmpSobra == null ? "—" : brl(l.cmpSobra)}</td>}
                      {rotuloCmp && <td className="r">{!d ? <span className="mut">—</span> : d.igual ? <span className="mut">=</span> : (
                        <span className={`rl-dt ${d.melhor ? "bom" : "ruim"}`}><span aria-hidden>{d.abs > 0 ? "▲" : "▼"}</span>{formatarDelta(d.abs, "brl")}<span className="rl-sr"> ({d.melhor ? "melhor" : "pior"})</span></span>
                      )}</td>}
                      {rotuloCmp && <td className="r mut rl-opc">{d && !d.igual && d.pct != null && Math.abs(d.pct) < 9.995 ? pctSinal(d.pct) : "—"}</td>}
                    </tr>
                  );
                })}
              </tbody>
              <tfoot><tr>
                <td>Total do período<span className="sub rl-cx-estreita" style={{ fontWeight: 400 }}>entrou {brl(t.entradas + t.previsto_entradas)} · saiu {brl(t.saidas + t.previsto_saidas)}</span></td>
                <td className="r rl-cx-larga">{brl(t.entradas + t.previsto_entradas)}</td><td className="r rl-cx-larga">{brl(t.saidas + t.previsto_saidas)}</td>
                <td className={`r${t.sobra_prevista < 0 ? " neg" : ""}`}>{brl(t.sobra_prevista)}</td>
                {rotuloCmp && <td className="r">{tq ? brl(tq.sobra_prevista) : "—"}</td>}
                {rotuloCmp && <td className="r">{tq ? formatarDelta(t.sobra_prevista - tq.sobra_prevista, "brl") : "—"}</td>}
                {rotuloCmp && <td className="rl-opc" />}
              </tr></tfoot>
            </table>
          </div>
        </section>

        <ContasFluxo dados={dados} titulo={`Por conta gerencial · realizado em ${periodo.curto}`}
          onAbrir={(c) => consultas(periodo.ini, periodo.fim, `Fluxo de caixa › ${c.nome}`, c)} />
      </>)}

      {mesDet && dadosMes && (<>
        <section className="rl-painel" aria-labelledby="rl-fx-dias">
          <h3 className="rl-tit" id="rl-fx-dias">Dia a dia · {mesLongo(mesDet)}</h3>
          {(dadosMes.dias ?? []).length ? (
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Fluxo de caixa dia a dia — {mesLongo(mesDet)}</caption>
                <thead><tr><th scope="col">Dia</th><th scope="col" className="r">Entra</th><th scope="col" className="r">Sai</th><th scope="col" className="r">Sobra do dia</th><th scope="col" className="r">Acumulado</th></tr></thead>
                <tbody>
                  {(dadosMes.dias ?? []).map((d) => {
                    const prev = d.previsto_entradas > 0 || d.previsto_saidas > 0;
                    return (
                      <tr key={d.data} className="clic" onClick={(e) => { if (!(e.target as HTMLElement).closest("button")) consultas(d.data, d.data, `Fluxo de caixa › ${d.data.split("-").reverse().join("/")}`); }}>
                        <td><button type="button" className="rl-linkbtn" onClick={() => consultas(d.data, d.data, `Fluxo de caixa › ${d.data.split("-").reverse().join("/")}`)}
                          aria-label={`${d.data.split("-").reverse().join("/")}: ver os lançamentos em Consultas`}>{d.data.slice(8)}/{d.data.slice(5, 7)}<ChevronRight size={14} aria-hidden /></button>
                          {prev && <span className="sub">previsto (em aberto ou agendado)</span>}</td>
                        <td className="r">{d.entradas + d.previsto_entradas ? brl(d.entradas + d.previsto_entradas) : <span className="mut">—</span>}</td>
                        <td className="r">{d.saidas + d.previsto_saidas ? brl(d.saidas + d.previsto_saidas) : <span className="mut">—</span>}</td>
                        <td className="r">{brl(d.sobra)}</td>
                        <td className={`r${d.acumulado < 0 ? " neg" : ""}`}><b>{brl(d.acumulado)}</b></td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot><tr><td>Total do mês</td><td className="r">{brl(dadosMes.totais.entradas + dadosMes.totais.previsto_entradas)}</td>
                  <td className="r">{brl(dadosMes.totais.saidas + dadosMes.totais.previsto_saidas)}</td><td className="r">{brl(dadosMes.totais.sobra_prevista)}</td><td /></tr></tfoot>
              </table>
            </div>
          ) : <p style={{ margin: 0, fontSize: ".86rem", color: "var(--text-muted)" }}>Nenhum dinheiro passou no banco neste mês.</p>}
          <p style={{ margin: ".7rem 0 0" }}>
            <button type="button" className="rl-btn" onClick={() => consultas(`${mesDet}-01`, fimDoMes(mesDet), `Fluxo de caixa › ${mesLongo(mesDet)}`)}>
              <ExternalLink size={14} aria-hidden /> Ver os lançamentos do mês em Consultas
            </button>
          </p>
        </section>
        <ContasFluxo dados={dadosMes} titulo={`Por conta gerencial · realizado em ${mesLongo(mesDet)}`}
          onAbrir={(c) => consultas(`${mesDet}-01`, fimDoMes(mesDet), `Fluxo de caixa › ${mesLongo(mesDet)} › ${c.nome}`, c)} />
      </>)}

      <NotasMetodo titulo="O que entra no fluxo de caixa"
        entra={[
          ["Regime", "Sempre pelo dia em que o dinheiro passou no banco." + (dados?.regras_v2 ? " Compra no cartão avulso entra no vencimento do cartão." : "")],
          ["Valor", dados?.regras_v2 ? "O que de fato saiu ou entrou (valor pago); sem descontar vale de funcionário." : "O valor pago (ou o da parcela, quando o pago não foi informado) — como no Fluxo de caixa anterior."],
          ["Previsto", "Contas em aberto pelo vencimento (vencidas entram hoje) e pagamentos já baixados com data futura. Só em mês em curso ou futuro; no gráfico, com contorno tracejado."],
          ["Centro de custo", "O centro da nota."],
          ["Saídas", "Incluem investimentos, parcelas de financiamento e retiradas — não são despesa na DRE, mas são dinheiro que saiu."],
        ]}
        naoEntra={["Transferências entre contas próprias (não mudam o total).", "Desgaste dos bens (depreciação não é dinheiro).", "Compensações no acerto do leite que não passam pelo banco."]} />
      {t && !mesDet && (
        <Conferencia fecha={Math.abs(Math.round((linhas.reduce((s, l) => s + l.sobra, 0)) * 100) / 100 - t.sobra_prevista) < 0.05
          && Math.abs(dados!.contas.reduce((s, c) => s + c.liquido, 0) - t.sobra) < 0.05}
          texto={`A soma dos meses (${brl(t.sobra_prevista)}) é o total do período; as contas gerenciais somam o realizado (${brl(t.sobra)}).`} />
      )}
    </RelatorioShell>
  );
}

function ContasFluxo({ dados, titulo, onAbrir }: { dados: RespostaFluxo; titulo: string; onAbrir: (c: { codigo: string | null; nome: string }) => void }) {
  if (!dados.contas.length) return null;
  return (
    <section className="rl-painel" aria-label={titulo}>
      <h3 className="rl-tit">{titulo}</h3>
      <div className="rl-tw">
        <table className="fazenda-table rl-tab rl-cx-conta">
          <caption className="rl-sr">{titulo}</caption>
          <thead><tr><th scope="col">Conta gerencial</th><th scope="col" className="r">Entrou</th><th scope="col" className="r">Saiu</th></tr></thead>
          <tbody>
            {dados.contas.map((c) => (
              <tr key={c.codigo ?? c.nome} className="clic" onClick={(e) => { if (!(e.target as HTMLElement).closest("button")) onAbrir(c); }}>
                <td><button type="button" className="rl-linkbtn" onClick={() => onAbrir(c)} aria-label={`${c.nome}: ver os lançamentos em Consultas`}>{c.nome}<ChevronRight size={14} aria-hidden /></button></td>
                <td className="r">{c.entradas ? brl(c.entradas) : <span className="mut">—</span>}</td>
                <td className="r">{c.saidas ? brl(c.saidas) : <span className="mut">—</span>}</td>
              </tr>
            ))}
          </tbody>
          <tfoot><tr><td>Total realizado</td><td className="r">{brl(dados.totais.entradas)}</td><td className="r">{brl(dados.totais.saidas)}</td></tr></tfoot>
        </table>
      </div>
    </section>
  );
}
