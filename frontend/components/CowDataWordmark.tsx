import { MILK_FLORIO, MILK_FLORIO_STROKE, MILK_GLYPHS, MILK_GOTA, MILK_TRANSFORM, MILK_VIEW_W } from "@/components/brand/milkPath";

/**
 * Wordmark da marca "CowData Milk": "Cow" + "Data" em dois tons e "Milk"
 * em cursiva inclinada, um pouco abaixo da linha do CowData, com um floreio
 * dourado que termina numa gota de leite (logomarca aprovada em 24/10/2026).
 * "Data" e o floreio usam o dourado da marca (var(--dourado-light) — já
 * reage a tema/paleta sozinho). "Cow" usa a cor de texto certa para o fundo
 * onde a marca está sentada, por isso é parametrizável. "Milk" usa
 * --marca-milk (azul-aço no claro, azul-claro no escuro) ou `milkColor`.
 *
 * `produto={null}` desenha só "CowData" — é a marca da empresa, usada no
 * Painel CowData (plataforma, que não é o produto Milk).
 */
export function CowDataWordmark({
  size = "0.8rem",
  cowColor = "var(--text)",
  dataColor = "var(--dourado-light)",
  milkColor = "var(--marca-milk, #416180)",
  produto = "milk",
}: {
  size?: string | number;
  cowColor?: string;
  dataColor?: string;
  milkColor?: string;
  produto?: "milk" | null;
}) {
  const largura = `${MILK_VIEW_W / 100}em`;
  return (
    <span style={{ fontWeight: 800, letterSpacing: "-0.01em", fontSize: size, whiteSpace: "nowrap" }} aria-label={produto ? "CowData Milk" : "CowData"}>
      <span style={{ color: cowColor }} aria-hidden="true">Cow</span>
      <span style={{ color: dataColor }} aria-hidden="true">Data</span>
      {produto === "milk" && (
        <span aria-hidden="true" style={{ position: "relative", display: "inline-block", width: largura, height: 0 }}>
          <svg viewBox={`0 -100 ${MILK_VIEW_W} 150`} width={largura} height="1.5em"
            style={{ position: "absolute", left: 0, top: "-1em", overflow: "visible" }}>
            <g transform={MILK_TRANSFORM}>
              {/* traço de 1,8% do em engrossa a cursiva para ela não sumir em tamanho pequeno */}
              <path d={MILK_GLYPHS} fill={milkColor} stroke={milkColor} strokeWidth={1.8} strokeLinejoin="round" />
              <path d={MILK_FLORIO} fill="none" stroke={dataColor} strokeWidth={MILK_FLORIO_STROKE} strokeLinecap="round" />
              <path d={MILK_GOTA} fill={dataColor} />
            </g>
          </svg>
        </span>
      )}
    </span>
  );
}
