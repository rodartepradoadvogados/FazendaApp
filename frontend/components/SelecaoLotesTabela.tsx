"use client";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

export type LoteRow = {
  id: number;
  codigo: string;
  nome: string;
  status_lactacao?: string | null;
};

// Seleção de VÁRIOS lotes de uma vez — mesma tabela estilizada de SelecaoAnimaisTabela.
export function SelecaoLotesTabela({ lotes, selecionados, toggle, toggleTodos }: {
  lotes: LoteRow[];
  selecionados: Set<string>;
  toggle: (codigo: string) => void;
  toggleTodos: () => void;
}) {
  const ord = useOrdenacao(lotes);
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>
      <div style={{ background: "var(--surface-2)", padding: "0.55rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.4rem" }}>
        <span style={{ fontSize: "0.85rem" }}>{lotes.length} lote(s) — {selecionados.size} selecionado(s)</span>
        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={toggleTodos} disabled={!lotes.length}>
          {selecionados.size === lotes.length && lotes.length ? "Limpar seleção" : "Selecionar todos"}
        </button>
      </div>
      <div className="overflow-x-auto" style={{ maxHeight: "260px" }}>
        <table className="fazenda-table" style={{ margin: 0 }}>
          <thead><tr>
            <th></th>
            <ThOrdenavel label="Código" campo="codigo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
            <ThOrdenavel label="Nome" campo="nome" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
            <ThOrdenavel label="Status" campo="status_lactacao" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          </tr></thead>
          <tbody>
            {ord.linhasOrdenadas.map((l) => (
              <tr key={l.codigo} style={{ cursor: "pointer" }} onClick={() => toggle(l.codigo)}>
                <td><input type="checkbox" checked={selecionados.has(l.codigo)} onChange={() => toggle(l.codigo)} onClick={(e) => e.stopPropagation()} /></td>
                <td style={{ fontSize: "0.8rem", fontWeight: 700 }}>{l.codigo}</td>
                <td style={{ fontSize: "0.8rem" }}>{l.nome}</td>
                <td style={{ fontSize: "0.78rem" }}>{l.status_lactacao || "—"}</td>
              </tr>
            ))}
            {!lotes.length && (
              <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum lote cadastrado.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
