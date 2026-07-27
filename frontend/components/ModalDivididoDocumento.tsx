"use client";
import { useEffect, useState } from "react";
import { X, Info } from "lucide-react";
import { Modal } from "@/components/Modal";

/**
 * Mesma casca do Modal genérico, mas quando um documento (nota/recibo/boleto/
 * fatura) é passado, a tela se divide: prévia do documento à esquerda,
 * formulário à direita — ocupando 80% do espaço do app, pra dar espaço real
 * pra ler o documento enquanto preenche/confere os campos. Sem documento
 * ainda, cai no Modal normal (mais estreito) — só divide "ao anexar".
 */
export function ModalDivididoDocumento({ title, onClose, arquivo, children }: {
  title: string; onClose: () => void; arquivo: File | null; children: React.ReactNode;
}) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!arquivo) { setUrl(null); return; }
    const objUrl = URL.createObjectURL(arquivo);
    setUrl(objUrl);
    return () => URL.revokeObjectURL(objUrl);
  }, [arquivo]);

  if (!arquivo) {
    return <Modal title={title} onClose={onClose} width="1000px">{children}</Modal>;
  }

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 90, padding: "1rem" }}>
      <div role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}
        style={{ width: "80vw", height: "80vh", maxWidth: "95vw", maxHeight: "92vh",
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px",
          display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div className="flex items-center justify-between" style={{ padding: "0.7rem 1rem", borderBottom: "1px solid var(--border)" }}>
          <div className="card-header" style={{ margin: 0 }}>{title}</div>
          <button onClick={onClose} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
        </div>
        <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
          <div style={{ flex: "0 0 42%", minWidth: 0, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", background: "var(--surface-2)" }}>
            <div style={{ flex: 1, minHeight: 0, overflow: "auto", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "0.6rem" }}>
              {url && arquivo.type === "application/pdf" ? (
                <iframe src={url} title={arquivo.name} style={{ width: "100%", height: "100%", border: "none", minHeight: "100%" }} />
              ) : url ? (
                <img src={url} alt={arquivo.name} style={{ maxWidth: "100%", borderRadius: "6px" }} />
              ) : null}
            </div>
            <div className="flex items-start gap-2" style={{ padding: "0.6rem 0.8rem", borderTop: "1px solid var(--border)", fontSize: "0.72rem", color: "var(--text-muted)" }}>
              <Info size={13} style={{ flexShrink: 0, marginTop: "0.1rem" }} />
              <span>Este documento é só pra conferência ao preencher os campos — não fica anexado ao sistema (a não ser que você o anexe de propósito no rodapé do lançamento).</span>
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: "0.9rem 1.1rem" }}>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
