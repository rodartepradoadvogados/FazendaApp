"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Calendar,
  Heart,
  BarChart3,
  Package,
  Home,
  Milk,
  Wheat,
  Syringe,
  ClipboardList,
  ShoppingCart,
  Menu,
  X,
  Building2,
  ListChecks,
  ChevronsLeft,
  ChevronsRight,
  ExternalLink,
  FlaskConical,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { checkHealth, getUsuario, getFazendaAtual, logout, podeModulo, ehAdmin, ehDono, podeFormularDietas, ROTA_MODULO } from "@/lib/api";
import { LogOut, UserCircle } from "lucide-react";
import { CowIcon } from "@/components/CowIcon";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { useCliqueOuDuploClique, abrirNovaAba } from "@/lib/tabs";

// Link de módulo com duplo clique = abrir aba nova (ver TabsShell), sem
// perder a aba atual onde ela estava. Clique com Ctrl/Cmd/Shift ou botão do
// meio passa direto (abre nova guia do NAVEGADOR, comportamento nativo do
// <a> preservado) — só o clique simples é interceptado para navegar por
// dentro do app como hoje, e o duplo clique vira aba interna.
function SidebarLink({ href, title, label, active, recolhida, children }: {
  href: string; title?: string; label: string; active: boolean; recolhida?: boolean; children: React.ReactNode;
}) {
  const router = useRouter();
  const aoClicar = useCliqueOuDuploClique(
    () => router.push(href),
    () => abrirNovaAba(href, label),
  );
  return (
    <Link
      href={href}
      title={title || label}
      className="flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150"
      style={{
        background: active ? "var(--sidebar-active-bg)" : "transparent",
        color: active ? "var(--sidebar-active-fg)" : "var(--sidebar-muted)",
        borderLeft: active ? "3px solid var(--sidebar-active-border)" : "3px solid transparent",
        fontSize: "10px",
        justifyContent: recolhida ? "center" : "flex-start",
        paddingLeft: recolhida ? "0.4rem" : undefined,
        paddingRight: recolhida ? "0.4rem" : undefined,
      }}
      onClick={(e) => {
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return; // deixa o navegador tratar normalmente
        e.preventDefault();
        aoClicar();
      }}
    >
      {children}
    </Link>
  );
}

// Grupos visuais da navegação (rótulo discreto acima de cada seção) — mesma
// ordem do fluxo de gestão: (1) ciclo diário; (2) manejo do rebanho; (3)
// insumos/sanidade (consumíveis do dia a dia); (4) análise; (5) financeiro
// (Controle Financeiro + Pedidos). Análise e Administração não têm mais
// grupo aqui — viraram o portal "Insights e Administração" (ver
// components/insights/InsightsLayout.tsx), aberto por um único atalho no
// rodapé desta barra, numa aba nova de verdade do navegador. Recria não tem
// mais item próprio aqui — virou sub-aba de Indicadores.
const GRUPOS = ["Ciclo diário", "Manejo do rebanho", "Insumos e sanidade", "Financeiro"] as const;

const links = [
  // ── Ciclo diário ──
  { href: "/",            label: "Capa",        icon: Home,          title: "Capa — visão geral da fazenda", grupo: "Ciclo diário" },
  { href: "/agenda",      label: "Agenda",       icon: Calendar,      title: "Agenda de atividades do dia — pendências e eventos a cumprir", grupo: "Ciclo diário" },
  { href: "/lancamentos", label: "Lançamentos",  icon: ClipboardList, title: "Lançamentos — registrar eventos e dados do dia a dia", grupo: "Ciclo diário" },
  { href: "/protocolos",  label: "Central de Protocolos", icon: ListChecks, title: "Central de Protocolos — cadastro, lançamento, acompanhamento e histórico de IATF, Sanitário, Indução de Lactação e Customizado", grupo: "Ciclo diário" },
  // ── Manejo do rebanho ──
  { href: "/rebanho",     label: "Rebanho",      icon: CowIcon,       title: "Rebanho — animais, movimentações entre lotes e ficha do animal", grupo: "Manejo do rebanho" },
  { href: "/historico",   label: "Histórico",    icon: Heart,         title: "Histórico — Reprodução (serviços, diagnósticos, partos) e Produção (controle leiteiro, secagem, BST)", grupo: "Manejo do rebanho" },
  // ── Insumos e sanidade ──
  { href: "/sanidade",    label: "Sanidade",     icon: Syringe,       title: "Sanidade — aplicações, protocolos e calendário sanitário", grupo: "Insumos e sanidade" },
  { href: "/alimentacao", label: "Alimentação",  icon: Wheat,         title: "Alimentação — dieta, consumo e necessidade por lote", grupo: "Insumos e sanidade" },
  { href: "/estoque",     label: "Estoque",      icon: Package,       title: "Estoque de insumos — quantidades, valores e itens abaixo do mínimo", grupo: "Insumos e sanidade" },
  // ── Financeiro ──
  { href: "/financeiro",  label: "Controle Financeiro", icon: BarChart3, title: "Controle Financeiro — contas a pagar/receber, folha e indicadores", grupo: "Financeiro" },
  { href: "/pedidos",     label: "Pedidos",      icon: ShoppingCart,  title: "Pedidos — intenção de compra/venda; só reflete em Estoque/Financeiro quando a nota fiscal/recibo é vinculada", grupo: "Financeiro" },
];

// Itens de módulo que não vêm de `links` (montados à parte, mais abaixo) mas
// que também registram sub-navegação — usado só para dar título à aba nova
// aberta em duplo clique numa sub-aba (ver SubNavItem).
const EXTRAS_TITULO_SIDEBAR: Record<string, string> = {
  "/configuracoes": "Configurações",
  "/portal": "Portal",
  "/consultor": "Consultor",
  "/usuarios": "Controle de Acesso",
  "/indicadores": "Indicadores",
  "/relatorios": "Listas",
  "/analise-relatorios": "Relatórios",
};
export function rotuloDaPagina(path: string): string {
  return links.find((l) => l.href === path)?.label ?? EXTRAS_TITULO_SIDEBAR[path] ?? path;
}

export function Sidebar() {
  const path = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);
  const [aberto, setAberto] = useState(false); // drawer no mobile
  // Recolher a barra inteira (só desktop) para ícones — preferência do
  // usuário, persistida entre sessões. Começa expandida (false) para não
  // "piscar" recolhida no primeiro paint; sincroniza com o localStorage já
  // no mount seguinte (undefined/erro = expandida).
  const [recolhidaPref, setRecolhidaPref] = useState(false);
  useEffect(() => {
    try { setRecolhidaPref(localStorage.getItem("sidebar-recolhida") === "1"); } catch { /* ignore */ }
  }, []);
  function alternarRecolhida() {
    setRecolhidaPref((prev) => {
      const next = !prev;
      try { localStorage.setItem("sidebar-recolhida", next ? "1" : "0"); } catch { /* ignore */ }
      return next;
    });
  }
  // A preferência de recolher só existe no desktop (breakpoint md, 768px) —
  // no mobile o drawer é sempre cheio, então o conteúdo (rótulos, wordmark,
  // sub-navegação) não pode virar "só ícone" ali mesmo com a preferência
  // salva de uma sessão desktop anterior.
  const [ehDesktop, setEhDesktop] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    setEhDesktop(mq.matches);
    const ouvir = (e: MediaQueryListEvent) => setEhDesktop(e.matches);
    mq.addEventListener("change", ouvir);
    return () => mq.removeEventListener("change", ouvir);
  }, []);
  const recolhida = recolhidaPref && ehDesktop;
  const [visiveis, setVisiveis] = useState(links);
  const [admin, setAdmin] = useState(false);
  const [dono, setDono] = useState(false);

  const [temConfiguracoes, setTemConfiguracoes] = useState(false);
  const [insightsHref, setInsightsHref] = useState("/indicadores");
  const [formularDietas, setFormularDietas] = useState(false);
  // Nome exibido embaixo do logo CowData — vem da fazenda selecionada no
  // login (piloto conservador de multi-fazenda). "Jairo Nasser" é o valor
  // fixo de sempre, mantido como fallback para quem nunca teve mais de uma
  // fazenda vinculada (ninguém percebe diferença nenhuma).
  const [fazendaNome, setFazendaNome] = useState("Jairo Nasser");

  useEffect(() => {
    // Filtra o menu conforme as permissões do usuário logado. "/historico"
    // reúne Reprodução + Produção — mostra o link se o usuário tiver
    // qualquer uma das duas (a página em si esconde a sub-aba sem permissão).
    setVisiveis(links.filter((l) => (
      l.href === "/historico" ? (podeModulo("reproducao") || podeModulo("producao")) : podeModulo(ROTA_MODULO[l.href] || l.href)
    )));
    setAdmin(ehAdmin());
    setDono(ehDono());
    setTemConfiguracoes(podeModulo("parametros") || podeModulo("upload") || ehAdmin());
    setFazendaNome(getFazendaAtual()?.nome || "Jairo Nasser");
    // Destino do atalho "Insights e Administração" (ver botão no rodapé) —
    // primeira aba que o usuário realmente enxerga dentro do portal, na
    // mesma ordem da barra de abas do portal (ver InsightsLayout.tsx:
    // Indicadores e Relatórios usam o módulo "indicadores"; Listas usa
    // "reproducao"). Portal é o único item de lá sem nenhuma permissão de
    // módulo — garante que o atalho sempre leva a algum lugar válido.
    setInsightsHref(
      podeModulo("indicadores") ? "/indicadores" :
      podeModulo("reproducao") ? "/relatorios" :
      "/portal"
    );
    setFormularDietas(podeFormularDietas());
  }, [path]);

  useEffect(() => {
    let ativo = true;
    const ping = () => checkHealth().then((ok) => ativo && setOnline(ok));
    ping();
    const id = setInterval(ping, 30000);
    return () => {
      ativo = false;
      clearInterval(id);
    };
  }, []);

  // Fecha o menu ao trocar de página (no mobile).
  useEffect(() => { setAberto(false); }, [path]);

  const statusLabel =
    online === null ? "Verificando..." : online ? "API conectada" : "API offline";
  const statusColor =
    online === null ? "var(--text-muted)" : online ? "var(--green-light)" : "var(--red)";

  return (
    <>
      {/* Barra superior — só no mobile. FIXA no topo (position: fixed) para não
          sumir ao rolar a página; sticky não segura aqui porque os ancestrais
          têm overflow-x: hidden (que vira scroll-container e quebra o sticky).
          paddingTop com safe-area-inset-top evita ficar atrás da barra de
          status do celular (relógio/bateria/sinal) em telas com notch — sem
          isso o conteúdo (inclusive o botão de abrir o menu) nascia parcialmente
          escondido atrás dela. */}
      <div className="md:hidden flex items-center gap-3 px-4 fixed top-0 left-0 right-0 z-30"
        style={{
          top: "var(--suporte-banner-h, 0px)",
          height: "calc(3.25rem + env(safe-area-inset-top, 0px))",
          paddingTop: "env(safe-area-inset-top, 0px)",
          background: "var(--sidebar-bg)", borderBottom: "1px solid var(--sidebar-border)",
        }}>
        <button onClick={() => setAberto(true)} aria-label="Abrir menu" title="Abrir o menu de navegação"
          style={{ background: "none", border: "none", color: "var(--sidebar-fg)", cursor: "pointer", display: "flex" }}>
          <Menu size={22} />
        </button>
        <CowDataWordmark size="0.85rem" cowColor="var(--sidebar-fg)" />
        <span style={{ color: "var(--sidebar-muted)", fontSize: "0.7rem" }}>· {fazendaNome}</span>
      </div>
      {/* Espaçador: reserva a altura da barra fixa (incluindo a faixa de segurança
          do topo) para o conteúdo não ficar por baixo dela. */}
      <div className="md:hidden" style={{ height: "calc(3.25rem + env(safe-area-inset-top, 0px))" }} aria-hidden="true" />

      {/* Fundo escuro atrás do drawer aberto (mobile) */}
      {aberto && <div className="md:hidden fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.55)" }} onClick={() => setAberto(false)} />}

      <aside
        // paddingTop com safe-area-inset-top: o drawer mobile (fixed, inset-y-0)
        // nasce colado no topo real da tela — sem essa reserva, o botão fechar
        // e a logo ficavam por baixo da barra de status/notch do celular ao
        // abrir o menu (a barra fixa de fora, acima, já tinha essa proteção —
        // ver comentário mais abaixo — mas o CONTEÚDO do drawer em si não
        // tinha). No desktop o valor é 0 (sem notch), então não muda nada lá.
        style={{ background: "var(--sidebar-bg)", borderRight: "1px solid var(--sidebar-border)", position: "relative", paddingTop: "env(safe-area-inset-top, 0px)" }}
        // Recolhida só vale a partir do breakpoint md — no mobile o drawer
        // sempre abre na largura cheia (w-56 base), independente da
        // preferência de recolher salva (essa é só para a barra fixa do
        // desktop; no mobile o menu já fecha inteiro depois de navegar).
        className={`w-56 ${recolhida ? "md:w-[52px]" : "md:w-56"} flex flex-col flex-shrink-0 h-full fixed md:static inset-y-0 left-0 z-50 transform transition-[width,transform] duration-200 ${aberto ? "translate-x-0" : "-translate-x-full"} md:translate-x-0`}
      >
      {/* Botão fechar — só no mobile */}
      <button onClick={() => setAberto(false)} aria-label="Fechar menu" title="Fechar o menu de navegação"
        className="md:hidden"
        style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", color: "var(--sidebar-muted)", cursor: "pointer" }}>
        <X size={20} />
      </button>
      {/* Recolher/expandir a barra inteira — só desktop (no mobile o menu já
          fecha/abre como drawer, não faz sentido também recolher). Preso à
          borda direita da barra, sempre visível independente do scroll. */}
      <button onClick={alternarRecolhida} aria-label={recolhida ? "Expandir menu" : "Recolher menu"}
        title={recolhida ? "Expandir menu" : "Recolher menu"}
        className="hidden md:flex"
        style={{
          position: "absolute", top: "1.1rem", right: "-11px", zIndex: 10,
          width: 22, height: 22, borderRadius: "50%", alignItems: "center", justifyContent: "center",
          background: "var(--sidebar-bg)", border: "1px solid var(--sidebar-border)", color: "var(--sidebar-muted)", cursor: "pointer",
        }}>
        {recolhida ? <ChevronsRight size={12} /> : <ChevronsLeft size={12} />}
      </button>
      {/* Logo */}
      <div
        className="p-4 border-b"
        style={{ borderColor: "var(--sidebar-border)" }}
      >
        <div className="flex flex-col gap-1 px-2 py-2" style={recolhida ? { alignItems: "center", padding: 0 } : undefined}>
          <CowDataMark size={recolhida ? 32 : 56} />
          {!recolhida && (
            <>
              <CowDataWordmark size="1.05rem" cowColor="var(--sidebar-fg)" />
              <p style={{ color: "var(--sidebar-logo-sub)", fontSize: "0.6rem", lineHeight: 1.2 }}>
                {fazendaNome}
              </p>
            </>
          )}
        </div>
      </div>

      {/* Nav: lista de módulos, agrupada por GRUPOS. A árvore de sub-abas da
          página atual (quando ela registra uma) não fica mais aqui — virou
          uma barra de abas horizontais no topo do conteúdo (ver
          components/SubNavTabs.tsx, montada em AuthShell.tsx). */}
      <nav className="flex-1 flex flex-col" style={{ minHeight: 0 }}>
        <div className="flex-1 p-3 space-y-1" style={{ overflowY: "auto", minHeight: 0 }}>
          {(() => {
            // Administração (Controle de Acesso, Painel CowData, Painel do
            // Contador, Portal, Consultor, Configurações) saiu daqui — mora
            // no portal Insights e Administração agora (atalho no rodapé).
            const todos = visiveis;
            return GRUPOS.map((grupo, i) => {
              const itens = todos.filter((l) => l.grupo === grupo);
              if (!itens.length) return null;
              return (
                <div key={grupo}>
                  {!recolhida && (
                    <p style={{
                      fontSize: "10px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em",
                      color: "var(--sidebar-muted)", margin: i === 0 ? "0 0 0.3rem 0.6rem" : "0.7rem 0 0.3rem 0.6rem",
                    }}>
                      {grupo}
                    </p>
                  )}
                  {itens.map(({ href, label, icon: Icon, title }) => {
                    const active = path === href || (href !== "/" && path.startsWith(href));
                    return (
                      <SidebarLink key={href} href={href} title={title} label={label} active={active} recolhida={recolhida}>
                        <Icon size={16} />
                        {!recolhida && label}
                      </SidebarLink>
                    );
                  })}
                </div>
              );
            });
          })()}
        </div>
      </nav>

      {/* Atalho para o portal "Insights e Administração" (Indicadores,
          Listas, Relatórios, Controle de Acesso, Painel CowData, Painel do
          Contador, Portal, Consultor, Configurações — ver
          components/insights/InsightsLayout.tsx). Abre numa aba NOVA de
          verdade do navegador (target="_blank"), não uma aba interna
          simulada (ver lib/tabs.ts) — pedido explícito do usuário para este
          portal "parecer um novo portal". */}
      <div className="p-2 border-t" style={{ borderColor: "var(--sidebar-border)" }}>
        <a href={insightsHref} target="_blank" rel="noopener noreferrer"
          title="Abrir Insights e Administração numa aba nova"
          className="flex items-center gap-2 rounded-lg transition-all duration-150"
          style={{
            padding: recolhida ? "0.5rem 0.4rem" : "0.5rem 0.6rem", justifyContent: recolhida ? "center" : "flex-start",
            color: "var(--sidebar-muted)", textDecoration: "none", fontSize: "10px", fontWeight: 600,
            border: "1px solid var(--sidebar-border)",
          }}>
          <Building2 size={16} />
          {!recolhida && <span className="flex-1">Insights e Administração</span>}
          {!recolhida && <ExternalLink size={12} />}
        </a>
      </div>

      {/* Atalho para o portal "Formulação de Dietas" (ver
          components/dietas/DietasLayout.tsx) — mesmo padrão do atalho de
          Insights acima (aba NOVA de verdade do navegador), só visível para
          quem passa em podeFormularDietas() (admin/contratante/consultor
          desta fazenda — eixo de acesso à parte, não módulo comum). */}
      {formularDietas && (
        <div className="p-2 border-t" style={{ borderColor: "var(--sidebar-border)" }}>
          <a href="/dietas" target="_blank" rel="noopener noreferrer"
            title="Abrir Formulação de Dietas numa aba nova"
            className="flex items-center gap-2 rounded-lg transition-all duration-150"
            style={{
              padding: recolhida ? "0.5rem 0.4rem" : "0.5rem 0.6rem", justifyContent: recolhida ? "center" : "flex-start",
              color: "var(--sidebar-muted)", textDecoration: "none", fontSize: "10px", fontWeight: 600,
              border: "1px solid var(--sidebar-border)",
            }}>
            <FlaskConical size={16} />
            {!recolhida && <span className="flex-1">Formulação de Dietas</span>}
            {!recolhida && <ExternalLink size={12} />}
          </a>
        </div>
      )}

      {/* Footer — recolhida: só o pontinho de status, sem texto (sem espaço
          para rótulo, usuário logado ou versão). */}
      <div
        className="p-2 border-t text-center"
        style={{ borderColor: "var(--sidebar-border)", fontSize: "0.65rem", color: "var(--sidebar-muted)" }}
        title={recolhida ? statusLabel : undefined}
      >
        <div className="flex items-center justify-center gap-1.5" style={{ color: statusColor }}>
          <span
            className={online === false ? "" : "pulse-dot"}
            style={
              online === false
                ? { width: 8, height: 8, borderRadius: "50%", background: "var(--red)", display: "inline-block" }
                : undefined
            }
          />
          {!recolhida && statusLabel}
        </div>
        {!recolhida && (
          <>
            <UsuarioLogado />
            <p className="mt-0.5">v1.0.0 · Sprint 1</p>
          </>
        )}
      </div>
      </aside>
    </>
  );
}

function UsuarioLogado() {
  const [nome, setNome] = useState<string | null>(null);
  useEffect(() => { const u = getUsuario(); setNome(u?.nome || u?.username || null); }, []);
  if (!nome) return null;
  return (
    <div className="mt-1" style={{ fontSize: "0.68rem" }}>
      <div className="flex items-center justify-center gap-1.5 mb-1" style={{ color: "var(--sidebar-fg)" }}>
        <UserCircle size={13} /> {nome}
      </div>
      <button onClick={logout} title="Encerra a sessão — a próxima pessoa faz login com o próprio usuário"
        className="flex items-center justify-center gap-1.5 mx-auto"
        style={{ background: "none", border: "1px solid var(--sidebar-border)", borderRadius: "var(--r-sm)", padding: "0.2rem 0.55rem", color: "var(--sidebar-muted)", cursor: "pointer" }}>
        <LogOut size={12} /> Sair / trocar de usuário
      </button>
    </div>
  );
}
