"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken, podeModulo, ehDono, ROTA_MODULO } from "@/lib/api";
import { iniciarMonitorInatividade } from "@/lib/idle";
import { Sidebar } from "@/components/Sidebar";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { NewsButton } from "@/components/NewsButton";
import { SubNavProvider } from "@/components/SubNavContext";
import AssistenteClaude from "@/components/AssistenteClaude";
import { SectionBackground } from "@/components/SectionBackground";
import { NewsShell } from "@/components/news/NewsShell";

// Rotas públicas: acessíveis sem login, sem redirecionar para /login.
// News é o blog da fazenda — leitura livre para qualquer visitante; /sobre/*
// são as páginas institucionais linkadas pelos banners da própria /login.
const ROTA_PUBLICA = (p: string) => p === "/login" || p === "/news" || p.startsWith("/sobre/");

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
  // Painel CowData (/painel-cowdata): administração da EMPRESA de software,
  // deliberadamente separada da navegação da FAZENDA (ver fazenda/models/
  // multitenant.py::EmpresaOperadora e a proposta de separação fazenda/
  // empresa) — casca própria (PainelCowDataSidebar), nunca a Sidebar da
  // fazenda, e restrita ao dono da plataforma.
  const ehPainelCowData = path.startsWith("/painel-cowdata");

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
    if (ehPainelCowData && !ehDono()) { router.replace("/"); return; }
    // "/historico" reúne Reprodução + Produção — basta ter qualquer uma das
    // duas (a página em si esconde a sub-aba sem permissão).
    if (path === "/historico" && !(podeModulo("reproducao") || podeModulo("producao"))) { router.replace("/"); return; }
    // Configurações tem a aba "Aparência" (tema/paleta) liberada para todo mundo,
    // mesmo sem nenhum outro módulo — o filtro por sub-aba já acontece dentro da página.
    if (mod && mod !== "capa" && !podeModulo(mod)) { router.replace("/"); return; }
    setEstado("logado");
  }, [path, router, ehApp, ehPainelCowData]);

  // Desloga sozinho após 15 min sem interação (mouse/teclado/toque/rolagem) —
  // segurança dos dados da fazenda e controle de acessos do proprietário.
  // Ativo em qualquer tela logada, tanto no site quanto no app móvel (/app).
  useEffect(() => {
    if (estado !== "logado") return;
    return iniciarMonitorInatividade();
  }, [estado]);

  // /sobre/* já vem com a própria casca pública (PublicPage) — igual /login,
  // não precisa da sidebar do sistema, esteja a pessoa logada ou não.
  if (path === "/login" || path.startsWith("/sobre/")) return <>{children}</>;

  // Milk News tem casca visual PRÓPRIA e FIXA (creme, mesmo logo do site/app)
  // — igual para qualquer visitante, logado ou não, independente do tema
  // escolhido no resto do sistema (ver NewsShell). Fica antes do gate de
  // "estado" porque não depende de login (ver ROTA_PUBLICA acima).
  if (path === "/news") {
    return (
      <NewsShell
        voltarHref={estado === "logado" ? "/" : "/login"}
        voltarLabel={estado === "logado" ? "Voltar ao painel" : "Entrar no sistema"}
      >
        {children}
      </NewsShell>
    );
  }

  if (estado !== "logado") {
    return <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>Carregando…</div>;
  }

  // App móvel: o layout de /app cuida de cabeçalho e navegação inferior.
  if (ehApp) return <>{children}</>;

  // Painel CowData: casca própria (PainelCowDataLayout), nunca a Sidebar da
  // fazenda — ver comentário no topo deste componente.
  if (ehPainelCowData) return <>{children}</>;

  return (
    <SubNavProvider>
      <div className="md:flex md:h-screen bg-fazenda-bg md:overflow-hidden">
        <Sidebar />
        <div style={{ position: "fixed", top: "1rem", right: "4.75rem", zIndex: 60 }}>
          <ThemeSwitcher />
        </div>
        <NewsButton />
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
