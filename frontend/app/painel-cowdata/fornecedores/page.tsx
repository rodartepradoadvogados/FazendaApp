"use client";
// Painel CowData > Fornecedores-padrão — cadastro dos PRÓPRIOS fornecedores
// da CowData (nunca os de uma fazenda-cliente), usado nas Cotações de preço
// (ver /painel-cowdata/cotacoes) para sugerir quem convidar por
// classificação/finalidade. Antes vivia como sub-aba interna de Cotações;
// promovido a item próprio do menu lateral (pedido do usuário, set/2026).
import CotacoesCowDataFornecedores from "@/components/painel-cowdata/CotacoesCowDataFornecedores";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";

export default function FornecedoresPadraoPage() {
  const { cor: COR } = usePainelCowDataEstilos();
  return (
    <div style={{ padding: "1.4rem" }}>
      <p style={{ fontSize: "0.82rem", color: COR.mudo, maxWidth: "60ch", marginBottom: "1rem" }}>
        Fornecedores da própria CowData — nunca os de uma fazenda-cliente. Usados nas Cotações de preço para sugerir
        quem convidar por classificação/finalidade; o fornecedor nunca aparece fora deste painel.
      </p>
      <CotacoesCowDataFornecedores />
    </div>
  );
}
