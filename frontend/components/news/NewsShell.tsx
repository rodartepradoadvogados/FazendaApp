import Link from "next/link";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";

// Casca visual PRÓPRIA e FIXA do Milk News: sempre branca, com o mesmo
// logo do site e do app — independente de estar logado ou não, e
// independente do tema (claro/escuro/misto) escolhido no resto do sistema.
// Antes o blog mudava de cara conforme a sessão (ver auditoria de marca);
// aqui os tokens de cor da árvore são sobrescritos localmente, do mesmo
// jeito que a área pública (institucional/PublicShell) fixa o visual marinho
// — mas o blog é a exceção clara: fundo branco, detalhes em azul (nunca o
// marinho escuro do resto da área pública).
const NEWS_VARS = {
  "--bg": "#FFFFFF",
  "--surface": "#FFFFFF",
  "--surface-2": "#EEF3F8",
  "--border": "rgba(14,42,71,0.12)",
  "--text": "#1B2A3A",
  "--text-muted": "rgba(27,42,58,0.62)",
  // --dourado-light é o token que os cards de matéria usam para manchete e
  // links — aqui vira azul (não ouro): #2563EB sobre fundo branco já dá
  // ~5.2:1 de contraste, acima do mínimo AA (4.5:1) para texto normal, sem
  // precisar de mistura.
  "--dourado-light": "#2563EB",
  "--vinho": "#0E2A47",
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
    <div style={{ ...NEWS_VARS, minHeight: "100vh", background: "var(--bg)", position: "relative" }}>
      {/* Marca d'água fixa do Milk News: a mesma "Curva" da marca, bem apagada
          em azul-marinho sobre o fundo branco, acompanhando a rolagem — igual
          em espírito ao que a tela de login faz em branco sobre a foto. */}
      <div aria-hidden="true" style={{ position: "fixed", inset: 0, overflow: "hidden", pointerEvents: "none", zIndex: 0 }}>
        <div
          style={{
            position: "absolute", top: "-6vh", left: "50%", transform: "translateX(-50%)",
            width: "clamp(480px, 78vw, 960px)", opacity: 0.05,
          }}
        >
          <CowDataMark size="100%" variant="mono" color="#0E2A47" />
        </div>
      </div>
      <div style={{ position: "relative", zIndex: 1 }}>
        <header
          style={{
            position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "0.9rem 1.5rem", background: "rgba(255,255,255,0.92)", backdropFilter: "blur(10px)",
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
            color: "var(--text)", textDecoration: "none", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)",
            border: "1px solid var(--border)",
          }}>
            {voltarLabel}
          </Link>
        </header>
        {children}
      </div>
      <style>{`.news-voltar:hover { color: var(--dourado-light) !important; border-color: var(--dourado-light) !important; }`}</style>
    </div>
  );
}
