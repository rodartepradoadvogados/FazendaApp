"use client";

import React, { useState } from "react";
import { CalendarClock, X } from "lucide-react";
import { today } from "@/lib/api";

const MOTIVOS = ["Sem produto ou estoque", "Veterinário não pode", "Chuva ou manejo", "Outro motivo"] as const;

const somar = (iso: string, n: number) => {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const fmt = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });

/**
 * Adiar em poucos toques: a data já vem escolhida (amanhã) e um toque no motivo
 * confirma. "Outro motivo" abre um campo de texto. Nada de data digitada à mão
 * no caso comum; "Escolher data" existe para o resto.
 */
export function AdiarComChips({
  dataAtual, ocupado, onConfirmar, onCancelar,
}: {
  dataAtual: string; ocupado?: boolean;
  onConfirmar: (novaData: string, motivo: string) => void; onCancelar: () => void;
}) {
  const hoje = today();
  const base = dataAtual > hoje ? dataAtual : hoje;
  const opcoes = [
    { rotulo: "Amanhã", data: somar(base, 1) },
    { rotulo: "Em 2 dias", data: somar(base, 2) },
    { rotulo: "Em 1 semana", data: somar(base, 7) },
  ];
  const [data, setData] = useState(opcoes[0].data);
  const [outra, setOutra] = useState(false);
  const [outro, setOutro] = useState(false);
  const [texto, setTexto] = useState("");
    return (
    <div className="ag2-adiar" role="group" aria-label="Adiar o agendamento">
      <div className="ag2-adiar-cab">
        <strong><CalendarClock size={15} aria-hidden="true" /> Adiar para {fmt(data)}</strong>
        <button type="button" className="btn-ghost ag2-icone-btn" onClick={onCancelar} aria-label="Fechar o adiamento"><X size={16} /></button>
      </div>
      <p className="ag2-mudo">Para quando?</p>
      <div className="ag2-chips" role="radiogroup" aria-label="Nova data">
        {opcoes.map((o) => (
          <button key={o.data} type="button" role="radio" aria-checked={!outra && data === o.data} className="ag2-chip"
            onClick={() => { setOutra(false); setData(o.data); }}>{o.rotulo}</button>
        ))}
        <button type="button" role="radio" aria-checked={outra} className="ag2-chip" onClick={() => setOutra(true)}>Escolher data</button>
      </div>
      {outra && (
        <input type="date" className="ag2-input" min={hoje} value={data} aria-label="Nova data" onChange={(e) => e.target.value && setData(e.target.value)} />
      )}
      <p className="ag2-mudo">Por quê? (toque para confirmar)</p>
      <div className="ag2-chips">
        {MOTIVOS.map((m) => (
          <button key={m} type="button" className="ag2-chip ag2-chip-acao" disabled={ocupado}
            onClick={() => (m === "Outro motivo" ? setOutro(true) : onConfirmar(data, m))}>{m}</button>
        ))}
      </div>
      {outro && (
        <div className="ag2-adiar-outro">
          <input className="ag2-input" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Qual o motivo?" aria-label="Motivo do adiamento" />
          <button type="button" className="btn-primary" disabled={ocupado || !texto.trim()} onClick={() => onConfirmar(data, texto.trim())}>Adiar</button>
        </div>
      )}
    </div>
  );
}
