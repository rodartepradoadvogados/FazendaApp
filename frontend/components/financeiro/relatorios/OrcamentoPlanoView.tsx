"use client";
// Relatórios › Plano › Orçamento — "Gastei o que planejei?" (Fase C).
// Orçado × realizado por linha da DRE (R$ e R$/L), desvio para os dois lados,
// conta a conta com os totais por grupo do PR 8 (receita, deduções, despesa
// operacional e fora do resultado — nunca somados) e a planilha conta × 12
// meses. Os números vêm de GET /planejamento/orcamento/relatorio; sem
// orçamento nada fica vermelho. Flag `financeiro_regras_v2` desligada: o
// comparativo antigo tal qual, com o que a regra antiga não tem travado.
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronRight, ExternalLink, Info, Table2 } from "lucide-react";
import { fetchItensOrcamento, fetchOrcamentoRelatorio } from "@/lib/apiPlano";
import { ESTADO_INICIAL, brl, brlSinal, delta, deslocar, formatarDelta, num, pctSinal, periodoDe } from "@/lib/relatorioContexto";
import { filtroConsultasDe } from "@/lib/relatorioDre";
import {
  NOME_LINHA, avaliar, contasForaDoPlano, desvioPorLinha, fraseOrcamento, linhaDre, periodoDeMesesInteiros, secoesContas,
  type LinhaConta, type RespostaOrcamento,
} from "@/lib/relatorioOrcamento";
import type { LinhaRelatorio, RelatorioParaExportar } from "@/lib/export";
import { Conferencia, NotasMetodo, PainelGrafico, RelatorioShell, VazioQueEnsina, type KpiDef } from "./RelatorioShell";
import { DesvioPorLinha, LegendaDesvio } from "./graficosPlano";
import { GradeOrcamento, type AcaoInicialGrade } from "./GradeOrcamento";
import { CSS_PLANO } from "./estilosPlano";
import { useContextoRelatorio, useDetalheNaUrl, type TravasContexto } from "./useContextoRelatorio";
import { useRegrasV2Estado, type PropsRelatorio } from "./comum";

const PORQUE = "O orçamento é feito pelo mês do gasto e sempre comparado com o realizado (meses inteiros).";
const ROTULO_GRUPO: Record<string, string> = { receita: "Receitas", deducao: "Deduções da receita (Funrural, Senar e descontos)", despesa_operacional: "Despesas", fora_do_resultado: "Fora do resultado (investimento, financiamento, capital)" };

export default function OrcamentoPlanoView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const regras = useRegrasV2Estado();
  const travas: TravasContexto = useMemo(() => ({ reg: "comp", cmp: "orc", porque: PORQUE }), []);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const { periodo, efetivo } = ctx;
  const [vista, abrirVista] = useDetalheNaUrl("v");
  const [porLitro, setPorLitro] = useState(false);
  const [acaoGrade, setAcaoGrade] = useState<AcaoInicialGrade>(null);
  const [dados, setDados] = useState<RespostaOrcamento | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const [temAnterior, setTemAnterior] = useState(false);
  const inteiros = periodoDeMesesInteiros(periodo);
  const centroApi = efetivo.cc === "todos" ? null : efetivo.cc;
  const ano = Number(periodo.ini.slice(0, 4));

  useEffect(() => {
    if (regras.ativa === null || !inteiros) return;
    let vivo = true;
    fetchOrcamentoRelatorio({ data_inicio: periodo.ini, data_fim: periodo.fim, centro_custo: centroApi })
      .then((r) => { if (vivo) { setDados(r); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [regras.ativa, inteiros, periodo.ini, periodo.fim, centroApi, tentativa]);
  useEffect(() => {
    let vivo = true;
    fetchItensOrcamento(ano - 1).then((x) => { if (vivo) setTemAnterior(x.length > 0); }).catch(() => {});
    return () => { vivo = false; };
  }, [ano]);

  const abrirGrade = (acao: AcaoInicialGrade = null) => { setAcaoGrade(acao); abrirVista("grade"); };
  const consultas = useCallback((l: LinhaConta) => props.onConsultas(filtroConsultasDe({
    periodo, regime: "comp", cc: efetivo.cc, conta: { codigo: l.codigo_conta_gerencial, nome: l.nome_conta_gerencial }, origem: "Orçamento",
  })), [props, periodo, efetivo.cc]);
  // Da linha da DRE para a DRE da fazenda, já comparando com o orçado.
  const abrirNaDre = (chave: string) => {
    const q = new URLSearchParams(window.location.search);
    q.set("cmp", "orc"); q.set("reg", "comp"); q.delete("cmpp");
    window.history.replaceState(window.history.state, "", `${window.location.pathname}?${q.toString()}${window.location.hash}`);
    props.onIrRelatorio("rel_dre", chave);
  };

  const v2 = !!dados?.regras_v2;
  const estado = vista === "grade" ? "ok"
    : !inteiros ? "vazio"
      : regras.ativa === null || (!dados && !erro) ? "carregando" : erro && !dados ? "erro" : dados && !dados.tem_orcamento ? "vazio" : "ok";

  const secoes = useMemo(() => secoesContas(dados), [dados]);
  const desvios = useMemo(() => desvioPorLinha(dados), [dados]);
  const res = linhaDre(dados, "RESULTADO_LIQUIDO");
  const fora = contasForaDoPlano(dados);

  const kpis: KpiDef[] = v2 && dados?.totais && res ? [
    { chave: "res", rotulo: "Resultado", valor: res.realizado, cmp: res.orcado, formato: "brl0", bom: "sobe", negativoEmVermelho: true,
      sub: `Orçado ${brl(res.orcado ?? 0, 0)} · ${dados.litros ? `${brl(res.realizado_l ?? 0)}/L entregue` : "sem litros no período"}`, onAbrir: () => abrirNaDre("RESULTADO_LIQUIDO") },
    { chave: "rec", rotulo: "Receitas", valor: dados.totais.receita.realizado, cmp: dados.totais.receita.orcado || null, formato: "brl0", bom: "sobe",
      sub: dados.totais.receita.orcado ? `Orçado ${brl(dados.totais.receita.orcado, 0)}` : "Sem receita orçada", onAbrir: () => abrirNaDre("RECEITA_VENDAS") },
    { chave: "des", rotulo: "Despesas", valor: dados.totais.despesa_operacional.realizado, cmp: dados.totais.despesa_operacional.orcado || null, formato: "brl0", bom: "desce",
      sub: dados.totais.despesa_operacional.orcado ? `Orçado ${brl(dados.totais.despesa_operacional.orcado, 0)} · inclui contas sem orçamento` : "Sem despesa orçada", onAbrir: () => abrirNaDre("EBITDA") },
    { chave: "resl", rotulo: "Resultado por litro", valor: res.realizado_l, cmp: res.orcado_l, formato: "brlL", unidade: "/L", bom: "sobe", negativoEmVermelho: true,
      sub: dados.litros ? `${num(dados.litros, 0)} L entregues; o orçado usa os mesmos litros` : "Sem litros entregues no período" },
  ] : [];

  const frase = v2 && dados ? fraseOrcamento({ periodo, r: dados, brl: (v) => brl(v, 0), delta: (a, b, bom) => delta(a, b, bom) }) : [];

  // ── Exportar ──
  const exportar = (): RelatorioParaExportar | null => {
    if (!dados) return null;
    const contexto = { periodo: periodo.label, comparacao: "o orçado", regime: "pelo mês do gasto (competência)", centro: efetivo.cc === "todos" ? "todos os centros" : efetivo.cc };
    if (!v2) {
      const a = dados.comparativo_antigo;
      if (!a) return null;
      return {
        titulo: "Orçamento", pergunta: "Gastei o que planejei?", contexto, nomeArquivoBase: "orcamento",
        colunas: [{ header: "Conta", tipo: "texto" }, { header: "Tipo", tipo: "texto" }, { header: "Orçado", tipo: "brl" }, { header: "Realizado", tipo: "brl" }, { header: "Desvio", tipo: "brl" }],
        linhas: a.linhas.map((l) => ({ valores: [l.nome_conta_gerencial, l.tipo === "receita" ? "Receita" : "Despesa", l.orcado || null, l.realizado, l.orcado ? l.desvio : null] })),
        notas: ["Regras antigas dos relatórios: sem totais por grupo nem linha da DRE."],
      };
    }
    const linhas: LinhaRelatorio[] = [];
    for (const s of secoes) {
      linhas.push({ valores: [ROTULO_GRUPO[s.grupo], null, null, null, null, null, null], total: true });
      for (const l of [...s.orcadas, ...s.semOrcamento]) {
        const av = avaliar(l);
        linhas.push({ valores: [l.nome_conta_gerencial, l.linha_dre ? NOME_LINHA[l.linha_dre] ?? l.linha_dre : "—", l.orcado || null, l.realizado, l.desvio, l.desvio_pct, av.texto], nivel: l.coberta_por ? 2 : 1 });
      }
      linhas.push({ valores: [`Total — ${s.rotulo}`, null, s.total.orcado, s.total.realizado, s.total.desvio, s.total.desvio_pct, avaliar({ grupo: s.grupo, situacao: s.total.situacao, desvio: s.total.desvio }).texto], total: true });
    }
    return {
      titulo: "Orçamento", pergunta: "Gastei o que planejei?", contexto, nomeArquivoBase: "orcamento",
      colunas: [{ header: "Conta", tipo: "texto" }, { header: "Linha da DRE", tipo: "texto" }, { header: "Orçado", tipo: "brl" }, { header: "Realizado", tipo: "brl" },
        { header: "Δ", tipo: "brl" }, { header: "Δ%", tipo: "pct" }, { header: "Avaliação", tipo: "texto" }],
      linhas,
      notas: [
        "Orçado × realizado do servidor (GET /planejamento/orcamento/relatorio): realizado pelos mesmos registros da DRE de competência.",
        "Totais por grupo, nunca somados: receitas, deduções, despesas e o que fica fora do resultado. Sem orçamento não há desvio.",
        ...desvios.map((d) => `${d.nome}: orçado ${d.orcado == null ? "—" : brl(d.orcado)}, realizado ${brl(d.realizado)}${d.realizadoL != null ? ` (${brl(d.realizadoL, 4)}/L)` : ""} — ${d.texto}.`),
      ],
    };
  };

  // ── Estados vazios que ensinam ──
  const vazioUi = !inteiros ? (
    <VazioQueEnsina titulo="O orçamento é mensal" texto={<>O período {periodo.label} começa ou termina no meio de um mês. Escolha meses inteiros para comparar com o orçado.</>}
      acoes={<button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: `m:${periodo.fim.slice(0, 7)}` })}>Ver {periodoDe(`m:${periodo.fim.slice(0, 7)}`)!.label}</button>} />
  ) : (
    <VazioQueEnsina titulo={`Ainda não há orçamento para ${periodo.label}${centroApi ? ` no centro ${centroApi}` : ""}`}
      texto="O orçamento é a régua do “gastei o que planejei?”. Sem ele, nenhum desvio aparece — nada fica vermelho por falta de plano. Comece por uma base e ajuste mês a mês na planilha."
      itens={[
        { texto: "Plano de contas da fazenda", pronto: true },
        { texto: `Valores por conta e mês de ${ano}`, pronto: false, acao: <button type="button" className="lk" style={{ all: "unset", cursor: "pointer", color: "var(--text-accent)", fontWeight: 600, textDecoration: "underline" }} onClick={() => abrirGrade()}>abrir a planilha</button> },
      ]}
      acoes={<>
        {temAnterior && <button type="button" className="rl-btn pri" onClick={() => abrirGrade({ tipo: "copiar" })}>Copiar o orçamento de {ano - 1}</button>}
        <button type="button" className="rl-btn" onClick={() => abrirGrade()}><Table2 size={14} aria-hidden /> Começar na planilha</button>
        <button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>
      </>} />
  );

  const avisos = (<>
    {dados && !v2 && vista !== "grade" && (
      <div className="rl-aviso" role="status"><AlertTriangle size={18} aria-hidden /><div>
        <b>Regras antigas dos relatórios: só o comparativo conta a conta, como antes.</b>
        <p>{dados.travado ?? "Totais separados por grupo, desvio por linha da DRE e R$ por litro entram quando as regras novas forem ligadas em Parâmetros financeiros — nenhum número muda até lá."}</p>
      </div></div>
    )}
    {v2 && dados?.orcado_sem_linha && dados.orcado_sem_linha.total > 0 && vista !== "grade" && (
      <div className="rl-aviso info" role="status"><Info size={18} aria-hidden /><div>
        <b>{brl(dados.orcado_sem_linha.total, 0)} orçados em conta sem linha da DRE</b>
        <p>{dados.orcado_sem_linha.contas.map((c) => c.nome || c.codigo).join(", ")} — ficam fora do desvio por linha até a conta ganhar uma linha (DRE por conta, tela anterior).</p>
      </div></div>
    )}
  </>);

  const cabecalhoVista = (
    <div className="rl-cabacoes rl-noprint">
      <div className="rl-segv" role="group" aria-label="O que ver">
        <button type="button" aria-pressed={vista !== "grade"} onClick={() => abrirVista("")}>Orçado × realizado</button>
        <button type="button" aria-pressed={vista === "grade"} onClick={() => abrirGrade()}>Editar orçamento (planilha)</button>
      </div>
      <button type="button" className="rl-btn" onClick={() => props.onIrRelatorio("orcamento_itens")}>
        <ExternalLink size={14} aria-hidden /> Item a item, observação e Importar para Pedidos
      </button>
    </div>
  );

  return (<>
    <style>{CSS_PLANO}</style>
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Plano" nome="Orçamento" pergunta="Gastei o que planejei?"
      onIrGrupo={props.onIrGrupo} niveis={vista === "grade" ? [{ rotulo: `Planilha de ${ano}` }] : []} onVoltarNivel={() => abrirVista("")}
      estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => { setErro(null); setTentativa((t) => t + 1); }} vazio={<>{cabecalhoVista}{vazioUi}</>}
      frase={vista === "grade" ? [] : frase} kpis={vista === "grade" ? undefined : kpis} rotuloCmp="o orçado" avisos={avisos} exportar={exportar}>
      {cabecalhoVista}
      {vista === "grade" ? (
        <GradeOrcamento key={`${ano}-${efetivo.cc}`} ano={ano} cc={efetivo.cc} centros={centros} acaoInicial={acaoGrade}
          onSalvo={() => setTentativa((t) => t + 1)} />
      ) : v2 && dados ? (<>
        <PainelGrafico titulo="Desvio por linha da DRE" legenda={<LegendaDesvio />}
          tabela={{ cabecalho: ["Linha", "Orçado", "Realizado", "Desvio", "Desvio por litro", "Avaliação"], linhas: desvios.map((d) => [
            d.nome, d.orcado == null ? "—" : brl(d.orcado, 0), brl(d.realizado, 0), d.desvio == null ? "—" : formatarDelta(d.desvio, "brl0"),
            d.desvioL == null ? "—" : `${formatarDelta(d.desvioL, "brl")}/L`, d.texto,
          ]) }}>
          <div className="rl-segv rl-noprint" role="group" aria-label="Unidade do desvio" style={{ marginBottom: ".5rem" }}>
            <button type="button" aria-pressed={!porLitro} onClick={() => setPorLitro(false)}>R$ no período</button>
            <button type="button" aria-pressed={porLitro} onClick={() => setPorLitro(true)} disabled={!dados.litros}>R$ por litro</button>
          </div>
          <DesvioPorLinha linhas={desvios} porLitro={porLitro && !!dados.litros} onAbrir={abrirNaDre}
            descricao={`Desvio entre realizado e orçado por linha da DRE em ${periodo.label}${porLitro ? ", em reais por litro" : ""}: ${desvios.map((d) => `${d.nome} ${d.texto}`).join("; ")}.`} />
        </PainelGrafico>
        <section className="rl-painel" aria-labelledby="rl-orc-dre">
          <h3 className="rl-tit" id="rl-orc-dre">Orçado × realizado por linha da DRE</h3>
          <TabelaLinhasDre r={dados} onAbrir={abrirNaDre} />
        </section>
        <section className="rl-painel" aria-labelledby="rl-orc-contas">
          <h3 className="rl-tit" id="rl-orc-contas">Orçado × realizado, conta a conta</h3>
          <TabelaContas secoes={secoes} onAbrir={consultas}
            onIncluir={(l) => abrirGrade({ tipo: "incluir", codigo: l.codigo_conta_gerencial, nome: l.nome_conta_gerencial, tipoConta: l.tipo === "receita" ? "receita" : "despesa", centro: centroApi })} />
          {fora.length > 0 && <p style={{ margin: ".55rem 0 0", fontSize: ".8rem", color: "var(--text-muted)" }}>Sem orçamento, a conta fica à parte e sem cor: o realizado dela entra no total do grupo, mas não vira “desvio”.</p>}
        </section>
      </>) : dados?.comparativo_antigo ? (
        <section className="rl-painel" aria-labelledby="rl-orc-antigo">
          <h3 className="rl-tit" id="rl-orc-antigo">Orçado × realizado, conta a conta</h3>
          <TabelaAntiga r={dados} />
        </section>
      ) : null}
      {vista !== "grade" && (
        <NotasMetodo titulo="Como o desvio é avaliado"
          entra={[
            ["Por tipo", "Receita abaixo do plano é pior; despesa acima do plano é pior. Receitas, deduções e despesas têm totais separados — nunca somados num “desvio” só."],
            ["Sem orçamento", "Conta sem orçamento fica numa linha à parte, sem cor de desvio. Use “Incluir no orçamento” para planejar."],
            ["Conta-grupo", "O orçamento de uma conta-grupo cobre as contas abaixo dela que não têm orçamento próprio (aparecem recuadas, sem desvio)."],
            ["Por linha da DRE", "O orçado de cada conta cai na linha da DRE dela (como o realizado). O desgaste dos bens não é orçado: entra o do Patrimônio dos dois lados."],
            ["Por litro", "Os dois lados divididos pelos litros entregues no período (o orçamento ainda não tem litros previstos)."],
            ["Base", "Pelo mês do gasto (competência), no mesmo centro de custo do filtro."],
          ]}
          naoEntra={["Investimentos, principal de financiamento, retirada particular e transferências — aparecem em “Fora do resultado”, sem desvio."]}>
          <p style={{ margin: ".6rem 0 0" }}>
            Para lançar item a item (com observação) ou levar uma linha para Pedidos, use a{" "}
            <button type="button" className="rl-linkbtn" style={{ color: "var(--text-accent)", fontWeight: 700 }} onClick={() => props.onIrRelatorio("orcamento_itens")}>tela anterior do orçamento</button>.
          </p>
        </NotasMetodo>
      )}
      {vista !== "grade" && v2 && dados?.conferencia && (
        <Conferencia fecha={dados.conferencia.fecha} texto={dados.conferencia.fecha
          ? `O realizado conta a conta, somado por linha, é o da DRE da fazenda em ${periodo.label} (fora o desgaste dos bens e os juros e descontos da baixa). Resultado: ${brl(res?.realizado ?? 0, 0)}.`
          : `Diferença de ${brl(dados.conferencia.maior_diferenca)} entre o realizado conta a conta e a DRE — avise o suporte.`} />
      )}
    </RelatorioShell>
  </>);
}

// ── Tabelas ───────────────────────────────────────────────────────────────
const Dt = ({ v, melhor, f = "brl0" }: { v: number | null; melhor: boolean | null; f?: "brl0" | "brl" }) =>
  v == null ? <span className="mut">—</span> : Math.abs(v) < (f === "brl" ? 0.00005 : 0.5) ? <span className="mut">=</span> : (
    <span className={`rl-dt ${melhor == null ? "neu" : melhor ? "bom" : "ruim"}`}>
      <span aria-hidden>{v > 0 ? "▲" : "▼"}</span>{f === "brl" ? brlSinal(v, 3) : formatarDelta(v, "brl0")}
      {melhor != null && <span className="rl-sr"> ({melhor ? "melhor" : "pior"})</span>}
    </span>
  );

function TabelaLinhasDre({ r, onAbrir }: { r: RespostaOrcamento; onAbrir: (chave: string) => void }) {
  const linhas = (r.linhas_dre ?? []).filter((l) => l.eh_subtotal || l.orcado != null || Math.abs(l.realizado) >= 0.005);
  const v = (x: number | null, f: "brl0" | "brl") => (x == null ? <span className="mut">—</span> : <span className={x < 0 ? "neg" : undefined}>{f === "brl" ? brl(x, 4) : brl(x, 0)}</span>);
  return (
    <div className="rl-tw">
      <table className="fazenda-table rl-tab">
        <caption className="rl-sr">Orçado e realizado por linha da DRE, em reais e por litro</caption>
        <thead><tr>
          <th scope="col">Linha da DRE</th><th scope="col" className="r">Orçado</th><th scope="col" className="r">Realizado</th><th scope="col" className="r">Δ</th>
          <th scope="col" className="r">Orçado R$/L</th><th scope="col" className="r">Realizado R$/L</th><th scope="col" className="r rl-opc">Δ R$/L</th><th scope="col">Avaliação</th>
        </tr></thead>
        <tbody>
          {linhas.map((l) => {
            const custo = l.operador === "-";
            // Na cascata o custo é magnitude: o desvio do custo se lê ao contrário (gastar menos é melhor).
            const d = l.orcado == null ? null : l.realizado - l.orcado, dL = l.orcado_l == null || l.realizado_l == null ? null : l.realizado_l - l.orcado_l;
            const melhor = d == null || Math.abs(d) < 0.5 ? null : custo ? d < 0 : d > 0;
            const av = l.orcado == null ? "sem orçamento" : melhor == null ? "no plano" : l.origem_orcado === "patrimonio" ? "do Patrimônio (não é orçado)"
              : custo ? (melhor ? "gasto abaixo · melhor" : "gasto acima · pior") : (melhor ? "acima do plano · melhor" : "abaixo do plano · pior");
            const nome = NOME_LINHA[l.chave] ?? l.rotulo;
            return (
              <tr key={l.chave} className={`${l.eh_subtotal ? "tot" : "ind"} clic`} onClick={(e) => { if (!(e.target as HTMLElement).closest("button")) onAbrir(l.chave); }}>
                <td><button type="button" className="rl-linkbtn" onClick={() => onAbrir(l.chave)} aria-label={`${nome}: abrir na DRE da fazenda comparando com o orçado`}>
                  {l.eh_subtotal ? `= ${nome}` : nome}<ChevronRight size={14} aria-hidden /></button></td>
                <td className="r mut">{v(l.orcado, "brl0")}</td>
                <td className="r">{v(l.realizado, "brl0")}</td>
                <td className="r"><Dt v={d} melhor={melhor} /></td>
                <td className="r mut">{v(l.orcado_l, "brl")}</td>
                <td className="r">{v(l.realizado_l, "brl")}</td>
                <td className="r rl-opc"><Dt v={dL} melhor={melhor} f="brl" /></td>
                <td className="av">{av}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TabelaContas({ secoes, onAbrir, onIncluir }: { secoes: ReturnType<typeof secoesContas>; onAbrir: (l: LinhaConta) => void; onIncluir: (l: LinhaConta) => void }) {
  const linha = (l: LinhaConta, sem = false) => {
    const av = avaliar(l);
    return (
      <tr key={`${l.codigo_conta_gerencial}-${l.coberta_por ?? ""}`} className={`clic${l.coberta_por ? " coberta" : ""}`}
        onClick={(e) => { if (!(e.target as HTMLElement).closest("button")) onAbrir(l); }}>
        <td>
          <button type="button" className="rl-linkbtn" onClick={() => onAbrir(l)} aria-label={`${l.nome_conta_gerencial}: ver os lançamentos em Consultas`}>
            {l.nome_conta_gerencial}<ChevronRight size={14} aria-hidden />
          </button>
          <span className="sub">{l.coberta_por ? `no orçamento do grupo ${l.coberta_por}` : l.linha_dre ? NOME_LINHA[l.linha_dre] ?? l.linha_dre : l.codigo_conta_gerencial}</span>
        </td>
        <td className="r mut">{l.orcado ? brl(l.orcado, 0) : "—"}</td>
        <td className="r">{brl(l.realizado, 0)}</td>
        <td className="r"><Dt v={l.desvio} melhor={av.melhor} /></td>
        <td className="r mut rl-opc">{l.desvio_pct == null ? "—" : pctSinal(l.desvio_pct / 100)}</td>
        <td className="av">{sem && l.grupo !== "fora_do_resultado" && !l.codigo_conta_gerencial.startsWith("(")
          ? <button type="button" className="lk" onClick={() => onIncluir(l)}>Incluir no orçamento</button> : av.texto}</td>
      </tr>
    );
  };
  return (
    <div className="rl-tw">
      <table className="fazenda-table rl-tab">
        <caption className="rl-sr">Orçado e realizado por conta, com totais separados por grupo</caption>
        <thead><tr><th scope="col">Conta</th><th scope="col" className="r">Orçado</th><th scope="col" className="r">Realizado</th><th scope="col" className="r">Δ</th><th scope="col" className="r rl-opc">Δ%</th><th scope="col">Avaliação</th></tr></thead>
        <tbody>
          {secoes.map((s) => {
            const av = avaliar({ grupo: s.grupo, situacao: s.total.situacao, desvio: s.total.desvio });
            return [
              <tr key={`h-${s.grupo}`} className="sec"><td colSpan={6}>{ROTULO_GRUPO[s.grupo]}</td></tr>,
              ...s.orcadas.map((l) => linha(l)),
              ...(s.semOrcamento.length && s.grupo !== "fora_do_resultado" ? [<tr key={`s-${s.grupo}`} className="sub2"><td colSpan={6}>Sem orçamento (à parte: sem plano não há desvio)</td></tr>] : []),
              ...s.semOrcamento.map((l) => linha(l, true)),
              <tr key={`t-${s.grupo}`} className="tot">
                <td>Total — {s.rotulo}</td><td className="r">{s.grupo === "fora_do_resultado" ? "—" : brl(s.total.orcado, 0)}</td><td className="r">{brl(s.total.realizado, 0)}</td>
                <td className="r"><Dt v={s.total.desvio} melhor={av.melhor} /></td><td className="r rl-opc">{s.total.desvio_pct == null ? "—" : pctSinal(s.total.desvio_pct / 100)}</td>
                <td className="av">{av.texto}</td>
              </tr>,
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}

function TabelaAntiga({ r }: { r: RespostaOrcamento }) {
  const a = r.comparativo_antigo;
  if (!a) return null;
  return (
    <div className="rl-tw">
      <table className="fazenda-table rl-tab">
        <caption className="rl-sr">Orçado e realizado por conta (regras antigas)</caption>
        <thead><tr><th scope="col">Conta</th><th scope="col">Tipo</th><th scope="col" className="r">Orçado</th><th scope="col" className="r">Realizado</th><th scope="col" className="r">Desvio</th><th scope="col">Avaliação</th></tr></thead>
        <tbody>
          {a.linhas.map((l) => {
            const receita = l.tipo === "receita", tem = !!l.orcado;
            const melhor = !tem || Math.abs(l.desvio) < 0.5 ? null : receita ? l.desvio > 0 : l.desvio < 0;
            return (
              <tr key={l.codigo_conta_gerencial}>
                <td>{l.nome_conta_gerencial}<span className="sub">{l.codigo_conta_gerencial}</span></td>
                <td>{receita ? "Receita" : "Despesa"}</td>
                <td className="r mut">{tem ? brl(l.orcado, 0) : "—"}</td>
                <td className="r">{brl(l.realizado, 0)}</td>
                <td className="r">{tem ? <Dt v={l.desvio} melhor={melhor} /> : <span className="mut">—</span>}</td>
                <td className="av">{!tem ? "sem orçamento" : melhor == null ? "no plano" : melhor ? "melhor que o plano" : "pior que o plano"}</td>
              </tr>
            );
          })}
          {!a.linhas.length && <tr><td colSpan={6} className="mut">Nenhum item de orçamento neste período.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

