"use client";
import { Bot } from "lucide-react";

const COR = { cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8" };

export default function ProdutoRobosCowData() {
  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Produto e robôs</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem", maxWidth: "42rem" }}>
        Status das automações do próprio produto — robô de publicação Milknews, backup automático,
        despacho de push. Hoje esses status só existem em log/console do servidor; agrupar aqui é
        trabalho futuro.
      </p>
      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "2rem", textAlign: "center", color: COR.mudo, display: "flex", flexDirection: "column", alignItems: "center", gap: "0.6rem" }}>
        <Bot size={28} />
        Em construção.
      </div>
    </div>
  );
}
