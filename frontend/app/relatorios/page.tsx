"use client";
import { useMemo, useState } from "react";
import { FileBarChart, ClipboardCheck, LineChart } from "lucide-react";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import RelatoriosManejo from "@/components/RelatoriosManejo";
import RelatoriosGerenciais from "@/components/RelatoriosGerenciais";

type Aba = "manejo" | "gerencial";
const ABAS = [
  { id: "manejo" as const, label: "Relatórios de manejo", icon: ClipboardCheck, title: "O que fazer hoje com cada animal — listas semaforizadas (PEV, a inseminar, toque, secagem, partos, sêmen)" },
  { id: "gerencial" as const, label: "Relatórios gerenciais", icon: LineChart, title: "Gráficos gerenciais do desempenho reprodutivo do rebanho" },
];

export default function RelatoriosPage() {
  const [aba, setAba] = useState<Aba>("manejo");
  const subNavTree: SubNavNode[] = useMemo(() => ABAS.map((a) => ({ id: a.id, label: a.label, icon: a.icon })), []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: aba, onSelect: (id: string) => setAba(id as Aba) }), [subNavTree, aba]));
  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><FileBarChart size={22} style={{ color: "var(--dourado)" }} /> Relatórios gerenciais</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Manejo do dia a dia e análise gerencial do desempenho reprodutivo — inspirado nas melhores práticas de programas zootécnicos.
        </p>
      </div>
      {aba === "manejo" && <RelatoriosManejo />}
      {aba === "gerencial" && <RelatoriosGerenciais />}
    </div>
  );
}
