"use client";
// Painel CowData > Cotações — a CowData cotiza com os PRÓPRIOS fornecedores
// (nunca os de uma fazenda-cliente) e atribui preços-base sugeridos a um
// catálogo de produtos-padrão, visível às fazendas como referência em
// Cadastro > Estoque. Ver backend/fazenda/api/routers/painel_cowdata_cotacoes.py.
import { useState } from "react";
import { ClipboardList, Package, Tags, Truck } from "lucide-react";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";
import CotacoesCowDataCotacoes from "@/components/painel-cowdata/CotacoesCowDataCotacoes";
import CotacoesCowDataProdutos from "@/components/painel-cowdata/CotacoesCowDataProdutos";
import CotacoesCowDataFornecedores from "@/components/painel-cowdata/CotacoesCowDataFornecedores";
import CotacoesCowDataClassificacoes from "@/components/painel-cowdata/CotacoesCowDataClassificacoes";

const ABAS = [
  { chave: "cotacoes", label: "Cotações", icone: ClipboardList },
  { chave: "produtos", label: "Produtos-padrão", icone: Package },
  { chave: "fornecedores", label: "Fornecedores", icone: Truck },
  { chave: "vocabulario", label: "Classificações e finalidades", icone: Tags },
] as const;
type Aba = (typeof ABAS)[number]["chave"];

export default function CotacoesCowDataPage() {
  const { cor: COR } = usePainelCowDataEstilos();
  const [aba, setAba] = useState<Aba>("cotacoes");

  return (
    <div style={{ padding: "1.4rem" }}>
      <p style={{ fontSize: "0.82rem", color: COR.mudo, maxWidth: "60ch", marginBottom: "1rem" }}>
        Cotação de preços com os fornecedores da própria CowData — nunca os de uma fazenda-cliente. O preço-base sugerido
        atribuído aqui vira referência em Cadastro &gt; Estoque de toda fazenda (quem não desligou a opção); o fornecedor
        nunca aparece fora deste painel.
      </p>
      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        {ABAS.map(({ chave, label, icone: Icone }) => (
          <button key={chave} onClick={() => setAba(chave)}
            style={{
              fontSize: "0.85rem", padding: "0.5rem 1rem", borderRadius: "var(--r-sm)", cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: "0.4rem", fontWeight: 700,
              border: `1px solid ${aba === chave ? COR.dourado : COR.borda}`,
              background: aba === chave ? COR.dourado : "transparent",
              color: aba === chave ? COR.bg : COR.mudo,
            }}>
            <Icone size={15} /> {label}
          </button>
        ))}
      </div>
      {aba === "cotacoes" && <CotacoesCowDataCotacoes />}
      {aba === "produtos" && <CotacoesCowDataProdutos />}
      {aba === "fornecedores" && <CotacoesCowDataFornecedores />}
      {aba === "vocabulario" && <CotacoesCowDataClassificacoes />}
    </div>
  );
}
