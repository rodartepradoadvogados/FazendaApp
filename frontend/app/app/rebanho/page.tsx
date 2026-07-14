"use client";
// Tela REBANHO do app de campo: duas sub-abas — Animais (ficha do animal,
// consulta) e Lotes (Composição / Indicadores).
// Movimentar e Baixar ficam na tela LANÇAR.
import { useState } from "react";
import { PawPrint, LayoutGrid } from "lucide-react";
import { MobTitulo, MobVoltar } from "@/components/mobile/ui";
import { GradeAcoes } from "@/components/mobile/lancar/comum";
import Ficha from "@/components/mobile/rebanho/Ficha";
import Lotes from "@/components/mobile/rebanho/Lotes";

type Aba = "animais" | "lotes";
const TITULOS: Record<Aba, string> = { animais: "Animais", lotes: "Lotes" };

export default function Pagina() {
  const [aba, setAba] = useState<Aba | null>(null);

  if (!aba) {
    return (
      <div>
        <MobTitulo>Rebanho</MobTitulo>
        <GradeAcoes
          opcoes={[
            { id: "animais", label: "Animais", icone: <PawPrint size={28} />, cor: "var(--mob-vinho)" },
            { id: "lotes", label: "Lotes", icone: <LayoutGrid size={28} />, cor: "var(--mob-azul)" },
          ]}
          onEscolher={(id) => setAba(id as Aba)}
        />
      </div>
    );
  }

  return (
    <div>
      <MobVoltar titulo={TITULOS[aba]} onVoltar={() => setAba(null)} />
      {aba === "animais" && <Ficha />}
      {aba === "lotes" && <Lotes />}
    </div>
  );
}
