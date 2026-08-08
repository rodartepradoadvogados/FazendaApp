"use client";
import { useId } from "react";

// Ícone de marca CowData — "A Curva": uma curva de lactação em ouro (sobe até
// o pico, marcado por um ponto, e desce suave), o único símbolo aprovado da
// marca. NUNCA volte a desenhar vaca, úbere, chifre ou gota — nem incline ou
// inverta o sentido da curva (sobe à esquerda, desce à direita). Fonte única
// do desenho: qualquer outro uso do ícone (favicon, manifest PWA) deriva
// deste mesmo path (ver frontend/public/brand/cowdata-mark.svg, exportado a
// partir daqui).
const PATH_CURVA =
  "M18 92 C30 88 38 50 52 44 C60 41 63 41 70 45 C84 52 90 82 102 90";

export type CowDataMarkVariant = "escuro" | "claro" | "mono";

export function CowDataMark({
  size = 32,
  variant = "escuro",
  color = "var(--gold)",
  legado = false,
}: {
  size?: number | string;
  /** "escuro": tile marinho com curva em gradiente ouro (padrão, lê bem
   *  sobre qualquer fundo). "claro": tile marinho um tom mais claro, para
   *  compor com fundos claros/creme mantendo o mesmo contraste do tile
   *  escuro. "mono": sem tile, só a curva sólida numa cor (marca d'água, ou
   *  onde já existe um fundo). */
  variant?: CowDataMarkVariant;
  /** Só usado em variant="mono" — cor sólida da curva e do ponto. */
  color?: string;
  /** true: mantém o tile vinho/ouro antigo (pré-redesign) — só o app de
   *  campo usa isso hoje (ver app/app/layout.tsx), porque o app ainda não
   *  entrou na rodada do redesign "Institucional". Nenhum outro lugar do
   *  site deve passar isso. */
  legado?: boolean;
}) {
  const gradId = useId();

  if (variant === "mono") {
    return (
      <svg width={size} height={size} viewBox="0 0 120 120" aria-label="CowData" style={{ flexShrink: 0 }}>
        <path d={PATH_CURVA} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" />
        <circle cx="58" cy="42.5" r="4.6" fill={color} />
      </svg>
    );
  }

  const tileBg = legado
    ? (variant === "claro" ? "#3A0F1A" : "#1E0F16")
    : (variant === "claro" ? "#0E2A47" : "#0A1F36");
  const golds = legado
    ? { grad0: "#B9831F", grad1: "#F0C874", ring: "#E0A63C", linha: "#7A2233" }
    : { grad0: "#8A6D2F", grad1: "#C9A44C", ring: "#C9A44C", linha: "#416180" };
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" aria-label="CowData" style={{ flexShrink: 0 }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor={golds.grad0} />
          <stop offset="100%" stopColor={golds.grad1} />
        </linearGradient>
      </defs>
      <rect width="120" height="120" rx="28" fill={tileBg} />
      <rect x="4.5" y="4.5" width="111" height="111" rx="24" fill="none" stroke={golds.ring} strokeOpacity="0.3" strokeWidth="1.3" />
      <line x1="16" y1="92" x2="104" y2="92" stroke={golds.linha} strokeWidth="1.4" />
      <path d={PATH_CURVA} fill="none" stroke={`url(#${gradId})`} strokeWidth="5.5" strokeLinecap="round" />
      <circle cx="58" cy="42.5" r="4.4" fill="#F3E7D3" />
      <circle cx="58" cy="42.5" r="7.6" fill="none" stroke={golds.ring} strokeWidth="1.4" />
    </svg>
  );
}
