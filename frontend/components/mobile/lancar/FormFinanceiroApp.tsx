"use client";
// Sub-tela LANÇAR ▸ Financeiro — Contas a pagar / Contas a receber, com TODOS
// os campos do lançamento financeiro do site (mesmo componente, FormFinanceiro),
// inclusive importação de XML/PDF/PNG/JPEG. Reaproveita o formulário do site
// tal como é: já força seleção via cadastro em tudo (conta gerencial, produto,
// fornecedor/cliente, conta bancária…), deixando só a "Descrição" de cada item
// como texto livre — exatamente o que a importação deve preservar.
import { useState } from "react";
import dynamic from "next/dynamic";
import { Receipt, HandCoins, ShoppingCart, Tag, Dna, Users, CircleDollarSign } from "lucide-react";
import { MobAviso, MobVoltar } from "@/components/mobile/ui";
import { GradeAcoes, type Animal } from "@/components/mobile/lancar/comum";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { enviarOuEnfileirar } from "@/lib/offline";
import { criarCompraAnimal, criarVendaAnimal, criarCompraSemen } from "@/lib/api";

// Compra/venda de animal e compra de sêmen são registros simples (1 POST,
// sem confirmação em 2 etapas nem anexo síncrono) — únicos 3 fluxos do
// Financeiro migrados para a fila offline por ora. Contas a pagar/receber
// (FormFinanceiro), folha de pagamento e dar baixa ficam de fora: nenhum tem
// proteção de duplicidade no backend hoje e dar baixa em lote, em especial,
// tem alto risco de pagar a mesma conta duas vezes se reenviada — mais seguro
// exigir internet ali do que arriscar duplicar valor financeiro.
async function salvarCompraAnimalOffline(dados: Parameters<typeof criarCompraAnimal>[0]) {
  const r = await enviarOuEnfileirar("/compras-animais/", dados, `Compra de ${dados.animais.length} animal(is)`);
  return { ...(r.resposta || {}), enviado: r.enviado };
}
async function salvarVendaAnimalOffline(dados: Parameters<typeof criarVendaAnimal>[0]) {
  const r = await enviarOuEnfileirar("/vendas-animais/", dados, `Venda de ${dados.animais.length} animal(is)`);
  return { ...(r.resposta || {}), enviado: r.enviado };
}
async function salvarCompraSemenOffline(dados: Parameters<typeof criarCompraSemen>[0]) {
  const r = await enviarOuEnfileirar("/compras-semen/", dados, `Compra de sêmen (${dados.itens.length} item(ns))`);
  return { ...(r.resposta || {}), enviado: r.enviado };
}

// Cada pílula só baixa seu próprio formulário quando aberta pela 1ª vez —
// importante em conexão de campo, onde o app roda mais.
const FormFinanceiro = dynamic(() => import("@/components/FormFinanceiro").then((m) => m.FormFinanceiro), { ssr: false });
const CompraVendaAnimalForm = dynamic(() => import("@/components/CompraVendaAnimalForm"), { ssr: false });
const CompraSemenForm = dynamic(() => import("@/components/CompraSemenForm"), { ssr: false });
const FolhaPagamentoView = dynamic(() => import("@/components/FolhaPagamentoView"), { ssr: false });
const DarBaixa = dynamic(() => import("@/components/mobile/lancar/DarBaixa"), { ssr: false });

type TipoLancamento = "despesa" | "receita" | "compra_animal" | "venda_animal" | "compra_semen" | "folha" | "baixa";

const TITULOS: Record<TipoLancamento, string> = {
  despesa: "Contas a pagar", receita: "Contas a receber", compra_animal: "Compra de animal",
  venda_animal: "Venda de animal", compra_semen: "Compra de sêmen", folha: "Folha de pagamento",
  baixa: "Dar baixa em conta",
};

export default function FormFinanceiroApp({ onVoltar, tipoInicial, animais }: { onVoltar: () => void; tipoInicial?: "despesa" | "receita"; animais: Animal[] }) {
  const [tipo, setTipo] = useState<TipoLancamento | null>(tipoInicial || null);
  const { nomes: nomesResponsaveis } = usePessoasAtivas();

  if (!tipo) {
    return (
      <div>
        <MobVoltar titulo="Financeiro" onVoltar={onVoltar} />
        <GradeAcoes
          opcoes={[
            { id: "despesa", label: "Contas a pagar", icone: <Receipt size={28} />, cor: "var(--mob-vermelho)" },
            { id: "receita", label: "Contas a receber", icone: <HandCoins size={28} />, cor: "var(--mob-verde)" },
            { id: "baixa", label: "Dar baixa em conta", icone: <CircleDollarSign size={28} />, cor: "var(--mob-dourado-2)" },
            { id: "compra_animal", label: "Compra de animal", icone: <ShoppingCart size={28} />, cor: "var(--mob-azul)" },
            { id: "venda_animal", label: "Venda de animal", icone: <Tag size={28} />, cor: "var(--mob-laranja)" },
            { id: "compra_semen", label: "Compra de sêmen", icone: <Dna size={28} />, cor: "var(--mob-roxo)" },
            { id: "folha", label: "Folha de pagamento", icone: <Users size={28} />, cor: "var(--mob-vinho)" },
          ]}
          onEscolher={(id) => setTipo(id as TipoLancamento)}
        />
      </div>
    );
  }

  if (tipo === "baixa") {
    return <DarBaixa onVoltar={() => setTipo(null)} />;
  }

  return (
    <div>
      <MobVoltar titulo={TITULOS[tipo]} onVoltar={() => setTipo(null)} />
      <div className="mob-form-embutido">
        {/* Contas a pagar/receber e folha de pagamento reaproveitam o
            formulário do site tal como é — salvam direto pela rede, sem
            passar pela fila offline (nenhum dos dois tem proteção de
            duplicidade no backend hoje). Compra/venda de animal e compra de
            sêmen já passam pela fila (ver salvar*Offline acima). */}
        {(tipo === "despesa" || tipo === "receita" || tipo === "folha") && (
          <MobAviso tipo="offline">Esta tela precisa de internet no momento de salvar — não fica guardada pra enviar depois se a conexão cair.</MobAviso>
        )}
        {(tipo === "despesa" || tipo === "receita") && <FormFinanceiro key={tipo} tipo={tipo} responsaveis={nomesResponsaveis} apresentacaoModais="tela" />}
        {tipo === "compra_animal" && <CompraVendaAnimalForm key="compra_animal" modo="compra" animais={animais} salvarCompra={salvarCompraAnimalOffline as any} />}
        {tipo === "venda_animal" && <CompraVendaAnimalForm key="venda_animal" modo="venda" animais={animais} salvarVenda={salvarVendaAnimalOffline as any} />}
        {tipo === "compra_semen" && <CompraSemenForm key="compra_semen" salvarCompra={salvarCompraSemenOffline as any} />}
        {tipo === "folha" && <FolhaPagamentoView key="folha" />}
      </div>
    </div>
  );
}
