"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Heart, PieChart, Stethoscope, Baby, Syringe, Droplets, ClipboardList, Stamp, HeartCrack,
} from "lucide-react";
import { podeModulo } from "@/lib/api";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import AnaliseReprodutivaPage from "@/app/analise-reprodutiva/page";
import AgendaVeterinarioPage from "@/app/reproducao/AgendaVeterinario";
import HistoricoServicos, { type Foco } from "@/components/reproducao/HistoricoServicos";
import HistoricoPartos from "@/components/reproducao/HistoricoPartos";
import HistoricoSecagens from "@/components/reproducao/HistoricoSecagens";

type AbaVisao = "servicos" | "ias" | "diagnosticos" | "perdas" | "partos" | "secagens";
const ABAS_VISAO = [
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
] as const satisfies readonly { id: AbaVisao; label: string; icon: any; foco: Foco | null; titulo: string; descricao: string }[];

export default function ReproducaoPage() {
  const [aba, setAba] = useState<"visao" | "analise" | "vet">("visao");
  const [abaVisao, setAbaVisao] = useState<AbaVisao>("servicos");
  const [temAnalise, setTemAnalise] = useState(false);
  const [temVet, setTemVet] = useState(false);
  // Cada usuário logado tem suas próprias permissões — reavalia sempre que a
  // página monta (evita mostrar abas de uma sessão anterior de outro usuário).
  useEffect(() => { setTemAnalise(podeModulo("analise")); setTemVet(podeModulo("vet")); }, []);

  const abas = useMemo(() => [
    { id: "visao" as const, label: "Reprodução", icon: Heart, title: "Histórico de serviços, IAs, diagnósticos, perda de prenhez, partos e secagens" },
    ...(temAnalise ? [{ id: "analise" as const, label: "Análise reprodutiva", icon: PieChart, title: "Taxa de concepção e perda de prenhez, com quebras por dimensão" }] : []),
    ...(temVet ? [{ id: "vet" as const, label: "Agenda do veterinário", icon: Stethoscope, title: "Roteiro da visita reprodutiva: toques, reconfirmações e classificações" }] : []),
  ], [temAnalise, temVet]);
  const abaAtiva = abas.some((a) => a.id === aba) ? aba : "visao";

  const subNavTree: SubNavNode[] = useMemo(() => abas.map((a) => ({
    id: a.id, label: a.label, icon: a.icon,
    children: a.id === "visao" ? ABAS_VISAO.map((v) => ({ id: v.id, label: v.label, icon: v.icon })) : undefined,
  })), [abas]);
  const onSelectSubNav = useCallback((id: string) => {
    if (ABAS_VISAO.some((v) => v.id === id)) { setAba("visao"); setAbaVisao(id as AbaVisao); }
    else setAba(id as "visao" | "analise" | "vet");
  }, []);
  useSubNavRegister(useMemo(() => ({
    tree: subNavTree,
    activeId: abaAtiva === "visao" ? abaVisao : abaAtiva,
    onSelect: onSelectSubNav,
  }), [subNavTree, abaAtiva, abaVisao, onSelectSubNav]));

  const visaoAtiva = ABAS_VISAO.find((v) => v.id === abaVisao) ?? ABAS_VISAO[0];

  return (
    <div className="px-6 pt-6">
      <div style={{ margin: "0 -1.5rem" }}>
        {abaAtiva === "visao" ? (
          <div className="p-6 animate-in">
            <div className="mb-4">
              <h1 className="text-2xl font-bold flex items-center gap-2"><Heart size={22} style={{ color: "var(--dourado)" }} /> Reprodução</h1>
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Histórico de partos, IAs, secagens, serviços, diagnósticos reprodutivos e perda de prenhez.</p>
            </div>
            {abaVisao === "partos" ? <HistoricoPartos />
              : abaVisao === "secagens" ? <HistoricoSecagens />
              : <HistoricoServicos foco={visaoAtiva.foco as Foco} titulo={visaoAtiva.titulo} descricao={visaoAtiva.descricao} />}
          </div>
        ) : abaAtiva === "analise" ? <AnaliseReprodutivaPage /> : <div className="px-6"><AgendaVeterinarioPage /></div>}
      </div>
    </div>
  );
}
