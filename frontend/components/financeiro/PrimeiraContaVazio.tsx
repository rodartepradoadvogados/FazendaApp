"use client";
// Estado vazio do Financeiro: fazenda sem nenhum lançamento ainda. Linguagem de cliente — nada de
// CSV, banco de dados ou provedor de deploy (Plano Financeiro §2.7). O dono ainda pode carregar
// o plano de contas inicial (POST /fazendas/{id}/financeiro/preparar, idempotente).
import { useState } from "react";
import { BarChart3 } from "lucide-react";
import { ehDono, getFazendaAtual, prepararFinanceiroFazenda } from "@/lib/api";

export function PrimeiraContaVazio({ onLancar, onPlanoCarregado }: { onLancar: () => void; onPlanoCarregado?: () => void }) {
  const fazendaId = getFazendaAtual()?.id ?? 0;
  const podePreparar = ehDono() && fazendaId > 0;
  const [carregando, setCarregando] = useState(false);
  const [msg, setMsg] = useState<{ texto: string; erro: boolean } | null>(null);

  async function carregarPlano() {
    setCarregando(true); setMsg(null);
    try {
      const r = await prepararFinanceiroFazenda(fazendaId);
      const texto = r.ja_preparado
        ? "O plano de contas já estava carregado."
        : r.plano_contas_carregado
          ? `Plano de contas carregado (${r.contas_criadas} ${r.contas_criadas === 1 ? "conta criada" : "contas criadas"}). Confira com o seu contador.`
          : "Nada a carregar agora.";
      setMsg({ texto, erro: false });
      onPlanoCarregado?.();
    } catch (e) {
      setMsg({ texto: (e as Error).message || "Não foi possível carregar o plano de contas agora. Tente de novo em instantes.", erro: true });
    } finally { setCarregando(false); }
  }

  return (
    <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
      <BarChart3 size={38} aria-hidden style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
      <p style={{ fontWeight: 700, fontSize: "1.05rem" }}>Lance sua primeira conta</p>
      <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", margin: "0.5rem auto 1.1rem", maxWidth: 480 }}>
        Quando houver contas a pagar, a receber ou pagas, o resumo, a DRE e o caixa da fazenda aparecem aqui.
        Comece lançando uma despesa ou uma receita.
      </p>
      <div style={{ display: "flex", gap: "0.6rem", justifyContent: "center", flexWrap: "wrap" }}>
        <button type="button" className="btn-primary" onClick={onLancar}>Lançar a primeira conta</button>
        {podePreparar && (
          <button type="button" className="btn-ghost" disabled={carregando} onClick={carregarPlano}>
            {carregando ? "Carregando…" : "Carregar plano de contas"}
          </button>
        )}
      </div>
      {msg && <p role={msg.erro ? "alert" : "status"} style={{ marginTop: "0.9rem", fontSize: "0.82rem", color: msg.erro ? "var(--red, #c0392b)" : "var(--text-muted)" }}>{msg.texto}</p>}
    </div>
  );
}
