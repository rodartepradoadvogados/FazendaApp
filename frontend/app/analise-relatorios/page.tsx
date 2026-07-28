"use client";
import { useEffect, useMemo, useState } from "react";
import { HeartPulse, Sparkles } from "lucide-react";
import { podeModulo } from "@/lib/api";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import AnaliseReprodutivaPage from "@/app/analise-reprodutiva/page";
import RelatorioPersonalizado from "@/components/RelatorioPersonalizado";

// Análise reprodutiva (antes em Listas) e Relatório personalizado (antes em
// Indicadores) moraram em outros lugares — migraram para cá porque, na
// prática, são os dois relatórios de verdade do sistema.
type Aba = "analise" | "personalizado";

export default function AnaliseRelatoriosPage() {
  const [temAnalise, setTemAnalise] = useState(false);
  const [aba, setAba] = useState<Aba>("analise");
  useEffect(() => { setTemAnalise(podeModulo("analise")); }, []);

  const ABAS = useMemo(() => [
    ...(temAnalise ? [{ id: "analise" as const, label: "Análise reprodutiva", icon: HeartPulse }] : []),
    { id: "personalizado" as const, label: "Relatório personalizado", icon: Sparkles },
  ], [temAnalise]);
  const abaAtiva = ABAS.some((a) => a.id === aba) ? aba : ABAS[0]?.id;

  const subNavTree: SubNavNode[] = useMemo(() => ABAS.map((a) => ({ id: a.id, label: a.label, icon: a.icon })), [ABAS]);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: abaAtiva, onSelect: (id: string) => setAba(id as Aba) }), [subNavTree, abaAtiva]));

  return abaAtiva === "analise" ? <AnaliseReprodutivaPage /> : <RelatorioPersonalizado />;
}
