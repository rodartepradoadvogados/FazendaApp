/**
 * Wordmark da marca CowData — "Cow" + "Data" em dois tons, sem ilustração
 * (ver design "CowData - 6 Aplicacoes da Logo"). "Data" usa o dourado da
 * marca (var(--dourado-light) — já reage a tema/paleta sozinho). "Cow" usa
 * a cor de texto certa para o fundo onde a marca está sentada — por isso é
 * parametrizável (o fundo varia: branco no site claro, vinho/verde no
 * misto, escuro no site/app escuro).
 */
export function CowDataWordmark({
  size = "0.8rem",
  cowColor = "var(--text)",
  dataColor = "var(--dourado-light)",
}: {
  size?: string | number;
  cowColor?: string;
  dataColor?: string;
}) {
  return (
    <span style={{ fontWeight: 800, letterSpacing: "-0.01em", fontSize: size, whiteSpace: "nowrap" }}>
      <span style={{ color: cowColor }}>Cow</span>
      <span style={{ color: dataColor }}>Data</span>
    </span>
  );
}
