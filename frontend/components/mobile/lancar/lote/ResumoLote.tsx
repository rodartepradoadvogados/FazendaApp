"use client";
// Peças do Passo 2 compartilhadas: cartão-resumo "N animais · Alterar", seção recolhível e opção grande de escolha única.
import type { ReactNode } from "react";
import { ChevronRight, Check } from "lucide-react";

export function ResumoLote({ titulo, sub, onAlterar }: { titulo: string; sub: ReactNode; onAlterar: () => void }) {
  return (
    <div className="lote-resumo">
      <div>
        <div className="g">{titulo}</div>
        <div className="p">{sub}</div>
      </div>
      <button type="button" className="lote-btn56" onClick={onAlterar}>Alterar</button>
    </div>
  );
}

export function ColapsavelLote({ titulo, dica, aberto, onAlternar, children }: {
  titulo: ReactNode; dica: ReactNode; aberto: boolean; onAlternar: () => void; children: ReactNode;
}) {
  return (
    <div className="lote-colap" data-aberto={aberto ? "1" : "0"}>
      <button type="button" aria-expanded={aberto} onClick={onAlternar}>
        <span><span className="v">{titulo}</span><span className="h">{dica}</span></span>
        <ChevronRight size={22} aria-hidden="true" />
      </button>
      {aberto && <div className="conteudo">{children}</div>}
    </div>
  );
}

/** Botão grande de escolha única (lote de destino, touro): nome, apoio e um número à direita. */
export function OpcaoLote({ nome, sub, selecionado, bloqueada, numero, onClick }: {
  nome: ReactNode; sub?: ReactNode; selecionado: boolean; bloqueada?: boolean; numero?: ReactNode; onClick: () => void;
}) {
  return (
    <button type="button" className="lote-opcao" aria-pressed={selecionado} aria-disabled={bloqueada || undefined} onClick={onClick}>
      <span style={{ minWidth: 0 }}>
        <span className="nm">{nome}</span>
        {sub && <span className="sb2">{sub}</span>}
      </span>
      <span className="num">{numero}<span className="ok" aria-hidden="true"><Check size={16} strokeWidth={3.2} /></span></span>
    </button>
  );
}
