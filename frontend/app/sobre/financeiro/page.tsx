import { Landmark, TrendingUp, Calculator, Ruler, Receipt, Wallet } from "lucide-react";
import { PublicPage } from "@/components/institucional/PublicShell";
import { InstitucionalHero } from "@/components/institucional/InstitucionalHero";
import { SecaoConteudo, DestaquesGrid, FaixaNumeros } from "@/components/institucional/Destaques";

export default function FinanceiroInstitucional() {
  return (
    <PublicPage>
      <InstitucionalHero
        icon={Landmark}
        eyebrow="Gestão financeira"
        titulo="Todo o financeiro da fazenda em um só painel"
        subtitulo="Fluxo de caixa, DRE, livro caixa e os custos que realmente importam — por litro, por vaca, por lote e por hectare."
        imagem="/images/bg-analise.webp"
      />
      <SecaoConteudo>
        <FaixaNumeros itens={[
          { valor: "5 abas", rotulo: "Contas a pagar/receber/pagas/recebidas/extrato" },
          { valor: "2 versões", rotulo: "RMCA gerencial e físico" },
          { valor: "4 recortes", rotulo: "Custo litro/vaca/lote/hectare" },
          { valor: "1 clique", rotulo: "Leitura automática de nota" },
        ]} />
        <DestaquesGrid itens={[
          { icon: TrendingUp, titulo: "Fluxo de caixa e DRE", texto: "Entradas e saídas por competência ou por caixa, sempre atualizados, com o livro caixa completo por trás." },
          { icon: Calculator, titulo: "RMCA — Receita Menos Custo com Alimentação", texto: "Duas versões lado a lado, gerencial e física, para saber quanto sobra da receita do leite depois da alimentação." },
          { icon: Ruler, titulo: "Custo por litro, por vaca e por lote", texto: "O gasto do período dividido pelo que cada frente realmente produziu — inclusive comparando lote a lote." },
          { icon: Ruler, titulo: "Custo por hectare", texto: "O retorno da fazenda também medido pela área usada, não só pelo tamanho do rebanho." },
          { icon: Receipt, titulo: "Contas a pagar e a receber", texto: "Lançamento único ou parcelado, com leitura automática de nota fiscal, recibo ou boleto anexado." },
          { icon: Wallet, titulo: "Folha de pagamento", texto: "Salário, vale e encargos calculados e refletidos direto nas contas a pagar e na agenda." },
        ]} />
      </SecaoConteudo>
    </PublicPage>
  );
}
