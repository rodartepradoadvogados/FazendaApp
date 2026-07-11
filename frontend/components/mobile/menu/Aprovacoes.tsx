"use client";
// Sub-tela: Aprovações (só admin) — aprova/rejeita os lançamentos de campo
// enviados pelo Telegram, sem sair do app. Reaproveita a mesma view do site.
import { MobVoltar } from "@/components/mobile/ui";
import { AprovacoesView } from "@/components/AprovacoesView";

export default function Aprovacoes({ onVoltar }: { onVoltar: () => void }) {
  return (
    <div style={{ padding: "1rem" }}>
      <MobVoltar titulo="Aprovações" onVoltar={onVoltar} />
      <AprovacoesView compacto />
    </div>
  );
}
