"use client";
// Árvore de sub-navegação genérica (N níveis) — reusada em dois lugares:
// (1) barra de abas horizontais no topo do conteúdo (ver SubNavTabs.tsx), e
// (2) o rail esquerdo do portal "Insights e Administração" (ver
// components/insights/InsightsLayout.tsx), que mantém o modelo antigo de
// árvore vertical por pedido explícito do usuário para diferenciar
// visualmente aquele portal do resto do site.
import { ChevronDown, ChevronUp } from "lucide-react";
import { useCliqueOuDuploClique, abrirNovaAba } from "@/lib/tabs";
import type { SubNavNode } from "@/components/SubNavContext";

// Folha mais à esquerda de um nó (usado ao clicar num grupo/sub-grupo: entra
// direto na primeira folha em vez de exigir mais um clique).
export function primeiraFolha(node: SubNavNode): string {
  if (!node.children || !node.children.length) return node.id;
  return primeiraFolha(node.children[0]);
}

// Caminho (ids) da raiz até o nó ativo — usado para saber quais grupos/
// sub-grupos ao longo do caminho devem aparecer expandidos.
export function caminhoAte(nodes: SubNavNode[], alvoId: string): string[] | null {
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
export function achatarFolhas(nodes: SubNavNode[], caminho: string[] = []): { id: string; label: string; caminho: string; icon: any }[] {
  return nodes.flatMap((n) =>
    n.children?.length
      ? achatarFolhas(n.children, [...caminho, n.label])
      : [{ id: n.id, label: n.label, caminho: caminho.join(" › "), icon: n.icon }]
  );
}
export function contarFolhas(nodes: SubNavNode[]): number {
  return nodes.reduce((acc, n) => acc + (n.children?.length ? contarFolhas(n.children) : 1), 0);
}
// Comparação sem acento/maiúscula — "recebi" acha "Recebidas", "a pagar" etc.
export const normalizarBusca = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

// Árvore de sub-navegação genérica (N níveis) — usada pelo rail esquerdo do
// portal "Insights e Administração" (ver components/insights/InsightsLayout.tsx).
export function SubNavTree({ nodes, activeId, onSelect, raiz, pathname, paginaLabel, depth = 0, recolhidos, onToggleRecolhido }: {
  nodes: SubNavNode[]; activeId: string; onSelect: (id: string) => void;
  raiz: SubNavNode[]; pathname: string; paginaLabel: string; depth?: number;
  recolhidos: Set<string>; onToggleRecolhido: (id: string) => void;
}) {
  const caminho = new Set(caminhoAte(nodes, activeId) ?? []);
  return (
    <div className="space-y-1" style={depth ? { paddingLeft: `${depth * 1.1}rem`, marginTop: "0.2rem" } : undefined}>
      {nodes.map((n) => {
        const temFilhos = !!n.children?.length;
        const ativo = temFilhos ? caminho.has(n.id) : n.id === activeId;
        // Submenu recolhido manualmente (seta discreta ao lado do título) —
        // some com os itens do submenu, mas mantém o título e a seleção
        // atual intactos; independente dos demais submenus.
        const recolhidoManualmente = temFilhos && recolhidos.has(n.id);
        // Item raiz atualmente aberto/ativo — destaca com uma moldura para
        // deixar claro qual sub-menu está aberto. Vale tanto para grupos com
        // filhos expandidos (ex.: Sanidade > Curativa) quanto para árvores
        // sem aninhamento (ex.: Alimentação), onde a folha ativa é o próprio
        // item raiz.
        const grupoAberto = depth === 0 && ativo;
        return (
          <div key={n.id}
            style={grupoAberto ? {
              border: "1.5px solid var(--sidebar-subnav-outline)", borderRadius: "var(--r-sm)",
              padding: "0.3rem", background: "var(--sidebar-subnav-outline-bg)",
            } : undefined}>
            <SubNavItem node={n} depth={depth} ativo={ativo} temFilhos={temFilhos} activeId={activeId}
              onSelect={onSelect} raiz={raiz} pathname={pathname} paginaLabel={paginaLabel}
              recolhido={recolhidoManualmente} onToggleRecolhido={() => onToggleRecolhido(n.id)} />
            {temFilhos && ativo && !recolhidoManualmente && (
              <SubNavTree nodes={n.children!} activeId={activeId} onSelect={onSelect}
                raiz={raiz} pathname={pathname} paginaLabel={paginaLabel} depth={depth + 1}
                recolhidos={recolhidos} onToggleRecolhido={onToggleRecolhido} />
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
function SubNavItem({ node, depth, ativo, temFilhos, activeId, onSelect, raiz, pathname, paginaLabel, recolhido, onToggleRecolhido }: {
  node: SubNavNode; depth: number; ativo: boolean; temFilhos: boolean; activeId: string; onSelect: (id: string) => void;
  raiz: SubNavNode[]; pathname: string; paginaLabel: string; recolhido: boolean; onToggleRecolhido: () => void;
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
  // A seta de recolher/expandir só faz sentido enquanto o submenu está
  // aberto (ativo) e tem itens — clicar nela some/mostra só os itens dele,
  // sem navegar e sem afetar outros submenus.
  const mostrarSeta = temFilhos && ativo;
  return (
    <div style={{ display: "flex", alignItems: "stretch", gap: "2px" }}>
      <button onClick={aoClicar}
        style={{
          flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: depth ? "0.5rem" : "0.6rem",
          padding: depth ? "0.4rem 0.6rem" : "0.55rem 0.7rem", borderRadius: "var(--r-sm)", cursor: "pointer", textAlign: "left",
          border: "1px solid " + (ativo ? "var(--sidebar-active-border)" : "transparent"),
          background: ativo ? "var(--sidebar-active-bg)" : "transparent",
          color: ativo ? "var(--sidebar-active-fg)" : "var(--sidebar-subnav-muted, var(--sidebar-muted))",
          fontSize: "10px", fontWeight: ativo ? 700 : 500,
        }}>
        <Icon size={depth ? 13 : 16} /> {node.label}
      </button>
      {mostrarSeta && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onToggleRecolhido(); }}
          aria-label={recolhido ? "Expandir sub-menu" : "Recolher sub-menu"}
          title={recolhido ? "Expandir sub-menu" : "Recolher sub-menu"}
          style={{
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
            width: "1.3rem", background: "none", border: "none", borderRadius: "var(--r-sm)",
            color: "var(--sidebar-muted)", opacity: 0.55, cursor: "pointer",
          }}
        >
          {recolhido ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
        </button>
      )}
    </div>
  );
}
