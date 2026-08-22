"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getToken, podeModulo, ehDono, ehAdmin, ehContador, ehMembroEquipeCowData, podeFormularDietas, ROTA_MODULO } from "@/lib/api";
import { iniciarMonitorInatividade } from "@/lib/idle";
import { Sidebar } from "@/components/Sidebar";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { NewsButton } from "@/components/NewsButton";
import AssistenteClaude from "@/components/AssistenteClaude";
import { SectionBackground } from "@/components/SectionBackground";
import { NewsShell } from "@/components/news/NewsShell";
import { SubNavTabs } from "@/components/SubNavTabs";
import { SuporteBanner } from "@/components/SuporteBanner";

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
  // Portais "Insights" (Indicadores, Listas, Relatórios) e "Administração"
  // (Controle de Acesso, Portal, Configurações): casca compartilhada (ver
  // components/insights/InsightsLayout.tsx, aplicada via layout.tsx dessas
  // 6 rotas — o próprio InsightsLayout decide qual dos dois grupos de abas
  // mostrar, conforme a rota), nunca a Sidebar da fazenda — cada um aberto
  // pelo próprio atalho na Sidebar, numa aba nova de verdade do navegador
  // (ver Sidebar.tsx). Painel CowData e Painel do Contador são checados à
  // parte acima: têm a própria casca bespoke, não a desta.
  const ROTAS_INSIGHTS = ["/indicadores", "/relatorios", "/analise-relatorios", "/usuarios", "/portal", "/configuracoes", "/parametros", "/news-admin"];
  const ehInsightsPortal = ROTAS_INSIGHTS.some((r) => path === r || path.startsWith(r + "/"));
  // Portal "Formulação de Dietas" (/dietas): casca própria
  // (components/dietas/DietasLayout.tsx via app/dietas/layout.tsx), nunca a
  // Sidebar da fazenda — aberto pela Sidebar numa aba nova de verdade do
  // navegador. Mesmo padrão dos portais Insights/Administração, com gate de
  // acesso próprio (admin desta fazenda OU consultor desta fazenda — ver
  // podeFormularDietas em lib/api.ts).
  const ehDietasPortal = path === "/dietas" || path.startsWith("/dietas/");

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
    // e os administradores da fazenda também podem visitar /contador (mesma
    // tela que o contador externo vê, acessível pela aba "Painel do Contador"
    // em Administração), mas não ficam presos lá — só quem tem o vínculo de
    // contador é redirecionado automaticamente.
    if (ehContador() && !ehPainelContador) { router.replace("/contador"); return; }
    if (ehPainelContador && !ehContador() && !ehDono() && !ehAdmin()) { router.replace(destinoRaiz); return; }
    // Bloqueia páginas sem permissão (ex.: operador sem financeiro).
    const mod = ROTA_MODULO[path];
    if (path === "/usuarios" && !ehDono()) { router.replace(destinoRaiz); return; }
    if (ehPainelCowData && !ehDono() && !ehMembroEquipeCowData()) { router.replace(destinoRaiz); return; }
    if (ehDietasPortal && !podeFormularDietas()) { router.replace(destinoRaiz); return; }
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

  // Largura real da faixa fixa News/Tema/Sino (.site-top-actions) — varia
  // (o Manual da Fazenda só aparece na Capa) e SubNavTabs precisa saber esse
  // valor para reservar espaço à direita e nunca desenhar abas por baixo dos
  // botões (ver --top-actions-width usado em SubNavTabs.tsx). Mesma técnica
  // de "medir e reservar" do cabeçalho fixo do app móvel (ver headerRef em
  // app/app/layout.tsx) — só que aqui é a LARGURA, não a altura.
  const topActionsRef = useRef<HTMLDivElement | null>(null);
  const [larguraTopActions, setLarguraTopActions] = useState(240);
  useEffect(() => {
    const medir = () => { if (topActionsRef.current) setLarguraTopActions(topActionsRef.current.offsetWidth); };
    medir();
    window.addEventListener("resize", medir);
    return () => window.removeEventListener("resize", medir);
  }, [path]); // path: Manual da Fazenda só em "/", muda a largura da faixa

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

  // Painel CowData: casca própria (PainelCowDataLayout), nunca a Sidebar da
  // fazenda — ver comentário no topo deste componente. Sem SuporteBanner
  // aqui: modo suporte é "estar dentro de uma fazenda-cliente como se fosse
  // o admin dela" — o Painel CowData é a base da própria CowData, não faz
  // sentido a faixa aparecer nele (quem quer ver sessões ativas usa a
  // própria tela de Suporte, ver painel-cowdata/cofre/page.tsx).
  if (ehPainelCowData) return <>{children}</>;

  // Todas as demais cascas logadas (app móvel, Painel do Contador, portais
  // Insights e Dietas, e a casca padrão da fazenda montada abaixo) recebem a
  // faixa de suporte quando ativa — pedido explícito do usuário: antes ela
  // só existia dentro da casca padrão, e sumia ao entrar em Insights e
  // Administração ou Formulação de Dietas (cascas próprias, que nem
  // chegavam a este ponto do componente). SuporteBanner é `position: fixed`
  // e mede a própria altura para publicar --suporte-banner-h (ver
  // SuporteBanner.tsx) — todo elemento fixo no topo do resto do app
  // (.site-top-actions, barra mobile da Sidebar, cabeçalho do app móvel)
  // soma essa variável ao próprio "top" para nunca ficar por baixo dela;
  // o restante do conteúdo (fluxo normal) desce sozinho via padding-top no
  // <body> (ver globals.css).
  let conteudo: React.ReactNode;

  // App móvel: o layout de /app cuida de cabeçalho e navegação inferior.
  if (ehApp) {
    conteudo = children;
  // Painel do Contador: casca própria (frontend/app/contador/layout.tsx),
  // nunca a Sidebar da fazenda nem a casca do app móvel — ver comentário
  // no topo deste componente.
  } else if (ehPainelContador) {
    conteudo = children;
  // Portal Insights e Administração: casca própria (InsightsLayout via
  // layout.tsx da rota) — ver comentário no topo deste componente.
  } else if (ehInsightsPortal) {
    conteudo = children;
  // Portal Formulação de Dietas: casca própria (DietasLayout via
  // app/dietas/layout.tsx) — ver comentário no topo deste componente.
  } else if (ehDietasPortal) {
    conteudo = children;
  } else {
    conteudo = (
      <div
        className="md:flex farm-shell-h bg-fazenda-bg md:overflow-hidden"
        // --top-actions-width: exposta aqui (ancestral comum) porque
        // .site-top-actions e <main>/SubNavTabs são IRMÃOS — uma custom
        // property só herda para descendentes, nunca entre irmãos, então
        // declarar isso dentro de .site-top-actions nunca chegaria à SubNavTabs.
        style={{ ["--top-actions-width" as any]: `${larguraTopActions}px` }}
      >
        <Sidebar />
        {/* News, Manual da Fazenda, tema e sino de notificações moram num único
            container fixed com gap (.site-top-actions, ver globals.css) em vez
            de cada um calcular sua própria posição (era assim que ficavam
            sobrepostos, ver comentário em globals.css). Exceto na Capa
            (redesign T1, mockup 1b): lá os mesmos quatro saem do fixed e
            entram no fluxo normal, dentro do próprio cabeçalho da página
            (ver app/page.tsx) — por isso não renderizam aqui nesse path. */}
        {path !== "/" && (
          <div className="site-top-actions" ref={topActionsRef}>
            <NewsButton />
            <ThemeSwitcher />
            <NotificationBell />
          </div>
        )}
        <AssistenteClaude />
        <main className="flex-1 md:overflow-y-auto app-main">
          <SubNavTabs />
          <SectionBackground />
          <div style={{ position: "relative", zIndex: 1, minHeight: "100%" }}>{children}</div>
        </main>
      </div>
    );
  }

  return (
    <>
      <SuporteBanner />
      {conteudo}
    </>
  );
}
