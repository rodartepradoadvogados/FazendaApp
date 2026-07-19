"use client";
// Primitivos de interface do APP MÓVEL (/app) — botões grandes, cartões e
// rótulos pensados para uso no campo (sol forte, pressa, dedo grosso).
// As classes .mob-* vivem em globals.css; aqui ficam os componentes React.
import { Check, ChevronRight, ChevronLeft, Heart, ShieldPlus, Milk, Wheat, Landmark, CheckCheck } from "lucide-react";
import Link from "next/link";
import type { ReactNode, CSSProperties } from "react";

/** Cores dos rótulos de categoria — as MESMAS cores já usadas em Lançar
 * (LancarTela) e no Menu, para que a mesma categoria nunca mude de cor ao
 * trocar de tela dentro do app. */
export const CATEGORIA_COR: Record<string, string> = {
  reprodutivo: "var(--mob-roxo)",
  producao: "var(--mob-azul)",
  sanidade: "var(--mob-verde)",
  manejo: "var(--mob-azul)",
  alimentacao: "var(--mob-laranja)",
  financeiro: "var(--mob-vinho)",
  atividades: "var(--mob-muted)",
};
export function corCategoria(cat?: string | null): string {
  return CATEGORIA_COR[(cat || "").toLowerCase()] || "var(--mob-muted)";
}

/** Ícones de categoria — mesma escolha usada no Menu (Heart/ShieldPlus/Wheat)
 * e em Lançar (Milk/Landmark), para reforçar a mesma identidade visual. */
const CATEGORIA_ICONE: Record<string, any> = {
  reprodutivo: Heart,
  producao: Milk,
  sanidade: ShieldPlus,
  manejo: Milk,
  alimentacao: Wheat,
  financeiro: Landmark,
  atividades: CheckCheck,
};
export function iconeCategoria(cat?: string | null) {
  return CATEGORIA_ICONE[(cat || "").toLowerCase()] || CheckCheck;
}

/** Rótulo de categoria com círculo de ícone colorido — usado na Agenda no
 * lugar do texto solto colorido, para reaproveitar o mesmo padrão visual do
 * chip de categoria já usado no site (Indicador) e em Lançar/Menu (MobBloco). */
export function RotuloCategoria({ chave, rotulo }: { chave: string; rotulo: string }) {
  const cor = corCategoria(chave);
  const Icon = iconeCategoria(chave);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.3rem" }}>
      <span style={{ width: 18, height: 18, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: `color-mix(in srgb, ${cor} 16%, transparent)`, color: cor, flexShrink: 0 }}>
        <Icon size={11} />
      </span>
      <span style={{ fontSize: "0.68rem", fontWeight: 800, letterSpacing: "0.06em", color: cor }}>{rotulo}</span>
    </div>
  );
}

/** `alt` alterna a cor do cartão em sequência (0 = 1º/3º/5º..., 1 = 2º/4º/6º...):
 * no claro, branco vs. um tom leve da paleta ativa; no escuro, preto contornado
 * de vinho vs. preto contornado de verde (fixos, sem seguir a paleta). Usado na
 * Agenda e na Ficha do animal para diferenciar cartões em sequência. */
export function MobCard({ children, style, onClick, alt, className }: { children: ReactNode; style?: CSSProperties; onClick?: () => void; alt?: 0 | 1; className?: string }) {
  const classe = [alt == null ? "mob-card" : `mob-card ${alt === 0 ? "mob-card-a" : "mob-card-b"}`, className].filter(Boolean).join(" ");
  return <div className={classe} style={{ padding: "0.95rem 1rem", ...style }} onClick={onClick}>{children}</div>;
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

/** Bloco grande do Lançamento Rápido — `cor` tinge o contorno e o fundo leve
 * do círculo do ícone (ex.: "var(--mob-roxo)"); sem `cor`, cai no dourado da marca. */
export function MobBloco({ icone, label, cor, onClick }: { icone: ReactNode; label: string; cor?: string; onClick: () => void }) {
  return (
    <button type="button" className="mob-bloco" onClick={onClick} style={cor ? ({ "--c": cor } as CSSProperties) : undefined}>
      <span className="icone">{icone}</span>
      {label}
    </button>
  );
}

/** Linha de lista com seta (menus e resultados). `alt` alterna a cor da linha
 * em sequência — mesmo tratamento de `MobCard` (ver comentário lá): tingido
 * translúcido da paleta ativa no claro, contorno vinho/verde fixo alternado
 * no escuro. Usado em Rebanho > Animais para diferenciar linhas em sequência. */
export function MobLinha({ icone, titulo, subtitulo, href, onClick, alt, categoria }: { icone?: ReactNode; titulo: ReactNode; subtitulo?: ReactNode; href?: string; onClick?: () => void; alt?: 0 | 1; categoria?: string }) {
  const classe = ["mob-linha", alt === 0 ? "mob-card-a" : alt === 1 ? "mob-card-b" : ""].filter(Boolean).join(" ");
  const corIcone = categoria ? corCategoria(categoria) : "var(--mob-dourado-2)";
  const fundoIcone = categoria ? `color-mix(in srgb, ${corIcone} 14%, transparent)` : "rgba(184,134,11,0.12)";
  const conteudo = (
    <>
      {icone && <span style={{ width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: fundoIcone, color: corIcone, flexShrink: 0 }}>{icone}</span>}
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontWeight: 700, fontSize: "0.95rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{titulo}</span>
        {subtitulo && <span style={{ display: "block", fontSize: "0.78rem", color: "var(--mob-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{subtitulo}</span>}
      </span>
      <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
    </>
  );
  if (href) return <Link href={href} className={classe} style={{ marginBottom: "0.6rem" }}>{conteudo}</Link>;
  return <button type="button" className={classe} style={{ marginBottom: "0.6rem" }} onClick={onClick}>{conteudo}</button>;
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
