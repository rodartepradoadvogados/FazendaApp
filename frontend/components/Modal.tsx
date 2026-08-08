"use client";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

/**
 * Modal genérico — overlay escuro + card centralizado com scroll interno.
 * Fecha só pelo X; clique dentro do card não propaga pro overlay.
 *
 * Renderizado via portal direto em document.body: sem isso, o modal nascia
 * dentro do wrapper de conteúdo de AuthShell.tsx (que tem z-index:1 próprio,
 * criando um novo contexto de empilhamento) — nesse contexto, o z-index do
 * modal só competia com o que está DENTRO dele, nunca com irmãos de fora
 * como a Sidebar (z-50); resultado: o modal abria visualmente por trás da
 * barra lateral. O portal escapa esse contexto e empilha direto na raiz.
 */
export function Modal({ title, onClose, width = "820px", zIndex = 90, children }: {
  title: string; onClose: () => void; width?: string; zIndex?: number; children: React.ReactNode;
}) {
  const [montado, setMontado] = useState(false);
  useEffect(() => { setMontado(true); }, []);
  if (!montado) return null;

  return createPortal(
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex, padding: "1rem" }}>
      <div className="card" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}
        style={{ width, maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>{title}</div>
          <button onClick={onClose} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
        </div>
        <div style={{ overflowY: "auto" }}>{children}</div>
      </div>
    </div>,
    document.body
  );
}
