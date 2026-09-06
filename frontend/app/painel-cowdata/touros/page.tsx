"use client";
// Painel CowData > Touros Naab — o ÚNICO lugar onde o catálogo global de
// touros se edita (set/2026).
//
// `Touro` não tem fazenda_id: é uma tabela só, lida por todas as fazendas-
// cliente. Até aqui a manutenção morava em Configurações > Cadastro > Touros
// de cada fazenda, protegida por `exigir_admin` — que é a proteção certa
// para o dado de UMA fazenda e a errada para este: o administrador de
// qualquer fazenda-cliente reescrevia ou apagava o catálogo de todas. As
// rotas de escrita foram removidas de lá e vivem em
// backend/fazenda/api/routers/painel_cowdata_touros.py, sob a permissão
// "editar touros NAAB" do cadastro de equipe.
//
// A tela é a mesma de sempre (components/CadastroTouros.tsx), agora em modo
// "painel": ela já usa var(--surface)/var(--border)/var(--text) etc., que o
// layout do Painel CowData escopa para a própria paleta escura (tokensPainel
// em app/painel-cowdata/layout.tsx), então não precisa de adaptação visual.
// Do lado da fazenda o mesmo componente roda em modo "fazenda", só leitura.
import CadastroTouros from "@/components/CadastroTouros";

export default function TourosNaabCowData() {
  return (
    <div style={{ padding: "1.4rem" }}>
      <CadastroTouros contexto="painel" />
    </div>
  );
}
