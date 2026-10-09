"use client";
// Relatórios › Painel › Painel do dono — "Como está a fazenda?"
// A entrada dos Relatórios responde em uma olhada às 4 perguntas do dono, cada
// uma com o número do SERVIDOR e o link para o relatório que a explica:
//   Estou ganhando?      → resultado da DRE única (GET /financeiro/dre)
//   Quanto custa o litro? → custo de custeio por litro (GET /financeiro/resultado-por-litro)
//   Quando o caixa aperta? → saldo de hoje e marcos do Caixa real (GET /financeiro/caixa-real)
//   Gastei o que planejei? → despesas × orçado (GET /planejamento/orcamento/comparativo)
// Embaixo, o caixa dos próximos 60 dias e o que vence em 7 dias; no topo, o
// botão "Apresentar o mês" (o único momento narrado e lento — ApresentarMes).
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ChevronRight, Clock, Play } from "lucide-react";
import { fetchCaixaReal, fetchComparativoOrcado, fetchDreCascata, fetchResultadoPorLitro, type DreResposta } from "@/lib/api";
import { ESTADO_INICIAL, REGIME_API, REGIME_NOME, brl, deslocar, mesLongo } from "@/lib/relatorioContexto";
import { linhasDre, valorLinha } from "@/lib/relatorioDre";
import { temResultadoPorLitro, type RespostaLitro } from "@/lib/relatorioLitro";
import {
  decisoesDoMes, frasePainel, mesesDoOrcamento, respostaCaixa, respostaOrcado, somaDias, type CaixaLite, type ComparativoLite, type Fmt,
} from "@/lib/painelDono";
import type { RelatorioParaExportar } from "@/lib/export";
import { ChipVariacao, NotasMetodo, NumeroAnimado, RelatorioShell, VazioQueEnsina } from "./RelatorioShell";
import { useContextoRelatorio, type TravasContexto } from "./useContextoRelatorio";
import { PORQUE_CENTRO_REGRAS_ANTIGAS, useRegrasV2Estado, type PropsRelatorio } from "./comum";
import { GraficoSaldo, LegendaSaldo } from "./GraficoSaldo";
import { ApresentarMes } from "./ApresentarMes";
import { CSS_C4 } from "./estilosC4";

export const FMT: Fmt = {
  brl: (v) => brl(v), brl0: (v) => brl(v, 0),
  dia: (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`,
};
const DIAS_SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const diaSemana = (iso: string) => DIAS_SEMANA[new Date(`${iso}T12:00:00`).getDay()];

export default function PainelDonoView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const regras = useRegrasV2Estado();
  const travas: TravasContexto = useMemo(() => (regras.ativa === false
    ? { cc: "todos", cmpOrcado: false, porque: PORQUE_CENTRO_REGRAS_ANTIGAS }
    : { cmpOrcado: false }), [regras.ativa]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const { periodo, comparacao, efetivo } = ctx;
  const cmpPeriodo = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const rotuloCmp = cmpPeriodo ? comparacao!.rotulo : null;
  const centroApi = efetivo.cc === "todos" ? null : efetivo.cc;

  const [dre, setDre] = useState<{ a: DreResposta; b: DreResposta | null } | null>(null);
  const [litro, setLitro] = useState<{ a: RespostaLitro | null; b: RespostaLitro | null } | null>(null);
  const [caixa, setCaixa] = useState<{ c: CaixaLite | null; erro: string | null } | null>(null);
  const [orc, setOrc] = useState<{ c: ComparativoLite | null; erro: string | null } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const [apresentando, setApresentando] = useState(false);
  const botaoApresentar = useRef<HTMLButtonElement>(null);
  const orcMeses = mesesDoOrcamento(periodo.ini, periodo.fim);

  useEffect(() => {
    if (regras.ativa === null) return;
    let vivo = true;
    const base = { regime: REGIME_API[efetivo.reg], centro_custo: centroApi };
    Promise.all([
      fetchDreCascata({ ...base, data_inicio: periodo.ini, data_fim: periodo.fim }),
      cmpPeriodo ? fetchDreCascata({ ...base, data_inicio: cmpPeriodo.ini, data_fim: cmpPeriodo.fim }) : Promise.resolve(null),
    ]).then(([a, b]) => { if (vivo) { setDre({ a, b }); setErro(null); } }).catch((e) => { if (vivo) setErro((e as Error).message); });
    Promise.all([
      fetchResultadoPorLitro({ ...base, data_inicio: periodo.ini, data_fim: periodo.fim, serie_meses: 12 }).catch(() => null),
      cmpPeriodo ? fetchResultadoPorLitro({ ...base, data_inicio: cmpPeriodo.ini, data_fim: cmpPeriodo.fim }).catch(() => null) : Promise.resolve(null),
    ]).then(([a, b]) => { if (vivo) setLitro({ a, b }); });
    // Período que atravessa o ano: o cartão já diz por que não compara (respostaOrcado → "varios_anos").
    if (orcMeses) {
      fetchComparativoOrcado({ ...orcMeses, centro_custo: centroApi ?? undefined })
        .then((c) => { if (vivo) setOrc({ c, erro: null }); }).catch((e) => { if (vivo) setOrc({ c: null, erro: (e as Error).message }); });
    }
    return () => { vivo = false; };
  }, [regras.ativa, periodo.ini, periodo.fim, cmpPeriodo?.ini, cmpPeriodo?.fim, efetivo.reg, centroApi, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    let vivo = true;
    // O caixa é de HOJE em diante: não muda com o período escolhido.
    fetchCaixaReal(60, hoje).then((c) => { if (vivo) setCaixa({ c, erro: null }); })
      .catch((e) => { if (vivo) setCaixa({ c: null, erro: /403/.test((e as Error).message) ? "O Caixa real só aparece para o administrador da fazenda." : (e as Error).message }); });
    return () => { vivo = false; };
  }, [hoje, tentativa]);

  const linhas = useMemo(() => linhasDre(dre?.a ?? null, cmpPeriodo ? dre?.b ?? null : null), [dre, cmpPeriodo]);
  const res = valorLinha(linhas, "RESULTADO_LIQUIDO"), rl = valorLinha(linhas, "RECEITA_LIQUIDA"), ebitda = valorLinha(linhas, "EBITDA");
  const la = litro?.a?.atual ?? null, lb = cmpPeriodo ? litro?.b?.atual ?? null : null;
  const okLitro = temResultadoPorLitro(la);
  const cx = useMemo(() => respostaCaixa(caixa?.c ?? null, hoje), [caixa, hoje]);
  const o = respostaOrcado(orc?.c ?? null, !!orcMeses);
  const estado = regras.ativa === null || (!dre && !erro) ? "carregando" : erro && !dre ? "erro" : linhas.every((l) => Math.abs(l.a) < 0.005) ? "vazio" : "ok";
  const frase = frasePainel({ periodoLabel: periodo.label, resultado: res?.a ?? null, litro: okLitro ? la : null, caixa: cx, fmt: FMT });
  const decisoes = decisoesDoMes({
    caixa: cx, litro: okLitro ? la : null, naoClassificado: dre?.a.nao_classificado?.total ?? 0,
    pendenciasNatureza: dre?.a.pendencias_natureza?.length ?? 0, orcado: o, fmt: FMT,
  });

  const exportar = (): RelatorioParaExportar | null => {
    if (!dre) return null;
    const t = (v: number | null | undefined, f: (x: number) => string) => (v == null ? "—" : f(v));
    return {
      titulo: "Painel do dono", pergunta: "Como está a fazenda?",
      contexto: { periodo: periodo.label, comparacao: cmpPeriodo?.label ?? null, regime: REGIME_NOME[efetivo.reg], centro: efetivo.cc === "todos" ? "todos os centros" : efetivo.cc },
      colunas: [{ header: "Pergunta", tipo: "texto", width: 28 }, { header: "Resposta", tipo: "texto", width: 26 }, { header: "Detalhe", tipo: "texto", width: 60 }],
      linhas: [
        { valores: ["Estou ganhando?", t(res?.a, FMT.brl), `Resultado da DRE · receita líquida ${t(rl?.a, FMT.brl)} · geração de caixa ${t(ebitda?.a, FMT.brl)}`] },
        { valores: ["Quanto custa o litro?", okLitro ? `${FMT.brl(la!.coe_l!)}/L` : "—", okLitro ? `Preço líquido ${FMT.brl(la!.preco_liquido_l!)}/L · sobra ${FMT.brl(la!.margem_l!)}/L` : "Sem litros ou sem receita do leite no período"] },
        { valores: ["Quando o caixa aperta?", cx ? FMT.brl(cx.saldoHoje) : "—", cx ? `${cx.negativoEm ? `negativo em ${FMT.dia(cx.negativoEm)}` : cx.abaixoReservaEm ? `abaixo da reserva em ${FMT.dia(cx.abaixoReservaEm)}` : "não fica abaixo da reserva em 60 dias"}${cx.menor ? ` · menor saldo ${FMT.brl(cx.menor.saldo)} em ${FMT.dia(cx.menor.data)}` : ""}` : caixa?.erro ?? "—"] },
        { valores: ["Gastei o que planejei?", o && o.estado === "ok" ? FMT.brl(o.realizado) : "—", o && o.estado === "ok" ? `orçado ${FMT.brl(o.orcado)} · ${o.acima ? "acima" : "abaixo"} em ${FMT.brl(Math.abs(o.desvio))}` : textoOrcado(o)] },
      ],
      nomeArquivoBase: "painel_do_dono",
      notas: ["Números do servidor: DRE da fazenda, Resultado por litro, Caixa real e orçado × realizado do mesmo contexto."],
    };
  };

  const ir = (id: string) => props.onIrRelatorio(id);
  const cartoes = (
    <div className="pd-cartoes">
      <article className="pd-cartao" aria-labelledby="pd-q1">
        <h3 className="q" id="pd-q1">Estou ganhando?</h3>
        <span className="l">Resultado (DRE)</span>
        <span className={`v${(res?.a ?? 0) < 0 ? " neg" : ""}`}>{res ? <NumeroAnimado valor={res.a} formato="brl0" /> : "—"}</span>
        {rotuloCmp && res && <ChipVariacao a={res.a} cmp={{ valor: res.b, rotulo: rotuloCmp }} bom="sobe" formato="brl0" />}
        <span className="s">Receita líquida <b>{rl ? brl(rl.a, 0) : "—"}</b> · geração de caixa da atividade <b className={(ebitda?.a ?? 0) < 0 ? "neg" : undefined}>{ebitda ? brl(ebitda.a, 0) : "—"}</b></span>
        <span className="ir"><button type="button" onClick={() => ir("rel_dre")}>Abrir a DRE da fazenda <ChevronRight size={13} aria-hidden /></button></span>
      </article>
      <article className="pd-cartao" aria-labelledby="pd-q2">
        <h3 className="q" id="pd-q2">Quanto custa o litro?</h3>
        <span className="l">Custo de custeio por litro</span>
        <span className="v">{okLitro && la!.coe_l != null ? <><NumeroAnimado valor={la!.coe_l} formato="brlL" /><span className="u">/L</span></> : "—"}</span>
        {rotuloCmp && okLitro && <ChipVariacao a={la!.coe_l} cmp={{ valor: temResultadoPorLitro(lb) ? lb!.coe_l : null, rotulo: rotuloCmp }} bom="desce" formato="brlL" />}
        <span className="s">{okLitro
          ? <>Vendido a <b>{brl(la!.preco_liquido_l!)}</b> líquido: {la!.margem_l! >= 0 ? "sobram" : "faltam"} <b className={la!.margem_l! < 0 ? "neg" : undefined}>{brl(Math.abs(la!.margem_l!))}</b> por litro.</>
          : "Sem litros entregues ou sem receita do leite neste período."}</span>
        <span className="ir"><button type="button" onClick={() => ir("rel_litro")}>Abrir o Resultado por litro <ChevronRight size={13} aria-hidden /></button></span>
      </article>
      <article className="pd-cartao" aria-labelledby="pd-q3">
        <h3 className="q" id="pd-q3">Quando o caixa aperta?</h3>
        <span className="l">Saldo hoje</span>
        <span className={`v${(cx?.saldoHoje ?? 0) < 0 ? " neg" : ""}`}>{cx ? <NumeroAnimado valor={cx.saldoHoje} formato="brl0" /> : "—"}</span>
        {cx && (cx.negativoEm
          ? <span className="pd-chip ruim"><AlertTriangle size={12} aria-hidden /> fica negativo em {FMT.dia(cx.negativoEm)}</span>
          : cx.abaixoReservaEm
            ? <span className="pd-chip aten"><Clock size={12} aria-hidden /> abaixo da reserva em {FMT.dia(cx.abaixoReservaEm)}</span>
            : <span className="pd-chip">não fica abaixo da reserva em 60 dias</span>)}
        <span className="s">{cx
          ? cx.menor ? <>Menor saldo em 60 dias: <b className={cx.menor.saldo < 0 ? "neg" : undefined}>{brl(cx.menor.saldo, 0)}</b> em {FMT.dia(cx.menor.data)}.</> : null
          : caixa?.erro || "Carregando o caixa…"}</span>
        <span className="ir"><button type="button" onClick={() => ir("rel_caixa")}>Abrir o Caixa real <ChevronRight size={13} aria-hidden /></button></span>
      </article>
      <article className="pd-cartao" aria-labelledby="pd-q4">
        <h3 className="q" id="pd-q4">Gastei o que planejei?</h3>
        <span className="l">Despesas × orçado</span>
        <span className="v">{o && (o.estado === "ok" || o.estado === "sem_orcamento") ? <NumeroAnimado valor={o.realizado} formato="brl0" /> : "—"}</span>
        {o && o.estado === "ok" && (
          <span className={`pd-chip ${o.acima ? "ruim" : "bom"}`}><span aria-hidden>{o.acima ? "▲" : "▼"}</span> {brl(Math.abs(o.desvio), 0)}{o.desvioPct != null ? ` (${Math.abs(o.desvioPct).toLocaleString("pt-BR")}%)` : ""} {o.acima ? "acima do orçado" : "abaixo do orçado"}</span>
        )}
        <span className="s">{o && o.estado === "ok" ? <>Orçado para {orcMeses && orcMeses.mes_inicio === orcMeses.mes_fim ? mesLongo(`${orcMeses.ano}-${String(orcMeses.mes_inicio).padStart(2, "0")}`) : "o período"}: <b>{brl(o.orcado, 0)}</b> de despesas.</> : orc?.erro && orcMeses ? `Não foi possível ler o orçamento (${orc.erro}).` : textoOrcado(o, !orc)}</span>
        <span className="ir"><button type="button" onClick={() => ir("rel_orcamento")}>{o?.estado === "sem_orcamento" ? "Montar o orçamento" : "Abrir o Orçamento"} <ChevronRight size={13} aria-hidden /></button></span>
      </article>
    </div>
  );

  const apresentar = (
    <button ref={botaoApresentar} type="button" className="c4-btn-pri" onClick={() => setApresentando(true)} disabled={estado !== "ok"}>
      <Play size={15} aria-hidden /> Apresentar o mês
    </button>
  );

  return (
    <>
      <style>{CSS_C4}</style>
      <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Painel" nome="Painel do dono" pergunta="Como está a fazenda?"
        onIrGrupo={props.onIrGrupo} estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => { setErro(null); setTentativa((t) => t + 1); }}
        frase={frase} exportar={exportar} acaoCabecalho={apresentar}
        vazio={<VazioQueEnsina titulo={`Nada lançado em ${periodo.label}`}
          texto="O painel responde às 4 perguntas com a DRE do período escolhido. Este período não tem receita nem custo lançado. O caixa não depende do período: ele continua no Caixa real."
          itens={[
            { texto: "Notas de compra e de venda do período", pronto: false, acao: <a href="/financeiro?sub=a_pagar">Lançar em Contas</a> },
            { texto: "Venda do leite (litros entregues)", pronto: false, acao: <a href="/lancamentos?sub=entrega_leite">Lançar a venda mensal do leite</a> },
          ]}
          acoes={<>
            <button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>
            <button type="button" className="rl-btn" onClick={() => ir("rel_caixa")}>Abrir o Caixa real</button>
          </>} />}>
        {cartoes}
        <div className="pd-dois">
          <section className="rl-painel" aria-labelledby="pd-60">
            <h3 className="rl-tit" id="pd-60">O caixa nos próximos 60 dias</h3>
            {cx && caixa?.c ? (<>
              <GraficoSaldo serie={caixa.c.serie.filter((p) => p.data <= somaDias(hoje, 60))} reserva={cx.reserva} abaixoReservaEm={cx.abaixoReservaEm}
                negativoEm={cx.negativoEm} menor={cx.menor}
                descricao={`Saldo projetado para 60 dias: hoje ${brl(cx.saldoHoje, 0)}${cx.menor ? `, menor ${brl(cx.menor.saldo, 0)} em ${FMT.dia(cx.menor.data)}` : ""}${cx.abaixoReservaEm ? `, abaixo da reserva em ${FMT.dia(cx.abaixoReservaEm)}` : ""}${cx.negativoEm ? `, negativo em ${FMT.dia(cx.negativoEm)}` : ""}.`} />
              <LegendaSaldo temNegativo={!!cx.menor && cx.menor.saldo < 0} />
            </>) : <p style={{ margin: 0, fontSize: ".86rem", color: "var(--text-muted)" }}>{caixa?.erro || "Carregando o caixa…"}</p>}
            <p style={{ margin: ".5rem 0 0" }}><button type="button" className="rg-lk" onClick={() => ir("rel_caixa")}>Abrir o Caixa real e simular uma compra <ChevronRight size={12} aria-hidden /></button></p>
          </section>
          <section className="rl-painel" aria-labelledby="pd-7">
            <h3 className="rl-tit" id="pd-7">Vence nos próximos 7 dias</h3>
            {cx ? (cx.vence7.itens.length ? (<>
              <ul className="pd-lst">
                {cx.vence7.itens.map((i, k) => (
                  <li key={`${i.data}-${k}`}>
                    <span className={`ic${i.vencido ? " ruim" : ""}`}>{i.vencido ? <AlertTriangle size={17} aria-hidden /> : <Clock size={17} aria-hidden />}</span>
                    <div><b>{i.descricao || "Sem descrição"}</b><small>{i.vencido ? `vencida em ${FMT.dia(i.data_original)} · ` : ""}{diaSemana(i.data)}, {FMT.dia(i.data)}</small></div>
                    <span className="vl">{brl(i.valor)}</span>
                  </li>
                ))}
              </ul>
              <p className="pd-total">Total: <b>{brl(cx.vence7.total)}</b> · mesma lista do Caixa real</p>
            </>) : <p style={{ margin: 0, fontSize: ".86rem", color: "var(--text-muted)" }}>Nada vence nos próximos 7 dias.</p>)
              : <p style={{ margin: 0, fontSize: ".86rem", color: "var(--text-muted)" }}>{caixa?.erro || "Carregando…"}</p>}
          </section>
        </div>
        <NotasMetodo titulo="Como estes números são feitos"
          entra={[
            ["Estou ganhando?", "O resultado da DRE da fazenda do mesmo período, regime e centro — o mesmo número da Capa e da DRE."],
            ["Quanto custa o litro?", "Custo de custeio (comida, gente e outros custeios da DRE) ÷ litros entregues, do relatório Resultado por litro."],
            ["Quando o caixa aperta?", "Saldo de hoje e a projeção do Caixa real: contas em aberto pelo vencimento, faturas e pagamentos agendados. Não muda com o período escolhido."],
            ["Gastei o que planejei?", "Despesas operacionais realizadas × orçadas no Orçamento, pelos totais separados das regras novas (receita não se mistura com despesa)."],
          ]} />
      </RelatorioShell>
      {apresentando && dre && (
        <ApresentarMes periodoLabel={periodo.label} contexto={`${periodo.label}, ${REGIME_NOME[efetivo.reg]}, ${efetivo.cc === "todos" ? "todos os centros" : efetivo.cc}`}
          linhas={linhas} rotuloCmp={rotuloCmp} litro={litro?.a ?? null} caixa={caixa?.c ?? null} cx={cx} decisoes={decisoes}
          onFechar={() => { setApresentando(false); requestAnimationFrame(() => botaoApresentar.current?.focus()); }}
          onIr={(id) => { setApresentando(false); ir(id); }} />
      )}
    </>
  );
}

function textoOrcado(o: ReturnType<typeof respostaOrcado>, carregando = false): string {
  if (carregando || !o) return "Carregando o orçamento…";
  switch (o.estado) {
    case "varios_anos": return "O orçamento é por ano: escolha um período dentro de um mesmo ano.";
    case "regras_antigas": return "Com as regras antigas o total do orçamento mistura receita e despesa. Ligue as regras novas em Parâmetros financeiros para ver aqui.";
    case "sem_orcamento": return "Sem orçamento de despesas para este período.";
    default: return "";
  }
}
