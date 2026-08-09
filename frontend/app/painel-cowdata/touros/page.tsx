"use client";
// Painel CowData > Touros Naab — mesmo catálogo global usado por TODAS as
// fazendas (Touro não tem fazenda_id, ver backend/fazenda/models/
// sanidade.py) e a mesma tela/rotas de Configurações > Cadastro > Touros de
// qualquer fazenda (backend/fazenda/api/routers/cadastro/genetica.py —
// nenhuma delas depende de fazenda selecionada). Reaproveita o componente
// inteiro: ele já usa var(--surface)/var(--border)/var(--text) etc., que o
// layout do Painel CowData escopa para a própria paleta escura (tokensPainel
// em app/painel-cowdata/layout.tsx), então não precisa de nenhuma adaptação
// visual — só entrar aqui de propósito para o dono/equipe CowData poder
// manter o catálogo sem abrir uma fazenda específica.
import CadastroTouros from "@/components/CadastroTouros";

export default function TourosNaabCowData() {
  return (
    <div style={{ padding: "1.4rem" }}>
      <CadastroTouros />
    </div>
  );
}
