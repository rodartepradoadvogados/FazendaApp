"use client";
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import type { PortalDestinatario } from "@/lib/api";

/**
 * Campo "Para:" do Portal — digitar "@" (ou simplesmente focar o campo) abre
 * a lista de destinatários, com "Marcar todos" sempre como primeira opção.
 * Seleção múltipla, cada escolhido vira um chip removível.
 */
export function PortalMencaoInput({ opcoes, selecionados, onChange, placeholder }: {
  opcoes: PortalDestinatario[];
  selecionados: number[];
  onChange: (ids: number[]) => void;
  placeholder?: string;
}) {
  const [texto, setTexto] = useState("");
  const [aberto, setAberto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setAberto(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const todosMarcados = opcoes.length > 0 && selecionados.length === opcoes.length;
  const filtro = texto.replace(/^@/, "").toLowerCase();
  const filtrados = opcoes.filter((o) => (o.nome || o.username).toLowerCase().includes(filtro));

  function alternarTodos() {
    onChange(todosMarcados ? [] : opcoes.map((o) => o.id));
    setTexto("");
  }
  function alternar(id: number) {
    onChange(selecionados.includes(id) ? selecionados.filter((x) => x !== id) : [...selecionados, id]);
    setTexto("");
  }

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <div
        onClick={() => setAberto(true)}
        style={{
          display: "flex", flexWrap: "wrap", gap: "0.35rem", alignItems: "center",
          border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface-2)",
          padding: "0.35rem 0.5rem", minHeight: "2.3rem", cursor: "text",
        }}
      >
        {todosMarcados ? (
          <Chip label="Todos" onRemover={() => onChange([])} />
        ) : (
          selecionados.map((id) => {
            const o = opcoes.find((x) => x.id === id);
            if (!o) return null;
            return <Chip key={id} label={o.nome || o.username} onRemover={() => onChange(selecionados.filter((x) => x !== id))} />;
          })
        )}
        <input
          value={texto}
          onChange={(e) => { setTexto(e.target.value); setAberto(true); }}
          onFocus={() => setAberto(true)}
          placeholder={selecionados.length ? "" : (placeholder || "Digite @ para marcar destinatário…")}
          style={{ flex: 1, minWidth: 140, border: "none", outline: "none", background: "transparent", color: "var(--text)", fontSize: "0.85rem" }}
        />
      </div>
      {aberto && (
        <div style={{
          position: "absolute", zIndex: 50, top: "100%", left: 0, right: 0, marginTop: 4,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
          boxShadow: "0 8px 24px rgba(0,0,0,0.18)", maxHeight: 240, overflowY: "auto",
        }}>
          <button type="button" onClick={alternarTodos}
            style={{ width: "100%", textAlign: "left", padding: "0.5rem 0.7rem", background: todosMarcados ? "var(--surface-2)" : "none", border: "none", borderBottom: "1px solid var(--border)", cursor: "pointer", fontWeight: 700, fontSize: "0.82rem", color: "var(--text)" }}>
            {todosMarcados ? "✓ " : ""}Marcar todos
          </button>
          {filtrados.length === 0 && <div style={{ padding: "0.5rem 0.7rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>Ninguém encontrado.</div>}
          {filtrados.map((o) => {
            const on = selecionados.includes(o.id);
            return (
              <button type="button" key={o.id} onClick={() => alternar(o.id)}
                style={{ width: "100%", textAlign: "left", padding: "0.45rem 0.7rem", background: on ? "var(--surface-2)" : "none", border: "none", cursor: "pointer", fontSize: "0.82rem", color: "var(--text)" }}>
                {on ? "✓ " : ""}{o.nome || o.username}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Chip({ label, onRemover }: { label: string; onRemover: () => void }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", background: "var(--dourado)", color: "#fff", borderRadius: 999, padding: "0.15rem 0.5rem 0.15rem 0.6rem", fontSize: "0.75rem", fontWeight: 600 }}>
      {label}
      <button type="button" onClick={(e) => { e.stopPropagation(); onRemover(); }} style={{ background: "none", border: "none", color: "#fff", cursor: "pointer", display: "flex", padding: 0 }}>
        <X size={12} />
      </button>
    </span>
  );
}
