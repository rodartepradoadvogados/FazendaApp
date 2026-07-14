"use client";
// Primitivos de interface do APP MÓVEL (/app) — botões grandes, cartões e
// rótulos pensados para uso no campo (sol forte, pressa, dedo grosso).
// As classes .mob-* vivem em globals.css; aqui ficam os componentes React.
import { Check, ChevronRight, ChevronLeft } from "lucide-react";
import Link from "next/link";
import type { ReactNode, CSSProperties } from "react";

/** Cores dos rótulos de categoria nos cartões da Agenda (padrão do PDF). */
export const CATEGORIA_COR: Record<string, string> = {
  reprodutivo: "var(--mob-acao)",
  producao: "var(--mob-verde)",
  sanidade: "var(--mob-azul)",
  manejo: "var(--mob-azul)",
  alimentacao: "var(--mob-ambar)",
  financeiro: "var(--mob-vermelho)",
  atividades: "var(--mob-muted)",
};
export function corCategoria(cat?: string | null): string {
  return CATEGORIA_COR[(cat || "").toLowerCase()] || "var(--mob-muted)";
}

export function MobCard({ children, style, onClick }: { children: ReactNode; style?: CSSProperties; onClick?: () => void }) {
  return <div className="mob-card" style={{ padding: "0.95rem 1rem", ...style }} onClick={onClick}>{children}</div>;
}

/** Título de tela (ex.: "Hoje, 10 de Julho") com espaço para um badge à direita. */
export function MobTitulo({ children, badge }: { children: ReactNode; badge?: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", margin: "0.25rem 0 0.9rem" }}>
      <h1 style={{ fontSize: "1.15rem", fontWeight: 800 }}>{children}</h1>
      {badge != null && (
        <span style={{ fontSize: "0.72rem", fontWeight: 700, padding: "0.25rem 0.7rem", borderRadius: "999px", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", color: "var(--mob-muted)" }}>
          {badge}
        </span>
      )}
    </div>
  );
}

/** Check circular grande — fica verde-luminoso quando concluído. */
export function MobCheck({ feito, onClick, title }: { feito: boolean; onClick?: () => void; title?: string }) {
  function aoClicar() {
    try { navigator.vibrate?.(20); } catch { /* sem suporte — segue sem vibrar */ }
    onClick?.();
  }
  return (
    <button type="button" className={`mob-check${feito ? " feito" : ""}`} onClick={aoClicar} title={title || (feito ? "Concluído — toque para desfazer" : "Toque para marcar como feito")} aria-label={title || "Concluir"}>
      <Check size={22} strokeWidth={3} />
    </button>
  );
}

/** Bloco grande do Lançamento Rápido. */
export function MobBloco({ icone, label, destaque, onClick }: { icone: ReactNode; label: string; destaque?: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`mob-bloco${destaque ? " destaque" : ""}`} onClick={onClick}>
      <span className="icone">{icone}</span>
      {label}
    </button>
  );
}

/** Linha de lista com seta (menus e resultados). */
export function MobLinha({ icone, titulo, subtitulo, href, onClick }: { icone?: ReactNode; titulo: ReactNode; subtitulo?: ReactNode; href?: string; onClick?: () => void }) {
  const conteudo = (
    <>
      {icone && <span style={{ width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(184,134,11,0.12)", color: "var(--mob-dourado-2)", flexShrink: 0 }}>{icone}</span>}
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontWeight: 700, fontSize: "0.95rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{titulo}</span>
        {subtitulo && <span style={{ display: "block", fontSize: "0.78rem", color: "var(--mob-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{subtitulo}</span>}
      </span>
      <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
    </>
  );
  if (href) return <Link href={href} className="mob-linha" style={{ marginBottom: "0.6rem" }}>{conteudo}</Link>;
  return <button type="button" className="mob-linha" style={{ marginBottom: "0.6rem" }} onClick={onClick}>{conteudo}</button>;
}

/** Campo com rótulo (label em cima, controle grande embaixo). */
export function MobCampo({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: "0.8rem" }}>
      <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.3rem" }}>{label}</label>
      {children}
    </div>
  );
}

/** Cabeçalho de sub-tela com botão voltar. */
export function MobVoltar({ titulo, onVoltar }: { titulo: string; onVoltar: () => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", margin: "0.25rem 0 1rem" }}>
      <button type="button" onClick={onVoltar} aria-label="Voltar"
        style={{ width: 40, height: 40, borderRadius: 12, border: "1px solid var(--mob-border)", background: "var(--mob-surface)", color: "var(--mob-text)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0 }}>
        <ChevronLeft size={20} />
      </button>
      <h1 style={{ fontSize: "1.1rem", fontWeight: 800 }}>{titulo}</h1>
    </div>
  );
}

/** Aviso pós-salvar: verde (enviado) ou âmbar (guardado offline). */
export function MobAviso({ tipo, children }: { tipo: "ok" | "offline" | "erro"; children: ReactNode }) {
  const cor = tipo === "ok" ? "var(--mob-verde)" : tipo === "offline" ? "var(--mob-ambar)" : "var(--mob-vermelho)";
  return (
    <p style={{ margin: "0.7rem 0 0", padding: "0.7rem 0.8rem", borderRadius: 12, fontSize: "0.88rem", fontWeight: 600, color: cor, background: "color-mix(in srgb, currentColor 10%, transparent)", border: `1px solid ${cor}` }}>
      {children}
    </p>
  );
}
