"use client";
// Barra de contexto GLOBAL dos Relatórios: período (mês/trimestre/safra/ano/
// livre), comparar com (anterior / ano passado / outro período com seletor /
// orçado / sem comparação), regime e centro de custo — e a exportação
// (Excel, PDF, Imprimir), presente em todo relatório. O estado mora na URL
// (useContextoRelatorio); o que o relatório trava aparece desabilitado com o porquê.
import { useEffect, useId, useState } from "react";
import { Check, FileSpreadsheet, FileText, Lock, Printer, SlidersHorizontal } from "lucide-react";
import {
  MODOS_COMPARACAO, REGIME_NOME, TIPOS_PERIODO, comparacaoDe, deslocar, anoAnterior, opcoesPeriodo, periodoDe, periodoPadrao,
  resumoContexto, type ModoComparacao, type TipoPeriodo,
} from "@/lib/relatorioContexto";
import type { ContextoRelatorio } from "./useContextoRelatorio";

export type AcaoExportar = "excel" | "pdf" | "imprimir";

export function BarraContexto({ ctx, hoje, centros, onExportar, podeExportar }: {
  ctx: ContextoRelatorio; hoje: string; centros: string[];
  onExportar: (tipo: AcaoExportar) => Promise<void> | void; podeExportar: boolean;
}) {
  const uid = useId();
  const id = (s: string) => `${uid}-${s}`;
  const { estado, efetivo, periodo, comparacao, mudar, travas } = ctx;
  const [aberta, setAberta] = useState(false);
  const [feito, setFeito] = useState<AcaoExportar | null>(null);
  const [gerando, setGerando] = useState<AcaoExportar | null>(null);
  useEffect(() => {
    if (!feito) return;
    const t = setTimeout(() => setFeito(null), 1600);
    return () => clearTimeout(t);
  }, [feito]);

  const tipo = periodo.tipo;
  const opcoes = tipo === "l" ? [] : opcoesPeriodo(tipo, hoje, periodo.cod);
  const cmpVal: ModoComparacao = estado.cmp;

  const exportar = async (t: AcaoExportar) => {
    setGerando(t);
    try { await onExportar(t); setFeito(t); } catch { /* o aviso de erro já aparece (lib/export.ts) */ } finally { setGerando(null); }
  };

  // "Comparar com qual período": lista do mesmo tipo (o padrão marcado) ou datas livres.
  const padraoCmp = estado.cmp === "aa" ? anoAnterior(periodo) : deslocar(periodo, -1);
  const cmpAtual = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const cmpLivre = !!cmpAtual && (tipo === "l" || cmpAtual.tipo === "l");
  const mostraQual = ["ant", "aa", "outro"].includes(estado.cmp);
  const opcoesCmp = tipo === "l" ? [] : opcoesPeriodo(tipo, hoje, cmpAtual?.cod).filter((o) => o.v !== periodo.cod);

  const centrosOpc = Array.from(new Set(centros.filter(Boolean))).sort((a, b) => a.localeCompare(b, "pt-BR"));
  if (efetivo.cc !== "todos" && !centrosOpc.includes(efetivo.cc)) centrosOpc.unshift(efetivo.cc);

  return (
    <div className={`rl-ctx rl-noprint${aberta ? " aberta" : ""}`} role="region" aria-label="Contexto do relatório">
      <div className="rl-ctx-sum">
        <span>{resumoContexto(periodo, comparacao, efetivo.reg, efetivo.cc)}</span>
        <button type="button" className="rl-btn" aria-expanded={aberta} aria-controls={id("linha")} onClick={() => setAberta((v) => !v)}>
          <SlidersHorizontal size={15} aria-hidden /> {aberta ? "Fechar" : "Filtros"}
        </button>
      </div>
      <div className="rl-ctx-row" id={id("linha")}>
        <div className="rl-campo">
          <label htmlFor={id("tipo")}>Período</label>
          <select id={id("tipo")} className="rl-in" value={tipo}
            onChange={(e) => mudar({ per: periodoPadrao(e.target.value as TipoPeriodo, hoje).cod })}>
            {TIPOS_PERIODO.map((t) => <option key={t.v} value={t.v}>{t.rotulo}</option>)}
          </select>
        </div>
        {tipo === "l" ? (<>
          <div className="rl-campo">
            <label htmlFor={id("de")}>De</label>
            <input id={id("de")} type="date" className="rl-in" value={periodo.ini}
              onChange={(e) => e.target.value && mudar({ per: periodoDe(`l:${e.target.value}~${periodo.fim}`)?.cod ?? estado.per })} />
          </div>
          <div className="rl-campo">
            <label htmlFor={id("ate")}>Até</label>
            <input id={id("ate")} type="date" className="rl-in" value={periodo.fim}
              onChange={(e) => e.target.value && mudar({ per: periodoDe(`l:${periodo.ini}~${e.target.value}`)?.cod ?? estado.per })} />
          </div>
        </>) : (
          <div className="rl-campo">
            <label htmlFor={id("val")}>{({ m: "Qual mês", t: "Qual trimestre", s: "Qual safra", a: "Qual ano" } as Record<string, string>)[tipo]}</label>
            <select id={id("val")} className="rl-in" value={periodo.cod} onChange={(e) => mudar({ per: e.target.value })}>
              {opcoes.map((o) => <option key={o.v} value={o.v}>{o.rotulo}</option>)}
            </select>
          </div>
        )}
        <div className="rl-campo">
          <label htmlFor={id("cmp")}>Comparar com</label>
          <select id={id("cmp")} className="rl-in" value={cmpVal}
            onChange={(e) => {
              const v = e.target.value as ModoComparacao;
              if (v === "outro") {
                const q = comparacaoDe(periodo, estado.cmp === "outro" ? "ant" : estado.cmp);
                mudar({ cmp: "outro", cmpp: q && q.tipo === "periodo" ? q.periodo.cod : deslocar(periodo, -1).cod });
              } else mudar({ cmp: v });
            }}>
            {MODOS_COMPARACAO.map((m) => <option key={m.v} value={m.v} disabled={m.v === "orc" && travas.cmpOrcado === false}>{m.rotulo}{m.v === "orc" && travas.cmpOrcado === false ? " (não nesta tela)" : ""}</option>)}
          </select>
        </div>
        {mostraQual && (<>
          {tipo !== "l" && (
            <div className="rl-campo">
              <label htmlFor={id("qual")}>Comparar com qual período</label>
              <select id={id("qual")} className="rl-in" value={cmpLivre ? "__livre" : cmpAtual?.cod ?? padraoCmp.cod}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "__livre") mudar({ cmp: "outro", cmpp: `l:${(cmpAtual ?? padraoCmp).ini}~${(cmpAtual ?? padraoCmp).fim}` });
                  else mudar({ cmp: "outro", cmpp: v });
                }}>
                {opcoesCmp.map((o) => (
                  <option key={o.v} value={o.v}>{o.rotulo.replace(" (em curso)", "")}{o.v === anoAnterior(periodo).cod ? " · mesmo período do ano passado" : o.v === deslocar(periodo, -1).cod ? " · imediatamente anterior" : ""}</option>
                ))}
                <option value="__livre">Intervalo livre (datas)…</option>
              </select>
            </div>
          )}
          {cmpLivre && cmpAtual && (<>
            <div className="rl-campo">
              <label htmlFor={id("cde")}>Comparar de</label>
              <input id={id("cde")} type="date" className="rl-in" value={cmpAtual.ini}
                onChange={(e) => e.target.value && mudar({ cmp: "outro", cmpp: `l:${e.target.value}~${cmpAtual.fim}` })} />
            </div>
            <div className="rl-campo">
              <label htmlFor={id("cate")}>até</label>
              <input id={id("cate")} type="date" className="rl-in" value={cmpAtual.fim}
                onChange={(e) => e.target.value && mudar({ cmp: "outro", cmpp: `l:${cmpAtual.ini}~${e.target.value}` })} />
            </div>
          </>)}
        </>)}
        <div className="rl-campo">
          <span className="rl-rot" id={id("reg")}>Regime</span>
          <div className="rl-seg" role="group" aria-labelledby={id("reg")}>
            {(["comp", "caixa"] as const).map((r) => (
              <button key={r} type="button" aria-pressed={efetivo.reg === r} disabled={!!travas.reg}
                title={REGIME_NOME[r]} onClick={() => mudar({ reg: r })}>
                {r === "comp" ? "Mês do gasto" : "Dia do pagamento"}<span className="rl-sr"> ({r === "comp" ? "competência" : "caixa"})</span>
              </button>
            ))}
          </div>
        </div>
        <div className="rl-campo">
          <label htmlFor={id("cc")}>Centro de custo</label>
          <select id={id("cc")} className="rl-in" value={efetivo.cc} disabled={!!travas.cc} onChange={(e) => mudar({ cc: e.target.value })}>
            <option value="todos">Todos os centros</option>
            {centrosOpc.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <span className="rl-cresce" />
        <div className="rl-acoes" role="group" aria-label="Exportar o relatório">
          {(["excel", "pdf", "imprimir"] as const).map((t) => {
            const Icone = feito === t ? Check : t === "excel" ? FileSpreadsheet : t === "pdf" ? FileText : Printer;
            const rot = t === "excel" ? "Excel" : t === "pdf" ? "PDF" : "Imprimir";
            return (
              <button key={t} type="button" className={`rl-btn${feito === t ? " feito" : ""}`} disabled={!podeExportar || gerando !== null}
                onClick={() => exportar(t)} aria-live="polite">
                <Icone size={14} aria-hidden /> {gerando === t ? "Gerando…" : feito === t ? (t === "imprimir" ? "Enviado" : "Pronto") : rot}
              </button>
            );
          })}
        </div>
      </div>
      {travas.porque && <p className="rl-ctxnota"><Lock size={13} aria-hidden /> {travas.porque}</p>}
    </div>
  );
}
