"use client";
import { useMemo, useState } from "react";
import { Search, X, ChevronDown } from "lucide-react";
import { AnimalRow } from "./AnimalModal";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";

const SIT_CORES: Record<string, string> = {
  "Ges.": "var(--green-light)", "Vaz. apt.": "var(--blue)", "Vaz. atr.": "var(--red)",
  "Vaz. pev": "var(--amber)", "Ins.": "var(--dourado-light)",
  Gestante: "var(--green-light)", Inseminada: "var(--dourado-light)", "Em protocolo (IA atual)": "var(--dourado-light)",
  PEV: "var(--amber)", Apta: "var(--blue)", Atrasada: "var(--red)", "Não apta": "var(--text-muted)", Vazia: "var(--blue)",
};

/**
 * Seletor de animal claro: mostra uma tabela (Nº · Grupo · Categoria · Sit. Rep.
 * · DEL) igual à dos indicadores, evitando confundir o número do animal com o
 * do lote. Abre num clique, tem busca, e devolve o número escolhido.
 */
export function AnimalPicker({ animais, value, onChange, placeholder = "Selecionar animal…" }:
  { animais: AnimalRow[]; value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const sel = animais.find((a) => a.numero === value);
  const { rotuloDe } = useEstadosReprodutivos();

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return animais;
    return animais.filter((a) =>
      `${a.numero} ${a.grupo_primario || ""} ${a.categoria_abrev || a.categoria_completa || ""} ${rotuloDe(a.numero)}`.toLowerCase().includes(q));
  }, [animais, busca, rotuloDe]);

  const btn: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: sel ? "var(--text)" : "var(--text-muted)",
    border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
    textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
  };

  return (
    <>
      <button type="button" style={btn} onClick={() => { setAberto(true); setBusca(""); }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {sel ? <><strong>{sel.numero}</strong> · {sel.categoria_abrev || sel.categoria_completa || sel.grupo_primario || "—"}{rotuloDe(sel.numero) !== "—" ? ` · ${rotuloDe(sel.numero)}` : ""}</> : placeholder}
        </span>
        <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>

      {aberto && (
        <div onClick={() => setAberto(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "680px", maxWidth: "96vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>Escolher animal <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({filtrados.length})</span></div>
              <button onClick={() => setAberto(false)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div style={{ position: "relative", marginBottom: "0.6rem" }}>
              <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
              <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por número, grupo, categoria…"
                style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem 0.45rem 2rem", fontSize: "0.85rem" }} />
            </div>
            <div style={{ overflowY: "auto" }}>
              <table className="fazenda-table">
                <thead><tr><th>Nº</th><th>Grupo</th><th>Categoria</th><th>Sit. Rep.</th><th style={{ textAlign: "right" }}>DEL</th></tr></thead>
                <tbody>
                  {filtrados.map((a) => (
                    <tr key={a.numero} onClick={() => { onChange(a.numero); setAberto(false); }} style={{ cursor: "pointer", background: a.numero === value ? "rgba(94,26,46,0.35)" : undefined }} className="row-clickable">
                      <td style={{ fontWeight: 700 }}>{a.numero}</td>
                      <td style={{ fontSize: "0.75rem" }}>{a.grupo_primario || "—"}</td>
                      <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || a.categoria_completa || "—"}</td>
                      <td><span style={{ color: SIT_CORES[rotuloDe(a.numero)] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{rotuloDe(a.numero)}</span></td>
                      <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum animal encontrado.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
