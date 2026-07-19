// Ícone ilustrativo de "Rebanho" — uma vaquinha branca com manchinhas pretas
// (padrão holandesa), ao invés do glifo genérico de biblioteca (Beef). Usado
// no menu lateral do site, no rodapé do app e na aba Animais de Rebanho.
export function CowIcon({ size = 24, color = "#2b2b2b" }: { size?: number; color?: string; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      {/* orelhas */}
      <ellipse cx="4.6" cy="8.4" rx="2.3" ry="2.9" fill="#fff" stroke={color} strokeWidth="1.1" />
      <ellipse cx="19.4" cy="8.4" rx="2.3" ry="2.9" fill="#fff" stroke={color} strokeWidth="1.1" />
      {/* cabeça */}
      <ellipse cx="12" cy="12.6" rx="7.9" ry="7" fill="#fff" stroke={color} strokeWidth="1.2" />
      {/* manchinhas pretas */}
      <ellipse cx="8" cy="8.9" rx="2" ry="1.6" fill={color} transform="rotate(-25 8 8.9)" />
      <ellipse cx="16.3" cy="15.2" rx="2.3" ry="1.8" fill={color} transform="rotate(18 16.3 15.2)" />
      <ellipse cx="16.5" cy="8.6" rx="1.2" ry="1" fill={color} transform="rotate(10 16.5 8.6)" />
      {/* focinho */}
      <ellipse cx="12" cy="16.9" rx="4.4" ry="2.8" fill="#fff" stroke={color} strokeWidth="1.1" />
      <ellipse cx="10.4" cy="17.1" rx="0.55" ry="0.75" fill={color} />
      <ellipse cx="13.6" cy="17.1" rx="0.55" ry="0.75" fill={color} />
      {/* olhos */}
      <circle cx="8.6" cy="11.7" r="0.95" fill={color} />
      <circle cx="15.4" cy="11.7" r="0.95" fill={color} />
    </svg>
  );
}
