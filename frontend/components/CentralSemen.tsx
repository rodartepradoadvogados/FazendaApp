"use client";
import { useState } from "react";
import { Dna, SlidersHorizontal } from "lucide-react";
import CadastroEstoqueSemen from "./CadastroEstoqueSemen";
import CadastroTouros from "./CadastroTouros";
import CadastroSemenMinimo from "./CadastroSemenMinimo";

const ABAS = [
  ["estoque-semen", "Estoque de sêmen", Dna],
  ["touros", "Touros (NAAB)", Dna],
  ["estoque-minimo", "Estoque mínimo", SlidersHorizontal],
] as const;
// Reexportado para o Cadastro compor a árvore de sub-navegação (Configurações
// › Cadastro › Central de Sêmen › estas 2 abas) sem duplicar rótulos/ícones.
export type AbaCentralSemen = (typeof ABAS)[number][0];
export const ABAS_CENTRAL_SEMEN = ABAS;

// Une o estoque de sêmen da própria fazenda (CadastroEstoqueSemen) e o
// catálogo genético NAAB (CadastroTouros) numa única aba — mesma origem de
// dados que o cascateamento em Rebanho › Touros já unificava conceitualmente.
export default function CentralSemen({ abaControlada, onAbaChange }: {
  abaControlada?: AbaCentralSemen; onAbaChange?: (id: AbaCentralSemen) => void;
} = {}) {
  const [abaInterna, setAbaInterna] = useState<AbaCentralSemen>("estoque-semen");
  const aba = abaControlada ?? abaInterna;

  return (
    <div>
      {aba === "estoque-semen" && <CadastroEstoqueSemen />}
      {aba === "touros" && <CadastroTouros />}
      {aba === "estoque-minimo" && <CadastroSemenMinimo />}
    </div>
  );
}
