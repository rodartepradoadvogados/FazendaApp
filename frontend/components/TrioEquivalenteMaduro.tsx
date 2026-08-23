"use client";
// Apresentação do trio do equivalente maduro — produz hoje / produzirá na
// maturidade / diferença — nunca o número sozinho. Reaproveitado nos três
// pontos em que o indicador entra no sistema: relatório de Produção,
// calculadora avulsa e card na Ficha do Animal — a regra de exibição fica só
// aqui, uma vez.
//
// Redesign "padronização por vaca": fatores fixos de tabela (Holandês,
// sempre — não depende mais de mínimo de lactações do rebanho) e confiança
// = fração medida/projetada (não mais tamanho de amostra do rebanho). Ver
// `NotaExplicativaEM` abaixo — a nota permanente que explica isso, exigida
// pelo dono junto do card (não é a mesma coisa que o painel de aferição
// colapsável, que compara o fator fixo com o observado no rebanho).
import { Info } from "lucide-react";
import type { NivelConfiancaEM, TrioEquivalenteMaduro as Trio } from "@/lib/api";

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

// Cor por nível de confiança — quanto mais projeção e menos medição, mais
// para o âmbar/vermelho; quanto mais medido, mais para o verde.
export function corNivelConfianca(nivel: NivelConfiancaEM | null | undefined): string {
  switch (nivel) {
    case "alta": return "var(--green-light)";
    case "média": return "var(--dourado-light, var(--amber))";
    case "baixa": return "var(--amber)";
    case "muito baixa": return "var(--red)";
    default: return "var(--text-muted)";
  }
}

/** Pílula de confiança — nível + a fração crua entre parênteses (ex.: "baixa
 * (23%)"), do jeito que o mockup aprovado mostra. */
export function PilulaConfianca({ nivel, fracao }: { nivel: NivelConfiancaEM | null | undefined; fracao?: number | null }) {
  if (!nivel) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  const cor = corNivelConfianca(nivel);
  return (
    <span
      style={{
        fontSize: "0.72rem", fontWeight: 700, color: cor, background: `color-mix(in srgb, ${cor} 14%, transparent)`,
        borderRadius: "999px", padding: "0.1rem 0.55rem", whiteSpace: "nowrap",
      }}
      title="Confiança = quanto do total de 305 dias é leite já medido nesta vaca, não projeção"
    >
      {nivel}{fracao != null && ` (${Math.round(fracao * 100)}%)`}
    </span>
  );
}

/** As três caixas — produz hoje, produzirá, diferença — mais o rodapé de
 * proveniência (ordem de parto, nº de controles, confiança). Quando
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
            <p style={{ ...estiloValor, fontSize: "0.85rem", fontStyle: "italic", color: "var(--text-muted)" }}>já está na maturidade</p>
          ) : (
            <p style={{ ...estiloValor, color: (trio.diferenca_kg ?? 0) > 0 ? "var(--amber)" : "var(--text-muted)" }}>
              {(trio.diferenca_kg ?? 0) > 0 ? "+" : ""}{fmt(trio.diferenca_kg)} kg
            </p>
          )}
        </div>
      </div>
      <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", margin: "0.5rem 0 0", display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
        {trio.ordem_parto != null ? `${trio.ordem_parto}ª cria` : "ordem de parto desconhecida"}
        {" · "}{trio.n_controles} {trio.n_controles === 1 ? "controle" : "controles"} na conta
        {trio.confianca_nivel && (
          <>
            {" · confiança: "}
            <PilulaConfianca nivel={trio.confianca_nivel} fracao={trio.confianca_fracao} />
          </>
        )}
      </p>
      {trio.sem_base && trio.motivo && (
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", margin: "0.3rem 0 0", fontStyle: "italic" }}>{trio.motivo}</p>
      )}
    </div>
  );
}

/** Nota explicativa PERMANENTE (não colapsável) — exigida junto do card em
 * toda tela que mostra o trio: todo animal é padronizado como Holandês
 * independente da raça cadastrada, o que "confiança" significa aqui, e os
 * três fatores fixos de tabela. Não é o painel de aferição (esse compara o
 * fator fixo com o observado no rebanho, é colapsável e fica só no
 * relatório) — esta nota explica o MÉTODO e fica sempre visível. */
export function NotaExplicativaEM() {
  return (
    <div
      style={{
        display: "flex", gap: "0.5rem", alignItems: "flex-start", marginTop: "0.75rem",
        padding: "0.65rem 0.85rem", borderRadius: "var(--r-sm)", background: "var(--surface-2)",
        borderLeft: "3px solid var(--dourado, var(--amber))",
      }}
    >
      <Info size={14} style={{ flexShrink: 0, marginTop: "0.15rem", color: "var(--text-muted)" }} />
      <p style={{ margin: 0, fontSize: "0.74rem", color: "var(--text-muted)", lineHeight: 1.55 }}>
        Todo animal é padronizado como <strong>Holandês</strong>, independente da raça/grau de sangue cadastrado —
        é o padrão usado para calcular quanto cada vaca ainda vai crescer até a maturidade.
        Fatores fixos de tabela: <strong>1ª cria → 1,22</strong> · <strong>2ª cria → 1,08</strong> · <strong>madura → 1,00</strong>.
        {" "}<strong>Confiança</strong> não é margem estatística: é a fração do total de 305 dias que já é leite
        de fato medido nesta vaca (cai com o DEL, sobe com o controle em dia — o resto é projeção pela curva de
        referência, não uma amostra do rebanho).
      </p>
    </div>
  );
}
