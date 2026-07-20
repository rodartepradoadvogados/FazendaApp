"use client";
// Sub-tela do app: Controle de Acesso (cadastro de usuários e permissões por
// módulo) — reaproveita a mesma página do site (/usuarios), igual ao padrão
// já usado em Auditoria.tsx e em Aprovações. Restrito ao proprietário (ver
// ehDono() em app/menu/page.tsx e, no backend, fazenda.auth.exigir_dono nos
// endpoints de /auth/usuarios) — nenhum outro admin tem acesso.
import { MobVoltar } from "@/components/mobile/ui";
import UsuariosPage from "@/app/usuarios/page";

export default function ControleAcesso({ onVoltar }: { onVoltar: () => void }) {
  return (
    <div>
      <MobVoltar titulo="Controle de Acesso" onVoltar={onVoltar} />
      <UsuariosPage />
    </div>
  );
}
