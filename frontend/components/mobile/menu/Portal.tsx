"use client";
// Sub-tela: Portal (comunicação interna) — duas abas: Comunicação (mensagem/
// e-mail/delegar tarefa, mesma view do site) e Fotos do campo (captura da
// câmera, que passou a morar aqui para poder marcar destinatário/assunto e
// cair na mesma central de notificações do Portal). "Exportar" já vem
// escondido sozinho para quem não é admin (ver PortalView), então nenhum
// gate extra é preciso aqui.
import { useState } from "react";
import { MobVoltar } from "@/components/mobile/ui";
import { PortalView } from "@/components/PortalView";
import { LinhaPills, MobPill } from "@/components/mobile/lancar/comum";
import FotosCampo from "@/components/mobile/menu/FotosCampo";

type Aba = "comunicacao" | "fotos";

export default function Portal({ onVoltar }: { onVoltar: () => void }) {
  const [aba, setAba] = useState<Aba>("comunicacao");
  return (
    <div style={{ padding: "1rem" }}>
      <MobVoltar titulo="Portal" onVoltar={onVoltar} />
      <LinhaPills>
        <MobPill ativa={aba === "comunicacao"} onClick={() => setAba("comunicacao")}>Comunicação</MobPill>
        <MobPill ativa={aba === "fotos"} onClick={() => setAba("fotos")}>Fotos do campo</MobPill>
      </LinhaPills>
      {aba === "comunicacao" ? <PortalView /> : <FotosCampo />}
    </div>
  );
}
