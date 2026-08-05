"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Calendar,
  Heart,
  BarChart3,
  Package,
  Home,
  LineChart,
  Milk,
  Wheat,
  Syringe,
  Settings,
  ClipboardList,
  FileBarChart,
  ShoppingCart,
  MessageSquare,
  Users,
  Briefcase,
  Menu,
  X,
  Search,
  Building2,
  ListChecks,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { checkHealth, getUsuario, getFazendaAtual, logout, podeModulo, ehAdmin, ehDono, ROTA_MODULO } from "@/lib/api";
import { LogOut, UserCircle } from "lucide-react";
import { CowIcon } from "@/components/CowIcon";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { useSubNav, type SubNavNode } from "@/components/SubNavContext";
import { useCliqueOuDuploClique, abrirNovaAba } from "@/lib/tabs";

// Link de módulo com duplo clique = abrir aba nova (ver TabsShell), sem
// perder a aba atual onde ela estava. Clique com Ctrl/Cmd/Shift ou botão do
// meio passa direto (abre nova guia do NAVEGADOR, comportamento nativo do
// <a> preservado) — só o clique simples é interceptado para navegar por
// dentro do app como hoje, e o duplo clique vira aba interna.
function SidebarLink({ href, title, label, active, children }: {
  href: string; title?: string; label: string; active: boolean; children: React.ReactNode;
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
// (Controle Financeiro + Pedidos); (6) administração (Configurações, sempre
// por último — Aprovações virou sub-aba de Configurações). Recria não tem
// mais item próprio aqui — virou sub-aba de Indicadores.
const GRUPOS = ["Ciclo diário", "Manejo do rebanho", "Insumos e sanidade", "Análise", "Financeiro", "Administração"] as const;

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
  // ── Análise ──
  { href: "/indicadores", label: "Indicadores",  icon: LineChart,     title: "Indicadores — KPIs e desempenho reprodutivo, produtivo e financeiro", grupo: "Análise" },
  { href: "/relatorios",  label: "Listas",       icon: FileBarChart,  title: "Listas de trabalho — o que fazer hoje com cada animal (PEV, a inseminar, toque, secagem, partos, sêmen)", grupo: "Análise" },
  { href: "/analise-relatorios", label: "Relatórios", icon: FileBarChart, title: "Relatórios — análise reprodutiva e relatório personalizado", grupo: "Análise" },
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
};
export function rotuloDaPagina(path: string): string {
  return links.find((l) => l.href === path)?.label ?? EXTRAS_TITULO_SIDEBAR[path] ?? path;
}

export function Sidebar() {
  const path = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);
  const [aberto, setAberto] = useState(false); // drawer no mobile
  const [visiveis, setVisiveis] = useState(links);
  const [admin, setAdmin] = useState(false);
  const [dono, setDono] = useState(false);

  const [temConfiguracoes, setTemConfiguracoes] = useState(false);
  // Nome exibido embaixo do logo CowData — vem da fazenda selecionada no
  // login (piloto conservador de multi-fazenda). "Jairo Nasser" é o valor
  // fixo de sempre, mantido como fallback para quem nunca teve mais de uma
  // fazenda vinculada (ninguém percebe diferença nenhuma).
  const [fazendaNome, setFazendaNome] = useState("Jairo Nasser");

  // Drill-down: quando a página registra sua árvore de sub-abas, a barra
  // mostra essa árvore ACIMA da lista de módulos (nunca no lugar dela) — assim
  // dá pra navegar dentro da página atual sem nunca perder acesso direto às
  // outras abas do menu principal.
  const subNav = useSubNav();
  // Busca dentro da sub-navegação — atalho para árvores com muitos grupos/
  // sub-abas (ex.: Financeiro, Lançamentos): em vez de abrir grupo por grupo
  // até achar a sub-aba certa, digita um pedaço do nome e pula direto nela.
  const [buscaSubNav, setBuscaSubNav] = useState("");

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

  // Fecha o menu ao trocar de página (no mobile) e limpa a busca de sub-navegação.
  useEffect(() => { setAberto(false); setBuscaSubNav(""); }, [path]);

  // Busca só aparece em árvores "pesadas" (muitas sub-abas) — em módulos com
  // poucas sub-abas não vale o espaço extra na tela.
  const folhasSubNav = useMemo(() => (subNav ? achatarFolhas(subNav.tree) : []), [subNav]);
  const totalFolhasSubNav = subNav ? contarFolhas(subNav.tree) : 0;
  const resultadosBuscaSubNav = useMemo(() => {
    const termo = normalizarBusca(buscaSubNav.trim());
    if (!termo) return null;
    return folhasSubNav.filter((f) => normalizarBusca(f.label).includes(termo) || normalizarBusca(f.caminho).includes(termo));
  }, [folhasSubNav, buscaSubNav]);

  const statusLabel =
    online === null ? "Verificando..." : online ? "API conectada" : "API offline";
  const statusColor =
    online === null ? "var(--text-muted)" : online ? "var(--green-light)" : "var(--red)";

  return (
    <>
      {/* Barra superior — só no mobile. FIXA no topo (position: fixed) para não
          sumir ao rolar a página; sticky não segura aqui porque os ancestrais
          têm overflow-x: hidden (que vira scroll-container e quebra o sticky). */}
      <div className="md:hidden flex items-center gap-3 px-4 fixed top-0 left-0 right-0 z-30"
        style={{ height: "3.25rem", background: "var(--sidebar-bg)", borderBottom: "1px solid var(--sidebar-border)" }}>
        <button onClick={() => setAberto(true)} aria-label="Abrir menu" title="Abrir o menu de navegação"
          style={{ background: "none", border: "none", color: "var(--sidebar-fg)", cursor: "pointer", display: "flex" }}>
          <Menu size={22} />
        </button>
        <CowDataWordmark size="0.85rem" cowColor="var(--sidebar-fg)" />
        <span style={{ color: "var(--sidebar-muted)", fontSize: "0.7rem" }}>· {fazendaNome}</span>
      </div>
      {/* Espaçador: reserva a altura da barra fixa para o conteúdo não ficar por baixo dela. */}
      <div className="md:hidden" style={{ height: "3.25rem" }} aria-hidden="true" />

      {/* Fundo escuro atrás do drawer aberto (mobile) */}
      {aberto && <div className="md:hidden fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.55)" }} onClick={() => setAberto(false)} />}

      <aside
        style={{ background: "var(--sidebar-bg)", borderRight: "1px solid var(--sidebar-border)" }}
        className={`w-56 flex flex-col flex-shrink-0 h-full fixed md:static inset-y-0 left-0 z-50 transform transition-transform duration-200 ${aberto ? "translate-x-0" : "-translate-x-full"} md:translate-x-0`}
      >
      {/* Botão fechar — só no mobile */}
      <button onClick={() => setAberto(false)} aria-label="Fechar menu" title="Fechar o menu de navegação"
        className="md:hidden"
        style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", color: "var(--sidebar-muted)", cursor: "pointer" }}>
        <X size={20} />
      </button>
      {/* Logo */}
      <div
        className="p-4 border-b"
        style={{ borderColor: "var(--sidebar-border)" }}
      >
        <div className="flex flex-col gap-1 px-2 py-2">
          <CowDataMark size={56} />
          <CowDataWordmark size="1.05rem" cowColor="var(--sidebar-fg)" />
          <p style={{ color: "var(--sidebar-logo-sub)", fontSize: "0.6rem", lineHeight: 1.2 }}>
            {fazendaNome}
          </p>
        </div>
      </div>

      {/* Nav: se a página atual registrou sub-navegação, a árvore de sub-abas
          dela aparece aqui em cima — sempre seguida da lista de módulos
          completa logo abaixo, nunca no lugar dela, para nunca "prender" a
          navegação dentro de uma página. As duas listas rolam de forma
          independente (cada uma no seu próprio container com overflow), para
          que abrir um grupo grande de sub-abas não empurre/role o menu
          principal junto. */}
      <nav className="flex-1 flex flex-col" style={{ minHeight: 0 }}>
        {subNav && (
          <div className="p-3" style={{ background: "var(--sidebar-subnav-bg)", maxHeight: "55%", overflowY: "auto", flexShrink: 0, borderBottom: "4px double var(--sidebar-border)" }}>
            {totalFolhasSubNav > 6 && (
              <div style={{ position: "relative", marginBottom: "0.5rem" }}>
                <Search size={12} style={{ position: "absolute", left: 7, top: 7, color: "var(--sidebar-muted)", pointerEvents: "none" }} />
                <input
                  value={buscaSubNav}
                  onChange={(e) => setBuscaSubNav(e.target.value)}
                  placeholder="Buscar sub-aba…"
                  title="Digite parte do nome para pular direto a uma sub-aba, sem abrir grupo por grupo"
                  style={{
                    width: "100%", boxSizing: "border-box", padding: "0.3rem 0.5rem 0.3rem 1.6rem", fontSize: "10px",
                    borderRadius: "6px", border: "1px solid var(--sidebar-border)",
                    background: "var(--sidebar-bg)", color: "var(--sidebar-fg)",
                  }}
                />
              </div>
            )}
            {resultadosBuscaSubNav ? (
              <div className="space-y-1">
                {resultadosBuscaSubNav.length === 0 && (
                  <p style={{ fontSize: "10px", color: "var(--sidebar-muted)", padding: "0.3rem 0.2rem" }}>Nenhuma sub-aba encontrada.</p>
                )}
                {resultadosBuscaSubNav.map((f) => {
                  const Icon = f.icon;
                  const ativo = f.id === subNav.activeId;
                  return (
                    <button key={f.id} onClick={() => { subNav.onSelect(f.id); setBuscaSubNav(""); }}
                      title={f.caminho ? `${f.caminho} › ${f.label}` : f.label}
                      style={{
                        width: "100%", display: "flex", alignItems: "center", gap: "0.5rem", textAlign: "left", cursor: "pointer",
                        padding: "0.4rem 0.6rem", borderRadius: "8px",
                        border: "1px solid " + (ativo ? "var(--sidebar-active-border)" : "transparent"),
                        background: ativo ? "var(--sidebar-active-bg)" : "transparent",
                        color: ativo ? "var(--sidebar-active-fg)" : "var(--sidebar-subnav-muted, var(--sidebar-muted))",
                        fontSize: "10px", fontWeight: ativo ? 700 : 500,
                      }}>
                      <Icon size={13} />
                      <span>
                        {f.label}
                        {f.caminho && <span style={{ display: "block", fontSize: "9px", fontWeight: 400, opacity: 0.7 }}>{f.caminho}</span>}
                      </span>
                    </button>
                  );
                })}
              </div>
            ) : (
              <SubNavTree nodes={subNav.tree} activeId={subNav.activeId} onSelect={subNav.onSelect}
                raiz={subNav.tree} pathname={path} paginaLabel={rotuloDaPagina(path)} />
            )}
          </div>
        )}
        <div className="flex-1 p-3 space-y-1" style={{ overflowY: "auto", minHeight: 0 }}>
          {(() => {
            const todos = [...visiveis,
              ...(dono ? [{ href: "/usuarios", label: "Controle de Acesso", icon: Users, title: "Controle de Acesso — restrito ao proprietário: cadastrar usuários e definir os módulos que cada um pode ver", grupo: "Administração" }] : []),
              ...(dono ? [{ href: "/painel-cowdata", label: "Painel CowData", icon: Building2, title: "Painel CowData — administração da empresa de software (assinaturas, financeiro, equipe), separado dos dados da fazenda", grupo: "Administração" }] : []),
              ...(dono ? [{ href: "/contador", label: "Painel do Contador", icon: FileBarChart, title: "Visão do proprietário sobre o Painel do Contador — a mesma tela que o contador externo vê (Financeiro somente leitura, arquivo fiscal-contábil)", grupo: "Administração" }] : []),
              { href: "/portal", label: "Portal", icon: MessageSquare, title: "Portal — comunicação interna: mensagens, e-mails e tarefas delegadas", grupo: "Administração" },
              { href: "/consultor", label: "Consultor", icon: Briefcase, title: "Área do consultor — fazendas gerenciadas por planilha e modo Simulação", grupo: "Administração" },
              ...(temConfiguracoes ? [{ href: "/configuracoes", label: "Configurações", icon: Settings, title: "Configurações — cadastros e parâmetros da fazenda", grupo: "Administração" }] : []),
            ];
            return GRUPOS.map((grupo, i) => {
              const itens = todos.filter((l) => l.grupo === grupo);
              if (!itens.length) return null;
              return (
                <div key={grupo}>
                  <p style={{
                    fontSize: "10px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em",
                    color: "var(--sidebar-muted)", margin: i === 0 ? "0 0 0.3rem 0.6rem" : "0.7rem 0 0.3rem 0.6rem",
                  }}>
                    {grupo}
                  </p>
                  {itens.map(({ href, label, icon: Icon, title }) => {
                    const active = path === href || (href !== "/" && path.startsWith(href));
                    return (
                      <SidebarLink key={href} href={href} title={title} label={label} active={active}>
                        <Icon size={16} />
                        {label}
                      </SidebarLink>
                    );
                  })}
                </div>
              );
            });
          })()}
        </div>
      </nav>

      {/* Footer */}
      <div
        className="p-2 border-t text-center"
        style={{ borderColor: "var(--sidebar-border)", fontSize: "0.65rem", color: "var(--sidebar-muted)" }}
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
          {statusLabel}
        </div>
        <UsuarioLogado />
        <p className="mt-0.5">v1.0.0 · Sprint 1</p>
      </div>
      </aside>
    </>
  );
}

// Folha mais à esquerda de um nó (usado ao clicar num grupo/sub-grupo: entra
// direto na primeira folha em vez de exigir mais um clique).
function primeiraFolha(node: SubNavNode): string {
  if (!node.children || !node.children.length) return node.id;
  return primeiraFolha(node.children[0]);
}

// Caminho (ids) da raiz até o nó ativo — usado para saber quais grupos/
// sub-grupos ao longo do caminho devem aparecer expandidos.
function caminhoAte(nodes: SubNavNode[], alvoId: string): string[] | null {
  for (const n of nodes) {
    if (n.id === alvoId) return [n.id];
    if (n.children) {
      const sub = caminhoAte(n.children, alvoId);
      if (sub) return [n.id, ...sub];
    }
  }
  return null;
}

// Mesma travessia que caminhoAte, mas devolve os rótulos (não os ids) — usado
// para nomear a aba nova aberta em duplo clique numa sub-aba.
export function caminhoLabels(nodes: SubNavNode[], alvoId: string): string[] | null {
  for (const n of nodes) {
    if (n.id === alvoId) return [n.label];
    if (n.children) {
      const sub = caminhoLabels(n.children, alvoId);
      if (sub) return [n.label, ...sub];
    }
  }
  return null;
}

// Lista achatada de folhas (id + rótulo + caminho de grupos até ela) — usada
// pela busca da sub-navegação para pular direto numa sub-aba, sem precisar
// abrir grupo por grupo em árvores fundas (ex.: Financeiro, Lançamentos).
function achatarFolhas(nodes: SubNavNode[], caminho: string[] = []): { id: string; label: string; caminho: string; icon: any }[] {
  return nodes.flatMap((n) =>
    n.children?.length
      ? achatarFolhas(n.children, [...caminho, n.label])
      : [{ id: n.id, label: n.label, caminho: caminho.join(" › "), icon: n.icon }]
  );
}
function contarFolhas(nodes: SubNavNode[]): number {
  return nodes.reduce((acc, n) => acc + (n.children?.length ? contarFolhas(n.children) : 1), 0);
}
// Comparação sem acento/maiúscula — "recebi" acha "Recebidas", "a pagar" etc.
const normalizarBusca = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

// Árvore de sub-navegação genérica (N níveis) — usada pela Sidebar no lugar
// da lista de módulos quando a página atual registra uma (piloto: Lançamentos).
function SubNavTree({ nodes, activeId, onSelect, raiz, pathname, paginaLabel, depth = 0 }: {
  nodes: SubNavNode[]; activeId: string; onSelect: (id: string) => void;
  raiz: SubNavNode[]; pathname: string; paginaLabel: string; depth?: number;
}) {
  const caminho = new Set(caminhoAte(nodes, activeId) ?? []);
  return (
    <div className="space-y-1" style={depth ? { paddingLeft: `${depth * 1.1}rem`, marginTop: "0.2rem" } : undefined}>
      {nodes.map((n) => {
        const temFilhos = !!n.children?.length;
        const ativo = temFilhos ? caminho.has(n.id) : n.id === activeId;
        // Item raiz atualmente aberto/ativo — destaca com uma moldura para
        // deixar claro qual sub-menu está aberto. Vale tanto para grupos com
        // filhos expandidos (ex.: Sanidade > Curativa) quanto para árvores
        // sem aninhamento (ex.: Alimentação), onde a folha ativa é o próprio
        // item raiz.
        const grupoAberto = depth === 0 && ativo;
        return (
          <div key={n.id}
            style={grupoAberto ? {
              border: "1.5px solid var(--sidebar-subnav-outline)", borderRadius: "10px",
              padding: "0.3rem", background: "var(--sidebar-subnav-outline-bg)",
            } : undefined}>
            <SubNavItem node={n} depth={depth} ativo={ativo} temFilhos={temFilhos} activeId={activeId}
              onSelect={onSelect} raiz={raiz} pathname={pathname} paginaLabel={paginaLabel} />
            {temFilhos && ativo && (
              <SubNavTree nodes={n.children!} activeId={activeId} onSelect={onSelect}
                raiz={raiz} pathname={pathname} paginaLabel={paginaLabel} depth={depth + 1} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// Um item da sub-navegação: clique simples troca de sub-aba dentro da página
// atual (como sempre); duplo clique abre a mesma sub-aba numa aba nova (ver
// TabsShell/abrirNovaAba), já direto no lugar certo via "?sub=" na URL.
function SubNavItem({ node, depth, ativo, temFilhos, activeId, onSelect, raiz, pathname, paginaLabel }: {
  node: SubNavNode; depth: number; ativo: boolean; temFilhos: boolean; activeId: string; onSelect: (id: string) => void;
  raiz: SubNavNode[]; pathname: string; paginaLabel: string;
}) {
  const Icon = node.icon;
  const aoClicar = useCliqueOuDuploClique(
    () => onSelect(temFilhos ? (ativo ? activeId : primeiraFolha(node)) : node.id),
    () => {
      const folhaAlvo = temFilhos ? primeiraFolha(node) : node.id;
      const labels = caminhoLabels(raiz, folhaAlvo) ?? [node.label];
      const params = new URLSearchParams();
      params.set("sub", folhaAlvo);
      abrirNovaAba(`${pathname}?${params.toString()}`, [paginaLabel, ...labels].join(" › "));
    },
  );
  return (
    <button onClick={aoClicar}
      style={{
        width: "100%", display: "flex", alignItems: "center", gap: depth ? "0.5rem" : "0.6rem",
        padding: depth ? "0.4rem 0.6rem" : "0.55rem 0.7rem", borderRadius: "8px", cursor: "pointer", textAlign: "left",
        border: "1px solid " + (ativo ? "var(--sidebar-active-border)" : "transparent"),
        background: ativo ? "var(--sidebar-active-bg)" : "transparent",
        color: ativo ? "var(--sidebar-active-fg)" : "var(--sidebar-subnav-muted, var(--sidebar-muted))",
        fontSize: "10px", fontWeight: ativo ? 700 : 500,
      }}>
      <Icon size={depth ? 13 : 16} /> {node.label}
    </button>
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
        style={{ background: "none", border: "1px solid var(--sidebar-border)", borderRadius: "6px", padding: "0.2rem 0.55rem", color: "var(--sidebar-muted)", cursor: "pointer" }}>
        <LogOut size={12} /> Sair / trocar de usuário
      </button>
    </div>
  );
}
