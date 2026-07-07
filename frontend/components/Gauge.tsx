"use client";

// Medidor semicircular (velocímetro) na identidade visual da fazenda.
// Zona vermelha/verde definida pela meta; ponteiro aponta o valor atual.

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const a = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
}

// Arco de a→b (graus, no sentido anti-horário do SVG semicircular superior).
function arc(cx: number, cy: number, r: number, aDeg: number, bDeg: number) {
  const s = polar(cx, cy, r, aDeg);
  const e = polar(cx, cy, r, bDeg);
  const large = Math.abs(bDeg - aDeg) > 180 ? 1 : 0;
  // aDeg > bDeg (ex.: 180 -> 0) desenha da esquerda para a direita passando pelo topo.
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`;
}

export function Gauge({
  value, min = 0, max = 100, meta, maiorMelhor = true, titulo, unidade = "%", cor = "var(--green-light)",
}: {
  value: number | null | undefined;
  min?: number; max?: number; meta?: number | null;
  maiorMelhor?: boolean; titulo?: string; unidade?: string; cor?: string;
}) {
  const cx = 100, cy = 100, r = 78;
  const ang = (v: number) => 180 - 180 * ((Math.max(min, Math.min(max, v)) - min) / (max - min));
  const v = value ?? min;
  const temValor = value !== null && value !== undefined;
  const metaAng = meta != null ? ang(meta) : null;

  // Zonas: verde no lado "bom", vermelha no lado "ruim", divididas pela meta.
  let verde: string | null = null, vermelha: string | null = null;
  if (metaAng != null) {
    if (maiorMelhor) {
      vermelha = arc(cx, cy, r, 180, metaAng); // min..meta
      verde = arc(cx, cy, r, metaAng, 0);       // meta..max
    } else {
      verde = arc(cx, cy, r, 180, metaAng);     // min..meta (bom)
      vermelha = arc(cx, cy, r, metaAng, 0);     // meta..max (ruim)
    }
  }

  const needle = polar(cx, cy, r - 10, ang(v));

  return (
    <div style={{ textAlign: "center" }}>
      {titulo && <div style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--text)", marginBottom: "0.2rem" }}>{titulo}</div>}
      <svg viewBox="0 0 200 118" width="100%" style={{ maxWidth: 220, margin: "0 auto", display: "block" }} role="img">
        {/* Trilho de fundo */}
        <path d={arc(cx, cy, r, 180, 0)} fill="none" stroke="var(--surface-2)" strokeWidth="14" strokeLinecap="round" />
        {metaAng != null ? (
          <>
            <path d={vermelha!} fill="none" stroke="var(--red)" strokeWidth="14" opacity="0.85" />
            <path d={verde!} fill="none" stroke="var(--green-light)" strokeWidth="14" opacity="0.9" />
          </>
        ) : (
          <path d={arc(cx, cy, r, 180, 0)} fill="none" stroke={cor} strokeWidth="14" opacity="0.9" />
        )}
        {/* Marca da meta */}
        {metaAng != null && (() => { const p1 = polar(cx, cy, r + 8, metaAng); const p2 = polar(cx, cy, r - 8, metaAng); return <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="var(--text)" strokeWidth="1.5" opacity="0.6" />; })()}
        {/* Ponteiro */}
        {temValor && <line x1={cx} y1={cy} x2={needle.x} y2={needle.y} stroke="var(--text)" strokeWidth="3" strokeLinecap="round" />}
        <circle cx={cx} cy={cy} r="5" fill="var(--text)" />
        {/* Valor */}
        <text x={cx} y={cy - 22} textAnchor="middle" fontSize="24" fontWeight="800" fill="var(--text)">
          {temValor ? `${value}${unidade}` : "—"}
        </text>
      </svg>
      {meta != null && (
        <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginTop: "-0.2rem" }}>
          meta {maiorMelhor ? "≥" : "≤"} {meta}{unidade}
        </div>
      )}
    </div>
  );
}
