"use client";
// Peças do Passo 1 ("quem") compartilhadas pelas três telas de lançamento em lote — Movimentar animais, Inseminação e
// Protocolo IATF —, no mesmo desenho do Diagnóstico: origem → situação → cartão-checkbox agrupado por lote → barra fixa.
// A diferença que o dono aprovou: aqui nada vem marcado sozinho e a seleção persiste ao trocar de origem/filtro
// (ver lib/lancamentoLote.ts). Estilos em app/globals.css (.lote-*).
import type { ReactNode } from "react";
import { Check, CircleAlert, CircleCheck, CloudOff, Info, Search, TriangleAlert } from "lucide-react";
import type { OrigemLote } from "@/lib/lancamentoLote";

export const ORIGENS_PADRAO: { id: OrigemLote; rotulo: string }[] = [
  { id: "animais", rotulo: "Animais" }, { id: "lotes", rotulo: "Lotes" }, { id: "agenda", rotulo: "Agenda do vet." },
];

/** Tira de 2 segmentos + frase ("Passo 1 de 2 · quem vai ser inseminada"). */
export function PassoIndicador({ passo, children }: { passo: 1 | 2; children: ReactNode }) {
  return (
    <div className="lote-passo">
      <div className="segs" aria-hidden="true"><i className="on" /><i className={passo === 2 ? "on" : undefined} /></div>
      <p>Passo {passo} de 2 · {children}</p>
    </div>
  );
}

export function RotuloLote({ children }: { children: ReactNode }) {
  return <div className="lote-rot">{children}</div>;
}

export function NotaLote({ children }: { children: ReactNode }) {
  return <p className="lote-nota">{children}</p>;
}

export function VazioLote({ children }: { children: ReactNode }) {
  return <div className="lote-vazio">{children}</div>;
}

const ICONE_AVISO = {
  ok: CircleCheck, offline: CloudOff, atencao: TriangleAlert, erro: CircleAlert, info: Info,
} as const;

/** Aviso com ícone. "offline" (nuvem cortada) é só para rede; atenção usa triângulo; erro, círculo com exclamação. */
export function AvisoLote({ tipo, children }: { tipo: keyof typeof ICONE_AVISO; children: ReactNode }) {
  const Icone = ICONE_AVISO[tipo];
  return (
    <div className={`lote-aviso ${tipo}`} role={tipo === "erro" ? "alert" : undefined}>
      <Icone size={20} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function SeletorOrigem({ valor, onChange, opcoes = ORIGENS_PADRAO }: {
  valor: OrigemLote; onChange: (o: OrigemLote) => void; opcoes?: { id: OrigemLote; rotulo: string }[];
}) {
  return (
    <div role="group" aria-label="Origem" className="lote-seg" style={{ gridTemplateColumns: `repeat(${opcoes.length}, 1fr)` }}>
      {opcoes.map((o) => (
        <button key={o.id} type="button" className="lote-btn-ft" aria-pressed={valor === o.id} onClick={() => onChange(o.id)}>{o.rotulo}</button>
      ))}
    </div>
  );
}

export function PilulaLote({ ativa, onClick, children, n }: { ativa: boolean; onClick: () => void; children: ReactNode; n?: number }) {
  return (
    <button type="button" className="lote-pill" aria-pressed={ativa} onClick={onClick}>
      {children}{n != null && <b>{n}</b>}
    </button>
  );
}

export function PilulasLote({ children }: { children: ReactNode }) {
  return <div className="lote-pills">{children}</div>;
}

export function CampoBusca({ valor, onChange, placeholder }: { valor: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div className="lote-busca">
      <Search size={20} aria-hidden="true" />
      <input type="search" className="mob-input" value={valor} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        aria-label={placeholder} autoComplete="off" />
    </div>
  );
}

/** Cabeçalho do grupo de animais (um lote), com o botão "Marcar todos" quando houver. */
export function CabecalhoGrupo({ titulo, n, todo }: {
  titulo: string; n: number; todo?: { marcado: boolean; rotulo: string; onClick: () => void };
}) {
  return (
    <div className="lote-grupo-cab">
      <div className="lote-rot">{titulo} · {n}</div>
      {todo && <button type="button" className="lote-todo" aria-pressed={todo.marcado} onClick={todo.onClick}>{todo.rotulo}</button>}
    </div>
  );
}

/** Botão largo com caixa de marcar ("Selecionar todas as aptas · 12"). */
export function BotaoMarcarTodas({ marcado, rotulo, n, onClick }: { marcado: boolean; rotulo: string; n: number; onClick: () => void }) {
  return (
    <button type="button" className="lote-cartao" aria-pressed={marcado} onClick={onClick} style={{ minHeight: 60, marginTop: "0.7rem", fontWeight: 800 }}>
      <span className="lote-cx" aria-hidden="true">{marcado && <Check size={20} strokeWidth={3.2} />}</span>
      <span className="lote-cc" style={{ fontSize: "0.98rem" }}>{rotulo} <span style={{ color: "var(--mob-muted)", fontWeight: 600 }}>· {n}</span></span>
    </button>
  );
}

/** Cartão-checkbox de um animal: brinco grande, nome, linha de apoio (chips, DEL, lote) e uma frase extra opcional. */
export function CartaoAnimal({ brinco, nome, marcado, travado, confirmar, onClick, linha2, extra }: {
  brinco: string; nome?: string; marcado: boolean; travado?: boolean; confirmar?: boolean; onClick: () => void; linha2?: ReactNode; extra?: ReactNode;
}) {
  return (
    <button type="button" className={`lote-cartao${confirmar ? " confirmar" : ""}`} aria-pressed={marcado} aria-disabled={travado || undefined} onClick={onClick}>
      <span className="lote-cx" aria-hidden="true">{marcado && <Check size={20} strokeWidth={3.2} />}</span>
      <span className="lote-cc">
        <span className="lote-l1">
          <span className="brinco">{brinco}</span>
          {nome ? <span className="nome">{nome}</span> : null}
        </span>
        {(linha2 || extra) && <span className="lote-l2">{linha2}{extra}</span>}
      </span>
    </button>
  );
}

export function ChipSituacao({ tom, children }: { tom: "apta" | "atrasada" | "pev" | "insem" | "prot" | "neutra"; children: ReactNode }) {
  return <span className={`lote-chip ${tom}`}><i aria-hidden="true" />{children}</span>;
}
