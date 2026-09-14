"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  getToken, podeModulo, ehDono, ehAdmin, ehContador, ehMembroEquipeCowData, podeFormularDietas, fetchContasDisponiveis,
  getContaAtivaId, ROTA_MODULO,
} from "@/lib/api";
import { iniciarMonitorInatividade, marcarPresenca, msDesdeUltimaPresenca, LIMITE_INATIVIDADE_MS } from "@/lib/idle";
import { Sidebar } from "@/components/Sidebar";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { NewsButton } from "@/components/NewsButton";
import AssistenteClaude from "@/components/AssistenteClaude";
import { SectionBackground } from "@/components/SectionBackground";
import { NewsShell } from "@/components/news/NewsShell";
import { SubNavTabs } from "@/components/SubNavTabs";
import { SuporteBanner } from "@/components/SuporteBanner";
import { FazendaTesteBanner } from "@/components/FazendaTesteBanner";
import { OfflineBanner } from "@/components/OfflineBanner";

// Rotas públicas: acessíveis sem login, sem redirecionar para /login.
// News é o blog da fazenda — leitura livre para qualquer visitante,
// incluindo a página de artigo (/news/[id]) — antes só a listagem exata
// (/news) era pública, deixando as manchetes sem pra onde linkar de verdade
// pra um visitante anônimo (achado P0 da crítica, ver
// docs/agents/design-implementation.md §5, a-materia-completa.html);
// /sobre/* são as páginas institucionais linkadas pelos banners da /login.
// "/" (T8): visitante sem login vê a landing pública, não é mais empurrado
// para /login — ver bypass de casca dedicado logo abaixo (path === "/" &&
// estado === "deslogado"), que faz o mesmo papel do bypass de /login/sobre
// para essa rota específica (que, ao contrário delas, também é válida
// LOGADA — por isso não pode ganhar o mesmo `return <>{children}</>}`
// incondicional daquelas duas, só o condicional a seguir).
const ROTA_PUBLICA = (p: string) => p === "/" || p === "/login" || p === "/news" || p.startsWith("/news/") || p.startsWith("/sobre/");

/**
 * Porta de entrada: só mostra o sistema para quem estiver logado.
 * A rota /login é aberta; /news também é pública (leitura sem login); "/"
 * é pública também (T8: landing para quem chega sem sessão, Capa para quem
 * já está logado — a própria app/page.tsx decide qual das duas mostrar,
 * consultando getToken()); qualquer outra rota sem token redireciona para
 * o login.
 */
export function AuthShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [estado, setEstado] = useState<"checando" | "logado" | "deslogado">("checando");
  // Espelho nativo da sessão (ver lib/nativo.ts) restaurado antes de checar
  // login — só um "trinco" pra não checar duas vezes (localStorage já
  // populado na 1ª passada não precisa de nova tentativa nas seguintes).
  const [hidratado, setHidratado] = useState(false);
  // Estamos num APARELHO DE CAMPO — app nativo (Capacitor) ou PWA instalado
  // numa tela pequena? Detecção única (ver lib/nativo.ts::ehAppDeCampo) —
  // usada só para destinoRaiz abaixo. Path-based (ehApp) não bastava: um push
  // pode abrir uma rota fora de /app (/financeiro, /estoque etc. — ver
  // lib/nativo.ts::rotaDoApp) e, se a permissão falhar logo em seguida, o
  // bounce caía no "/" desktop mesmo rodando dentro do app.
  // Era `ehAppOuPwa()`, que dá true também para o PWA instalado no NOTEBOOK
  // (display-mode: standalone não tem relação com tamanho de tela) — quem
  // instalou o atalho no computador era jogado na casca de celular a cada
  // bounce. Mesma correção já feita no Painel CowData.
  const [dentroDoApp, setDentroDoApp] = useState(false);
  useEffect(() => {
    import("@/lib/nativo").then(({ ehAppDeCampo }) => ehAppDeCampo()).then(setDentroDoApp).catch(() => {});
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
  const ROTAS_INSIGHTS = ["/indicadores", "/relatorios", "/analise-relatorios", "/usuarios", "/portal", "/configuracoes", "/parametros", "/news-admin", "/documentos-central"];
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
    // contador é redirecionado automaticamente. Exceto /escolher-conta: um
    // contador vinculado a mais de uma fazenda (raro, mas possível) pode
    // estar ali JUSTAMENTE para trocar para a outra — sem essa exceção, o
    // `fazenda_atual` (ainda) marcado como contador da fazenda anterior
    // bloquearia a própria troca antes dela acontecer.
    if (ehContador() && !ehPainelContador && path !== "/escolher-conta") { router.replace("/contador"); return; }
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

  // Ref sempre atualizada com o path atual — o gatilho de "abrir o app"
  // abaixo dispara de um evento assíncrono (appStateChange/visibilitychange,
  // ver registrarAoAbrirApp) que não pode depender do `path` capturado no
  // fechamento do efeito no momento em que ele foi registrado (senão, ao
  // reabrir o app numa tela diferente da que estava aberta quando o
  // listener foi criado, o "next" da troca de conta apontaria pro lugar
  // errado).
  const pathRef = useRef(path);
  useEffect(() => { pathRef.current = path; }, [path]);

  // Pergunta "trocar de conta" a cada ABERTURA do app — nunca em navegação
  // interna (ver lib/nativo.ts::registrarAoAbrirApp, que só dispara no
  // sinal do próprio SO/navegador de troca de foco, jamais numa navegação
  // client-side dentro da SPA). Só dentro da casca mobile (app nativo/PWA
  // instalado): no site o mesmo convite só aparece ao entrar (login) e ao
  // pedir para trocar ("Trocar de conta" no menu, ver Sidebar.tsx) — pedido
  // explícito do dono do produto, nunca sozinho a cada foco de aba no
  // navegador comum.
  //
  // Depende só de `dentroDoApp` (Capacitor.isNativePlatform()/PWA
  // standalone, ver lib/nativo.ts::ehAppOuPwa) — NUNCA de `ehApp` (que é
  // só `path.startsWith("/app")`): quem está dentro do app e navega para
  // uma rota "de site" (ex.: Financeiro, aberto pela Sidebar dentro da
  // mesma WebView) continua tão "dentro do app" quanto estava — `ehApp`
  // viraria false nessa hora e, se estivesse nas dependências abaixo,
  // dispararia este efeito de novo por causa da NAVEGAÇÃO, não de uma
  // abertura de verdade. `dentroDoApp` não muda com a rota, só com o
  // ambiente de execução — é o sinal certo aqui.
  //
  // Deliberadamente um efeito PRÓPRIO, independente do de permissões acima:
  // ele não bloqueia a renderização normal (evita amarrar uma checagem de
  // rede a toda a lógica síncrona de permissão) — só navega para
  // /escolher-conta DEPOIS, se descobrir que há mais de uma conta. O custo
  // é uma eventual piscada de conteúdo antes do redirecionamento; o
  // benefício é não arriscar travar a abertura do app numa chamada de
  // rede que pode falhar (ver catch abaixo — falha de rede nunca deve
  // impedir o uso do app, só deixar de perguntar desta vez).
  useEffect(() => {
    if (!hidratado) return;
    if (!dentroDoApp) return; // site (fora do app/PWA): não pergunta sozinho ao focar

    let cancelado = false;
    const perguntarSeTrocaDeConta = async () => {
      if (cancelado || !getToken()) return;
      const atual = pathRef.current;
      // Já estamos na própria tela de escolha, ou ainda nem logamos — nada
      // a fazer (login cuida do próprio caso via selecao_fazenda_necessaria).
      if (atual === "/escolher-conta" || atual === "/login") return;

      // Só repergunta depois de uma AUSÊNCIA DE VERDADE. Antes disto, o
      // gatilho era "o app voltou ao primeiro plano" — e isso acontece ao
      // trocar de aba, atender o telefone, ou abrir e fechar o app de novo em
      // dois segundos. O resultado prático era ter que escolher a fazenda a
      // cada volta, para depois seguir exatamente para onde já se estava:
      // uma pergunta cuja resposta certa é sempre a mesma não é uma pergunta,
      // é um pedágio.
      //
      // 15 minutos é o mesmo limite do logout por inatividade (lib/idle.ts) —
      // a fronteira que o produto já usa para dizer "esta pessoa saiu de
      // perto". Já ter uma conta escolhida é a outra metade: sem ela, ainda
      // não há contexto nenhum e perguntar é o certo, tenha passado o tempo
      // que for. `null` (nenhuma marca ainda) cai no mesmo caso.
      const foraHa = msDesdeUltimaPresenca();
      const jaTemConta = getContaAtivaId() != null;
      if (jaTemConta && foraHa != null && foraHa < LIMITE_INATIVIDADE_MS) return;

      try {
        const opcoes = await fetchContasDisponiveis();
        // Só vale a pena perguntar quando há de fato mais de 1 opção — um
        // funcionário de fazenda única nunca deve ver esta tela sozinha
        // (regra de produto: "um acesso só entra direto, sem tela").
        if (!cancelado && opcoes.length > 1) {
          const destino = `${window.location.pathname}${window.location.search}`;
          router.push(`/escolher-conta?next=${encodeURIComponent(destino)}`);
        }
      } catch {
        // Rede indisponível/instável (uso rural comum, ver comentário sobre
        // CapacitorHttp em capacitor.config.ts) — segue sem perguntar desta
        // vez, nunca trava a abertura do app por causa disto.
      }
    };

    perguntarSeTrocaDeConta(); // cobre a abertura fria (1º mount deste componente)

    // A marca de presença é mantida por CONTA PRÓPRIA, sem depender do monitor
    // de inatividade (que desiste quando "manter conectado" está marcado — ver
    // lib/idle.ts). Regravada enquanto o app está à vista e uma última vez ao
    // ir para segundo plano, para que o cálculo do tempo fora seja o tempo
    // fora de verdade, e não o tempo desde a última vez que o monitor rodou.
    marcarPresenca();
    const carimbar = () => { if (typeof document === "undefined" || document.visibilityState === "visible") marcarPresenca(); };
    const carimbarAoSair = () => { if (typeof document !== "undefined" && document.visibilityState === "hidden") marcarPresenca(); };
    const intervalo = window.setInterval(carimbar, 60 * 1000);
    document.addEventListener("visibilitychange", carimbarAoSair);

    // Ordem importa: a pergunta lê a marca ANTES de qualquer recarimbo, senão
    // o próprio retorno zeraria o tempo fora e a checagem nunca dispararia.
    const aoVoltar = () => { perguntarSeTrocaDeConta().finally(carimbar); };
    const limpezaPromise = import("@/lib/nativo").then(({ registrarAoAbrirApp }) => registrarAoAbrirApp(aoVoltar));

    return () => {
      cancelado = true;
      window.clearInterval(intervalo);
      document.removeEventListener("visibilitychange", carimbarAoSair);
      limpezaPromise.then((limpar) => limpar()).catch(() => {});
    };
  }, [hidratado, dentroDoApp, router]);

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

  // "/" pública (T8): visitante SEM login não é redirecionado para /login
  // (ver ROTA_PUBLICA acima) — em vez disso vê a landing pública, com a
  // própria casca (PublicPage), sem a Sidebar/farm-shell abaixo. app/page.tsx
  // decide sozinha landing-vs-Capa (mesmo getToken() que este componente já
  // usa, sem contexto novo); aqui só liberamos a passagem, do mesmo jeito que
  // /login e /sobre/* acima. Só entra nesse bypass quando `estado` já
  // resolveu para "deslogado" (não durante "checando", que ainda cai no
  // "Carregando…" abaixo) — quando `estado` vira "logado", a raiz volta a
  // cair na Sidebar/farm-shell normal, exatamente como sempre foi.
  if (path === "/" && estado === "deslogado") return <>{children}</>;

  // Milk News tem casca visual PRÓPRIA e FIXA (branca, mesmo logo do site/app)
  // — igual para qualquer visitante, logado ou não, independente do tema
  // escolhido no resto do sistema (ver NewsShell). Fica antes do gate de
  // "estado" porque não depende de login (ver ROTA_PUBLICA acima).
  if (path === "/news" || path.startsWith("/news/")) {
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
  // fazenda — ver comentário no topo deste componente. Sem SuporteBanner nem
  // FazendaTesteBanner aqui: modo suporte é "estar dentro de uma
  // fazenda-cliente como se fosse o admin dela" e "eh_teste" é um atributo
  // da FAZENDA atual — o Painel CowData é a base da própria CowData, sem
  // fazenda-cliente selecionada, não faz sentido nenhuma das duas tarjas
  // aparecer nele (quem quer ver sessões ativas usa a própria tela de
  // Suporte, ver painel-cowdata/cofre/page.tsx).
  if (ehPainelCowData) return <>{children}</>;

  // Tela-eixo de troca de conta (/escolher-conta, ver components/
  // EscolherConta.tsx): casca própria e mínima, igual no site e no app —
  // nem a Sidebar da fazenda nem a barra do app móvel fazem sentido antes
  // de saber em qual conta a pessoa está entrando.
  if (path === "/escolher-conta") return <>{children}</>;

  // Todas as demais cascas logadas (app móvel, Painel do Contador, portais
  // Insights e Dietas, e a casca padrão da fazenda montada abaixo) recebem a
  // faixa de suporte quando ativa e a tarja de Fazenda Teste quando a fazenda
  // atual é o sandbox — pedido explícito do usuário: antes a de suporte só
  // existia dentro da casca padrão, e sumia ao entrar em Insights e
  // Administração ou Formulação de Dietas (cascas próprias, que nem
  // chegavam a este ponto do componente); a de Fazenda Teste nasce já
  // cobrindo todas elas de uma vez. Ambas são `position: fixed` e medem a
  // própria altura para publicar --suporte-banner-h/--fazenda-teste-banner-h
  // (ver SuporteBanner.tsx/FazendaTesteBanner.tsx) — todo elemento fixo no
  // topo do resto do app (.site-top-actions, barra mobile da Sidebar,
  // cabeçalho do app móvel) soma as duas variáveis ao próprio "top" para
  // nunca ficar por baixo delas; o restante do conteúdo (fluxo normal) desce
  // sozinho via padding-top no <body> (ver globals.css).
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
      {/* Ordem importa: FazendaTesteBanner fica por cima (top:0, z-index
          maior) — "em que ambiente eu estou" é mais fundamental e nunca muda
          durante a sessão, então empilha ANTES da de suporte, que é
          temporária e some ao encerrar. SuporteBanner já soma
          --fazenda-teste-banner-h no próprio `top` para descer pra baixo
          dela quando as duas coexistirem (ver comentário no topo de cada
          arquivo). */}
      <FazendaTesteBanner />
      <SuporteBanner />
      <OfflineBanner />
      {conteudo}
    </>
  );
}
