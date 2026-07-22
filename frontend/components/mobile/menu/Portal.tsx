"use client";
// Sub-tela: Portal (comunicação interna) — mensagem/e-mail/delegar tarefa,
// mesma view do site. "Exportar" já vem escondido sozinho para quem não é
// admin (ver PortalView), então nenhum gate extra é preciso aqui.
import { MobVoltar } from "@/components/mobile/ui";
import { PortalView } from "@/components/PortalView";

export default function Portal({ onVoltar }: { onVoltar: () => void }) {
  return (
    <div style={{ padding: "1rem" }}>
      <MobVoltar titulo="Portal" onVoltar={onVoltar} />
      <PortalView />
    </div>
  );
}
