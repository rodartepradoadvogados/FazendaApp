"use client";
// Casca do APP MÓVEL (/app): cabeçalho marinho institucional com status online/offline,
// alternador claro/escuro, badge de pendências e navegação inferior fixa
// (Agenda · Lançar · Rebanho · Menu). Registra o service worker (abre sem
// internet) e liga a sincronização automática da fila offline.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { PlusCircle, Sun, Moon, CloudUpload } from "lucide-react";
import { aplicarTema } from "@/components/ThemeSwitcher";
import { fetchAgenda, today } from "@/lib/api";
import { iniciarSincronizacaoAutomatica, useConectividadeReal, usePendentes, useSincProgresso } from "@/lib/offline";
import { ajustarStatusBar, esconderSplash, registrarBotaoVoltar, registrarPushNativo } from "@/lib/nativo";
import { InstalarApp } from "@/components/mobile/InstalarApp";
import { ConexaoFaixa } from "@/components/mobile/ConexaoFaixa";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { NewsIcon } from "@/components/mobile/NewsIcon";
import { CalendarColorfulIcon, MenuTricolorIcon } from "@/components/mobile/AppIcons";
import { CowIcon } from "@/components/CowIcon";

// `cor`: identidade própria de cada aba (ver --mob-nav-* em globals.css) —
// exposta como var(--aba) no <Link> (abaixo) e usada pelo CSS (.mob-nav
// a.ativo) e pelos ícones via prop `color`, em vez de todo mundo compartilhar
// um único --mob-acao dourado.
const ABAS = [
  { href: "/app", label: "Agenda", cor: "var(--mob-nav-agenda)" },
  { href: "/app/lancar", label: "Lançar", cor: "var(--mob-nav-lancar)" },
  { href: "/app/rebanho", label: "Rebanho", cor: "var(--mob-nav-rebanho)" },
  { href: "/app/menu", label: "Menu", cor: "var(--mob-nav-menu)" },
];

// Índice da aba a que `caminho` pertence (-1 se não for nenhuma das 4 — ex.:
// /app/curral, aberto pelo link "Modo Curral" dentro de Lançar, não é aba).
function indiceAba(caminho: string): number {
  return ABAS.findIndex(({ href }) => (href === "/app" ? caminho === "/app" : caminho.startsWith(href)));
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const pathRef = useRef(path);
  pathRef.current = path;

  // Direção da troca de aba (para o conteúdo deslizar do lado certo — ver
  // .mob-troca-aba em globals.css): comparamos a aba do caminho ANTERIOR com
  // a do caminho atual durante a própria renderização (padrão documentado do
  // React para "guardar informação do render anterior" com useRef, sem
  // useEffect — dispensável aqui e evitaria só o primeiro quadro do slide).
  // Troca dentro da MESMA aba (ex.: abrir a ficha de um animal em Rebanho)
  // não desliza — só transições entre as 4 abas da barra.
  const caminhoAnteriorRef = useRef(path);
  const direcaoRef = useRef<"direita" | "esquerda" | null>(null);
  if (caminhoAnteriorRef.current !== path) {
    const abaAnterior = indiceAba(caminhoAnteriorRef.current);
    const abaAtual = indiceAba(path);
    direcaoRef.current = abaAnterior === -1 || abaAtual === -1 || abaAnterior === abaAtual
      ? null
      : abaAtual > abaAnterior ? "direita" : "esquerda";
    caminhoAnteriorRef.current = path;
  }
  // Ping real ao servidor (não só a rádio do aparelho, que pode dizer
  // "conectado" mesmo com nosso servidor inalcançável — ver lib/offline.ts).
  const online = useConectividadeReal();
  const fila = usePendentes();
  const progressoSync = useSincProgresso();
  const [escuro, setEscuro] = useState(false);
  // Cabeçalho FIXO (não some ao rolar). Medimos a altura real — que varia com a
  // faixa de segurança do topo (notch) — para reservar o mesmo espaço abaixo.
  const headerRef = useRef<HTMLElement | null>(null);
  const [alturaHeader, setAlturaHeader] = useState(64);

  // Tema: no app só existe claro (alto contraste) e escuro (OLED); o "misto"
  // do site é tratado como claro aqui.
  useEffect(() => {
    setEscuro(document.documentElement.getAttribute("data-theme") === "escuro");
  }, []);
  function alternarTema() {
    const novo = escuro ? "claro" : "escuro";
    setEscuro(!escuro);
    aplicarTema(novo as "claro" | "escuro");
  }

  // Mede a altura do cabeçalho fixo e mantém o espaçador sincronizado.
  useEffect(() => {
    const medir = () => { if (headerRef.current) setAlturaHeader(headerRef.current.offsetHeight); };
    medir();
    window.addEventListener("resize", medir);
    return () => window.removeEventListener("resize", medir);
    // progressoSync entra na dependência porque a faixa de conexão (dentro do
    // cabeçalho) muda de altura conforme o estado (lasquinha fina vs. barra
    // de sincronização com 2 linhas) — sem isso o espaçador ficava com a
    // altura antiga e o conteúdo passava por baixo do cabeçalho.
  }, [fila.length, progressoSync]);

  // Service worker (abrir offline) + sincronização automática da fila.
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
    return iniciarSincronizacaoAutomatica();
  }, []);

  // App Android nativo (Capacitor) — nenhuma destas chamadas faz nada fora
  // dele (ver lib/nativo.ts). Esconde a splash assim que a casca montou (a
  // config tem um teto de segurança caso isto nunca rode) e registra o botão
  // voltar físico: navega como o navegador, só fecha o app na raiz do /app.
  useEffect(() => {
    esconderSplash();
  }, []);
  useEffect(() => {
    let ativo = true;
    let remover = () => {};
    // pathRef (não `path` direto) — registra uma única vez; o listener nativo
    // sempre lê o caminho MAIS RECENTE sem precisar remover/recriar a cada navegação.
    registrarBotaoVoltar(() => pathRef.current === "/app").then((r) => { if (ativo) remover = r; else r(); });
    return () => { ativo = false; remover(); };
  }, []);
  useEffect(() => {
    ajustarStatusBar(escuro);
  }, [escuro]);
  // Push nativo (FCM) — pede permissão, registra o token no backend e
  // navega pra rota certa se o usuário tocar numa notificação com o app já
  // aberto. Não faz nada fora do app nativo (ver lib/nativo.ts).
  useEffect(() => {
    let ativo = true;
    let remover = () => {};
    registrarPushNativo((rota) => router.push(rota)).then((r) => { if (ativo) remover = r; else r(); });
    return () => { ativo = false; remover(); };
  }, [router]);

  // Bolinha no ícone do app instalado (Badging API) com a quantidade de
  // eventos da agenda de hoje — mesma contagem do push "Agenda do dia"
  // (backend/fazenda/api/routers/push.py:despachar_agenda_do_dia), mas
  // recalculada aqui a cada 5 min (e ao abrir o app) para o badge continuar
  // certo mesmo sem depender de push (ex.: navegador sem suporte a Web Push,
  // ou eventos marcados como realizados desde o último push do dia).
  useEffect(() => {
    if (typeof navigator === "undefined" || !("setAppBadge" in navigator)) return;
    let cancelado = false;
    const atualizarBadge = () => {
      fetchAgenda(today())
        .then((agenda) => {
          if (cancelado) return;
          const hoje = today();
          const total = (agenda?.eventos || []).filter((e: { data?: string }) => e.data === hoje).length;
          if (total > 0) (navigator as any).setAppBadge(total).catch(() => {});
          else (navigator as any).clearAppBadge?.().catch(() => {});
        })
        .catch(() => {}); // offline ou erro de rede — mantém o badge como estava
    };
    atualizarBadge();
    const h = setInterval(atualizarBadge, 5 * 60 * 1000);
    return () => { cancelado = true; clearInterval(h); };
  }, []);

  return (
    <div className="mob">
      {/* Cabeçalho marinho institucional — FIXO no topo (não some ao rolar no celular). */}
      <header ref={headerRef} style={{ background: "var(--mob-header)", color: "var(--mob-header-fg)", padding: "calc(0.9rem + env(safe-area-inset-top)) 1.1rem 0.9rem", borderRadius: "var(--r-app)", position: "fixed", top: "var(--suporte-banner-h, 0px)", left: 0, right: 0, zIndex: 40 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", maxWidth: 560, margin: "0 auto" }}>
          <div>
            <p style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
              <CowDataMark size={22} />
              <CowDataWordmark size="1rem" cowColor="var(--mob-header-fg)" dataColor="var(--mob-dourado-2)" />
              {/* Bolinha de conexão: verde luminoso quando o SERVIDOR responde de
                  verdade (ping real, não só a rádio do aparelho — ver
                  useConectividadeReal em lib/offline.ts), vermelha quando não. */}
              <span
                title={online ? "Servidor CowData respondendo" : "Servidor CowData inalcançável agora — os lançamentos ficam guardados e serão enviados quando voltar"}
                style={{
                  width: 9, height: 9, borderRadius: "50%", display: "inline-block",
                  background: online ? "var(--mob-verde-neon)" : "#FF4D4D",
                  boxShadow: online ? "0 0 7px rgba(0,255,157,0.8)" : "0 0 7px rgba(255,77,77,0.8)",
                }}
              />
            </p>
            <p style={{ fontSize: "0.68rem", opacity: 0.85 }}>Estreito Ponte de Pedra</p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {fila.length > 0 && (
              <Link href="/app/menu#pendentes" title={`${fila.length} lançamento(s) aguardando internet para enviar`}
                style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.72rem", fontWeight: 700, color: "var(--mob-dourado-pale)", background: "rgba(255,255,255,0.12)", borderRadius: 999, padding: "0.3rem 0.6rem", textDecoration: "none" }}>
                <CloudUpload size={14} /> {fila.length}
              </Link>
            )}
            <Link href="/app/menu#news" title="News — notícias de pecuária leiteira" aria-label="Abrir News"
              onClick={(e) => {
                // Já estamos em /app/menu: o Next faz a navegação por
                // pushState (mesma rota, sem remontar a página) — pushState
                // NÃO dispara o evento 'hashchange' que a página escuta, então
                // o clique não abria nada. Avisa direto por evento customizado.
                if (path === "/app/menu") {
                  e.preventDefault();
                  if (window.location.hash !== "#news") history.pushState(null, "", "/app/menu#news");
                  window.dispatchEvent(new CustomEvent("app-abrir-news"));
                }
              }}
              style={{ width: 56, height: 56, borderRadius: "50%", background: "rgba(255,255,255,0.12)", color: "var(--mob-header-fg)", display: "flex", alignItems: "center", justifyContent: "center", textDecoration: "none" }}>
              <NewsIcon size={19} color="var(--mob-header-fg)" />
            </Link>
            <button type="button" onClick={alternarTema} aria-label={escuro ? "Mudar para tema claro" : "Mudar para tema escuro"}
              style={{ width: 56, height: 56, borderRadius: "50%", border: "none", cursor: "pointer", background: "rgba(255,255,255,0.12)", color: "var(--mob-header-fg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              {escuro ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>

        {/* Faixa de conexão — DoD T6: indicador persistente do estado
            online/offline/sincronizando da fila (lib/offline.ts). Fica DENTRO
            do cabeçalho fixo de propósito: o próprio `alturaHeader` acima já
            mede a altura total do cabeçalho (ref no <header>), então o
            espaçador abaixo dele se ajusta sozinho sem nenhuma outra conta de
            posição fixa. */}
        <div style={{ maxWidth: 560, margin: "0 auto" }}>
          <ConexaoFaixa online={online} pendentes={fila.length} progresso={progressoSync} />
        </div>
      </header>

      {/* Espaçador da altura do cabeçalho fixo — evita que o conteúdo comece por baixo dele. */}
      <div aria-hidden="true" style={{ height: alturaHeader }} />

      {/* Conteúdo da aba — chaveado pelo caminho para remontar (e disparar de
          novo a animação de entrada) a cada navegação; a classe de direção só
          entra quando a troca foi de fato entre duas das 4 abas da barra. */}
      <main className="mob-conteudo">
        <InstalarApp />
        <div key={path} className={direcaoRef.current ? `mob-troca-aba ${direcaoRef.current}` : undefined}>
          {children}
        </div>
      </main>

      {/* Navegação inferior (zona do polegar) */}
      <nav className="mob-nav">
        {ABAS.map(({ href, label, cor }) => {
          const ativo = href === "/app" ? path === "/app" : path.startsWith(href);
          const ehLancar = href === "/app/lancar";
          // Cor da aba inativa vem do token neutro --mob-nav-inativa; ativa usa
          // a cor própria da aba (var(--aba), exposta no <Link> abaixo). O ícone
          // de "Lançar" fica de fora: o pill elevado (.mob-nav-lancar) já define
          // `color:#fff` incondicionalmente via CSS (contraste sobre o círculo
          // dourado em qualquer estado) — passar uma cor explícita aqui
          // sobrescreveria esse branco com a própria cor de fundo do pill.
          const corIcone = ativo ? cor : "var(--mob-nav-inativa)";
          return (
            <Link key={href} href={href} className={ativo ? "ativo" : ""} style={{ "--aba": cor } as React.CSSProperties}>
              <span className={ehLancar ? "mob-nav-icone mob-nav-lancar" : "mob-nav-icone"}>
                {href === "/app" && <CalendarColorfulIcon size={21} color={corIcone} strokeWidth={ativo ? 1.6 : 1.2} />}
                {href === "/app/lancar" && <PlusCircle size={27} strokeWidth={ativo ? 2.4 : 1.8} />}
                {href === "/app/rebanho" && <CowIcon size={21} color={corIcone} strokeWidth={ativo ? 1.4 : 1.1} />}
                {href === "/app/menu" && <MenuTricolorIcon size={21} color={corIcone} />}
              </span>
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
