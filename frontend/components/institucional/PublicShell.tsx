import Link from "next/link";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { CwdMilkMark } from "@/components/CwdMilkMark";

// Casca compartilhada das páginas públicas (sem login): a página de entrada
// (/login) e as páginas institucionais (/sobre/*). Extraída daqui para que
// as duas famílias de página fiquem visualmente idênticas — mesmo cabeçalho,
// mesmo fundo de marca, mesmo rodapé — sem duplicar o CSS em cada arquivo.

// Tokens locais fixos — a área pública é uma vitrine, não a área logada (que
// segue o tema claro/escuro/misto escolhido em Aparência). Ela assume sempre
// o visual de marca (fundo vinho escuro, texto claro), sobrescrevendo
// --surface/--text/etc. só dentro desta árvore.
export const marcaVars = {
  "--surface": "rgba(255,255,255,0.05)",
  "--surface-2": "rgba(255,255,255,0.045)",
  "--border": "rgba(255,255,255,0.14)",
  "--text": "#F5EEF1",
  "--text-muted": "rgba(245,238,241,0.68)",
} as React.CSSProperties;

export function PublicHeader({ variant = "institucional" }: { variant?: "login" | "institucional" }) {
  const linkStyle: React.CSSProperties = { color: "rgba(245,238,241,0.8)", textDecoration: "none", fontSize: "0.85rem", fontWeight: 600 };
  const base = variant === "login" ? "" : "/login";
  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0.9rem 1.5rem", background: "rgba(20,10,14,0.55)", backdropFilter: "blur(10px)",
      borderBottom: "1px solid rgba(255,255,255,0.08)", flexWrap: "wrap", gap: "0.6rem",
    }}>
      <Link href="/login" style={{ display: "flex", alignItems: "center", gap: "0.55rem", textDecoration: "none" }}>
        <CwdMilkMark size={30} color="#F5EEF1" />
        <div>
          <CowDataWordmark size="1rem" cowColor="#F5EEF1" />
          <p style={{ margin: 0, fontSize: "0.65rem", color: "rgba(245,238,241,0.6)" }}>Estreito Ponte de Pedra · Jairo Nasser</p>
        </div>
      </Link>
      <nav style={{ display: "flex", alignItems: "center", gap: "1.4rem" }}>
        <a href={`${base}#recursos`} style={linkStyle} className="login-nav-link">Recursos</a>
        <a href={`${base}#simulador`} style={linkStyle} className="login-nav-link">Simulador</a>
        <Link href="/news" style={{ ...linkStyle, color: "#FFE066" }} className="login-nav-link">Milk News</Link>
        {variant === "institucional" && (
          <Link href="/login" className="btn-primary" style={{ fontSize: "0.82rem", padding: "0.4rem 0.9rem" }}>Entrar</Link>
        )}
      </nav>
    </header>
  );
}

export function PublicFooter() {
  return (
    <footer style={{ padding: "1.5rem", textAlign: "center", color: "rgba(245,238,241,0.45)", fontSize: "0.75rem", borderTop: "1px solid rgba(255,255,255,0.08)" }}>
      CowData · Estreito Ponte de Pedra · Jairo Nasser
    </footer>
  );
}

export function PublicPage({ variant = "institucional", children }: { variant?: "login" | "institucional"; children: React.ReactNode }) {
  return (
    <div style={{ ...marcaVars, minHeight: "100vh", background: "linear-gradient(180deg, #2a1219 0%, #1c0d12 45%, #150a0e 100%)" }}>
      <PublicHeader variant={variant} />
      {children}
      <PublicFooter />
      <style>{`
        .login-nav-link { transition: color 0.15s ease; }
        .login-nav-link:hover { color: #ffffff !important; }
        @media (max-width: 860px) {
          /* minmax(0, 1fr), não só 1fr — um "1fr" puro tem mínimo "auto" (o
             min-content do conteúdo), então a coluna estoura a largura da
             tela em vez de encolher para caber no mobile. */
          .login-hero-grid { grid-template-columns: minmax(0, 1fr) !important; }
          .login-card-offset { transform: none !important; }
        }
      `}</style>
    </div>
  );
}
