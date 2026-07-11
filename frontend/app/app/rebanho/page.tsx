"use client";
// Tela REBANHO do app de campo: três abas em pílula no topo
// (Ficha do Animal · Movimentar · Baixar).
import { useState } from "react";
import { MobTitulo } from "@/components/mobile/ui";
import Ficha from "@/components/mobile/rebanho/Ficha";
import Movimentar from "@/components/mobile/rebanho/Movimentar";
import Baixar from "@/components/mobile/rebanho/Baixar";

type Aba = "ficha" | "movimentar" | "baixar";
const ABAS: { chave: Aba; rotulo: string }[] = [
  { chave: "ficha", rotulo: "Ficha do Animal" },
  { chave: "movimentar", rotulo: "Movimentar" },
  { chave: "baixar", rotulo: "Baixar" },
];

export default function Pagina() {
  const [aba, setAba] = useState<Aba>("ficha");

  return (
    <div>
      <MobTitulo>Rebanho</MobTitulo>

      <div style={{ display: "flex", gap: "0.5rem", overflowX: "auto", marginBottom: "1rem", paddingBottom: "0.2rem" }}>
        {ABAS.map((a) => (
          <button key={a.chave} type="button" className={`mob-pill${aba === a.chave ? " ativa" : ""}`}
            style={{ whiteSpace: "nowrap", flexShrink: 0 }} onClick={() => setAba(a.chave)}>
            {a.rotulo}
          </button>
        ))}
      </div>

      {aba === "ficha" && <Ficha />}
      {aba === "movimentar" && <Movimentar />}
      {aba === "baixar" && <Baixar />}
    </div>
  );
}
