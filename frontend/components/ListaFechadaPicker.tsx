"use client";
import { useMemo, useState } from "react";
import { Search, X, ChevronDown } from "lucide-react";
import { casaBusca } from "@/lib/busca";

export type OpcaoListaFechada = { nome: string; nota?: string | null };

/**
 * Seletor de lista fechada (Raça, Grau de sangue…): mesma "caixa clicável +
 * modal com busca" do AnimalPicker/LotePicker, mas para cadastros simples de
 * nome + nota didática — cada linha mostra o nome e, abaixo, a nota como
 * subtítulo (quando existir). Sempre tem uma opção "(vazio)" no topo, porque
 * esses dois campos são opcionais.
 */
export function ListaFechadaPicker({ opcoes, value, onChange, placeholder = "Selecionar…", rotuloVazio = "(vazio)" }:
  { opcoes: OpcaoListaFechada[]; value: string | null | undefined; onChange: (v: string | null) => void;
    placeholder?: string; rotuloVazio?: string }) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");

  const filtrados = useMemo(
    () => opcoes.filter((o) => casaBusca(`${o.nome} ${o.nota || ""}`, busca)),
    [opcoes, busca]
  );

  const btn: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: value ? "var(--text)" : "var(--text-muted)",
    border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
    textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
  };

  return (
    <>
      <button type="button" style={btn} onClick={() => { setAberto(true); setBusca(""); }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {value || placeholder}
        </span>
        <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>

      {aberto && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70, padding: "1rem" }}
          onClick={() => setAberto(false)}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "520px", maxWidth: "96vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>{placeholder} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({filtrados.length})</span></div>
              <button onClick={() => setAberto(false)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div style={{ position: "relative", marginBottom: "0.6rem" }}>
              <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
              <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar…"
                style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem 0.45rem 2rem", fontSize: "0.85rem" }} />
            </div>
            <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.15rem" }}>
              <div onClick={() => { onChange(null); setAberto(false); }} className="row-clickable"
                style={{ cursor: "pointer", padding: "0.45rem 0.6rem", borderRadius: "var(--r-sm)", background: !value ? "rgba(94,26,46,0.35)" : undefined }}>
                <span style={{ fontStyle: "italic", color: "var(--text-muted)" }}>{rotuloVazio}</span>
              </div>
              {filtrados.map((o) => (
                <div key={o.nome} onClick={() => { onChange(o.nome); setAberto(false); }} className="row-clickable"
                  style={{ cursor: "pointer", padding: "0.45rem 0.6rem", borderRadius: "var(--r-sm)", background: o.nome === value ? "rgba(94,26,46,0.35)" : undefined }}>
                  <div style={{ fontWeight: 600 }}>{o.nome}</div>
                  {o.nota && <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.1rem" }}>{o.nota}</div>}
                </div>
              ))}
              {!filtrados.length && <div style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhuma opção encontrada.</div>}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
