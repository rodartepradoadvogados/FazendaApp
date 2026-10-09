"use client";
// Relatórios › Registros › Compra de sêmen — "Quanto custa cada prenhez?"
// As compras de sêmen do período (com a classificação da Fase A em cada uma)
// e, quando há dado do Reprodutivo, o custo do sêmen por prenhez: doses das
// inseminações já diagnosticadas × preço médio da dose comprada nos 12 meses ÷
// prenhezes confirmadas. Mantém a busca da tela anterior (touro, vendedor,
// documento) e a exportação. Números de GET /relatorio-compra-semen/resumo.
import { useEffect, useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { fetchResumoSemen } from "@/lib/apiRelatoriosLeite";
import { ESTADO_INICIAL, brl, deslocar, mesCurto, mesLongo, num, periodoDe, type Periodo } from "@/lib/relatorioContexto";
import { buscaGlobal, fraseSemen, porqueSemCustoPrenhez, type LinhaSemen, type RespostaSemen } from "@/lib/relatorioRegistros";
import type { RelatorioParaExportar } from "@/lib/export";
import { Conferencia, NotasMetodo, PainelGrafico, RelatorioShell, VazioQueEnsina, type EstadoTela, type KpiDef } from "./RelatorioShell";
import { Barras12Meses } from "./barras";
import { useContextoRelatorio, type TravasContexto } from "./useContextoRelatorio";
import type { PropsRelatorio } from "./comum";
import { CSS_LEITE_REGISTROS } from "./estilosLeite";
import { FormBusca, SeloNatureza, TabelaOrdenavel, useBuscaNaUrl, type Coluna } from "./registrosComum";

const NOME = "Compra de sêmen";
const PERGUNTA = "Quanto custa cada prenhez?";
const TRAVAS: TravasContexto = { reg: "comp", cmpOrcado: false, porque: "Compra de sêmen é pela data da nota; as inseminações, pela data do serviço." };
const dmy = (s: string) => s.split("-").reverse().join("/");

export default function CompraSemenView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, TRAVAS);
  const { periodo, comparacao, efetivo } = ctx;
  const [busca, mudarBusca] = useBuscaNaUrl();
  // Documento busca em todo o histórico; touro e vendedor filtram dentro do período.
  const global = buscaGlobal({ documento: busca.documento });
  const cmp = !global && comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const centroApi = global || efetivo.cc === "todos" ? null : efetivo.cc;
  const [tentativa, setTentativa] = useState(0);
  const [res, setRes] = useState<{ chave: string; a: RespostaSemen; b: RespostaSemen | null } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const chave = [global ? "" : periodo.cod, cmp?.cod, centroApi, busca.touro, busca.vendedor, busca.documento].join("|");

  useEffect(() => {
    let vivo = true;
    const ler = (p: Periodo, serie: number) => fetchResumoSemen({
      data_de: p.ini, data_ate: p.fim, centro_custo: centroApi, touro: busca.touro, vendedor: busca.vendedor, numero_documento: busca.documento, serie_meses: serie,
    });
    const atual: Periodo = global ? periodoDe(`l:2000-01-01~${hoje}`)! : periodo;
    Promise.all([ler(atual, global ? 0 : 12), cmp ? ler(cmp, 0) : Promise.resolve(null)])
      .then(([a, b]) => { if (vivo) { setRes({ chave, a, b }); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [chave, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps

  const r = res && res.chave === chave ? res.a : null;
  const rb = res && res.chave === chave ? res.b : null;
  const p = r?.prenhez, pb = rb?.prenhez, t = r?.totais, tb = rb?.totais;
  const temReproducao = !!p && p.inseminacoes > 0;
  const vazio = !!r && !r.linhas.length && !temReproducao;
  const estado: EstadoTela = !r && !erro ? "carregando" : erro && !r ? "erro" : vazio ? "vazio" : "ok";
  const porque = porqueSemCustoPrenhez(p);
  const quando = global ? "no histórico buscado" : periodo.label;

  const consultas = (l: LinhaSemen) => {
    if (!l.numero_lancamento) return;
    props.onConsultas({ de: "", ate: "", periodoPor: "competencia", origem: `${NOME} › ${l.touro_nome}`, documento: l.numero_lancamento } as Parameters<PropsRelatorio["onConsultas"]>[0]);
  };

  const kpiGasto: KpiDef | null = t ? { chave: "gasto", rotulo: "Gasto com sêmen", valor: t.gasto, cmp: tb?.gasto ?? null, formato: "brl0", bom: "neutro",
    sub: `${t.compras} compra${t.compras === 1 ? "" : "s"} no período`, onAbrir: () => props.onIrRelatorio("rel_dre", "CUSTO_VARIAVEL") } : null;
  const kpis: KpiDef[] = r && p && t ? (temReproducao && !global ? [
    { chave: "prenhez", rotulo: "Custo do sêmen por prenhez", valor: p.custo_por_prenhez, cmp: pb?.custo_por_prenhez ?? null, formato: "brl", bom: "desce",
      sub: porque ?? `${p.diagnosticadas} dose${p.diagnosticadas === 1 ? "" : "s"} diagnosticada${p.diagnosticadas === 1 ? "" : "s"} × ${brl(p.preco_dose.preco ?? 0)} (preço médio da dose${p.preco_dose.base === "historico" ? ", todo o histórico" : " em 12 meses"}) ÷ ${p.prenhezes} prenhez${p.prenhezes === 1 ? "" : "es"}` },
    { chave: "ia", rotulo: "Inseminações", valor: p.inseminacoes, cmp: pb?.inseminacoes ?? null, formato: "num", bom: "neutro",
      sub: p.aguardando_diagnostico ? `${p.aguardando_diagnostico} aguardando diagnóstico` : "todas já diagnosticadas" },
    { chave: "conc", rotulo: "Taxa de concepção", valor: p.taxa_concepcao_pct, cmp: pb?.taxa_concepcao_pct ?? null, formato: "pct", bom: "sobe",
      sub: `${p.prenhezes} prenhez${p.prenhezes === 1 ? "" : "es"} ÷ ${p.diagnosticadas} inseminação(ões) diagnosticada(s)` },
    kpiGasto!,
  ] : [
    kpiGasto!,
    { chave: "doses", rotulo: "Doses compradas", valor: t.doses, cmp: tb?.doses ?? null, formato: "num", bom: "neutro",
      sub: t.preco_medio_dose != null ? `${brl(t.preco_medio_dose)} por dose em média` : "sem compra" },
    { chave: "prenhez", rotulo: "Custo do sêmen por prenhez", valor: global ? null : p.custo_por_prenhez, formato: "brl", bom: "desce",
      sub: global ? "Na busca por documento não há período de inseminação" : porque ?? "" },
  ]) : [];

  const colunas: Coluna<LinhaSemen>[] = [
    { chave: "touro", rotulo: "Touro", valor: (l) => l.touro_nome, celula: (l) => <>{l.touro_nome}{l.numero_lancamento && <ExternalLink size={12} aria-hidden />}<small>{[l.naab, l.tipo === "sexado" ? "sexado" : "convencional"].filter(Boolean).join(" · ")}</small></> },
    { chave: "data", rotulo: "Data", valor: (l) => l.data_compra, celula: (l) => dmy(l.data_compra) },
    { chave: "doses", rotulo: "Doses", num: true, valor: (l) => l.doses },
    { chave: "dose", rotulo: "R$/dose", num: true, valor: (l) => l.valor_unitario, celula: (l) => brl(l.valor_unitario) },
    { chave: "total", rotulo: "Total", num: true, valor: (l) => l.valor_total, celula: (l) => brl(l.valor_total) },
    { chave: "vendedor", rotulo: "Vendedor", valor: (l) => l.vendedor || "" },
    { chave: "natureza", rotulo: "Classificação", valor: (l) => l.natureza_rotulo, celula: (l) => <SeloNatureza n={l.natureza} rotulo={l.natureza_rotulo} /> },
    { chave: "doc", rotulo: "Documento", opc: true, valor: (l) => l.numero_documento || "—" },
    { chave: "lanc", rotulo: "Lançamento", opc: true, valor: (l) => l.numero_lancamento || "—" },
    { chave: "centro", rotulo: "Centro de custo", opc: true, valor: (l) => l.centro_custo || "—" },
  ];

  const exportar = (): RelatorioParaExportar | null => r ? {
    titulo: NOME, pergunta: PERGUNTA,
    contexto: { periodo: global ? "todo o histórico (busca)" : periodo.label, comparacao: cmp?.label ?? null, regime: "pela data da nota", centro: centroApi ?? "todos os centros" },
    colunas: [{ header: "Touro", tipo: "texto" }, { header: "NAAB", tipo: "texto" }, { header: "Tipo", tipo: "texto" }, { header: "Doses", tipo: "num" },
      { header: "Valor/dose", tipo: "brl" }, { header: "Valor total", tipo: "brl" }, { header: "Data", tipo: "texto" }, { header: "Vendedor", tipo: "texto" },
      { header: "Classificação", tipo: "texto" }, { header: "Documento", tipo: "texto" }, { header: "Lançamento", tipo: "texto" }, { header: "Centro de custo", tipo: "texto" }],
    linhas: [
      ...r.linhas.map((l) => ({ valores: [l.touro_nome, l.naab, l.tipo === "sexado" ? "Sexado" : "Convencional", l.doses, l.valor_unitario, l.valor_total, dmy(l.data_compra), l.vendedor, l.natureza_rotulo, l.numero_documento, l.numero_lancamento, l.centro_custo] })),
      { valores: ["Total", null, null, r.totais.doses, r.totais.preco_medio_dose, r.totais.gasto, null, null, null, null, null, null], total: true },
    ],
    nomeArquivoBase: "compra_semen",
    notas: [
      !global && r.prenhez.inseminacoes ? `Inseminações: ${r.prenhez.inseminacoes} (${r.prenhez.diagnosticadas} diagnosticadas, ${r.prenhez.prenhezes} prenhezes). Custo do sêmen por prenhez: ${r.prenhez.custo_por_prenhez != null ? brl(r.prenhez.custo_por_prenhez) : "—"}.` : "",
      r.prenhez.preco_dose.preco != null ? `Preço médio da dose: ${brl(r.prenhez.preco_dose.preco)} (${r.prenhez.preco_dose.base === "historico" ? "todas as compras" : "compras dos 12 meses anteriores"}).` : "",
    ].filter(Boolean),
  } : null;

  const vazioUi = (
    <VazioQueEnsina titulo={global ? "Nenhuma compra com esse documento" : `Nenhuma compra de sêmen nem inseminação em ${periodo.label}`}
      texto={global ? "A busca por documento olha todo o histórico. Confira o número ou limpe a busca." : "O custo por prenhez precisa das inseminações (Reprodutivo) e de compras de sêmen para saber o preço da dose."}
      itens={global ? [] : [
        { texto: "Compra de sêmen registrada", pronto: false, acao: <a href="/lancamentos?ir=comprar_semen">Registrar a compra de sêmen</a> },
        { texto: "Inseminações lançadas no período", pronto: false, acao: <a href="/reproducao">Abrir o Reprodutivo</a> },
      ]}
      acoes={global ? <button type="button" className="rl-btn" onClick={() => mudarBusca({})}>Limpar a busca</button>
        : <button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>} />
  );

  const serie = r?.serie ?? [];
  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Registros" nome={NOME} pergunta={PERGUNTA} onIrGrupo={props.onIrGrupo}
      estado={estado} erro={erro} onTentarDeNovo={() => { setErro(null); setTentativa((x) => x + 1); }} vazio={vazioUi}
      frase={r && !global ? fraseSemen({ periodo, r, brl }) : []} kpis={kpis} exportar={exportar}
      avisos={<>
        <style>{CSS_LEITE_REGISTROS}</style>
        <FormBusca valor={busca} onBuscar={mudarBusca}
          campos={[{ chave: "touro", rotulo: "Touro", dica: "ex.: Coors" }, { chave: "vendedor", rotulo: "Vendedor", dica: "ex.: ABS" }, { chave: "documento", rotulo: "Nº do documento" }]}
          nota={global ? <>Busca por documento em <b>todo o histórico</b> e em todos os centros.</> : "Touro e vendedor filtram as compras do período; o documento busca em todo o histórico."} />
      </>}>
      {r && (<>
        {!global && serie.some((m) => m.custo_por_prenhez != null) && (
          <PainelGrafico titulo="Custo do sêmen por prenhez, 12 meses"
            tabela={{ cabecalho: ["Mês", "Inseminações", "Prenhezes", "R$ por prenhez"], linhas: serie.map((m) => [mesCurto(m.competencia), String(m.inseminacoes), String(m.prenhezes), m.custo_por_prenhez != null ? brl(m.custo_por_prenhez) : "—"]) }}>
            <Barras12Meses pontos={serie.map((m) => ({ comp: m.competencia, valor: m.custo_por_prenhez }))} nome="Custo por prenhez" fmt={(v) => brl(v)}
              descricao={`Custo do sêmen por prenhez por mês, ${mesCurto(serie[0].competencia)} a ${mesCurto(serie[serie.length - 1].competencia)}.`} />
          </PainelGrafico>
        )}
        <section className="rl-painel" aria-labelledby="rl-sm-comp">
          <h3 className="rl-tit" id="rl-sm-comp">Compras de sêmen · {global ? "busca" : periodo.curto}</h3>
          <TabelaOrdenavel titulo={`Compras de sêmen — ${quando}`} colunas={colunas} linhas={r.linhas} chaveLinha={(l, i) => `${l.data_compra}-${l.touro_nome}-${i}`}
            onAbrir={consultas} rotuloAbrir={(l) => (l.numero_lancamento ? `${l.touro_nome}: ver o lançamento ${l.numero_lancamento} em Consultas` : `${l.touro_nome}: sem lançamento financeiro`)}
            vazio="Nenhuma compra de sêmen no período (as doses usadas vêm do botijão)."
            rodape={r.linhas.length ? <tr><td colSpan={2}>Total</td><td className="r">{r.totais.doses}</td><td className="r">{r.totais.preco_medio_dose != null ? brl(r.totais.preco_medio_dose) : "—"}</td><td className="r">{brl(r.totais.gasto)}</td><td colSpan={5} /></tr> : undefined} />
          <p className="rl-hint">Clique no touro para abrir o lançamento em Consultas. A classificação vem da Fase A: sêmen é custeio (operacional, linha de reprodução).</p>
        </section>
        {!global && (
          <section className="rl-painel" aria-labelledby="rl-sm-uso">
            <h3 className="rl-tit" id="rl-sm-uso">Uso por mês (Reprodutivo)</h3>
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Inseminações e prenhezes por mês</caption>
                <thead><tr><th scope="col">Mês</th><th scope="col" className="r">Inseminações</th><th scope="col" className="r rl-opc">Diagnosticadas</th><th scope="col" className="r">Prenhezes</th>
                  <th scope="col" className="r rl-opc">Concepção</th><th scope="col" className="r">R$ por prenhez</th></tr></thead>
                <tbody>{serie.map((m) => (
                  <tr key={m.competencia}><td>{mesLongo(m.competencia)}</td><td className="r">{m.inseminacoes || "—"}</td><td className="r rl-opc">{m.diagnosticadas || "—"}</td>
                    <td className="r">{m.prenhezes || "—"}</td><td className="r rl-opc">{m.taxa_concepcao_pct != null ? `${num(m.taxa_concepcao_pct, 0)}%` : "—"}</td>
                    <td className="r">{m.custo_por_prenhez != null ? brl(m.custo_por_prenhez) : "—"}</td></tr>
                ))}</tbody>
                {p && periodo.tipo !== "m" && <tfoot><tr><td>{periodo.label}</td><td className="r">{p.inseminacoes}</td><td className="r rl-opc">{p.diagnosticadas}</td><td className="r">{p.prenhezes}</td>
                  <td className="r rl-opc">{p.taxa_concepcao_pct != null ? `${num(p.taxa_concepcao_pct, 0)}%` : "—"}</td><td className="r">{p.custo_por_prenhez != null ? brl(p.custo_por_prenhez) : "—"}</td></tr></tfoot>}
              </table>
            </div>
            {porque && <p className="rl-hint">Sem custo por prenhez no período: {porque}</p>}
          </section>
        )}
      </>)}
      <NotasMetodo titulo="Como o custo por prenhez é calculado"
        entra={[
          ["Sêmen usado", "Uma dose por inseminação (IA/IATF com sêmen convencional ou sexado), pela data do serviço. Monta natural não gasta dose."],
          ["Preço da dose", "Média das doses compradas nos 12 meses antes do fim do período (o botijão mistura compras); sem compra na janela, a média de todas as compras."],
          ["Prenhezes", "Diagnóstico positivo no Reprodutivo. Inseminação ainda sem diagnóstico fica fora da conta (senão o custo subiria só porque o toque não aconteceu)."],
          ["Compras", "Pela data da nota; o centro é o do lançamento financeiro gerado."],
        ]}
        naoEntra={["Hormônios do protocolo (estão em Reprodução na DRE, mas não aqui).", "Mão de obra do inseminador e o nitrogênio do botijão."]} />
      {r && t && (
        <Conferencia fecha={Math.abs(r.linhas.reduce((s, l) => s + l.valor_total, 0) - t.gasto) < 0.02}
          texto={`As compras listadas somam ${brl(t.gasto)} (${t.doses} doses)${p?.custo_por_prenhez != null ? `; ${p.diagnosticadas} doses × ${brl(p.preco_dose.preco ?? 0)} ÷ ${p.prenhezes} prenhezes = ${brl(p.custo_por_prenhez)}` : ""}.`} />
      )}
    </RelatorioShell>
  );
}
