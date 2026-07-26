"use client";
import { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

// Navegação em drill-down, usada por várias páginas (Lançamentos, Rebanho,
// Reprodução, Sanidade, Financeiro, Recria, Relatórios, Alimentação,
// Configurações…): cada página registra sua árvore de sub-abas aqui, e é a
// barra lateral (Sidebar) — não o conteúdo — quem desenha os níveis de
// navegação, substituindo a lista de módulos enquanto a página estiver
// montada. `tree`/`onSelect` devem ser memoizados pelo chamador
// (useMemo/useCallback) para não reabrir o registro a cada render.
export type SubNavNode = { id: string; label: string; icon: any; children?: SubNavNode[] };
export type SubNavValue = { tree: SubNavNode[]; activeId: string; onSelect: (id: string) => void } | null;

const SubNavContext = createContext<{ subNav: SubNavValue; setSubNav: (v: SubNavValue) => void } | null>(null);

export function SubNavProvider({ children }: { children: ReactNode }) {
  const [subNav, setSubNav] = useState<SubNavValue>(null);
  return <SubNavContext.Provider value={{ subNav, setSubNav }}>{children}</SubNavContext.Provider>;
}

function existeId(nodes: SubNavNode[], id: string): boolean {
  return nodes.some((n) => n.id === id || (n.children && existeId(n.children, id)));
}

// Chamado pela página dona da sub-navegação (ex.: Lançamentos). Some com o
// registro (volta a lista de módulos) quando a página desmontar.
//
// Também mantém "?sub=" na URL da própria página em sincronia com a seleção
// atual — é o que permite que um duplo clique na Sidebar (ver SubNavTree)
// abra uma aba nova já direto na sub-aba certa: a aba nova chega com
// "?sub=<id>" e, ao montar, esta função aplica essa seleção uma única vez.
// Usa window.location direto (em vez de useSearchParams) para não exigir que
// as ~13 páginas que chamam este hook fiquem dentro de <Suspense>.
export function useSubNavRegister(value: SubNavValue) {
  const ctx = useContext(SubNavContext);
  const pathname = usePathname();
  const router = useRouter();
  const aplicouParamInicial = useRef(false);

  useEffect(() => {
    if (aplicouParamInicial.current || !value) return;
    aplicouParamInicial.current = true;
    const sub = new URLSearchParams(window.location.search).get("sub");
    if (sub && sub !== value.activeId && existeId(value.tree, sub)) value.onSelect(sub);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!value]);

  useEffect(() => {
    if (!value) return;
    const atual = new URLSearchParams(window.location.search);
    if (atual.get("sub") === value.activeId) return;
    atual.set("sub", value.activeId);
    router.replace(`${pathname}?${atual.toString()}`, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value?.activeId]);

  useEffect(() => {
    ctx?.setSubNav(value);
    return () => ctx?.setSubNav(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
}

export function useSubNav(): SubNavValue {
  return useContext(SubNavContext)?.subNav ?? null;
}
