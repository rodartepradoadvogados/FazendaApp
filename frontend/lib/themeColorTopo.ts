// Cor da faixa do topo do navegador/app instalado (<meta name="theme-color">)
// e valor padrão do manifesto PWA — precisa acompanhar tema (claro/misto vs.
// escuro) e paleta (vinho vs. verde) juntos. Fonte única: antes esta mesma
// tabela existia copiada em manifest.ts, no script anti-flash de layout.tsx e
// em ThemeSwitcher.tsx, podendo divergir a cada mudança de marca.
export const COR_TOPO = {
  vinho: { clara: "#3A0F1A", escura: "#1E0F16" },
  verde: { clara: "#1F5C3D", escura: "#16402B" },
} as const;

export function corTopo(escuro: boolean, verde: boolean): string {
  const paleta = verde ? COR_TOPO.verde : COR_TOPO.vinho;
  return escuro ? paleta.escura : paleta.clara;
}
