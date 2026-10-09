"use client";
// Relatórios › Leite › Custos do leite — "Quanto custa meu litro?"
// Uma tela com quatro visões (?visao=): por litro (COE/L, COT/L e CT/L pela
// metodologia CNA/Embrapa, 12 meses custo × preço), por vaca e lote, por
// hectare e por safra. Substitui as quatro telas antigas (custo_litro_leite,
// custo_vaca_lote, custo_hectare, custo_safra — os ids redirecionam para a
// visão certa). Números SEMPRE do servidor:
//   por litro → GET /financeiro/custos-leite (o Resultado por litro + estimativas por parâmetro);
//   por vaca/lote, hectare e safra → os endpoints da Fase A (numerador único da DRE,
//   investimento fora, depreciação por centro), os mesmos das telas anteriores.
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, ExternalLink, Info, Settings2 } from "lucide-react";
import {
  fetchCustoHectareMolde, fetchCustoSafraMolde, fetchCustoVacaLoteMolde, fetchCustosLeite, fetchSafrasMolde,
} from "@/lib/apiRelatoriosLeite";
import { ESTADO_INICIAL, REGIME_API, REGIME_NOME, brl, delta, deslocar, litros, mesCurto, num, type Periodo } from "@/lib/relatorioContexto";
import {
  VISOES_CUSTO, barrasPorLote, foraDoCusto, fraseCustos, linhasCustoLitro, pendenciasEstimativas, visaoCusto,
  type CamposCot, type RespostaCustoHectare, type RespostaCustoSafra, type RespostaCustoVacaLote, type RespostaCustosLeite,
  type SafraOpcao, type VisaoCusto,
} from "@/lib/relatorioLeite";
import { serieLitro } from "@/lib/relatorioLitro";
import { filtroConsultasDe } from "@/lib/relatorioDre";
import type { RelatorioParaExportar } from "@/lib/export";
import {
  Conferencia, FaixaKpis, NotasMetodo, PainelGrafico, RelatorioShell, TabelaComparacao, VazioQueEnsina, type EstadoTela, type KpiDef, type LinhaTabela,
} from "./RelatorioShell";
import { GraficoPrecoCusto, LegendaPrecoCusto } from "./graficos";
import { BarrasHorizontais, LegendaBarras } from "./barras";
import { CSS_LEITE_REGISTROS } from "./estilosLeite";
import { useContextoRelatorio, useDetalheNaUrl, type ContextoRelatorio, type TravasContexto } from "./useContextoRelatorio";
import { PORQUE_CENTRO_REGRAS_ANTIGAS, useRegrasV2Estado, type PropsRelatorio } from "./comum";

const NOME = "Custos do leite";
const PERGUNTA = "Quanto custa meu litro?";
const PARAMETROS_HREF = "/parametros?sub=financeiro&pf=parametros";
const seloEst = (t = "estimativa", titulo = "Conta feita com parâmetro ou com a separação da própria DRE") => <span className="rl-selo" title={titulo}>{t}</span>;
const contextoExport = (ctx: ContextoRelatorio, cmp?: Periodo | null) => ({
  periodo: ctx.periodo.label, comparacao: cmp?.label ?? null, regime: REGIME_NOME[ctx.efetivo.reg],
  centro: ctx.efetivo.cc === "todos" ? "todos os centros" : ctx.efetivo.cc,
});

function SeletorVisao({ visao, onMudar, extra }: { visao: VisaoCusto; onMudar: (v: VisaoCusto) => void; extra?: ReactNode }) {
  return (
    <div className="rl-noprint" style={{ display: "flex", flexWrap: "wrap", gap: ".5rem", alignItems: "flex-end" }}>
      <style>{CSS_LEITE_REGISTROS}</style>
      <div className="rl-seg" role="group" aria-label="Como ver o custo">
        {VISOES_CUSTO.map((x) => (
          <button key={x.v} type="button" aria-pressed={visao === x.v} onClick={() => onMudar(x.v)}>{x.rotulo}</button>
        ))}
      </div>
      {extra}
    </div>
  );
}

/** Busca o período atual e o de comparação; `chave` evita mostrar o número de outro contexto. */
function useBusca<T>(chave: string | null, buscar: (ini: string, fim: string) => Promise<T>, cmp: Periodo | null, periodo: Periodo, tentativa: number) {
  const [res, setRes] = useState<{ chave: string; a: T; b: T | null } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    if (!chave) return;
    let vivo = true;
    Promise.all([buscar(periodo.ini, periodo.fim), cmp ? buscar(cmp.ini, cmp.fim) : Promise.resolve(null)])
      .then(([a, b]) => { if (vivo) { setRes({ chave, a, b }); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [chave, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps
  const atual = res && res.chave === chave ? res : null;
  return { a: atual?.a ?? null, b: atual?.b ?? null, erro, pronto: !!atual };
}

export default function CustosLeiteView(props: PropsRelatorio) {
  const [v, abrirVisao] = useDetalheNaUrl("visao");
  const visao = visaoCusto(v);
  const mudar = (x: VisaoCusto) => abrirVisao(x === "litro" ? "" : x);
  if (visao === "lote") return <CustoPorLote {...props} visao={visao} onVisao={mudar} />;
  if (visao === "ha") return <CustoPorHectare {...props} visao={visao} onVisao={mudar} />;
  if (visao === "safra") return <CustoPorSafra {...props} visao={visao} onVisao={mudar} />;
  return <CustoPorLitro {...props} visao={visao} onVisao={mudar} />;
}

type PropsVisao = PropsRelatorio & { visao: VisaoCusto; onVisao: (v: VisaoCusto) => void };

// ═══ Por litro ═══════════════════════════════════════════════════════════════
function CustoPorLitro(props: PropsVisao) {
  const { hoje, centros, ccPadrao } = props;
  const regras = useRegrasV2Estado();
  const travas: TravasContexto = useMemo(() => (regras.ativa === false
    ? { cc: "todos", cmpOrcado: false, porque: PORQUE_CENTRO_REGRAS_ANTIGAS } : { cmpOrcado: false }), [regras.ativa]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const { periodo, comparacao, efetivo } = ctx;
  const cmp = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const rotuloCmp = cmp ? comparacao!.rotulo : null;
  const centroApi = efetivo.cc === "todos" ? null : efetivo.cc;
  const [tentativa, setTentativa] = useState(0);
  const chave = regras.ativa === null ? null : ["litro", periodo.cod, cmp?.cod, efetivo.reg, centroApi].join("|");
  const { a: r, b: rb, erro } = useBusca<RespostaCustosLeite>(chave, (ini, fim) =>
    fetchCustosLeite({ data_inicio: ini, data_fim: fim, regime: REGIME_API[efetivo.reg], centro_custo: centroApi, serie_meses: ini === periodo.ini ? 12 : 0 }),
  cmp, periodo, tentativa);

  const a = r?.litro.atual ?? null, b = rb?.litro.atual ?? null;
  const e = r?.estimativas ?? null, eb = rb?.estimativas ?? null;
  const ok = !!a && a.litros > 0 && a.coe_l != null;
  const estado: EstadoTela = !chave || (!r && !erro) ? "carregando" : erro && !r ? "erro" : !ok ? "vazio" : "ok";
  const linhas = useMemo(() => linhasCustoLitro(r, rb), [r, rb]);
  const pontos = useMemo(() => serieLitro(r?.litro ?? null), [r]);
  const media = r?.media_serie;
  const dre = (det: string) => () => props.onIrRelatorio("rel_dre", det);

  const kpis: KpiDef[] = a && e && ok ? [
    { chave: "coe_l", rotulo: "Custo de custeio (COE)", valor: a.coe_l, cmp: b?.coe_l ?? null, formato: "brlL", unidade: "/L", bom: "desce",
      selo: seloEst("estimativa", "Estoque de ração e silagem desloca custo entre meses: compare com a média"),
      sub: <>O que saiu do bolso{media?.coe_l != null && media.meses > 1 ? <> · média de {media.meses} meses <b>{brl(media.coe_l)}</b></> : null}</>,
      onAbrir: () => props.onIrRelatorio("rel_litro") },
    { chave: "cot_l", rotulo: "Custo operacional total (COT)", valor: e.cot_l, cmp: eb?.cot_l ?? null, formato: "brlL", unidade: "/L", bom: "desce",
      selo: e.familia_informada ? seloEst("parâmetro", "Inclui a remuneração da família informada em Parâmetros") : undefined,
      sub: `Custeio + desgaste ${brl(a.depreciacao_l ?? 0)}${e.familia_informada ? ` + família ${brl(e.familia_l ?? 0)}` : " (família não informada)"}`,
      onAbrir: dre("DEPRECIACAO_AMORT_EXAUSTAO") },
    { chave: "ct_l", rotulo: "Custo total com retorno do capital (CT)", valor: e.ct_l, cmp: eb?.ct_l ?? null, formato: "brlL", unidade: "/L", bom: "desce",
      selo: e.capital_informado ? seloEst("parâmetro", "Taxa ao ano × capital empatado, dos Parâmetros") : undefined,
      sub: e.capital_informado ? `+ ${num(e.taxa_capital_aa, 1)}% a.a. sobre ${brl(e.capital_total, 0)}` : "Informe o capital empatado em Parâmetros para ver o custo total",
      onAbrir: () => { window.location.href = PARAMETROS_HREF; } },
    { chave: "preco", rotulo: "Preço líquido do leite", valor: a.preco_liquido_l, cmp: b?.preco_liquido_l ?? null, formato: "brlL", unidade: "/L", bom: "sobe",
      sub: `A margem é a distância até o custo de custeio: ${brl(a.margem_l ?? 0)}`, negativoEmVermelho: true, onAbrir: dre("RECEITA_VENDAS") },
  ] : [];

  const linhasTabela: LinhaTabela[] = linhas.map((l) => ({
    chave: l.chave, nome: <>{l.tot ? "= " : ["comida", "gente", "outros"].includes(l.chave) ? "" : "+ "}{l.nome}{l.parametro ? <> {seloEst("parâmetro")}</> : null}</>, textoNome: l.nome, sub: l.sub,
    a: l.a, b: l.b, bom: "desce", formato: "brlL", tot: l.tot, ind: l.ind, zero: l.a == null,
    onAbrir: l.dre ? dre(l.dre) : l.parametro ? () => { window.location.href = PARAMETROS_HREF; } : undefined,
    rotuloAbrir: l.dre ? `${l.nome}: abrir a linha na DRE da fazenda` : `${l.nome}: ajustar em Parâmetros financeiros`,
  }));

  const descricaoGrafico = (() => {
    const vs = pontos.filter((p) => p.preco != null && p.custo != null);
    if (!vs.length) return "Sem meses com leite e custo para desenhar o gráfico.";
    const u = vs[vs.length - 1];
    return `Custo de custeio e preço líquido por litro, ${mesCurto(pontos[0].comp)} a ${mesCurto(pontos[pontos.length - 1].comp)}. Em ${mesCurto(u.comp)}: custo ${brl(u.custo!)}, preço ${brl(u.preco!)}.`;
  })();

  const exportar = (): RelatorioParaExportar | null => {
    if (!a || !e || !ok) return null;
    const comCmp = !!rotuloCmp;
    const val = (nome: string, x: number | null, y: number | null, total = false) => {
      const d = comCmp ? delta(x, y) : null;
      return { valores: [nome, x, ...(comCmp ? [y, d ? d.abs : null, d && d.pct != null ? d.pct * 100 : null] : [])], total };
    };
    return {
      titulo: `${NOME} — por litro`, pergunta: PERGUNTA, contexto: contextoExport(ctx, cmp),
      colunas: [{ header: "Linha (R$ por litro)", tipo: "texto" }, { header: "Atual", tipo: "brlL" },
        ...(comCmp ? [{ header: rotuloCmp!, tipo: "brlL" as const }, { header: "Δ", tipo: "brlL" as const }, { header: "Δ%", tipo: "pct" as const }] : [])],
      linhas: [
        ...linhas.map((l) => val(l.nome, l.a, l.b, !!l.tot)),
        val("Preço líquido do leite", a.preco_liquido_l, b?.preco_liquido_l ?? null, true),
      ],
      nomeArquivoBase: "custos_do_leite_por_litro",
      notas: [
        `Litros: ${num(a.litros, 0)} L entregues no período${r?.regras_v2 ? " (kg convertido para litro)" : ""}.`,
        "COE = custo variável + despesas variáveis + pessoal + despesas operacionais da DRE do mesmo período, regime e centro (o mesmo do Resultado por litro).",
        `COT = COE + depreciação${e.familia_informada ? ` + remuneração da família (${brl(e.familia_mes, 0)}/mês, parâmetro)` : " (remuneração da família não informada)"}.`,
        e.capital_informado ? `CT = COT + ${num(e.taxa_capital_aa, 1)}% ao ano sobre ${brl(e.capital_total, 0)} de capital empatado (parâmetros).` : "CT: capital empatado não informado em Parâmetros.",
        ...(r?.litro.avisos ?? []),
      ],
    };
  };

  const pend = pendenciasEstimativas(e);
  const vazioUi = (
    <VazioQueEnsina titulo={`Sem custo por litro em ${periodo.label}`}
      texto="Para dividir por litro, o relatório precisa dos litros entregues e do custo no mesmo período. Veja o que falta:"
      itens={[
        { texto: "Litros entregues no período", pronto: (a?.litros ?? 0) > 0, acao: <a href="/lancamentos?sub=entrega_leite">Lançar a venda mensal do leite</a> },
        { texto: "Custos lançados no período", pronto: (a?.coe ?? 0) > 0, acao: <a href="/financeiro?sub=a_pagar">Lançar uma conta</a> },
      ]}
      acoes={<button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>} />
  );

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Leite" nome={NOME} pergunta={PERGUNTA} onIrGrupo={props.onIrGrupo}
      estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => setTentativa((t) => t + 1)} vazio={vazioUi}
      frase={r && ok ? fraseCustos({ periodo, r, b: rb, rotuloCmp, brl, delta: (x, y, bom) => delta(x, y, bom) }) : []}
      kpis={kpis} exportar={exportar}
      avisos={<>
        <SeletorVisao visao={props.visao} onMudar={props.onVisao} />
        {r && r.litro.avisos.length > 0 && (
          <div className="rl-aviso info" role="status"><Info size={18} aria-hidden /><div>{r.litro.avisos.map((x) => <p key={x} style={{ margin: 0 }}>{x}</p>)}</div></div>
        )}
      </>}>
      {a && e && ok && (<>
        <PainelGrafico titulo="Custo × preço do leite, 12 meses · a distância entre as linhas é a margem" legenda={<LegendaPrecoCusto />}
          tabela={{ cabecalho: ["Mês", "Litros", "Preço líquido/L", "Custeio/L", "Sobra/L"], linhas: (r?.litro.serie ?? []).map((m) => [
            mesCurto(m.competencia), m.litros > 0 ? litros(m.litros) : "—", m.preco_liquido_l != null ? brl(m.preco_liquido_l) : "—",
            m.coe_l != null ? brl(m.coe_l) : "—", m.margem_l != null ? brl(m.margem_l) : "—",
          ]) }}>
          <GraficoPrecoCusto pontos={pontos} descricao={descricaoGrafico} />
        </PainelGrafico>
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-cl-tab">
            <h3 className="rl-tit" id="rl-cl-tab">Do custeio ao custo total, por litro</h3>
            <TabelaComparacao titulo={`Custos do leite por litro — ${periodo.label}`} linhas={linhasTabela} rotuloCmp={rotuloCmp} formato="brlL" />
          </section>
          <section className="rl-painel" aria-labelledby="rl-cl-par">
            <h3 className="rl-tit" id="rl-cl-par">Parâmetros das estimativas</h3>
            <dl className="rl-dl-par">
              <dt>Remuneração da família</dt><dd>{e.familia_informada ? `${brl(e.familia_mes, 0)}/mês` : "não informada"}</dd>
              <dt>Retorno do capital</dt><dd>{num(e.taxa_capital_aa, 1)}% ao ano</dd>
              <dt>Rebanho</dt><dd>{e.capital.rebanho ? brl(e.capital.rebanho, 0) : "não informado"}</dd>
              <dt>Máquinas e benfeitorias</dt><dd>{e.capital.maquinas ? brl(e.capital.maquinas, 0) : "não informado"}</dd>
              <dt>Terra</dt><dd>{e.capital.terra ? brl(e.capital.terra, 0) : "não incluída"}</dd>
              <dt>Litros no período</dt><dd>{litros(a.litros)}</dd>
            </dl>
            <p className="rl-hint">A remuneração da família é um valor de referência, não a retirada real (que é Particular, fora da DRE). O retorno do capital não é saída de dinheiro: serve para comparar com outras fazendas.</p>
            <ul className="rl-chk" style={{ margin: ".5rem 0" }}>
              {pend.map((p) => (
                <li key={p.chave}><span className={p.pronto ? "y" : "n"}>{p.pronto ? "✓" : "○"}</span><span>{p.texto}<span className="rl-sr"> — {p.pronto ? "pronto" : "falta"}</span></span></li>
              ))}
            </ul>
            <a className="rl-btn" href={PARAMETROS_HREF}><Settings2 size={14} aria-hidden /> Ajustar parâmetros</a>
          </section>
        </div>
      </>)}
      <NotasMetodo titulo="Como cada custo é calculado"
        entra={[
          ["Custo de custeio (COE)", "Comida + gente + outros custeios da DRE do mesmo período, regime e centro ÷ litros. É o mesmo número do Resultado por litro. Por mês ele oscila com compras para estoque: por isso a média de 12 meses fica ao lado e o número leva o selo “estimativa”."],
          ["Custo operacional total (COT)", "Custeio + desgaste dos bens (a depreciação da DRE, por centro com as regras novas) + remuneração da família (parâmetro). Sem a família informada, é o “custo total” do Resultado por litro."],
          ["Custo total (CT)", "COT + o que o capital empatado renderia (taxa ao ano × rebanho, máquinas e benfeitorias; terra opcional). Metodologia CNA/Embrapa."],
          ["Litros", `Venda mensal do leite${r?.regras_v2 ? " (lançada em kg é convertida: 1 L = 1,029 kg)" : " (com as regras antigas, kg conta como litro)"}.`],
        ]}
        naoEntra={["Compra de bem, de matriz ou de reprodutor: é investimento e entra aos poucos pelo desgaste (com as regras novas).", "Principal de financiamento, aporte e retirada particular.", "Venda de animais: não abate o custo do litro (está na DRE)."]} />
      {a && ok && (
        <Conferencia fecha={Math.abs(Math.round(((a.comida_l ?? 0) + (a.pessoal_l ?? 0) + (a.outros_l ?? 0)) * 10000) / 10000 - (a.coe_l ?? 0)) < 0.0002}
          texto={`Custeio ${brl(a.coe)} ÷ ${litros(a.litros)} = ${brl(a.coe_l ?? 0)}/L — o mesmo número do Resultado por litro.${r?.alimentacao_tela_anterior ? ` Com as regras antigas, a comida por litro mostrada é a da tela anterior (${brl(r.alimentacao_tela_anterior.custo_total)} ÷ ${litros(r.alimentacao_tela_anterior.litros)}).` : ""}`} />
      )}
    </RelatorioShell>
  );
}

// ═══ Por vaca e lote ═════════════════════════════════════════════════════════
const PORQUE_COMPETENCIA = "Custo por vaca, por hectare e por safra é pelo mês do gasto (competência), como na tela anterior.";

function NotaRateio({ c }: { c: CamposCot | null }) {
  const rt = c?.depreciacao_rateio;
  if (!rt) return null;
  return (
    <p className="rl-hint">
      Desgaste no centro {rt.centro_custo}: {brl(rt.depreciacao_bens_do_centro)} dos bens do centro
      {rt.depreciacao_bens_sem_centro ? ` + ${brl(rt.depreciacao_rateada)} de ${brl(rt.depreciacao_bens_sem_centro)} dos bens sem centro (${num(rt.participacao * 100, 1)}% das despesas operacionais do período)` : ""}.
      {rt.aviso ? ` ${rt.aviso}` : ""}
    </p>
  );
}

function ForaDoCusto({ c, regrasV2 }: { c: CamposCot | null; regrasV2: boolean }) {
  const fora = foraDoCusto(c);
  return (
    <section className="rl-painel" aria-labelledby="rl-cl-fora">
      <h3 className="rl-tit" id="rl-cl-fora">Fora do custo, por natureza</h3>
      {!regrasV2 ? (
        <p className="rl-hint" style={{ margin: 0 }}>Com as regras antigas, compra de bem e principal de financiamento ainda entram nas despesas (como na tela anterior). Ligue as regras novas em Parâmetros financeiros para tirá-los do custo.</p>
      ) : fora.length ? (<>
        <p className="rl-hint" style={{ marginTop: 0 }}>Não são custo do período: investimento entra aos poucos pelo desgaste; o resto mexe no caixa, não no custo.</p>
        {fora.map((f) => (
          <div key={f.natureza} className="rl-linha-valor"><span>{f.rotulo}</span><b>{brl(f.valor)}</b></div>
        ))}
      </>) : <p className="rl-hint" style={{ margin: 0 }}>Nada ficou fora neste período: todas as despesas são de custeio.</p>}
    </section>
  );
}

function useCtxCompetencia(props: PropsRelatorio, porque = PORQUE_COMPETENCIA) {
  const travas: TravasContexto = useMemo(() => ({ reg: "comp", cmpOrcado: false, porque }), [porque]);
  const padrao = useMemo(() => ESTADO_INICIAL(props.hoje, props.ccPadrao), [props.hoje, props.ccPadrao]);
  return useContextoRelatorio(padrao, travas);
}

function CustoPorLote(props: PropsVisao) {
  const regras = useRegrasV2Estado();
  const ctx = useCtxCompetencia(props);
  const { periodo, comparacao, efetivo } = ctx;
  const cmp = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const centroApi = efetivo.cc === "todos" ? undefined : efetivo.cc;
  const [tentativa, setTentativa] = useState(0);
  const chave = ["lote", periodo.cod, cmp?.cod, centroApi].join("|");
  const { a, b, erro } = useBusca<RespostaCustoVacaLote>(chave, (ini, fim) => fetchCustoVacaLoteMolde({ data_inicio: ini, data_fim: fim, centro_custo: centroApi }), cmp, periodo, tentativa);
  const ok = !!a && a.tem_vacas_no_periodo;
  const estado: EstadoTela = (!a && !erro) || regras.ativa === null ? "carregando" : erro && !a ? "erro" : !ok ? "vazio" : "ok";
  const barras = useMemo(() => barrasPorLote(a), [a]);
  const centroResp = a?.centro_custo ?? null;
  const consultas = (origem: string) => props.onConsultas(filtroConsultasDe({ periodo, regime: "comp", cc: centroResp ?? "todos", origem }));

  const kpis: KpiDef[] = a && ok ? [
    { chave: "vaca", rotulo: "Custo por vaca em lactação", valor: a.custo_por_vaca, cmp: b?.custo_por_vaca ?? null, formato: "brl", bom: "desce",
      sub: `${brl(a.despesas_total, 0)} de despesas ÷ ${a.num_vacas} vaca${a.num_vacas === 1 ? "" : "s"} com controle leiteiro no período`,
      onAbrir: () => consultas(`${NOME} › Por vaca`) },
    ...(a.cot_por_vaca !== undefined ? [{ chave: "cot", rotulo: "Custo por vaca com desgaste (COT)", valor: a.cot_por_vaca ?? null, cmp: b?.cot_por_vaca ?? null, formato: "brl" as const, bom: "desce" as const,
      sub: `Despesas + desgaste dos bens ${brl(a.depreciacao_periodo ?? 0, 0)}`, onAbrir: () => props.onIrRelatorio("rel_dre", "DEPRECIACAO_AMORT_EXAUSTAO") }] : []),
    { chave: "desp", rotulo: "Despesas do período", valor: a.despesas_total, cmp: b?.despesas_total ?? null, formato: "brl0", bom: "desce",
      sub: a.regras_v2 ? "Só custeio: investimento e financiamento ficam fora" : "Todas as despesas (regras antigas)", onAbrir: () => consultas(`${NOME} › Despesas`) },
    { chave: "vacas", rotulo: "Vacas em lactação", valor: a.num_vacas, cmp: b?.num_vacas ?? null, formato: "num", bom: "neutro",
      sub: <>em {a.por_lote.length} lote{a.por_lote.length === 1 ? "" : "s"} · ver a sobra da comida por vaca</>, onAbrir: () => props.onIrRelatorio("rmca") },
  ] : [];

  const exportar = (): RelatorioParaExportar | null => a && ok ? {
    titulo: `${NOME} — por vaca e lote`, pergunta: PERGUNTA, contexto: { ...contextoExport(ctx, null), centro: centroResp ?? "todos os centros" },
    colunas: [{ header: "Lote", tipo: "texto" }, { header: "Vacas", tipo: "num" }, { header: "Custo alocado", tipo: "brl" }, { header: "Custo por vaca", tipo: "brl" }],
    linhas: [...a.por_lote.map((l) => ({ valores: [l.lote, l.num_vacas, l.custo_alocado, l.custo_por_vaca] })),
      { valores: ["Total", a.num_vacas, a.despesas_total, a.custo_por_vaca], total: true }],
    nomeArquivoBase: "custos_do_leite_por_vaca_lote",
    notas: [
      "Despesas do período (competência) ÷ vacas com ao menos um Controle leiteiro no período; o lote recebe a fatia pelo número de vacas.",
      a.regras_v2 ? "Regras novas: só natureza operacional (investimento, financiamento e aporte fora); COT soma a depreciação do centro." : "Regras antigas: todas as despesas, como na tela anterior.",
      ...(a.cot_por_vaca != null ? [`COT por vaca: ${brl(a.cot_por_vaca)}.`] : []),
    ],
  } : null;

  return (
    <RelatorioShell ctx={ctx} hoje={props.hoje} centros={props.centros} grupo="Leite" nome={NOME} pergunta={PERGUNTA} onIrGrupo={props.onIrGrupo}
      estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => setTentativa((t) => t + 1)} exportar={exportar}
      vazio={<VazioQueEnsina titulo={`Sem vacas em lactação em ${periodo.label}`}
        texto="O custo por vaca divide as despesas do período pelas vacas com Controle leiteiro lançado no período."
        itens={[{ texto: "Controle leiteiro lançado no período", pronto: false, acao: <a href="/lancamentos?sub=controle">Lançar o controle leiteiro</a> }]}
        acoes={<button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>} />}
      frase={a && ok ? [{ t: `Em ${periodo.label} cada vaca em lactação custou ` }, { t: brl(a.custo_por_vaca ?? 0), b: true },
        { t: ` (${brl(a.despesas_total, 0)} de despesas ÷ ${a.num_vacas} vacas)` },
        ...(a.cot_por_vaca != null ? [{ t: "; com o desgaste dos bens, " }, { t: brl(a.cot_por_vaca), b: true }] : []),
        { t: ". O custo é repartido entre os lotes pelo número de vacas — não há lançamento ligado a lote." }] : []}
      kpis={kpis}
      avisos={<>
        <SeletorVisao visao={props.visao} onMudar={props.onVisao} />
        {a && !a.regras_v2 && efetivo.cc === "todos" && centroResp && (
          <div className="rl-aviso" role="status"><AlertTriangle size={18} aria-hidden /><div>
            <b>Com as regras antigas, “Todos os centros” no custo por vaca usa o centro {centroResp}.</b>
            <p>É o mesmo número da tela anterior. Com as regras novas ligadas, “Todos” passa a somar todos os centros.</p>
          </div></div>
        )}
      </>}>
      {a && ok && (<>
        <PainelGrafico titulo="Custo alocado por lote" legenda={<LegendaBarras cheio="Custo do período repartido pelas vacas do lote" />}
          tabela={{ cabecalho: ["Lote", "Vacas", "Custo alocado", "Custo por vaca"], linhas: a.por_lote.map((l) => [l.lote, String(l.num_vacas), brl(l.custo_alocado), brl(l.custo_por_vaca)]) }}>
          <BarrasHorizontais itens={barras.map((x) => ({ ...x, rotuloAbrir: `${x.nome}: ver as despesas do período em Consultas` }))} fmt={(v) => brl(v, 0)}
            descricao={`Custo alocado por lote em ${periodo.label}: ${barras.map((x) => `${x.nome} ${brl(x.valor, 0)}`).join(", ")}.`}
            onAbrir={(lote) => consultas(`${NOME} › Lote ${lote}`)} />
        </PainelGrafico>
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-cl-lote">
            <h3 className="rl-tit" id="rl-cl-lote">Por lote</h3>
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Custo por lote — {periodo.label}</caption>
                <thead><tr><th scope="col">Lote</th><th scope="col" className="r">Vacas</th><th scope="col" className="r">Custo alocado</th><th scope="col" className="r">Custo por vaca</th></tr></thead>
                <tbody>{a.por_lote.map((l) => (
                  <tr key={l.lote}><td>{l.lote}</td><td className="r">{l.num_vacas}</td><td className="r">{brl(l.custo_alocado)}</td><td className="r">{brl(l.custo_por_vaca)}</td></tr>
                ))}</tbody>
                <tfoot><tr><td>Total</td><td className="r">{a.num_vacas}</td><td className="r">{brl(a.despesas_total)}</td><td className="r">{brl(a.custo_por_vaca ?? 0)}</td></tr></tfoot>
              </table>
            </div>
            <p className="rl-hint">Rateio pelo número de vacas de cada lote (lote atual do animal). Para a comida de cada lote, veja a <button type="button" className="lk" onClick={() => props.onIrRelatorio("rmca")}>Sobra da comida por vaca</button>.</p>
            <NotaRateio c={a} />
          </section>
          <ForaDoCusto c={a} regrasV2={!!a.regras_v2} />
        </div>
      </>)}
      <NotasMetodo titulo="Como o custo por vaca é calculado"
        entra={[
          ["Por vaca", "Despesas do período (pelo mês do gasto) ÷ vacas com ao menos um Controle leiteiro lançado no período."],
          ["Por lote", "Cada lote recebe a fatia do custo pelo número de vacas — não há vínculo entre lançamento financeiro e lote."],
          ["COT por vaca", "Com as regras novas: + a depreciação do período, a do centro e o rateio dos bens sem centro."],
        ]}
        naoEntra={[a?.regras_v2 ? "Compra de bem e de matriz (investimento), principal de financiamento e aporte." : "Com as regras antigas, nada fica de fora por natureza."]} />
      {a && ok && (
        <Conferencia fecha={Math.abs(a.por_lote.reduce((s, l) => s + l.custo_alocado, 0) - a.despesas_total) < 0.05}
          texto={`Os lotes somam ${brl(a.por_lote.reduce((s, l) => s + l.custo_alocado, 0))} = despesas do período ${brl(a.despesas_total)}.`} />
      )}
    </RelatorioShell>
  );
}

// ═══ Por hectare ═════════════════════════════════════════════════════════════
function CustoPorHectare(props: PropsVisao) {
  const regras = useRegrasV2Estado();
  const ctx = useCtxCompetencia(props);
  const { periodo, comparacao, efetivo } = ctx;
  const cmp = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const rotuloCmp = cmp ? comparacao!.rotulo : null;
  const centroApi = efetivo.cc === "todos" ? undefined : efetivo.cc;
  const [tentativa, setTentativa] = useState(0);
  const chave = ["ha", periodo.cod, cmp?.cod, centroApi].join("|");
  const { a, b, erro } = useBusca<RespostaCustoHectare>(chave, (ini, fim) => fetchCustoHectareMolde({ data_inicio: ini, data_fim: fim, centro_custo: centroApi }), cmp, periodo, tentativa);
  const vazio = !!a && !a.area_configurada && Math.abs(a.despesas_total) < 0.005;
  const estado: EstadoTela = (!a && !erro) || regras.ativa === null ? "carregando" : erro && !a ? "erro" : vazio ? "vazio" : "ok";
  const consultas = (origem: string) => props.onConsultas(filtroConsultasDe({ periodo, regime: "comp", cc: efetivo.cc, origem }));

  const kpis: KpiDef[] = a ? [
    { chave: "ha", rotulo: "Custo por hectare", valor: a.custo_por_hectare, cmp: b?.custo_por_hectare ?? null, formato: "brl", unidade: "/ha", bom: "desce",
      sub: a.area_hectares ? `${brl(a.despesas_total, 0)} ÷ ${num(a.area_hectares, 1)} ha` : "Informe a área da fazenda em Parâmetros gerais", onAbrir: () => consultas(`${NOME} › Por hectare`) },
    ...(a.cot_por_hectare !== undefined ? [{ chave: "cot", rotulo: "Custo por hectare com desgaste (COT)", valor: a.cot_por_hectare ?? null, cmp: b?.cot_por_hectare ?? null,
      formato: "brl" as const, unidade: "/ha", bom: "desce" as const, sub: `Despesas + desgaste ${brl(a.depreciacao_periodo ?? 0, 0)}`, onAbrir: () => props.onIrRelatorio("rel_dre", "DEPRECIACAO_AMORT_EXAUSTAO") }] : []),
    { chave: "desp", rotulo: "Despesas do período", valor: a.despesas_total, cmp: b?.despesas_total ?? null, formato: "brl0", bom: "desce",
      sub: a.regras_v2 ? "Só custeio: investimento fora" : "Todas as despesas (regras antigas)", onAbrir: () => consultas(`${NOME} › Despesas`) },
    ...(a.depreciacao_periodo !== undefined ? [{ chave: "dep", rotulo: "Desgaste dos bens", valor: a.depreciacao_periodo ?? null, cmp: b?.depreciacao_periodo ?? null,
      formato: "brl0" as const, bom: "neutro" as const, sub: "Depreciação do período (não é saída de caixa)", onAbrir: () => props.onIrRelatorio("rel_dre", "DEPRECIACAO_AMORT_EXAUSTAO") }] : []),
  ] : [];

  const linhas: LinhaTabela[] = a ? [
    { chave: "desp", nome: "Despesas do período", textoNome: "Despesas do período", a: a.despesas_total, b: b?.despesas_total ?? null, bom: "desce",
      onAbrir: () => consultas(`${NOME} › Despesas`), rotuloAbrir: "Despesas do período: ver em Consultas" },
    ...(a.depreciacao_periodo !== undefined ? [{ chave: "dep", nome: "+ Desgaste dos bens", textoNome: "Desgaste dos bens", a: a.depreciacao_periodo ?? null, b: b?.depreciacao_periodo ?? null, bom: "desce" as const, ind: true,
      onAbrir: () => props.onIrRelatorio("rel_dre", "DEPRECIACAO_AMORT_EXAUSTAO") }, { chave: "cot", nome: "= Custo com desgaste (COT)", textoNome: "COT", a: a.cot ?? null, b: b?.cot ?? null, bom: "desce" as const, tot: true }] : []),
    { chave: "cha", nome: "Custo por hectare", textoNome: "Custo por hectare", a: a.custo_por_hectare, b: b?.custo_por_hectare ?? null, bom: "desce", tot: true },
    ...(a.cot_por_hectare !== undefined ? [{ chave: "cotha", nome: "COT por hectare", textoNome: "COT por hectare", a: a.cot_por_hectare ?? null, b: b?.cot_por_hectare ?? null, bom: "desce" as const, tot: true }] : []),
  ] : [];

  const exportar = (): RelatorioParaExportar | null => a ? {
    titulo: `${NOME} — por hectare`, pergunta: PERGUNTA, contexto: contextoExport(ctx, cmp),
    colunas: [{ header: "Linha", tipo: "texto" }, { header: "Atual", tipo: "brl" }, ...(rotuloCmp ? [{ header: rotuloCmp, tipo: "brl" as const }] : [])],
    linhas: linhas.map((l) => ({ valores: [l.textoNome, l.a, ...(rotuloCmp ? [l.b ?? null] : [])], total: l.tot })),
    nomeArquivoBase: "custos_do_leite_por_hectare",
    notas: [`Área: ${a.area_hectares ? `${num(a.area_hectares, 1)} ha` : "não informada"} (Parâmetros gerais › Estrutura da fazenda).`,
      ...foraDoCusto(a).map((f) => `Fora do custo — ${f.rotulo}: ${brl(f.valor)}.`)],
  } : null;

  return (
    <RelatorioShell ctx={ctx} hoje={props.hoje} centros={props.centros} grupo="Leite" nome={NOME} pergunta={PERGUNTA} onIrGrupo={props.onIrGrupo}
      estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => setTentativa((t) => t + 1)} exportar={exportar}
      vazio={<VazioQueEnsina titulo={`Sem custo por hectare em ${periodo.label}`} texto="O custo por hectare divide as despesas do período pela área da fazenda."
        itens={[{ texto: "Área da fazenda informada", pronto: false, acao: <a href="/parametros?sub=gerais">Informar em Parâmetros gerais › Estrutura da fazenda</a> },
          { texto: "Despesas no período", pronto: false, acao: <a href="/financeiro?sub=a_pagar">Lançar uma conta</a> }]}
        acoes={<button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>} />}
      frase={a ? (a.custo_por_hectare != null
        ? [{ t: `Em ${periodo.label} as despesas foram ` }, { t: brl(a.despesas_total, 0), b: true }, { t: ` em ${num(a.area_hectares ?? 0, 1)} ha: ` },
          { t: `${brl(a.custo_por_hectare)} por hectare`, b: true }, ...(a.cot_por_hectare != null ? [{ t: "; com o desgaste dos bens, " }, { t: `${brl(a.cot_por_hectare)}`, b: true }] : []), { t: "." }]
        : [{ t: `Em ${periodo.label} as despesas foram ` }, { t: brl(a.despesas_total, 0), b: true }, { t: ". Falta a área da fazenda para dividir por hectare." }]) : []}
      kpis={kpis}
      avisos={<>
        <SeletorVisao visao={props.visao} onMudar={props.onVisao} />
        {a && !a.area_configurada && (
          <div className="rl-aviso" role="status"><AlertTriangle size={18} aria-hidden /><div>
            <b>Falta a área da fazenda.</b><p>Sem ela o custo por hectare fica indefinido. <a href="/parametros?sub=gerais">Informar em Parâmetros gerais › Estrutura da fazenda</a>.</p>
          </div></div>
        )}
      </>}>
      {a && (
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-cl-ha">
            <h3 className="rl-tit" id="rl-cl-ha">Custo por hectare</h3>
            <TabelaComparacao titulo={`Custo por hectare — ${periodo.label}`} linhas={linhas} rotuloCmp={rotuloCmp} />
            <NotaRateio c={a} />
          </section>
          <ForaDoCusto c={a} regrasV2={!!a.regras_v2} />
        </div>
      )}
      <NotasMetodo titulo="Como o custo por hectare é calculado"
        entra={[
          ["Despesas", `Pelo mês do gasto${efetivo.cc !== "todos" ? `, no centro ${efetivo.cc}` : ", em todos os centros"}${a?.regras_v2 ? "; só natureza operacional (o mesmo numerador da DRE)" : ""}.`],
          ["Área", "A área total da fazenda, em Parâmetros gerais › Estrutura da fazenda."],
          ["COT", "Despesas + a depreciação do período (com centro: a dos bens do centro + o rateio dos bens sem centro)."],
        ]} />
    </RelatorioShell>
  );
}

// ═══ Por safra ═══════════════════════════════════════════════════════════════
function CustoPorSafra(props: PropsVisao) {
  const regras = useRegrasV2Estado();
  const ctx = useCtxCompetencia(props, "Por safra valem o período e o centro de custo da safra cadastrada (pelo mês do gasto); período, comparação e centro da barra não mudam esta visão.");
  const [safraUrl, abrirSafra] = useDetalheNaUrl("safra");
  const [safras, setSafras] = useState<SafraOpcao[] | null>(null);
  const [erroSafras, setErroSafras] = useState<string | null>(null);
  const [dados, setDados] = useState<{ id: number; r: RespostaCustoSafra } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    let vivo = true;
    fetchSafrasMolde().then((l) => { if (vivo) setSafras(l); }).catch((e) => { if (vivo) setErroSafras((e as Error).message); });
    return () => { vivo = false; };
  }, [tentativa]);
  const escolhida = safras?.find((s) => String(s.id) === safraUrl) ?? safras?.find((s) => s.ativo) ?? safras?.[0] ?? null;
  useEffect(() => {
    if (!escolhida) return;
    let vivo = true;
    fetchCustoSafraMolde(escolhida.id).then((r) => { if (vivo) { setDados({ id: escolhida.id, r }); setErro(null); } }).catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [escolhida?.id, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps
  const a = dados && escolhida && dados.id === escolhida.id ? dados.r : null;
  const semSafra = !!safras && safras.length === 0;
  const estado: EstadoTela = erroSafras ? "erro" : semSafra ? "vazio" : (!a && !erro) ? "carregando" : erro && !a ? "erro" : "ok";
  const per = a ? { ini: a.safra.data_inicio, fim: a.safra.data_fim } : null;
  const consultas = (conta: { codigo: string; nome: string } | null) => a && per && props.onConsultas({
    de: per.ini, ate: per.fim, periodoPor: "competencia", centro: a.safra.centro_custo, origem: `${NOME} › ${a.safra.nome}`,
    ...(conta ? { conta: conta.codigo, contaNome: conta.nome } : {}),
  });
  const dmy = (s: string) => s.split("-").reverse().join("/");

  const kpis: KpiDef[] = a ? [
    { chave: "ha", rotulo: "Custo por hectare", valor: a.custo_por_hectare, formato: "brl", unidade: "/ha", bom: "desce", sub: `${brl(a.despesas_total, 0)} ÷ ${num(a.hectares ?? 0, 1)} ha`, onAbrir: () => consultas(null) },
    { chave: "t", rotulo: "Custo por tonelada", valor: a.custo_por_tonelada, formato: "brl", unidade: "/t", bom: "desce", sub: `${num(a.toneladas_produzidas ?? 0, 1)} t produzidas` },
    { chave: "desp", rotulo: "Despesas da safra", valor: a.despesas_total, formato: "brl0", bom: "desce", sub: `${dmy(a.safra.data_inicio)} a ${dmy(a.safra.data_fim)} · ${a.safra.centro_custo}`, onAbrir: () => consultas(null) },
    ...(a.cot !== undefined ? [{ chave: "cot", rotulo: "Custo com desgaste (COT)", valor: a.cot ?? null, formato: "brl0" as const, bom: "desce" as const, sub: `+ desgaste ${brl(a.depreciacao_periodo ?? 0, 0)}` }] : []),
  ] : [];

  const exportar = (): RelatorioParaExportar | null => a ? {
    titulo: `${NOME} — ${a.safra.nome}`, pergunta: PERGUNTA,
    contexto: { periodo: `${dmy(a.safra.data_inicio)} a ${dmy(a.safra.data_fim)}`, comparacao: null, regime: REGIME_NOME.comp, centro: a.safra.centro_custo },
    colunas: [{ header: "Categoria", tipo: "texto" }, { header: "Valor", tipo: "brl" }],
    linhas: [...a.por_categoria.map((c) => ({ valores: [`${c.codigo} — ${c.descricao || "Sem descrição"}`, c.valor] })), { valores: ["Total", a.despesas_total], total: true }],
    nomeArquivoBase: "custos_do_leite_por_safra",
    notas: [`Hectares: ${num(a.hectares ?? 0, 1)}; toneladas: ${num(a.toneladas_produzidas ?? 0, 1)}.`,
      `Custo por hectare: ${a.custo_por_hectare != null ? brl(a.custo_por_hectare) : "—"}; por tonelada: ${a.custo_por_tonelada != null ? brl(a.custo_por_tonelada) : "—"}.`,
      ...(a.cot != null ? [`COT (com desgaste dos bens): ${brl(a.cot)}.`] : []), ...foraDoCusto(a).map((f) => `Fora do custo — ${f.rotulo}: ${brl(f.valor)}.`)],
  } : null;

  const seletorSafra = safras && safras.length > 0 ? (
    <div className="rl-campo">
      <label htmlFor="rl-cl-safra">Safra</label>
      <select id="rl-cl-safra" className="rl-in" value={escolhida?.id ?? ""} onChange={(e) => abrirSafra(e.target.value)}>
        {safras.map((s) => <option key={s.id} value={s.id}>{s.nome}{!s.ativo ? " (inativa)" : ""}</option>)}
      </select>
    </div>
  ) : null;

  return (
    <RelatorioShell ctx={ctx} hoje={props.hoje} centros={props.centros} grupo="Leite" nome={NOME} pergunta={PERGUNTA} onIrGrupo={props.onIrGrupo}
      estado={estado} erro={erroSafras || erro || regras.erro} onTentarDeNovo={() => { setErro(null); setErroSafras(null); setTentativa((t) => t + 1); }} exportar={exportar}
      vazio={<VazioQueEnsina titulo="Nenhuma safra cadastrada" texto="O custo por safra usa a safra cadastrada: nome, centro de custo, período, hectares e toneladas produzidas."
        itens={[{ texto: "Safra cadastrada", pronto: false, acao: <a href="/configuracoes?aba=cadastro&sub=safra">Cadastrar em Configurações › Cadastro › Safra</a> }]} />}
      frase={a ? [{ t: `Na ${a.safra.nome} (${dmy(a.safra.data_inicio)} a ${dmy(a.safra.data_fim)}, centro ${a.safra.centro_custo}) as despesas foram ` },
        { t: brl(a.despesas_total, 0), b: true }, { t: ": " }, { t: a.custo_por_hectare != null ? `${brl(a.custo_por_hectare)} por hectare` : "sem hectares cadastrados", b: true },
        { t: a.custo_por_tonelada != null ? ` e ${brl(a.custo_por_tonelada)} por tonelada.` : "." }] : []}
      avisos={<SeletorVisao visao={props.visao} onMudar={props.onVisao} extra={seletorSafra} />}>
      {a && (<>
        <FaixaKpis kpis={kpis} rotuloCmp={null} />
        {a.por_categoria.length > 0 ? (
          <PainelGrafico titulo="Despesas da safra por categoria" legenda={<LegendaBarras cheio="Despesas da categoria na safra" />}
            tabela={{ cabecalho: ["Categoria", "Valor"], linhas: a.por_categoria.map((c) => [`${c.codigo} — ${c.descricao || "Sem descrição"}`, brl(c.valor)]) }}>
            <BarrasHorizontais itens={a.por_categoria.map((c) => ({ chave: c.codigo, nome: c.descricao || c.codigo, valor: c.valor, sub: c.codigo,
              rotuloAbrir: `${c.descricao || c.codigo}: ver os lançamentos em Consultas` }))} fmt={(v) => brl(v, 0)}
              descricao={`Despesas da ${a.safra.nome} por categoria: ${a.por_categoria.map((c) => `${c.descricao || c.codigo} ${brl(c.valor, 0)}`).join(", ")}.`}
              onAbrir={(cod) => { const c = a.por_categoria.find((x) => x.codigo === cod); consultas(c ? { codigo: c.codigo, nome: c.descricao || c.codigo } : null); }} />
          </PainelGrafico>
        ) : <p className="rl-hint">Nenhuma despesa lançada no centro {a.safra.centro_custo} no período da safra.</p>}
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-cl-sf">
            <h3 className="rl-tit" id="rl-cl-sf">Quebra por categoria</h3>
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Despesas da {a.safra.nome} por categoria</caption>
                <thead><tr><th scope="col">Categoria</th><th scope="col" className="r">Valor</th></tr></thead>
                <tbody>{a.por_categoria.map((c) => (
                  <tr key={c.codigo} className="clic" onClick={(ev) => { if (!(ev.target as HTMLElement).closest("button")) consultas({ codigo: c.codigo, nome: c.descricao || c.codigo }); }}>
                    <td><button type="button" className="rl-linkbtn" onClick={() => consultas({ codigo: c.codigo, nome: c.descricao || c.codigo })} aria-label={`${c.descricao || c.codigo}: ver os lançamentos em Consultas`}>
                      {c.codigo} — {c.descricao || "Sem descrição"}<ExternalLink size={13} aria-hidden /></button></td>
                    <td className="r">{brl(c.valor)}</td>
                  </tr>
                ))}</tbody>
                <tfoot><tr><td>Total</td><td className="r">{brl(a.despesas_total)}</td></tr></tfoot>
              </table>
            </div>
            <NotaRateio c={a} />
          </section>
          <ForaDoCusto c={a} regrasV2={!!a.regras_v2} />
        </div>
      </>)}
      <NotasMetodo titulo="Regras da safra"
        entra={[["Período e centro", "Os da safra cadastrada (Configurações › Cadastro › Safra)."], ["Por hectare e por tonelada", "Despesas da safra ÷ hectares e ÷ toneladas produzidas cadastrados."],
          ["Categoria", "O primeiro nível do código da conta de cada item (o mesmo agrupamento da DRE)."]]}
        naoEntra={[a?.regras_v2 ? "Investimento, financiamento e aporte (natureza fora do custeio)." : "Com as regras antigas, nada fica de fora por natureza."]} />
      {a && (
        <Conferencia fecha={Math.abs(a.por_categoria.reduce((s, c) => s + c.valor, 0) - a.despesas_total) < 0.05}
          texto={`As categorias somam ${brl(a.por_categoria.reduce((s, c) => s + c.valor, 0))} = despesas da safra ${brl(a.despesas_total)}.`} />
      )}
    </RelatorioShell>
  );
}
