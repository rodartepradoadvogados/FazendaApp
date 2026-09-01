"use client";
// Sanidade > Catálogo (Fase F, 01/09/2026) — pedido do usuário: "em
// configurações da fazenda, cadastro, farmácia, temos uma espécie de
// farmácia do Painel CowData. Ali, na verdade, tem que ser uma reprodução
// do que há no painel cowdata, mas sem a possibilidade de cadastrar nada,
// apenas o catálogo." Além de virar somente-leitura, saiu de Configurações
// > Cadastro > Farmácia (que não é tela de cadastro alguma coisa aqui, é
// consulta) e passou para Sanidade — mesmo lugar onde a fazenda já consulta
// doenças, remédios (RemediosPorDoenca) e protocolos, continuação natural
// do mesmo fluxo. Reaproveita o componente CatalogoFarmacia (Farmacia.tsx),
// que já sabe renderizar tanto o modo Painel CowData (contextoGlobal) quanto
// o modo fazenda — aqui só liga somenteLeitura, sem duplicar a árvore de
// indicação → princípio → marca.
import { CatalogoFarmacia } from "@/components/Farmacia";

export default function CatalogoFarmaciaConsulta() {
  return <CatalogoFarmacia somenteLeitura />;
}
