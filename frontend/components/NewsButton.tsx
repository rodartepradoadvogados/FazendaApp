"use client";
import Link from "next/link";
import { Newspaper } from "lucide-react";

/**
 * Botão fixo no topo do site — abre o blog de notícias de pecuária leiteira
 * (/news). Fundo na cor da paleta (vinho) e escrita amarela, bem distinto dos
 * ícones de dados (sino de notificações, tema) para não parecer mais um
 * widget de dados acumulados da fazenda.
 */
export function NewsButton() {
  return (
    <Link
      href="/news"
      title="News — notícias de pecuária leiteira"
      aria-label="Abrir News — notícias de pecuária leiteira"
      style={{
        // O ThemeSwitcher (right: 4.75rem) tem largura variável — o rótulo mais
        // longo ("misto (barra vinho)") mede ~157px, então o News precisa de
        // folga extra à direita dele para não sobrepor (medido via Playwright).
        position: "fixed", top: "1rem", right: "16rem", zIndex: 60,
        display: "inline-flex", alignItems: "center", gap: "0.35rem",
        padding: "0.4rem 0.8rem", borderRadius: "999px",
        background: "var(--vinho)", border: "1px solid var(--vinho-light)",
        color: "#FFE066", fontWeight: 700, fontSize: "0.78rem", letterSpacing: "0.01em",
        textDecoration: "none", boxShadow: "0 2px 6px rgba(0,0,0,0.25)",
      }}
    >
      <Newspaper size={15} style={{ color: "#FFE066" }} />
      News
    </Link>
  );
}
