"use client";
// Página da exclusão (Fase 2) — abas Apagar / Pedidos / Trilha e o fluxo em etapas.
// Consome o backend da Fase 1 (impacto estruturado, risco, trilha, pedidos).
import { useEffect, useState } from "react";
import { Trash2, ClipboardList, History } from "lucide-react";
import { ehAdmin } from "@/lib/api";
import { useExclusao } from "./useExclusao";
import { EscolherTipo } from "./EscolherTipo";
import { ListaResultados } from "./ListaResultados";
import { PainelImpacto } from "./PainelImpacto";
import { DecisaoExclusao } from "./DecisaoExclusao";
import { ResultadoExclusao } from "./ResultadoExclusao";
import { PedidosAdmin } from "./PedidosAdmin";
import { MeusPedidos } from "./MeusPedidos";
import { TrilhaExclusao } from "./TrilhaExclusao";

type Aba = "apagar" | "pedidos" | "trilha";

export function ExclusaoPage({ ocultarTipos }: { ocultarTipos?: string[] } = {}) {
  const [aba, setAba] = useState<Aba>("apagar");
  const [souAdmin, setSouAdmin] = useState(false);
  const ex = useExclusao();

  useEffect(() => { setSouAdmin(ehAdmin()); }, []);

  const abas: { id: Aba; rotulo: string; icone: React.ReactNode; admin?: boolean }[] = [
    { id: "apagar", rotulo: "Apagar", icone: <Trash2 size={16} /> },
    { id: "pedidos", rotulo: souAdmin ? "Pedidos" : "Meus pedidos", icone: <ClipboardList size={16} /> },
    { id: "trilha", rotulo: "Trilha", icone: <History size={16} />, admin: true },
  ];

  return (
    <div className="exc-page">
      <div className="exc-tabs" role="tablist" aria-label="Excluir lançamentos">
        {abas.filter((a) => !a.admin || souAdmin).map((a) => (
          <button
            key={a.id}
            role="tab"
            aria-selected={aba === a.id}
            className={`exc-tab ${aba === a.id ? "exc-tab-ativa" : ""}`}
            onClick={() => setAba(a.id)}
          >
            {a.icone} {a.rotulo}
          </button>
        ))}
      </div>

      {aba === "apagar" && (
        <FluxoApagar ocultarTipos={ocultarTipos} ex={ex} souAdmin={souAdmin} />
      )}
      {aba === "pedidos" && (souAdmin ? <PedidosAdmin /> : <MeusPedidos />)}
      {aba === "trilha" && souAdmin && <TrilhaExclusao />}
    </div>
  );
}

function FluxoApagar({ ocultarTipos, ex, souAdmin }: { ocultarTipos?: string[]; ex: ReturnType<typeof useExclusao>; souAdmin: boolean }) {
  const { estado } = ex;

  if (estado.etapa === "escolher") {
    return <EscolherTipo ocultarTipos={ocultarTipos} aoEscolher={ex.escolher} />;
  }
  if (estado.etapa === "impacto") {
    if (!estado.impacto) {
      return <ListaResultados tipo={estado.selecao?.tipo ?? ""} titulo={estado.selecao?.titulo ?? ""} aoImpacto={ex.setImpacto} aoErro={ex.setErro} />;
    }
    return (
      <div className="exc-impacto">
        <PainelImpacto impacto={estado.impacto} />
        <DecisaoExclusao
          impacto={estado.impacto}
          motivo={estado.motivo}
          confirmacao={estado.confirmacao}
          souAdmin={souAdmin}
          aoMotivo={ex.setMotivo}
          aoConfirmacao={ex.setConfirmacao}
          aoPronto={ex.pronto}
          aoErro={ex.setErro}
          aoVoltar={ex.reiniciar}
        />
      </div>
    );
  }
  return <ResultadoExclusao resultado={estado.resultado} aoReiniciar={ex.reiniciar} />;
}
