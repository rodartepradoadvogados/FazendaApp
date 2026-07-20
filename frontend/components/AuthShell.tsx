"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LogIn } from "lucide-react";
import { getToken, podeModulo, ehAdmin, ehDono, ROTA_MODULO } from "@/lib/api";
import { iniciarMonitorInatividade } from "@/lib/idle";
import { Sidebar } from "@/components/Sidebar";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { NewsButton } from "@/components/NewsButton";
import { SubNavProvider } from "@/components/SubNavContext";
import AssistenteClaude from "@/components/AssistenteClaude";
import { SectionBackground } from "@/components/SectionBackground";
import { CowDataWordmark } from "@/components/CowDataWordmark";

// Rotas públicas: acessíveis sem login, sem redirecionar para /login.
// News é o blog da fazenda — leitura livre para qualquer visitante.
const ROTA_PUBLICA = (p: string) => p === "/login" || p === "/news";

/**
 * Porta de entrada: só mostra o sistema para quem estiver logado.
 * A rota /login é aberta; /news também é pública (leitura sem login);
 * qualquer outra sem token redireciona para o login.
 */
export function AuthShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [estado, setEstado] = useState<"checando" | "logado" | "deslogado">("checando");

  // O app móvel (/app) tem casca própria (barra inferior, sem sidebar).
  const ehApp = path.startsWith("/app");

  useEffect(() => {
    if (path === "/login") { setEstado("deslogado"); return; }
    if (!getToken()) {
      setEstado("deslogado");
      if (ROTA_PUBLICA(path)) return; // /news: mostra a matéria mesmo sem sessão.
      // No app móvel, volta para o app depois do login.
      router.replace(ehApp ? `/login?next=${encodeURIComponent(path)}` : "/login");
      return;
    }
    // Bloqueia páginas sem permissão (ex.: operador sem financeiro).
    const mod = ROTA_MODULO[path];
    if (path === "/usuarios" && !ehDono()) { router.replace("/"); return; }
    // Configurações tem a aba "Aparência" (tema/paleta) liberada para todo mundo,
    // mesmo sem nenhum outro módulo — o filtro por sub-aba já acontece dentro da página.
    if (mod && mod !== "capa" && !podeModulo(mod)) { router.replace("/"); return; }
    setEstado("logado");
  }, [path, router, ehApp]);

  // Desloga sozinho após 15 min sem interação (mouse/teclado/toque/rolagem) —
  // segurança dos dados da fazenda e controle de acessos do proprietário.
  // Ativo em qualquer tela logada, tanto no site quanto no app móvel (/app).
  useEffect(() => {
    if (estado !== "logado") return;
    return iniciarMonitorInatividade();
  }, [estado]);

  if (path === "/login") return <>{children}</>;

  // Visitante sem login em /news: mostra a matéria com uma casca própria e
  // simples (sem a sidebar do sistema, que é só para quem está logado).
  if (path === "/news" && estado === "deslogado") {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
        <PublicNewsHeader />
        {children}
      </div>
    );
  }

  if (estado !== "logado") {
    return <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>Carregando…</div>;
  }

  // App móvel: o layout de /app cuida de cabeçalho e navegação inferior.
  if (ehApp) return <>{children}</>;

  return (
    <SubNavProvider>
      <div className="md:flex md:h-screen bg-fazenda-bg md:overflow-hidden">
        <Sidebar />
        <div style={{ position: "fixed", top: "1rem", right: "4.75rem", zIndex: 60 }}>
          <ThemeSwitcher />
        </div>
        {ehAdmin() && <NewsButton />}
        <NotificationBell />
        <AssistenteClaude />
        <main className="flex-1 md:overflow-y-auto app-main">
          <SectionBackground />
          <div style={{ position: "relative", zIndex: 1, minHeight: "100%" }}>{children}</div>
        </main>
      </div>
    </SubNavProvider>
  );
}

/** Cabeçalho enxuto para quem chega em /news sem estar logado — identifica a
 * marca e oferece o caminho de volta para o sistema, sem expor a sidebar. */
function PublicNewsHeader() {
  return (
    <header style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0.9rem 1.5rem", borderBottom: "1px solid var(--border)",
      background: "var(--surface)", flexWrap: "wrap", gap: "0.6rem",
    }}>
      <CowDataWordmark size="1.2rem" />
      <Link href="/login" className="btn-ghost" style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", textDecoration: "none" }}>
        <LogIn size={15} /> Entrar no sistema
      </Link>
    </header>
  );
}
