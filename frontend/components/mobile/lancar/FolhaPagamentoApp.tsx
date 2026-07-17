"use client";
// Sub-tela LANÇAR ▸ Folha de pagamento — reaproveita o mesmo componente do
// site (4 abas: Funcionário/Empreita/Contrato/Diárias), igual ao padrão do
// FormFinanceiroApp.tsx (casca mobile + componente do site, sem duplicar lógica).
import { MobVoltar } from "@/components/mobile/ui";
import FolhaPagamentoView from "@/components/FolhaPagamentoView";

export default function FolhaPagamentoApp({ onVoltar }: { onVoltar: () => void }) {
  return (
    <div>
      <MobVoltar titulo="Folha de pagamento" onVoltar={onVoltar} />
      <div className="mob-form-embutido">
        <FolhaPagamentoView />
      </div>
    </div>
  );
}
