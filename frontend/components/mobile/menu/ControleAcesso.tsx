"use client";
// Sub-tela do app: Controle de Acesso (cadastro de usuários e permissões por
// módulo) — reaproveita a mesma página do site (/usuarios), igual ao padrão
// já usado em Auditoria.tsx e em Aprovações. Sem tela mobile própria: o
// backend e a lógica já são únicos, só falta a entrada no Menu do app (ver
// app/menu/page.tsx, gated por ehAdmin() — qualquer admin, não só o dono).
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
