"use client";
import { AnimalRow } from "@/components/AnimalModal";

// Seleção de VÁRIOS animais de uma vez, com a mesma tabela estilizada (cabeçalho
// vinho/dourado via .fazenda-table) usada em Rebanho > Baixar animal / Movimentar
// animais — substitui listas de checkbox simples/brancas por esta, mais clara.
export function SelecaoAnimaisTabela({ animais, selecionados, toggle, toggleTodos, colunas }: {
  animais: AnimalRow[];
  selecionados: Set<string>;
  toggle: (numero: string) => void;
  toggleTodos: () => void;
  colunas: { header: string; render: (a: AnimalRow) => React.ReactNode }[];
}) {
  // Ordem numérica crescente pelo número do animal (consistente com o resto do site).
  const ordenados = [...animais].sort((a, b) => a.numero.localeCompare(b.numero, undefined, { numeric: true }));
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
      <div style={{ background: "var(--surface-2)", padding: "0.55rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.4rem" }}>
        <span style={{ fontSize: "0.85rem" }}>{ordenados.length} animal(is) — {selecionados.size} selecionado(s)</span>
        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={toggleTodos} disabled={!ordenados.length}>
          {selecionados.size === ordenados.length && ordenados.length ? "Limpar seleção" : "Selecionar todos"}
        </button>
      </div>
      <div className="overflow-x-auto" style={{ maxHeight: "260px" }}>
        <table className="fazenda-table" style={{ margin: 0 }}>
          <thead><tr><th></th>{colunas.map((c) => <th key={c.header}>{c.header}</th>)}</tr></thead>
          <tbody>
            {ordenados.map((a) => (
              <tr key={a.numero} style={{ cursor: "pointer" }} onClick={() => toggle(a.numero)}>
                <td><input type="checkbox" checked={selecionados.has(a.numero)} onChange={() => toggle(a.numero)} onClick={(e) => e.stopPropagation()} /></td>
                {colunas.map((c) => <td key={c.header} style={{ fontSize: "0.8rem" }}>{c.render(a)}</td>)}
              </tr>
            ))}
            {!ordenados.length && (
              <tr><td colSpan={colunas.length + 1} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum animal disponível.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
