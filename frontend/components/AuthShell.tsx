"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken, podeModulo, ehAdmin, ROTA_MODULO } from "@/lib/api";
import { iniciarMonitorInatividade } from "@/lib/idle";
import { Sidebar } from "@/components/Sidebar";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { SubNavProvider } from "@/components/SubNavContext";
import AssistenteClaude from "@/components/AssistenteClaude";

/**
 * Porta de entrada: só mostra o sistema para quem estiver logado.
 * A rota /login é aberta; qualquer outra sem token redireciona para o login.
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
      // No app móvel, volta para o app depois do login.
      router.replace(ehApp ? `/login?next=${encodeURIComponent(path)}` : "/login");
      return;
    }
    // Bloqueia páginas sem permissão (ex.: operador sem financeiro).
    const mod = ROTA_MODULO[path];
    if (path === "/usuarios" && !ehAdmin()) { router.replace("/"); return; }
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
        <NotificationBell />
        <AssistenteClaude />
        <main className="flex-1 md:overflow-y-auto app-main">{children}</main>
      </div>
    </SubNavProvider>
  );
}
