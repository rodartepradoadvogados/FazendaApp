"use client";
import { Tag } from "lucide-react";
import { fetchMotivosVenda, criarMotivoVenda, atualizarMotivoVenda } from "@/lib/api";
import CadastroMotivosGenerico from "@/components/CadastroMotivosGenerico";

export default function CadastroMotivosVenda() {
  return (
    <CadastroMotivosGenerico
      icone={<Tag size={16} />}
      titulo="Motivos de venda de animal"
      descricao={<>Motivo comercial da venda de um animal (Lançamentos &gt; Compra/Venda &gt; Vender animal). Desative em vez de
        excluir para preservar o histórico das vendas já lançadas.</>}
      placeholderBusca="Buscar motivo de venda…"
      textoVazio="Nenhum motivo cadastrado ainda."
      fetchMotivos={fetchMotivosVenda}
      criarMotivo={criarMotivoVenda}
      atualizarMotivo={atualizarMotivoVenda}
    />
  );
}
