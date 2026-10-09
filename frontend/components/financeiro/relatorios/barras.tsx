"use client";
// Barras dos Relatórios › Leite e Registros (Fase C): horizontais (custo por
// lote, preço por cabeça por categoria, custo da safra por categoria) — SVG
// próprio como a cascata, rótulo longo legível em qualquer largura, cada barra
// clicável (Enter/Espaço) — e verticais de 12 meses (custo do sêmen por
// prenhez). Cor só por token; custo é neutro; o segundo grupo é hachurado
// (nunca só cor). Movimento: a barra cresce (transform), nada com prefers-reduced-motion.
import type { KeyboardEvent } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { mesCurto, num } from "@/lib/relatorioContexto";
import { compacto, useLargura } from "./graficos";
import { useMovimentoReduzido } from "./RelatorioShell";

export type ItemBarra = { chave: string; nome: string; valor: number; sub?: string; hachura?: boolean; rotuloAbrir?: string };

const FUNDO_HACHURA = "repeating-linear-gradient(45deg,var(--rl-n3) 0 3px,var(--rl-n1) 3px 5px)";

export function BarrasHorizontais({ itens, fmt, descricao, onAbrir }: {
  itens: ItemBarra[]; fmt: (v: number) => string; descricao: string; onAbrir?: (chave: string) => void;
}) {
  const [ref, W] = useLargura<HTMLDivElement>();
  const estreito = W < 600;
  const LW = estreito ? 120 : 220, VW = estreito ? 78 : 120, rh = itens.some((i) => i.sub) ? 40 : 32, T = 4;
  const H = T + itens.length * rh + 4;
  const max = Math.max(...itens.map((i) => Math.abs(i.valor)), 0) || 1;
  const x = (v: number) => (Math.abs(v) / max) * (W - LW - VW - 12);
  const tecla = (e: KeyboardEvent, chave: string) => { if (onAbrir && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onAbrir(chave); } };
  return (
    <div ref={ref}>
      <svg className="rl-svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={descricao}>
        <defs>
          <pattern id="rlb-hach" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" style={{ fill: "var(--rl-n3)" }} />
            <line x1="0" y1="0" x2="0" y2="6" style={{ stroke: "var(--rl-n1)" }} strokeWidth="2" />
          </pattern>
        </defs>
        {itens.map((it, i) => {
          const y = T + i * rh;
          const nome = estreito && it.nome.length > 17 ? `${it.nome.slice(0, 16)}…` : it.nome;
          const valorTxt = estreito ? compacto(it.valor) : fmt(it.valor);
          return (
            <g key={it.chave} {...(onAbrir ? {
              role: "button", tabIndex: 0, style: { cursor: "pointer" }, onClick: () => onAbrir(it.chave), onKeyDown: (e: KeyboardEvent) => tecla(e, it.chave),
              "aria-label": it.rotuloAbrir ?? `${it.nome}: ${fmt(it.valor)}. Abrir o detalhe`,
            } : {})}>
              <rect x={0} y={y} width={W} height={rh} style={{ fill: "transparent" }} />
              <text x={LW - 10} y={y + (it.sub ? rh / 2 - 2 : rh / 2 + 4)} textAnchor="end" className="forte">{nome}</text>
              {it.sub && <text x={LW - 10} y={y + rh / 2 + 12} textAnchor="end" style={{ fontSize: 11 }}>{it.sub}</text>}
              <rect className="rl-degrau" style={{ ["--i" as string]: i, fill: it.hachura ? "url(#rlb-hach)" : it.valor < 0 ? "var(--st-venc-fg)" : "var(--rl-n1)" } as React.CSSProperties}
                x={LW} y={y + 7} width={Math.max(1.5, x(it.valor))} height={rh - 14}>
                <title>{`${it.nome}: ${fmt(it.valor)}`}</title>
              </rect>
              <text x={LW + Math.max(1.5, x(it.valor)) + 6} y={y + rh / 2 + 4} style={{ fill: "var(--text)", fontVariantNumeric: "tabular-nums" }}>{valorTxt}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function LegendaBarras({ cheio, hachura }: { cheio: string; hachura?: string }) {
  return (<>
    <span><i style={{ background: "var(--rl-n1)" }} />{cheio}</span>
    {hachura && <span><i style={{ background: FUNDO_HACHURA }} />{hachura}</span>}
  </>);
}

/** Barras verticais de 12 meses (mês sem valor fica sem barra, nunca zero inventado). */
export function Barras12Meses({ pontos, nome, fmt, descricao }: {
  pontos: { comp: string; valor: number | null }[]; nome: string; fmt: (v: number) => string; descricao: string;
}) {
  const reduz = useMovimentoReduzido();
  const dados = pontos.map((p) => ({ rot: mesCurto(p.comp), valor: p.valor }));
  return (
    <div role="img" aria-label={descricao} style={{ width: "100%", height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={dados} margin={{ top: 10, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="rot" tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--border-strong, var(--border))" }} interval="preserveStartEnd" minTickGap={8} />
          <YAxis tickFormatter={(v: number) => `R$ ${num(v, 0)}`} tick={{ fill: "var(--text-muted)", fontSize: 11 }} width={64} tickLine={false} axisLine={false} />
          <Tooltip cursor={{ fill: "var(--surface-2)" }}
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" }}
            formatter={(v) => [v == null ? "sem dado" : fmt(Number(v)), nome]} />
          <Bar dataKey="valor" name={nome} fill="var(--rl-n1)" radius={[2, 2, 0, 0]} isAnimationActive={!reduz} animationDuration={420} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
