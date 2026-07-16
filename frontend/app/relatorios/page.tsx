"use client";
import { useMemo, useState } from "react";
import { ClipboardList, Combine } from "lucide-react";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import RelatoriosManejo from "@/components/RelatoriosManejo";
import CombinadorListas from "@/components/CombinadorListas";

// Os gráficos gerenciais (antiga sub-aba "Relatórios gerenciais") foram
// transferidos para Indicadores > Relatórios gerenciais. Aqui ficam as listas
// de trabalho do dia a dia e as Listas Gerenciais (BST + combinador).
type Aba = "trabalho" | "gerenciais";
const ABAS = [
  { id: "trabalho" as const, label: "Listas de trabalho", icon: ClipboardList },
  { id: "gerenciais" as const, label: "Listas Gerenciais", icon: Combine },
];

export default function RelatoriosPage() {
  const [aba, setAba] = useState<Aba>("trabalho");
  const subNavTree: SubNavNode[] = useMemo(() => ABAS.map((a) => ({ id: a.id, label: a.label, icon: a.icon })), []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: aba, onSelect: (id: string) => setAba(id as Aba) }), [subNavTree, aba]));

  return aba === "gerenciais" ? <CombinadorListas /> : <RelatoriosManejo />;
}
