"use client";
// Tela REBANHO do app de campo: painel único com todos os quadros (Animais,
// Lotes e os 10 indicadores) — sem seleção intermediária. Tocar em Animais ou
// Lotes abre a tela cheia correspondente; os demais quadros abrem o
// drill-down dentro do próprio Indicadores (ver esse arquivo).
// Movimentar e Baixar ficam na tela LANÇAR.
import { useEffect, useState } from "react";
import { MobVoltar } from "@/components/mobile/ui";
import Ficha from "@/components/mobile/rebanho/Ficha";
import Lotes from "@/components/mobile/rebanho/Lotes";
import Indicadores from "@/components/mobile/rebanho/Indicadores";

type Aba = "animais" | "lotes";
const TITULOS: Record<Aba, string> = { animais: "Animais", lotes: "Lotes" };

export default function Pagina() {
  const [aba, setAba] = useState<Aba | null>(null);
  const [numeroInicial, setNumeroInicial] = useState<string | null>(null);
  const [destacarInicial, setDestacarInicial] = useState<string | null>(null);

  // Chegou da Agenda com uma pendência de colostro/IgG (link /app/rebanho?numero=...&destacar=...).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const numero = params.get("numero");
    const destacar = params.get("destacar");
    if (numero) {
      setNumeroInicial(numero);
      setDestacarInicial(destacar);
      setAba("animais");
    }
  }, []);

  if (!aba) {
    return <Indicadores onAbrirAnimais={() => setAba("animais")} onAbrirLotes={() => setAba("lotes")} />;
  }

  return (
    <div>
      <MobVoltar titulo={TITULOS[aba]} onVoltar={() => setAba(null)} />
      {aba === "animais" && <Ficha numeroInicial={numeroInicial} destacarInicial={destacarInicial} />}
      {aba === "lotes" && <Lotes />}
    </div>
  );
}
