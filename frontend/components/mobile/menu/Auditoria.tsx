"use client";
// Sub-tela do app: Controle de acesso e Auditoria de atividade — só o
// proprietário da fazenda vê este item no Menu (ver ehDono() em app/menu/page.tsx
// e, no backend, fazenda.auth.exigir_dono). Reaproveita a mesma view do site
// (Configurações > Usuários), igual ao padrão já usado em Aprovações.
import { MobVoltar } from "@/components/mobile/ui";
import { RelatorioAcessos, AuditoriaAtividade } from "@/components/AuditoriaAcessoView";

export default function Auditoria({ onVoltar }: { onVoltar: () => void }) {
  return (
    <div style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <MobVoltar titulo="Acessos e Auditoria" onVoltar={onVoltar} />
      <RelatorioAcessos />
      <AuditoriaAtividade />
    </div>
  );
}
