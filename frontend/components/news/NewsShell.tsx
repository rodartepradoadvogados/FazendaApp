import Link from "next/link";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";

// Casca visual PRÓPRIA e FIXA do Milk News: sempre creme/clara, com o mesmo
// logo do site e do app — independente de estar logado ou não, e
// independente do tema (claro/escuro/misto) escolhido no resto do sistema.
// Antes o blog mudava de cara conforme a sessão (ver auditoria de marca);
// aqui os tokens de cor da árvore são sobrescritos localmente, do mesmo
// jeito que a área pública (institucional/PublicShell) fixa o visual vinho.
const NEWS_VARS = {
  "--bg": "#F3E7D3",
  "--surface": "#F3E7D3",
  "--surface-2": "#EADCC3",
  "--border": "rgba(21,11,16,0.12)",
  "--text": "#150B10",
  "--text-muted": "rgba(21,11,16,0.62)",
  // --dourado-light é o token que os cards de matéria usam para manchete e
  // links — aqui vira uma versão mais escura do --gold-deep (mesma família,
  // misturada com --ink) porque o --gold-deep puro sobre este creme só
  // atinge 2.71:1 de contraste — abaixo do mínimo AA (4.5:1). Esta mistura
  // chega a ~5.1:1, legível para texto normal.
  "--dourado-light": "color-mix(in srgb, #B9831F 65%, #150B10)",
  "--vinho": "#3A0F1A",
} as React.CSSProperties;

export function NewsShell({
  voltarHref,
  voltarLabel,
  children,
}: {
  voltarHref: string;
  voltarLabel: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ ...NEWS_VARS, minHeight: "100vh", background: "var(--bg)" }}>
      <header
        style={{
          position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0.9rem 1.5rem", background: "rgba(243,231,211,0.92)", backdropFilter: "blur(10px)",
          borderBottom: "1px solid var(--border)", flexWrap: "wrap", gap: "0.6rem",
        }}
      >
        <Link href="/login" style={{ display: "flex", alignItems: "center", gap: "0.55rem", textDecoration: "none" }}>
          <CowDataMark size={30} variant="claro" />
          <span style={{ fontFamily: "var(--font-sora), sans-serif" }}>
            <CowDataWordmark size="1rem" cowColor="var(--text)" dataColor="var(--dourado-light)" />
          </span>
        </Link>
        <Link href={voltarHref} className="news-voltar" style={{
          display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", fontWeight: 600,
          color: "var(--text)", textDecoration: "none", padding: "0.4rem 0.8rem", borderRadius: "8px",
          border: "1px solid var(--border)",
        }}>
          {voltarLabel}
        </Link>
      </header>
      {children}
      <style>{`.news-voltar:hover { color: var(--dourado-light) !important; border-color: var(--dourado-light) !important; }`}</style>
    </div>
  );
}
