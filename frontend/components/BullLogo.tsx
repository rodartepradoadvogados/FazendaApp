"use client";

/**
 * Marca da fazenda — cabeça de touro estilizada, inspirada na logomarca
 * "Fazenda Jairo Nasser", em traços dourados sobre o fundo vinho da identidade.
 */
export function BullLogo({ size = 22, color = "var(--dourado-light)" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none"
      stroke={color} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {/* chifres */}
      <path d="M20 23 C 11 17, 6 21, 9 28 C 12 24, 16 24, 20 26" />
      <path d="M44 23 C 53 17, 58 21, 55 28 C 52 24, 48 24, 44 26" />
      {/* orelhas */}
      <path d="M20 25 C 14 24, 11 27, 15 31" />
      <path d="M44 25 C 50 24, 53 27, 49 31" />
      {/* cabeça */}
      <path d="M20 25 C 18 36, 23 48, 32 48 C 41 48, 46 36, 44 25 C 40 29, 36 30, 32 30 C 28 30, 24 29, 20 25 Z" />
      {/* focinho / narinas */}
      <circle cx="28.5" cy="41" r="1.1" fill={color} stroke="none" />
      <circle cx="35.5" cy="41" r="1.1" fill={color} stroke="none" />
    </svg>
  );
}
