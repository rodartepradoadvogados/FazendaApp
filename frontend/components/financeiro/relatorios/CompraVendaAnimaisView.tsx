"use client";
// Relatórios › Registros › Compra e venda de animais — "Quanto rendeu a compra e venda de animais?"
// Consulta unificada das duas pontas (Comprar/Vender animal em Lançamentos),
// no molde: período e centro da barra de contexto, resultado por cabeça e por
// categoria, a classificação da Fase A (matriz/reprodutor = INVESTIMENTO, fora
// da DRE e dos custos com as regras novas) visível em cada linha, drill até
// Consultas e exportação. Mantém a busca da tela anterior (número do animal,
// documento, GTA — em todo o histórico, como a busca global do Financeiro).
// Números de GET /relatorio-compra-venda-animais/resumo.
import { useEffect, useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { fetchResumoAnimais } from "@/lib/apiRelatoriosLeite";
import { ESTADO_INICIAL, brl, periodoDe, type Periodo } from "@/lib/relatorioContexto";
import { buscaGlobal, fraseAnimais, type LinhaAnimal, type RespostaAnimais } from "@/lib/relatorioRegistros";
import type { RelatorioParaExportar } from "@/lib/export";
import { Conferencia, NotasMetodo, PainelGrafico, RelatorioShell, VazioQueEnsina, type EstadoTela, type KpiDef } from "./RelatorioShell";
import { BarrasHorizontais, LegendaBarras } from "./barras";
import { useContextoRelatorio, useDetalheNaUrl, type TravasContexto } from "./useContextoRelatorio";
import type { PropsRelatorio } from "./comum";
import { CSS_LEITE_REGISTROS } from "./estilosLeite";
import { FormBusca, SeloNatureza, TabelaOrdenavel, useBuscaNaUrl, type Coluna } from "./registrosComum";

const NOME = "Compra e venda de animais";
const PERGUNTA = "Quanto rendeu a compra e venda de animais?";
const TRAVAS: TravasContexto = { reg: "comp", cmpOrcado: false, porque: "Compra e venda de animais é pela data da nota (como na tela anterior)." };
const dmy = (s: string) => s.split("-").reverse().join("/");
const cab = (n: number) => `${n.toLocaleString("pt-BR")} cab.`;

export default function CompraVendaAnimaisView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, TRAVAS);
  const { periodo, comparacao, efetivo } = ctx;
  const [busca, mudarBusca] = useBuscaNaUrl();
  const global = buscaGlobal(busca);
  const cmp = !global && comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const centroApi = global || efetivo.cc === "todos" ? null : efetivo.cc;
  const [det, abrirDet] = useDetalheNaUrl("det");
  const [tentativa, setTentativa] = useState(0);
  const [res, setRes] = useState<{ chave: string; a: RespostaAnimais; b: RespostaAnimais | null } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const chave = [global ? "" : periodo.cod, cmp?.cod, centroApi, busca.numero, busca.documento, busca.gta].join("|");

  useEffect(() => {
    let vivo = true;
    const ler = (p: Periodo | null) => fetchResumoAnimais({
      ...(p ? { data_de: p.ini, data_ate: p.fim } : {}), centro_custo: centroApi,
      numero: busca.numero, numero_documento: busca.documento, gta: busca.gta,
    });
    Promise.all([ler(global ? null : periodo), cmp ? ler(cmp) : Promise.resolve(null)])
      .then(([a, b]) => { if (vivo) { setRes({ chave, a, b }); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [chave, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps

  const r = res && res.chave === chave ? res.a : null;
  const rb = res && res.chave === chave ? res.b : null;
  const t = r?.totais, tb = rb?.totais;
  const estado: EstadoTela = !r && !erro ? "carregando" : erro && !r ? "erro" : !r!.linhas.length ? "vazio" : "ok";
  const categoria = det.startsWith("cat:") ? det.slice(4) : null;
  const linhas = useMemo(() => (r?.linhas ?? []).filter((l) => !categoria || l.categoria === categoria), [r, categoria]);
  const quando = global ? "no histórico buscado" : periodo.label;

  const consultas = (l: LinhaAnimal) => {
    if (!l.numero_lancamento) return;
    props.onConsultas({ de: "", ate: "", periodoPor: "competencia", origem: `${NOME} › animal ${l.numero_animal}`, documento: l.numero_lancamento } as Parameters<PropsRelatorio["onConsultas"]>[0]);
  };

  const kpis: KpiDef[] = t ? [
    { chave: "saldo", rotulo: "Vendas − compras", valor: t.saldo, cmp: tb?.saldo ?? null, formato: "brl0", bom: "sobe", negativoEmVermelho: true,
      sub: "Vendas entram na receita da DRE; matriz e reprodutor comprados são investimento" },
    { chave: "vendas", rotulo: "Vendas", valor: t.vendas, cmp: tb?.vendas ?? null, formato: "brl0", bom: "sobe",
      sub: `${cab(t.cab_vendidas)}${t.venda_por_cabeca != null ? ` · ${brl(t.venda_por_cabeca, 0)} por cabeça` : ""}`, onAbrir: () => props.onIrRelatorio("rel_dre", "RECEITA_VENDAS") },
    { chave: "compras", rotulo: "Compras", valor: t.compras, cmp: tb?.compras ?? null, formato: "brl0", bom: "neutro",
      sub: `${cab(t.cab_compradas)}${t.compra_por_cabeca != null ? ` · ${brl(t.compra_por_cabeca, 0)} por cabeça` : ""}` },
    { chave: "inv", rotulo: "Compras para o plantel (investimento)", valor: t.compras_investimento, cmp: tb?.compras_investimento ?? null, formato: "brl0", bom: "neutro",
      sub: r?.regras_v2 ? "Fora da DRE e dos custos; entram aos poucos pelo desgaste" : "Classificadas; só saem da DRE com as regras novas ligadas",
      onAbrir: () => props.onIrRelatorio("rel_dre") },
  ] : [];

  const barras = (r?.por_categoria ?? []).flatMap((c) => [
    ...(c.cab_vendidas ? [{ chave: `v:${c.categoria}`, nome: `Venda · ${c.categoria}`, valor: c.venda_por_cabeca ?? 0, sub: cab(c.cab_vendidas), rotuloAbrir: `Vendas de ${c.categoria}: abrir os animais` }] : []),
    ...(c.cab_compradas ? [{ chave: `c:${c.categoria}`, nome: `Compra · ${c.categoria}`, valor: c.compra_por_cabeca ?? 0, sub: cab(c.cab_compradas), hachura: true, rotuloAbrir: `Compras de ${c.categoria}: abrir os animais` }] : []),
  ]);

  const colunas: Coluna<LinhaAnimal>[] = [
    { chave: "numero", rotulo: "Nº animal", valor: (l) => l.numero_animal, celula: (l) => <>{l.numero_animal}{l.numero_lancamento && <ExternalLink size={12} aria-hidden />}</> },
    { chave: "tipo", rotulo: "Tipo", valor: (l) => (l.tipo === "compra" ? "Compra" : "Venda") },
    { chave: "categoria", rotulo: "Categoria", valor: (l) => l.categoria, celula: (l) => (l.origem_categoria === "animal" ? <span title="Categoria atual do animal no cadastro (a nota não diz)">{l.categoria}*</span> : l.categoria) },
    { chave: "contraparte", rotulo: "Contraparte", valor: (l) => l.contraparte || "" },
    { chave: "data", rotulo: "Data", valor: (l) => l.data, celula: (l) => dmy(l.data) },
    { chave: "valor", rotulo: "Valor (por animal)", num: true, valor: (l) => l.valor, celula: (l) => brl(l.valor) },
    { chave: "natureza", rotulo: "Classificação", valor: (l) => l.natureza_rotulo, celula: (l) => <SeloNatureza n={l.natureza} rotulo={l.natureza_rotulo} /> },
    { chave: "gta", rotulo: "GTA", opc: true, valor: (l) => l.gta || "—" },
    { chave: "doc", rotulo: "Documento", opc: true, valor: (l) => l.numero_documento || "—" },
    { chave: "lanc", rotulo: "Lançamento", opc: true, valor: (l) => l.numero_lancamento || "—" },
    { chave: "centro", rotulo: "Centro de custo", opc: true, valor: (l) => l.centro_custo || "—" },
  ];

  const exportar = (): RelatorioParaExportar | null => r ? {
    titulo: categoria ? `${NOME} — ${categoria}` : NOME, pergunta: PERGUNTA,
    contexto: { periodo: global ? "todo o histórico (busca)" : periodo.label, comparacao: cmp?.label ?? null, regime: "pela data da nota", centro: centroApi ?? "todos os centros" },
    colunas: [{ header: "Tipo", tipo: "texto" }, { header: "Nº animal", tipo: "texto" }, { header: "Categoria", tipo: "texto" }, { header: "Contraparte", tipo: "texto" },
      { header: "Data", tipo: "texto" }, { header: "Valor (por animal)", tipo: "brl" }, { header: "Classificação", tipo: "texto" }, { header: "GTA", tipo: "texto" },
      { header: "Documento", tipo: "texto" }, { header: "Lançamento", tipo: "texto" }, { header: "Centro de custo", tipo: "texto" }],
    linhas: [
      ...linhas.map((l) => ({ valores: [l.tipo === "compra" ? "Compra" : "Venda", l.numero_animal, l.categoria, l.contraparte, dmy(l.data), l.valor, l.natureza_rotulo, l.gta, l.numero_documento, l.numero_lancamento, l.centro_custo] })),
      { valores: ["Vendas", null, null, null, null, linhas.filter((l) => l.tipo === "venda").reduce((s, l) => s + l.valor, 0), null, null, null, null, null], total: true },
      { valores: ["Compras", null, null, null, null, linhas.filter((l) => l.tipo === "compra").reduce((s, l) => s + l.valor, 0), null, null, null, null, null], total: true },
    ],
    nomeArquivoBase: "compra_venda_animais",
    notas: [
      ...(r.por_categoria.map((c) => `${c.categoria}: ${c.cab_vendidas} vendida(s) por ${brl(c.vendas)}${c.venda_por_cabeca != null ? ` (${brl(c.venda_por_cabeca)}/cab.)` : ""}; ${c.cab_compradas} comprada(s) por ${brl(c.compras)}${c.compra_por_cabeca != null ? ` (${brl(c.compra_por_cabeca)}/cab.)` : ""}.`)),
      `Compras para o plantel classificadas como investimento: ${brl(r.totais.compras_investimento)}${r.regras_v2 ? " (fora da DRE e dos custos)" : " (saem da DRE só com as regras novas)"}.`,
      ...(r.totais.sem_lancamento ? [`${r.totais.sem_lancamento} registro(s) sem lançamento financeiro (sem centro e sem classificação).`] : []),
    ],
  } : null;

  const vazioUi = (
    <VazioQueEnsina titulo={global ? "Nada encontrado para a busca" : `Nenhuma compra ou venda de animais em ${periodo.label}`}
      texto={global ? "A busca olha todo o histórico pelo número do animal, documento ou GTA. Confira o número ou limpe a busca." : "Escolha um período maior para ver o resultado por categoria."}
      acoes={<>
        {global ? <button type="button" className="rl-btn" onClick={() => mudarBusca({})}>Limpar a busca</button> : (<>
          <button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: periodoDe(`a:${hoje.slice(0, 4)}`)!.cod })}>Ver {hoje.slice(0, 4)}</button>
          <button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: periodoDe(`a:${Number(hoje.slice(0, 4)) - 1}`)!.cod })}>Ver {Number(hoje.slice(0, 4)) - 1}</button>
          {efetivo.cc !== "todos" && <button type="button" className="rl-btn" onClick={() => ctx.mudar({ cc: "todos" })}>Ver todos os centros</button>}
        </>)}
        <a className="rl-btn" href="/lancamentos?ir=comprar_animal">Lançar uma compra</a>
        <a className="rl-btn" href="/lancamentos?ir=vender_animal">Lançar uma venda</a>
      </>} />
  );

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Registros" nome={NOME} pergunta={PERGUNTA} onIrGrupo={props.onIrGrupo}
      niveis={categoria ? [{ rotulo: categoria }] : []} onVoltarNivel={() => abrirDet("")}
      estado={estado} erro={erro} onTentarDeNovo={() => { setErro(null); setTentativa((x) => x + 1); }} vazio={vazioUi}
      frase={r && !categoria ? fraseAnimais({ periodo: global ? null : periodo, r, brl }) : []} kpis={categoria ? undefined : kpis} exportar={exportar}
      avisos={<>
        <style>{CSS_LEITE_REGISTROS}</style>
        <FormBusca valor={busca} onBuscar={mudarBusca}
          campos={[{ chave: "numero", rotulo: "Número do animal", dica: "ex.: 950" }, { chave: "documento", rotulo: "Nº do documento" }, { chave: "gta", rotulo: "GTA" }]}
          nota={global ? <>Busca em <b>todo o histórico</b> e em todos os centros (o período da barra não vale para a busca).</> : "Número do animal, documento ou GTA buscam em todo o histórico, como a busca do Financeiro."} />
      </>}>
      {r && !categoria && (<>
        {barras.length > 0 && (
          <PainelGrafico titulo="Preço médio por cabeça, por categoria" legenda={<LegendaBarras cheio="Venda" hachura="Compra" />}
            tabela={{ cabecalho: ["Categoria", "Vendidas", "R$/cabeça (venda)", "Compradas", "R$/cabeça (compra)"], linhas: r.por_categoria.map((c) => [
              c.categoria, String(c.cab_vendidas), c.venda_por_cabeca != null ? brl(c.venda_por_cabeca) : "—", String(c.cab_compradas), c.compra_por_cabeca != null ? brl(c.compra_por_cabeca) : "—",
            ]) }}>
            <BarrasHorizontais itens={barras} fmt={(v) => `${brl(v, 0)}/cab.`} onAbrir={(k) => abrirDet(`cat:${k.slice(2)}`)}
              descricao={`Preço médio por cabeça ${quando}: ${barras.map((b) => `${b.nome} ${brl(b.valor, 0)}`).join(", ")}.`} />
          </PainelGrafico>
        )}
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-an-cat">
            <h3 className="rl-tit" id="rl-an-cat">Por categoria</h3>
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Compra e venda por categoria — {quando}</caption>
                <thead><tr><th scope="col">Categoria</th><th scope="col" className="r">Vendidas</th><th scope="col" className="r">Vendas</th><th scope="col" className="r rl-opc">R$/cab.</th>
                  <th scope="col" className="r">Compradas</th><th scope="col" className="r">Compras</th><th scope="col" className="r rl-opc">R$/cab.</th></tr></thead>
                <tbody>{r.por_categoria.map((c) => (
                  <tr key={c.categoria} className="clic" onClick={(e) => { if (!(e.target as HTMLElement).closest("button")) abrirDet(`cat:${c.categoria}`); }}>
                    <td><button type="button" className="rl-linkbtn" onClick={() => abrirDet(`cat:${c.categoria}`)} aria-label={`${c.categoria}: abrir os animais`}>{c.categoria}</button></td>
                    <td className="r">{c.cab_vendidas || "—"}</td><td className="r">{c.vendas ? brl(c.vendas, 0) : "—"}</td><td className="r rl-opc">{c.venda_por_cabeca != null ? brl(c.venda_por_cabeca, 0) : "—"}</td>
                    <td className="r">{c.cab_compradas || "—"}</td><td className="r">{c.compras ? brl(c.compras, 0) : "—"}</td><td className="r rl-opc">{c.compra_por_cabeca != null ? brl(c.compra_por_cabeca, 0) : "—"}</td>
                  </tr>
                ))}</tbody>
                <tfoot><tr><td>Total</td><td className="r">{t!.cab_vendidas}</td><td className="r">{brl(t!.vendas, 0)}</td><td className="r rl-opc">{t!.venda_por_cabeca != null ? brl(t!.venda_por_cabeca, 0) : "—"}</td>
                  <td className="r">{t!.cab_compradas}</td><td className="r">{brl(t!.compras, 0)}</td><td className="r rl-opc">{t!.compra_por_cabeca != null ? brl(t!.compra_por_cabeca, 0) : "—"}</td></tr></tfoot>
              </table>
            </div>
            <p className="rl-hint">Categoria da nota de venda; quando a nota não diz (e na compra), a categoria atual do animal no cadastro.</p>
          </section>
          <section className="rl-painel" aria-labelledby="rl-an-nat">
            <h3 className="rl-tit" id="rl-an-nat">Classificação dos lançamentos</h3>
            {r.por_natureza.map((n) => (
              <div key={n.natureza ?? "sem"} className="rl-linha-valor">
                <span><SeloNatureza n={n.natureza} rotulo={n.rotulo} /> {n.rotulo}<small>{[n.cab_compradas ? `${cab(n.cab_compradas)} compradas` : "", n.cab_vendidas ? `${cab(n.cab_vendidas)} vendidas` : ""].filter(Boolean).join(" · ")}</small></span>
                <b>{[n.compras ? `compras ${brl(n.compras, 0)}` : "", n.vendas ? `vendas ${brl(n.vendas, 0)}` : ""].filter(Boolean).join(" · ")}</b>
              </div>
            ))}
            <p className="rl-hint">{r.regras_v2
              ? "Investimento (matriz e reprodutor para o plantel) fica fora da DRE e dos custos; recria e venda são operacionais."
              : "A classificação já aparece, mas com as regras antigas a compra continua como despesa na DRE (como antes). Ligue as regras novas em Parâmetros financeiros."}</p>
          </section>
        </div>
      </>)}
      {r && (
        <section className="rl-painel" aria-labelledby="rl-an-lanc">
          <h3 className="rl-tit" id="rl-an-lanc">{categoria ? `${categoria} — animal a animal` : "Animal a animal"}</h3>
          <TabelaOrdenavel titulo={`Compras e vendas de animais — ${quando}`} colunas={colunas} linhas={linhas} chaveLinha={(l, i) => `${l.tipo}-${l.numero_animal}-${l.data}-${i}`}
            onAbrir={consultas} rotuloAbrir={(l) => (l.numero_lancamento ? `Animal ${l.numero_animal}: ver o lançamento ${l.numero_lancamento} em Consultas` : `Animal ${l.numero_animal}: sem lançamento financeiro`)}
            vazio="Nenhuma compra ou venda nesta categoria."
            rodape={<tr><td colSpan={5}>Total — {linhas.length} animal(is)</td><td className="r">{brl(linhas.reduce((s, l) => s + (l.tipo === "venda" ? l.valor : -l.valor), 0))}</td><td colSpan={5} className="mut">vendas − compras</td></tr>} />
          <p className="rl-hint">* categoria atual do animal no cadastro (a nota não diz). Clique no animal para abrir o lançamento em Consultas. Consultas mostra o que já foi pago ou recebido; o que está em aberto fica em Contas.</p>
        </section>
      )}
      <NotasMetodo titulo="Regras"
        entra={[
          ["Vendas", "Entram na receita bruta da DRE (venda de animais) e ajudam a pagar o custo do leite."],
          ["Compras para o plantel", "Matriz e reprodutor: investimento (Fase A) — fora da DRE e dos custos com as regras novas; no livro caixa, saída no mês do pagamento."],
          ["Compras para recria ou venda", "Operacionais: entram no custo como antes."],
          ["Por cabeça", "Cada registro é um animal, com o valor por animal da nota."],
          ["Período e centro", "Pela data da nota; o centro é o do lançamento financeiro gerado (registro sem lançamento só aparece em “Todos os centros”)."],
        ]} />
      {r && t && (
        <Conferencia fecha={Math.abs(r.por_categoria.reduce((s, c) => s + c.vendas - c.compras, 0) - t.saldo) < 0.05}
          texto={`As categorias somam vendas ${brl(t.vendas)} e compras ${brl(t.compras)} — o total do período (${t.cab_vendidas + t.cab_compradas} animais).`} />
      )}
    </RelatorioShell>
  );
}
