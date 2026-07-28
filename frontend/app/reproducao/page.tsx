"use client";
import { useMemo, useState } from "react";
import { Heart, Baby, Syringe, Droplets, ClipboardList, Stamp, HeartCrack, CalendarRange } from "lucide-react";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import HistoricoServicos, { type Foco } from "@/components/reproducao/HistoricoServicos";
import HistoricoPartos from "@/components/reproducao/HistoricoPartos";
import HistoricoSecagens from "@/components/reproducao/HistoricoSecagens";
import HistoricoCiclosIatf from "@/components/reproducao/HistoricoCiclosIatf";

export type AbaVisao = "servicos" | "ias" | "diagnosticos" | "perdas" | "partos" | "secagens" | "ciclos_iatf";
export const ABAS_VISAO = [
  { id: "servicos", label: "Serviços", icon: ClipboardList, foco: "todos" as Foco,
    titulo: "Histórico de serviços", descricao: "Todo serviço reprodutivo (IA/monta) — filtre por data ou ciclo, ordem de parto/tentativa, método e diagnóstico." },
  { id: "ias", label: "IAs", icon: Syringe, foco: "ias" as Foco,
    titulo: "Histórico de IAs", descricao: "Só inseminações artificiais (IATF ou em cio natural) — monta natural fica de fora." },
  { id: "diagnosticos", label: "Diagnósticos", icon: Stamp, foco: "diagnosticos" as Foco,
    titulo: "Histórico de diagnósticos reprodutivos", descricao: "Só serviços já diagnosticados — filtre positivo/negativo." },
  { id: "perdas", label: "Perda de prenhez", icon: HeartCrack, foco: "perdas" as Foco,
    titulo: "Histórico de perda de prenhez", descricao: "Perdas de prenhez registradas — filtre por motivo (aborto/natimorto/outros)." },
  { id: "partos", label: "Partos", icon: Baby, foco: null,
    titulo: "", descricao: "" },
  { id: "secagens", label: "Secagens", icon: Droplets, foco: null,
    titulo: "", descricao: "" },
  { id: "ciclos_iatf", label: "Ciclos de IATF", icon: CalendarRange, foco: null,
    titulo: "", descricao: "" },
] as const satisfies readonly { id: AbaVisao; label: string; icon: any; foco: Foco | null; titulo: string; descricao: string }[];

export default function ReproducaoPage() {
  const [abaVisao, setAbaVisao] = useState<AbaVisao>("servicos");

  const subNavTree: SubNavNode[] = useMemo(() => ABAS_VISAO.map((v) => ({ id: v.id, label: v.label, icon: v.icon })), []);
  useSubNavRegister(useMemo(() => ({
    tree: subNavTree, activeId: abaVisao, onSelect: (id: string) => setAbaVisao(id as AbaVisao),
  }), [subNavTree, abaVisao]));

  const visaoAtiva = ABAS_VISAO.find((v) => v.id === abaVisao) ?? ABAS_VISAO[0];

  return (
    <div className="px-6 pt-6">
      <div className="p-6 animate-in">
        <div className="mb-4">
          <h1 className="text-2xl font-bold flex items-center gap-2"><Heart size={22} style={{ color: "var(--dourado)" }} /> Reprodução</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Histórico de partos, IAs, secagens, serviços, diagnósticos reprodutivos, perda de prenhez e ciclos de IATF.</p>
        </div>
        {abaVisao === "partos" ? <HistoricoPartos />
          : abaVisao === "secagens" ? <HistoricoSecagens />
          : abaVisao === "ciclos_iatf" ? <HistoricoCiclosIatf />
          : <HistoricoServicos foco={visaoAtiva.foco as Foco} titulo={visaoAtiva.titulo} descricao={visaoAtiva.descricao} />}
      </div>
    </div>
  );
}
