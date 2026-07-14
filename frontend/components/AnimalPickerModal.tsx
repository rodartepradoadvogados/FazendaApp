"use client";
import { useMemo, useState } from "react";
import { Search, X, ChevronDown } from "lucide-react";
import { AnimalRow } from "./AnimalModal";

/**
 * Padrão único de seleção de VÁRIOS animais no site: um botão mostra quantos
 * já foram escolhidos e, ao tocar, abre uma tela suspensa com busca + tabela
 * marcável — em vez de uma lista de checkbox sempre aberta ocupando a página
 * (como era em Inseminação/Diagnóstico) ou de overlays reimplementados a cada
 * tela. Mesmo visual do `AnimalPicker` (seleção única), com checkboxes.
 */
export function AnimalPickerModal({ animais, selecionados, onToggle, colunas, placeholder = "Selecionar animais…", titulo = "Escolher animais" }: {
  animais: AnimalRow[];
  selecionados: Set<string>;
  onToggle: (numero: string) => void;
  colunas: { header: string; render: (a: AnimalRow) => React.ReactNode }[];
  placeholder?: string;
  titulo?: string;
}) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return animais;
    return animais.filter((a) =>
      `${a.numero} ${a.grupo_primario || ""} ${a.categoria_abrev || a.categoria_completa || ""} ${a.sit_rep || ""}`.toLowerCase().includes(q));
  }, [animais, busca]);

  const todosFiltradosSelecionados = filtrados.length > 0 && filtrados.every((a) => selecionados.has(a.numero));
  function alternarFiltrados() {
    filtrados.forEach((a) => {
      const selecionado = selecionados.has(a.numero);
      if (todosFiltradosSelecionados ? selecionado : !selecionado) onToggle(a.numero);
    });
  }

  const btn: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: selecionados.size ? "var(--text)" : "var(--text-muted)",
    border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
    textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
  };

  return (
    <>
      <button type="button" style={btn} onClick={() => { setAberto(true); setBusca(""); }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {selecionados.size ? `${selecionados.size} animal(is) selecionado(s)` : placeholder}
        </span>
        <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>

      {aberto && (
        <div onClick={() => setAberto(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "720px", maxWidth: "96vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>
                {titulo} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({selecionados.size}/{animais.length})</span>
              </div>
              <button onClick={() => setAberto(false)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div style={{ position: "relative", marginBottom: "0.6rem" }}>
              <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
              <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por número, grupo, categoria…"
                style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem 0.45rem 2rem", fontSize: "0.85rem" }} />
            </div>
            <div className="flex items-center justify-between mb-2">
              <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={alternarFiltrados} disabled={!filtrados.length}>
                {todosFiltradosSelecionados ? "Limpar seleção" : "Selecionar todos"}{busca.trim() ? " (filtrados)" : ""}
              </button>
            </div>
            <div style={{ overflowY: "auto" }}>
              <table className="fazenda-table">
                <thead><tr><th></th>{colunas.map((c) => <th key={c.header}>{c.header}</th>)}</tr></thead>
                <tbody>
                  {filtrados.map((a) => (
                    <tr key={a.numero} onClick={() => onToggle(a.numero)} style={{ cursor: "pointer" }} className="row-clickable">
                      <td><input type="checkbox" checked={selecionados.has(a.numero)} onChange={() => onToggle(a.numero)} onClick={(e) => e.stopPropagation()} /></td>
                      {colunas.map((c) => <td key={c.header} style={{ fontSize: "0.8rem" }}>{c.render(a)}</td>)}
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td colSpan={colunas.length + 1} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum animal encontrado.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-end mt-3">
              <button type="button" className="btn-primary" onClick={() => setAberto(false)}>Concluir</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
