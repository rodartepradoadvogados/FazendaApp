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
  Beef,
  LineChart,
  Milk,
  Wheat,
  Syringe,
  Settings,
  ClipboardList,
  FileBarChart,
  CheckCheck,
  Baby,
  Menu,
  X,
} from "lucide-react";
import { checkHealth, getUsuario, logout, podeModulo, ehAdmin, ROTA_MODULO } from "@/lib/api";
import { LogOut, UserCircle } from "lucide-react";
import { BullLogo } from "@/components/BullLogo";
import { useSubNav, type SubNavNode } from "@/components/SubNavContext";

// Ordem por fluxo de gestão: (1) ciclo diário — panorama, o que fazer e
// registrar; (2) áreas de manejo do rebanho; (3) análise e administração;
// (4) Configurações fica sempre por último (acrescentada dinamicamente).
const links = [
  // ── Ciclo diário ──
  { href: "/",            label: "Capa",        icon: Home,          title: "Capa — visão geral da fazenda" },
  { href: "/agenda",      label: "Agenda",       icon: Calendar,      title: "Agenda de atividades do dia — pendências e eventos a cumprir" },
  { href: "/lancamentos", label: "Lançamentos",  icon: ClipboardList, title: "Lançamentos — registrar eventos e dados do dia a dia" },
  // ── Manejo do rebanho ──
  { href: "/rebanho",     label: "Rebanho",      icon: Beef,          title: "Rebanho — animais, movimentações entre lotes e ficha do animal" },
  { href: "/reproducao",  label: "Reprodução",   icon: Heart,         title: "Reprodução — serviços, diagnósticos e análise reprodutiva" },
  { href: "/producao",    label: "Produção",     icon: Milk,          title: "Produção — controle leiteiro, secagem e qualidade do leite" },
  { href: "/sanidade",    label: "Sanidade",     icon: Syringe,       title: "Sanidade — aplicações, protocolos e calendário sanitário" },
  { href: "/alimentacao", label: "Alimentação",  icon: Wheat,         title: "Alimentação — dieta, consumo e necessidade por lote" },
  { href: "/recria",      label: "Recria",       icon: Baby,          title: "Recria — Dossiê Zootécnico de bezerras e novilhas: saúde por idade, ponto crítico e crescimento" },
  // ── Análise e administração ──
  { href: "/indicadores", label: "Indicadores",  icon: LineChart,     title: "Indicadores — KPIs e desempenho reprodutivo, produtivo e financeiro" },
  { href: "/relatorios",  label: "Listas",       icon: FileBarChart,  title: "Listas de trabalho — o que fazer hoje com cada animal (PEV, a inseminar, toque, secagem, partos, sêmen)" },
  { href: "/financeiro",  label: "Financeiro",   icon: BarChart3,     title: "Financeiro — contas a pagar/receber, folha e indicadores" },
  { href: "/estoque",     label: "Estoque",      icon: Package,       title: "Estoque de insumos — quantidades, valores e itens abaixo do mínimo" },
];

export function Sidebar() {
  const path = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);
  const [aberto, setAberto] = useState(false); // drawer no mobile
  const [visiveis, setVisiveis] = useState(links);
  const [admin, setAdmin] = useState(false);

  const [temConfiguracoes, setTemConfiguracoes] = useState(false);

  // Drill-down: quando a página registra sua árvore de sub-abas, a barra
  // mostra essa árvore ACIMA da lista de módulos (nunca no lugar dela) — assim
  // dá pra navegar dentro da página atual sem nunca perder acesso direto às
  // outras abas do menu principal.
  const subNav = useSubNav();

  useEffect(() => {
    // Filtra o menu conforme as permissões do usuário logado.
    setVisiveis(links.filter((l) => podeModulo(ROTA_MODULO[l.href] || l.href)));
    setAdmin(ehAdmin());
    setTemConfiguracoes(podeModulo("parametros") || podeModulo("upload") || ehAdmin());
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
          têm overflow-x: hidden (que vira scroll-container e quebra o sticky). */}
      <div className="md:hidden flex items-center gap-3 px-4 fixed top-0 left-0 right-0 z-30"
        style={{ height: "3.25rem", background: "var(--sidebar-bg)", borderBottom: "1px solid var(--sidebar-border)" }}>
        <button onClick={() => setAberto(true)} aria-label="Abrir menu" title="Abrir o menu de navegação"
          style={{ background: "none", border: "none", color: "var(--sidebar-fg)", cursor: "pointer", display: "flex" }}>
          <Menu size={22} />
        </button>
        <BullLogo size={18} />
        <span style={{ color: "var(--sidebar-logo-fg)", fontSize: "0.8rem", fontWeight: 800, letterSpacing: "0.05em" }}>FAZENDA</span>
        <span style={{ color: "var(--sidebar-muted)", fontSize: "0.7rem" }}>· Jairo Nasser</span>
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
        <div
          className="flex items-center gap-2 px-2 py-2 rounded-lg"
          style={{ background: "var(--sidebar-logo-bg)" }}
        >
          <BullLogo size={22} />
          <div>
            <p style={{ color: "var(--sidebar-logo-fg)", fontSize: "0.7rem", fontWeight: 800, letterSpacing: "0.05em", lineHeight: 1.2 }}>
              FAZENDA
            </p>
            <p style={{ color: "var(--sidebar-logo-sub)", fontSize: "0.6rem", lineHeight: 1.2 }}>
              Jairo Nasser
            </p>
          </div>
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
          <div className="p-3" style={{ maxHeight: "55%", overflowY: "auto", flexShrink: 0, borderBottom: "1px solid var(--sidebar-border)" }}>
            <SubNavTree nodes={subNav.tree} activeId={subNav.activeId} onSelect={subNav.onSelect} />
          </div>
        )}
        <div className="flex-1 p-3 space-y-1" style={{ overflowY: "auto", minHeight: 0 }}>
          {[...visiveis,
            ...(admin ? [{ href: "/aprovacoes", label: "Aprovações", icon: CheckCheck, title: "Aprovar lançamentos de campo enviados pelo Telegram" }] : []),
            ...(temConfiguracoes ? [{ href: "/configuracoes", label: "Configurações", icon: Settings, title: "Configurações — cadastros e parâmetros da fazenda" }] : []),
          ].map(({ href, label, icon: Icon, title }) => {
            const active = path === href || (href !== "/" && path.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                title={title || label}
                className="flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150"
                style={{
                  background: active ? "var(--sidebar-active-bg)" : "transparent",
                  color: active ? "var(--sidebar-active-fg)" : "var(--sidebar-muted)",
                  borderLeft: active ? "3px solid var(--sidebar-active-border)" : "3px solid transparent",
                  fontSize: "10px",
                }}
              >
                <Icon size={16} />
                {label}
              </Link>
            );
          })}
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

// Árvore de sub-navegação genérica (N níveis) — usada pela Sidebar no lugar
// da lista de módulos quando a página atual registra uma (piloto: Lançamentos).
function SubNavTree({ nodes, activeId, onSelect, depth = 0 }: {
  nodes: SubNavNode[]; activeId: string; onSelect: (id: string) => void; depth?: number;
}) {
  const caminho = new Set(caminhoAte(nodes, activeId) ?? []);
  return (
    <div className="space-y-1" style={depth ? { paddingLeft: `${depth * 1.1}rem`, marginTop: "0.2rem" } : undefined}>
      {nodes.map((n) => {
        const Icon = n.icon;
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
            <button onClick={() => onSelect(temFilhos ? (ativo ? activeId : primeiraFolha(n)) : n.id)}
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: depth ? "0.5rem" : "0.6rem",
                padding: depth ? "0.4rem 0.6rem" : "0.55rem 0.7rem", borderRadius: "8px", cursor: "pointer", textAlign: "left",
                border: "1px solid " + (ativo ? "var(--sidebar-active-border)" : "transparent"),
                background: ativo ? "var(--sidebar-active-bg)" : "transparent",
                color: ativo ? "var(--sidebar-active-fg)" : "var(--sidebar-muted)",
                fontSize: "10px", fontWeight: ativo ? 700 : 500,
              }}>
              <Icon size={depth ? 13 : 16} /> {n.label}
            </button>
            {temFilhos && ativo && (
              <SubNavTree nodes={n.children!} activeId={activeId} onSelect={onSelect} depth={depth + 1} />
            )}
          </div>
        );
      })}
    </div>
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
