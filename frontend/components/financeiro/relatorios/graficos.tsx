"use client";
// Gráficos dos Relatórios (Fase B): a cascata em degraus da DRE (SVG próprio —
// rótulos longos legíveis em qualquer largura, cada degrau clicável) e o
// "preço × custo por litro" de 12 meses (recharts), com a sobra preenchida
// entre as duas linhas. Cores só por token; o "sai" é hachurado (não só cor).
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Degrau } from "@/lib/relatorioDre";
import type { PontoLitro } from "@/lib/relatorioLitro";
import { brl, mesCurto, num, MENOS } from "@/lib/relatorioContexto";
import { useMovimentoReduzido } from "./RelatorioShell";
import { useMorph } from "./movimento";

export function useLargura<T extends HTMLElement>(padrao = 880) {
  const ref = useRef<T>(null);
  const [w, setW] = useState(padrao);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const medir = () => setW(Math.max(280, Math.round(el.clientWidth)));
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export const compacto = (v: number) => {
  const a = Math.abs(v), s = v < 0 ? MENOS : "";
  if (a >= 1e6) return `${s}${num(a / 1e6, 1)} mi`;
  if (a >= 1000) return `${s}${num(a / 1000, a >= 1e4 ? 0 : 1)} mil`;
  return `${s}${num(a, 0)}`;
};

/** Padrões de preenchimento (hachuras) — definidos uma vez por gráfico. */
function Padroes({ id }: { id: string }) {
  return (
    <defs>
      <pattern id={`${id}-sai`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" style={{ fill: "var(--rl-n3)" }} />
        <line x1="0" y1="0" x2="0" y2="6" style={{ stroke: "var(--rl-n1)" }} strokeWidth="2" />
      </pattern>
      <pattern id={`${id}-neg`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
        <rect width="6" height="6" style={{ fill: "var(--st-venc-bg)" }} />
        <line x1="0" y1="0" x2="0" y2="6" style={{ stroke: "var(--st-venc-fg)" }} strokeWidth="1.6" />
      </pattern>
    </defs>
  );
}

/** Cascata em degraus, horizontal. `onAbrir` abre o detalhe da linha (clique ou Enter). */
export function CascataDegraus({ degraus, onAbrir, descricao }: { degraus: Degrau[]; onAbrir?: (chave: string) => void; descricao: string }) {
  const [ref, W] = useLargura<HTMLDivElement>();
  // Continuidade (MOVIMENTO.md §2): ao trocar o contexto, cada degrau morfa do tamanho antigo ao novo.
  useMorph(ref, degraus);
  const estreito = W < 600;
  const LW = estreito ? 118 : 230, VW = estreito ? 70 : 112, rh = estreito ? 30 : 32, T = 6;
  const H = T + degraus.length * rh + 6;
  const vals = degraus.flatMap((d) => [d.ini, d.fim]).concat(0);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const x = (v: number) => LW + ((v - mn) / (mx - mn || 1)) * (W - LW - VW - 10);
  const id = "rlc";
  const tecla = (e: KeyboardEvent, chave: string) => { if (onAbrir && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onAbrir(chave); } };
  return (
    <div ref={ref}>
      <svg className="rl-svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={descricao}>
        <Padroes id={id} />
        <line x1={x(0)} x2={x(0)} y1={T - 4} y2={H - 2} style={{ stroke: "var(--border-strong, var(--border))" }} />
        {degraus.map((d, i) => {
          const y = T + i * rh, a = Math.min(d.ini, d.fim), b = Math.max(d.ini, d.fim);
          const w = Math.max(1.5, x(b) - x(a));
          const fill = d.resultado ? (d.v < 0 ? `url(#${id}-neg)` : "var(--rl-a)") : d.subtotal ? "var(--rl-n1)" : d.v >= 0 ? "var(--rl-n2)" : `url(#${id}-sai)`;
          const nome = estreito && d.nome.length > 17 ? `${d.nome.slice(0, 16)}…` : d.nome;
          const valorTxt = `${d.subtotal ? "" : d.v >= 0 ? "+" : ""}${estreito ? compacto(d.v) : brl(d.v, 0)}`;
          const prox = degraus[i + 1];
          return (
            <g key={d.chave} {...(onAbrir ? {
              role: "button", tabIndex: 0, style: { cursor: "pointer" }, onClick: () => onAbrir(d.chave), onKeyDown: (e: KeyboardEvent) => tecla(e, d.chave),
              "aria-label": `${d.nome}: ${brl(d.v)}. Abrir o detalhe`,
            } : {})}>
              <rect x={0} y={y} width={W} height={rh} style={{ fill: "transparent" }} />
              <text x={LW - 10} y={y + rh / 2 + 4} textAnchor="end" className={d.subtotal ? "forte" : undefined}>{nome}</text>
              <rect data-m={`deg:${d.chave}`} className={`rl-degrau${d.v < 0 && !d.subtotal ? " esq" : ""}`} style={{ ["--i" as string]: i, fill, stroke: d.resultado ? (d.v < 0 ? "var(--st-venc-fg)" : "var(--rl-a)") : "none" } as React.CSSProperties}
                x={x(a)} y={y + 6} width={w} height={rh - 12}>
                <title>{`${d.nome}: ${brl(d.v)}`}</title>
              </rect>
              {prox && !prox.subtotal && <line x1={x(d.fim)} x2={x(d.fim)} y1={y + rh - 6} y2={y + rh + 6} style={{ stroke: "var(--border-strong, var(--border))", strokeDasharray: "2 2" }} />}
              <text x={W - 4} y={y + rh / 2 + 4} textAnchor="end" className={d.subtotal ? "forte" : undefined}
                style={d.resultado && d.v < 0 ? { fill: "var(--st-venc-fg)" } : { fill: "var(--text)" }}>{valorTxt}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function LegendaCascata() {
  return (<>
    <span><i style={{ background: "var(--rl-n2)" }} />Entra (soma)</span>
    <span><i style={{ background: "repeating-linear-gradient(45deg,var(--rl-n3) 0 3px,var(--rl-n1) 3px 5px)" }} />Sai (subtrai)</span>
    <span><i style={{ background: "var(--rl-n1)" }} />Subtotal</span>
    <span><i style={{ background: "var(--rl-a)" }} />Resultado</span>
  </>);
}

/** Nomes das duas linhas e das faixas (padrão: preço × custo por litro). Fase C: o RMCA usa o mesmo
 *  gráfico com receita × comida por vaca/dia — um componente só, mudam os rótulos e a unidade. */
export type NomesDuasLinhas = { preco: string; custo: string; sobra: string; falta: string; sufixo: string };
const NOMES_LITRO: NomesDuasLinhas = {
  preco: "Preço líquido", custo: "Custo de custeio (COE/L)", sobra: "Sobra do custeio", falta: "Falta", sufixo: "/L",
};

/** Preço líquido × custo de custeio por litro, 12 meses; a área entre as linhas é a sobra (ou a falta, hachurada). */
export function GraficoPrecoCusto({ pontos, descricao, nomes = NOMES_LITRO, cursor, altura = 280, duracao = 450 }: {
  pontos: PontoLitro[]; descricao: string;
  /** Rótulos das linhas e unidade (C2: o RMCA usa receita × comida por vaca/dia). */
  nomes?: NomesDuasLinhas;
  /** Mês sob o cursor do "Reproduzir o ano" (competência AAAA-MM). */
  cursor?: string | null; altura?: number;
  /** A apresentação narrada desenha mais devagar; o uso diário fica em 450 ms. */
  duracao?: number;
}) {
  const reduz = useMovimentoReduzido();
  const dados = pontos.map((p) => ({ ...p, rot: mesCurto(p.comp) }));
  const fmt = (v: number) => `R$ ${num(v, 2)}`;
  // Eixo largo o bastante para "R$ 25,00" (RMCA por vaca/dia) sem quebrar o rótulo.
  const maior = Math.max(0, ...pontos.flatMap((p) => [Math.abs(p.preco ?? 0), Math.abs(p.custo ?? 0)]));
  const larguraEixo = maior >= 100 ? 86 : maior >= 10 ? 76 : 64;
  return (
    <div role="img" aria-label={descricao} style={{ width: "100%", height: altura }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={dados} margin={{ top: 10, right: 16, bottom: 4, left: 4 }}>
          <defs>
            <pattern id="rll-neg" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
              <rect width="6" height="6" style={{ fill: "var(--st-venc-bg)" }} />
              <line x1="0" y1="0" x2="0" y2="6" style={{ stroke: "var(--st-venc-fg)" }} strokeWidth="1.6" />
            </pattern>
          </defs>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="rot" tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--border-strong, var(--border))" }} interval="preserveStartEnd" minTickGap={8} />
          <YAxis tickFormatter={fmt} tick={{ fill: "var(--text-muted)", fontSize: 11 }} width={larguraEixo} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" }}
            formatter={(v, nome) => (Array.isArray(v) ? [`${fmt(Number(v[1]) - Number(v[0]))}${nomes.sufixo}`, String(nome)] : [`${fmt(Number(v))}${nomes.sufixo}`, String(nome)])} />
          <Area dataKey="faixaPos" name={nomes.sobra} stroke="none" fill="var(--rl-margem)" isAnimationActive={!reduz} animationDuration={duracao} connectNulls={false} />
          <Area dataKey="faixaNeg" name={nomes.falta} stroke="none" fill="url(#rll-neg)" isAnimationActive={!reduz} animationDuration={duracao} connectNulls={false} />
          <Line dataKey="custo" name={nomes.custo} stroke="var(--rl-n1)" strokeWidth={2.2} dot={{ r: 3, fill: "var(--rl-n1)" }} isAnimationActive={!reduz} animationDuration={duracao} connectNulls={false} />
          {cursor && <ReferenceLine x={mesCurto(cursor)} stroke="var(--text)" strokeDasharray="3 3" strokeWidth={1.5} ifOverflow="extendDomain" />}
          <Line dataKey="preco" name={nomes.preco} stroke="var(--rl-a)" strokeWidth={2.6} dot={{ r: 3, fill: "var(--rl-a)" }} isAnimationActive={!reduz} animationDuration={duracao} connectNulls={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LegendaPrecoCusto({ textos }: { textos?: [string, string, string, string] } = {}) {
  const [a, b, c, d] = textos ?? ["Preço líquido do leite", "Custo de custeio por litro", "Sobra (preço acima do custo)", "Falta (custo acima do preço)"];
  return (<>
    <span style={{ color: "var(--rl-a)" }}><i className="ln" />{a}</span>
    <span style={{ color: "var(--rl-n1)" }}><i className="ln" />{b}</span>
    <span><i style={{ background: "var(--rl-margem)" }} />{c}</span>
    <span><i style={{ background: "repeating-linear-gradient(-45deg,var(--st-venc-bg) 0 3px,var(--st-venc-fg) 3px 4.5px)" }} />{d}</span>
  </>);
}
