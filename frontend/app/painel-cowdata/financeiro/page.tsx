"use client";
import { useEffect, useState } from "react";
import { TrendingUp, Wallet } from "lucide-react";
import { fetchResumoCowData, type ResumoCowData } from "@/lib/api";

const COR = { cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8", verde: "#3ecf8e", vermelho: "#e05c5c" };

export default function FinanceiroCowData() {
  const [resumo, setResumo] = useState<ResumoCowData | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchResumoCowData().then(setResumo).catch((e) => setErro(e.message)); }, []);

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Financeiro CowData</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem" }}>
        Receita (MRR) e despesas da própria empresa CowData.
      </p>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", marginBottom: "1.8rem" }}>
        <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "1.1rem 1.3rem", flex: "1 1 12rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em", color: COR.mudo, marginBottom: "0.5rem" }}>
            <TrendingUp size={13} /> MRR
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, color: COR.verde, fontVariantNumeric: "tabular-nums" }}>
            {resumo ? `R$ ${resumo.mrr.toFixed(2)}` : "—"}
          </div>
        </div>
        <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "1.1rem 1.3rem", flex: "1 1 12rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em", color: COR.mudo, marginBottom: "0.5rem" }}>
            <Wallet size={13} /> Despesas do mês
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, color: "#e8ecf5" }}>—</div>
        </div>
      </div>

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "1.4rem", textAlign: "center", color: COR.mudo, fontSize: "0.85rem" }}>
        Lançamento de despesas da própria CowData (aluguel de servidor, ferramentas, etc.) — em construção.
        Por ora, o MRR acima já é real (soma dos contratos ativos, ver Assinaturas).
      </div>
    </div>
  );
}
