"use client";
import { X } from "lucide-react";

export type AnimalRow = {
  numero: string;
  grupo_primario?: string | null;
  categoria_abrev?: string | null;
  categoria_completa?: string | null;
  raca?: string | null;
  sit_rep?: string | null;
  del_dias?: number | null;
  ult_cl_kg?: number | null;
};

const SIT_CORES: Record<string, string> = {
  "Ges.": "var(--green-light)", "Vaz. apt.": "var(--blue)", "Vaz. atr.": "var(--red)",
  "Vaz. pev": "var(--amber)", "Ins.": "var(--dourado-light)",
};

/** Modal que lista os animais por trás de um número (drill-down). */
export function AnimalModal({ title, animais, onClose }: { title: string; animais: AnimalRow[]; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }}
    >
      <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "640px", maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>{title} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({animais.length})</span></div>
          <button onClick={onClose} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
        </div>
        <div style={{ overflowY: "auto" }}>
          {animais.length ? (
            <table className="fazenda-table">
              <thead><tr><th>Nº</th><th>Grupo</th><th>Categoria</th><th>Raça</th><th>Sit. Rep.</th><th style={{ textAlign: "right" }}>DEL</th></tr></thead>
              <tbody>
                {animais.map((a) => (
                  <tr key={a.numero}>
                    <td style={{ fontWeight: 700 }}>{a.numero}</td>
                    <td style={{ fontSize: "0.75rem" }}>{a.grupo_primario || "—"}</td>
                    <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || a.categoria_completa || "—"}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.raca || "—"}</td>
                    <td><span style={{ color: SIT_CORES[a.sit_rep || ""] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{a.sit_rep || "—"}</span></td>
                    <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", padding: "1rem" }}>Nenhum animal.</p>}
        </div>
      </div>
    </div>
  );
}
