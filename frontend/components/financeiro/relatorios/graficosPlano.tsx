"use client";
// Gráficos do grupo Plano (Fase C): o desvio orçado × realizado por linha da
// DRE (barras para os dois lados a partir do plano — SVG próprio, rótulos
// longos legíveis em qualquer largura, cada linha abre a DRE) e o saldo de caixa
// de 12 meses dos cenários (recharts). Cores só por token; verde/vermelho só
// para melhor/pior, sempre com a palavra ao lado.
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { brl, mesCurto, num, MENOS } from "@/lib/relatorioContexto";
import type { DesvioLinha } from "@/lib/relatorioOrcamento";
import { useMovimentoReduzido } from "./RelatorioShell";

function useLargura<T extends HTMLElement>(padrao = 880) {
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

const compacto = (v: number) => {
  const a = Math.abs(v), s = v < 0 ? MENOS : v > 0 ? "+" : "";
  if (a >= 1e6) return `${s}${num(a / 1e6, 1)} mi`;
  if (a >= 1000) return `${s}${num(a / 1000, a >= 1e4 ? 0 : 1)} mil`;
  return `${s}${num(a, 0)}`;
};
const sinal = (v: number, casas: number) => `${v > 0 ? "+" : v < 0 ? MENOS : ""}R$ ${num(v, casas)}`;

/** Desvio (realizado − orçado) por linha da DRE: à esquerda abaixo do plano, à direita acima.
 *  A cor diz melhor/pior (custo abaixo do plano é melhor), e o texto ao lado também. */
export function DesvioPorLinha({ linhas, porLitro, onAbrir, descricao }: {
  linhas: DesvioLinha[]; porLitro: boolean; onAbrir?: (chave: string) => void; descricao: string;
}) {
  const [ref, W] = useLargura<HTMLDivElement>();
  const estreito = W < 640;
  const LW = estreito ? 112 : 210, TW = estreito ? 118 : 270, rh = estreito ? 34 : 32, T = 4;
  const vals = linhas.map((l) => (porLitro ? l.desvioL : l.desvio) ?? 0);
  const mx = Math.max(...vals.map(Math.abs), 1e-9);
  const meio = LW + (W - LW - TW) / 2, meia = (W - LW - TW) / 2 - 6;
  const H = T + linhas.length * rh + 22;
  const tecla = (e: KeyboardEvent, chave: string) => { if (onAbrir && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onAbrir(chave); } };
  return (
    <div ref={ref}>
      <svg className="rl-svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={descricao}>
        <defs>
          <pattern id="rlp-pior" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="5" height="5" style={{ fill: "var(--st-venc-fg)" }} />
            <line x1="0" y1="0" x2="0" y2="5" style={{ stroke: "var(--st-venc-bg)" }} strokeWidth="1.4" />
          </pattern>
        </defs>
        <line x1={meio} x2={meio} y1={T - 2} y2={H - 20} style={{ stroke: "var(--text)" }} strokeWidth={1.2} />
        {linhas.map((l, i) => {
          const y = T + i * rh, v = vals[i], w = (Math.abs(v) / mx) * meia;
          const sem = (porLitro ? l.desvioL : l.desvio) == null;
          const fill = sem ? "none" : l.melhor == null ? "var(--rl-n3)" : l.melhor ? "var(--st-pago-fg)" : "url(#rlp-pior)";
          const nome = estreito && l.nome.length > 16 ? `${l.nome.slice(0, 15)}…` : l.nome;
          const valor = sem ? "" : porLitro ? sinal(v, 3) + "/L" : estreito ? compacto(v) : sinal(v, 0);
          const palavra = sem ? "sem orçamento" : l.melhor == null ? "no plano" : l.melhor ? "melhor" : "pior";
          return (
            <g key={l.chave} {...(onAbrir ? {
              role: "button", tabIndex: 0, style: { cursor: "pointer" }, onClick: () => onAbrir(l.chave), onKeyDown: (e: KeyboardEvent) => tecla(e, l.chave),
              "aria-label": `${l.nome}: ${sem ? "sem orçamento" : `${valor}, ${l.texto}`}. Abrir na DRE`,
            } : {})}>
              <rect x={0} y={y} width={W} height={rh} style={{ fill: "transparent" }} />
              <text x={LW - 10} y={y + rh / 2 + 4} textAnchor="end">{nome}</text>
              {!sem && w > 0 && (
                <rect className={`rl-degrau${v < 0 ? " esq" : ""}`} style={{ ["--i" as string]: i, fill } as React.CSSProperties}
                  x={v < 0 ? meio - w : meio} y={y + 8} width={Math.max(1.5, w)} height={rh - 16}>
                  <title>{`${l.nome}: ${valor} · ${l.texto}`}</title>
                </rect>
              )}
              {sem && <text x={meio + 6} y={y + rh / 2 + 4} style={{ fontStyle: "italic" }}>—</text>}
              <text x={W - 4} y={y + rh / 2 + 4} textAnchor="end" className="forte"
                style={{ fill: sem || l.melhor == null ? "var(--text-muted)" : l.melhor ? "var(--st-pago-fg)" : "var(--st-venc-fg)" }}>
                {valor ? `${valor} · ` : ""}{palavra}
              </text>
            </g>
          );
        })}
        <text x={meio - 6} y={H - 4} textAnchor="end">◀ abaixo do plano</text>
        <text x={meio + 6} y={H - 4}>acima do plano ▶</text>
      </svg>
    </div>
  );
}

export function LegendaDesvio() {
  return (<>
    <span><i style={{ background: "var(--st-pago-fg)" }} />Melhor que o plano</span>
    <span><i style={{ background: "repeating-linear-gradient(45deg,var(--st-venc-fg) 0 3px,var(--st-venc-bg) 3px 4.5px)" }} />Pior que o plano</span>
    <span><i style={{ background: "var(--rl-n3)" }} />No plano</span>
  </>);
}

// ── Saldo de caixa de 12 meses: real e cenários ──
export type SerieSaldo = { nome: string; vals: number[]; estilo: "real" | "a" | "b" | "c" };
const ESTILO: Record<SerieSaldo["estilo"], { cor: string; w: number; dash?: string }> = {
  real: { cor: "var(--rl-n2)", w: 1.8, dash: "5 4" },
  a: { cor: "var(--rl-a)", w: 3 },
  b: { cor: "var(--rl-n1)", w: 2.2, dash: "8 3" },
  c: { cor: "var(--text-muted)", w: 2.2, dash: "2 3" },
};

export function GraficoSaldo({ rotulos, series, reserva, descricao }: { rotulos: string[]; series: SerieSaldo[]; reserva: number; descricao: string }) {
  const reduz = useMovimentoReduzido();
  const dados = rotulos.map((rot, i) => Object.fromEntries([["rot", rot], ...series.map((s, k) => [`s${k}`, s.vals[i]])]));
  const fmt = (v: number) => compacto(v).replace(/^\+/, "");
  return (
    <div role="img" aria-label={descricao} style={{ width: "100%", height: 300 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={dados} margin={{ top: 10, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="rot" tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--border-strong, var(--border))" }} interval="preserveStartEnd" minTickGap={6} />
          <YAxis tickFormatter={fmt} tick={{ fill: "var(--text-muted)", fontSize: 11 }} width={56} tickLine={false} axisLine={false} />
          <ReferenceLine y={0} stroke="var(--st-venc-fg)" strokeWidth={1} />
          {reserva > 0 && <ReferenceLine y={reserva} stroke="var(--text-muted)" strokeDasharray="3 3"
            label={{ value: `reserva ${brl(reserva, 0)}`, position: "insideTopLeft", fill: "var(--text-muted)", fontSize: 11 }} />}
          <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" }}
            formatter={(v, nome) => [brl(Number(v), 0), String(nome)]} />
          {series.map((s, k) => {
            const e = ESTILO[s.estilo];
            return <Line key={s.nome + k} dataKey={`s${k}`} name={s.nome} stroke={e.cor} strokeWidth={e.w} strokeDasharray={e.dash}
              dot={{ r: 2.5, fill: e.cor, strokeWidth: 0 }} isAnimationActive={!reduz} animationDuration={420} />;
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LegendaSaldo({ series }: { series: SerieSaldo[] }) {
  return (<>
    {series.map((s) => {
      const e = ESTILO[s.estilo];
      return (
        <span key={s.nome}>
          <svg width="22" height="10" aria-hidden><line x1="0" y1="5" x2="22" y2="5" style={{ stroke: e.cor }} strokeWidth={e.w} strokeDasharray={e.dash} /></svg>
          {s.nome}
        </span>
      );
    })}
    <span><svg width="22" height="10" aria-hidden><line x1="0" y1="5" x2="22" y2="5" style={{ stroke: "var(--st-venc-fg)" }} strokeWidth={1} /></svg>saldo zero</span>
  </>);
}

export const rotuloMes = (ym: string) => mesCurto(ym);
