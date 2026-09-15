"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

// Duração da saída (ver .popup-fundo/.popup-caixa em globals.css) — precisa
// bater com o CSS pra desmontar só depois da animação terminar visualmente.
const DURACAO_SAIDA_MS = 160;

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
 *
 * Entrada/saída (04/09/2026): a entrada é só CSS (`.popup-fundo`/`.popup-caixa`
 * em globals.css, aplicada assim que monta). A saída precisa de um estado
 * interno (`saindo`) porque o React desmontaria o modal na hora — sem essa
 * pausa, a chamada de `onClose` do consumidor nunca teria como "esperar" a
 * animação antes de sumir o componente da árvore. `onClose` continua com a
 * mesma assinatura de sempre; quem chama este componente não muda nada.
 */
export function Modal({ title, onClose, width = "820px", zIndex = 90, children }: {
  title: string; onClose: () => void; width?: string; zIndex?: number; children: React.ReactNode;
}) {
  const [montado, setMontado] = useState(false);
  const [saindo, setSaindo] = useState(false);
  const caixaRef = useRef<HTMLDivElement>(null);
  const gatilhoRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    gatilhoRef.current = document.activeElement as HTMLElement | null;
    setMontado(true);
  }, []);

  function fechar() {
    const reduzido = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduzido) { onClose(); return; }
    setSaindo(true);
    setTimeout(onClose, DURACAO_SAIDA_MS);
  }

  // Foco preso dentro do diálogo (Tab/Shift+Tab não escapam), Esc fecha, e o
  // foco volta pra quem abriu o modal ao fechar — sem isso, um usuário de
  // teclado/leitor de tela perdia a posição no resto da página inteira.
  useEffect(() => {
    if (!montado) return;
    const caixa = caixaRef.current;
    if (!caixa) return;
    const seletorFocavel = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';
    const primeiro = caixa.querySelector<HTMLElement>(seletorFocavel);
    (primeiro || caixa).focus();

    function aoTeclar(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); fechar(); return; }
      if (e.key !== "Tab" || !caixa) return;
      const focaveis = Array.from(caixa.querySelectorAll<HTMLElement>(seletorFocavel)).filter((el) => el.offsetParent !== null);
      if (!focaveis.length) return;
      const [primeiroFocavel, ultimoFocavel] = [focaveis[0], focaveis[focaveis.length - 1]];
      if (e.shiftKey && document.activeElement === primeiroFocavel) { e.preventDefault(); ultimoFocavel.focus(); }
      else if (!e.shiftKey && document.activeElement === ultimoFocavel) { e.preventDefault(); primeiroFocavel.focus(); }
    }
    document.addEventListener("keydown", aoTeclar);
    return () => {
      document.removeEventListener("keydown", aoTeclar);
      gatilhoRef.current?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [montado]);

  if (!montado) return null;

  return createPortal(
    <div className={"popup-fundo" + (saindo ? " popup-saindo" : "")}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex, padding: "1rem" }}>
      <div ref={caixaRef} tabIndex={-1} className={"card popup-caixa" + (saindo ? " popup-saindo" : "")} role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}
        style={{ width, maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column", outline: "none" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>{title}</div>
          <button onClick={fechar} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
        </div>
        <div style={{ overflowY: "auto" }}>{children}</div>
      </div>
    </div>,
    document.body
  );
}
