"use client";
// Relatórios › Resultado › Classificar — "O que falta classificar?"
// A fila vem do SERVIDOR (GET /financeiro/classificacao/pendencias): os mesmos registros da DRE,
// então o que está aqui é exatamente o que a DRE deixa de fora ("Sem conta") ou deixa fora sem
// dizer por quê. A tela agrupa por motivo, deixa escolher a conta / a linha da DRE / a natureza
// para um lote de linhas e mostra as sugestões — que só valem quando alguém aceita, com um
// clique. Cada lote fica num log e tem Desfazer. Só administrador grava.
// Com as regras antigas (financeiro_regras_v2 desligada) a natureza fica travada, com o porquê.
import { Fragment, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, Info, Lightbulb, Lock, Undo2 } from "lucide-react";
import { ehAdmin, fetchPlanoContas } from "@/lib/api";
import {
  aplicarClassificacao, fetchFilaClassificacao, reverterClassificacao, type AcaoClassificacao, type FilaClassificacao, type LinhaPendencia,
  type MotivoClassificacao,
} from "@/lib/classificacaoApi";
import { ESTADO_INICIAL, REGIME_API, REGIME_NOME, brl } from "@/lib/relatorioContexto";
import {
  ACAO_DO_MOTIVO, LINHAS_DRE, MOTIVOS, MOTIVOS_POR_CONTA, ROTULO_MOTIVO, acoesDasSugestoes, acoesDoControle, agruparLinhas, descreverLote,
  destinoDaLinha, filtrarLinhas, fraseClassificar, limitarGrupos, linhasParaExportar, mensagemAplicada, mensagemDesfeita, podeAplicar, sugestaoAplicavel,
  textoDoLote, tipoUniforme, totais, type Controle,
} from "@/lib/relatorioClassificar";
import { NATUREZAS_FIN } from "@/lib/naturezaFin";
import type { ContaPlano } from "@/lib/contaGerencial";
import type { RelatorioParaExportar } from "@/lib/export";
import { FiltroContaGerencial } from "@/components/financeiro/filtroContaGerencial";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import { NotasMetodo, RelatorioShell, VazioQueEnsina } from "./RelatorioShell";
import { CSS_CLASSIFICAR } from "./estilosClassificar";
import { useContextoRelatorio, useDetalheNaUrl, type TravasContexto } from "./useContextoRelatorio";
import { PORQUE_CENTRO_REGRAS_ANTIGAS, useRegrasV2Estado, type PropsRelatorio } from "./comum";

const POR_PAGINA = 100;
const brData = (iso: string | null) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");
const dataHoraBr = (iso: string) => {
  // O servidor grava UTC: mostra no fuso de quem lê.
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? brData(iso) : d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
};
const NATUREZAS_FORA = NATUREZAS_FIN.filter((n) => n.valor !== "OPERACIONAL");
const PORQUE_SO_ADMIN = "Só o administrador classifica. Você pode ver a fila e exportar.";

type Mensagem = { ok: boolean; t: string; avisos?: string[] };

/** Caixa de seleção com o estado “parcial” (alguns marcados). */
function CaixaSelecao({ marcado, parcial, onChange, rotulo, desabilitado }: {
  marcado: boolean; parcial?: boolean; onChange: (v: boolean) => void; rotulo: string; desabilitado?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = !!parcial && !marcado; }, [parcial, marcado]);
  return <input ref={ref} type="checkbox" aria-label={rotulo} checked={marcado} disabled={desabilitado} onChange={(e) => onChange(e.target.checked)} />;
}

export default function ClassificarView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const uid = useId();
  const admin = ehAdmin();
  const regras = useRegrasV2Estado();
  // Sem comparação de períodos nesta tela. Com as regras antigas a DRE é sempre da fazenda inteira.
  const travas: TravasContexto = useMemo(() => ({
    cmp: false, ...(regras.ativa === false ? { cc: "todos", porque: PORQUE_CENTRO_REGRAS_ANTIGAS } : {}),
  }), [regras.ativa]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const { periodo, efetivo } = ctx;
  const [motivoUrl, abrirMotivo] = useDetalheNaUrl("mot");

  const centroApi = efetivo.cc === "todos" ? null : efetivo.cc;
  const chave = `${periodo.ini}|${periodo.fim}|${efetivo.reg}|${centroApi ?? ""}`;
  const [leitura, setLeitura] = useState<{ k: string; fila: FilaClassificacao } | null>(null);
  const [erro, setErro] = useState<{ k: string; t: string } | null>(null);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    if (regras.ativa === null) return;
    let vivo = true;
    fetchFilaClassificacao({ data_inicio: periodo.ini, data_fim: periodo.fim, regime: REGIME_API[efetivo.reg], centro_custo: centroApi })
      .then((fila) => { if (vivo) { setLeitura({ k: chave, fila }); setErro(null); } })
      .catch((e) => { if (vivo) setErro({ k: chave, t: (e as Error).message }); });
    return () => { vivo = false; };
  }, [regras.ativa, chave, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps
  const recarregar = useCallback(() => setTentativa((t) => t + 1), []);
  const fila = leitura?.k === chave ? leitura.fila : null;
  const erroAtual = erro?.k === chave ? erro.t : null;

  const [plano, setPlano] = useState<ContaPlano[]>([]);
  useEffect(() => { fetchPlanoContas().then(setPlano).catch(() => { /* o seletor fica vazio; a fila continua valendo */ }); }, []);

  // ── o motivo aberto ──
  const motivoAtivo: MotivoClassificacao = useMemo(() => {
    if (motivoUrl && (MOTIVOS as string[]).includes(motivoUrl)) return motivoUrl as MotivoClassificacao;
    return fila?.por_motivo.find((m) => m.quantidade > 0)?.motivo ?? MOTIVOS[0];
  }, [motivoUrl, fila]);
  const resumoMotivo = fila?.por_motivo.find((m) => m.motivo === motivoAtivo) ?? null;
  const acao = ACAO_DO_MOTIVO[motivoAtivo];

  // ── seleção e controles (zeram ao trocar de período ou de motivo) ──
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");
  const [filtroConta, setFiltroConta] = useState({ codigo: "", nome: "" });
  const [visiveis, setVisiveis] = useState(POR_PAGINA);
  const [linhaEscolhida, setLinhaEscolhida] = useState("");
  const [naturezaEscolhida, setNaturezaEscolhida] = useState("");
  const [escopoNatureza, setEscopoNatureza] = useState<"conta" | "lancamento">("conta");
  const [contaEscolhida, setContaEscolhida] = useState({ codigo: "", nome: "" });
  const escopo = `${chave}|${motivoAtivo}`;
  const [escopoVisto, setEscopoVisto] = useState(escopo);
  if (escopoVisto !== escopo) {
    setEscopoVisto(escopo); setSel(new Set()); setBusca(""); setFiltroConta({ codigo: "", nome: "" }); setVisiveis(POR_PAGINA);
    setLinhaEscolhida(""); setNaturezaEscolhida(""); setContaEscolhida({ codigo: "", nome: "" });
  }

  const [msg, setMsg] = useState<Mensagem | null>(null);
  const [enviando, setEnviando] = useState(false);

  const doMotivo = useMemo(() => (fila?.pendencias ?? []).filter((l) => l.motivo === motivoAtivo), [fila, motivoAtivo]);
  const filtradas = useMemo(() => filtrarLinhas(doMotivo, { q: busca, conta: filtroConta.codigo }), [doMotivo, busca, filtroConta.codigo]);
  const liberada = useCallback((l: LinhaPendencia) => admin && podeAplicar(l, acao).ok, [admin, acao]);
  const selecionadas = useMemo(() => filtradas.filter((l) => sel.has(l.chave) && liberada(l)), [filtradas, sel, liberada]);
  const marcaveis = useMemo(() => filtradas.filter(liberada), [filtradas, liberada]);

  const mostradas = useMemo(() => limitarGrupos(agruparLinhas(filtradas, motivoAtivo), visiveis), [filtradas, motivoAtivo, visiveis]);

  const alternar = (chaves: string[], marcar: boolean) => setSel((atual) => {
    const nova = new Set(atual);
    for (const k of chaves) { if (marcar) nova.add(k); else nova.delete(k); }
    return nova;
  });

  // ── gravar ──
  const aplicar = async (acoes: AcaoClassificacao[]) => {
    if (!acoes.length || enviando) return;
    setEnviando(true); setMsg(null);
    try {
      const r = await aplicarClassificacao(acoes);
      setMsg({ ok: true, t: mensagemAplicada(r), avisos: r.avisos });
      setSel(new Set());
      recarregar();
    } catch (e) {
      setMsg({ ok: false, t: (e as Error).message });
    } finally { setEnviando(false); }
  };
  const desfazer = async () => {
    const lote = fila?.ultimo_lote?.lote;
    if (!lote || enviando) return;
    setEnviando(true); setMsg(null);
    try {
      const r = await reverterClassificacao(lote);
      setMsg({ ok: true, t: mensagemDesfeita(r) });
      recarregar();
    } catch (e) {
      setMsg({ ok: false, t: (e as Error).message });
    } finally { setEnviando(false); }
  };

  const controle: Controle | null = acao === "linha_dre" ? (linhaEscolhida ? { tipo: "linha_dre", valor: linhaEscolhida } : null)
    : acao === "conta" ? (contaEscolhida.codigo ? { tipo: "conta", valor: contaEscolhida.codigo } : null)
      : (naturezaEscolhida ? { tipo: "natureza", valor: naturezaEscolhida, escopo: escopoNatureza } : null);
  const plan = controle ? acoesDoControle(selecionadas, controle) : null;
  const sugestoesDaSelecao = acoesDasSugestoes(selecionadas);
  const comSugestao = marcaveis.filter(sugestaoAplicavel);
  const tipoSel = tipoUniforme(selecionadas);
  const totalSel = totais(selecionadas);

  // ── ver o lançamento: o realizado em Consultas; o a prazo em Contas a pagar/receber ──
  const ver = (l: LinhaPendencia) => {
    const d = destinoDaLinha(l);
    if (d.onde === "consultas") props.onConsultas({ de: "", ate: "", periodoPor: "pagamento", documento: d.documento ?? undefined, origem: "Classificar" });
    else props.onIrRelatorio(d.relatorio, undefined, d.documento ?? undefined);
  };

  const estado = regras.ativa === null || (!fila && !erroAtual) ? "carregando" : erroAtual && !fila ? "erro" : fila && fila.resumo.total_pendencias === 0 ? "vazio" : "ok";
  const frase = fila ? fraseClassificar(fila, periodo.label, (v) => brl(v)) : [];

  const exportar = (): RelatorioParaExportar | null => fila && ({
    titulo: "O que falta classificar", pergunta: "O que falta classificar?",
    contexto: { periodo: periodo.label, comparacao: null, regime: REGIME_NOME[efetivo.reg], centro: efetivo.cc === "todos" ? "todos os centros" : efetivo.cc },
    colunas: [
      { header: "Motivo", tipo: "texto" }, { header: "Data", tipo: "texto" }, { header: "Fornecedor / cliente", tipo: "texto" }, { header: "Descrição", tipo: "texto" },
      { header: "Nº do lançamento", tipo: "texto" }, { header: "Conta hoje", tipo: "texto" }, { header: "Tipo", tipo: "texto" }, { header: "Valor", tipo: "brl" },
      { header: "Sugestão (não aplicada)", tipo: "texto" },
    ],
    linhas: linhasParaExportar(fila.pendencias, brData).map((valores) => ({ valores })),
    notas: [
      "Fila do servidor (GET /financeiro/classificacao/pendencias): os mesmos lançamentos que a DRE deixa fora por falta de classificação.",
      `Receita ${brl(fila.resumo.total_receita)} e despesa ${brl(fila.resumo.total_despesa)} — nunca somadas.`,
      fila.resumo.truncado ? `A lista traz as ${fila.resumo.mostradas} primeiras de ${fila.resumo.total_pendencias}.` : "",
    ].filter(Boolean),
    nomeArquivoBase: "classificar",
  });

  // ── avisos acima de tudo (ficam mesmo quando a fila esvazia, para o Desfazer continuar à mão) ──
  const avisos = (<>
    <div aria-live="polite">
      {msg && (
        <div className={`cl-msg${msg.ok ? "" : " erro"}`} role={msg.ok ? "status" : "alert"}>
          {msg.ok ? <CheckCircle2 size={18} aria-hidden /> : <AlertTriangle size={18} aria-hidden />}
          <div>
            <b>{msg.t}</b>
            {msg.avisos?.map((a) => <p key={a}>{a}</p>)}
          </div>
        </div>
      )}
    </div>
    {fila?.ultimo_lote && (
      <div className="cl-desfazer rl-noprint" role="group" aria-label="Desfazer a última classificação">
        <Undo2 size={16} aria-hidden />
        <span>Última classificação: {descreverLote(fila.ultimo_lote, dataHoraBr)}.</span>
        <button type="button" className="rl-btn" onClick={desfazer} disabled={!admin || enviando} title={admin ? undefined : PORQUE_SO_ADMIN}>
          <Undo2 size={14} aria-hidden /> Desfazer
        </button>
      </div>
    )}
    {fila && !fila.regras_v2 && (
      <div className="rl-aviso info" role="status"><Info size={18} aria-hidden /><div>
        <b>Regras antigas dos relatórios: aqui só dá para classificar a conta e a linha da DRE.</b>
        <p>A natureza (investimento, financiamento, capital...) e a folha gerada pelo sistema só valem com as regras novas — <a href="/parametros?sub=financeiro">Parâmetros financeiros</a>.</p>
      </div></div>
    )}
    {fila && !admin && (
      <div className="rl-aviso info" role="status"><Lock size={18} aria-hidden /><div><b>{PORQUE_SO_ADMIN}</b></div></div>
    )}
    {fila?.resumo.truncado && (
      <div className="rl-aviso" role="status"><AlertTriangle size={18} aria-hidden /><div>
        <b>A fila tem {fila.resumo.total_pendencias} lançamentos; aqui estão os {fila.resumo.mostradas} primeiros.</b>
        <p>Os totais acima contam todos. Classifique estes e a fila se renova; ou estreite o período.</p>
      </div></div>
    )}
  </>);

  const vazioUi = (
    <VazioQueEnsina
      titulo={`Nada a classificar em ${periodo.label} ✓`}
      texto={<>Todo lançamento do período tem conta, a conta tem linha na DRE e, quando algo fica de fora dela, o motivo está dito. É isso que deixa a DRE fechar sem buraco.</>}
      itens={[
        { texto: "Lançamentos com conta gerencial", pronto: true },
        { texto: "Contas ligadas a uma linha da DRE", pronto: true },
        { texto: "O que fica fora da DRE tem o motivo (natureza)", pronto: true },
      ]}
      acoes={<>
        <button type="button" className="rl-btn" onClick={() => props.onIrRelatorio("rel_dre")}>Voltar à DRE da fazenda</button>
        <button type="button" className="rl-btn" onClick={() => props.onIrRelatorio("fechamento_mes")}>Conferir o Fechamento do mês</button>
      </>}
    />
  );

  // ── peças da seção de resolver ──
  const idLinha = `${uid}-linha`, idNat = `${uid}-nat`, idConta = `${uid}-conta`;
  const tiposDaConta: ("despesa" | "receita")[] = useMemo(() => {
    const t = new Set(doMotivo.map((l) => l.tipo));
    return t.size === 1 ? [[...t][0]] : ["despesa", "receita"];
  }, [doMotivo]);

  const controleUi = (() => {
    if (acao === "linha_dre") return (
      <div className="rl-campo">
        <label htmlFor={idLinha}>Linha da DRE das contas selecionadas</label>
        <select id={idLinha} className="rl-in" value={linhaEscolhida} onChange={(e) => setLinhaEscolhida(e.target.value)} disabled={!admin}>
          <option value="">Escolher a linha…</option>
          {LINHAS_DRE.map((l) => <option key={l.valor} value={l.valor}>{l.rotulo}</option>)}
        </select>
      </div>
    );
    if (acao === "conta") return (
      <div className="rl-campo" role="group" aria-labelledby={idConta}>
        <span className="rl-rot" id={idConta}>Conta gerencial dos lançamentos selecionados</span>
        {selecionadas.length > 0 && tipoSel === null
          ? <span className="cl-barra-d">Há receita e despesa na seleção: escolha só um tipo por vez, para a conta combinar.</span>
          : <SeletorContaGerencial contas={plano} tipo={tipoSel ?? tiposDaConta[0]} codigo={contaEscolhida.codigo} nome={contaEscolhida.nome}
              onSelect={(codigo, nome) => setContaEscolhida({ codigo, nome })} placeholder="Escolher a conta…" />}
      </div>
    );
    return (<>
      <div className="rl-campo">
        <label htmlFor={idNat}>Por que fica fora da DRE</label>
        <select id={idNat} className="rl-in" value={naturezaEscolhida} onChange={(e) => setNaturezaEscolhida(e.target.value)} disabled={!admin}>
          <option value="">Escolher a natureza…</option>
          {NATUREZAS_FORA.map((n) => <option key={n.valor} value={n.valor}>{n.rotulo}</option>)}
        </select>
      </div>
      <fieldset>
        <legend>Vale para</legend>
        <label><input type="radio" name={`${uid}-escopo`} checked={escopoNatureza === "conta"} onChange={() => setEscopoNatureza("conta")} disabled={!admin} /> a conta (todos os lançamentos dela)</label>
        <label><input type="radio" name={`${uid}-escopo`} checked={escopoNatureza === "lancamento"} onChange={() => setEscopoNatureza("lancamento")} disabled={!admin} /> só estes lançamentos</label>
      </fieldset>
    </>);
  })();

  const rotuloAcao = acao === "linha_dre" ? "contas" : "lançamentos";
  const linhaTabela = (l: LinhaPendencia) => {
    const lib = podeAplicar(l, acao);
    const marcada = sel.has(l.chave) && liberada(l);
    const aplicavel = sugestaoAplicavel(l);
    return (
      <tr key={l.chave} className={lib.ok ? undefined : "travada"}>
        <td className="c-sel">
          <CaixaSelecao marcado={marcada} desabilitado={!liberada(l)} onChange={(v) => alternar([l.chave], v)}
            rotulo={`Selecionar ${l.fornecedor || l.descricao || l.numero_lancamento || "o lançamento"}, ${brl(l.valor)}`} />
        </td>
        <td className="c-lanc">
          <b>{l.fornecedor || l.descricao || "Sem fornecedor"}</b>
          <span className="sub">{[l.fornecedor ? l.descricao : null, l.produto && l.produto !== l.descricao ? l.produto : null].filter(Boolean).join(" · ") || "—"}</span>
          <span className="sub">
            {l.origem_automatica && <span className="cl-chip">gerado pelo sistema</span>}
            {l.mes_fechado && <span className="cl-chip trava"><Lock size={11} aria-hidden /> mês fechado</span>}
            {l.numero_lancamento ?? "sem número"}{l.parcelas > 1 ? ` · ${l.parcelas} parcelas` : ""}{l.centro_custo ? ` · ${l.centro_custo}` : ""}
          </span>
          <button type="button" className="cl-ver rl-noprint" onClick={() => ver(l)} aria-label={`Ver o lançamento ${l.numero_lancamento ?? ""} ${destinoDaLinha(l).onde === "consultas" ? "em Consultas" : "em Contas"}`}>
            <ExternalLink size={13} aria-hidden /> {destinoDaLinha(l).onde === "consultas" ? "Ver em Consultas" : "Ver em Contas"}
          </button>
        </td>
        <td className="c-data" data-rotulo="Data">{brData(l.data)}</td>
        <td className="c-conta" data-rotulo="Conta hoje">
          {l.codigo_conta && !l.codigo_conta.startsWith("(")
            ? <>{l.codigo_conta} {l.nome_conta ?? <span className="nenhuma">(fora do plano)</span>}</>
            : <span className="nenhuma">{l.codigo_conta ? l.codigo_conta.replace(/^\(sem conta: (.*)\)$/, "sem conta · $1") : "sem conta"}</span>}
          {motivoAtivo === "natureza_nao_informada" && <span className="sub">Fora da DRE, sem dizer o motivo</span>}
          {!lib.ok && admin && <span className="sub"><Lock size={11} aria-hidden /> {lib.porque}</span>}
        </td>
        <td className="c-valor">
          {l.tipo === "receita" ? "+" : "−"} {brl(l.valor)}
          <small>{l.tipo === "receita" ? "receita" : "despesa"}</small>
        </td>
        <td className="c-sug">
          {l.sugestao && !MOTIVOS_POR_CONTA.has(motivoAtivo) ? (<>
            <span className="t"><Lightbulb size={13} aria-hidden style={{ verticalAlign: "-2px" }} /> {l.sugestao.rotulo}</span>
            <span className="m">{l.sugestao.motivo}</span>
            {aplicavel && admin && (
              <button type="button" className="rl-btn" disabled={enviando} onClick={() => aplicar(acoesDasSugestoes([l]))}
                aria-label={`Aceitar a sugestão para ${l.fornecedor || l.numero_lancamento}: ${l.sugestao.rotulo}`}>
                <CheckCircle2 size={14} aria-hidden /> Aceitar
              </button>
            )}
          </>) : <span className="mut" style={{ color: "var(--text-muted)" }}>{MOTIVOS_POR_CONTA.has(motivoAtivo) ? "" : "sem sugestão"}</span>}
        </td>
      </tr>
    );
  };

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Resultado" nome="Classificar" pergunta="O que falta classificar?"
      onIrGrupo={props.onIrGrupo} estado={estado} erro={erroAtual || regras.erro} onTentarDeNovo={() => { setErro(null); recarregar(); }}
      vazio={vazioUi} frase={frase} avisos={avisos} exportar={exportar} rotuloCmp={null}>
      <style>{CSS_CLASSIFICAR}</style>
      {fila && (<>
        <section aria-labelledby={`${uid}-mot`}>
          <h3 className="rl-tit" id={`${uid}-mot`}>Por que ficaram de fora</h3>
          <div className="cl-motivos" role="group" aria-labelledby={`${uid}-mot`}>
            {fila.por_motivo.map((m) => (
              <button key={m.motivo} type="button" className={`cl-motivo${m.quantidade === 0 && !m.travado ? " zero" : m.quantidade ? " falta" : ""}`}
                aria-pressed={m.motivo === motivoAtivo} onClick={() => abrirMotivo(m.motivo)}>
                <span className="l">{ROTULO_MOTIVO[m.motivo]}</span>
                <span className="v">{m.quantidade}<small>{m.quantidade === 1 ? "lançamento" : "lançamentos"}</small></span>
                {m.travado ? <span className="trava"><Lock size={13} aria-hidden style={{ flexShrink: 0, marginTop: 2 }} /> Travado com as regras antigas</span>
                  : m.quantidade === 0 ? <span className="ok"><CheckCircle2 size={14} aria-hidden /> nada aqui</span>
                    : <span className="s">{[m.total_despesa ? `${brl(m.total_despesa)} de despesa` : null, m.total_receita ? `${brl(m.total_receita)} de receita` : null].filter(Boolean).join(" · ")}{m.contas > 1 ? ` · ${m.contas} contas` : ""}</span>}
              </button>
            ))}
          </div>
        </section>

        <section className="rl-painel" aria-labelledby={`${uid}-res`}>
          <div className="cl-cab">
            <h3 className="rl-tit" id={`${uid}-res`} style={{ margin: 0 }}>{ROTULO_MOTIVO[motivoAtivo]}</h3>
            <p>{resumoMotivo?.explicacao}</p>
          </div>

          {resumoMotivo?.travado ? (
            <div className="cl-trava-motivo" role="status"><Lock size={18} aria-hidden /><div><b>Travado com as regras antigas.</b><p style={{ margin: ".2rem 0 0" }}>{resumoMotivo.travado}</p></div></div>
          ) : doMotivo.length === 0 ? (
            <div className="cl-vazio-motivo" role="status"><CheckCircle2 size={20} aria-hidden /> <span>Nada a classificar por este motivo em {periodo.label} ✓</span></div>
          ) : (<>
            <div className="cl-tools rl-noprint">
              <div className="rl-campo">
                <label htmlFor={`${uid}-q`}>Buscar na fila</label>
                <input id={`${uid}-q`} type="search" className="rl-in" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Fornecedor, descrição, nº ou conta" />
              </div>
              {MOTIVOS_POR_CONTA.has(motivoAtivo) && (
                <div className="rl-campo" role="group" aria-label="Filtrar por conta">
                  <span className="rl-rot">Só a conta</span>
                  <FiltroContaGerencial contas={plano} tipos={tiposDaConta} codigo={filtroConta.codigo} nome={filtroConta.nome}
                    onChange={(codigo, nome) => setFiltroConta({ codigo, nome })} />
                </div>
              )}
              <span className="cl-barra-d" aria-live="polite">{filtradas.length === doMotivo.length ? `${filtradas.length} na fila` : `${filtradas.length} de ${doMotivo.length} na fila`}</span>
            </div>

            <div className="cl-barra rl-noprint" role="group" aria-label="Classificar as linhas selecionadas">
              <p className="cl-barra-t" aria-live="polite">
                <b>{selecionadas.length} {selecionadas.length === 1 ? "selecionada" : "selecionadas"}</b>
                {selecionadas.length > 0 && <span>{[totalSel.despesa ? `${brl(totalSel.despesa)} de despesa` : null, totalSel.receita ? `${brl(totalSel.receita)} de receita` : null].filter(Boolean).join(" · ")}</span>}
                {comSugestao.length > 0 && admin && (
                  <button type="button" className="cl-ver" onClick={() => alternar(comSugestao.map((l) => l.chave), true)}>Marcar as {comSugestao.length} que têm sugestão</button>
                )}
              </p>
              <div className="cl-barra-c">
                {controleUi}
                <button type="button" className="btn-primary-gold cl-aplicar" disabled={!admin || enviando || !plan || plan.acoes.length === 0} title={admin ? undefined : PORQUE_SO_ADMIN}
                  onClick={() => plan && aplicar(plan.acoes)}>
                  {enviando ? "Gravando…" : controle && plan && plan.acoes.length ? textoDoLote(controle, plan) : "Aplicar"}
                </button>
                <button type="button" className="rl-btn" disabled={!admin || enviando || sugestoesDaSelecao.length === 0} onClick={() => aplicar(sugestoesDaSelecao)}
                  title={sugestoesDaSelecao.length ? undefined : "Marque linhas que tenham sugestão"}>
                  <Lightbulb size={14} aria-hidden /> Aceitar as sugestões ({sugestoesDaSelecao.length})
                </button>
              </div>
              <p className="cl-barra-d">
                {acao === "linha_dre" && <>A linha é <b>da conta</b>: vale para todos os lançamentos dela, em qualquer período — não só os que estão na tela.</>}
                {acao === "conta" && <>A conta vale só para os {rotuloAcao} marcados. Nada de valor, data ou pagamento muda.</>}
                {acao === "natureza" && <>Com “a conta”, todo lançamento dela passa a ter este motivo. Para colocar a conta DENTRO da DRE, mude a linha dela no plano de contas.</>}
                {plan && plan.puladas > 0 && <> {plan.puladas} marcada{plan.puladas === 1 ? "" : "s"} ficará{plan.puladas === 1 ? "" : "ão"} de fora (travada{plan.puladas === 1 ? "" : "s"}).</>}
                {" "}Tudo fica registrado e dá para desfazer.
              </p>
            </div>

            <div className="rl-tw cl-tw">
              <table className="fazenda-table rl-tab cl-tab">
                <caption className="rl-sr">{ROTULO_MOTIVO[motivoAtivo]}: {filtradas.length} lançamentos, em {periodo.label}</caption>
                <thead>
                  <tr>
                    <th scope="col" className="cl-sel">
                      <CaixaSelecao marcado={marcaveis.length > 0 && selecionadas.length === marcaveis.length} parcial={selecionadas.length > 0}
                        desabilitado={marcaveis.length === 0} onChange={(v) => alternar(marcaveis.map((l) => l.chave), v)}
                        rotulo="Selecionar todas as linhas liberadas" />
                    </th>
                    <th scope="col">Lançamento</th><th scope="col">Data</th><th scope="col">Conta hoje</th>
                    <th scope="col" className="r">Valor</th><th scope="col">Sugestão</th>
                  </tr>
                </thead>
                <tbody>
                  {mostradas.map((g) => {
                    const doGrupo = g.linhas.filter(liberada);
                    const marcadas = doGrupo.filter((l) => sel.has(l.chave)).length;
                    const aplicavel = g.sugestao && g.linhas.some(sugestaoAplicavel);
                    return (
                      <Fragment key={g.chave || "todas"}>
                        {MOTIVOS_POR_CONTA.has(motivoAtivo) && (
                          <tr className="cl-grupo">
                            <th scope="colgroup" colSpan={6}>
                              <div className="cl-grupo-in">
                                <label>
                                  <CaixaSelecao marcado={doGrupo.length > 0 && marcadas === doGrupo.length} parcial={marcadas > 0} desabilitado={doGrupo.length === 0}
                                    onChange={(v) => alternar(doGrupo.map((l) => l.chave), v)} rotulo={`Selecionar os lançamentos da conta ${g.codigo ?? "sem código"}`} />
                                  <span><b>{g.codigo ?? "Sem código"}</b> {g.nome ?? (g.noPlano ? "" : "(conta fora do plano)")}</span>
                                </label>
                                <span className="qtd">{g.quantidade} {g.quantidade === 1 ? "lançamento" : "lançamentos"} · {[g.totalDespesa ? `${brl(g.totalDespesa)} de despesa` : null, g.totalReceita ? `${brl(g.totalReceita)} de receita` : null].filter(Boolean).join(" · ")}</span>
                              </div>
                              {g.sugestao && (
                                <div className="cl-grupo-sug">
                                  <span><Lightbulb size={13} aria-hidden style={{ verticalAlign: "-2px" }} /> <b>{g.sugestao.rotulo}</b></span>
                                  <span className="m">{g.sugestao.motivo}</span>
                                  {aplicavel && admin && (
                                    <button type="button" className="rl-btn" disabled={enviando} onClick={() => aplicar(acoesDasSugestoes(g.linhas))}
                                      aria-label={`Aceitar a sugestão para a conta ${g.codigo}: ${g.sugestao.rotulo}`}>
                                      <CheckCircle2 size={14} aria-hidden /> Aceitar
                                    </button>
                                  )}
                                </div>
                              )}
                            </th>
                          </tr>
                        )}
                        {g.linhas.map(linhaTabela)}
                      </Fragment>
                    );
                  })}
                  {mostradas.length === 0 && (
                    <tr><td colSpan={6} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhuma linha com esse filtro.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {filtradas.length > visiveis && (
              <p className="cl-mais rl-noprint">
                <span>Mostrando {visiveis} de {filtradas.length}.</span>
                <button type="button" className="rl-btn" onClick={() => setVisiveis((v) => v + POR_PAGINA)}>Mostrar mais {Math.min(POR_PAGINA, filtradas.length - visiveis)}</button>
              </p>
            )}
          </>)}
        </section>

        <NotasMetodo titulo="Como a fila é montada e o que muda quando você classifica"
          entra={[
            ["De onde vem", "Do servidor: os mesmos lançamentos e itens que a DRE lê, no mesmo período, regime e centro de custo. A soma da fila fecha com o “sem classificação” da DRE."],
            ["Conta sem linha da DRE", "A conta existe mas não tem linha (nem herdada da conta-mãe). Escolher a linha vale para todos os lançamentos da conta."],
            ["Lançamento sem conta", "Escolher a conta grava só no lançamento (ou no item) marcado; valor, data e pagamento não mudam."],
            ["Fora da DRE sem motivo", "Contas marcadas como “não entra na DRE” sem natureza. Só com as regras novas."],
            ["Sugestões", "Pelo nome da conta, pelas contas irmãs, pelo histórico do fornecedor. Nunca são aplicadas sozinhas."],
          ]}
          naoEntra={[
            "Mês fechado: mudar a conta de um lançamento dele exige reabrir o mês em Fechamento do mês. A linha da DRE de uma conta vale para todos os meses e avisa quais meses fechados mudam.",
            "Desfazer devolve o valor de antes só onde ninguém mudou à mão depois.",
          ]}>
          <p style={{ margin: ".7rem 0 0" }}>
            Conferir o resultado depois de classificar: <button type="button" className="rl-linkbtn" style={{ color: "var(--text-accent)", fontWeight: 700 }} onClick={() => props.onIrRelatorio("rel_dre")}>DRE da fazenda</button>.
          </p>
        </NotasMetodo>
      </>)}
    </RelatorioShell>
  );
}
