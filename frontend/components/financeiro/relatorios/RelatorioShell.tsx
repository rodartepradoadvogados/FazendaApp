"use client";
// Molde ÚNICO dos Relatórios do Financeiro (Fase B do redesenho — mockup
// aprovado, PLANO.md §3). Ordem fixa, igual em toda tela:
//   1. barra de contexto global (URL) + onde estou / voltar um nível
//   2. pergunta no título
//   3. frase-resumo escrita
//   4. faixa de KPIs (1 principal + 3 de apoio, variação em texto + seta, clicáveis)
//   5. gráfico principal (slot) com a tabela equivalente para leitor de tela
//   6. tabela Atual | Comparação | Δ | Δ% (o detalhe sempre fecha com o total)
//   7. notas de método recolhidas
// e os estados: carregando, vazio que ensina, erro com recuperação.
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight, Circle, CircleCheck, Info, List, RotateCcw, Undo2 } from "lucide-react";
import { getFazendaAtual } from "@/lib/api";
import { exportarRelatorioExcel, exportarRelatorioPDF, linhaDeContexto, type RelatorioParaExportar } from "@/lib/export";
import {
  REGIME_NOME, delta, formatar, formatarDelta, pctSinal, type FormatoNumero, type SentidoBom,
} from "@/lib/relatorioContexto";
import { CSS_RELATORIO } from "./estilos";
import { BarraContexto, type AcaoExportar } from "./BarraContexto";
import type { ContextoRelatorio } from "./useContextoRelatorio";

// ── Movimento ─────────────────────────────────────────────────────────────
export function useMovimentoReduzido(): boolean {
  const [reduz, setReduz] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const aplicar = () => setReduz(mq.matches);
    aplicar();
    mq.addEventListener("change", aplicar);
    return () => mq.removeEventListener("change", aplicar);
  }, []);
  return reduz;
}

/** Número que conta até o valor (entrada 300 ms; troca de contexto 420 ms, do alvo anterior ao novo).
 *  O texto final é sempre o valor exato; com movimento reduzido, aparece direto. */
export function NumeroAnimado({ valor, formato }: { valor: number; formato: FormatoNumero }) {
  const reduz = useMovimentoReduzido();
  const [mostrado, setMostrado] = useState(valor);
  const alvoAnterior = useRef<number | null>(null);
  useEffect(() => {
    const de = alvoAnterior.current;
    alvoAnterior.current = valor;
    if (reduz || de === valor) { setMostrado(valor); return; }
    const inicio = de ?? 0, dur = de == null ? 300 : 420, t0 = performance.now();
    let raf = 0;
    const passo = (t: number) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      setMostrado(k >= 1 ? valor : inicio + (valor - inicio) * e);
      if (k < 1) raf = requestAnimationFrame(passo);
    };
    raf = requestAnimationFrame(passo);
    return () => cancelAnimationFrame(raf);
  }, [valor, reduz]);
  return <>{formatar(mostrado, formato)}</>;
}

// ── Variação (chip e célula) ──────────────────────────────────────────────
type Cmp = { valor: number | null | undefined; rotulo: string } | null;

export function ChipVariacao({ a, cmp, bom, formato }: { a: number | null; cmp: Cmp; bom: SentidoBom; formato: FormatoNumero }) {
  if (!cmp) return null;
  if (cmp.valor == null || a == null) return <span className="rl-dl">sem dados de {cmp.rotulo}</span>;
  const d = delta(a, cmp.valor, bom);
  if (!d) return null;
  if (d.igual) return <span className="rl-dl">= igual a {cmp.rotulo}</span>;
  const cls = d.melhor == null ? "" : d.melhor ? " bom" : " ruim";
  const palavra = d.melhor == null ? (d.abs > 0 ? "acima de" : "abaixo de") : d.melhor ? "melhor que" : "pior que";
  const pctTxt = d.pct != null && formato !== "pct" && Math.abs(d.pct) < 9.995 ? ` (${pctSinal(d.pct)})` : "";
  return (
    <span className={`rl-dl${cls}`}>
      <span aria-hidden>{d.abs > 0 ? "▲" : "▼"}</span> {formatarDelta(d.abs, formato)}{pctTxt} · {palavra} {cmp.rotulo}
    </span>
  );
}

// ── KPIs ──────────────────────────────────────────────────────────────────
export type KpiDef = {
  chave: string; rotulo: string; valor: number | null; formato: FormatoNumero; unidade?: string;
  cmp?: number | null; bom: SentidoBom; sub?: ReactNode; selo?: ReactNode; onAbrir?: () => void; negativoEmVermelho?: boolean;
};

function Kpi({ k, principal, rotuloCmp }: { k: KpiDef; principal: boolean; rotuloCmp: string | null }) {
  const Tag = k.onAbrir ? "button" : "div";
  const texto = k.valor == null ? "sem valor" : `${formatar(k.valor, k.formato)}${k.unidade || ""}`;
  return (
    <Tag {...(k.onAbrir ? { type: "button" as const, onClick: k.onAbrir, "aria-label": `${k.rotulo}: ${texto}. Abrir o detalhe` } : {})}
      className={`rl-kpi${principal ? " principal" : ""}`}>
      <span className="l">{k.rotulo}{k.selo}</span>
      <span className={`v${k.negativoEmVermelho && (k.valor ?? 0) < 0 ? " neg" : ""}`}>
        {k.valor == null ? "—" : <><NumeroAnimado valor={k.valor} formato={k.formato} />{k.unidade && <span className="u">{k.unidade}</span>}</>}
      </span>
      {rotuloCmp && <ChipVariacao a={k.valor} cmp={{ valor: k.cmp, rotulo: rotuloCmp }} bom={k.bom} formato={k.formato} />}
      {k.sub && <span className="s">{k.sub}</span>}
      {k.onAbrir && <span className="ir" aria-hidden>Ver o detalhe <ChevronRight size={13} /></span>}
    </Tag>
  );
}

export function FaixaKpis({ kpis, rotuloCmp }: { kpis: KpiDef[]; rotuloCmp: string | null }) {
  return (
    <div className="rl-kpis">
      {kpis.map((k, i) => <Kpi key={k.chave} k={k} principal={i === 0} rotuloCmp={rotuloCmp} />)}
    </div>
  );
}

// ── Tabela Atual | Comparação | Δ | Δ% ────────────────────────────────────
export type LinhaTabela = {
  chave: string; nome: ReactNode; textoNome: string; sub?: ReactNode; a: number | null; b?: number | null;
  bom?: SentidoBom; formato?: FormatoNumero; tot?: boolean; ind?: boolean; zero?: boolean; extra?: ReactNode;
  onAbrir?: () => void; rotuloAbrir?: string;
};

export function TabelaComparacao({ titulo, linhas, rotuloCmp, formato = "brl", colunaNome = "Linha", colunaExtra, rodape }: {
  titulo: string; linhas: LinhaTabela[]; rotuloCmp: string | null; formato?: FormatoNumero; colunaNome?: string;
  colunaExtra?: string; rodape?: LinhaTabela;
}) {
  const comCmp = !!rotuloCmp;
  const celulas = (l: LinhaTabela) => {
    const f = l.formato || formato;
    const d = comCmp ? delta(l.a, l.b, l.bom || "sobe") : null;
    const val = (v: number | null | undefined) => (v == null ? <span className="mut">—</span> : <span className={v < 0 ? "neg" : undefined}>{formatar(v, f)}</span>);
    return (<>
      <td className="r">{l.a == null ? <span className="mut">—</span> : val(l.a)}</td>
      {comCmp && <td className="r mut">{val(l.b)}</td>}
      {comCmp && (
        <td className="r">
          {!d ? <span className="mut">—</span> : d.igual ? <span className="mut" title="igual">=</span> : (
            <span className={`rl-dt ${d.melhor == null ? "neu" : d.melhor ? "bom" : "ruim"}`}>
              <span aria-hidden>{d.abs > 0 ? "▲" : "▼"}</span>{formatarDelta(d.abs, f)}
              {d.melhor != null && <span className="rl-sr"> ({d.melhor ? "melhor" : "pior"})</span>}
            </span>
          )}
        </td>
      )}
      {comCmp && <td className="r mut rl-opc">{d && !d.igual && d.pct != null && f !== "pct" && Math.abs(d.pct) < 9.995 ? pctSinal(d.pct) : "—"}</td>}
      {colunaExtra && <td className="r mut rl-opc">{l.extra ?? ""}</td>}
    </>);
  };
  const linha = (l: LinhaTabela) => (
    <tr key={l.chave} className={[l.tot ? "tot" : "", l.ind ? "ind" : "", l.zero ? "zero" : "", l.onAbrir ? "clic" : ""].filter(Boolean).join(" ") || undefined}
      onClick={l.onAbrir ? (e) => { if (!(e.target as HTMLElement).closest("button")) l.onAbrir!(); } : undefined}>
      <td>
        {l.onAbrir ? (
          <button type="button" className="rl-linkbtn" onClick={l.onAbrir} aria-label={l.rotuloAbrir || `${l.textoNome}: abrir o detalhe`}>
            {l.nome}<ChevronRight size={14} aria-hidden />
          </button>
        ) : l.nome}
        {l.sub && <span className="sub">{l.sub}</span>}
      </td>
      {celulas(l)}
    </tr>
  );
  return (
    <div className="rl-tw">
      <table className="fazenda-table rl-tab">
        <caption className="rl-sr">{titulo}</caption>
        <thead>
          <tr>
            <th scope="col">{colunaNome}</th>
            <th scope="col" className="r">Atual</th>
            {comCmp && <th scope="col" className="r">{rotuloCmp}</th>}
            {comCmp && <th scope="col" className="r">Δ</th>}
            {comCmp && <th scope="col" className="r rl-opc">Δ%</th>}
            {colunaExtra && <th scope="col" className="r rl-opc">{colunaExtra}</th>}
          </tr>
        </thead>
        <tbody>{linhas.map(linha)}</tbody>
        {rodape && (
          <tfoot>
            <tr><td>{rodape.nome}</td>{celulas(rodape)}</tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

// ── Gráfico (slot) + tabela equivalente ───────────────────────────────────
export function PainelGrafico({ titulo, children, tabela, legenda }: {
  titulo: string; children: ReactNode; legenda?: ReactNode; tabela: { cabecalho: string[]; linhas: string[][] };
}) {
  return (
    <section className="rl-painel rl-graf" aria-label={titulo}>
      <h3 className="rl-tit">{titulo}</h3>
      {children}
      {legenda && <div className="rl-leg">{legenda}</div>}
      <details className="rl-astab rl-noprint">
        <summary><List size={14} aria-hidden /> Ver os dados do gráfico em tabela</summary>
        <div className="rl-tw" style={{ marginTop: ".5rem" }}>
          <table className="fazenda-table rl-tab">
            <caption className="rl-sr">{titulo}</caption>
            <thead><tr>{tabela.cabecalho.map((h, i) => <th key={h} scope="col" className={i ? "r" : undefined}>{h}</th>)}</tr></thead>
            <tbody>{tabela.linhas.map((l, i) => (
              <tr key={i}>{l.map((c, j) => (j === 0 ? <th key={j} scope="row" style={{ textAlign: "left", fontWeight: 500 }}>{c}</th> : <td key={j} className="r">{c}</td>))}</tr>
            ))}</tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

// ── Notas de método, vazio, erro ──────────────────────────────────────────
export function NotasMetodo({ titulo = "Como este número é feito", entra, naoEntra, children }: {
  titulo?: string; entra: [string, ReactNode][]; naoEntra?: ReactNode[]; children?: ReactNode;
}) {
  return (
    <details className="rl-nota">
      <summary><Info size={16} aria-hidden /> {titulo}</summary>
      <div>
        <dl>{entra.map(([t, d]) => <Fragment key={t}><dt>{t}</dt><dd>{d}</dd></Fragment>)}</dl>
        {naoEntra && naoEntra.length > 0 && (
          <div style={{ marginTop: ".6rem" }}><b>Não entra neste número</b><ul>{naoEntra.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
        )}
        {children}
      </div>
    </details>
  );
}

export type ItemPendencia = { texto: string; pronto: boolean; acao?: ReactNode };
export function VazioQueEnsina({ titulo, texto, itens = [], acoes }: { titulo: string; texto: ReactNode; itens?: ItemPendencia[]; acoes?: ReactNode }) {
  const ok = itens.filter((i) => i.pronto).length;
  return (
    <div className="rl-vazio" role="status">
      <b>{titulo}</b>
      <p>{texto}</p>
      {itens.length > 0 && (<>
        <span className="prog">{ok} de {itens.length} pronto{itens.length > 1 ? "s" : ""}</span>
        <ul className="rl-chk">
          {itens.map((i) => (
            <li key={i.texto}>
              <span className={i.pronto ? "y" : "n"}>{i.pronto ? <CircleCheck size={18} aria-hidden /> : <Circle size={18} aria-hidden />}</span>
              <span>{i.texto}{!i.pronto && i.acao ? <> · {i.acao}</> : null}<span className="rl-sr"> — {i.pronto ? "pronto" : "falta"}</span></span>
            </li>
          ))}
        </ul>
      </>)}
      {acoes && <div className="rl-acoes">{acoes}</div>}
    </div>
  );
}

export function Conferencia({ fecha, texto }: { fecha: boolean; texto: ReactNode }) {
  return (
    <p className="rl-conf">
      {fecha
        ? <b className="ok"><CheckCircle2 size={15} aria-hidden /> Conferência: o total fecha</b>
        : <b className="nok"><AlertTriangle size={15} aria-hidden /> Conferência: o total NÃO fecha</b>}
      <span>{texto}</span>
    </p>
  );
}

// ── O molde ───────────────────────────────────────────────────────────────
export type Migalha = { rotulo: string; onIr?: () => void };
export type EstadoTela = "carregando" | "erro" | "vazio" | "ok";

export function RelatorioShell(props: {
  ctx: ContextoRelatorio; hoje: string; centros: string[];
  grupo: string; nome: string; pergunta: string;
  /** Níveis do drill depois do relatório (ex.: "Despesas operacionais"). */
  niveis?: Migalha[]; onVoltarNivel?: () => void; onIrGrupo?: () => void;
  estado: EstadoTela; erro?: string | null; onTentarDeNovo?: () => void; vazio?: ReactNode;
  frase?: { t: string; b?: boolean }[]; kpis?: KpiDef[]; avisos?: ReactNode;
  /** Rótulo da comparação nos chips dos KPIs quando não é um período (Fase C: "orçado"). */
  rotuloCmp?: string | null;
  children?: ReactNode;
  exportar: () => RelatorioParaExportar | null;
}) {
  const { ctx, estado } = props;
  const rotuloCmp = props.rotuloCmp !== undefined ? props.rotuloCmp : ctx.comparacao && ctx.comparacao.tipo === "periodo" ? ctx.comparacao.rotulo : null;
  const tituloRef = useRef<HTMLHeadingElement>(null);
  const fazenda = typeof window === "undefined" ? "" : getFazendaAtual()?.nome || "";
  const contextoTexto = {
    periodo: ctx.periodo.label, comparacao: ctx.comparacao ? (ctx.comparacao.tipo === "orcado" ? "o orçado" : ctx.comparacao.periodo.label) : null,
    regime: REGIME_NOME[ctx.efetivo.reg], centro: ctx.efetivo.cc === "todos" ? "todos os centros" : ctx.efetivo.cc,
  };
  // Ao subir/descer um nível, o foco vai para o título (leitor de tela anuncia onde está).
  const nivelAtual = (props.niveis ?? []).map((n) => n.rotulo).join("/");
  // Só quando a pessoa sobe/desce um nível com a tela já carregada — abrir um link
  // (ou o dado chegar) não rouba o foco.
  const nivelAnterior = useRef(nivelAtual);
  const estavaPronto = useRef(estado === "ok");
  useEffect(() => {
    const mudou = nivelAnterior.current !== nivelAtual;
    nivelAnterior.current = nivelAtual;
    if (mudou && estavaPronto.current) tituloRef.current?.focus();
    estavaPronto.current = estado === "ok";
  }, [nivelAtual, estado]);

  const onExportar = async (tipo: AcaoExportar) => {
    if (tipo === "imprimir") { window.print(); return; }
    const r = props.exportar();
    if (!r) return;
    if (tipo === "excel") await exportarRelatorioExcel(r);
    else await exportarRelatorioPDF(r);
  };
  const niveis = props.niveis ?? [];

  return (
    <div className="rl">
      <style>{CSS_RELATORIO}</style>
      <BarraContexto ctx={ctx} hoje={props.hoje} centros={props.centros} onExportar={onExportar} podeExportar={estado === "ok"} />
      <nav className="rl-mig rl-noprint" aria-label="Onde você está">
        <ol>
          <li>Relatórios</li>
          <li aria-hidden>›</li>
          <li>{props.onIrGrupo ? <button type="button" className="lk" onClick={props.onIrGrupo}>{props.grupo}</button> : props.grupo}</li>
          <li aria-hidden>›</li>
          <li>{niveis.length ? <button type="button" className="lk" onClick={niveis[0].onIr ?? props.onVoltarNivel}>{props.nome}</button> : <span aria-current="page">{props.nome}</span>}</li>
          {niveis.map((n, i) => (
            <Fragment key={n.rotulo}>
              <li aria-hidden>›</li>
              <li>{i === niveis.length - 1 ? <span aria-current="page">{n.rotulo}</span> : <button type="button" className="lk" onClick={niveis[i + 1]?.onIr}>{n.rotulo}</button>}</li>
            </Fragment>
          ))}
        </ol>
        {niveis.length > 0 && props.onVoltarNivel && (
          <button type="button" className="rl-btn" onClick={props.onVoltarNivel}><Undo2 size={14} aria-hidden /> Voltar um nível</button>
        )}
      </nav>
      <div className="rl-cab-impressao">
        <b>{fazenda ? `${fazenda} · ` : ""}{props.nome}</b>
        {linhaDeContexto(contextoTexto)} · Emitido em {new Date().toLocaleDateString("pt-BR")}
      </div>
      <header className="rl-cab">
        <h2 ref={tituloRef} tabIndex={-1}>{props.pergunta}</h2>
        <p>{[props.nome, ...niveis.map((n) => n.rotulo)].join(" › ")} · {ctx.periodo.label} · {REGIME_NOME[ctx.efetivo.reg]} · {contextoTexto.centro}</p>
      </header>
      {props.avisos}
      {estado === "carregando" && (
        <div className="rl-esq" role="status" aria-live="polite">
          <span className="rl-sr">Carregando o relatório…</span>
          <div className="skeleton" style={{ height: 28, maxWidth: 640 }} />
          <div className="rl-kpis">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: i ? 110 : 130 }} />)}</div>
          <div className="skeleton" style={{ height: 260 }} />
        </div>
      )}
      {estado === "erro" && (
        <div className="rl-aviso erro" role="alert">
          <AlertTriangle size={18} aria-hidden />
          <div>
            <b>Não foi possível carregar este relatório.</b>
            <p>{props.erro || "Erro desconhecido."} Os números não foram alterados — é só a leitura que falhou.</p>
            {props.onTentarDeNovo && (
              <p><button type="button" className="rl-btn" onClick={props.onTentarDeNovo}><RotateCcw size={14} aria-hidden /> Tentar de novo</button></p>
            )}
          </div>
        </div>
      )}
      {estado === "vazio" && props.vazio}
      {estado === "ok" && (
        <div className="rl rl-entra" key={nivelAtual}>
          {props.frase && props.frase.length > 0 && (
            <p className="rl-frase" aria-live="polite">{props.frase.map((t, i) => (t.b ? <strong key={i}>{t.t}</strong> : <Fragment key={i}>{t.t}</Fragment>))}</p>
          )}
          {props.kpis && props.kpis.length > 0 && <FaixaKpis kpis={props.kpis} rotuloCmp={rotuloCmp} />}
          {props.children}
        </div>
      )}
    </div>
  );
}
