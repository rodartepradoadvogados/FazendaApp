"use client";
import { useMemo, useState } from "react";
import { Search, X, ChevronDown, Check } from "lucide-react";
import { AnimalRow } from "./AnimalModal";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

export type LoteOpcao = { codigo: string; total: number; categoria: string; del_medio: number | null };

// Constrói as opções de lote (com mais dados) a partir da lista de animais —
// nº de animais no lote, categoria predominante e DEL médio.
export function opcoesLoteDeAnimais(animais: AnimalRow[], codigos: string[]): LoteOpcao[] {
  return codigos.map((codigo) => {
    const doLote = animais.filter((a) => (a.grupo_primario || "") === codigo);
    const catCount = new Map<string, number>();
    let somaDel = 0, nDel = 0;
    for (const a of doLote) {
      const cat = a.categoria_abrev || a.categoria_completa || "—";
      catCount.set(cat, (catCount.get(cat) || 0) + 1);
      if (a.del_dias != null) { somaDel += a.del_dias; nDel += 1; }
    }
    const categoria = Array.from(catCount.entries()).sort((x, y) => y[1] - x[1])[0]?.[0] || "—";
    return { codigo, total: doLote.length, categoria, del_medio: nDel ? Math.round(somaDel / nDel) : null };
  });
}

/**
 * Seletor de lote(s) — a mesma "lista bonita vermelha suspensa" do AnimalPicker,
 * mas para lotes e com seleção múltipla (checkbox). Mostra código, nº de
 * animais, categoria predominante e DEL médio, em vez de só o código.
 */
export function LotePicker({ opcoes, selecionados, onChange, placeholder = "Selecionar lote(s)…" }:
  { opcoes: LoteOpcao[]; selecionados: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const sel = new Set(selecionados);

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return opcoes;
    return opcoes.filter((o) => `${o.codigo} ${o.categoria}`.toLowerCase().includes(q));
  }, [opcoes, busca]);
  const ord = useOrdenacao(filtrados);

  const toggle = (codigo: string) => {
    const novo = new Set(sel);
    novo.has(codigo) ? novo.delete(codigo) : novo.add(codigo);
    onChange(Array.from(novo));
  };
  const todos = () => onChange(sel.size === opcoes.length ? [] : opcoes.map((o) => o.codigo));

  const btn: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: sel.size ? "var(--text)" : "var(--text-muted)",
    border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
    textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
  };

  return (
    <>
      <button type="button" style={btn} onClick={() => { setAberto(true); setBusca(""); }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {sel.size ? (sel.size === 1 ? selecionados[0] : `${sel.size} lotes selecionados`) : placeholder}
        </span>
        <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>

      {aberto && (
        <div onClick={() => setAberto(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "560px", maxWidth: "96vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>Escolher lote(s) <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({filtrados.length})</span></div>
              <button onClick={() => setAberto(false)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div style={{ position: "relative", marginBottom: "0.6rem" }}>
              <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
              <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por código ou categoria…"
                style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem 0.45rem 2rem", fontSize: "0.85rem" }} />
            </div>
            <div style={{ overflowY: "auto" }}>
              <table className="fazenda-table">
                <thead><tr>
                  <th style={{ width: 32 }}><button onClick={todos} className="btn-ghost" style={{ fontSize: "0.68rem", padding: "0.1rem 0.3rem" }}>{sel.size === opcoes.length && opcoes.length ? "Limpar" : "Todos"}</button></th>
                  <ThOrdenavel label="Lote" campo="codigo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Animais" campo="total" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  <ThOrdenavel label="Categoria" campo="categoria" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="DEL médio" campo="del_medio" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                </tr></thead>
                <tbody>
                  {ord.linhasOrdenadas.map((o) => (
                    <tr key={o.codigo} onClick={() => toggle(o.codigo)} style={{ cursor: "pointer", background: sel.has(o.codigo) ? "rgba(94,26,46,0.35)" : undefined }} className="row-clickable">
                      <td style={{ textAlign: "center" }}>{sel.has(o.codigo) ? <Check size={14} style={{ color: "var(--dourado-light)" }} /> : null}</td>
                      <td style={{ fontWeight: 700 }}>{o.codigo}</td>
                      <td style={{ textAlign: "right" }}>{o.total}</td>
                      <td style={{ fontSize: "0.75rem" }}>{o.categoria}</td>
                      <td style={{ textAlign: "right" }}>{o.del_medio ?? "—"}</td>
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum lote encontrado.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end mt-3">
              <button onClick={() => setAberto(false)} className="btn-primary" style={{ fontSize: "0.82rem" }}>Concluir</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
