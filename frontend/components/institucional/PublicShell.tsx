import Link from "next/link";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { CowDataMark } from "@/components/brand/CowDataMark";

// Casca compartilhada das páginas públicas (sem login): a página de entrada
// (/login) e as páginas institucionais (/sobre/*). Extraída daqui para que
// as duas famílias de página fiquem visualmente idênticas — mesmo cabeçalho,
// mesmo fundo de marca, mesmo rodapé — sem duplicar o CSS em cada arquivo.

// Tokens locais fixos — a área pública é uma vitrine, não a área logada (que
// segue o tema claro/escuro/misto escolhido em Aparência). Ela assume sempre
// o visual de marca — agora a paleta "Institucional" (fundo marinho escuro,
// texto claro) — sobrescrevendo --surface/--text/etc. só dentro desta árvore.
export const marcaVars = {
  "--surface": "rgba(255,255,255,0.05)",
  "--surface-2": "rgba(255,255,255,0.045)",
  "--border": "rgba(255,255,255,0.14)",
  "--text": "#F5EEF1",
  "--text-muted": "rgba(245,238,241,0.68)",
  // --red/--green-light/--alert-fg do tema claro/escuro do site falham
  // contraste (2.2:1 / 4.4:1) contra o fundo marinho fixo desta árvore —
  // recalibrados só aqui (achado da crítica da página pública, ver
  // docs/agents/design-implementation.md §5, entrada-acessivel.html).
  "--red": "#FF8A80",
  "--green-light": "#6BC79A",
  "--alert-fg": "#FF8A80",
} as React.CSSProperties;

export function PublicHeader({ variant = "institucional" }: { variant?: "login" | "institucional" }) {
  const linkStyle: React.CSSProperties = { color: "rgba(245,238,241,0.8)", textDecoration: "none", fontSize: "0.85rem", fontWeight: 600 };
  const base = variant === "login" ? "" : "/login";
  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0.9rem 1.5rem", background: "rgba(8,20,33,0.6)", backdropFilter: "blur(10px)",
      borderBottom: "1px solid rgba(255,255,255,0.08)", flexWrap: "wrap", gap: "0.6rem",
    }}>
      <Link href="/login" style={{ display: "flex", alignItems: "center", gap: "0.55rem", textDecoration: "none" }}>
        <CowDataMark size={30} />
        <div>
          <CowDataWordmark size="1rem" cowColor="#F5EEF1" />
          <p style={{ margin: 0, fontSize: "0.65rem", color: "rgba(245,238,241,0.6)" }}>Estreito Ponte de Pedra · Jairo Nasser</p>
        </div>
      </Link>
      <nav style={{ display: "flex", alignItems: "center", gap: "1.4rem" }}>
        <a href={`${base}#recursos`} style={linkStyle} className="login-nav-link">Recursos</a>
        <a href={`${base}#simulador`} style={linkStyle} className="login-nav-link">Simulador</a>
        <Link href="/news" style={{ ...linkStyle, color: "#C9A44C" }} className="login-nav-link">Milk News</Link>
        {variant === "institucional" && (
          <Link href="/login" className="btn-primary" style={{ fontSize: "0.82rem", padding: "0.4rem 0.9rem" }}>Entrar</Link>
        )}
      </nav>
    </header>
  );
}

// Rodapé com prova concreta + links — antes era uma linha só, sem nenhum
// sinal de confiança pra um visitante que rolou a página inteira procurando
// um motivo pra confiar (achado da crítica, ver
// docs/agents/design-implementation.md §5, prova-e-acabamento.html).
export function PublicFooter() {
  const linkStyle: React.CSSProperties = { color: "rgba(245,238,241,0.65)", textDecoration: "none", fontSize: "0.8rem" };
  return (
    <footer style={{
      padding: "1.6rem 1.5rem", borderTop: "1px solid rgba(255,255,255,0.08)",
      display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "1rem",
    }}>
      <div>
        <p style={{ margin: "0 0 0.3rem", fontSize: "0.8rem", fontWeight: 700, color: "#C9A44C" }}>
          48+ testes automatizados das regras de negócio · construído com dados reais da Fazenda Estreito Ponte de Pedra
        </p>
        <p style={{ margin: 0, fontSize: "0.75rem", color: "rgba(245,238,241,0.45)" }}>
          CowData · Estreito Ponte de Pedra · Jairo Nasser
        </p>
      </div>
      {/* Só links que já existem de verdade no site — nada de "Contato"/
          "Termos" fabricados sem página real por trás. */}
      <nav style={{ display: "flex", gap: "1.2rem" }}>
        <a href="/login#recursos" style={linkStyle}>Recursos</a>
        <a href="/news" style={linkStyle}>Milk News</a>
      </nav>
    </footer>
  );
}

export function PublicPage({ variant = "institucional", children }: { variant?: "login" | "institucional"; children: React.ReactNode }) {
  return (
    <div style={{ ...marcaVars, minHeight: "100vh", background: "linear-gradient(180deg, #14385A 0%, #0E2A47 45%, #081A2C 100%)" }}>
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
