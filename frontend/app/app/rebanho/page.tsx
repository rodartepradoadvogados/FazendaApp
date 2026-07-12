"use client";
// Tela REBANHO do app de campo: ficha do animal (consulta).
// Movimentar e Baixar animal foram para a tela LANÇAR.
import { MobTitulo } from "@/components/mobile/ui";
import Ficha from "@/components/mobile/rebanho/Ficha";

export default function Pagina() {
  return (
    <div>
      <MobTitulo>Rebanho</MobTitulo>
      <Ficha />
    </div>
  );
}
