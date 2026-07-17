// Ícone ilustrativo do "News" (blog de pecuária leiteira) — uma folha de
// jornal com dobra, foto e linhas de manchete, ao invés de um glifo genérico
// de biblioteca. Usado no cabeçalho do app (faixa da cor da paleta, ao lado
// do alternador claro/escuro) e reaproveitado onde mais fizer sentido.
export function NewsIcon({ size = 22, color = "currentColor", destaque = "#FFE066" }: { size?: number; color?: string; destaque?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4.5 3.5h11.2l3.3 3.3V19.5a1 1 0 0 1-1 1h-13.5a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1z" fill={color} opacity="0.14" />
      <path d="M4.5 3.5h11.2l3.3 3.3V19.5a1 1 0 0 1-1 1h-13.5a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1z" stroke={color} strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M15.7 3.5v3.3H19" stroke={color} strokeWidth="1.4" strokeLinejoin="round" />
      <rect x="6.7" y="8.1" width="4" height="4" rx="0.6" fill={destaque} />
      <path d="M12.4 8.5h4.3M12.4 10.4h4.3" stroke={color} strokeWidth="1.15" strokeLinecap="round" />
      <path d="M6.7 14.1h9.9M6.7 16.2h9.9M6.7 18.3h6.2" stroke={color} strokeWidth="1.15" strokeLinecap="round" />
    </svg>
  );
}
