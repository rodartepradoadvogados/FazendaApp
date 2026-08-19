"use client";
import { useMemo } from "react";

/**
 * Curva de lactação de UM animal — produção (kg) por DEL (dias em lactação),
 * com a curva média do rebanho desenhada por trás como referência.
 *
 * A referência é o que transforma o gráfico em decisão: um ponto isolado de
 * 22 kg não diz nada; 22 kg quando as contemporâneas dela fazem 30 no mesmo
 * DEL diz muito. Vem de `curva_referencia_rebanho` na ficha (calculada por
 * `rules/producao.calcular_producao`, a mesma da tela de Produção).
 *
 * SVG inline, sem biblioteca de gráficos — é o padrão do projeto (ver
 * `Gauge.tsx`, `RelatoriosGerenciais.tsx`, `AnaliseInterativa.tsx`).
 */

export type PontoControle = { del: number; kg: number; data?: string | null };
export type FaixaReferencia = { faixa_del: string; media_kg: number; controles: number };

// "0-30" → 15 | "301+" → 331. A faixa aberta vira um ponto plausível à frente
// do limite, só para a linha de referência não terminar no ar.
function meioDaFaixa(faixa: string): number {
  const intervalo = faixa.match(/^(\d+)-(\d+)$/);
  if (intervalo) return (Number(intervalo[1]) + Number(intervalo[2])) / 2;
  const aberta = faixa.match(/^(\d+)\+$/);
  if (aberta) return Number(aberta[1]) + 30;
  return NaN;
}

const M = { top: 16, right: 16, bottom: 34, left: 44 };
const W = 640;
const H = 260;

export function CurvaLactacao({ pontos, referencia }: {
  pontos: PontoControle[];
  referencia?: FaixaReferencia[];
}) {
  const dados = useMemo(() => {
    const validos = pontos
      .filter((p) => Number.isFinite(p.del) && Number.isFinite(p.kg) && p.del >= 0)
      .sort((a, b) => a.del - b.del);

    const ref = (referencia || [])
      .map((f) => ({ del: meioDaFaixa(f.faixa_del), kg: f.media_kg, rotulo: f.faixa_del }))
      .filter((f) => Number.isFinite(f.del) && f.kg > 0)
      .sort((a, b) => a.del - b.del);

    const delsX = [...validos.map((p) => p.del), ...ref.map((r) => r.del)];
    const kgsY = [...validos.map((p) => p.kg), ...ref.map((r) => r.kg)];
    const delMax = Math.max(...delsX, 60);
    const kgMax = Math.max(...kgsY, 10);
    return { validos, ref, delMax: Math.ceil(delMax / 30) * 30, kgMax: Math.ceil(kgMax * 1.15) };
  }, [pontos, referencia]);

  if (!dados.validos.length) {
    return (
      <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", padding: "1rem 0" }}>
        Sem controle leiteiro com DEL registrado — a curva aparece assim que houver
        pelo menos um controle com o DEL informado.
      </p>
    );
  }

  const x = (del: number) => M.left + (del / dados.delMax) * (W - M.left - M.right);
  const y = (kg: number) => H - M.bottom - (kg / dados.kgMax) * (H - M.top - M.bottom);

  const linha = (pts: { del: number; kg: number }[]) =>
    pts.map((p) => `${x(p.del).toFixed(1)},${y(p.kg).toFixed(1)}`).join(" ");

  // 5 marcas no eixo Y, arredondadas para inteiro (kg de leite não precisa de casa decimal aqui).
  const marcasY = Array.from({ length: 5 }, (_, i) => Math.round((dados.kgMax / 4) * i));
  const marcasX = Array.from({ length: dados.delMax / 30 + 1 }, (_, i) => i * 30)
    .filter((_, i, arr) => arr.length <= 8 || i % 2 === 0);

  const pico = dados.validos.reduce((a, b) => (b.kg > a.kg ? b : a));

  return (
    <div>
      <div style={{ overflowX: "auto" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", minWidth: 420, height: "auto" }}
          role="img" aria-label="Curva de lactação do animal comparada à média do rebanho">
          {/* Grade horizontal + eixo Y */}
          {marcasY.map((kg) => (
            <g key={kg}>
              <line x1={M.left} x2={W - M.right} y1={y(kg)} y2={y(kg)}
                stroke="var(--border)" strokeWidth="1" opacity="0.5" />
              <text x={M.left - 7} y={y(kg) + 4} textAnchor="end"
                style={{ fontSize: 10, fill: "var(--text-muted)" }}>{kg}</text>
            </g>
          ))}
          {/* Eixo X */}
          {marcasX.map((del) => (
            <text key={del} x={x(del)} y={H - M.bottom + 15} textAnchor="middle"
              style={{ fontSize: 10, fill: "var(--text-muted)" }}>{del}</text>
          ))}
          <text x={(W - M.left) / 2 + M.left} y={H - 4} textAnchor="middle"
            style={{ fontSize: 10, fill: "var(--text-muted)" }}>DEL (dias em lactação)</text>
          <text x={12} y={M.top + 4} style={{ fontSize: 10, fill: "var(--text-muted)" }}>kg</text>

          {/* Referência do rebanho — tracejada, atrás dos pontos do animal. */}
          {dados.ref.length > 1 && (
            <polyline points={linha(dados.ref)} fill="none" stroke="var(--text-muted)"
              strokeWidth="2" strokeDasharray="5 4" opacity="0.75" />
          )}

          {/* Curva do animal */}
          <polyline points={linha(dados.validos)} fill="none" stroke="var(--dourado-light)" strokeWidth="2" />
          {dados.validos.map((p, i) => (
            <circle key={i} cx={x(p.del)} cy={y(p.kg)} r="3.5"
              fill="var(--dourado-light)" stroke="var(--surface)" strokeWidth="1.5">
              <title>{`DEL ${p.del} — ${p.kg} kg${p.data ? ` (${p.data})` : ""}`}</title>
            </circle>
          ))}

          {/* Pico da lactação, marcado porque é o número que o produtor procura. */}
          <circle cx={x(pico.del)} cy={y(pico.kg)} r="6" fill="none"
            stroke="var(--dourado-light)" strokeWidth="1.5" opacity="0.8" />
        </svg>
      </div>

      <div style={{ display: "flex", gap: "1.2rem", flexWrap: "wrap", fontSize: "0.75rem",
        color: "var(--text-muted)", marginTop: "0.4rem" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
          <svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4"
            stroke="var(--dourado-light)" strokeWidth="2" /></svg>
          Este animal — pico {pico.kg} kg no DEL {pico.del}
        </span>
        {dados.ref.length > 1 && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
            <svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4"
              stroke="var(--text-muted)" strokeWidth="2" strokeDasharray="5 4" /></svg>
            Média do rebanho no mesmo DEL
          </span>
        )}
      </div>
    </div>
  );
}
