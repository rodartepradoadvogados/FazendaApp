"use client";
// Peças da tela de resultado compartilhadas: selo + frase humana, quadro de números e linha de ação.
import type { ReactNode } from "react";

export function ResultadoCabecalho({ tipo, titulo, texto }: { tipo: "ok" | "offline" | "erro"; titulo: ReactNode; texto?: ReactNode }) {
  return (
    <div className={`lote-res ${tipo}`}>
      <svg className="selo" viewBox="0 0 84 84" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="42" cy="42" r="38" />
        {tipo === "ok" && <path d="M26 43l11 11 21-23" />}
        {tipo === "offline" && <path d="M42 22v22M42 56v1" />}
        {tipo === "erro" && <path d="M42 22v24M42 58v1" />}
      </svg>
      <h2 role="status">{titulo}</h2>
      {texto ? <p>{texto}</p> : null}
    </div>
  );
}

/** Quadro de linhas "nome — número". `previsto` = tracejado (valores que só valem quando o envio chegar ao servidor). */
export function QuadroLote({ previsto, rotulo, children }: { previsto?: boolean; rotulo: string; children: ReactNode }) {
  return <div className={`lote-quadro${previsto ? " prev" : ""}`} role="group" aria-label={rotulo}>{children}</div>;
}

export function LinhaQuadro({ nome, apoio, children }: { nome: ReactNode; apoio?: ReactNode; children: ReactNode }) {
  return (
    <div className="lin">
      <div className="nm">{nome}{apoio && <small>{apoio}</small>}</div>
      <div className="q">{children}</div>
    </div>
  );
}

export function AcoesFim({ children }: { children: ReactNode }) {
  return <div className="lote-acoes-fim">{children}</div>;
}
