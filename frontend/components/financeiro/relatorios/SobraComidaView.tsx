"use client";
// Relatórios › Leite › Sobra da comida por vaca (RMCA) — "Quanto sobra da comida por vaca?"
// Receita do leite menos custo com alimentação, total e por vaca em lactação
// por dia, comida ÷ receita (%), 12 meses (receita × comida por vaca/dia; a
// distância é a sobra), gerencial × físico numa tabela, por lote e por mês.
// Números de GET /financeiro/rmca-vaca, que parte do MESMO GET /financeiro/rmca
// da tela anterior (convenção: receita BRUTA, a líquida ao lado).
// Régua de referência: só se GET /financeiro/reguas-referencia liberar a régua
// ("publicada", faixa válida, aceite feito, dentro da validade) — faixa cinza
// neutra, a palavra "referência", sem semáforo nem meta (parecer jurídico 6.3).
// A régua nunca sai na exportação nem na impressão (parecer 6.2: exportar com
// réguas só com autorização expressa — aqui o relatório sai só com os dados da fazenda).
import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Info } from "lucide-react";
import { fetchReguasReferenciaOpcional, fetchRmcaVaca } from "@/lib/apiRelatoriosLeite";
import { ESTADO_INICIAL, REGIME_NOME, brl, deslocar, mesCurto, mesLongo, num, pct } from "@/lib/relatorioContexto";
import { fraseRmca, reguaVisivel, serieRmca, temPorVaca, temRmca, type ReguaVisivel, type RespostaRmcaVaca } from "@/lib/relatorioLeite";
import type { RelatorioParaExportar } from "@/lib/export";
import {
  Conferencia, NotasMetodo, PainelGrafico, RelatorioShell, VazioQueEnsina, type EstadoTela, type KpiDef,
} from "./RelatorioShell";
import { GraficoPrecoCusto, LegendaPrecoCusto, type NomesDuasLinhas } from "./graficos";
import { useContextoRelatorio, useDetalheNaUrl, type TravasContexto } from "./useContextoRelatorio";
import { useRegrasV2Estado, type PropsRelatorio } from "./comum";
import { CSS_LEITE_REGISTROS } from "./estilosLeite";
import RmcaSimulador from "./RmcaSimulador";

const NOME = "Sobra da comida por vaca";
const PERGUNTA = "Quanto sobra da comida por vaca?";
const TRAVAS: TravasContexto = {
  reg: "comp", cc: "todos", cmpOrcado: false,
  porque: "O RMCA é pelo mês do gasto e da fazenda inteira — as contas de leite e de alimentação marcadas em Parâmetros financeiros, como na tela anterior.",
};
const NOMES_GRAFICO: NomesDuasLinhas = { preco: "Receita do leite/vaca/dia", custo: "Comida/vaca/dia", sobra: "Sobra da comida", falta: "Falta", sufixo: "/vaca/dia" };
const ROTEIRO: [string, string][] = [
  ["Versão gerencial", "Em Parâmetros financeiros › Conta gerencial, marque a(s) conta(s) de receita da venda do leite e as de despesa de alimentação (ração, silagem, sal mineral). O gerencial soma os lançamentos dessas contas no período."],
  ["Versão física", "Em Configurações › Cadastro › Estoque › Itens, marque na coluna RMCA os produtos que são alimento. O físico soma o que a Alimentação baixou do estoque no período × o preço do item."],
  ["Por que duas versões", "O gerencial é o que foi lançado (pode incluir compra para estoque); o físico é o consumo do período. A diferença costuma vir de estoque, sobra no cocho e perdas de silagem."],
];

/** Régua cinza: trilho, faixa de referência e o marcador da fazenda (sem cor de juízo). */
function ReguaReferencia({ r, valor }: { r: ReguaVisivel; valor: number | null }) {
  const W = 320, mn = Math.min(r.min, valor ?? r.min) - 10, mx = Math.max(r.max, valor ?? r.max) + 10;
  const x = (v: number) => 8 + ((v - mn) / (mx - mn || 1)) * (W - 16);
  const fmt = (v: number) => `${num(v, 0)}${r.unidade === "%" ? "%" : ` ${r.unidade}`}`;
  const venc = r.venceEm ? r.venceEm.split("-").reverse().join("/") : null;
  return (
    <div className="rl-regua">
      <svg viewBox={`0 0 ${W} 46`} role="img" aria-label={`${r.nome}: faixa de referência de mercado ${fmt(r.min)} a ${fmt(r.max)}${valor != null ? `; fazenda no período ${num(valor, 1)}%` : ""}. Referência, não é meta.`}>
        <rect className="trilho" x={8} y={20} width={W - 16} height={10} rx={2} />
        <rect className="faixa" x={x(r.min)} y={20} width={x(r.max) - x(r.min)} height={10} />
        <text x={x(r.min)} y={44} textAnchor="middle">{fmt(r.min)}</text>
        <text x={x(r.max)} y={44} textAnchor="middle">{fmt(r.max)}</text>
        {valor != null && <path className="marca" d={`M${x(valor) - 6} 6 L${x(valor) + 6} 6 L${x(valor)} 17 Z`} />}
      </svg>
      <div className="rl-leg" style={{ marginTop: 0 }}>
        <span><i style={{ background: "color-mix(in srgb,var(--text) 22%,var(--surface))" }} />Faixa de referência de mercado</span>
        <span><svg width="12" height="10" aria-hidden><path d="M0 0 L12 0 L6 10 Z" style={{ fill: "var(--text)" }} /></svg>Fazenda no período</span>
        {r.fidedignidade && <span className="rl-selo">confiabilidade {r.fidedignidade}</span>}
        {venc && <span>válida até {venc}</span>}
      </div>
      <p className="rl-hint" style={{ margin: 0 }}>Estimativa de mercado compilada pelo CowData: é referência, não é meta nem recomendação. Fontes e método em Réguas de referência.</p>
    </div>
  );
}

export default function SobraComidaView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const regras = useRegrasV2Estado();
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, TRAVAS);
  const { periodo, comparacao } = ctx;
  const cmp = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const rotuloCmp = cmp ? comparacao!.rotulo : null;
  const [det, abrirDet] = useDetalheNaUrl("det");
  const [tentativa, setTentativa] = useState(0);
  const [res, setRes] = useState<{ chave: string; a: RespostaRmcaVaca; b: RespostaRmcaVaca | null } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [reguas, setReguas] = useState<unknown>(null);
  const chave = [periodo.cod, cmp?.cod].join("|");

  useEffect(() => {
    let vivo = true;
    Promise.all([
      fetchRmcaVaca({ data_inicio: periodo.ini, data_fim: periodo.fim, serie_meses: 12 }),
      cmp ? fetchRmcaVaca({ data_inicio: cmp.ini, data_fim: cmp.fim, serie_meses: 0 }) : Promise.resolve(null),
    ]).then(([a, b]) => { if (vivo) { setRes({ chave, a, b }); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [chave, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    let vivo = true;
    fetchReguasReferenciaOpcional().then((r) => { if (vivo) setReguas(r); });
    return () => { vivo = false; };
  }, []);

  const r = res && res.chave === chave ? res.a : null;
  const rb = res && res.chave === chave ? res.b : null;
  const a = r?.atual ?? null, b = rb?.atual ?? null;
  const porVaca = temPorVaca(a);
  const estado: EstadoTela = (!r && !erro) ? "carregando" : erro && !r ? "erro" : !temRmca(r) ? "vazio" : "ok";
  const regua = useMemo(() => reguaVisivel(reguas, "comida_receita", hoje), [reguas, hoje]);
  const pontos = useMemo(() => serieRmca(r), [r]);
  const contasCusto = r?.contas_custo_codigos ?? [];
  const contasLeite = r?.contas_receita_codigos ?? [];

  const consultas = (conta: { codigo: string; nome: string } | null, origem: string) => props.onConsultas({
    de: periodo.ini, ate: periodo.fim, periodoPor: "competencia", origem: `${NOME} › ${origem}`,
    ...(conta ? { conta: conta.codigo, contaNome: conta.nome } : {}),
  });
  const abrirContas = (tipo: "comida" | "leite") => {
    const lista = tipo === "comida" ? contasCusto : contasLeite;
    if (lista.length === 1) consultas(lista[0], tipo === "comida" ? "Comida" : "Receita do leite");
    else abrirDet(tipo);
  };

  const kpis: KpiDef[] = a && r && temRmca(r) ? (porVaca ? [
    { chave: "rmca_vd", rotulo: "Sobra da comida por vaca/dia", valor: a.rmca_vaca_dia, cmp: b?.rmca_vaca_dia ?? null, formato: "brl", bom: "sobe", negativoEmVermelho: true,
      sub: `Receita do leite − comida, por vaca em lactação por dia · ${num(a.vacas_media ?? 0, 0)} vacas em média, ${a.dias} dias`, onAbrir: () => abrirContas("comida") },
    { chave: "rec_vd", rotulo: "Receita do leite por vaca/dia", valor: a.receita_vaca_dia, cmp: b?.receita_vaca_dia ?? null, formato: "brl", bom: "sobe",
      sub: a.litros_vaca_dia != null && r.preco_bruto_l != null ? `${num(a.litros_vaca_dia, 1)} L × ${brl(r.preco_bruto_l)} (bruto)` : "receita bruta do leite", onAbrir: () => abrirContas("leite") },
    { chave: "com_vd", rotulo: "Comida por vaca/dia", valor: a.comida_vaca_dia, cmp: b?.comida_vaca_dia ?? null, formato: "brl", bom: "desce",
      sub: "Todas as contas de alimentação (inclui recria e secas)", onAbrir: () => abrirContas("comida") },
    { chave: "pct", rotulo: "Comida ÷ receita do leite", valor: a.comida_receita_pct, cmp: b?.comida_receita_pct ?? null, formato: "pct", bom: "desce",
      sub: regua ? `Referência de mercado ${num(regua.min, 0)}–${num(regua.max, 0)}% (não é meta)` : a.comida_receita_liquida_pct != null ? `Sobre a receita líquida: ${num(a.comida_receita_liquida_pct, 1)}%` : "Sobre a receita bruta do leite" },
  ] : [
    { chave: "rmca", rotulo: "Sobra da comida (RMCA)", valor: a.rmca, cmp: b?.rmca ?? null, formato: "brl0", bom: "sobe", negativoEmVermelho: true, sub: "Receita do leite − comida no período" },
    { chave: "rec", rotulo: "Receita do leite", valor: a.receita_bruta, cmp: b?.receita_bruta ?? null, formato: "brl0", bom: "sobe", sub: "Bruta (convenção do indicador)", onAbrir: () => abrirContas("leite") },
    { chave: "com", rotulo: "Comida", valor: a.comida, cmp: b?.comida ?? null, formato: "brl0", bom: "desce", sub: "Contas de alimentação", onAbrir: () => abrirContas("comida") },
    { chave: "pct", rotulo: "Comida ÷ receita do leite", valor: a.comida_receita_pct, cmp: b?.comida_receita_pct ?? null, formato: "pct", bom: "desce",
      sub: regua ? `Referência de mercado ${num(regua.min, 0)}–${num(regua.max, 0)}% (não é meta)` : "Sobre a receita bruta do leite" },
  ]) : [];

  const descricaoGrafico = (() => {
    const vs = pontos.filter((p) => p.preco != null && p.custo != null);
    if (!vs.length) return "Sem meses com vacas controladas e receita do leite para desenhar o gráfico.";
    const u = vs[vs.length - 1];
    return `Receita do leite e comida por vaca em lactação por dia, ${mesCurto(pontos[0].comp)} a ${mesCurto(pontos[pontos.length - 1].comp)}. Em ${mesCurto(u.comp)}: receita ${brl(u.preco!)}, comida ${brl(u.custo!)}.`;
  })();

  const exportar = (): RelatorioParaExportar | null => {
    if (!r || !a) return null;
    return {
      titulo: NOME, pergunta: PERGUNTA,
      contexto: { periodo: periodo.label, comparacao: cmp?.label ?? null, regime: REGIME_NOME.comp, centro: "todos os centros" },
      colunas: [{ header: "Mês", tipo: "texto" }, { header: "Vacas (média/dia)", tipo: "num" }, { header: "Receita/vaca/dia", tipo: "brl" },
        { header: "Comida/vaca/dia", tipo: "brl" }, { header: "Sobra/vaca/dia", tipo: "brl" }, { header: "Comida ÷ receita", tipo: "pct" }, { header: "RMCA do mês", tipo: "brl" }],
      linhas: [
        ...r.serie.map((m) => ({ valores: [mesLongo(m.competencia), m.vacas_media, m.receita_vaca_dia, m.comida_vaca_dia, m.rmca_vaca_dia, m.comida_receita_pct, m.rmca] })),
        { valores: [`Período: ${periodo.label}`, a.vacas_media, a.receita_vaca_dia, a.comida_vaca_dia, a.rmca_vaca_dia, a.comida_receita_pct, a.rmca], total: true },
      ],
      nomeArquivoBase: "sobra_da_comida_rmca",
      notas: [
        `Receita do leite (bruta): ${brl(a.receita_bruta)}; comida: ${brl(a.comida)}; RMCA: ${brl(a.rmca)}.`,
        a.receita_liquida != null ? `Sobre a receita líquida de Funrural/Senar e descontos (${brl(a.receita_liquida)}): RMCA de ${brl(a.rmca_liquida ?? 0)}.` : "",
        `Físico (consumo registrado na Alimentação × preço do estoque): comida ${brl(r.fisico.comida)}, RMCA ${brl(r.fisico.rmca)}.`,
        "Vaca em lactação no mês = teve Controle leiteiro naquele mês; por vaca/dia = ÷ (vacas × dias).",
        "Este arquivo traz só os dados da fazenda (sem réguas de referência).",
      ].filter(Boolean),
    };
  };

  const vazioUi = (
    <VazioQueEnsina titulo={`Sem receita do leite nem comida em ${periodo.label}`}
      texto="O RMCA precisa das contas de leite e de alimentação marcadas e de lançamentos no período. Veja o que falta:"
      itens={[
        { texto: "Contas da venda do leite marcadas", pronto: (r?.contas_receita.length ?? 0) > 0, acao: <a href="/parametros?sub=financeiro&pf=gerenciais">Marcar em Parâmetros financeiros › Conta gerencial</a> },
        { texto: "Contas de alimentação marcadas", pronto: (r?.contas_custo.length ?? 0) > 0, acao: <a href="/parametros?sub=financeiro&pf=gerenciais">Marcar em Parâmetros financeiros › Conta gerencial</a> },
        { texto: "Lançamentos de leite e de comida no período", pronto: false, acao: <a href="/financeiro?sub=a_receber">Lançar o recebimento do laticínio</a> },
      ]}
      acoes={<button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: deslocar(periodo, -1).cod })}>Ver o período anterior</button>} />
  );

  // Nível 2: as contas de uma das pontas (drill até Consultas, conta a conta).
  const nivel = det === "comida" || det === "leite" ? det : null;
  const contasNivel = nivel === "comida" ? contasCusto : contasLeite;

  const t3 = (g: number | null, f: number | null) => (
    <><td className="r">{g == null ? "—" : <span className={g < 0 ? "neg" : undefined}>{brl(g)}</span>}</td><td className="r">{f == null ? "—" : <span className={f < 0 ? "neg" : undefined}>{brl(f)}</span>}</td>
      <td className="r mut">{g == null || f == null ? "—" : `${g - f > 0 ? "+" : g - f < 0 ? "−" : ""}${brl(Math.abs(g - f))}`}</td></>
  );

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Leite" nome={NOME} pergunta={PERGUNTA} onIrGrupo={props.onIrGrupo}
      niveis={nivel ? [{ rotulo: nivel === "comida" ? "Contas de alimentação" : "Contas da venda do leite" }] : []} onVoltarNivel={() => abrirDet("")}
      estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => { setErro(null); setTentativa((t) => t + 1); }} vazio={vazioUi}
      frase={r && !nivel ? fraseRmca({ periodo, r, rb, rotuloCmp, brl }) : []} kpis={nivel ? undefined : kpis} exportar={exportar}
      avisos={<>
        <style>{CSS_LEITE_REGISTROS}</style>
        {r && (r.avisos.length > 0 || !r.configurado) && (
          <div className="rl-aviso" role="status"><Info size={18} aria-hidden /><div>
            {!r.configurado && <p style={{ margin: 0 }}>Falta marcar {r.contas_receita.length ? "as contas de alimentação" : "as contas da venda do leite"} em <a href="/parametros?sub=financeiro&pf=gerenciais">Parâmetros financeiros › Conta gerencial</a>.</p>}
            {r.avisos.map((x) => <p key={x} style={{ margin: 0 }}>{x} <a href="/lancamentos?sub=controle">Lançar o controle leiteiro</a>.</p>)}
          </div></div>
        )}
      </>}>
      {r && a && nivel && (
        <section className="rl-painel" aria-labelledby="rl-rm-contas">
          <h3 className="rl-tit" id="rl-rm-contas">{nivel === "comida" ? "Contas de alimentação" : "Contas da venda do leite"} · {periodo.curto}</h3>
          <p className="rl-hint" style={{ marginTop: 0 }}>
            {nivel === "comida" ? `Somam ${brl(a.comida)} de comida no período` : `Somam ${brl(a.receita_bruta)} de receita bruta no período`}. Abra cada conta em Consultas, já filtrada pelo mês do gasto.
          </p>
          {contasNivel.length ? contasNivel.map((c) => (
            <div key={c.codigo} className="rl-linha-valor">
              <span>{c.nome}<small>{c.codigo}</small></span>
              <button type="button" className="rl-btn" onClick={() => consultas(c, nivel === "comida" ? "Comida" : "Receita do leite")}><ExternalLink size={14} aria-hidden /> Ver em Consultas</button>
            </div>
          )) : <p className="rl-hint">Nenhuma conta marcada. <a href="/parametros?sub=financeiro&pf=gerenciais">Marcar em Parâmetros financeiros</a>.</p>}
        </section>
      )}
      {r && a && !nivel && (<>
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-rm-gf">
            <h3 className="rl-tit" id="rl-rm-gf">Gerencial × físico, {porVaca ? "por vaca/dia" : "no período"}</h3>
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Gerencial × físico — {periodo.label}</caption>
                <thead><tr><th scope="col">{porVaca ? "Por vaca/dia" : "No período"}</th><th scope="col" className="r">Gerencial</th><th scope="col" className="r">Físico</th><th scope="col" className="r">Diferença</th></tr></thead>
                <tbody>
                  <tr className="clic" onClick={(ev) => { if (!(ev.target as HTMLElement).closest("button")) abrirContas("leite"); }}>
                    <td><button type="button" className="rl-linkbtn" onClick={() => abrirContas("leite")} aria-label="Receita do leite: abrir as contas">Receita do leite<ExternalLink size={13} aria-hidden /></button><small>bruta, a mesma nas duas versões</small></td>
                    {t3(porVaca ? a.receita_vaca_dia : a.receita_bruta, porVaca ? r.fisico.receita_vaca_dia : r.fisico.receita_bruta)}
                  </tr>
                  <tr className="clic" onClick={(ev) => { if (!(ev.target as HTMLElement).closest("button")) abrirContas("comida"); }}>
                    <td><button type="button" className="rl-linkbtn" onClick={() => abrirContas("comida")} aria-label="Comida: abrir as contas">Comida<ExternalLink size={13} aria-hidden /></button><small>gerencial = lançamentos; físico = consumo registrado</small></td>
                    {t3(porVaca ? a.comida_vaca_dia : a.comida, porVaca ? r.fisico.comida_vaca_dia : r.fisico.comida)}
                  </tr>
                  <tr className="tot"><td>Sobra da comida</td>{t3(porVaca ? a.rmca_vaca_dia : a.rmca, porVaca ? r.fisico.rmca_vaca_dia : r.fisico.rmca)}</tr>
                  {a.rmca_liquida != null && (
                    <tr><td>Sobra sobre a receita líquida<small>receita − Funrural/Senar e descontos da nota</small></td>
                      {t3(porVaca ? a.rmca_liquida_vaca_dia : a.rmca_liquida, porVaca ? r.fisico.rmca_liquida_vaca_dia : r.fisico.rmca_liquida)}</tr>
                  )}
                </tbody>
              </table>
            </div>
            <p className="rl-hint">A diferença na comida costuma vir de compras para estoque (entram no mês da compra no gerencial), sobra no cocho e perdas de silagem.{!r.fisico.itens.length ? " Sem consumo registrado pela Alimentação no período: o físico fica zerado." : ""}</p>
          </section>
          <section className="rl-painel" aria-labelledby="rl-rm-pct">
            <h3 className="rl-tit" id="rl-rm-pct">Comida ÷ receita do leite</h3>
            <p style={{ margin: "0 0 .5rem", fontSize: "1.6rem", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
              {a.comida_receita_pct != null ? `${num(a.comida_receita_pct, 1)}%` : "—"}
              <span style={{ fontSize: ".8rem", fontWeight: 600, color: "var(--text-muted)", marginLeft: ".4rem" }}>sobre a receita bruta</span>
            </p>
            {a.comida_receita_liquida_pct != null && <p className="rl-hint" style={{ marginTop: 0 }}>Sobre a receita líquida: {num(a.comida_receita_liquida_pct, 1)}%.</p>}
            {regua && <ReguaReferencia r={regua} valor={a.comida_receita_pct} />}
            <p className="rl-hint">Convenção do indicador: receita BRUTA do leite; a líquida aparece ao lado. Meta própria (se houver) mora em Parâmetros financeiros.</p>
          </section>
        </div>
        <PainelGrafico titulo="Receita × comida por vaca/dia, 12 meses · a distância é a sobra"
          legenda={<LegendaPrecoCusto textos={["Receita do leite por vaca/dia", "Comida por vaca/dia", "Sobra da comida", "Falta (comida acima da receita)"]} />}
          tabela={{ cabecalho: ["Mês", "Receita/vaca/dia", "Comida/vaca/dia", "Sobra/vaca/dia"], linhas: r.serie.map((m) => [
            mesCurto(m.competencia), m.receita_vaca_dia != null ? brl(m.receita_vaca_dia) : "—", m.comida_vaca_dia != null ? brl(m.comida_vaca_dia) : "—", m.rmca_vaca_dia != null ? brl(m.rmca_vaca_dia) : "—",
          ]) }}>
          <GraficoPrecoCusto pontos={pontos} descricao={descricaoGrafico} nomes={NOMES_GRAFICO} />
        </PainelGrafico>
        <section className="rl-painel" aria-labelledby="rl-rm-mes">
          <h3 className="rl-tit" id="rl-rm-mes">Mês a mês</h3>
          <div className="rl-tw">
            <table className="fazenda-table rl-tab">
              <caption className="rl-sr">Sobra da comida mês a mês</caption>
              <thead><tr><th scope="col">Mês</th><th scope="col" className="r">Vacas/dia</th><th scope="col" className="r rl-opc">Leite/vaca/dia</th><th scope="col" className="r">Receita/vaca/dia</th>
                <th scope="col" className="r">Comida/vaca/dia</th><th scope="col" className="r">Sobra/vaca/dia</th><th scope="col" className="r rl-opc">Comida ÷ receita</th><th scope="col" className="r rl-opc">RMCA do mês</th></tr></thead>
              <tbody>{r.serie.map((m) => {
                const atual = `m:${m.competencia}` === periodo.cod;
                return (
                  <tr key={m.competencia} className="clic" aria-current={atual ? "true" : undefined} style={atual ? { fontWeight: 700 } : undefined}
                    onClick={(ev) => { if (!(ev.target as HTMLElement).closest("button")) ctx.mudar({ per: `m:${m.competencia}` }); }}>
                    <td><button type="button" className="rl-linkbtn" onClick={() => ctx.mudar({ per: `m:${m.competencia}` })} aria-label={`Abrir ${mesLongo(m.competencia)}`}>{mesLongo(m.competencia)}</button></td>
                    <td className="r">{m.vacas_media ? num(m.vacas_media, 0) : "—"}</td>
                    <td className="r rl-opc">{m.litros_vaca_dia != null ? `${num(m.litros_vaca_dia, 1)} L` : "—"}</td>
                    <td className="r">{m.receita_vaca_dia != null ? brl(m.receita_vaca_dia) : "—"}</td>
                    <td className="r">{m.comida_vaca_dia != null ? brl(m.comida_vaca_dia) : "—"}</td>
                    <td className="r">{m.rmca_vaca_dia != null ? <span className={m.rmca_vaca_dia < 0 ? "neg" : undefined}>{brl(m.rmca_vaca_dia)}</span> : "—"}</td>
                    <td className="r rl-opc">{m.comida_receita_pct != null ? pct(m.comida_receita_pct / 100) : "—"}</td>
                    <td className="r rl-opc">{Math.abs(m.receita_bruta) + Math.abs(m.comida) >= 0.005 ? <span className={m.rmca < 0 ? "neg" : undefined}>{brl(m.rmca, 0)}</span> : "—"}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
          <p className="rl-hint">Clique num mês para abri-lo. Mês sem Controle leiteiro fica sem o “por vaca” (nunca zero inventado).</p>
        </section>
        <section className="rl-painel" aria-labelledby="rl-rm-lote">
          <h3 className="rl-tit" id="rl-rm-lote" style={{ display: "flex", gap: ".5rem", justifyContent: "space-between", flexWrap: "wrap" }}>Por lote · {periodo.curto} <span className="rl-selo" title="Leite do controle leiteiro × preço médio do leite; comida pelo consumo registrado por lote">estimativa</span></h3>
          {r.por_lote.length ? (<>
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Sobra da comida por lote</caption>
                <thead><tr><th scope="col">Lote</th><th scope="col" className="r">Vacas</th><th scope="col" className="r">Leite/vaca/dia</th><th scope="col" className="r">Receita/vaca/dia</th><th scope="col" className="r">Comida/vaca/dia</th><th scope="col" className="r">Sobra/vaca/dia</th></tr></thead>
                <tbody>{r.por_lote.map((l) => (
                  <tr key={l.lote}>
                    <td>{l.lote}{l.consumo_sem_preco_kg > 0 && <small>{num(l.consumo_sem_preco_kg, 0)} kg de consumo sem preço no estoque</small>}</td>
                    <td className="r">{l.vacas}</td>
                    <td className="r">{l.leite_l_vaca_dia != null ? `${num(l.leite_l_vaca_dia, 1)} L` : "—"}</td>
                    <td className="r">{l.receita_vaca_dia != null ? brl(l.receita_vaca_dia) : "—"}</td>
                    <td className="r">{l.comida_vaca_dia != null ? brl(l.comida_vaca_dia) : <span className="mut" title="Sem consumo registrado por lote na Alimentação">sem consumo</span>}</td>
                    <td className="r">{l.rmca_vaca_dia != null ? <span className={l.rmca_vaca_dia < 0 ? "neg" : undefined}>{brl(l.rmca_vaca_dia)}</span> : "—"}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <p className="rl-hint">Leite: média do Controle leiteiro do lote{r.regras_v2 ? " (kg ÷ 1,029)" : ""} × {r.preco_bruto_l != null ? brl(r.preco_bruto_l) : "—"} por litro (preço bruto médio do período). Comida: o consumo lançado por lote na Alimentação × o preço do item no estoque. O lote é o atual do animal.</p>
          </>) : <p className="rl-hint" style={{ margin: 0 }}>Sem Controle leiteiro no período: não há vaca para repartir por lote.</p>}
        </section>
        <details className="rl-nota rl-noprint">
          <summary>Simulador de dieta (dois cenários)</summary>
          <div><RmcaSimulador key={r.periodo.inicio + r.periodo.fim} dados={r} /></div>
        </details>
        {r.fisico.itens.length > 0 && (
          <details className="rl-nota">
            <summary>Consumo registrado pela Alimentação (físico), ingrediente a ingrediente</summary>
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Custo físico por ingrediente</caption>
                <thead><tr><th scope="col">Ingrediente</th><th scope="col" className="r">Consumo</th><th scope="col" className="r">Vlr. unit.</th><th scope="col" className="r">Custo</th></tr></thead>
                <tbody>{r.fisico.itens.map((it) => (
                  <tr key={it.ingrediente}><td>{it.ingrediente}</td><td className="r">{num(it.quantidade, 2)}{it.unidade ? ` ${it.unidade}` : ""}</td><td className="r">{brl(it.valor_unitario)}</td><td className="r">{brl(it.custo)}</td></tr>
                ))}</tbody>
                <tfoot><tr><td>Total</td><td /><td /><td className="r">{brl(r.fisico.comida)}</td></tr></tfoot>
              </table>
            </div>
          </details>
        )}
      </>)}
      <NotasMetodo titulo="Como a sobra da comida é calculada"
        entra={[
          ["Receita do leite", `Contas marcadas como venda do leite (${r?.contas_receita.join(", ") || "nenhuma"}), pelo mês do gasto. BRUTA: é a convenção do indicador; a líquida de Funrural/Senar aparece ao lado${r?.regras_v2 ? "" : " quando as regras novas estão ligadas"}.`],
          ["Comida (gerencial)", `Contas marcadas como alimentação (${r?.contas_custo.join(", ") || "nenhuma"})${r?.regras_v2 ? ", com o desconto da nota rateado (o mesmo valor da DRE)" : ""}. Inclui a comida da recria e das vacas secas.`],
          ["Comida (físico)", "O que a Alimentação baixou do estoque no período × o preço do item na época."],
          ["Por vaca/dia", "÷ (vacas em lactação × dias). Vaca em lactação no mês = teve Controle leiteiro no mês."],
          ...ROTEIRO,
        ]}
        naoEntra={["Gente, energia e os outros custeios (estão em Custos do leite).", "Venda de animais e outras receitas."]} />
      {r && a && !nivel && porVaca && (
        <Conferencia fecha={Math.abs((a.comida_vaca_dia ?? 0) * a.vaca_dias - a.comida) < 0.5 && Math.abs(a.receita_bruta - a.comida - a.rmca) < 0.02}
          texto={`Comida ${brl(a.comida_vaca_dia ?? 0)} × ${num(a.vaca_dias, 0)} vaca-dias = ${brl(a.comida)}; receita ${brl(a.receita_bruta)} − comida = RMCA ${brl(a.rmca)} (o mesmo da tela anterior).`} />
      )}
    </RelatorioShell>
  );
}
