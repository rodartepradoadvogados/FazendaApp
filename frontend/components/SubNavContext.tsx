"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

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

// Chamado pela página dona da sub-navegação (ex.: Lançamentos). Some com o
// registro (volta a lista de módulos) quando a página desmontar.
export function useSubNavRegister(value: SubNavValue) {
  const ctx = useContext(SubNavContext);
  useEffect(() => {
    ctx?.setSubNav(value);
    return () => ctx?.setSubNav(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
}

export function useSubNav(): SubNavValue {
  return useContext(SubNavContext)?.subNav ?? null;
}
