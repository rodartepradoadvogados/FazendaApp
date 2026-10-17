"use client";
// Peças visuais do ciclo de diagnóstico: resultado P/V/I, situação (a tocar / a reconfirmar / reconfirmada),
// selo AINDA NÃO e a legenda. Usadas pela tabela dos cards (site) e pelas linhas do app — as cores vêm dos tokens
// --ft-* de app/globals.css, que já têm a versão AA de cada tema. Cor nunca é o único sinal: P, V e I levam letra,
// e o selo leva texto e ampulheta. Regras de negócio: backend rules/fase_toque.py.
import { Hourglass } from "lucide-react";
import { ROTULO_FASE, regraDoPrazo, textoFaltam, type FaseToque } from "@/lib/fasesToque";

const fmtCurto = (iso: string | null | undefined) => {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
};
const fmtCompleto = (iso: string | null | undefined) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "");

const TITULO_RESULTADO: Record<string, string> = { P: "Prenha", V: "Vazia", I: "Indefinida" };

/** "POSITIVO" | "NEGATIVO" | "INDEFINIDO" → P | V | I (outro valor: sem selo). */
export function letraResultado(diagnostico: string | null | undefined): "P" | "V" | "I" | null {
  const d = (diagnostico ?? "").trim().toUpperCase();
  if (d === "POSITIVO") return "P";
  if (d === "NEGATIVO") return "V";
  if (d === "INDEFINIDO") return "I";
  return null;
}

export function BadgeResultado({ letra }: { letra: "P" | "V" | "I" }) {
  return <span className={`ft-res ${letra.toLowerCase()}`} title={TITULO_RESULTADO[letra]} aria-label={TITULO_RESULTADO[letra]}>{letra}</span>;
}

/** Célula de exame: data + P/V/I, ou "–" quando ainda não houve. */
export function CelulaExame({ data, diagnostico }: { data: string | null | undefined; diagnostico: string | null | undefined }) {
  const letra = letraResultado(diagnostico);
  if (!data && !letra) return <span className="ft-traco" title="Ainda não houve">–</span>;
  return (
    <span style={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }} title={data ? fmtCompleto(data) : undefined}>
      {data ? fmtCurto(data) : ""}{letra && <BadgeResultado letra={letra} />}
    </span>
  );
}

export function ChipFase({ fase }: { fase: FaseToque | null | undefined }) {
  if (!fase) return <span className="ft-traco">–</span>;
  return <span className={`ft-st ft-st-${fase}`}>{ROTULO_FASE[fase]}</span>;
}

/** Selo dourado AINDA NÃO · faltam N d. `prazoTipo` só afina o texto de ajuda (toque ou reconfirmação). */
export function SeloAindaNao({ dias, prazoTipo }: { dias: number | null | undefined; prazoTipo?: "toque" | "reconfirmacao" | null }) {
  const alvo = prazoTipo === "reconfirmacao" ? "reconfirmação" : "toque";
  const texto = textoFaltam(dias);
  return (
    <span className="ft-selo" title={`Ainda dentro do prazo para ${alvo}${texto ? `: ${texto}` : ""}. Dá para lançar mesmo assim.`}>
      <Hourglass size={11} aria-hidden="true" />Ainda não{texto ? ` · ${texto}` : ""}
    </span>
  );
}

/** Legenda de baixo da tabela: P/V/I, o traço e o selo, com o prazo da fazenda. */
export function LegendaToque({ parametros }: { parametros?: { dias_toque: number; dias_reconfirmacao: number } | null }) {
  return (
    <div className="ft-legenda" data-testid="legenda-toque">
      <span><span className="ft-res p">P</span>prenha</span>
      <span><span className="ft-res v">V</span>vazia</span>
      <span><span className="ft-res i">I</span>indefinida</span>
      <span><span className="ft-traco">–</span> ainda não houve</span>
      <span><span className="ft-selo" style={{ margin: 0 }}>Ainda não</span> dentro do prazo: {regraDoPrazo(parametros)}</span>
    </div>
  );
}
