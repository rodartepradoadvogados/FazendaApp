"use client";
import { X } from "lucide-react";

/**
 * Modal genérico — overlay escuro + card centralizado com scroll interno.
 * Clique fora ou no X fecha; clique dentro do card não propaga pro overlay.
 */
export function Modal({ title, onClose, width = "820px", zIndex = 90, children }: {
  title: string; onClose: () => void; width?: string; zIndex?: number; children: React.ReactNode;
}) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex, padding: "1rem" }}>
      <div className="card" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}
        style={{ width, maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>{title}</div>
          <button onClick={onClose} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
        </div>
        <div style={{ overflowY: "auto" }}>{children}</div>
      </div>
    </div>
  );
}
