import { Wheat, AlertTriangle, Calculator, PackageCheck, LineChart, Link2 } from "lucide-react";
import { PublicPage } from "@/components/institucional/PublicShell";
import { InstitucionalHero } from "@/components/institucional/InstitucionalHero";
import { SecaoConteudo, DestaquesGrid } from "@/components/institucional/Destaques";

export default function EstoqueAlimentacaoInstitucional() {
  return (
    <PublicPage>
      <InstitucionalHero
        icon={Wheat}
        eyebrow="Estoque & Alimentação"
        titulo="Estoque e dieta calculados sozinhos"
        subtitulo="Estoque mínimo com alerta automático, cálculo de alimentação por lote e controle de gasto diário e mensal do rebanho."
        imagem="/images/bg-insumos-sanidade.webp"
      />
      <SecaoConteudo>
        <DestaquesGrid itens={[
          { icon: AlertTriangle, titulo: "Estoque mínimo com alerta", texto: "O sistema avisa sozinho quando um item cai abaixo do ponto de compra — sem precisar conferir prateleira por prateleira." },
          { icon: Calculator, titulo: "Necessidade mensal calculada", texto: "Quilos e sacas por ingrediente, direto da dieta cadastrada de cada lote — inclusive convertendo pela unidade do produto." },
          { icon: PackageCheck, titulo: "Baixa automática", texto: "O consumo do dia é descontado do estoque sozinho, conforme os dias que passaram — sem lançamento manual." },
          { icon: LineChart, titulo: "Gasto diário e mensal por lote", texto: "Quanto cada lote — e o rebanho inteiro — está gastando com alimentação, período a período." },
          { icon: Link2, titulo: "Vínculo direto com o financeiro", texto: "O que sai do estoque como ração já entra no cálculo do RMCA, sem precisar lançar duas vezes." },
        ]} />
      </SecaoConteudo>
    </PublicPage>
  );
}
