"use client";

import React from "react";
import { CalendarClock } from "lucide-react";

type Ev = { id: string; data: string; descricao: string; categoria?: string; numero_animal?: string | null; animais?: string[]; lote?: string | null };

function rotuloDia(iso: string, hoje: string) {
  const d = new Date(iso + "T00:00:00");
  const amanha = new Date(hoje + "T00:00:00");
  amanha.setDate(amanha.getDate() + 1);
  const txt = d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
  return d.toDateString() === amanha.toDateString() ? `Amanhã · ${txt}` : txt;
}

/**
 * "O que vem": os próximos dias com tarefa, na 1ª dobra ao lado da lista (no
 * celular, logo abaixo). Só tarefas (animal em lista de espera nunca aparece
 * aqui). Títulos completos, sem cortar.
 */
export function OQueVem({
  eventos, hoje, dias = 3, porDia = 3, onVerSemana, carregando,
}: { eventos: Ev[]; hoje: string; dias?: number; porDia?: number; onVerSemana?: () => void; carregando?: boolean }) {
  const futuros = eventos.filter((e) => e.data > hoje);
  const datas = Array.from(new Set(futuros.map((e) => e.data))).sort().slice(0, dias);
  return (
    <aside className="card ag2-oquevem" aria-label="O que vem nos próximos dias">
      <div className="ag2-oquevem-cab">
        <h2><CalendarClock size={16} aria-hidden="true" /> O que vem</h2>
        {onVerSemana && <button type="button" className="ag2-link" onClick={onVerSemana}>Ver semana</button>}
      </div>
      {datas.length === 0 ? (
        <p className="ag2-mudo" role={carregando ? "status" : undefined}>{carregando ? "Buscando o que vem…" : "Nada agendado para os próximos dias."}</p>
      ) : datas.map((d) => {
        const doDia = futuros.filter((e) => e.data === d);
        return (
          <div key={d} className="ag2-oquevem-dia">
            <p className="ag2-oquevem-data">{rotuloDia(d, hoje)}</p>
            <ul>
              {doDia.slice(0, porDia).map((e) => (
                <li key={e.id}>
                  <span>{e.descricao}</span>
                  {(e.animais?.length ?? 0) > 1 ? <span className="ag2-mudo"> · {e.animais!.length} animais</span> : null}
                  {e.lote ? <span className="ag2-mudo"> · {e.lote}</span> : null}
                </li>
              ))}
            </ul>
            {doDia.length > porDia && <p className="ag2-mudo">+ {doDia.length - porDia} no mesmo dia</p>}
          </div>
        );
      })}
    </aside>
  );
}
