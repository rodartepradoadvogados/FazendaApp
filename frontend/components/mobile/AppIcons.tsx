// Ícones ilustrativos da navegação do app — a cor principal vem do prop
// `color` (padrão "currentColor"), controlada pelo chamador via a variável
// CSS --aba (ver .mob-nav em globals.css e ABAS em app/app/layout.tsx): cada
// aba tem sua própria cor quando ativa, e a cor neutra --mob-nav-inativa
// quando não. O calendário mantém o "papel" de fundo em --mob-surface (ou
// branco) para continuar lendo como um corpo de calendário, não só um
// contorno.
export function CalendarColorfulIcon({ size = 22, color = "currentColor", strokeWidth = 1.2 }: { size?: number; strokeWidth?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="6.6" y="2.2" width="1.6" height="3.6" rx="0.8" fill={color} />
      <rect x="15.8" y="2.2" width="1.6" height="3.6" rx="0.8" fill={color} />
      <rect x="3" y="4.2" width="18" height="16.6" rx="2.4" fill="var(--mob-surface)" stroke={color} strokeWidth={strokeWidth} />
      <path d="M3 4.2a2.4 2.4 0 0 1 2.4-2.4h13.2A2.4 2.4 0 0 1 21 4.2v3.3H3V4.2z" fill={color} />
      <circle cx="7.3" cy="13" r="1.1" fill={color} />
      <circle cx="12" cy="13" r="1.1" fill={color} />
      <circle cx="16.7" cy="13" r="1.1" fill={color} />
      <circle cx="7.3" cy="17.2" r="1.1" fill={color} />
      <circle cx="12" cy="17.2" r="1.1" fill={color} />
      <circle cx="16.7" cy="17.2" r="1.1" fill={color} />
    </svg>
  );
}

export function MenuTricolorIcon({ size = 22, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="5.4" width="18" height="2.7" rx="1.35" fill={color} />
      <rect x="3" y="10.65" width="18" height="2.7" rx="1.35" fill={color} />
      <rect x="3" y="15.9" width="18" height="2.7" rx="1.35" fill={color} />
    </svg>
  );
}
