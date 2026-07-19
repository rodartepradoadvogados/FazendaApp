"use client";
// Sub-tela LANÇAR ▸ Financeiro — Contas a pagar / Contas a receber, com TODOS
// os campos do lançamento financeiro do site (mesmo componente, FormFinanceiro),
// inclusive importação de XML/PDF/PNG/JPEG. Reaproveita o formulário do site
// tal como é: já força seleção via cadastro em tudo (conta gerencial, produto,
// fornecedor/cliente, conta bancária…), deixando só a "Descrição" de cada item
// como texto livre — exatamente o que a importação deve preservar.
import { useState } from "react";
import dynamic from "next/dynamic";
import { Receipt, HandCoins, ShoppingCart, Tag, Dna, Users } from "lucide-react";
import { MobVoltar } from "@/components/mobile/ui";
import { GradeAcoes, type Animal } from "@/components/mobile/lancar/comum";
import { RESPONSAVEIS } from "@/lib/constants";

// Cada pílula só baixa seu próprio formulário quando aberta pela 1ª vez —
// importante em conexão de campo, onde o app roda mais.
const FormFinanceiro = dynamic(() => import("@/components/FormFinanceiro").then((m) => m.FormFinanceiro), { ssr: false });
const CompraVendaAnimalForm = dynamic(() => import("@/components/CompraVendaAnimalForm"), { ssr: false });
const CompraSemenForm = dynamic(() => import("@/components/CompraSemenForm"), { ssr: false });
const FolhaPagamentoView = dynamic(() => import("@/components/FolhaPagamentoView"), { ssr: false });

type TipoLancamento = "despesa" | "receita" | "compra_animal" | "venda_animal" | "compra_semen" | "folha";

const TITULOS: Record<TipoLancamento, string> = {
  despesa: "Contas a pagar", receita: "Contas a receber", compra_animal: "Compra de animal",
  venda_animal: "Venda de animal", compra_semen: "Compra de sêmen", folha: "Folha de pagamento",
};

export default function FormFinanceiroApp({ onVoltar, tipoInicial, animais }: { onVoltar: () => void; tipoInicial?: "despesa" | "receita"; animais: Animal[] }) {
  const [tipo, setTipo] = useState<TipoLancamento | null>(tipoInicial || null);

  if (!tipo) {
    return (
      <div>
        <MobVoltar titulo="Financeiro" onVoltar={onVoltar} />
        <GradeAcoes
          opcoes={[
            { id: "despesa", label: "Contas a pagar", icone: <Receipt size={28} />, cor: "var(--mob-vermelho)" },
            { id: "receita", label: "Contas a receber", icone: <HandCoins size={28} />, cor: "var(--mob-verde)" },
            { id: "compra_animal", label: "Compra de animal", icone: <ShoppingCart size={28} />, cor: "var(--mob-azul)" },
            { id: "venda_animal", label: "Venda de animal", icone: <Tag size={28} />, cor: "var(--mob-laranja)" },
            { id: "compra_semen", label: "Compra de sêmen", icone: <Dna size={28} />, cor: "var(--mob-roxo)" },
            { id: "folha", label: "Folha de pagamento", icone: <Users size={28} />, cor: "var(--mob-dourado-2)" },
          ]}
          onEscolher={(id) => setTipo(id as TipoLancamento)}
        />
      </div>
    );
  }

  return (
    <div>
      <MobVoltar titulo={TITULOS[tipo]} onVoltar={() => setTipo(null)} />
      <div className="mob-form-embutido">
        {(tipo === "despesa" || tipo === "receita") && <FormFinanceiro key={tipo} tipo={tipo} responsaveis={RESPONSAVEIS} />}
        {tipo === "compra_animal" && <CompraVendaAnimalForm key="compra_animal" modo="compra" animais={animais} />}
        {tipo === "venda_animal" && <CompraVendaAnimalForm key="venda_animal" modo="venda" animais={animais} />}
        {tipo === "compra_semen" && <CompraSemenForm key="compra_semen" />}
        {tipo === "folha" && <FolhaPagamentoView key="folha" />}
      </div>
    </div>
  );
}
