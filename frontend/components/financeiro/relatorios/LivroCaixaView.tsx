"use client";
// Relatórios › Caixa › Livro caixa da atividade rural — "O que vai para o Imposto de Renda?"
// O livro no formato do contador (data, histórico, documento, receita, despesa,
// saldo), com os totais de cada mês e do período. Os números vêm de GET
// /financeiro/livro-caixa-rural: com as regras novas, a regra fiscal do produtor
// pessoa física (receita bruta, investimento como despesa no pagamento,
// financiamento/aporte/transferência fora) e a ponte para a DRE de caixa; com
// as regras antigas, o Livro caixa de antes (todo pagamento e recebimento),
// com a separação fiscal travada e o porquê. O livro por conta bancária, com o
// saldo do extrato, continua em Consultas › Livro caixa.
import { useEffect, useMemo, useState } from "react";
import { BookOpen, ExternalLink, Info, Lock } from "lucide-react";
import { fetchLivroCaixaRural } from "@/lib/apiRelatoriosCaixa";
import { ESTADO_INICIAL, REGIME_NOME, brl, delta, deslocar, mesCurto, mesLongo } from "@/lib/relatorioContexto";
import { documentoDe, fraseLivro, historicoDe, secoesLivro, temLivro, type LinhaLivro, type RespostaLivro } from "@/lib/relatorioLivro";
import type { FiltroConsultasDrill } from "@/lib/relatorioDre";
import type { LinhaRelatorio, RelatorioParaExportar } from "@/lib/export";
import { Conferencia, NotasMetodo, PainelGrafico, RelatorioShell, VazioQueEnsina, type KpiDef } from "./RelatorioShell";
import { BarrasMensais, CSS_CAIXA, LegendaBarras } from "./graficosCaixa";
import { useContextoRelatorio, useDetalheNaUrl, type TravasContexto } from "./useContextoRelatorio";
import type { PropsRelatorio } from "./comum";

const brl0 = (v: number) => brl(v, 0);
const dmy = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
const CSS_LIVRO = `
.rl-lv-rolo{max-height:70vh;overflow:auto}
.rl-lv-rolo thead th{position:sticky;top:0;z-index:1}
.rl-lv tr.mes td{background:var(--surface-2);font-weight:700;font-size:.82rem}
.rl-lv tr.sub-mes td{font-weight:700;border-top:1px solid var(--border-strong,var(--border))}
.rl-lv td.doc{white-space:nowrap;color:var(--text-muted);font-size:.8rem}
.rl-lv .cat{display:inline-block;margin-left:.35rem;font-size:.68rem;font-weight:600;color:var(--text-muted);border:1px solid var(--border);border-radius:999px;padding:0 6px}
.rl-cmpbox{display:flex;flex-wrap:wrap;gap:.6rem}
.rl-cmpbox>div{flex:1 1 11rem;border:1px solid var(--border);border-radius:var(--r-sm);padding:.6rem .75rem}
.rl-cmpbox>div.com{border-color:var(--rl-a);background:var(--surface-2)}
.rl-cmpbox small{display:block;font-size:.74rem;color:var(--text-muted)}
.rl-cmpbox b{font-size:1.35rem;font-variant-numeric:tabular-nums}
.rl-ponte{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.35rem 1rem;margin:0;font-size:.86rem}
.rl-ponte dd{margin:0;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rl-ponte .tot{font-weight:700;border-top:1px solid var(--border-strong,var(--border));padding-top:.35rem}
@media print{.rl-lv-rolo{max-height:none!important;overflow:visible!important}.rl-lv-rolo thead th{position:static}}
`;
const CATEGORIA: Record<string, string> = { custeio: "custeio", investimento: "investimento", misto: "custeio + investimento" };

export default function LivroCaixaView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const [det, abrirDet] = useDetalheNaUrl("det");
  const mesDet = /^\d{4}-\d{2}$/.test(det) ? det : "";
  const travas: TravasContexto = useMemo(() => ({
    reg: "caixa", cc: "todos", cmpOrcado: false,
    ...(mesDet ? { rotuloPeriodo: mesLongo(mesDet) } : {}),
    porque: "O livro caixa segue a regra fiscal do produtor pessoa física: sempre pelo dia do pagamento e com todos os centros do imóvel.",
  }), [mesDet]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const { periodo, comparacao } = ctx;

  const [dados, setDados] = useState<RespostaLivro | null>(null);
  const [dadosCmp, setDadosCmp] = useState<RespostaLivro | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const cmpPeriodo = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  useEffect(() => {
    let vivo = true;
    Promise.all([
      fetchLivroCaixaRural({ data_inicio: periodo.ini, data_fim: periodo.fim }),
      cmpPeriodo ? fetchLivroCaixaRural({ data_inicio: cmpPeriodo.ini, data_fim: cmpPeriodo.fim }) : Promise.resolve(null),
    ]).then(([a, b]) => { if (vivo) { setDados(a); setDadosCmp(b); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [periodo.ini, periodo.fim, cmpPeriodo?.ini, cmpPeriodo?.fim, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps

  const rotuloCmp = cmpPeriodo ? comparacao!.rotulo : null;
  const t = dados?.totais, tq = cmpPeriodo ? dadosCmp?.totais ?? null : null;
  const fiscal = !!dados?.separacao_fiscal;
  const secoes = useMemo(() => secoesLivro(dados, mesDet || undefined), [dados, mesDet]);
  const mesSel = mesDet ? dados?.meses.find((m) => m.competencia === mesDet) ?? null : null;
  const estado = !dados && !erro ? "carregando" : erro && !dados ? "erro" : !temLivro(dados) ? "vazio" : "ok";

  const consultas = (f: FiltroConsultasDrill & { documento?: string; modo?: "livro" }) => props.onConsultas(f);
  const abrirLinha = (l: LinhaLivro) => consultas({ de: l.data, ate: l.data, periodoPor: "pagamento", origem: `Livro caixa › ${dmy(l.data)}`, ...(l.numero_lancamento ? { documento: l.numero_lancamento } : {}) });
  const livroPorConta = () => consultas({ de: periodo.ini, ate: periodo.fim, periodoPor: "pagamento", origem: "Livro caixa da atividade rural", modo: "livro" });

  const kpis: KpiDef[] = t ? [
    { chave: "res", rotulo: fiscal ? "Resultado da atividade rural" : "Recebido − pago", valor: t.resultado, cmp: tq?.resultado ?? null, formato: "brl0", bom: "sobe", negativoEmVermelho: true,
      sub: fiscal ? "Receitas recebidas − despesas pagas (custeio + investimentos)" : "Todo recebimento menos todo pagamento do período" },
    { chave: "rec", rotulo: "Receitas recebidas", valor: t.receitas, cmp: tq?.receitas ?? null, formato: "brl0", bom: "sobe",
      sub: fiscal ? "Leite pelo bruto, venda de animais e de bens" : "Todos os recebimentos (inclui empréstimo e aporte)",
      onAbrir: () => consultas({ de: periodo.ini, ate: periodo.fim, periodoPor: "pagamento", origem: "Livro caixa › Receitas" }) },
    { chave: "cus", rotulo: fiscal ? "Despesas de custeio pagas" : "Pagamentos", valor: fiscal ? t.custeio : t.despesas, cmp: tq ? (fiscal ? tq.custeio : tq.despesas) : null, formato: "brl0", bom: "desce",
      sub: fiscal ? "Inclui juros; não inclui principal de financiamento" : "Todos os pagamentos (inclui investimento e principal)",
      onAbrir: () => consultas({ de: periodo.ini, ate: periodo.fim, periodoPor: "pagamento", origem: "Livro caixa › Despesas" }) },
    fiscal
      ? { chave: "inv", rotulo: "Investimentos pagos", valor: t.investimentos, cmp: tq?.investimentos ?? null, formato: "brl0", bom: "neutro",
        sub: "Despesa no mês do pagamento, sem depreciação" }
      // Regras antigas: sem natureza não há investimento separado — trava com o porquê, nunca outro número.
      : { chave: "qtd", rotulo: "Lançamentos no livro", valor: t.quantidade, cmp: tq?.quantidade ?? null, formato: "num", bom: "neutro",
        selo: <span className="rl-selo"><Lock size={11} aria-hidden /> investimento: regras novas</span>,
        sub: "A separação custeio × investimento chega com as regras novas dos relatórios" },
  ] : [];

  const exportar = (): RelatorioParaExportar | null => {
    if (!dados || !t) return null;
    const linhas: LinhaRelatorio[] = [];
    for (const s of secoes) {
      for (const l of s.linhas) linhas.push({ valores: [dmy(l.data), historicoDe(l), documentoDe(l), l.receita || null, l.despesa || null, l.saldo] });
      linhas.push({ valores: [`Total de ${mesLongo(s.mes.competencia)}`, fiscal ? `custeio ${brl(s.mes.custeio)} · investimentos ${brl(s.mes.investimentos)}` : "", "", s.mes.receitas, s.mes.despesas, s.mes.resultado], total: true });
    }
    const alvo = mesSel ?? t;
    linhas.push({ valores: [mesSel ? `Total de ${mesLongo(mesDet)}` : "Total do período", "", "", alvo.receitas, alvo.despesas, alvo.resultado], total: true });
    return {
      titulo: mesDet ? `Livro caixa da atividade rural — ${mesLongo(mesDet)}` : "Livro caixa da atividade rural", pergunta: "O que vai para o Imposto de Renda?",
      contexto: { periodo: mesDet ? mesLongo(mesDet) : periodo.label, comparacao: null, regime: REGIME_NOME.caixa, centro: "todos os centros do imóvel" },
      colunas: [{ header: "Data", tipo: "texto" }, { header: "Histórico", tipo: "texto", width: 46 }, { header: "Documento", tipo: "texto" },
        { header: "Receita", tipo: "brl" }, { header: "Despesa", tipo: "brl" }, { header: "Saldo", tipo: "brl" }],
      linhas, nomeArquivoBase: "livro_caixa_atividade_rural",
      notas: [
        fiscal ? "Regra fiscal do produtor pessoa física: receita bruta recebida; despesas de custeio pagas (com juros) e investimentos pagos como despesa no mês, sem depreciação." :
          "Regras antigas: todo pagamento e recebimento do período, pelo valor pago (o Livro caixa de antes). A separação fiscal entra com as regras novas.",
        fiscal && dados.presumido_20 != null ? `Opção de 20% da receita bruta: ${brl(dados.presumido_20)}.` : "",
        fiscal && dados.fora_do_livro?.grupos.length ? `Fora do livro: ${dados.fora_do_livro.grupos.map((g) => `${g.rotulo} (${brl(g.entradas + g.saidas)})`).join("; ")}.` : "",
        "Saldo = resultado acumulado no período (receitas − despesas), não o saldo do banco.",
      ].filter(Boolean),
    };
  };

  const vazioUi = (
    <VazioQueEnsina titulo={`Nada no livro caixa em ${periodo.label}`}
      texto="O livro caixa junta o que foi recebido e pago no período, pelo dia do pagamento. Nada caiu aqui ainda:"
      itens={[
        { texto: "Pagamentos e recebimentos com data no período", pronto: false, acao: <a href="/financeiro?sub=a_pagar">Dar baixa numa conta</a> },
        { texto: "Regras novas dos relatórios (separação fiscal)", pronto: fiscal || !dados, acao: <a href="/parametros?sub=financeiro">Ligar em Parâmetros financeiros</a> },
      ]}
      acoes={<button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>} />
  );

  const avisos = dados && !fiscal ? (
    <div className="rl-aviso info" role="status"><Info size={18} aria-hidden /><div>
      <b>Livro com as regras antigas: todo pagamento e recebimento entra.</b>
      <p>Empréstimo, aporte, transferência e principal de financiamento aparecem como receita ou despesa, como no Livro caixa de antes. A separação fiscal (custeio, investimento e o que fica fora) vem com as regras novas: <a href="/parametros?sub=financeiro">ligar em Parâmetros financeiros</a>.</p>
    </div></div>
  ) : null;

  const melhor = dados?.presumido_20 != null && t ? (t.resultado <= dados.presumido_20 ? "real" : "presumido") : null;
  const p = dados?.ponte_dre;

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Caixa" nome="Livro caixa da atividade rural" pergunta="O que vai para o Imposto de Renda?"
      onIrGrupo={props.onIrGrupo} niveis={mesDet ? [{ rotulo: mesLongo(mesDet) }] : []} onVoltarNivel={() => abrirDet("")}
      estado={estado} erro={erro} onTentarDeNovo={() => { setErro(null); setTentativa((x) => x + 1); }} vazio={vazioUi}
      frase={dados && !mesDet ? fraseLivro(periodo, dados, brl0) : []} kpis={mesDet ? undefined : kpis} avisos={avisos} exportar={exportar}>
      <style>{CSS_CAIXA + CSS_LIVRO}</style>
      {dados && t && !mesDet && dados.meses.length >= 2 && (
        <PainelGrafico titulo="Resultado mês a mês (dia do pagamento)"
          legenda={<LegendaBarras series={[{ nome: "Resultado do mês", estilo: "resultado", valores: [] }]} sobrouFaltou />}
          tabela={{ cabecalho: ["Mês", "Receitas", "Despesas", "Resultado"], linhas: dados.meses.map((m) => [mesLongo(m.competencia), brl(m.receitas), brl(m.despesas), brl(m.resultado)]) }}>
          <BarrasMensais rotulos={dados.meses.map((m) => mesCurto(m.competencia))}
            series={[{ nome: "Resultado do mês", estilo: "resultado", valores: dados.meses.map((m) => (m.quantidade ? m.resultado : null)) }]}
            onAbrir={(i) => abrirDet(dados.meses[i].competencia)}
            rotuloAbrir={(i) => `${mesLongo(dados.meses[i].competencia)}: ${dados.meses[i].resultado >= 0 ? "sobrou" : "faltou"} ${brl(Math.abs(dados.meses[i].resultado))}. Abrir o mês no livro`}
            descricao={`Resultado mensal do livro caixa de ${periodo.label}: total ${brl0(t.resultado)}.`} />
        </PainelGrafico>
      )}

      {dados && t && !mesDet && (
        <section className="rl-painel" aria-labelledby="rl-lv-meses">
          <h3 className="rl-tit" id="rl-lv-meses">Totais por mês</h3>
          <div className="rl-tw">
            <table className="fazenda-table rl-tab">
              <caption className="rl-sr">Livro caixa: totais por mês — {periodo.label}</caption>
              <thead><tr><th scope="col">Mês</th><th scope="col" className="r">Receitas</th>
                {fiscal ? <><th scope="col" className="r">Custeio</th><th scope="col" className="r">Investimentos</th></> : <th scope="col" className="r">Despesas</th>}
                <th scope="col" className="r">Sobrou</th></tr></thead>
              <tbody>
                {dados.meses.map((m) => (
                  <tr key={m.competencia} className={m.quantidade ? "clic" : "zero"} onClick={m.quantidade ? (e) => { if (!(e.target as HTMLElement).closest("button")) abrirDet(m.competencia); } : undefined}>
                    <td>{m.quantidade ? <button type="button" className="rl-linkbtn" onClick={() => abrirDet(m.competencia)} aria-label={`${mesLongo(m.competencia)}: abrir o mês no livro`}>{mesLongo(m.competencia)}</button> : mesLongo(m.competencia)}
                      <span className="sub">{m.quantidade} lançamento{m.quantidade === 1 ? "" : "s"}</span></td>
                    <td className="r">{brl(m.receitas)}</td>
                    {fiscal ? <><td className="r">{brl(m.custeio)}</td><td className="r">{brl(m.investimentos)}</td></> : <td className="r">{brl(m.despesas)}</td>}
                    <td className={`r${m.resultado < 0 ? " neg" : ""}`}><b>{brl(m.resultado)}</b></td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr><td>Total do período</td><td className="r">{brl(t.receitas)}</td>
                {fiscal ? <><td className="r">{brl(t.custeio)}</td><td className="r">{brl(t.investimentos)}</td></> : <td className="r">{brl(t.despesas)}</td>}
                <td className={`r${t.resultado < 0 ? " neg" : ""}`}>{brl(t.resultado)}</td></tr></tfoot>
            </table>
          </div>
          {rotuloCmp && tq && (
            <p style={{ margin: ".55rem 0 0", fontSize: ".8rem", color: "var(--text-muted)" }}>
              Em {rotuloCmp}: receitas {brl0(tq.receitas)}, despesas {brl0(tq.despesas)}, resultado {brl0(tq.resultado)}
              {(() => { const d = delta(t.resultado, tq.resultado, "sobe"); return d && !d.igual ? ` (${d.abs > 0 ? "+" : "−"}${brl0(Math.abs(d.abs))} agora)` : ""; })()}.
            </p>
          )}
        </section>
      )}

      {dados && t && (
        <section className="rl-painel rl-lv" aria-labelledby="rl-lv-livro">
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: ".5rem", marginBottom: ".6rem" }}>
            <h3 className="rl-tit" id="rl-lv-livro" style={{ margin: 0 }}>{mesDet ? `O livro de ${mesLongo(mesDet)}` : "O livro, lançamento a lançamento"}</h3>
            <button type="button" className="rl-linkbtn rl-noprint" style={{ color: "var(--text-accent)", fontWeight: 600, fontSize: ".8rem" }} onClick={livroPorConta}>
              <BookOpen size={14} aria-hidden /> Livro por conta bancária, com o saldo do extrato
            </button>
          </div>
          <div className="rl-tw rl-lv-rolo">
            <table className="fazenda-table rl-tab">
              <caption className="rl-sr">Livro caixa da atividade rural — {mesDet ? mesLongo(mesDet) : periodo.label}</caption>
              <thead><tr>
                <th scope="col">Data</th><th scope="col">Histórico</th><th scope="col">Documento</th>
                <th scope="col" className="r">Receita</th><th scope="col" className="r">Despesa</th><th scope="col" className="r">Saldo</th>
              </tr></thead>
              <tbody>
                {secoes.map((s) => (
                  <SecaoMes key={s.mes.competencia} secao={s} fiscal={fiscal} mostrarCabecalho={!mesDet} onAbrir={abrirLinha} />
                ))}
              </tbody>
              <tfoot><tr>
                <td colSpan={3}>{mesSel ? `Total de ${mesLongo(mesDet)}` : "Total do período"}</td>
                <td className="r">{brl(mesSel ? mesSel.receitas : t.receitas)}</td>
                <td className="r">{brl(mesSel ? mesSel.despesas : t.despesas)}</td>
                <td className={`r${(mesSel ? mesSel.resultado : t.resultado) < 0 ? " neg" : ""}`}>{brl(mesSel ? mesSel.resultado : t.resultado)}</td>
              </tr></tfoot>
            </table>
          </div>
          <p style={{ margin: ".5rem 0 0", fontSize: ".76rem", color: "var(--text-muted)" }}>
            Saldo = resultado acumulado no período (receitas − despesas), não o saldo do banco. Clique numa linha para ver o lançamento em Consultas.
          </p>
        </section>
      )}

      {dados && t && fiscal && !mesDet && (
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-lv-pres">
            <h3 className="rl-tit" id="rl-lv-pres">Resultado real × 20% da receita bruta</h3>
            <div className="rl-cmpbox">
              <div className={melhor === "real" ? "com" : undefined}><small>Resultado real (livro caixa)</small><b style={t.resultado < 0 ? { color: "var(--st-venc-fg)" } : undefined}>{brl0(t.resultado)}</b></div>
              <div className={melhor === "presumido" ? "com" : undefined}><small>20% da receita bruta</small><b>{brl0(dados.presumido_20 ?? 0)}</b></div>
            </div>
            <p style={{ margin: ".7rem 0 0", fontSize: ".86rem" }}>
              A base menor neste período é a <b>{melhor === "real" ? "do resultado real" : "dos 20% da receita"}</b>. A escolha é anual e tem consequências (prejuízo a compensar só existe no real): decida com o contador.
            </p>
          </section>
          {p && (
            <section className="rl-painel" aria-labelledby="rl-lv-ponte">
              <h3 className="rl-tit" id="rl-lv-ponte">Por que não bate com a DRE?</h3>
              <dl className="rl-ponte">
                <dt>Resultado da DRE (dia do pagamento, todos os centros)</dt><dd>{brl(p.resultado_dre)}</dd>
                <dt>+ Desgaste dos bens (a DRE desconta, o livro não)</dt><dd>{brl(p.depreciacao)}</dd>
                {Math.abs(p.resultado_baixas) >= 0.005 && <><dt>− Ganho ou perda na venda de bens (está na DRE, não no livro)</dt><dd>{brl(-p.resultado_baixas)}</dd></>}
                <dt>+ Funrural, Senar e descontos da venda (a DRE deduz; o livro usa a receita bruta)</dt><dd>{brl(p.deducoes)}</dd>
                <dt>− Investimentos pagos{p.venda_de_bens ? " (menos a venda de bens)" : ""} (o livro desconta no mês do pagamento)</dt><dd>{brl(-p.investimentos_liquidos)}</dd>
                <dt className="tot">= Resultado do livro caixa</dt><dd className="tot">{brl(p.reconstruido)}</dd>
              </dl>
              <Conferencia fecha={p.fecha} texto={p.fecha ? "A ponte entre a DRE e o livro caixa fecha no centavo." : `A ponte não fecha: ${brl(p.reconstruido)} × ${brl(p.resultado_livro)}. Avise o suporte.`} />
            </section>
          )}
        </div>
      )}

      {dados && fiscal && !mesDet && (dados.fora_do_livro?.grupos.length ?? 0) > 0 && (
        <section className="rl-painel" aria-labelledby="rl-lv-fora">
          <h3 className="rl-tit" id="rl-lv-fora">Fora do livro, por regra</h3>
          <p style={{ margin: "0 0 .6rem", fontSize: ".8rem", color: "var(--text-muted)" }}>Passaram no banco, mas não são receita nem despesa da atividade rural (ou ainda não têm conta da DRE).</p>
          {dados.fora_do_livro!.grupos.map((g) => (
            <div key={g.natureza} style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", padding: ".45rem 0", borderBottom: "1px solid var(--border)", fontSize: ".86rem" }}>
              <span>{g.rotulo}<span style={{ display: "block", fontSize: ".72rem", color: "var(--text-muted)" }}>{g.quantidade} lançamento{g.quantidade === 1 ? "" : "s"}</span></span>
              <span style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                {g.entradas ? <>entrou <b>{brl(g.entradas)}</b></> : null}{g.entradas && g.saidas ? <br /> : null}{g.saidas ? <>saiu <b>{brl(g.saidas)}</b></> : null}
              </span>
            </div>
          ))}
          {dados.fora_do_livro!.grupos.some((g) => g.natureza === "sem_conta" || g.natureza === "NAO_INFORMADA") && (
            <p style={{ margin: ".6rem 0 0", fontSize: ".82rem" }}>
              <button type="button" className="rl-linkbtn" style={{ color: "var(--text-accent)", fontWeight: 700 }} onClick={() => props.onIrRelatorio("dre_contas")}>
                <ExternalLink size={13} aria-hidden /> Classificar as contas
              </button>{" "}para elas entrarem (ou saírem com o motivo certo).
            </p>
          )}
        </section>
      )}

      <NotasMetodo titulo="Regra fiscal usada neste livro"
        entra={[
          ["Regime", "Sempre pelo dia do pagamento ou recebimento, com todos os centros do imóvel."],
          ["Receitas", fiscal ? "Leite pelo valor bruto (o Funrural/Senar retido não é despesa paga), venda de animais e de bens." : "Todo recebimento do período, pelo valor recebido."],
          ["Despesas de custeio", fiscal ? "Tudo o que foi pago para produzir, inclusive juros. Desconto por pagar adiantado reduz a despesa (conta o valor pago)." : "Todo pagamento do período, pelo valor pago."],
          ["Investimentos", fiscal ? "Bens, máquinas, benfeitorias e animais para o plantel: despesa no mês do pagamento, sem depreciação." : "Com as regras novas, separados do custeio."],
          ["Saldo", "Resultado acumulado no período, linha a linha — não é o saldo do banco (esse está em Consultas › Livro caixa, por conta)."],
        ]}
        naoEntra={fiscal ? [
          "Principal de financiamento (amortização) e entrada de empréstimo.",
          "Aporte e retirada de sócio, transferências entre contas, adiantamentos (vales).",
          "Lançamentos sem conta da DRE, até serem classificados.",
        ] : ["Nada fica de fora com as regras antigas: a separação fiscal chega com as regras novas."]} />
      {dados && t && !mesDet && (
        <Conferencia fecha={Math.abs(dados.meses.reduce((s, m) => s + m.resultado, 0) - t.resultado) < 0.02 && (!dados.linhas.length || Math.abs(dados.linhas[dados.linhas.length - 1].saldo - t.resultado) < 0.02)}
          texto={`A soma dos meses (${brl(dados.meses.reduce((s, m) => s + m.resultado, 0))}) e o saldo da última linha são o resultado do período.`} />
      )}
    </RelatorioShell>
  );
}

function SecaoMes({ secao, fiscal, mostrarCabecalho, onAbrir }: {
  secao: ReturnType<typeof secoesLivro>[number]; fiscal: boolean; mostrarCabecalho: boolean; onAbrir: (l: LinhaLivro) => void;
}) {
  const m = secao.mes;
  return (<>
    {mostrarCabecalho && <tr className="mes"><td colSpan={6}>{mesLongo(m.competencia)}</td></tr>}
    {secao.linhas.map((l, i) => (
      <tr key={`${l.id}-${i}`} className="clic" onClick={(e) => { if (!(e.target as HTMLElement).closest("button")) onAbrir(l); }}>
        <td style={{ whiteSpace: "nowrap" }}>{dmy(l.data)}</td>
        <td>
          <button type="button" className="rl-linkbtn" onClick={() => onAbrir(l)} aria-label={`${historicoDe(l)}, ${dmy(l.data)}: ver em Consultas`} style={{ fontWeight: 500 }}>{historicoDe(l)}</button>
          {fiscal && l.categoria && CATEGORIA[l.categoria] && <span className="cat">{CATEGORIA[l.categoria]}</span>}
          {l.conta && <span className="sub">{l.conta}</span>}
        </td>
        <td className="doc">{documentoDe(l)}</td>
        <td className="r">{l.receita ? brl(l.receita) : ""}</td>
        <td className="r">{l.despesa ? brl(l.despesa) : ""}</td>
        <td className={`r${l.saldo < 0 ? " neg" : ""}`}>{brl(l.saldo)}</td>
      </tr>
    ))}
    {mostrarCabecalho && <tr className="sub-mes"><td colSpan={3}>Total de {mesLongo(m.competencia)}{fiscal ? <span className="sub" style={{ fontWeight: 400 }}>custeio {brl(m.custeio)} · investimentos {brl(m.investimentos)}</span> : null}</td>
      <td className="r">{brl(m.receitas)}</td><td className="r">{brl(m.despesas)}</td><td className={`r${m.resultado < 0 ? " neg" : ""}`}>{brl(m.resultado)}</td></tr>}
  </>);
}
