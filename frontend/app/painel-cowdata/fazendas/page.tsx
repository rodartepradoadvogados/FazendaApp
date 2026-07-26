"use client";
// Reaproveita o componente já existente (cadastro de fazenda, plano/módulos,
// contrato-modelo, anexos e assinatura ZapSign — ver Configurações) em vez
// de duplicar essa tela dentro do Painel CowData.
import FazendasAdmin from "@/components/FazendasAdmin";

export default function FazendasCowData() {
  return (
    <div className="animate-in">
      <FazendasAdmin />
    </div>
  );
}
