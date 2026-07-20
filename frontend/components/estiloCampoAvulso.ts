// Estilos de campo compartilhados pelas telas de lançamento avulso
// (Empreitada/Contrato/Diária e seus vales) — extraídos aqui para não
// duplicar o mesmo par label/input em cada arquivo (backlog #532).
import type { CSSProperties } from "react";

export const lbl: CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };
export const inputSm: CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", width: "100%",
};
