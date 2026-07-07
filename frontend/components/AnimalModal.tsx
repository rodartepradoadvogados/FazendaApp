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
  data_ult_servico_pos?: string | null;
  data_ult_parto?: string | null;
};

const SIT_CORES: Record<string, string> = {
  "Ges.": "var(--green-light)", "Vaz. apt.": "var(--blue)", "Vaz. atr.": "var(--red)",
  "Vaz. pev": "var(--amber)", "Ins.": "var(--dourado-light)",
};

const GESTACAO = 280;
const diasEntre = (aIso: string, bIso: string) =>
  Math.round((new Date(bIso + "T00:00:00").getTime() - new Date(aIso + "T00:00:00").getTime()) / 86400000);

// Indicadores reprodutivos por animal, calculados das datas de serviço/parto.
function repro(a: AnimalRow) {
  const hoje = new Date().toISOString().slice(0, 10);
  const sit = a.sit_rep || "";
  let gestacao: number | null = null, paraParto: number | null = null, partoData: string | null = null, pev: number | null = null;
  if (sit === "Ges." && a.data_ult_servico_pos) {
    gestacao = diasEntre(a.data_ult_servico_pos, hoje);
    const p = new Date(a.data_ult_servico_pos + "T00:00:00"); p.setDate(p.getDate() + GESTACAO);
    partoData = p.toLocaleDateString("pt-BR");
    paraParto = Math.round((p.getTime() - new Date(hoje + "T00:00:00").getTime()) / 86400000);
  }
  if (sit.startsWith("Vaz.") && a.data_ult_parto) pev = diasEntre(a.data_ult_parto, hoje);
  return { gestacao, paraParto, partoData, pev };
}

/** Modal que lista os animais por trás de um número (drill-down). */
export function AnimalModal({ title, animais, onClose }: { title: string; animais: AnimalRow[]; onClose: () => void }) {
  const temRepro = animais.some((a) => a.data_ult_servico_pos || a.data_ult_parto);
  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }}
    >
      <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: temRepro ? "820px" : "640px", maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>{title} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({animais.length})</span></div>
          <button onClick={onClose} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
        </div>
        <div style={{ overflowY: "auto" }}>
          {animais.length ? (
            <table className="fazenda-table">
              <thead><tr>
                <th>Nº</th><th>Grupo</th><th>Categoria</th><th>Sit. Rep.</th><th style={{ textAlign: "right" }}>DEL</th>
                {temRepro && <><th style={{ textAlign: "right" }}>Gest.</th><th style={{ textAlign: "right" }}>P/ parto</th><th>Parto prov.</th><th style={{ textAlign: "right" }}>PEV</th></>}
              </tr></thead>
              <tbody>
                {animais.map((a) => {
                  const r = repro(a);
                  return (
                    <tr key={a.numero}>
                      <td style={{ fontWeight: 700 }}>{a.numero}</td>
                      <td style={{ fontSize: "0.75rem" }}>{a.grupo_primario || "—"}</td>
                      <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || a.categoria_completa || "—"}</td>
                      <td><span style={{ color: SIT_CORES[a.sit_rep || ""] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{a.sit_rep || "—"}</span></td>
                      <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
                      {temRepro && <>
                        <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{r.gestacao != null ? `${r.gestacao}d` : "—"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.78rem", color: r.paraParto != null && r.paraParto <= 30 ? "var(--green-light)" : undefined }}>{r.paraParto != null ? `${r.paraParto}d` : "—"}</td>
                        <td style={{ fontSize: "0.75rem" }}>{r.partoData || "—"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{r.pev != null ? `${r.pev}d` : "—"}</td>
                      </>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", padding: "1rem" }}>Nenhum animal.</p>}
        </div>
      </div>
    </div>
  );
}
