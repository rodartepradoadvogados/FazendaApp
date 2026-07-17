"use client";
// Sub-tela LANÇAR ▸ Financeiro — Contas a pagar / Contas a receber, com TODOS
// os campos do lançamento financeiro do site (mesmo componente, FormFinanceiro),
// inclusive importação de XML/PDF/PNG/JPEG. Reaproveita o formulário do site
// tal como é: já força seleção via cadastro em tudo (conta gerencial, produto,
// fornecedor/cliente, conta bancária…), deixando só a "Descrição" de cada item
// como texto livre — exatamente o que a importação deve preservar.
import { useState } from "react";
import { MobVoltar } from "@/components/mobile/ui";
import { LinhaPills, MobPill } from "@/components/mobile/lancar/comum";
import { FormFinanceiro } from "@/components/FormFinanceiro";
import { RESPONSAVEIS } from "@/lib/constants";

export default function FormFinanceiroApp({ onVoltar, tipoInicial }: { onVoltar: () => void; tipoInicial?: "despesa" | "receita" }) {
  const [tipo, setTipo] = useState<"despesa" | "receita">(tipoInicial || "despesa");

  return (
    <div>
      <MobVoltar titulo="Financeiro" onVoltar={onVoltar} />
      <LinhaPills>
        <MobPill ativa={tipo === "despesa"} onClick={() => setTipo("despesa")}>Contas a pagar</MobPill>
        <MobPill ativa={tipo === "receita"} onClick={() => setTipo("receita")}>Contas a receber</MobPill>
      </LinhaPills>
      <div className="mob-form-embutido">
        <FormFinanceiro key={tipo} tipo={tipo} responsaveis={RESPONSAVEIS} />
      </div>
    </div>
  );
}
