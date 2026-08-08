"use client";

// Medidor tipo velocímetro (arco aberto, não fechado) na identidade visual Institucional.
// Trilho neutro + traço de progresso colorido + marca perpendicular na posição do valor.

function polar(cx: number, cy: number, r: number, angDeg: number) {
  const a = (angDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
}

// Arco de aDeg -> bDeg (graus). aDeg > bDeg desenha da esquerda para a direita passando pelo topo.
function arc(cx: number, cy: number, r: number, aDeg: number, bDeg: number) {
  const s = polar(cx, cy, r, aDeg);
  const e = polar(cx, cy, r, bDeg);
  const large = Math.abs(aDeg - bDeg) > 180 ? 1 : 0;
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`;
}

export function Gauge({
  value, min = 0, max = 100, meta, mediaPais, maiorMelhor = true, titulo, unidade = "%",
}: {
  value: number | null | undefined;
  min?: number; max?: number;
  meta?: number | null;
  mediaPais?: number | null;
  maiorMelhor?: boolean;
  titulo?: string;
  unidade?: string;
}) {
  const cx = 100, cy = 104, r = 76;
  const START = 190, SWEEP = 200; // varredura de 190° a -10°, abertura embaixo

  const ang = (v: number) => START - SWEEP * ((Math.max(min, Math.min(max, v)) - min) / (max - min));

  const temValor = value !== null && value !== undefined;
  const v = temValor ? (value as number) : min;
  const valorAng = ang(v);

  const dentroMeta = meta != null ? (maiorMelhor ? v >= meta : v <= meta) : null;
  const corValor = meta == null ? "var(--vinho-light)" : dentroMeta ? "var(--vinho-light)" : "var(--dourado)";

  const metaAng = meta != null ? ang(meta) : null;
  const needleA = polar(cx, cy, r - 10, valorAng);
  const needleB = polar(cx, cy, r + 10, valorAng);
  const metaA = metaAng != null ? polar(cx, cy, r - 7, metaAng) : null;
  const metaB = metaAng != null ? polar(cx, cy, r + 7, metaAng) : null;

  const legenda: string[] = [];
  if (meta != null) legenda.push(`meta ${meta}${unidade}`);
  if (mediaPais != null) legenda.push(`país ${mediaPais}${unidade}`);

  return (
    <div style={{ textAlign: "center" }}>
      <svg viewBox="0 0 200 130" width="100%" style={{ maxWidth: 220, margin: "0 auto", display: "block" }} role="img">
        {/* Trilho de fundo */}
        <path d={arc(cx, cy, r, START, START - SWEEP)} fill="none" stroke="var(--border-strong, var(--border))" strokeWidth={7} strokeLinecap="round" />
        {/* Traço de progresso */}
        {temValor && (
          <path d={arc(cx, cy, r, START, valorAng)} fill="none" stroke={corValor} strokeWidth={7} strokeLinecap="round" />
        )}
        {/* Marca da meta */}
        {metaA && metaB && (
          <line x1={metaA.x} y1={metaA.y} x2={metaB.x} y2={metaB.y} stroke="var(--text-muted)" strokeWidth={1} opacity={0.55} />
        )}
        {/* Ponteiro do valor (perpendicular ao arco) */}
        {temValor && (
          <line x1={needleA.x} y1={needleA.y} x2={needleB.x} y2={needleB.y} stroke="var(--vinho)" strokeWidth={2.5} strokeLinecap="butt" />
        )}
      </svg>
      <div style={{ fontFamily: "var(--font-heading)", fontSize: "2.1rem", fontWeight: 700, lineHeight: 1, color: temValor ? corValor : "var(--text-muted)" }}>
        {temValor ? `${value}${unidade}` : "—"}
      </div>
      {titulo && (
        <div style={{ fontFamily: "var(--font-heading)", fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", marginTop: "0.15rem" }}>
          {titulo}
        </div>
      )}
      {legenda.length > 0 && (
        <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
          {legenda.join(" · ")}
        </div>
      )}
    </div>
  );
}
