"use client";
// Campo de seleção múltipla com busca — substitui a "parede de botões" sem
// filtro que existia em Cadastrar > Medicamentos (Painel CowData) e o
// <select> simples de Princípio ativo no cadastro de Item de Estoque.
// Pedido do usuário (31/08/2026): "Precisa de um campo chamado princípio
// ativo, e, clicando, abre em pop up para seleção, com filtro e,
// igualmente, a categoria."
//
// Sem tema próprio: usa os tokens CSS do site (--surface/--border/--text)
// por padrão, mas aceita `cor` (mesmo formato de CoresPainelCowData) pra
// funcionar também dentro do Painel CowData, que não usa esses tokens.
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { normalizarBusca as normalizar } from "@/lib/busca";

export type OpcaoSeletor = { id: number; nome: string; grupo?: string };

type CoresSeletor = { bg: string; borda: string; texto: string; mudo: string; dourado: string; painelAlt: string };
const CORES_PADRAO: CoresSeletor = {
  bg: "var(--surface)", borda: "var(--border)", texto: "var(--text)", mudo: "var(--text-muted)",
  dourado: "var(--dourado)", painelAlt: "var(--surface-2)",
};

export default function SeletorMultiploComBusca({
  label, opcoes, selecionados, onChange, placeholder, cor,
}: {
  label?: string; opcoes: OpcaoSeletor[]; selecionados: number[]; onChange: (ids: number[]) => void;
  placeholder?: string; cor?: Partial<CoresSeletor>;
}) {
  const C = { ...CORES_PADRAO, ...cor };
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    const fechar = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setAberto(false); };
    document.addEventListener("mousedown", fechar);
    return () => document.removeEventListener("mousedown", fechar);
  }, [aberto]);

  const porId = useMemo(() => new Map(opcoes.map((o) => [o.id, o])), [opcoes]);
  const filtradas = useMemo(() => {
    const q = normalizar(busca.trim());
    const lista = q ? opcoes.filter((o) => normalizar(o.nome).includes(q)) : opcoes;
    const grupos = new Map<string, OpcaoSeletor[]>();
    for (const o of lista) {
      const g = o.grupo || "";
      if (!grupos.has(g)) grupos.set(g, []);
      grupos.get(g)!.push(o);
    }
    return grupos;
  }, [opcoes, busca]);

  function alternar(id: number) {
    onChange(selecionados.includes(id) ? selecionados.filter((x) => x !== id) : [...selecionados, id]);
  }
  function remover(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    onChange(selecionados.filter((x) => x !== id));
  }

  return (
    <div ref={ref} style={{ position: "relative" }}>
      {label && <label style={{ display: "block", fontSize: "0.7rem", color: C.mudo, marginBottom: "0.25rem" }}>{label}</label>}
      <div onClick={() => setAberto((v) => !v)}
        style={{
          display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap", cursor: "pointer",
          border: `1px solid ${C.borda}`, background: C.bg, borderRadius: 6, padding: "0.4rem 0.6rem", minHeight: "2.1rem",
        }}>
        {selecionados.length === 0 && <span style={{ color: C.mudo, fontSize: "0.82rem" }}>{placeholder || "Selecionar…"}</span>}
        {selecionados.map((id) => {
          const opt = porId.get(id);
          if (!opt) return null;
          return (
            <span key={id} style={{
              display: "inline-flex", alignItems: "center", gap: "0.3rem", padding: "0.15rem 0.5rem", borderRadius: 999,
              background: C.painelAlt, border: `1px solid ${C.borda}`, fontSize: "0.78rem", color: C.texto,
            }}>
              {opt.nome}
              <button type="button" onClick={(e) => remover(id, e)} style={{ background: "none", border: "none", color: C.mudo, cursor: "pointer", padding: 0, lineHeight: 1 }}>
                <X size={11} />
              </button>
            </span>
          );
        })}
        <ChevronDown size={13} style={{ marginLeft: "auto", color: C.mudo, flexShrink: 0 }} />
      </div>

      {aberto && (
        <div style={{
          position: "absolute", zIndex: 20, top: "calc(100% + 0.3rem)", left: 0, right: 0, minWidth: 260,
          border: `1px solid ${C.borda}`, borderRadius: 8, background: C.bg, boxShadow: "0 12px 28px rgba(0,0,0,.25)", overflow: "hidden",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.65rem", borderBottom: `1px solid ${C.borda}` }}>
            <Search size={13} color={C.mudo} />
            <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar…"
              style={{ background: "none", border: "none", outline: "none", color: C.texto, fontSize: "0.82rem", width: "100%" }} />
          </div>
          <div style={{ maxHeight: 260, overflowY: "auto" }}>
            {[...filtradas.entries()].map(([grupo, itens]) => (
              <div key={grupo || "_"}>
                {grupo && (
                  <div style={{ fontSize: "0.64rem", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 800, color: C.mudo, padding: "0.5rem 0.65rem 0.2rem" }}>
                    {grupo}
                  </div>
                )}
                {itens.map((o) => {
                  const sel = selecionados.includes(o.id);
                  return (
                    <div key={o.id} onClick={() => alternar(o.id)}
                      style={{
                        display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.45rem 0.65rem", cursor: "pointer",
                        fontSize: "0.82rem", color: sel ? C.dourado : C.texto, fontWeight: sel ? 700 : 400,
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = C.painelAlt)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                      {o.nome}
                      {sel && <Check size={13} style={{ marginLeft: "auto" }} />}
                    </div>
                  );
                })}
              </div>
            ))}
            {[...filtradas.values()].every((l) => l.length === 0) && (
              <p style={{ padding: "0.6rem 0.65rem", fontSize: "0.78rem", color: C.mudo, margin: 0 }}>Nada encontrado.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
