"use client";
// Apresentação do trio do equivalente maduro — produz hoje / produzirá na
// maturidade / diferença — nunca o número sozinho (ver seção 1 e 4 de
// docs/equivalente-maduro-proposta.md). Reaproveitado nos três pontos em que
// o indicador entra no sistema: relatório de Produção, calculadora avulsa e
// card na Ficha do Animal — a regra de exibição fica só aqui, uma vez.
import type { TrioEquivalenteMaduro as Trio } from "@/lib/api";

function fmt(v: number | null | undefined) {
  return v == null ? "—" : v.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

const estiloTile: React.CSSProperties = {
  background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)",
  padding: "0.6rem 0.8rem", flex: "1 1 8rem", minWidth: "8rem",
};
const estiloRotulo: React.CSSProperties = {
  fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", margin: "0 0 0.25rem",
};
const estiloValor: React.CSSProperties = { fontSize: "1.05rem", fontWeight: 700, margin: 0 };

/** As três caixas — produz hoje, produzirá, diferença — mais o rodapé de
 * proveniência (ordem de parto, nº de controles, confiança do fator). Quando
 * `sem_base`, mostra só a produção real e o motivo — nunca inventa um
 * "produzirá". */
export function TrioEquivalenteMaduroView({ trio }: { trio: Trio }) {
  return (
    <div>
      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
        <div style={estiloTile}>
          <p style={estiloRotulo}>Produz hoje</p>
          <p style={estiloValor}>{fmt(trio.producao_hoje_kg)} kg</p>
        </div>
        <div style={estiloTile}>
          <p style={estiloRotulo}>Produzirá (madura)</p>
          <p style={estiloValor}>
            {trio.sem_base ? "—" : trio.ja_maduro ? `${fmt(trio.producao_hoje_kg)} kg` : `${fmt(trio.producao_maturidade_kg)} kg`}
          </p>
        </div>
        <div style={estiloTile}>
          <p style={estiloRotulo}>Diferença</p>
          {trio.sem_base ? (
            <p style={{ ...estiloValor, fontSize: "0.8rem", fontWeight: 500, color: "var(--text-muted)" }}>sem base para ajustar</p>
          ) : trio.ja_maduro ? (
            <p style={{ ...estiloValor, fontSize: "0.85rem", color: "var(--green-light)" }}>já está na maturidade</p>
          ) : trio.faixa_diferenca_kg ? (
            <p style={{ ...estiloValor, color: "var(--amber)" }}>
              {fmt(trio.faixa_diferenca_kg[0])} a +{fmt(trio.faixa_diferenca_kg[1])} kg
            </p>
          ) : (
            <p style={{ ...estiloValor, color: (trio.diferenca_kg ?? 0) > 0 ? "var(--amber)" : "var(--text-muted)" }}>
              {(trio.diferenca_kg ?? 0) > 0 ? "+" : ""}{fmt(trio.diferenca_kg)} kg
            </p>
          )}
        </div>
      </div>
      <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", margin: "0.5rem 0 0" }}>
        {trio.ordem_parto != null ? `${trio.ordem_parto}ª cria` : "ordem de parto desconhecida"}
        {" · "}{trio.n_controles} {trio.n_controles === 1 ? "controle" : "controles"} na conta
        {trio.confianca_fator && ` · confiança do fator: ${trio.confianca_fator === "ok" ? "boa" : "baixa (poucas lactações na classe)"}`}
        {trio.faixa_diferenca_kg && " · faixa por ser 1ª cria — incerteza maior"}
      </p>
      {trio.sem_base && trio.motivo && (
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", margin: "0.3rem 0 0", fontStyle: "italic" }}>{trio.motivo}</p>
      )}
    </div>
  );
}
