"use client";
/*
 * Peças visuais da Folha de pagamento e do Caixa dos funcionários (visual v2
 * do Financeiro). Só aparência e acessibilidade — nenhuma regra de negócio:
 *
 *  - PilulaStatusFolha: status da linha da folha como `.st-pill` com ícone +
 *    texto (o texto continua o de `rotuloStatusLinha`, só a cor sai dos
 *    tokens `--st-*`, que valem nas 3 paletas e nos 3 temas);
 *  - ThOrdem: cabeçalho ordenável com <button> real e `aria-sort` no <th>
 *    (mesma API do ThOrdenavel de components/Ordenavel.tsx);
 *  - propsLinhaExpansivel: <tr onClick> alcançável por teclado (Enter/Espaço);
 *  - useConfirmacao: troca window.confirm/alert por um Modal com a MESMA
 *    semântica (devolve uma Promise<boolean> no lugar do retorno síncrono);
 *  - BotaoArquivo: "Anexar …" que abre o seletor de arquivo e é um botão de
 *    verdade (o <label> com input escondido não recebia foco de teclado).
 */
import { useCallback, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Clock, MinusCircle } from "lucide-react";
import { Modal } from "@/components/Modal";
import { rotuloStatusLinha } from "@/lib/holerite";

/* ── status da linha da folha ─────────────────────────────────────────── */
export function PilulaStatusFolha({ status, vencido = false }: { status: string; vencido?: boolean }) {
  const st = rotuloStatusLinha(status);
  const classe = status === "pago" ? "pago" : status === "cancelado_rescisao" ? "" : vencido ? "venc" : "logo";
  const icone = status === "pago" ? <CheckCircle2 size={12} aria-hidden />
    : status === "cancelado_rescisao" ? <MinusCircle size={12} aria-hidden />
    : vencido ? <AlertTriangle size={12} aria-hidden /> : <Clock size={12} aria-hidden />;
  return (
    <span className={`st-pill ${classe}`} title={vencido && status !== "pago" ? `${st.titulo} — vencido` : st.titulo}>
      {icone}{st.texto}
    </span>
  );
}

/** Pílula genérica com ícone + texto (situação nunca só por cor). */
export function Pilula({ tom, icone, children, title }: {
  tom?: "venc" | "logo" | "aberto" | "fat" | "pago" | "parc"; icone?: ReactNode; children: ReactNode; title?: string;
}) {
  return <span className={`st-pill${tom ? ` ${tom}` : ""}`} title={title}>{icone}{children}</span>;
}

/* ── cabeçalho ordenável ───────────────────────────────────────────────── */
export function ThOrdem({ label, campo, coluna, dir, ordenar, alinhar }: {
  label: string; campo: string; coluna: string | null; dir: 1 | -1; ordenar: (c: string) => void; alinhar?: "left" | "right" | "center";
}) {
  const ativo = coluna === campo;
  return (
    <th aria-sort={ativo ? (dir === 1 ? "ascending" : "descending") : "none"} style={{ whiteSpace: "nowrap", textAlign: alinhar }}>
      <button type="button" onClick={() => ordenar(campo)}
        style={{
          background: "none", border: 0, color: "inherit", font: "inherit", letterSpacing: "inherit", textTransform: "inherit",
          cursor: "pointer", padding: 0, display: "inline-flex", alignItems: "center", gap: 3,
          justifyContent: alinhar === "right" ? "flex-end" : undefined, width: alinhar === "right" ? "100%" : undefined,
        }}>
        {label}{ativo ? (dir === 1 ? <ChevronUp size={12} aria-hidden /> : <ChevronDown size={12} aria-hidden />) : null}
      </button>
    </th>
  );
}

/* ── linha de tabela que abre/fecha um detalhe ─────────────────────────── */
export function propsLinhaExpansivel(aberta: boolean, alternar: () => void, rotulo: string) {
  return {
    tabIndex: 0,
    "aria-expanded": aberta,
    "aria-label": rotulo,
    className: "linha-selecionavel",
    onKeyDown: (e: KeyboardEvent<HTMLTableRowElement>) => {
      if (e.target !== e.currentTarget) return; // tecla num botão/campo da linha: é dele
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); alternar(); }
    },
  };
}

/** Linha (ou item de lista) que executa uma ação ao clicar: foco + Enter/Espaço. */
export function propsLinhaAcao(acao: () => void, rotulo: string) {
  return {
    tabIndex: 0,
    role: "button" as const,
    "aria-label": rotulo,
    onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
      if (e.target !== e.currentTarget) return;
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); acao(); }
    },
  };
}

/* ── chip de filtro compacto (categoria/grupo) ─────────────────────────── */
export function estiloChip(ativo: boolean): CSSProperties {
  return {
    display: "inline-flex", alignItems: "center", minHeight: 30, padding: "0.15rem 0.7rem",
    borderRadius: 999, fontSize: "0.78rem", fontWeight: ativo ? 700 : 600, cursor: "pointer", lineHeight: 1.3,
    border: `1px solid ${ativo ? "var(--text-accent)" : "var(--border)"}`,
    background: ativo ? "var(--text-accent)" : "var(--surface)",
    color: ativo ? "var(--surface)" : "var(--text)",
  };
}

/** Botão de "modo"/situação (ghost) — ativo marcado por borda/peso + texto de destaque legível. */
export function estiloAlternador(ativo: boolean): CSSProperties | undefined {
  return ativo ? {
    borderColor: "var(--text-accent)", color: "var(--text-accent)", fontWeight: 700,
    background: "color-mix(in srgb, var(--text-accent) 8%, transparent)",
  } : undefined;
}

/* ── confirmação/aviso em Modal (no lugar de window.confirm/alert) ─────── */
type Pedido = { mensagem: string; titulo: string; confirmar: string; cancelar: string | null; perigo: boolean };
export type OpcoesConfirmacao = { titulo?: string; confirmar?: string; cancelar?: string; perigo?: boolean };

export function useConfirmacao(zIndex = 96) {
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const resolver = useRef<((v: boolean) => void) | null>(null);

  const abrir = useCallback((p: Pedido) => new Promise<boolean>((res) => {
    resolver.current?.(false);
    resolver.current = res;
    setPedido(p);
  }), []);
  const responder = useCallback((v: boolean) => {
    const r = resolver.current;
    resolver.current = null;
    setPedido(null);
    r?.(v);
  }, []);

  const confirmar = useCallback((mensagem: string, o: OpcoesConfirmacao = {}) => abrir({
    mensagem, titulo: o.titulo ?? "Confirmar", confirmar: o.confirmar ?? "Confirmar", cancelar: o.cancelar ?? "Cancelar", perigo: !!o.perigo,
  }), [abrir]);
  const avisar = useCallback(async (mensagem: string, titulo = "Aviso") => {
    await abrir({ mensagem, titulo, confirmar: "OK", cancelar: null, perigo: false });
  }, [abrir]);

  const dialogo = pedido ? (
    <Modal title={pedido.titulo} onClose={() => responder(false)} width="480px" zIndex={zIndex}>
      <p style={{ fontSize: "0.86rem", whiteSpace: "pre-line", lineHeight: 1.5, margin: 0 }}>{pedido.mensagem}</p>
      <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "1rem", flexWrap: "wrap" }}>
        {pedido.cancelar && <button type="button" className="btn-ghost" style={{ minHeight: 40 }} onClick={() => responder(false)}>{pedido.cancelar}</button>}
        <button type="button" className="btn-primary" onClick={() => responder(true)}
          style={{ minHeight: 40, ...(pedido.perigo ? { background: "var(--st-venc-fg)", borderColor: "var(--st-venc-fg)", color: "var(--surface)" } : null) }}>
          {pedido.confirmar}
        </button>
      </div>
    </Modal>
  ) : null;

  return { confirmar, avisar, dialogo };
}

/* ── "Anexar arquivo" como botão de verdade ────────────────────────────── */
export function BotaoArquivo({ accept, onArquivo, rotulo, className = "btn-ghost", style, title, children }: {
  accept: string; onArquivo: (f: File) => void; rotulo: string; className?: string; style?: CSSProperties; title?: string; children: ReactNode;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className={className} style={style} title={title} aria-label={rotulo} onClick={() => ref.current?.click()}>{children}</button>
      <input ref={ref} type="file" accept={accept} tabIndex={-1} aria-hidden style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onArquivo(f); e.target.value = ""; }} />
    </>
  );
}

/* ── ajustes de toque no celular, escopados em .fin-v2 ─────────────────
   Alvos ≥44px e campos com fonte ≥16px (sem zoom automático no iOS) só
   abaixo de 768px; no desktop a densidade de relatório continua igual. */
const CSS_FIN_V2 = `
@media (max-width: 767px) {
  .fin-v2 button:not(.st-pill), .fin-v2 select, .fin-v2 a.btn-ghost,
  .fin-v2 input:not([type="checkbox"]):not([type="radio"]):not([type="file"]) { min-height: 44px !important; }
  .fin-v2 label:has(> input[type="checkbox"]), .fin-v2 label:has(> input[type="radio"]) { min-height: 44px !important; }
  .fin-v2 select, .fin-v2 input:not([type="checkbox"]):not([type="radio"]), .fin-v2 textarea { font-size: 16px !important; }
  .fin-v2 input[type="checkbox"], .fin-v2 input[type="radio"] { width: 20px; height: 20px; }
}
.fin-v2 .fazenda-table tbody tr.linha-selecionavel { cursor: pointer; }
`;
export function EstilosFinV2() {
  return <style>{CSS_FIN_V2}</style>;
}
