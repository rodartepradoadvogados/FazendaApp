"use client";
// Relatórios › Entrega ao contador › Pacote do contador — "O que entrego ao contador?"
// Um ZIP (PDF + Excel + CSV + apoio ao LCDPR) montado no SERVIDOR pelas mesmas
// funções dos relatórios (GET /financeiro/pacote-contador[/zip|/pdf]): DRE de
// competência e de caixa, livro caixa, não classificados, pendências do
// fechamento, patrimônio e depreciação, conciliação e a trilha do fechamento.
// A tela só mostra o que vai no pacote e baixa. O Painel do Contador usa a
// mesma lista (ListaPacote).
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Mail } from "lucide-react";
import { fetchPacoteContador, type PacoteResumo } from "@/lib/fechamentoApi";
import { ESTADO_INICIAL, brl, emCurso, mesCurto, mesLongo } from "@/lib/relatorioContexto";
import { frasePacote } from "@/lib/relatorioFechamento";
import type { RelatorioParaExportar } from "@/lib/export";
import { Conferencia, NotasMetodo, RelatorioShell, VazioQueEnsina } from "./RelatorioShell";
import { useContextoRelatorio, type TravasContexto } from "./useContextoRelatorio";
import { CSS_ENTREGA } from "./estilosEntrega";
import { ListaPacote, Pill } from "./entregaComum";
import type { PropsRelatorio } from "./comum";

const DIAS_MAX = 400;
const TRAVAS: TravasContexto = {
  cc: "todos", reg: "caixa", cmp: "nada" as const, tiposPeriodo: ["a", "m", "t", "s", "l"],
  porque: "O pacote do contador é por período (o ano-calendário, pela regra fiscal) e leva as duas DREs — mês do gasto e dia do pagamento — da fazenda inteira.",
};

export default function PacoteContadorView(props: PropsRelatorio) {
  const { hoje, centros } = props;
  const padrao = useMemo(() => ({ ...ESTADO_INICIAL(hoje, "todos"), per: `a:${Number(hoje.slice(0, 4)) - 1}` }), [hoje]);
  const ctx = useContextoRelatorio(padrao, TRAVAS);
  const { periodo } = ctx;
  const dias = Math.round((new Date(`${periodo.fim}T12:00:00`).getTime() - new Date(`${periodo.ini}T12:00:00`).getTime()) / 86400000);
  const longoDemais = dias > DIAS_MAX;

  const [dados, setDados] = useState<PacoteResumo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const [chave, setChave] = useState("");
  useEffect(() => {
    if (longoDemais) return;
    let vivo = true;
    fetchPacoteContador(periodo.ini, periodo.fim)
      .then((d) => { if (vivo) { setDados(d); setErro(null); setChave(`${periodo.ini}~${periodo.fim}`); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [periodo.ini, periodo.fim, tentativa, longoDemais]);

  const atual = chave === `${periodo.ini}~${periodo.fim}` ? dados : null;
  const estado = longoDemais ? "vazio" : !atual && !erro ? "carregando" : erro && !atual ? "erro" : "ok";
  const previa = emCurso(periodo, hoje) || periodo.fim > hoje;

  const exportar = (): RelatorioParaExportar | null => atual && ({
    titulo: "Pacote do contador", pergunta: "O que entrego ao contador?",
    contexto: { periodo: periodo.label, comparacao: null, regime: "competência e caixa (as duas DREs)", centro: "todos os centros" },
    colunas: [{ header: "Arquivo", tipo: "texto" }, { header: "Formato", tipo: "texto" }, { header: "Situação", tipo: "texto" }, { header: "Detalhe", tipo: "texto" }],
    linhas: atual.itens.map((i) => ({ valores: [i.nome, i.formato, i.ok ? "pronto" : "pendência", i.detalhe] })),
    notas: atual.metodo, nomeArquivoBase: "pacote_do_contador_lista",
  });

  const pendBloq = atual?.pendencias.filter((p) => p.bloqueia) ?? [];
  const mesesPend = Array.from(new Set(pendBloq.map((p) => p.mes))).sort();
  // Uma linha por conferência, com os meses em que ela falta (o detalhe mês a mês vai no CSV).
  const grupos = Array.from(pendBloq.reduce((m, p) => m.set(p.conferencia, [...(m.get(p.conferencia) ?? []), p.mes]), new Map<string, string[]>()))
    .map(([conferencia, meses]) => ({ conferencia, meses: Array.from(new Set(meses)).sort() }));

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Entrega ao contador" nome="Pacote do contador"
      pergunta="O que entrego ao contador?" onIrGrupo={props.onIrGrupo}
      estado={estado} erro={erro} onTentarDeNovo={() => { setErro(null); setTentativa((t) => t + 1); }}
      vazio={<VazioQueEnsina titulo="Período longo demais para um pacote" texto={<>O pacote vai até 13 meses por vez — o ano-calendário é o mais comum. Escolha um ano, um trimestre ou um mês na barra acima.</>}
        acoes={<button type="button" className="rl-btn" onClick={() => ctx.mudar({ per: padrao.per })}>Usar o ano de {padrao.per.slice(2)}</button>} />}
      frase={atual ? frasePacote(atual.itens, previa) : []} exportar={exportar}
      avisos={atual && !atual.cabecalho.regras_v2 ? (
        <div className="rl-aviso info" role="status"><AlertTriangle size={18} aria-hidden /><div>
          <b>Regras antigas dos relatórios nesta fazenda.</b>
          <p>O pacote sai com a DRE das regras antigas e o livro caixa sem a natureza de cada lançamento (o apoio ao LCDPR fica só com o cabeçalho). A nota de método do pacote diz isso ao contador.</p>
        </div></div>
      ) : null}>
      <style>{CSS_ENTREGA}</style>
      {atual && (<>
        <section className="rl-painel" aria-labelledby="pk-t">
          <h3 className="rl-tit" id="pk-t">O que vai no pacote</h3>
          <ListaPacote itens={atual.itens} inicio={periodo.ini} fim={periodo.fim}
            extraAcoes={mesesPend.length > 0 ? (
              <button type="button" className="rl-linkbtn" style={{ color: "var(--text-accent)", fontWeight: 700, textDecoration: "underline", textUnderlineOffset: 3 }}
                onClick={() => props.onIrRelatorio("fechamento_mes")}>
                Resolver pendências primeiro
              </button>) : null} />
        </section>
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="pk-n">
            <h3 className="rl-tit" id="pk-n">Números que vão no pacote</h3>
            <dl className="ce-dl">
              <dt>Resultado — mês do gasto (DRE de competência)</dt><dd style={atual.dre.competencia.resultado < 0 ? { color: "var(--st-venc-fg)" } : undefined}>{brl(atual.dre.competencia.resultado)}</dd>
              <dt>Resultado — dia do pagamento (DRE de caixa)</dt><dd style={atual.dre.caixa.resultado < 0 ? { color: "var(--st-venc-fg)" } : undefined}>{brl(atual.dre.caixa.resultado)}</dd>
              <dt>Livro caixa: entradas</dt><dd>{brl(atual.livro.entradas)}</dd>
              <dt>Livro caixa: saídas</dt><dd>{brl(atual.livro.saidas)}</dd>
              <dt>Livro caixa: saldo no fim{atual.livro.saldo_inicial_pendente ? " (sem saldo de abertura conferido)" : ""}</dt>
              <dd style={atual.livro.saldo_final < 0 ? { color: "var(--st-venc-fg)" } : undefined}>{brl(atual.livro.saldo_final)}</dd>
              {atual.livro.receitas_atividade != null && (<>
                <dt>Receitas da atividade rural (livro)</dt><dd>{brl(atual.livro.receitas_atividade)}</dd>
                <dt>Despesas de custeio e investimento (livro)</dt><dd>{brl(atual.livro.despesas_atividade ?? 0)}</dd>
              </>)}
              <dt>Depreciação do período</dt><dd>{brl(atual.patrimonio.depreciacao_periodo)}</dd>
            </dl>
            <p style={{ margin: ".6rem 0 0", fontSize: ".76rem", color: "var(--text-muted)" }}>
              {atual.livro.lancamentos} lançamentos no livro · gerado por {atual.cabecalho.gerado_por || "—"} · {atual.cabecalho.fazenda}{atual.cabecalho.documento ? ` · ${atual.cabecalho.documento}` : " · CPF/CNPJ não cadastrado"}
            </p>
          </section>
          <section className="rl-painel" aria-labelledby="pk-p">
            <h3 className="rl-tit" id="pk-p">Pendências que vão junto</h3>
            {grupos.length === 0 ? <p style={{ margin: 0, fontSize: ".84rem", color: "var(--text-muted)" }}>Nenhuma pendência de fechamento no período.</p> : (
              <ul className="ce-lst">
                {grupos.map((g) => (
                  <li key={g.conferencia}>
                    <span className="ce-ic aten"><AlertTriangle size={16} aria-hidden /></span>
                    <div><b>{g.conferencia}</b><small>{g.meses.length === 1 ? mesLongo(g.meses[0]) : `${g.meses.length} meses: ${g.meses.map(mesCurto).join(", ")}`}</small></div>
                    <Pill tom="aten" icone={null}>pendente</Pill>
                  </li>
                ))}
              </ul>
            )}
            {grupos.length > 0 && <p className="ce-mais">Mês a mês, com o detalhe, em pendencias.csv.</p>}
          </section>
        </div>
        <NotasMetodo titulo="Por que estes arquivos (e a nota de método que vai no pacote)"
          entra={[
            ["DRE de competência e de caixa", "A cascata única do servidor — a mesma da DRE da fazenda e do e-mail do Portal."],
            ["Livro caixa da atividade rural", "O que passou pelo caixa no período, pelo dia e pelo valor pago. Base da declaração do produtor rural."],
            ["Não classificados e pendências", "O que ainda não tem linha na DRE e o que falta em cada mês (sem conta, contas automáticas, saldo de abertura, cartão, folha, conciliação, depreciação)."],
            ["Patrimônio e depreciação", "Bens, aquisições e baixas do período, depreciação do período e acumulada."],
            ["Conciliação e fechamento", "Provam que o livro bate com os bancos e que os meses foram fechados (com o retrato SHA-256 de cada fechamento)."],
            ["Apoio ao LCDPR", "Registros Q100 e Q200 no leiaute do Livro Caixa Digital com o que o sistema sabe; imóvel e CPF/CNPJ dos participantes ficam em branco (o LEIA-ME lista o que falta)."],
          ]}
          naoEntra={["CPF/CNPJ de fornecedores e funcionários, dados de saúde, endereços e contatos (LGPD: só o necessário para a escrituração)."]}>
          <ul style={{ margin: ".6rem 0 0" }}>{atual.metodo.map((n) => <li key={n}>{n}</li>)}</ul>
          <p style={{ margin: ".6rem 0 0", display: "flex", gap: ".35rem", alignItems: "center" }}>
            <Mail size={14} aria-hidden /> Para mandar por e-mail: Portal › Enviar e-mail › relatório “Pacote do contador (ZIP)”. O contador vinculado também baixa pelo Painel do Contador.
          </p>
        </NotasMetodo>
        <Conferencia fecha texto={`Cada arquivo é gerado pelas mesmas funções dos relatórios (DRE, saldo das contas, depreciação): resultado de ${brl(atual.dre.competencia.resultado)} no mês do gasto, igual à DRE da fazenda de ${periodo.label}.`} />
      </>)}
    </RelatorioShell>
  );
}
