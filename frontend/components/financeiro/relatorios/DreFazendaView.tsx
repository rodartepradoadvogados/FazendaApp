"use client";
// Relatórios › Resultado › DRE da fazenda — "Estou ganhando?"
// A cascata do SERVIDOR (GET /financeiro/dre) é a única fonte do número: esta
// tela só reorganiza (molde único, degraus, comparação, detalhe por conta).
// Com a flag financeiro_regras_v2 desligada, o centro de custo fica travado em
// "Todos" — a DRE das regras antigas é sempre da fazenda inteira, como antes.
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ExternalLink, Info } from "lucide-react";
import { fetchDreCascata, type DreResposta } from "@/lib/api";
import { fetchOrcamentoRelatorio } from "@/lib/apiPlano";
import { aplicarSemOrcamento, periodoDeMesesInteiros, type RespostaOrcamento } from "@/lib/relatorioOrcamento";
import {
  ESTADO_INICIAL, REGIME_API, REGIME_NOME, brl, delta, deslocar,
} from "@/lib/relatorioContexto";
import {
  composicaoSubtotal, conferirCascata, degrausCascata, filtroConsultasDe, fraseDre, linhasDre, valorLinha, type LinhaVis,
} from "@/lib/relatorioDre";
import type { LinhaRelatorio, RelatorioParaExportar } from "@/lib/export";
import {
  Conferencia, NotasMetodo, PainelGrafico, RelatorioShell, TabelaComparacao, VazioQueEnsina, type KpiDef, type LinhaTabela,
} from "./RelatorioShell";
import { CascataDegraus, LegendaCascata } from "./graficos";
import { useContextoRelatorio, useDetalheNaUrl, type TravasContexto } from "./useContextoRelatorio";
import { PORQUE_CENTRO_REGRAS_ANTIGAS, useRegrasV2Estado, type PropsRelatorio } from "./comum";

const KPI_LINHAS: { chave: string; rotulo: string; sub: string }[] = [
  { chave: "RESULTADO_LIQUIDO", rotulo: "Resultado", sub: "" },
  { chave: "RECEITA_LIQUIDA", rotulo: "Receita líquida", sub: "Receita de vendas − Funrural, Senar e descontos" },
  { chave: "EBITDA", rotulo: "Geração de caixa da atividade", sub: "Antes do desgaste dos bens e dos juros (EBITDA)" },
  { chave: "DEPRECIACAO_AMORT_EXAUSTAO", rotulo: "Desgaste e reserva para repor", sub: "Depreciação dos bens — não é lançamento nem saída de caixa" },
];

export default function DreFazendaView(props: PropsRelatorio & { onClassificar: () => void }) {
  const { hoje, centros, ccPadrao } = props;
  const regras = useRegrasV2Estado();
  // Fase C: "Comparar com: Orçado" liga no orçamento de Plano › Orçamento (só com as regras novas).
  const travas: TravasContexto = useMemo(() => (regras.ativa === false
    ? { cc: "todos", cmpOrcado: false, porque: `${PORQUE_CENTRO_REGRAS_ANTIGAS} O orçado como comparação também.` }
    : {}), [regras.ativa]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const { periodo, comparacao, efetivo } = ctx;
  const [det, abrirDet] = useDetalheNaUrl("det");
  const [leituraOrc, setLeituraOrc] = useState<{ k: string; r: RespostaOrcamento | null; erro: string | null } | null>(null);

  const [dados, setDados] = useState<DreResposta | null>(null);
  const [dadosCmp, setDadosCmp] = useState<DreResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);

  const cmpPeriodo = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const centroApi = efetivo.cc === "todos" ? null : efetivo.cc;
  useEffect(() => {
    if (regras.ativa === null) return;
    let vivo = true;
    const buscar = (ini: string, fim: string) => fetchDreCascata({ data_inicio: ini, data_fim: fim, regime: REGIME_API[efetivo.reg], centro_custo: centroApi });
    Promise.all([buscar(periodo.ini, periodo.fim), cmpPeriodo ? buscar(cmpPeriodo.ini, cmpPeriodo.fim) : Promise.resolve(null)])
      .then(([a, b]) => { if (vivo) { setDados(a); setDadosCmp(b); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [regras.ativa, periodo.ini, periodo.fim, cmpPeriodo?.ini, cmpPeriodo?.fim, efetivo.reg, centroApi, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps

  // Orçado: a cascata montada com os valores orçados (servidor); só pelo mês do gasto e em meses inteiros.
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
  const orcAtivo = orcPossivel && !!orc?.tem_orcamento && !!orc.cascata_orcada;
  const linhas = useMemo(() => (orcAtivo
    ? aplicarSemOrcamento(linhasDre(dados, { cascata: orc!.cascata_orcada } as unknown as DreResposta), orc!.cascata_orcada!)
    : linhasDre(dados, cmpPeriodo ? dadosCmp : null)), [dados, dadosCmp, cmpPeriodo, orcAtivo, orc]);
  const rotuloCmp = cmpPeriodo ? comparacao!.rotulo : orcAtivo ? "Orçado" : null;
  const naoClass = dados?.nao_classificado ?? { total: 0, contas: [] };
  const fora = dados?.fora_da_dre ?? { total: 0, contas: [] };
  const vazio = !!dados && linhas.every((l) => Math.abs(l.a) < 0.005) && Math.abs(naoClass.total) < 0.005 && Math.abs(fora.total) < 0.005;
  const conf = conferirCascata(linhas);
  const receita = valorLinha(linhas, "RECEITA_LIQUIDA")?.a ?? 0;

  const consultas = useCallback((conta?: { codigo: string | null; nome: string } | null, origem = "DRE da fazenda") =>
    props.onConsultas(filtroConsultasDe({ periodo, regime: efetivo.reg, cc: efetivo.cc, conta, origem })), [props, periodo, efetivo.reg, efetivo.cc]);

  const linhaDet = det ? valorLinha(linhas, det) : null;
  const estado = regras.ativa === null || (!dados && !erro) || (orcPossivel && !orc && !orcErro) ? "carregando" : erro && !dados ? "erro" : vazio ? "vazio" : "ok";

  // ── KPIs: 1 principal + 3 de apoio, todos abrem o detalhe ──
  const kpis: KpiDef[] = KPI_LINHAS.map((k, i) => {
    const l = valorLinha(linhas, k.chave);
    const ehDep = k.chave === "DEPRECIACAO_AMORT_EXAUSTAO";
    const valor = l ? (ehDep ? Math.abs(l.a) : l.a) : null;
    const cmp = l && l.b != null ? (ehDep ? Math.abs(l.b) : l.b) : null;
    const sub = i === 0 && valor != null
      ? `${receita > 0 ? `${(Math.round((1000 * valor) / receita) / 10).toLocaleString("pt-BR")}% da receita líquida` : "sem receita no período"}`
      : k.sub;
    return {
      chave: k.chave, rotulo: k.rotulo, valor, cmp, formato: "brl0", bom: ehDep ? "neutro" : "sobe", sub,
      negativoEmVermelho: !ehDep, onAbrir: () => abrirDet(k.chave),
    };
  });

  // ── Tabela principal ──
  const linhaTabela = (l: LinhaVis): LinhaTabela => ({
    chave: l.chave, nome: l.subtotal ? `= ${l.nome}` : l.nome, textoNome: l.nome,
    sub: l.tecnico ? l.tecnico : undefined, a: l.a, b: l.b, bom: "sobe", tot: l.subtotal, ind: !l.subtotal,
    zero: !l.subtotal && Math.abs(l.a) < 0.005 && (l.b == null || Math.abs(l.b) < 0.005),
    extra: l.pctReceita != null ? `${(Math.round(l.pctReceita * 1000) / 10).toLocaleString("pt-BR", { minimumFractionDigits: 1 })}%` : "—",
    onAbrir: l.subtotal || l.contas.length || Math.abs(l.a) >= 0.005 ? () => abrirDet(l.chave) : undefined,
    rotuloAbrir: `${l.nome}: abrir o detalhe`,
  });

  // ── Detalhe (nível 2): contas da linha, ou a composição do subtotal — sempre fecha com o total ──
  const detalhe = linhaDet ? (linhaDet.subtotal ? composicaoSubtotal(linhas, linhaDet.chave).map((l, i, arr) => ({
    ...linhaTabela(l),
    // O ponto de partida (subtotal anterior) não é "item"; as linhas somadas são.
    ind: !(i === 0 && l.subtotal && arr.length > 1), tot: false,
    nome: i === 0 && l.subtotal ? `${l.nome} (ponto de partida)` : l.nome,
  })) : linhaDet.contas.map((c): LinhaTabela => ({
    chave: c.chave, nome: c.nome, textoNome: c.nome, sub: c.codigo && !c.codigo.startsWith("(") ? c.codigo : undefined,
    a: c.a, b: c.b, bom: "sobe",
    onAbrir: () => consultas(c, `DRE da fazenda › ${linhaDet.nome}`), rotuloAbrir: `${c.nome}: ver os lançamentos em Consultas`,
  }))) : [];

  const exportar = (): RelatorioParaExportar | null => {
    if (!dados) return null;
    const comCmp = !!rotuloCmp;
    const colunas: RelatorioParaExportar["colunas"] = [
      { header: linhaDet ? "Conta" : "Linha da DRE", tipo: "texto" }, { header: "Atual", tipo: "brl" },
      ...(comCmp ? [{ header: rotuloCmp!, tipo: "brl" as const }, { header: "Δ", tipo: "brl" as const }, { header: "Δ%", tipo: "pct" as const }] : []),
      ...(!linhaDet ? [{ header: "% da receita", tipo: "pct" as const }] : []),
    ];
    const valores = (nome: string, a: number, b: number | null, pctRec?: number | null): (string | number | null)[] => {
      const d = comCmp ? delta(a, b) : null;
      return [nome, a, ...(comCmp ? [b, d ? d.abs : null, d && d.pct != null ? d.pct * 100 : null] : []), ...(!linhaDet ? [pctRec != null ? pctRec * 100 : null] : [])];
    };
    let ls: LinhaRelatorio[];
    if (linhaDet) {
      ls = detalhe.map((l) => ({ valores: valores(l.textoNome, l.a ?? 0, l.b ?? null) }));
      ls.push({ valores: valores(`Total — ${linhaDet.nome}`, linhaDet.a, linhaDet.b), total: true });
    } else {
      ls = linhas.flatMap((l) => [
        { valores: valores(l.nome, l.a, l.b, l.pctReceita), total: l.subtotal },
        ...l.contas.map((c) => ({ valores: valores(`${c.codigo && !c.codigo.startsWith("(") ? `${c.codigo} ` : ""}${c.nome}`, c.a, c.b), nivel: 1 })),
      ]);
    }
    return {
      titulo: linhaDet ? `DRE da fazenda — ${linhaDet.nome}` : "DRE da fazenda", pergunta: "Estou ganhando?",
      contexto: { periodo: periodo.label, comparacao: cmpPeriodo?.label ?? (orcAtivo ? "o orçado" : null), regime: REGIME_NOME[efetivo.reg], centro: efetivo.cc === "todos" ? "todos os centros" : efetivo.cc },
      colunas, linhas: ls, nomeArquivoBase: "dre_da_fazenda",
      notas: [
        "Números da DRE do servidor (GET /financeiro/dre): a mesma cascata da Capa e do e-mail do Portal.",
        naoClass.total ? `Sem classificação (fora de todas as linhas até ser classificado): ${brl(naoClass.total)}.` : "",
        fora.total ? `Fora da DRE por regra (investimento, financiamento, aporte, transferência): ${brl(fora.total)}.` : "",
        `Conferência: ${conf.fecha ? "cada subtotal é a soma das linhas acima dele" : `diferença de ${brl(conf.diferenca)} entre subtotal e linhas`}.`,
      ].filter(Boolean),
    };
  };

  const avisos = dados && (<>
    {!dados.cascata && (
      <div className="rl-aviso" role="status"><AlertTriangle size={18} aria-hidden /><div><b>O servidor ainda está na versão anterior.</b><p>Atualize a página em alguns minutos.</p></div></div>
    )}
    {cmpOrc && <AvisoOrcado regrasNovas={regras.ativa === true} regimeCaixa={efetivo.reg === "caixa"} mesesInteiros={periodoDeMesesInteiros(periodo)}
      orc={orc} erro={orcErro} periodo={periodo.label} onComp={() => ctx.mudar({ reg: "comp" })} onPlano={() => props.onIrRelatorio("rel_orcamento")} />}
    {(dados.pendencias_contas_automaticas?.length ?? 0) > 0 && (
      <div className="rl-aviso" role="status"><AlertTriangle size={18} aria-hidden /><div>
        <b>Configure as contas automáticas</b>
        <p>Folha, contratos e diárias criados pelo sistema estão sem conta e ficaram em “não classificado”:{" "}
          {dados.pendencias_contas_automaticas!.map((p) => `${p.rotulo} (${brl(p.valor)})`).join(", ")}.{" "}
          <a href="/parametros?sub=financeiro&pf=automaticas">Escolher a conta de cada origem</a>.</p>
      </div></div>
    )}
  </>);

  const vazioUi = (
    <VazioQueEnsina
      titulo={`Nenhum lançamento em ${periodo.label}`}
      texto={<>A DRE junta tudo o que foi lançado no período {efetivo.reg === "caixa" ? "pelo dia do pagamento" : "pelo mês do gasto"}{efetivo.cc !== "todos" ? ` no centro ${efetivo.cc}` : ""}. Nada caiu aqui ainda — confira o que falta para ela aparecer:</>}
      itens={[
        { texto: "Lançamentos no período", pronto: false, acao: <a href="/financeiro?sub=a_pagar">Lançar uma conta</a> },
        { texto: "Contas gerenciais ligadas a uma linha da DRE", pronto: true },
        { texto: "Regras novas dos relatórios (centro de custo, natureza)", pronto: !!dados?.regras_v2, acao: <a href="/parametros?sub=financeiro">Ligar em Parâmetros financeiros</a> },
      ]}
      acoes={<>
        <button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>
        {efetivo.cc !== "todos" && !travas.cc && <button type="button" className="rl-btn" onClick={() => ctx.mudar({ cc: "todos" })}>Ver todos os centros</button>}
      </>}
    />
  );

  const frase = dados ? fraseDre({
    periodo, regime: efetivo.reg, linhas, rotuloCmp: cmpPeriodo ? rotuloCmp : null, brl: (v) => brl(v, 0), naoClassificadoContas: naoClass.contas.length,
    delta: (a, b) => delta(a, b, "sobe"),
  }) : [];
  const resOrc = orcAtivo ? valorLinha(linhas, "RESULTADO_LIQUIDO") : null;
  if (resOrc && resOrc.b != null) {
    const d = delta(resOrc.a, resOrc.b, "sobe");
    frase.push({ t: " O orçado previa " }, { t: brl(resOrc.b, 0), b: true }, { t: d && !d.igual ? ` — resultado ${d.melhor ? "melhor" : "pior"} que o plano.` : " — no plano." });
  }

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Resultado" nome="DRE da fazenda" pergunta="Estou ganhando?"
      onIrGrupo={props.onIrGrupo}
      niveis={linhaDet ? [{ rotulo: linhaDet.nome }] : []} onVoltarNivel={() => abrirDet("")}
      estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => { setErro(null); setTentativa((t) => t + 1); }} vazio={vazioUi}
      frase={linhaDet ? [] : frase} kpis={linhaDet ? undefined : kpis} avisos={avisos} exportar={exportar} rotuloCmp={orcAtivo ? "o orçado" : undefined}>
      {!linhaDet && (<>
        <PainelGrafico titulo="Do faturamento ao resultado, degrau a degrau"
          legenda={<LegendaCascata />}
          tabela={{ cabecalho: ["Linha", "Valor"], linhas: degrausCascata(linhas).map((d) => [d.nome, brl(d.v)]) }}>
          <CascataDegraus degraus={degrausCascata(linhas)} onAbrir={abrirDet}
            descricao={`Cascata da DRE de ${periodo.label}: receita líquida de ${brl(receita, 0)}, resultado de ${brl(valorLinha(linhas, "RESULTADO_LIQUIDO")?.a ?? 0, 0)}.`} />
        </PainelGrafico>
        <section className="rl-painel" aria-labelledby="rl-dre-tab">
          <h3 className="rl-tit" id="rl-dre-tab">DRE da fazenda, linha a linha</h3>
          <TabelaComparacao titulo={`DRE da fazenda — ${periodo.label}`} linhas={linhas.map(linhaTabela)} rotuloCmp={rotuloCmp} colunaExtra="% da receita" />
        </section>
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-dre-fora">
            <h3 className="rl-tit" id="rl-dre-fora">Fora da DRE, por regra</h3>
            <p style={{ margin: "0 0 .6rem", fontSize: ".8rem", color: "var(--text-muted)" }}>
              Não são receita nem despesa: mudam o caixa ou o patrimônio, não o resultado (compra de bem, principal de financiamento, aporte, transferência).
            </p>
            {(fora.grupos?.length ? fora.grupos.map((g) => ({ k: g.natureza, nome: g.rotulo, v: g.total, n: g.contas.length }))
              : fora.contas.map((c) => ({ k: c.codigo || c.nome || "", nome: c.nome || c.codigo || "", v: c.valor, n: 1 }))).map((g) => (
              <div key={g.k} style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", padding: ".45rem 0", borderBottom: "1px solid var(--border)", fontSize: ".86rem" }}>
                <span>{g.nome}<span style={{ display: "block", fontSize: ".72rem", color: "var(--text-muted)" }}>{g.n} conta{g.n === 1 ? "" : "s"}</span></span>
                <b style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{brl(g.v)}</b>
              </div>
            ))}
            {!fora.contas.length && <p style={{ margin: 0, fontSize: ".84rem", color: "var(--text-muted)" }}>Nada fora da DRE neste período.</p>}
          </section>
          <section className="rl-painel" aria-labelledby="rl-dre-sem">
            <h3 className="rl-tit" id="rl-dre-sem">Sem conta: precisa classificar</h3>
            {naoClass.contas.length ? (<>
              <p style={{ margin: "0 0 .6rem", fontSize: ".8rem", color: "var(--text-muted)" }}>
                Ficam fora de todas as linhas até ganharem uma linha da DRE — a DRE prefere mostrar o buraco a fechar com um número errado.
              </p>
              <p style={{ margin: "0 0 .6rem", fontSize: ".86rem" }}>
                <AlertTriangle size={15} aria-hidden style={{ verticalAlign: "-2px", color: "var(--st-logo-fg)" }} />{" "}
                <b>{naoClass.contas.length} conta{naoClass.contas.length === 1 ? "" : "s"}</b>
                {naoClass.total_receita !== undefined ? <> · {brl(naoClass.total_receita)} de receita e {brl(naoClass.total_despesa ?? 0)} de despesa (nunca somadas)</> : <> · {brl(Math.abs(naoClass.total))}</>}
              </p>
              <button type="button" className="rl-btn" onClick={props.onClassificar}>Classificar agora</button>
            </>) : <p style={{ margin: 0, fontSize: ".84rem", color: "var(--text-muted)" }}>Tudo classificado neste período.</p>}
          </section>
        </div>
      </>)}
      {linhaDet && (
        <section className="rl-painel" aria-labelledby="rl-dre-det">
          <h3 className="rl-tit" id="rl-dre-det">{linhaDet.subtotal ? `Como se chega em ${linhaDet.nome}` : `${linhaDet.nome} — por conta`}</h3>
          {linhaDet.subtotal || detalhe.length ? (
            <TabelaComparacao titulo={`${linhaDet.nome} — ${periodo.label}`} linhas={detalhe} rotuloCmp={rotuloCmp}
              colunaNome={linhaDet.subtotal ? "Linha" : "Conta gerencial"}
              rodape={{ chave: "total", nome: `Total — ${linhaDet.nome}`, textoNome: "Total", a: linhaDet.a, b: linhaDet.b, bom: "sobe" }} />
          ) : (
            <p style={{ margin: 0, fontSize: ".86rem", color: "var(--text-muted)" }}>
              {linhaDet.chave === "DEPRECIACAO_AMORT_EXAUSTAO"
                ? "A depreciação não é lançamento: sai do cadastro de Patrimônio, pelo método de cada bem."
                : "Nenhuma conta nesta linha no período."}
            </p>
          )}
          {linhaDet.chave === "DEPRECIACAO_AMORT_EXAUSTAO" && dados?.depreciacao_periodo?.rateio && (
            <p style={{ margin: ".6rem 0 0", fontSize: ".8rem", color: "var(--text-muted)" }}>
              Centro {dados.depreciacao_periodo.rateio.centro_custo}: {brl(dados.depreciacao_periodo.rateio.depreciacao_bens_do_centro)} dos bens do centro
              {dados.depreciacao_periodo.rateio.depreciacao_bens_sem_centro ? ` + ${brl(dados.depreciacao_periodo.rateio.depreciacao_rateada)} rateados dos bens sem centro` : ""}.
            </p>
          )}
          {!linhaDet.subtotal && linhaDet.chave !== "DEPRECIACAO_AMORT_EXAUSTAO" && (
            <p style={{ margin: ".7rem 0 0" }}>
              <button type="button" className="rl-btn" onClick={() => consultas(null, `DRE da fazenda › ${linhaDet.nome}`)}>
                <ExternalLink size={14} aria-hidden /> Ver os lançamentos do período em Consultas
              </button>
            </p>
          )}
        </section>
      )}
      <NotasMetodo titulo="Regras desta DRE (o que entra em cada linha)"
        entra={[
          ["De onde vem", "Da DRE do servidor — a mesma cascata da Capa, do e-mail do Portal e da DRE por conta. Esta tela não soma nada no navegador."],
          ["Regime", efetivo.reg === "caixa" ? "Pelo dia do pagamento: o que foi pago e recebido no período (juros e descontos da baixa vão para Resultado financeiro)." : "Pelo mês do gasto: o que aconteceu no período, pago ou não."],
          ["Centro de custo", regras.ativa ? "Com o filtro, só os lançamentos (e itens) do centro; a depreciação é a dos bens do centro mais o rateio dos bens sem centro." : "Regras antigas: sempre a fazenda inteira."],
          ["Desgaste dos bens", "A depreciação do período, calculada do cadastro de Patrimônio. Não é saída de caixa."],
        ]}
        naoEntra={[
          "Compra de bem (investimento), principal de financiamento, aporte e transferência entre contas — ficam em “Fora da DRE”.",
          "Contas sem linha da DRE — ficam em “Sem conta” até serem classificadas.",
          "Orçado (Comparar com: Orçado): linha sem conta orçada fica sem comparação; o desgaste dos bens é o do Patrimônio dos dois lados. O detalhe conta a conta fica em Plano › Orçamento.",
        ]}>
        <p style={{ margin: ".7rem 0 0" }}>
          Para classificar contas uma a uma, use a <button type="button" className="rl-linkbtn" style={{ color: "var(--text-accent)", fontWeight: 700 }} onClick={props.onClassificar}>DRE por conta (tela anterior)</button>.
        </p>
      </NotasMetodo>
      <Conferencia fecha={conf.fecha} texto={conf.fecha
        ? `Cada subtotal é a soma das linhas acima dele (${periodo.label}). Fora da DRE: ${brl(fora.total)}; sem classificação: ${brl(naoClass.total)}.`
        : `Diferença de ${brl(conf.diferenca)} entre um subtotal e as linhas — avise o suporte.`} />
    </RelatorioShell>
  );
}

/** "Comparar com: Orçado" — o que falta para comparar (ou o que está sendo comparado). */
function AvisoOrcado({ regrasNovas, regimeCaixa, mesesInteiros, orc, erro, periodo, onComp, onPlano }: {
  regrasNovas: boolean; regimeCaixa: boolean; mesesInteiros: boolean; orc: RespostaOrcamento | null; erro: string | null; periodo: string;
  onComp: () => void; onPlano: () => void;
}) {
  const plano = <button type="button" className="lk" onClick={onPlano}>Plano › Orçamento</button>;
  let titulo: string, texto: React.ReactNode, info = false;
  if (!regrasNovas) { titulo = "O orçado por linha da DRE usa as regras novas dos relatórios."; texto = <>Com as regras antigas, o orçado × realizado conta a conta está em {plano}.</>; }
  else if (regimeCaixa) { titulo = "O orçamento é pelo mês do gasto."; texto = <>Para comparar com o orçado, <button type="button" className="lk" onClick={onComp}>use o mês do gasto</button>.</>; }
  else if (!mesesInteiros) { titulo = "O orçamento é mensal."; texto = "Escolha um período de meses inteiros para comparar com o orçado."; }
  else if (erro) { titulo = "Não foi possível ler o orçado."; texto = <>{erro} Os números da DRE não mudaram.</>; }
  else if (orc && !orc.tem_orcamento) { titulo = `Não há orçamento para ${periodo}.`; texto = <>Crie em {plano} (copie o ano anterior ou comece na planilha).</>; }
  else if (orc) { info = true; titulo = `Comparando com o orçado de ${periodo}.`; texto = <>Linha sem conta orçada fica sem comparação (nada vermelho por falta de plano); o desgaste dos bens é o do Patrimônio dos dois lados. Conta a conta: {plano}.</>; }
  else return null;
  return (
    <div className={`rl-aviso${info ? " info" : ""}`} role="status">{info ? <Info size={18} aria-hidden /> : <AlertTriangle size={18} aria-hidden />}<div>
      <b>{titulo}</b><p>{texto}</p>
    </div></div>
  );
}
