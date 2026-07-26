"use client";
import Link from "next/link";
import { Lock } from "lucide-react";

const COR = { cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8", dourado: "#e8c256" };

export default function CofreAcessoCowData() {
  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Cofre de acesso</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem", maxWidth: "42rem" }}>
        Hoje, qualquer conta "admin" (ver Equipe CowData) enxerga os dados de qualquer fazenda pelo banco
        de dados direto — não existe ainda um fluxo de solicitação/aprovação de acesso, sessão com prazo,
        log de auditoria append-only nem "campo lacrado" que nem o dono consiga apagar. Esse é
        precisamente o gap descrito na proposta de separação fazenda/empresa (Fase 1 em diante:
        access-request, break-glass, log de auditoria). Esta tela vai virar o painel de controle
        desse fluxo quando ele existir.
      </p>
      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "2rem", textAlign: "center", color: COR.mudo, display: "flex", flexDirection: "column", alignItems: "center", gap: "0.6rem" }}>
        <Lock size={28} />
        Em construção — depende da Fase 1 da separação fazenda/empresa.
      </div>
      <p style={{ fontSize: "0.78rem", marginTop: "1rem" }}>
        <Link href="/painel-cowdata/equipe" style={{ color: COR.dourado }}>Ver quem tem acesso hoje →</Link>
      </p>
    </div>
  );
}
