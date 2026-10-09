"use client";
// A linha do saldo projetado (Caixa real do servidor) — Painel do dono e cena
// "O caixa" do "Apresentar o mês". Faixa da reserva em âmbar claro com texto, o
// trecho abaixo de zero em vermelho (saldo negativo é vermelho, com texto), e as
// marcas escritas: 1º dia abaixo da reserva, 1º dia negativo e o menor saldo.
// Entrada: a linha se desenha (stroke-dashoffset) em 450 ms no uso diário e
// devagar (1,1 s) só na apresentação; movimento reduzido: aparece pronta.
import { useEffect, useId, useRef, useState } from "react";
import { MESES_CURTOS } from "@/lib/relatorioContexto";
// O número compacto do molde (graficos.tsx) — um só em todos os gráficos.
import { compacto } from "./graficos";

const dm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

export function GraficoSaldo({ serie, reserva, abaixoReservaEm, negativoEm, menor, lento = false, altura = 230, descricao }: {
  serie: { data: string; saldo: number }[]; reserva: number; abaixoReservaEm: string | null; negativoEm: string | null;
  menor: { saldo: number; data: string } | null; lento?: boolean; altura?: number; descricao: string;
}) {
  const uid = useId().replace(/:/g, "");
  const caixa = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(640);
  useEffect(() => {
    const el = caixa.current;
    if (!el) return;
    const medir = () => setW(Math.max(280, Math.round(el.clientWidth)));
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  if (serie.length < 2) return <p style={{ margin: 0, color: "var(--text-muted)", fontSize: ".85rem" }}>Sem projeção de caixa para desenhar.</p>;
  const H = altura, L = 52, R = 12, T = 12, B = 26;
  const vals = serie.map((p) => p.saldo).concat(0, reserva > 0 ? reserva : 0);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo || 1) * 0.08;
  const y0 = lo - (lo < 0 ? pad : 0), y1 = hi + pad;
  const x = (i: number) => L + (i / (serie.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - y0) / (y1 - y0 || 1)) * (H - T - B);
  const d = serie.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p.saldo).toFixed(1)}`).join(" ");
  // Marcas "redondas" do eixo (1, 2 ou 5 × 10^n), sempre com o zero.
  const bruto = (y1 - y0) / 4, pot = Math.pow(10, Math.floor(Math.log10(bruto || 1)));
  const passo = [1, 2, 5, 10].map((k) => k * pot).find((k) => k >= bruto) ?? 10 * pot;
  const ticks: number[] = [];
  for (let v = Math.ceil(y0 / passo) * passo; v <= y1 + 1e-9; v += passo) ticks.push(Math.abs(v) < 1e-9 ? 0 : v);
  const idx = (iso: string | null) => (iso ? serie.findIndex((p) => p.data === iso) : -1);
  const iRes = idx(abaixoReservaEm), iNeg = idx(negativoEm), iMen = menor ? idx(menor.data) : -1;
  const meses = serie.map((p, i) => ({ p, i })).filter(({ p, i }) => i > 3 && p.data.slice(8) === "01");
  const estilo = { ["--c4-dur" as string]: lento ? "1100ms" : "450ms", ["--c4-tarde" as string]: lento ? "1100ms" : "300ms" } as React.CSSProperties;
  return (
    <div ref={caixa} className="pd-saldo" style={estilo}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={descricao}>
        <defs>
          <clipPath id={`${uid}-neg`}><rect x={0} y={y(0)} width={W} height={Math.max(0, H - y(0))} /></clipPath>
        </defs>
        {reserva > 0 && (
          <g>
            <rect x={L} y={y(reserva)} width={W - L - R} height={Math.max(0, y(Math.max(0, y0)) - y(reserva))} style={{ fill: "var(--st-logo-bg)" }} />
            <text x={L + 6} y={y(reserva) + 14} style={{ fill: "var(--st-logo-fg)", fontWeight: 600 }}>Faixa da reserva (até {compacto(reserva)})</text>
          </g>
        )}
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} style={{ stroke: Math.abs(v) < 1e-9 ? "var(--border-strong, var(--border))" : "var(--border)" }} />
            <text x={L - 6} y={y(v) + 4} textAnchor="end">{compacto(v)}</text>
          </g>
        ))}
        <text x={x(0)} y={H - 8} style={{ fill: "var(--text)", fontWeight: 700 }}>hoje</text>
        {meses.map(({ p, i }) => <text key={p.data} x={x(i)} y={H - 8} textAnchor="middle">{MESES_CURTOS[Number(p.data.slice(5, 7)) - 1]}</text>)}
        <path data-m="saldo" className="c4-linha" pathLength={1} d={d} style={{ fill: "none", stroke: "var(--rl-a)", strokeWidth: 2.4, strokeLinejoin: "round" }} />
        {lo < 0 && <path className="c4-linha" pathLength={1} d={d} clipPath={`url(#${uid}-neg)`} style={{ fill: "none", stroke: "var(--st-venc-fg)", strokeWidth: 2.6, strokeLinejoin: "round" }} />}
        <g className="c4-tarde">
          {iRes > 0 && (<>
            <line x1={x(iRes)} x2={x(iRes)} y1={T} y2={H - B} style={{ stroke: "var(--st-logo-fg)", strokeDasharray: "3 3" }} />
            <text x={x(iRes) > W * 0.6 ? x(iRes) - 4 : x(iRes) + 4} textAnchor={x(iRes) > W * 0.6 ? "end" : "start"} y={T + 10} style={{ fill: "var(--st-logo-fg)", fontWeight: 700 }}>abaixo da reserva: {dm(abaixoReservaEm!)}</text>
          </>)}
          {iNeg > 0 && (<>
            <line x1={x(iNeg)} x2={x(iNeg)} y1={T + 16} y2={H - B} style={{ stroke: "var(--st-venc-fg)", strokeDasharray: "3 3" }} />
            <text x={x(iNeg) > W * 0.6 ? x(iNeg) - 4 : x(iNeg) + 4} textAnchor={x(iNeg) > W * 0.6 ? "end" : "start"} y={T + 26} style={{ fill: "var(--st-venc-fg)", fontWeight: 700 }}>1º dia negativo: {dm(negativoEm!)}</text>
          </>)}
          {iMen >= 0 && menor && (<>
            <circle cx={x(iMen)} cy={y(menor.saldo)} r={4} style={{ fill: menor.saldo < 0 ? "var(--st-venc-fg)" : "var(--rl-a)" }} />
            {y(menor.saldo) + 18 > H - B - 4
              // Perto do pé do gráfico: o rótulo vai à esquerda do ponto, na altura dele.
              ? <text x={Math.max(x(iMen) - 8, L + 150)} y={y(menor.saldo) + 4} textAnchor="end" style={{ fill: "var(--text)", fontWeight: 700 }}>menor: {compacto(menor.saldo)} em {dm(menor.data)}</text>
              : <text x={Math.min(Math.max(x(iMen), L + 60), W - 60)} y={y(menor.saldo) + 18} textAnchor="middle" style={{ fill: "var(--text)", fontWeight: 700 }}>menor: {compacto(menor.saldo)} em {dm(menor.data)}</text>}
          </>)}
        </g>
      </svg>
    </div>
  );
}

export function LegendaSaldo({ temNegativo }: { temNegativo: boolean }) {
  return (
    <div className="rl-leg">
      <span style={{ color: "var(--rl-a)" }}><i className="ln" />Saldo projetado (todas as contas)</span>
      {temNegativo && <span style={{ color: "var(--st-venc-fg)" }}><i className="ln" />Abaixo de zero</span>}
      <span><i style={{ background: "var(--st-logo-bg)", border: "1px solid var(--st-logo-line)" }} />Faixa da reserva</span>
    </div>
  );
}
