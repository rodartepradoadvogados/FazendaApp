"use client";
import { useMemo, useState } from "react";
import { Search, X, ChevronDown } from "lucide-react";
import { useOrdenacao, ThOrdenavel } from "./Ordenavel";

export type EstoqueItemPicker = { nome: string; categoria?: string | null; quantidade?: number | null; unidade?: string | null; estocavel?: boolean | null; finalidade?: string | null; alimento_id?: number | null; estoque_semen_id?: number | null };

/**
 * Seletor de produto do estoque: mesma tabela estilizada (vermelha) usada
 * para escolher animal (AnimalPicker) — nome, categoria e estoque atual —
 * em vez de um campo de texto livre sujeito a erro de digitação. Usado só
 * para definir QUAL medicamento um protocolo/evento sanitário usa (cadastro,
 * não lançamento) — por isso restringe a itens com finalidade "Medicamento"
 * (ração/material/equipamento não fazem sentido aqui), sem exigir saldo.
 */
export function EstoquePicker({ itens, value, onChange, placeholder = "Selecionar produto…", finalidades = ["Medicamento"], somenteVinculadosAlimento = false, incluirNaoEstocaveis = false, disabled = false }:
  { itens: EstoqueItemPicker[]; value: string; onChange: (v: string) => void; placeholder?: string; finalidades?: string[];
    // Restringe aos itens vinculados a um Alimento cadastrado (Configurações >
    // Cadastro > Alimentação > Alimentos) — ou seja, só volumosos, concentrados
    // (proteicos/energéticos), minerais e quaisquer outras categorias que o
    // administrador tenha cadastrado ali, nunca um item de estoque avulso só
    // com finalidade "Ração/Alimento" e sem categorização nutricional.
    somenteVinculadosAlimento?: boolean;
    // Por padrão só mostra itens estocáveis (o caso comum: escolher um
    // medicamento/alimento para aplicar/consumir). O Balanço de estoque (site)
    // usa true para deixar visível também o item cadastrado só para
    // lançamento financeiro, quando o usuário desmarcar "somente itens em estoque".
    incluirNaoEstocaveis?: boolean;
    // Ex.: esperar o usuário escolher um critério de filtro antes de liberar a
    // escolha do produto (ver Sanidade > Aplicação avulsa no app).
    disabled?: boolean;
  }) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const disponiveis = useMemo(
    () => itens
      .filter((i) => (incluirNaoEstocaveis || i.estocavel !== false) && (i.finalidade == null || finalidades.includes(i.finalidade)) && (!somenteVinculadosAlimento || i.alimento_id != null))
      .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR")),
    [itens, finalidades, somenteVinculadosAlimento, incluirNaoEstocaveis]
  );
  const sel = disponiveis.find((i) => i.nome === value);

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return disponiveis;
    return disponiveis.filter((i) => `${i.nome} ${i.categoria || ""}`.toLowerCase().includes(q));
  }, [disponiveis, busca]);

  const ord = useOrdenacao(filtrados);

  const btn: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: sel ? "var(--text)" : "var(--text-muted)",
    border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
    textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
  };

  return (
    <>
      <button type="button" style={{ ...btn, opacity: disabled ? 0.6 : 1, cursor: disabled ? "not-allowed" : "pointer" }} disabled={disabled}
        onClick={() => { setAberto(true); setBusca(""); }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {sel ? sel.nome : (value || placeholder)}
        </span>
        <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>

      {aberto && (
        <div onClick={() => setAberto(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "620px", maxWidth: "96vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>Escolher produto <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({filtrados.length})</span></div>
              <button onClick={() => setAberto(false)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div style={{ position: "relative", marginBottom: "0.6rem" }}>
              <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
              <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por nome ou categoria…"
                style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem 0.45rem 2rem", fontSize: "0.85rem" }} />
            </div>
            <div style={{ overflowY: "auto" }}>
              <table className="fazenda-table">
                <thead>
                  <tr>
                    <ThOrdenavel label="Produto" campo="nome" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                    <ThOrdenavel label="Categoria" campo="categoria" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                    <ThOrdenavel label="Estoque atual" campo="quantidade" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  </tr>
                </thead>
                <tbody>
                  {ord.linhasOrdenadas.map((i) => (
                    <tr key={i.nome} onClick={() => { onChange(i.nome); setAberto(false); }} style={{ cursor: "pointer", background: i.nome === value ? "rgba(94,26,46,0.35)" : undefined }} className="row-clickable">
                      <td style={{ fontWeight: 700 }}>{i.nome}</td>
                      <td style={{ fontSize: "0.75rem" }}>{i.categoria || "—"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{i.quantidade ?? "—"} {i.unidade || ""}</td>
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td colSpan={3} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum produto encontrado.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
