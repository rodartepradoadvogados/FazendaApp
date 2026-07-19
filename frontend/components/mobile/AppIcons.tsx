// Ícones ilustrativos (coloridos) da navegação do app — substituem glifos
// monocromáticos de biblioteca por versões com cor própria, usando os tokens
// da paleta (--mob-vinho/--mob-dourado/--mob-verde/--mob-azul) para já vir
// certo em qualquer variante de tema/paleta.
export function CalendarColorfulIcon({ size = 22 }: { size?: number; strokeWidth?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="6.6" y="2.2" width="1.6" height="3.6" rx="0.8" fill="var(--mob-vinho)" />
      <rect x="15.8" y="2.2" width="1.6" height="3.6" rx="0.8" fill="var(--mob-vinho)" />
      <rect x="3" y="4.2" width="18" height="16.6" rx="2.4" fill="#fff" stroke="var(--mob-vinho)" strokeWidth="1.2" />
      <path d="M3 4.2a2.4 2.4 0 0 1 2.4-2.4h13.2A2.4 2.4 0 0 1 21 4.2v3.3H3V4.2z" fill="var(--mob-vinho)" />
      <circle cx="7.3" cy="13" r="1.1" fill="var(--mob-dourado)" />
      <circle cx="12" cy="13" r="1.1" fill="var(--mob-verde)" />
      <circle cx="16.7" cy="13" r="1.1" fill="var(--mob-azul)" />
      <circle cx="7.3" cy="17.2" r="1.1" fill="var(--mob-verde)" />
      <circle cx="12" cy="17.2" r="1.1" fill="var(--mob-vinho)" />
      <circle cx="16.7" cy="17.2" r="1.1" fill="var(--mob-dourado)" />
    </svg>
  );
}

export function MenuTricolorIcon({ size = 22 }: { size?: number; strokeWidth?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="5.4" width="18" height="2.7" rx="1.35" fill="var(--mob-vinho)" />
      <rect x="3" y="10.65" width="18" height="2.7" rx="1.35" fill="var(--mob-dourado)" />
      <rect x="3" y="15.9" width="18" height="2.7" rx="1.35" fill="var(--mob-verde)" />
    </svg>
  );
}
