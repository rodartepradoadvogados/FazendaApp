"use client";
// Relatórios › Resultado › Resultado por litro — "Quanto sobra de cada litro?"
// Preço líquido do leite, custo de custeio (COE/L), custo total (COT/L),
// sobra por litro (R$ e %), ponto de equilíbrio e 12 meses de preço × custo.
// Os números vêm de GET /financeiro/resultado-por-litro, que reparte por litro a
// MESMA DRE do servidor (mesmo regime e centro) — não há soma no navegador.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Info } from "lucide-react";
import { fetchResultadoPorLitro } from "@/lib/api";
import { fetchOrcamentoRelatorio } from "@/lib/apiPlano";
import { periodoDeMesesInteiros, type RespostaOrcamento } from "@/lib/relatorioOrcamento";
import { ESTADO_INICIAL, REGIME_API, REGIME_NOME, brl, delta, deslocar, litros, mesCurto, num } from "@/lib/relatorioContexto";
import {
  fraseLitro, linhasLitro, pendenciasLitro, serieLitro, temResultadoPorLitro, type RespostaLitro,
} from "@/lib/relatorioLitro";
import type { RelatorioParaExportar } from "@/lib/export";
import {
  Conferencia, NotasMetodo, PainelGrafico, RelatorioShell, TabelaComparacao, VazioQueEnsina, type KpiDef, type LinhaTabela,
} from "./RelatorioShell";
import { GraficoPrecoCusto, LegendaPrecoCusto } from "./graficos";
import { useContextoRelatorio, type TravasContexto } from "./useContextoRelatorio";
import { PORQUE_CENTRO_REGRAS_ANTIGAS, useRegrasV2Estado, type PropsRelatorio } from "./comum";

const selo = <span className="rl-selo" title="Conta feita com a separação variável × fixo da própria DRE">estimativa</span>;

export default function ResultadoLitroView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const regras = useRegrasV2Estado();
  // Fase C: "Comparar com: Orçado" = o orçamento de Plano › Orçamento repartido pelos litros entregues.
  const travas: TravasContexto = useMemo(() => (regras.ativa === false
    ? { cc: "todos", cmpOrcado: false, porque: `${PORQUE_CENTRO_REGRAS_ANTIGAS} O orçado como comparação também.` }
    : {}), [regras.ativa]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const { periodo, comparacao, efetivo } = ctx;

  const [dados, setDados] = useState<RespostaLitro | null>(null);
  const [dadosCmp, setDadosCmp] = useState<RespostaLitro | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const cmpPeriodo = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const centroApi = efetivo.cc === "todos" ? null : efetivo.cc;

  useEffect(() => {
    if (regras.ativa === null) return;
    let vivo = true;
    const base = { regime: REGIME_API[efetivo.reg], centro_custo: centroApi };
    Promise.all([
      fetchResultadoPorLitro({ ...base, data_inicio: periodo.ini, data_fim: periodo.fim, serie_meses: 12 }),
      cmpPeriodo ? fetchResultadoPorLitro({ ...base, data_inicio: cmpPeriodo.ini, data_fim: cmpPeriodo.fim }) : Promise.resolve(null),
    ])
      .then(([a, b]) => { if (vivo) { setDados(a); setDadosCmp(b); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [regras.ativa, periodo.ini, periodo.fim, cmpPeriodo?.ini, cmpPeriodo?.fim, efetivo.reg, centroApi, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps

  const [leituraOrc, setLeituraOrc] = useState<{ k: string; r: RespostaOrcamento | null; erro: string | null } | null>(null);
  const cmpOrc = comparacao?.tipo === "orcado";
  const orcPossivel = cmpOrc && regras.ativa === true && efetivo.reg === "comp" && periodoDeMesesInteiros(periodo);
  const chaveOrc = `${periodo.ini}|${periodo.fim}|${centroApi ?? ""}|${tentativa}`;
  useEffect(() => {
    if (!orcPossivel) return;
    let vivo = true;
    fetchOrcamentoRelatorio({ data_inicio: periodo.ini, data_fim: periodo.fim, centro_custo: centroApi })
      .then((r) => { if (vivo) setLeituraOrc({ k: chaveOrc, r, erro: null }); })
      .catch((e) => { if (vivo) setLeituraOrc({ k: chaveOrc, r: null, erro: (e as Error).message }); });
    return () => { vivo = false; };
  }, [orcPossivel, chaveOrc]); // eslint-disable-line react-hooks/exhaustive-deps
  const leituraValida = orcPossivel && leituraOrc?.k === chaveOrc ? leituraOrc : null;
  const orc = leituraValida?.r ?? null, orcErro = leituraValida?.erro ?? null;
  const orcAtivo = orcPossivel && !!orc?.tem_orcamento && !!orc.litro_orcado;

  const a = dados?.atual ?? null;
  const b = cmpPeriodo ? dadosCmp?.atual ?? null : orcAtivo ? orc!.litro_orcado! : null;
  const rotuloCmp = cmpPeriodo ? comparacao!.rotulo : orcAtivo ? "Orçado" : null;
  const ok = temResultadoPorLitro(a);
  const pend = pendenciasLitro(dados);
  const estado = regras.ativa === null || (!dados && !erro) || (orcPossivel && !orc && !orcErro) ? "carregando" : erro && !dados ? "erro" : !ok ? "vazio" : "ok";
  const linhas = useMemo(() => linhasLitro(a, b), [a, b]);
  const pontos = useMemo(() => serieLitro(dados), [dados]);
  const pe = a?.ponto_equilibrio ?? null;

  const kpis: KpiDef[] = a && ok ? [
    { chave: "margem_l", rotulo: "Sobra do custeio por litro", valor: a.margem_l, cmp: b?.margem_l ?? null, formato: "brlL", unidade: "/L", bom: "sobe",
      negativoEmVermelho: true,
      sub: <>De cada litro vendido a {brl(a.preco_liquido_l!)}, sobra isto depois de pagar comida, gente e os outros custeios{a.margem_pct != null ? ` — ${num(a.margem_pct, 1)}% da receita do leite` : ""}.</>,
      onAbrir: () => props.onIrRelatorio("rel_dre", "EBITDA") },
    { chave: "preco", rotulo: "Preço líquido do leite", valor: a.preco_liquido_l, cmp: b?.preco_liquido_l ?? null, formato: "brlL", unidade: "/L", bom: "sobe",
      sub: `Bruto ${brl(a.preco_bruto_l ?? 0)} − Funrural/Senar e descontos`, onAbrir: () => props.onIrRelatorio("rel_dre", "RECEITA_VENDAS") },
    { chave: "coe_l", rotulo: "Custo de custeio (COE)", valor: a.coe_l, cmp: b?.coe_l ?? null, formato: "brlL", unidade: "/L", bom: "desce",
      sub: `${brl(a.coe, 0)} de custeio ÷ ${litros(a.litros)}`, onAbrir: () => props.onIrRelatorio("rel_dre", "EBITDA") },
    { chave: "cot_l", rotulo: "Custo total (COT)", valor: a.cot_l, cmp: b?.cot_l ?? null, formato: "brlL", unidade: "/L", bom: "desce",
      sub: `Custeio + desgaste dos bens (${brl(a.depreciacao_l ?? 0)}/L)`, onAbrir: () => props.onIrRelatorio("rel_dre", "DEPRECIACAO_AMORT_EXAUSTAO") },
  ] : [];

  const linhasTabela: LinhaTabela[] = linhas.map((l) => ({
    chave: l.chave, nome: l.tot ? `= ${l.nome}` : `− ${l.nome}`.replace("− Preço bruto", "Preço bruto"), textoNome: l.nome, sub: l.sub,
    a: l.a, b: l.b, bom: l.bom, formato: "brlL", tot: l.tot, ind: l.ind,
    onAbrir: l.dre ? () => props.onIrRelatorio("rel_dre", l.dre) : undefined,
    rotuloAbrir: `${l.nome}: abrir a linha na DRE da fazenda`,
  }));

  const descricaoGrafico = (() => {
    const v = pontos.filter((p) => p.preco != null && p.custo != null);
    if (!v.length) return "Sem meses com leite e custo para desenhar o gráfico.";
    const u = v[v.length - 1];
    return `Preço líquido e custo de custeio por litro, ${mesCurto(pontos[0].comp)} a ${mesCurto(pontos[pontos.length - 1].comp)}. Em ${mesCurto(u.comp)}: preço ${brl(u.preco!)}, custo ${brl(u.custo!)}.`;
  })();

  const exportar = (): RelatorioParaExportar | null => {
    if (!a || !ok) return null;
    const comCmp = !!rotuloCmp;
    const val = (nome: string, x: number | null, y: number | null, total = false, tipo?: "litros" | "brl") => {
      const d = comCmp ? delta(x, y) : null;
      return {
        valores: [nome, x, ...(comCmp ? [y, d ? d.abs : null, d && d.pct != null ? d.pct * 100 : null] : [])], total,
        ...(tipo ? { tipos: [undefined, tipo, tipo, tipo, undefined] } : {}),
      };
    };
    return {
      titulo: "Resultado por litro", pergunta: "Quanto sobra de cada litro?",
      contexto: { periodo: periodo.label, comparacao: cmpPeriodo?.label ?? (orcAtivo ? "o orçado" : null), regime: REGIME_NOME[efetivo.reg], centro: efetivo.cc === "todos" ? "todos os centros" : efetivo.cc },
      colunas: [
        { header: "Linha (R$ por litro)", tipo: "texto" }, { header: "Atual", tipo: "brlL" },
        ...(comCmp ? [{ header: rotuloCmp!, tipo: "brlL" as const }, { header: "Δ", tipo: "brlL" as const }, { header: "Δ%", tipo: "pct" as const }] : []),
      ],
      linhas: [
        ...linhas.map((l) => val(l.nome, l.a, l.b, !!l.tot)),
        val("Litros entregues", a.litros, b?.litros ?? null, false, "litros"),
        val("Receita líquida do leite", a.receita_leite_liquida, b?.receita_leite_liquida ?? null, false, "brl"),
        val("Custo de custeio do período", a.coe, b?.coe ?? null, false, "brl"),
      ],
      nomeArquivoBase: "resultado_por_litro",
      notas: [
        `Litros: ${num(a.litros, 0)} L entregues no período (Venda mensal do leite${dados?.regras_v2 ? ", kg convertido para litro" : ""}).`,
        "Custeio (COE) = custo variável + despesas variáveis + pessoal + despesas operacionais da DRE do mesmo período; COT = COE + depreciação.",
        pe ? `Ponto de equilíbrio (estimativa): ${num(pe.litros_mes ?? pe.litros_periodo, 0)} L por mês.` : "",
        ...(dados?.avisos ?? []),
      ].filter(Boolean),
    };
  };

  const vazioUi = (
    <VazioQueEnsina
      titulo={`Sem resultado por litro em ${periodo.label}`}
      texto="Para dividir por litro, o relatório precisa da receita do leite, do custo e dos litros entregues no mesmo período. Veja o que falta:"
      itens={[
        ...pend.map((p) => ({ texto: p.texto, pronto: p.pronto, acao: <a href={p.href}>{p.acao}</a> })),
        { texto: "Venda do leite lançada no período", pronto: (a?.receita_leite_liquida ?? 0) > 0, acao: <a href="/financeiro?sub=a_receber">Lançar o recebimento do laticínio</a> },
      ]}
      acoes={<button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>}
    />
  );

  const frase = a && ok ? fraseLitro({ periodo, regime: efetivo.reg, a, b: cmpPeriodo ? b : null, rotuloCmp: cmpPeriodo ? rotuloCmp : null, brl, delta: (x, y, bom) => delta(x, y, bom) }) : [];
  if (orcAtivo && b?.margem_l != null && a && ok) {
    const d = delta(a.margem_l, b.margem_l, "sobe");
    frase.push({ t: " O orçado previa " }, { t: `${brl(b.margem_l)} por litro`, b: true }, { t: d && !d.igual ? ` de sobra — ${d.melhor ? "melhor" : "pior"} que o plano.` : " de sobra — no plano." });
  }
  const avisoOrc = !cmpOrc ? null : (() => {
    const plano = <button type="button" className="lk" onClick={() => props.onIrRelatorio("rel_orcamento")}>Plano › Orçamento</button>;
    if (regras.ativa !== true) return { info: false, t: "O orçado por litro usa as regras novas dos relatórios.", p: <>O orçado × realizado conta a conta está em {plano}.</> };
    if (efetivo.reg === "caixa") return { info: false, t: "O orçamento é pelo mês do gasto.", p: <>Para comparar com o orçado, <button type="button" className="lk" onClick={() => ctx.mudar({ reg: "comp" })}>use o mês do gasto</button>.</> };
    if (!periodoDeMesesInteiros(periodo)) return { info: false, t: "O orçamento é mensal.", p: "Escolha um período de meses inteiros para comparar com o orçado." };
    if (orcErro) return { info: false, t: "Não foi possível ler o orçado.", p: <>{orcErro} Os números do litro não mudaram.</> };
    if (orc && !orc.tem_orcamento) return { info: false, t: `Não há orçamento para ${periodo.label}.`, p: <>Crie em {plano}.</> };
    if (orcAtivo) return { info: true, t: `Comparando com o orçado de ${periodo.label}, pelos mesmos ${litros(a?.litros ?? 0)} entregues.`, p: <>O orçamento ainda não tem litros previstos: o orçado de cada conta é dividido pelos litros que saíram. Conta a conta: {plano}.</> };
    return null;
  })();
  const soma = a ? Math.round(((a.comida_l ?? 0) + (a.pessoal_l ?? 0) + (a.outros_l ?? 0)) * 10000) / 10000 : 0;

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Resultado" nome="Resultado por litro" pergunta="Quanto sobra de cada litro?"
      onIrGrupo={props.onIrGrupo} estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => { setErro(null); setTentativa((t) => t + 1); }} vazio={vazioUi}
      frase={frase} kpis={kpis} exportar={exportar} rotuloCmp={orcAtivo ? "o orçado" : undefined}
      avisos={<>
        {avisoOrc && (
          <div className={`rl-aviso${avisoOrc.info ? " info" : ""}`} role="status">{avisoOrc.info ? <Info size={18} aria-hidden /> : <AlertTriangle size={18} aria-hidden />}<div><b>{avisoOrc.t}</b><p>{avisoOrc.p}</p></div></div>
        )}
        {dados && dados.avisos.length > 0 && (
          <div className="rl-aviso info" role="status"><AlertTriangle size={18} aria-hidden /><div>{dados.avisos.map((x) => <p key={x} style={{ margin: 0 }}>{x}</p>)}</div></div>
        )}
      </>}>
      {a && ok && (<>
        <section className="rl-painel" aria-labelledby="rl-litro-barra">
          <h3 className="rl-tit" id="rl-litro-barra">Para onde vai cada litro · {periodo.curto}</h3>
          <BarraDoLitro a={a} />
        </section>
        <PainelGrafico titulo="O ano, mês a mês · preço × custo por litro" legenda={<LegendaPrecoCusto />}
          tabela={{ cabecalho: ["Mês", "Preço líquido", "Custo de custeio", "Sobra"], linhas: pontos.map((p) => [
            mesCurto(p.comp), p.preco != null ? brl(p.preco) : "—", p.custo != null ? brl(p.custo) : "—",
            p.preco != null && p.custo != null ? brl(p.preco - p.custo) : "—",
          ]) }}>
          <GraficoPrecoCusto pontos={pontos} descricao={descricaoGrafico} />
        </PainelGrafico>
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-litro-tab">
            <h3 className="rl-tit" id="rl-litro-tab">Resultado por litro, linha a linha</h3>
            <TabelaComparacao titulo={`Resultado por litro — ${periodo.label}`} linhas={linhasTabela} rotuloCmp={rotuloCmp} formato="brlL" />
          </section>
          <section className="rl-painel" aria-labelledby="rl-litro-pe">
            <h3 className="rl-tit" id="rl-litro-pe" style={{ display: "flex", justifyContent: "space-between", gap: ".5rem" }}>Litros para empatar {selo}</h3>
            {pe ? (<>
              <p style={{ margin: "0 0 .7rem", fontSize: ".95rem", lineHeight: 1.55 }}>
                Para pagar os custos fixos (gente, despesas operacionais e desgaste dos bens), a fazenda precisa entregar{" "}
                <strong>{litros(pe.litros_mes ?? pe.litros_periodo)}{a.meses > 1.01 ? " por mês" : ""}</strong>. Entregou{" "}
                <strong>{litros(a.litros_mes ?? a.litros)}</strong>
                {pe.folga_pct != null && <>: <strong>{num(Math.abs(pe.folga_pct), 0)}% {pe.folga_pct >= 0 ? "acima" : "abaixo"}</strong> do ponto de empate</>}.
              </p>
              <BarraEmpate litrosEntregues={a.litros} litrosEmpate={pe.litros_periodo} />
              <p style={{ margin: ".55rem 0 0", fontSize: ".76rem", color: "var(--text-muted)" }}>
                Conta: fixos ÷ (preço líquido − custo variável por litro) = {brl(a.custo_fixo, 0)} ÷ {brl(pe.contribuicao_por_litro)}.
              </p>
            </>) : (
              <p style={{ margin: 0, fontSize: ".86rem", color: "var(--text-muted)" }}>
                Sem ponto de empate: o custo variável por litro já passa do preço líquido — cada litro a mais aumenta a falta.
              </p>
            )}
          </section>
        </div>
      </>)}
      <NotasMetodo titulo="O que entra e o que não entra em cada número"
        entra={[
          ["Preço líquido", "Receita das contas marcadas como venda do leite − Funrural, Senar e descontos da nota, ÷ litros entregues."],
          ["Custo de custeio (COE)", "As linhas de custo da DRE do mesmo período, regime e centro: custo variável + despesas variáveis + pessoal + despesas operacionais."],
          ["Custo total (COT)", "COE + a depreciação do período (a mesma linha da DRE). Pró-labore e remuneração do capital ainda não entram."],
          ["Comida", `As contas marcadas como alimentação (as mesmas do RMCA)${dados?.configuracao.contas_alimentacao.length ? `: ${dados.configuracao.contas_alimentacao.join(", ")}` : ""}.`],
          ["Litros", `Venda mensal do leite${dados?.regras_v2 ? " (lançada em kg é convertida: 1 L = 1,029 kg)" : ""}; mês parcial entra proporcional aos dias.`],
        ]}
        naoEntra={[
          "Venda de animais e outras receitas: não abatem o custo do litro (estão na DRE).",
          "Compra de bem, principal de financiamento e aporte (fora da DRE).",
          "Contas sem classificação na DRE — classifique para elas entrarem no custeio.",
        ]}>
        <p style={{ margin: ".6rem 0 0" }}><b>Pendências de configuração</b></p>
        <ul className="rl-chk" style={{ marginTop: ".3rem" }}>
          {pend.map((p) => (
            <li key={p.chave}><span className={p.pronto ? "y" : "n"}>{p.pronto ? "✓" : "○"}</span>
              <span>{p.texto}{p.pronto ? "" : <> · <a href={p.href}>{p.acao}</a></>}<span className="rl-sr"> — {p.pronto ? "pronto" : "falta"}</span></span></li>
          ))}
        </ul>
      </NotasMetodo>
      {a && ok && (
        <Conferencia fecha={Math.abs(soma - (a.coe_l ?? 0)) < 0.0002 && a.resultado_liquido_dre != null}
          texto={`Custeio ${brl(a.coe)} ÷ ${litros(a.litros)} = ${brl(a.coe_l ?? 0)}/L = comida + gente + outros custeios. O resultado da DRE no mesmo contexto é ${brl(a.resultado_liquido_dre, 0)}.`} />
      )}
    </RelatorioShell>
  );
}

/** Um litro vendido, repartido: comida, gente, outros custeios e a sobra (ou a falta). */
function BarraDoLitro({ a }: { a: NonNullable<RespostaLitro["atual"]> }) {
  const preco = a.preco_liquido_l ?? 0, sobra = a.margem_l ?? 0;
  const total = Math.max(preco, a.coe_l ?? 0) || 1;
  const partes = [
    { k: "Comida", v: a.comida_l ?? 0, fundo: "var(--rl-n1)" },
    { k: "Gente", v: a.pessoal_l ?? 0, fundo: "repeating-linear-gradient(45deg,var(--rl-n3) 0 3px,var(--rl-n1) 3px 5px)" },
    { k: "Outros custeios", v: a.outros_l ?? 0, fundo: "radial-gradient(var(--rl-n1) 30%,var(--rl-n3) 32%) 0 0/5px 5px" },
    ...(sobra > 0 ? [{ k: "Sobra", v: sobra, fundo: "var(--rl-a)" }] : []),
  ].filter((p) => p.v > 0);
  const aria = `Um litro vendido a ${brl(preco)} líquido: ${partes.map((p) => `${p.k.toLowerCase()} ${brl(p.v)}`).join(", ")}${sobra < 0 ? `; falta ${brl(-sobra)}` : ""}.`;
  return (
    <figure style={{ margin: 0 }} role="img" aria-label={aria}>
      <div style={{ display: "flex", height: 44, width: "100%", gap: 2, overflow: "hidden" }} className="rl-barra">
        {partes.map((p) => (
          <div key={p.k} title={`${p.k}: ${brl(p.v)} por litro`}
            style={{ flex: `${p.v / total} 0 0`, background: p.fundo, minWidth: 2, display: "flex", alignItems: "center", paddingLeft: 6, color: p.k === "Sobra" ? "var(--surface)" : "transparent", fontWeight: 700, fontSize: ".8rem", whiteSpace: "nowrap", overflow: "hidden" }}>
            {p.k === "Sobra" && p.v / total >= 0.14 ? `Sobra ${brl(p.v)}` : ""}
          </div>
        ))}
        {sobra < 0 && <div title={`Falta ${brl(-sobra)} por litro`} style={{ flex: `${-sobra / total} 0 0`, background: "repeating-linear-gradient(-45deg,var(--st-venc-bg) 0 3px,var(--st-venc-fg) 3px 4.5px)", border: "1px solid var(--st-venc-fg)" }} />}
      </div>
      <figcaption className="rl-leg" style={{ marginTop: ".55rem" }}>
        {partes.map((p) => (
          <span key={p.k}><i style={{ background: p.fundo }} />{p.k} <b style={{ color: "var(--text)", fontVariantNumeric: "tabular-nums" }}>{brl(p.v)}</b></span>
        ))}
        {sobra < 0 && <span style={{ color: "var(--st-venc-fg)", fontWeight: 700 }}>Falta {brl(-sobra)} por litro</span>}
        <span>Preço líquido <b style={{ color: "var(--text)" }}>{brl(preco)}/L</b></span>
      </figcaption>
    </figure>
  );
}

/** Barra da produção que só paga os fixos (até o empate) × o que passou dele. Movimento: só transform. */
function BarraEmpate({ litrosEntregues, litrosEmpate }: { litrosEntregues: number; litrosEmpate: number }) {
  const max = Math.max(litrosEntregues, litrosEmpate) || 1;
  const fEntregue = litrosEntregues / max, fEmpate = litrosEmpate / max;
  return (
    <div aria-hidden style={{ position: "relative", height: 14, background: "var(--st-neutro-bg)", border: "1px solid var(--st-neutro-line)", borderRadius: 999, overflow: "hidden" }}>
      <div className="rl-barra" style={{ position: "absolute", inset: 0, transform: `scaleX(${fEntregue})`, transformOrigin: "left center", background: "var(--rl-a)" }} />
      <div style={{ position: "absolute", top: -2, bottom: -2, left: `calc(${fEmpate * 100}% - 1px)`, width: 2, background: "var(--text)" }} title="Ponto de empate" />
    </div>
  );
}
