/**
 * Marca "CWD milk" para o cabeçalho — o mesmo monograma de traço único
 * aprovado para a marca d'água do login (ver LoginWatermark.tsx: a perna de
 * cima do C emenda no topo do W, que emenda no topo-esquerda do D, com
 * "milk" cursivo na barriga do D). Paleta de cores diferente da versão do
 * login: aqui C, W e "milk" acompanham a cor de texto da barra lateral
 * (vinho/verde/branco conforme tema+paleta, mesma lógica de `cowColor` em
 * CowDataWordmark); o D fica sempre dourado fixo, independente da paleta
 * escolhida.
 */
export function CwdMilkMark({
  size = 28,
  color = "var(--sidebar-fg)",
}: {
  size?: number;
  color?: string;
}) {
  const height = size * (400 / 1160);
  return (
    <svg viewBox="0 0 1160 400" width={size} height={height} aria-hidden="true" style={{ flexShrink: 0 }}>
      <path d="M240,305 A140,140 0 1 1 240,75"
        fill="none" stroke={color} strokeWidth="36" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M240,75 L380,305 L520,75 L660,305 L920,75"
        fill="none" stroke={color} strokeWidth="36" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M920,75 L920,305 A150,150 0 1,0 920,74.9"
        fill="none" stroke="var(--dourado-fixo)" strokeWidth="36" strokeLinecap="round" strokeLinejoin="round" />
      <text x="1015" y="272" textAnchor="middle" className="font-script" fontSize="60" fill={color}>Milk</text>
    </svg>
  );
}
