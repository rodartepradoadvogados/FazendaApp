"use client";
// Barra de ação fixa das telas de lote, logo acima da navegação do app (mesma posição da barra do Diagnóstico).
import type { ReactNode } from "react";

/** Passo 1: o número de marcados bem grande à esquerda e "Continuar" à direita. Sem ninguém marcado o botão fica cinza. */
export function BarraContinuar({ n, fora, onContinuar, rotulo = "Continuar" }: { n: number; fora: number; onContinuar: () => void; rotulo?: string }) {
  return (
    <div className="lote-barra linha">
      {/* aria-live: quem usa leitor de tela ouve a contagem mudar a cada toque */}
      <div className="n" aria-live="polite" aria-atomic="true">
        {/* key = o número: cada mudança remonta o <b> e a animação de "pulso" roda de novo */}
        <b key={n} className="bump">{n}</b>
        <span>{n === 1 ? "marcado" : "marcados"}{fora > 0 && <small>({fora} fora deste filtro)</small>}</span>
      </div>
      <button type="button" className="lote-cta" disabled={n === 0} onClick={onContinuar}>{n === 0 ? "Marque pelo menos 1" : rotulo}</button>
    </div>
  );
}

/** Passo 2: só o(s) botão(ões) de ação, um abaixo do outro. */
export function BarraAcao({ children }: { children: ReactNode }) {
  return <div className="lote-barra">{children}</div>;
}
