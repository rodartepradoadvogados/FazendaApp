"use client";
import { Dna, X } from "lucide-react";

/** Modal de detalhes do touro — usado sempre que se quer ver a "prova
 * completa" de um touro (não só um resumo) a partir de qualquer tela: Rebanho
 * > Touros, cadastro do animal (genealogia do pai/avô/bisavô), etc. */
export function TouroDetalheModal({ titulo, campos, onFechar, nota }: {
  titulo: string;
  campos: [string, string][];
  onFechar: () => void;
  nota?: string;
}) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }} onClick={onFechar}>
      <div className="card" style={{ maxWidth: 480, width: "90%", maxHeight: "80vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="card-header mb-3 flex items-center justify-between">
          <span className="flex items-center gap-2"><Dna size={16} /> {titulo}</span>
          <button className="btn-ghost" onClick={onFechar}><X size={16} /></button>
        </div>
        <table className="fazenda-table" style={{ margin: 0 }}>
          <tbody>
            {campos.map(([label, valor], i) => (
              <tr key={i}>
                <td style={{ fontSize: "0.78rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>{label}</td>
                <td style={{ fontSize: "0.85rem", fontWeight: 600 }}>{valor}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {nota && (
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.75rem" }}>{nota}</p>
        )}
      </div>
    </div>
  );
}
