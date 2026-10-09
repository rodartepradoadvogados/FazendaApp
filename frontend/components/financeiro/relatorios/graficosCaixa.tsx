"use client";
// Gráficos dos Relatórios › Caixa (Fase C1), em SVG próprio como a cascata da
// Fase B: o saldo projetado dia a dia (faixa da reserva, 1º dia abaixo dela,
// 1º dia negativo, menor saldo, a compra simulada tracejada) e as barras
// mensais (entradas, saídas e sobra, com a linha do ano anterior). Cores só
// por token; "sai" e "faltou" são hachurados (nunca só cor). Movimento: a linha
// se desenha e as barras crescem na entrada; ao trocar de contexto as barras
// mudam de altura (morph); tudo desligado em prefers-reduced-motion.
import { useState, type KeyboardEvent, type MouseEvent } from "react";
import { brl } from "@/lib/relatorioContexto";
import { dm } from "@/lib/relatorioCaixa";
// Medida do contêiner e número compacto: os mesmos do molde (graficos.tsx), um só lugar.
import { compacto, useLargura } from "./graficos";
// Continuidade (MOVIMENTO.md §2): as barras morfam ao trocar o contexto, como os degraus da DRE.
import { useMorph } from "./movimento";

export const CSS_CAIXA = `
.rl-cx-svg{display:block;width:100%;height:auto;overflow:visible;touch-action:pan-y}
.rl-cx-svg text{fill:var(--text-muted);font-size:11.5px;font-family:var(--font-body)}
.rl-cx-svg .tx{fill:var(--text);font-weight:700;font-size:12px;paint-order:stroke;stroke:var(--surface);stroke-width:4px;stroke-linejoin:round}
.rl-cx-svg .halo{paint-order:stroke;stroke:var(--surface);stroke-width:4px;stroke-linejoin:round}
.rl-cx-svg .gl{stroke:var(--border)}
.rl-cx-svg .z{stroke:var(--border-strong,var(--border));stroke-width:1.4}
.rl-cx-svg g[role=button]{cursor:pointer;outline:none}
.rl-cx-svg g[role=button]:focus-visible .hit{fill:color-mix(in srgb,var(--text-accent) 12%,transparent);stroke:var(--text-accent);stroke-width:2}
.rl-cx-svg g[role=button]:hover .hit{fill:color-mix(in srgb,var(--text) 5%,transparent)}
.rl-cx-svg .hit{fill:transparent}
.rl-cx-dica{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--border);border-radius:var(--r-sm);padding:.3rem .5rem;font-size:.76rem;color:var(--text);white-space:nowrap;font-variant-numeric:tabular-nums;box-shadow:0 2px 8px color-mix(in srgb,var(--text) 10%,transparent)}
.rl-cx-sw{display:inline-block;width:14px;height:10px;border-radius:1px}
.rl-cx-ln{display:inline-block;width:16px;height:0;border-top:2.5px solid currentColor}
.rl-cx-ln.tr{border-top-style:dashed}
@media (prefers-reduced-motion:no-preference){
  .rl-cx-desenha{stroke-dasharray:1;stroke-dashoffset:1;animation:rl-cx-traco 420ms var(--rl-ease) forwards}
  .rl-cx-tarde{animation:rl-cx-surge 200ms ease-out 260ms both}
  .rl-cx-cresce{transform-box:fill-box;transform-origin:center bottom;animation:rl-cx-cresceY 280ms var(--rl-ease) both;animation-delay:min(calc(var(--i,0) * 22ms),150ms)}
  .rl-cx-cresce.neg{transform-origin:center top}
  .rl-cx-pulso{transform-box:fill-box;transform-origin:center;animation:rl-cx-pulso 760ms var(--rl-ease) 520ms 1 both}
}
@keyframes rl-cx-traco{to{stroke-dashoffset:0}}
@keyframes rl-cx-surge{from{opacity:0}}
@keyframes rl-cx-pulso{0%{opacity:.85;transform:scale(1)}100%{opacity:0;transform:scale(3.2)}}
@keyframes rl-cx-cresceY{from{transform:scaleY(0)}}
.rl-cx-estreita{display:none!important}
.rl-tab tr.dest td{background:var(--surface-2)}
.rl-tab tr.dest td:first-child{box-shadow:inset 3px 0 0 var(--rl-a)}
@media (max-width:767px){.rl-tab.rl-cx-conta td:first-child{min-width:5rem}.rl-tab.rl-cx-conta th,.rl-tab.rl-cx-conta td{padding-left:.3rem;padding-right:.3rem}.rl-tab.rl-cx-conta td.r{font-size:.75rem}.rl-tab.rl-cx-conta th{letter-spacing:.05em;padding-left:.3rem;padding-right:.3rem}.rl-tab.rl-cx-conta th:first-child{white-space:normal}.rl-tab.rl-cx-conta .rl-linkbtn svg{display:none}}
@media (max-width:640px){.rl-leg .rl-cx-leg-es{display:none}.rl-cx-larga{display:none}.rl-cx-estreita{display:block!important}}
@media print{.rl-cx-desenha{stroke-dasharray:none!important;stroke-dashoffset:0!important}}
`;

function nice(v: number) {
  if (v <= 0) return 1;
  const e = Math.pow(10, Math.floor(Math.log10(v))), f = v / e;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e;
}
function escala(mn: number, mx: number, n = 4) {
  if (mn === mx) { mn -= 1; mx += 1; }
  const passo = nice((mx - mn) / n), lo = Math.floor(mn / passo) * passo, hi = Math.ceil(mx / passo) * passo;
  const ticks: number[] = [];
  for (let t = lo; t <= hi + passo / 2; t += passo) ticks.push(Math.round(t * 100) / 100);
  return { lo, hi, ticks };
}

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

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

// ── Saldo projetado ──────────────────────────────────────────────────────
export function GraficoSaldo({ serie, reserva, rotuloReserva, primeiroAbaixoReserva, primeiroNegativo, menor, comCompra, marcos = [], descricao }: {
  serie: { data: string; saldo: number }[]; reserva: number; rotuloReserva: string;
  primeiroAbaixoReserva: string | null; primeiroNegativo: string | null; menor: { saldo: number; data: string };
  comCompra?: number[] | null; marcos?: { data: string; texto: string }[]; descricao: string;
}) {
  const [ref, W] = useLargura<HTMLDivElement>();
  const [dica, setDica] = useState<number | null>(null);
  const estreito = W < 600, n = serie.length;
  const H = estreito ? 250 : 300, L = estreito ? 46 : 62, R = 14, T = 30, B = 30;
  if (n < 2) return null;
  const vals = serie.map((p) => p.saldo).concat(comCompra ?? []).concat([0, reserva > 0 ? reserva * 1.08 : 0]);
  const sc = escala(Math.min(...vals), Math.max(...vals), estreito ? 4 : 5);
  const x = (i: number) => L + (i * (W - L - R)) / (n - 1);
  const y = (v: number) => T + ((sc.hi - v) / (sc.hi - sc.lo || 1)) * (H - T - B);
  const y0 = y(0), id = "rlcx-s";
  const caminho = (vs: number[]) => vs.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  const saldos = serie.map((p) => p.saldo);
  const area = `M${x(0)} ${y0}${saldos.map((v, i) => `L${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("")}L${x(n - 1)} ${y0}Z`;
  const idx = (d: string | null) => (d ? serie.findIndex((p) => p.data === d) : -1);
  const iRes = idx(primeiroAbaixoReserva), iNeg = idx(primeiroNegativo), iMin = idx(menor.data);
  // Rótulo da reserva: no lado (esquerdo ou direito) em que a linha do saldo passa mais longe dele.
  const yRot = reserva > 0 ? y(reserva) - 6 : 0;
  const folga = (de: number, ate: number) => Math.min(...saldos.slice(de, ate).map((v) => Math.abs(y(v) - yRot)), 1e9);
  const rotuloADireita = reserva > 0 && folga(Math.floor(n * 0.55), n) > folga(0, Math.ceil(n * 0.45));
  const rotX = (i: number, largura: number) => Math.max(L + largura / 2, Math.min(x(i), W - R - largura / 2));
  const mover = (e: MouseEvent<SVGSVGElement>) => {
    const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((px - L) / (W - L - R)) * (n - 1));
    setDica(i >= 0 && i < n ? i : null);
  };
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <svg className="rl-cx-svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={descricao}
        onMouseMove={mover} onMouseLeave={() => setDica(null)}>
        <Padroes id={id} />
        <clipPath id={`${id}-p`}><rect x="0" y="0" width={W} height={y0} /></clipPath>
        <clipPath id={`${id}-n`}><rect x="0" y={y0} width={W} height={Math.max(0, H - y0)} /></clipPath>
        {reserva > 0 && (<>
          <rect x={L} y={y(reserva)} width={W - L - R} height={Math.max(0, y0 - y(reserva))} style={{ fill: "var(--st-logo-bg)" }} />
          <line x1={L} x2={W - R} y1={y(reserva)} y2={y(reserva)} style={{ stroke: "var(--st-logo-line)", strokeDasharray: "4 3" }} />
          <text className="halo" x={rotuloADireita ? W - R - 4 : L + 6} y={yRot} textAnchor={rotuloADireita ? "end" : "start"} style={{ fill: "var(--text)" }}>{estreito ? `reserva ${compacto(reserva)}` : rotuloReserva}</text>
        </>)}
        {sc.ticks.map((t) => (
          <g key={t}>
            <line className={Math.abs(t) < 1e-9 ? "z" : "gl"} x1={L} x2={W - R} y1={y(t)} y2={y(t)} />
            <text x={L - 6} y={y(t) + 4} textAnchor="end">{compacto(t)}</text>
          </g>
        ))}
        {serie.map((p, i) => (p.data.slice(8) === "01" ? (
          <g key={p.data}>
            <line className="gl" x1={x(i)} x2={x(i)} y1={T} y2={H - B} style={{ strokeDasharray: "2 3" }} />
            <text x={x(i) + 4} y={H - 9}>{MESES[Number(p.data.slice(5, 7)) - 1]}</text>
          </g>
        ) : null))}
        <text x={x(0)} y={H - 9} className="tx">hoje</text>
        <g clipPath={`url(#${id}-n)`}><path d={area} style={{ fill: `url(#${id}-neg)` }} /></g>
        {comCompra && comCompra.length === n && (
          <path d={caminho(comCompra)} style={{ fill: "none", stroke: "var(--rl-n1)", strokeWidth: 2, strokeDasharray: "6 5" }} />
        )}
        <path key={`p${n}`} className="rl-cx-desenha" pathLength={1} d={caminho(saldos)} clipPath={`url(#${id}-p)`} style={{ fill: "none", stroke: "var(--rl-a)", strokeWidth: 2.6, strokeLinejoin: "round" }} />
        <path key={`n${n}`} className="rl-cx-desenha" pathLength={1} d={caminho(saldos)} clipPath={`url(#${id}-n)`} style={{ fill: "none", stroke: "var(--st-venc-fg)", strokeWidth: 2.6, strokeLinejoin: "round" }} />
        <g key={`t${n}`} className="rl-cx-tarde">
          {marcos.map((m) => {
            const i = idx(m.data);
            if (i < 0) return null;
            return (
              <rect key={`${m.data}-${m.texto}`} x={x(i) - 4.5} y={y(saldos[i]) - 4.5} width={9} height={9} transform={`rotate(45 ${x(i)} ${y(saldos[i])})`}
                style={{ fill: "var(--gold)", stroke: "var(--gold-deep)", strokeWidth: 1.4 }}><title>{`${dm(m.data)}: ${m.texto}`}</title></rect>
            );
          })}
          {iRes > 0 && iRes !== iNeg && (<>
            {iNeg < 0 && <circle className="rl-cx-pulso" cx={x(iRes)} cy={y(saldos[iRes])} r={5.5} style={{ fill: "none", stroke: "var(--gold-deep)", strokeWidth: 2 }} aria-hidden />}
            <circle cx={x(iRes)} cy={y(saldos[iRes])} r={5.5} style={{ fill: "var(--gold)", stroke: "var(--gold-deep)", strokeWidth: 1.5 }} />
            <text className="tx" x={rotX(iRes, 150)} y={y(saldos[iRes]) - 11} textAnchor="middle">{estreito ? "" : "abaixo da reserva: "}{dm(serie[iRes].data)}</text>
          </>)}
          {iNeg >= 0 && (<>
            <circle className="rl-cx-pulso" cx={x(iNeg)} cy={y0} r={5} style={{ fill: "none", stroke: "var(--st-venc-fg)", strokeWidth: 2 }} aria-hidden />
            <circle cx={x(iNeg)} cy={y0} r={5} style={{ fill: "var(--st-venc-fg)" }} />
            <text className="tx" x={rotX(iNeg, estreito ? 90 : 140)} y={y0 - 10} textAnchor="middle" style={{ fill: "var(--st-venc-fg)" }}>{estreito ? "negativo" : "1º dia negativo"}: {dm(serie[iNeg].data)}</text>
          </>)}
          {iMin >= 0 && (
            <text className="tx" x={rotX(iMin, 150)} y={Math.min(H - B - 4, y(menor.saldo) + 18)} textAnchor="middle">menor: {compacto(menor.saldo)} em {dm(menor.data)}</text>
          )}
        </g>
        {dica != null && (
          <g aria-hidden>
            <line x1={x(dica)} x2={x(dica)} y1={T} y2={H - B} style={{ stroke: "var(--text-muted)", strokeDasharray: "3 3" }} />
            <circle cx={x(dica)} cy={y(saldos[dica])} r={4} style={{ fill: "var(--surface)", stroke: saldos[dica] < 0 ? "var(--st-venc-fg)" : "var(--rl-a)", strokeWidth: 2 }} />
          </g>
        )}
      </svg>
      {dica != null && (
        <div className="rl-cx-dica" aria-hidden style={{ left: Math.min(Math.max(0, x(dica) / W * 100), 70) + "%", top: 0 }}>
          {dm(serie[dica].data)}: <b style={{ color: saldos[dica] < 0 ? "var(--st-venc-fg)" : undefined }}>{brl(saldos[dica], 0)}</b>
          {comCompra && comCompra.length === n ? <> · com a compra {brl(comCompra[dica], 0)}</> : null}
        </div>
      )}
    </div>
  );
}

export function LegendaSaldo({ reserva, compra, marcos }: { reserva: boolean; compra: boolean; marcos: boolean }) {
  return (<>
    <span style={{ color: "var(--rl-a)" }}><i className="rl-cx-ln" />Saldo projetado (todas as contas)</span>
    <span style={{ color: "var(--st-venc-fg)" }}><i className="rl-cx-ln" />Abaixo de zero (hachurado)</span>
    {reserva && <span><i className="rl-cx-sw" style={{ background: "var(--st-logo-bg)", border: "1px solid var(--st-logo-line)" }} />Faixa da reserva</span>}
    {marcos && <span><span aria-hidden style={{ color: "var(--gold-deep)" }}>◆</span>Vencimento da fatura do cartão</span>}
    {compra && <span style={{ color: "var(--rl-n1)" }}><i className="rl-cx-ln tr" />Com a compra simulada</span>}
  </>);
}

// ── Barras mensais ───────────────────────────────────────────────────────
export type SerieBarras = { nome: string; estilo: "entra" | "sai" | "resultado"; valores: (number | null)[] };

export function BarrasMensais({ rotulos, series, linha, projetado, onAbrir, rotuloAbrir, descricao, selecionado, aoPassar }: {
  rotulos: string[]; series: SerieBarras[]; linha?: { nome: string; valores: (number | null)[] } | null; projetado?: boolean[];
  onAbrir?: (i: number) => void; rotuloAbrir?: (i: number) => string; descricao: string; selecionado?: number | null;
  /** Mês sob o mouse ou o foco (ou null ao sair): a tabela ao lado destaca a mesma linha. */
  aoPassar?: (i: number | null) => void;
}) {
  const [ref, W] = useLargura<HTMLDivElement>();
  // Gatilho estável (os valores, não a identidade dos arrays): trocou o contexto, as barras morfam.
  useMorph(ref, JSON.stringify([rotulos, series.map((s) => s.valores), linha?.valores ?? null, W]));
  const n = rotulos.length;
  const estreito = W < 600;
  const H = estreito ? 220 : 250, L = estreito ? 42 : 56, R = 10, T = 20, B = 28;
  const gw = (W - L - R) / Math.max(1, n);
  // Pouco espaço por mês: só a série de resultado (a legenda avisa).
  const visiveis = gw / series.length < 9 ? series.filter((s) => s.estilo === "resultado") : series;
  const nb = Math.max(1, visiveis.length);
  const bw = Math.min(nb === 1 ? 44 : 20, (gw * 0.74) / nb);
  const todos = visiveis.flatMap((s) => s.valores.filter((v): v is number => v != null)).concat((linha?.valores ?? []).filter((v): v is number => v != null)).concat(0);
  const sc = escala(Math.min(...todos), Math.max(...todos));
  const y = (v: number) => T + ((sc.hi - v) / (sc.hi - sc.lo || 1)) * (H - T - B);
  const y0 = y(0), id = "rlcx-b";
  const tecla = (e: KeyboardEvent, i: number) => { if (onAbrir && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onAbrir(i); } };
  // Rótulo do eixo: sem ano quando aperta ("jan" em vez de "jan/26") e salteado se ainda não couber.
  const rotuloCurto = gw < 46;
  const passoRotulo = Math.max(1, Math.ceil((rotuloCurto ? 30 : 44) / gw));
  const comValores = visiveis.length === 1 && gw > 40 && n <= 13;
  return (
    <div ref={ref}>
      <svg className="rl-cx-svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={descricao}>
        <Padroes id={id} />
        {sc.ticks.map((t) => (
          <g key={t}>
            <line className={Math.abs(t) < 1e-9 ? "z" : "gl"} x1={L} x2={W - R} y1={y(t)} y2={y(t)} />
            <text x={L - 6} y={y(t) + 4} textAnchor="end">{compacto(t)}</text>
          </g>
        ))}
        {rotulos.map((rot, i) => {
          const pj = projetado?.[i];
          const x0 = L + i * gw + (gw - bw * nb) / 2;
          const desc = visiveis.map((s) => `${s.nome} ${s.valores[i] == null ? "sem dado" : brl(s.valores[i]!)}`).join(", ");
          return (
            <g key={rot + i} onMouseEnter={aoPassar ? () => aoPassar(i) : undefined} onMouseLeave={aoPassar ? () => aoPassar(null) : undefined}
              onFocus={aoPassar ? () => aoPassar(i) : undefined} onBlur={aoPassar ? () => aoPassar(null) : undefined} {...(onAbrir ? {
              role: "button", tabIndex: 0, onClick: () => onAbrir(i), onKeyDown: (e: KeyboardEvent) => tecla(e, i),
              "aria-label": rotuloAbrir ? rotuloAbrir(i) : `${rot}${pj ? " (projetado)" : ""}: ${desc}. Abrir o detalhe`,
            } : {})}>
              <rect className="hit" x={L + i * gw} y={T - 6} width={gw} height={H - T - B + 6} rx={3}
                style={selecionado === i ? { fill: "color-mix(in srgb,var(--text-accent) 10%,transparent)" } : undefined} />
              {visiveis.map((s, k) => {
                const v = s.valores[i];
                if (v == null) return null;
                const topo = y(Math.max(0, v)), alt = Math.max(1, Math.abs(y(v) - y0));
                const fill = s.estilo === "entra" ? "var(--rl-n2)" : s.estilo === "sai" ? `url(#${id}-sai)` : v < 0 ? `url(#${id}-neg)` : "var(--rl-a)";
                const stroke = pj ? "var(--rl-n1)" : s.estilo === "resultado" && v < 0 ? "var(--st-venc-fg)" : "none";
                return (
                  <rect key={s.nome} data-m={`b:${rot}:${s.nome}`} className={`rl-cx-cresce${v < 0 ? " neg" : ""}`}
                    style={{ ["--i" as string]: i, fill, stroke, strokeWidth: pj ? 1.3 : 1, strokeDasharray: pj ? "3 2" : undefined, opacity: pj ? 0.55 : 1 } as React.CSSProperties}
                    x={x0 + k * bw} y={topo} width={Math.max(2, bw - (nb > 1 ? 2 : 0))} height={alt}>
                    <title>{`${rot} · ${s.nome}: ${brl(v)}${pj ? " (com o previsto)" : ""}`}</title>
                  </rect>
                );
              })}
              {comValores && visiveis[0].valores[i] != null && (
                <text className="rl-cx-tarde" x={x0 + bw / 2} y={visiveis[0].valores[i]! >= 0 ? y(visiveis[0].valores[i]!) - 5 : y(visiveis[0].valores[i]!) + 13}
                  textAnchor="middle" style={{ fill: "var(--text)", fontSize: 11 }}>{compacto(visiveis[0].valores[i]!)}</text>
              )}
              {i % passoRotulo === 0 && <text x={L + i * gw + gw / 2} y={H - 9} textAnchor="middle">{rotuloCurto ? rot.split("/")[0] : rot}</text>}
            </g>
          );
        })}
        {(() => {
          const i0 = projetado ? projetado.findIndex(Boolean) : -1;
          if (i0 <= 0) return null;
          const xd = L + i0 * gw;
          return (
            <g className="rl-cx-tarde" aria-hidden>
              <line x1={xd} x2={xd} y1={T - 8} y2={H - B} style={{ stroke: "var(--text-muted)", strokeDasharray: "3 3" }} />
              {!estreito && <text x={xd + 5} y={T - 1} style={{ fontSize: 11 }}>com o previsto →</text>}
            </g>
          );
        })()}
        {linha && (() => {
          let d = "", caneta = false;
          linha.valores.forEach((v, i) => {
            if (v == null) { caneta = false; return; }
            d += `${caneta ? "L" : "M"}${(L + i * gw + gw / 2).toFixed(1)} ${y(v).toFixed(1)}`;
            caneta = true;
          });
          return (
            <g aria-hidden>
              <path className="rl-cx-desenha" pathLength={1} d={d} style={{ fill: "none", stroke: "var(--text)", strokeWidth: 1.8, strokeDasharray: undefined }} />
              {linha.valores.map((v, i) => (v == null ? null : (
                <rect key={i} className="rl-cx-tarde" x={L + i * gw + gw / 2 - 4} y={y(v) - 4} width={8} height={8}
                  transform={`rotate(45 ${L + i * gw + gw / 2} ${y(v)})`} style={{ fill: "var(--surface)", stroke: "var(--text)", strokeWidth: 1.8 }}>
                  <title>{`${rotulos[i]} · ${linha.nome}: ${brl(v)}`}</title>
                </rect>
              )))}
            </g>
          );
        })()}
      </svg>
      {visiveis.length < series.length && (
        <p style={{ margin: ".3rem 0 0", fontSize: ".74rem", color: "var(--text-muted)" }}>Na tela estreita, só a sobra de cada mês; entradas e saídas estão na tabela.</p>
      )}
    </div>
  );
}

export function LegendaBarras({ series, linha, projetado, sobrouFaltou }: { series: SerieBarras[]; linha?: string | null; projetado?: boolean; sobrouFaltou?: boolean }) {
  return (<>
    {series.map((s) => s.estilo === "entra" ? <span key={s.nome} className="rl-cx-leg-es"><i className="rl-cx-sw" style={{ background: "var(--rl-n2)" }} />{s.nome}</span>
      : s.estilo === "sai" ? <span key={s.nome} className="rl-cx-leg-es"><i className="rl-cx-sw" style={{ background: "repeating-linear-gradient(45deg,var(--rl-n3) 0 3px,var(--rl-n1) 3px 5px)" }} />{s.nome}</span>
        : <span key={s.nome}><i className="rl-cx-sw" style={{ background: "var(--rl-a)" }} />{sobrouFaltou ? "Sobrou" : s.nome}</span>)}
    {series.some((s) => s.estilo === "resultado") && (
      <span><i className="rl-cx-sw" style={{ background: "repeating-linear-gradient(-45deg,var(--st-venc-bg) 0 3px,var(--st-venc-fg) 3px 4.5px)", border: "1px solid var(--st-venc-fg)" }} />Faltou (negativo)</span>
    )}
    {projetado && <span><i className="rl-cx-sw" style={{ background: "var(--rl-n3)", border: "1px dashed var(--rl-n1)", opacity: 0.8 }} />Com o previsto (em aberto e agendado)</span>}
    {linha && <span style={{ color: "var(--text)" }}><i className="rl-cx-ln" />◆ {linha}</span>}
  </>);
}
