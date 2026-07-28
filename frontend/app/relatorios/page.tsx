"use client";
import { useEffect, useMemo, useState } from "react";
import { ClipboardList, Combine, Stethoscope } from "lucide-react";
import { podeModulo } from "@/lib/api";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import RelatoriosManejo from "@/components/RelatoriosManejo";
import CombinadorListas from "@/components/CombinadorListas";
import AgendaVeterinarioPage from "@/app/reproducao/AgendaVeterinario";

// Os gráficos gerenciais (antiga sub-aba "Relatórios gerenciais") foram
// transferidos para Indicadores > Indicadores Gerais. A Análise reprodutiva e
// o Relatório personalizado migraram para a aba Relatórios (ver
// frontend/app/analise-relatorios/page.tsx). Aqui ficam as listas de
// trabalho do dia a dia, as Listas Gerenciais (BST + combinador), e — na
// permissão "vet" — a Agenda Reprodutiva.
type Aba = "trabalho" | "gerenciais" | "vet";

export default function RelatoriosPage() {
  const [aba, setAba] = useState<Aba>("trabalho");
  const [temVet, setTemVet] = useState(false);
  // Cada usuário logado tem suas próprias permissões — reavalia sempre que a
  // página monta (evita mostrar abas de uma sessão anterior de outro usuário).
  useEffect(() => { setTemVet(podeModulo("vet")); }, []);

  const ABAS = useMemo(() => [
    { id: "trabalho" as const, label: "Listas de trabalho", icon: ClipboardList },
    { id: "gerenciais" as const, label: "Listas Gerenciais", icon: Combine },
    ...(temVet ? [{ id: "vet" as const, label: "Agenda Reprodutiva", icon: Stethoscope }] : []),
  ], [temVet]);
  const abaAtiva = ABAS.some((a) => a.id === aba) ? aba : "trabalho";

  const subNavTree: SubNavNode[] = useMemo(() => ABAS.map((a) => ({ id: a.id, label: a.label, icon: a.icon })), [ABAS]);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: abaAtiva, onSelect: (id: string) => setAba(id as Aba) }), [subNavTree, abaAtiva]));

  return abaAtiva === "gerenciais" ? <CombinadorListas />
    : abaAtiva === "vet" ? <div className="px-6 pt-6"><AgendaVeterinarioPage /></div>
    : <RelatoriosManejo />;
}
