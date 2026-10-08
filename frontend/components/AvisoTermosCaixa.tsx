"use client";
// Aviso no Fechamento da folha: retenção do caixa dos funcionários rodando sem o
// termo de autorização anexado. Some quando não há pendência (ou não é admin).
import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { ehAdmin, fetchPendenciasCaixa } from "@/lib/api";

export default function AvisoTermosCaixa() {
  const [nomes, setNomes] = useState<string[]>([]);
  useEffect(() => {
    if (!ehAdmin()) return;
    fetchPendenciasCaixa().then((d) => setNomes(d.termos_pendentes.map((t) => t.nome))).catch(() => {});
  }, []);
  if (!nomes.length) return null;
  return (
    <div role="status" className="card" style={{
      border: "1px solid var(--st-logo-line)", borderLeft: "3px solid var(--st-logo-line)", background: "var(--st-logo-bg)",
      padding: "0.6rem 0.8rem", marginBottom: "0.9rem", fontSize: "0.8rem", color: "var(--text)",
    }}>
      <AlertTriangle size={14} aria-hidden style={{ display: "inline", marginRight: 6, verticalAlign: "-2px", color: "var(--st-logo-fg)" }} />
      <b>Pendência no fechamento:</b> {nomes.length === 1 ? "1 retenção" : `${nomes.length} retenções`} do caixa dos funcionários
      {" "}sem o termo de autorização anexado ({nomes.join(", ")}). Anexe em{" "}
      <a href="/financeiro?ir=caixa_funcionarios" style={{ color: "var(--text-accent)", textDecoration: "underline", fontWeight: 600 }}>Caixa dos funcionários</a>.
    </div>
  );
}
