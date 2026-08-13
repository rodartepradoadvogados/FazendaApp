"use client";
import { useCallback, useMemo, useState } from "react";
import { Heart, Milk } from "lucide-react";
import { podeModulo } from "@/lib/api";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import HistoricoServicos, { type Foco } from "@/components/reproducao/HistoricoServicos";
import HistoricoPartos from "@/components/reproducao/HistoricoPartos";
import HistoricoSecagens from "@/components/reproducao/HistoricoSecagens";
import HistoricoCiclosIatf from "@/components/reproducao/HistoricoCiclosIatf";
import { ABAS_VISAO, type AbaVisao } from "@/app/reproducao/page";
import {
  ABAS_PRODUCAO, ProducaoLeiteira, RelatoriosBstView, RelatoriosPesagemView,
  HistoricoInducaoLactacao, HistoricoSecagensProducao,
} from "@/app/producao/page";

type AbaProducao = "leiteira" | "pesagens" | "secagem" | "inducao" | "qualidade" | "entrega" | "bst";
type Aba = "reproducao" | "producao";

export default function HistoricoPage() {
  const temReproducao = podeModulo("reproducao");
  const temProducao = podeModulo("producao");
  const [aba, setAba] = useState<Aba>(temReproducao ? "reproducao" : "producao");
  const [abaVisao, setAbaVisao] = useState<AbaVisao>("servicos");
  const [abaProducao, setAbaProducao] = useState<AbaProducao>("leiteira");

  const subNavTree: SubNavNode[] = useMemo(() => [
    ...(temReproducao ? [{ id: "reproducao", label: "Reprodução", icon: Heart, children: ABAS_VISAO.map((v) => ({ id: v.id, label: v.label, icon: v.icon })) }] : []),
    ...(temProducao ? [{ id: "producao", label: "Produção", icon: Milk, children: ABAS_PRODUCAO.map((a) => ({ id: a.id, label: a.label, icon: a.icon })) }] : []),
  ], [temReproducao, temProducao]);

  const activeId = aba === "reproducao" ? abaVisao : abaProducao;
  const onSelect = useCallback((id: string) => {
    if (id === "reproducao" || id === "producao") { setAba(id); return; }
    if (ABAS_VISAO.some((v) => v.id === id)) { setAba("reproducao"); setAbaVisao(id as AbaVisao); return; }
    if (ABAS_PRODUCAO.some((a) => a.id === id)) { setAba("producao"); setAbaProducao(id as AbaProducao); return; }
  }, []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId, onSelect }), [subNavTree, activeId, onSelect]));

  if (aba === "producao") {
    switch (abaProducao) {
      case "bst": return <RelatoriosBstView />;
      case "pesagens": return <RelatoriosPesagemView />;
      case "secagem": return <HistoricoSecagensProducao />;
      case "inducao": return <HistoricoInducaoLactacao />;
      case "qualidade": return <ProducaoLeiteira secao="qualidade" />;
      case "entrega": return <ProducaoLeiteira secao="entrega" />;
      default: return <ProducaoLeiteira secao="controle" />;
    }
  }

  const visaoAtiva = ABAS_VISAO.find((v) => v.id === abaVisao) ?? ABAS_VISAO[0];
  return (
    <div className="px-6 pt-6">
      <div className="p-6 animate-in">
        <div className="mb-4">
          <h1 className="text-2xl font-bold flex items-center gap-2"><Heart size={22} style={{ color: "var(--dourado)" }} /> Reprodução</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Histórico de partos, IAs, secagens, serviços, diagnósticos reprodutivos e perda de prenhez.</p>
        </div>
        {abaVisao === "partos" ? <HistoricoPartos />
          : abaVisao === "secagens" ? <HistoricoSecagens />
          : abaVisao === "ciclos_iatf" ? <HistoricoCiclosIatf />
          : <HistoricoServicos foco={visaoAtiva.foco as Foco} titulo={visaoAtiva.titulo} descricao={visaoAtiva.descricao} />}
      </div>
    </div>
  );
}
