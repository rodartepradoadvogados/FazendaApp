"use client";
// Painel CowData > Farmácia — duas telas complementares:
// 1) "Catálogo" — navega/edita as indicações padrão já existentes (mesmo
//    componente reaproveitado da fazenda, ver Farmacia.tsx com
//    contextoGlobal), incluindo bula, carência e prioridade;
// 2) "Cadastrar" — cria categoria/princípio ativo/medicamento NOVOS, que
//    passam a existir para todas as fazendas-cliente (catálogo global) e,
//    no caso de medicamento, fazem fan-out automático para o Estoque de
//    cada tenant (inativo/não-estocável) — ver
//    backend/fazenda/api/routers/painel_cowdata_farmacia.py.
import { useState } from "react";
import { BookOpen, FilePlus2 } from "lucide-react";
import Farmacia from "@/components/Farmacia";
import FarmaciaCadastroCentral from "@/components/painel-cowdata/FarmaciaCadastroCentral";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";

export default function FarmaciaCowData() {
  const { cor: COR } = usePainelCowDataEstilos();
  const [aba, setAba] = useState<"catalogo" | "cadastrar">("cadastrar");

  return (
    <div style={{ padding: "1.4rem" }}>
      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        {([["cadastrar", "Cadastrar", FilePlus2], ["catalogo", "Catálogo", BookOpen]] as const).map(([chave, label, Icone]) => (
          <button key={chave} onClick={() => setAba(chave)}
            style={{
              fontSize: "0.85rem", padding: "0.5rem 1rem", borderRadius: "var(--r-sm)", cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: "0.4rem", fontWeight: 700,
              border: `1px solid ${aba === chave ? COR.dourado : COR.borda}`,
              background: aba === chave ? COR.dourado : "transparent",
              color: aba === chave ? COR.bg : COR.mudo,
            }}>
            <Icone size={15} /> {label}
          </button>
        ))}
      </div>
      {aba === "cadastrar" ? <FarmaciaCadastroCentral /> : <Farmacia contextoGlobal />}
    </div>
  );
}
