"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Check, AlertTriangle, X } from "lucide-react";

/**
 * Aviso flutuante de confirmação (toast) — não existia nenhum sistema desse
 * tipo no app antes (04/09/2026); telas hoje confirmam salvamento com um
 * texto inline (ex.: FormDiagnostico's `sucesso`), que fica na tela até a
 * próxima ação. O toast é um COMPLEMENTO a isso, não substitui: confirma na
 * hora, sem travar a tela nem exigir clique pra fechar — mesmo padrão de
 * `Modal.tsx` (entra com animação, sai com uma pausa antes de desmontar).
 *
 * Mesmo padrão de contexto de `ExportContext.tsx`: Provider no layout raiz +
 * hook de uso em qualquer componente client.
 */
export type ToastTipo = "sucesso" | "erro";
type ToastItem = { id: number; texto: string; tipo: ToastTipo };

const DURACAO_AUTO_MS = 2400;
const DURACAO_SAIDA_MS = 180;

const ToastContext = createContext<((texto: string, tipo?: ToastTipo) => void) | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [itens, setItens] = useState<ToastItem[]>([]);
  const [saindo, setSaindo] = useState<Set<number>>(new Set());
  const proximoId = useRef(1);
  const [montado, setMontado] = useState(false);
  useEffect(() => setMontado(true), []); // createPortal precisa de `document`, que só existe no cliente

  const remover = useCallback((id: number) => {
    setSaindo((s) => new Set(s).add(id));
    setTimeout(() => {
      setItens((p) => p.filter((t) => t.id !== id));
      setSaindo((s) => { const n = new Set(s); n.delete(id); return n; });
    }, DURACAO_SAIDA_MS);
  }, []);

  const mostrar = useCallback((texto: string, tipo: ToastTipo = "sucesso") => {
    const id = proximoId.current++;
    setItens((p) => [...p, { id, texto, tipo }]);
    setTimeout(() => remover(id), DURACAO_AUTO_MS);
  }, [remover]);

  return (
    <ToastContext.Provider value={mostrar}>
      {children}
      {montado && createPortal(
        <div className="toast-container">
          {itens.map((t) => (
            <div key={t.id} className={"toast-item" + (saindo.has(t.id) ? " toast-saindo" : "")} role="status"
              style={{
                display: "flex", alignItems: "center", gap: "0.55rem", pointerEvents: "auto",
                background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)",
                borderRadius: "0.6rem", padding: "0.6rem 0.75rem 0.6rem 0.9rem", boxShadow: "0 10px 28px rgba(0,0,0,0.25)",
                minWidth: 240, maxWidth: 380,
              }}>
              {t.tipo === "sucesso" ? <Check size={16} color="var(--green-light, #0b7a4b)" style={{ flexShrink: 0 }} /> : <AlertTriangle size={16} color="var(--red)" style={{ flexShrink: 0 }} />}
              <span style={{ fontSize: "0.85rem", flex: 1 }}>{t.texto}</span>
              <button type="button" onClick={() => remover(t.id)} className="btn-ghost" style={{ padding: "0.15rem", flexShrink: 0 }} aria-label="Fechar aviso">
                <X size={13} />
              </button>
            </div>
          ))}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  );
}

/** `useToast()("Salvo com sucesso")` ou `useToast()("Erro ao salvar", "erro")`. */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast precisa estar dentro de <ToastProvider> (ver app/layout.tsx)");
  return ctx;
}
