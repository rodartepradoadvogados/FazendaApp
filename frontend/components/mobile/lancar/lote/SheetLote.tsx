"use client";
// Folha de confirmação (sheet) e aviso rápido (toast) das telas de lote. A folha prende o foco, fecha no Esc e devolve o
// foco ao botão que a abriu; o toast fala por aria-live e some sozinho.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

const FOCAVEIS = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function SheetLote({ titulo, onFechar, children }: { titulo: string; onFechar: () => void; children: ReactNode }) {
  const caixa = useRef<HTMLDivElement>(null);
  const aoFechar = useRef(onFechar);
  useEffect(() => { aoFechar.current = onFechar; });

  useEffect(() => {
    const anterior = document.activeElement as HTMLElement | null;
    const primeiro = caixa.current?.querySelector<HTMLElement>(FOCAVEIS);
    primeiro?.focus();
    function aoTeclar(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); aoFechar.current(); return; }
      if (e.key !== "Tab" || !caixa.current) return;
      const itens = [...caixa.current.querySelectorAll<HTMLElement>(FOCAVEIS)];
      if (!itens.length) return;
      const ultimo = itens[itens.length - 1];
      const inicio = itens[0];
      if (e.shiftKey && document.activeElement === inicio) { e.preventDefault(); ultimo.focus(); }
      else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); inicio.focus(); }
    }
    document.addEventListener("keydown", aoTeclar);
    // O app rola dentro do <body>: com a folha aberta o fundo não pode rolar por baixo.
    const rolagemAntes = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", aoTeclar); document.body.style.overflow = rolagemAntes; anterior?.focus?.(); };
  }, []);

  return (
    <div className="lote-sheet-wrap" role="presentation" onClick={onFechar}>
      <div ref={caixa} className="lote-sheet" role="dialog" aria-modal="true" aria-label={titulo} onClick={(e) => e.stopPropagation()}>
        <h3>{titulo}</h3>
        {children}
      </div>
    </div>
  );
}

/** Aviso rápido no topo (não cobre o botão de ação). `mostrar("texto")` acende; some em ~3 s. */
export function useToastLote(): { toast: ReactNode; mostrar: (texto: string) => void } {
  const [texto, setTexto] = useState<string | null>(null);
  const relogio = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mostrar = useCallback((t: string) => {
    setTexto(t);
    if (relogio.current) clearTimeout(relogio.current);
    relogio.current = setTimeout(() => setTexto(null), 3200);
  }, []);
  useEffect(() => () => { if (relogio.current) clearTimeout(relogio.current); }, []);
  return { toast: texto ? <div className="lote-toast" role="status">{texto}</div> : null, mostrar };
}
