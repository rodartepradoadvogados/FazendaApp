"use client";
import { AnimalRow } from "@/components/AnimalModal";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

// Seleção de VÁRIOS animais de uma vez, com a mesma tabela estilizada (cabeçalho
// vinho/dourado via .fazenda-table) usada em Rebanho > Baixar animal / Movimentar
// animais — substitui listas de checkbox simples/brancas por esta, mais clara.
export function SelecaoAnimaisTabela({ animais, selecionados, toggle, toggleTodos, colunas }: {
  animais: AnimalRow[];
  selecionados: Set<string>;
  toggle: (numero: string) => void;
  toggleTodos: () => void;
  // `campo` é opcional: quando informado (e existir em AnimalRow), o cabeçalho
  // vira clicável via ThOrdenavel; colunas sem campo continuam simples <th>,
  // já que `render` pode compor valores que não existem como chave única na linha.
  colunas: { header: string; campo?: string; render: (a: AnimalRow) => React.ReactNode }[];
}) {
  // Ordem numérica crescente pelo número do animal por padrão (consistente com
  // o resto do site) — o clique num cabeçalho ordenável substitui esse critério.
  const base = [...animais].sort((a, b) => a.numero.localeCompare(b.numero, undefined, { numeric: true }));
  const ord = useOrdenacao(base);
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>
      <div style={{ background: "var(--surface-2)", padding: "0.55rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.4rem" }}>
        <span style={{ fontSize: "0.85rem" }}>{base.length} animal(is) — {selecionados.size} selecionado(s)</span>
        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={toggleTodos} disabled={!base.length}>
          {selecionados.size === base.length && base.length ? "Limpar seleção" : "Selecionar todos"}
        </button>
      </div>
      <div className="overflow-x-auto" style={{ maxHeight: "260px" }}>
        <table className="fazenda-table" style={{ margin: 0 }}>
          <thead><tr><th></th>{colunas.map((c) => c.campo
            ? <ThOrdenavel key={c.header} label={c.header} campo={c.campo} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
            : <th key={c.header}>{c.header}</th>)}</tr></thead>
          <tbody>
            {ord.linhasOrdenadas.map((a) => (
              <tr key={a.numero} style={{ cursor: "pointer" }} onClick={() => toggle(a.numero)}>
                <td><input type="checkbox" checked={selecionados.has(a.numero)} onChange={() => toggle(a.numero)} onClick={(e) => e.stopPropagation()} /></td>
                {colunas.map((c) => <td key={c.header} style={{ fontSize: "0.8rem" }}>{c.render(a)}</td>)}
              </tr>
            ))}
            {!base.length && (
              <tr><td colSpan={colunas.length + 1} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum animal disponível.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
