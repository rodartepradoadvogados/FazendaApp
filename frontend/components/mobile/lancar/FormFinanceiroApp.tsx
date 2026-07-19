"use client";
// Sub-tela LANÇAR ▸ Financeiro — Contas a pagar / Contas a receber, com TODOS
// os campos do lançamento financeiro do site (mesmo componente, FormFinanceiro),
// inclusive importação de XML/PDF/PNG/JPEG. Reaproveita o formulário do site
// tal como é: já força seleção via cadastro em tudo (conta gerencial, produto,
// fornecedor/cliente, conta bancária…), deixando só a "Descrição" de cada item
// como texto livre — exatamente o que a importação deve preservar.
import { useState } from "react";
import dynamic from "next/dynamic";
import { MobVoltar } from "@/components/mobile/ui";
import { LinhaPills, MobPill, type Animal } from "@/components/mobile/lancar/comum";
import { RESPONSAVEIS } from "@/lib/constants";

// Cada pílula só baixa seu próprio formulário quando aberta pela 1ª vez —
// importante em conexão de campo, onde o app roda mais.
const FormFinanceiro = dynamic(() => import("@/components/FormFinanceiro").then((m) => m.FormFinanceiro), { ssr: false });
const CompraVendaAnimalForm = dynamic(() => import("@/components/CompraVendaAnimalForm"), { ssr: false });
const CompraSemenForm = dynamic(() => import("@/components/CompraSemenForm"), { ssr: false });
const FolhaPagamentoView = dynamic(() => import("@/components/FolhaPagamentoView"), { ssr: false });

type TipoLancamento = "despesa" | "receita" | "compra_animal" | "venda_animal" | "compra_semen" | "folha";

export default function FormFinanceiroApp({ onVoltar, tipoInicial, animais }: { onVoltar: () => void; tipoInicial?: "despesa" | "receita"; animais: Animal[] }) {
  const [tipo, setTipo] = useState<TipoLancamento>(tipoInicial || "despesa");

  return (
    <div>
      <MobVoltar titulo="Financeiro" onVoltar={onVoltar} />
      <LinhaPills>
        <MobPill ativa={tipo === "despesa"} onClick={() => setTipo("despesa")}>Contas a pagar</MobPill>
        <MobPill ativa={tipo === "receita"} onClick={() => setTipo("receita")}>Contas a receber</MobPill>
        <MobPill ativa={tipo === "compra_animal"} onClick={() => setTipo("compra_animal")}>Compra de animal</MobPill>
        <MobPill ativa={tipo === "venda_animal"} onClick={() => setTipo("venda_animal")}>Venda de animal</MobPill>
        <MobPill ativa={tipo === "compra_semen"} onClick={() => setTipo("compra_semen")}>Compra de sêmen</MobPill>
        <MobPill ativa={tipo === "folha"} onClick={() => setTipo("folha")}>Folha de pagamento</MobPill>
      </LinhaPills>
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
