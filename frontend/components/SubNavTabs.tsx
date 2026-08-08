"use client";
// Barra de abas horizontais no TOPO da área de conteúdo, mostrando a árvore
// de sub-navegação da página atual (ver useSubNavRegister/SubNavContext) —
// substitui o antigo bloco de sub-nav que ficava dentro da Sidebar esquerda.
// Uma linha por nível ao longo do caminho ativo: a linha 0 é sempre a raiz
// da árvore (nível de módulo/grupo); cada linha seguinte mostra os irmãos do
// nó ativo daquele nível, enquanto houver filhos no caminho — cobre árvores
// de 2 a 4 níveis (Financeiro, Lançamentos etc.) de forma genérica, sem
// precisar saber a profundidade de antemão.
//
// Não implementa busca nem recolhimento manual de submenu — descontinuados
// neste modelo (a árvore inteira cabe no topo, com rolagem horizontal por
// linha quando necessário).
import { usePathname } from "next/navigation";
import { useSubNav } from "@/components/SubNavContext";
import { useCliqueOuDuploClique, abrirNovaAba } from "@/lib/tabs";
import { caminhoAte, caminhoLabels, primeiraFolha } from "@/components/SubNavTree";
import { rotuloDaPagina } from "@/components/Sidebar";
import type { SubNavNode } from "@/components/SubNavContext";

export function SubNavTabs() {
  const subNav = useSubNav();
  const pathname = usePathname();
  if (!subNav) return null;

  const caminho = caminhoAte(subNav.tree, subNav.activeId) ?? [];

  // Monta as linhas: linha 0 = raiz; linha k = filhos do nó caminho[k-1],
  // enquanto esse nó existir no caminho e tiver filhos.
  const linhas: SubNavNode[][] = [subNav.tree];
  for (let k = 0; k < caminho.length; k++) {
    const atual = linhas[k].find((n) => n.id === caminho[k]);
    if (atual?.children?.length) linhas.push(atual.children);
    else break;
  }

  return (
    <nav className="md:pr-52" style={{ position: "sticky", top: 0, zIndex: 5, background: "var(--surface)", borderBottom: "1px solid var(--border)", padding: "0 1.5rem" }}>
      {linhas.map((nos, i) => (
        <SubNavTabsLinha key={i} nos={nos} primaria={i === 0}
          subNav={subNav} pathname={pathname} caminho={caminho} />
      ))}
    </nav>
  );
}

function SubNavTabsLinha({ nos, primaria, subNav, pathname, caminho }: {
  nos: SubNavNode[]; primaria: boolean;
  subNav: { tree: SubNavNode[]; activeId: string; onSelect: (id: string) => void };
  pathname: string; caminho: string[];
}) {
  return (
    <div
      style={{
        display: "flex", gap: primaria ? "0.15rem" : "0.15rem", overflowX: "auto", whiteSpace: "nowrap",
        background: primaria ? undefined : "var(--surface-2)",
        borderTop: primaria ? undefined : "1px solid var(--border)",
      }}
    >
      {nos.map((n) => (
        <SubNavTabButton key={n.id} node={n} primaria={primaria}
          ativo={caminho.includes(n.id)} subNav={subNav} pathname={pathname} />
      ))}
    </div>
  );
}

function SubNavTabButton({ node, primaria, ativo, subNav, pathname }: {
  node: SubNavNode; primaria: boolean; ativo: boolean;
  subNav: { tree: SubNavNode[]; activeId: string; onSelect: (id: string) => void };
  pathname: string;
}) {
  const temFilhos = !!node.children?.length;
  const Icon = node.icon;
  const aoClicar = useCliqueOuDuploClique(
    () => subNav.onSelect(temFilhos ? (ativo ? subNav.activeId : primeiraFolha(node)) : node.id),
    () => {
      const folhaAlvo = temFilhos ? primeiraFolha(node) : node.id;
      const labels = caminhoLabels(subNav.tree, folhaAlvo) ?? [node.label];
      abrirNovaAba(`${pathname}?sub=${folhaAlvo}`, [rotuloDaPagina(pathname), ...labels].join(" › "));
    },
  );

  return (
    <button
      type="button"
      onClick={aoClicar}
      title={node.label}
      style={{
        fontFamily: "var(--font-heading)",
        fontSize: primaria ? "0.72rem" : "0.66rem",
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: primaria ? "0.07em" : "0.05em",
        padding: primaria ? "0.7rem 0.9rem" : "0.45rem 0.75rem",
        background: "none",
        border: "none",
        borderBottom: ativo ? `2px solid var(${primaria ? "--dourado" : "--dourado-light"})` : "2px solid transparent",
        cursor: "pointer",
        color: ativo ? (primaria ? "var(--vinho)" : "var(--text)") : "var(--text-muted)",
        display: "flex",
        alignItems: "center",
        gap: primaria ? undefined : "0.35rem",
      }}
    >
      {!primaria && <Icon size={12} />}
      {node.label}
    </button>
  );
}
