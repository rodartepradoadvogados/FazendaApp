"use client";
import { HeartCrack } from "lucide-react";
import { fetchMotivosBaixaCadastro, criarMotivoBaixa, atualizarMotivoBaixa } from "@/lib/api";
import CadastroMotivosGenerico from "@/components/CadastroMotivosGenerico";

export default function CadastroMotivosBaixa() {
  return (
    <CadastroMotivosGenerico
      icone={<HeartCrack size={16} />}
      titulo="Motivos de baixa"
      descricao={<>Causa específica da baixa (Rebanho &gt; Baixar animal), usada no select quando o motivo geral é "doença" — cobre
        também outras causas comuns (acidente, roubo, idade avançada, etc.). Desative em vez de excluir para preservar
        o histórico das baixas já lançadas.</>}
      placeholderBusca="Buscar motivo de baixa…"
      textoVazio="Nenhum motivo cadastrado ainda."
      fetchMotivos={fetchMotivosBaixaCadastro}
      criarMotivo={criarMotivoBaixa}
      atualizarMotivo={atualizarMotivoBaixa}
    />
  );
}
