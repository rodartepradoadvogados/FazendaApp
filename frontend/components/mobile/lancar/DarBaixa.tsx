"use client";
// Sub-tela LANÇAR ▸ Financeiro ▸ Dar baixa em conta — quita um lançamento que
// JÁ está no sistema (a pagar/a receber), individual ou em lote. Reaproveita
// exatamente as mesmas telas do site (Financeiro > Ações > Pagamento/
// Recebimento/Lote), só embrulhadas no shell mobile — nenhuma lógica nova.
import { useEffect, useState } from "react";
import { Receipt, HandCoins, Layers } from "lucide-react";
import { MobAviso, MobVoltar } from "@/components/mobile/ui";
import { GradeAcoes } from "@/components/mobile/lancar/comum";
import { fetchOpcoesFinanceiro } from "@/lib/api";
import { PagamentoIndividualView, PagamentoLoteView } from "@/app/financeiro/page";

type Modo = "pagar" | "receber" | "lote";

const TITULOS: Record<Modo, string> = {
  pagar: "Quitar contas a pagar", receber: "Quitar contas a receber", lote: "Baixa em lote",
};

export default function DarBaixa({ onVoltar }: { onVoltar: () => void }) {
  const [modo, setModo] = useState<Modo | null>(null);
  const [contasBancarias, setContasBancarias] = useState<string[]>([]);

  useEffect(() => {
    fetchOpcoesFinanceiro().then((d) => setContasBancarias(d.contas_bancarias || [])).catch(() => {});
  }, []);

  if (!modo) {
    return (
      <div>
        <MobVoltar titulo="Dar baixa em conta" onVoltar={onVoltar} />
        <GradeAcoes
          opcoes={[
            { id: "pagar", label: "Contas a pagar", icone: <Receipt size={28} />, cor: "var(--mob-vermelho)" },
            { id: "receber", label: "Contas a receber", icone: <HandCoins size={28} />, cor: "var(--mob-verde)" },
            { id: "lote", label: "Baixa em lote", icone: <Layers size={28} />, cor: "var(--mob-azul)" },
          ]}
          onEscolher={(id) => setModo(id as Modo)}
        />
      </div>
    );
  }

  return (
    <div>
      <MobVoltar titulo={TITULOS[modo]} onVoltar={() => setModo(null)} />
      <div className="mob-form-embutido">
        <MobAviso tipo="offline">Esta tela precisa de internet no momento de salvar — não fica guardada pra enviar depois se a conexão cair.</MobAviso>
        {modo === "pagar" && <PagamentoIndividualView tipo="despesa" contasBancarias={contasBancarias} notaAlvoRef={null} />}
        {modo === "receber" && <PagamentoIndividualView tipo="receita" contasBancarias={contasBancarias} notaAlvoRef={null} />}
        {modo === "lote" && <PagamentoLoteView contasBancarias={contasBancarias} />}
      </div>
    </div>
  );
}
