"use client";

import React from "react";
import { AlertTriangle, LayoutGrid, ListChecks } from "lucide-react";

export type VisaoAgenda = "dia" | "painel";

/**
 * Sub-abas da Agenda (pedido do dono): "Dia a dia" (só lista e calendário, para
 * a rotina) e "Painel" (todos os cards, concluídos no período e a programação
 * projetada). Ficam na linha do título, no topo da página. Setas do teclado
 * trocam de aba; alvo de toque >= 44 px.
 */
export function SubAbasAgenda({
  ativa, onChange, atrasadas, alertasPainel,
}: {
  ativa: VisaoAgenda;
  onChange: (v: VisaoAgenda) => void;
  /** Pendências atrasadas (selo na aba "Dia a dia"). */
  atrasadas?: number;
  /** Alertas que pedem olhar o Painel (estoque abaixo do mínimo etc.). */
  alertasPainel?: number;
}) {
  const abas: { id: VisaoAgenda; label: string; icon: any; selo?: number; seloTitulo?: string }[] = [
    { id: "dia", label: "Dia a dia", icon: ListChecks, selo: atrasadas, seloTitulo: "atrasadas" },
    { id: "painel", label: "Painel", icon: LayoutGrid, selo: alertasPainel, seloTitulo: "alertas" },
  ];
  function aoTeclar(e: React.KeyboardEvent, i: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const prox = abas[(i + (e.key === "ArrowRight" ? 1 : abas.length - 1)) % abas.length];
    onChange(prox.id);
    // devolve o foco à aba nova depois da troca
    requestAnimationFrame(() => document.getElementById(`ag2-tab-${prox.id}`)?.focus());
  }
  return (
    <div className="ag2-tabs" role="tablist" aria-label="Visões da Agenda">
      {abas.map((a, i) => {
        const Icon = a.icon;
        const ativo = a.id === ativa;
        return (
          <button
            key={a.id} id={`ag2-tab-${a.id}`} role="tab" type="button" aria-selected={ativo} aria-controls={`ag2-painel-${a.id}`}
            tabIndex={ativo ? 0 : -1} className="ag2-tab" onClick={() => onChange(a.id)} onKeyDown={(e) => aoTeclar(e, i)}
          >
            <Icon size={16} aria-hidden="true" />
            <span>{a.label}</span>
            {!!a.selo && a.selo > 0 && (
              <span className={"ag2-selo" + (a.id === "dia" ? " ag2-selo-alerta" : "")} title={`${a.selo} ${a.seloTitulo}`} aria-label={`${a.selo} ${a.seloTitulo}`}>
                {a.id === "dia" && <AlertTriangle size={12} aria-hidden="true" />}
                {a.selo}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
