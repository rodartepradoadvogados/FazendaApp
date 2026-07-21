import { ClipboardList, ShoppingCart, PiggyBank, Link2, CircleCheck } from "lucide-react";
import { PublicPage } from "@/components/institucional/PublicShell";
import { InstitucionalHero } from "@/components/institucional/InstitucionalHero";
import { SecaoConteudo, DestaquesGrid } from "@/components/institucional/Destaques";

export default function PedidosPlanejamentoInstitucional() {
  return (
    <PublicPage>
      <InstitucionalHero
        icon={ClipboardList}
        eyebrow="Pedidos & Planejamento"
        titulo="Do orçamento ao pedido, sem perder o fio"
        subtitulo="Controle de pedidos e orçamentos ligado ao planejamento financeiro — acompanhe o que foi pedido, aprovado e ainda falta chegar."
        imagem="/images/bg-analise.webp"
      />
      <SecaoConteudo>
        <DestaquesGrid itens={[
          { icon: ShoppingCart, titulo: "Pedidos", texto: "Do orçamento ao recebimento, sem depender de e-mail ou WhatsApp solto para saber o que já foi pedido." },
          { icon: PiggyBank, titulo: "Orçamento e planejamento financeiro", texto: "Projeção de entradas e saídas por período, para decidir com o que vem pela frente em mente." },
          { icon: Link2, titulo: "Vínculo com Financeiro e Estoque", texto: "Pedido aprovado já reflete na conta a pagar e na entrada de estoque — sem lançar de novo." },
          { icon: CircleCheck, titulo: "Acompanhamento de status", texto: "Feito, aprovado, entregue — o andamento de cada pedido sempre visível, sem precisar perguntar." },
        ]} />
      </SecaoConteudo>
    </PublicPage>
  );
}
