"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken, podeModulo, ehDono, ehContador, ROTA_MODULO } from "@/lib/api";
import { iniciarMonitorInatividade } from "@/lib/idle";
import { Sidebar } from "@/components/Sidebar";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { NewsButton } from "@/components/NewsButton";
import { ManualFazendaButton } from "@/components/ManualFazendaModal";
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
  // Espelho nativo da sessão (ver lib/nativo.ts) restaurado antes de checar
  // login — só um "trinco" pra não checar duas vezes (localStorage já
  // populado na 1ª passada não precisa de nova tentativa nas seguintes).
  const [hidratado, setHidratado] = useState(false);
  // Estamos dentro do app nativo (Capacitor) OU do PWA instalado? Detecção
  // única (ver lib/nativo.ts::ehAppOuPwa) — usada só para destinoRaiz abaixo.
  // Path-based (ehApp) não bastava: um push pode abrir uma rota fora de /app
  // (/financeiro, /estoque etc. — ver lib/nativo.ts::rotaDoApp) e, se a
  // permissão falhar logo em seguida, o bounce caía no "/" desktop mesmo
  // rodando dentro do app/PWA.
  const [dentroDoApp, setDentroDoApp] = useState(false);
  useEffect(() => {
    import("@/lib/nativo").then(({ ehAppOuPwa }) => ehAppOuPwa()).then(setDentroDoApp).catch(() => {});
  }, []);

  // O app móvel (/app) tem casca própria (barra inferior, sem sidebar).
  const ehApp = path.startsWith("/app");
  // Dentro do app nativo/PWA, qualquer navegação "para a raiz" (sessão
  // expirada, página sem permissão etc.) deve cair no /app (casca mobile),
  // nunca no site desktop completo — só o botão proposital "Site completo"
  // do Menu (app/app/menu/page.tsx) deve levar ao "/" de verdade.
  const destinoRaiz = (ehApp || dentroDoApp) ? "/app" : "/";

  // Se o localStorage está vazio dentro do app nativo, tenta restaurar a
  // sessão da cópia nativa (@capacitor/preferences) antes de decidir "checando"
  // → "deslogado" — o localStorage da WebView pode ter sido limpo pelo
  // sistema sem o app ser desinstalado (ver lib/nativo.ts::restaurarSessaoNativa).
  useEffect(() => {
    if (getToken()) { setHidratado(true); return; }
    import("@/lib/nativo").then(({ restaurarSessaoNativa }) => restaurarSessaoNativa()).catch(() => {}).finally(() => setHidratado(true));
  }, []);
  // Painel CowData (/painel-cowdata): administração da EMPRESA de software,
  // deliberadamente separada da navegação da FAZENDA (ver fazenda/models/
  // multitenant.py::EmpresaOperadora e a proposta de separação fazenda/
  // empresa) — casca própria (PainelCowDataSidebar), nunca a Sidebar da
  // fazenda, e restrita ao dono da plataforma.
  const ehPainelCowData = path.startsWith("/painel-cowdata");
  // Painel do Contador (/contador): acesso restrito ao vínculo UsuarioFazenda.
  // contador (Financeiro somente leitura/exportação, sem app móvel) — casca
  // própria (ver frontend/app/contador/layout.tsx), nunca a Sidebar da fazenda.
  const ehPainelContador = path.startsWith("/contador");

  useEffect(() => {
    if (!hidratado) return; // aguarda a tentativa de restaurar a sessão nativa (ver acima)
    if (path === "/login") { setEstado("deslogado"); return; }
    if (!getToken()) {
      setEstado("deslogado");
      if (ROTA_PUBLICA(path)) return; // /news: mostra a matéria mesmo sem sessão.
      // No app móvel, volta para o app depois do login.
      router.replace(ehApp ? `/login?next=${encodeURIComponent(path)}` : "/login");
      return;
    }
    // Um vínculo de contador só enxerga o Painel do Contador — nunca o resto
    // do sistema (nem o app móvel, que sequer tem essa tela). O proprietário
    // também pode visitar /contador (mesma tela que o contador externo vê,
    // acessível pela Sidebar > Administração), mas não fica preso lá — só
    // quem tem o vínculo de contador é redirecionado automaticamente.
    if (ehContador() && !ehPainelContador) { router.replace("/contador"); return; }
    if (ehPainelContador && !ehContador() && !ehDono()) { router.replace(destinoRaiz); return; }
    // Bloqueia páginas sem permissão (ex.: operador sem financeiro).
    const mod = ROTA_MODULO[path];
    if (path === "/usuarios" && !ehDono()) { router.replace(destinoRaiz); return; }
    if (ehPainelCowData && !ehDono()) { router.replace(destinoRaiz); return; }
    // "/historico" reúne Reprodução + Produção — basta ter qualquer uma das
    // duas (a página em si esconde a sub-aba sem permissão).
    if (path === "/historico" && !(podeModulo("reproducao") || podeModulo("producao"))) { router.replace(destinoRaiz); return; }
    // Configurações tem a aba "Aparência" (tema/paleta) liberada para todo mundo,
    // mesmo sem nenhum outro módulo — o filtro por sub-aba já acontece dentro da página.
    if (mod && mod !== "capa" && !podeModulo(mod)) { router.replace(destinoRaiz); return; }
    setEstado("logado");
  }, [path, router, ehApp, ehPainelCowData, ehPainelContador, hidratado, destinoRaiz]);

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

  // Painel do Contador: casca própria (frontend/app/contador/layout.tsx),
  // nunca a Sidebar da fazenda nem a casca do app móvel — ver comentário
  // no topo deste componente.
  if (ehPainelContador) return <>{children}</>;

  return (
    <div className="md:flex md:h-screen bg-fazenda-bg md:overflow-hidden">
      <Sidebar />
      {/* News fica sempre; Manual da Fazenda só na Capa (path === "/"); tema e
          sino de notificações também moram aqui — os quatro num único
          container fixed com gap (.site-top-actions, ver globals.css) em vez
          de cada um calcular sua própria posição (era assim que ficavam
          sobrepostos, ver comentário em globals.css). */}
      <div className="site-top-actions">
        {path === "/" && <ManualFazendaButton />}
        <NewsButton />
        <ThemeSwitcher />
        <NotificationBell />
      </div>
      <AssistenteClaude />
      <main className="flex-1 md:overflow-y-auto app-main">
        <SectionBackground />
        <div style={{ position: "relative", zIndex: 1, minHeight: "100%" }}>{children}</div>
      </main>
    </div>
  );
}
