"use client";
import Link from "next/link";
import { Newspaper } from "lucide-react";

/**
 * Botão que abre o blog de notícias de pecuária leiteira (/news). Fundo na
 * cor da paleta (vinho) e escrita amarela, bem distinto dos ícones de dados
 * (sino de notificações, tema) para não parecer mais um widget de dados
 * acumulados da fazenda. Posicionamento (fixed no topo) é do container pai —
 * ver AuthShell.tsx / .site-top-actions em globals.css — para nunca mais
 * depender de offsets calculados por botão (foi assim que ele ficou
 * sobreposto ao botão do Manual da Fazenda).
 */
export function NewsButton() {
  return (
    <Link
      href="/news"
      title="News — notícias de pecuária leiteira"
      aria-label="Abrir News — notícias de pecuária leiteira"
      style={{
        display: "inline-flex", alignItems: "center", gap: "0.35rem",
        padding: "0.4rem 0.8rem", borderRadius: "999px",
        background: "var(--vinho)", border: "1px solid var(--vinho-light)",
        color: "#FFE066", fontWeight: 700, fontSize: "0.78rem", letterSpacing: "0.01em",
        textDecoration: "none", boxShadow: "0 2px 6px rgba(0,0,0,0.25)", whiteSpace: "nowrap",
      }}
    >
      <Newspaper size={15} style={{ color: "#FFE066" }} />
      News
    </Link>
  );
}
