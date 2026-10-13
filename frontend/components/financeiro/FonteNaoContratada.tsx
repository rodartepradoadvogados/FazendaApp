"use client";
// Relatório cuja fonte de dados não faz parte do contrato da fazenda (Plano Financeiro §2.7).
// Aparece no lugar da tela (link salvo ?sub=…), sem número nenhum: R$ 0 seria informação
// contábil falsa. O menu já esconde esses relatórios (relatoriosVisiveis).
import { Lock } from "lucide-react";

export function FonteNaoContratada({ texto, onVoltar }: { texto: string; onVoltar?: () => void }) {
  return (
    <div className="card" role="status" style={{ textAlign: "center", padding: "2.5rem 1.5rem" }}>
      <Lock size={32} aria-hidden style={{ color: "var(--text-muted)", margin: "0 auto 0.9rem" }} />
      <p style={{ fontWeight: 700, marginBottom: "0.4rem" }}>Relatório indisponível neste contrato</p>
      <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", maxWidth: 520, margin: "0 auto" }}>{texto}</p>
      {onVoltar && (
        <button type="button" className="btn-ghost" style={{ marginTop: "1rem" }} onClick={onVoltar}>Voltar ao Painel do dono</button>
      )}
    </div>
  );
}
