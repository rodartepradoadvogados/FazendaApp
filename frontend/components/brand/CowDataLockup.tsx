import { CowDataMark, type CowDataMarkVariant } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";

// Versão horizontal da marca (ícone + "CowData") — usada nos cabeçalhos do
// site, do app de campo e do Milk News, para o logo ficar idêntico nas 3
// superfícies (ver manual de identidade CowData, seção "Aplicações do logo").
export function CowDataLockup({
  size = 30,
  variant = "escuro",
  cowColor = "var(--text)",
  dataColor = "var(--dourado-light)",
  wordmarkSize = "1rem",
  gap = "0.55rem",
}: {
  size?: number;
  variant?: CowDataMarkVariant;
  cowColor?: string;
  dataColor?: string;
  wordmarkSize?: string | number;
  gap?: string;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap }}>
      <CowDataMark size={size} variant={variant} />
      <CowDataWordmark size={wordmarkSize} cowColor={cowColor} dataColor={dataColor} />
    </span>
  );
}
