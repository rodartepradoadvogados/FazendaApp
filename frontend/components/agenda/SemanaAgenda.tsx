"use client";

import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

type Ev = { id: string; data: string; descricao: string; categoria?: string };

const somar = (iso: string, n: number) => {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
/** Segunda-feira da semana de `iso`. */
export function inicioDaSemana(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return somar(iso, -((d.getDay() + 6) % 7));
}

/**
 * Visão Semana do Dia a dia: 7 dias (segunda a domingo) com as tarefas de cada
 * um; tocar no dia abre a lista completa dele logo abaixo. No celular vira uma
 * pilha (um dia por bloco).
 */
export function SemanaAgenda({
  eventos, hoje, inicio, selecionado, cor, onMudarSemana, onSelecionar,
}: {
  eventos: Ev[]; hoje: string; inicio: string; selecionado: string | null;
  cor: (categoria: string) => string;
  onMudarSemana: (delta: number) => void; onSelecionar: (iso: string) => void;
}) {
  const dias = Array.from({ length: 7 }, (_, i) => somar(inicio, i));
  const fim = dias[6];
  const titulo = `${new Date(inicio + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })} a ${new Date(fim + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" })}`;
  return (
    <div className="ag2-semana-bloco">
      <div className="ag2-semana-nav">
        <button type="button" className="btn-ghost ag2-icone-btn" onClick={() => onMudarSemana(-1)} aria-label="Semana anterior"><ChevronLeft size={18} /></button>
        <button type="button" className="btn-ghost" onClick={() => onMudarSemana(0)} title="Voltar para esta semana"><strong>{titulo}</strong></button>
        <button type="button" className="btn-ghost ag2-icone-btn" onClick={() => onMudarSemana(1)} aria-label="Próxima semana"><ChevronRight size={18} /></button>
      </div>
      <div className="ag2-semana">
        {dias.map((d) => {
          const evs = eventos.filter((e) => e.data === d);
          const dt = new Date(d + "T00:00:00");
          const ativo = d === selecionado;
          return (
            <button key={d} type="button" onClick={() => onSelecionar(d)} aria-pressed={ativo}
              className={"ag2-dia" + (d === hoje ? " ag2-dia-hoje" : "") + (ativo ? " ag2-dia-sel" : "")}
              aria-label={`${dt.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })}: ${evs.length} ${evs.length === 1 ? "tarefa" : "tarefas"}`}>
              <span className="ag2-dia-cab">
                <span className="ag2-dia-sem">{dt.toLocaleDateString("pt-BR", { weekday: "short" })}</span>
                <span className="ag2-dia-num">{dt.getDate()}</span>
                <span className="ag2-dia-qtd">{evs.length > 0 ? `${evs.length} ${evs.length === 1 ? "tarefa" : "tarefas"}` : "livre"}</span>
              </span>
              <span className="ag2-dia-lista">
                {evs.slice(0, 4).map((e) => (
                  <span key={e.id} className="ag2-dia-item"><span className="ag2-ponto" style={{ background: cor(e.categoria || "") }} aria-hidden="true" />{e.descricao}</span>
                ))}
                {evs.length > 4 && <span className="ag2-mudo">+ {evs.length - 4}</span>}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
