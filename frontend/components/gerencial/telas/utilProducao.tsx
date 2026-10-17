"use client";
// Peças e funções de apoio das propostas de Lançamentos › Produção (Controle leiteiro, Pesagem corporal, Secagem).
// Só apresentação: nada aqui fala com a API. Datas fixas (hoje = 17/10/2026) para a imagem sair sempre igual.
import React from "react";

export const HOJE_ISO = "2026-10-17";

/** "2026-10-17" → "17/10/2026" (ou "17/10" quando curta). */
export function dataBR(iso: string, curta = false): string {
  const [a, m, d] = iso.split("-");
  return curta ? `${d}/${m}` : `${d}/${m}/${a}`;
}
export function diasEntre(deIso: string, ateIso: string): number {
  const t = (s: string) => Date.UTC(Number(s.slice(0, 4)), Number(s.slice(5, 7)) - 1, Number(s.slice(8, 10)));
  return Math.round((t(ateIso) - t(deIso)) / 86400000);
}
export function somarDias(iso: string, dias: number): string {
  const d = new Date(Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)) + dias));
  return d.toISOString().slice(0, 10);
}
/** Número no padrão brasileiro (vírgula decimal). */
export function nb(v: number, casas = 1): string {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}
/** Campo em branco = null (nunca 0). */
export function numOuNull(v: string | undefined): number | null {
  if (v == null || v.trim() === "") return null;
  const n = Number(v.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

/** Gerador determinístico (a imagem não pode mudar de uma renderização para outra). */
export function semente(seed: number): () => number {
  let s = seed >>> 0;
  return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
}

/**
 * Enter avança para o próximo campo da grade (Shift+Enter volta). A ordem é a do DOM: da esquerda para a direita e de cima
 * para baixo — ou seja, da 1ª para a 2ª ordenha da mesma vaca e depois para a próxima vaca. Ligar no <tbody> (onKeyDown);
 * os inputs participam com `data-nav`. Tab continua funcionando como sempre.
 */
export function aoApertarEnter(e: React.KeyboardEvent<HTMLElement>) {
  if (e.key !== "Enter") return;
  const alvo = e.target as HTMLElement;
  if (!(alvo instanceof HTMLInputElement) || alvo.dataset.nav === undefined) return;
  e.preventDefault();
  const todos = Array.from(e.currentTarget.querySelectorAll<HTMLInputElement>("input[data-nav]"));
  const prox = todos[todos.indexOf(alvo) + (e.shiftKey ? -1 : 1)];
  if (prox) { prox.focus(); prox.select(); }
}

/** Tecla de atalho em texto (dica visível de teclado). */
export function Tecla({ children }: { children: React.ReactNode }) {
  return (
    <kbd style={{
      display: "inline-block", padding: "0 0.4rem", border: "1px solid var(--border-strong, var(--border))", borderBottomWidth: 2,
      borderRadius: "var(--r-sm)", background: "var(--surface-2)", color: "var(--text)", fontFamily: "inherit", fontSize: "0.7rem",
      fontWeight: 700, lineHeight: 1.5,
    }}>{children}</kbd>
  );
}

/** Rótulo pequeno de um grupo de pílulas (mesmo estilo do rótulo de `Campo`). */
export function RotuloMini({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <span id={id} style={{ fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
      {children}
    </span>
  );
}

/** Linha de grupo (lote) da tabela. */
export function LinhaGrupo({ colSpan, titulo, n }: { colSpan: number; titulo: string; n: number }) {
  return (
    <tr className="gv-grupo"><th scope="rowgroup" colSpan={colSpan}>{titulo} · {n}</th></tr>
  );
}

/** Caixa tracejada de arquivo (estado vazio/escolhido) — borda tracejada, ícone + texto. */
export function CaixaArquivo({ nome, detalhe, aceita }: { nome?: string; detalhe?: string; aceita: string }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.8rem 1rem", border: "1.5px dashed var(--border-strong, var(--border))",
      borderRadius: "var(--r-sm)", background: "var(--surface-2)", minHeight: "3.2rem",
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.1rem", minWidth: 0 }}>
        <b style={{ fontSize: "0.85rem" }}>{nome ?? "Arraste a planilha para cá ou escolha o arquivo"}</b>
        <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{detalhe ?? `Aceita ${aceita}`}</span>
      </div>
    </div>
  );
}
