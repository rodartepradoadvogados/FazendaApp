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
} as React.CSSProperties;

export function PublicHeader({ variant = "institucional" }: { variant?: "login" | "institucional" }) {
  const linkStyle: React.CSSProperties = { color: "rgba(245,238,241,0.8)", textDecoration: "none", fontSize: "0.85rem", fontWeight: 600 };
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
        {/* "Recursos"/"Simulador" saíram do menu — apontavam para âncoras
            (#recursos/#simulador) que existiam só na Hero antiga do login;
            redesign T7 ("Login enxuto", mockup 1h) tirou essas seções de lá
            (viram a landing pública — T8, ainda não construída). */}
        {/* Antes #C9A44C — um terceiro tom de dourado inventado, que não batia
            nem com --dourado (#B9831F) nem com --dourado-light (#E0A63C).
            Trocado pelo token --dourado (mais escuro/sóbrio que --dourado-light,
            pedido do dono do produto). */}
        <Link href="/news" style={{ ...linkStyle, color: "var(--dourado)" }} className="login-nav-link">Milk News</Link>
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
    // Fundo marinho institucional — não segue --vinho/--dourado do :root porque
    // esses tokens são o "vinho" bordô por padrão (só viram marinho quando o
    // visitante tem data-paleta="azul" salvo, e um visitante deslogado nunca
    // tem essa preferência). Por isso os hex ficam fixos aqui, mas não são
    // inventados: são os MESMOS já cadastrados em app/globals.css para
    // data-paleta="azul" (--vinho:#0B2038 / --vinho-dark:#071A2E), a variante
    // de mesa do marinho que o cabeçalho do app móvel usa (--mob-vinho/
    // --mob-vinho-fixo). Antes o degradê tinha um terceiro tom no topo
    // (#14385A) mais claro/saturado que nenhum token do sistema usa — lido
    // como "azul infantil" pelo dono do produto — removido.
    <div style={{ ...marcaVars, minHeight: "100vh", background: "linear-gradient(180deg, #0B2038 0%, #071A2E 100%)" }}>
      <PublicHeader variant={variant} />
      {children}
      <PublicFooter />
      <style>{`
        .login-nav-link { transition: color 0.15s ease; }
        .login-nav-link:hover { color: #ffffff !important; }
      `}</style>
    </div>
  );
}
