"use client";
import { useState } from "react";
import { CalendarClock } from "lucide-react";
import { ajustarProximaAplicacaoBst } from "@/lib/api";

const inputStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.85rem",
};

function fmtBr(iso: string | null) {
  return iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—";
}

/**
 * Conteúdo do painel de ajuste manual da "próxima aplicação de BST" —
 * reaproveitado tanto no card clicável de Produção > Relatórios de BST
 * quanto na caixa sempre visível de Lançamentos > Produção > BST.
 */
export function PainelAjustarProximaAplicacaoBst({
  proximaVisitaBst, intervaloBstDias, onAjustado,
}: {
  proximaVisitaBst: string | null;
  intervaloBstDias: number | null;
  onAjustado: () => void;
}) {
  const [novaData, setNovaData] = useState(proximaVisitaBst || "");
  const [modo, setModo] = useState<"intervalo" | "referencia" | "">("");
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const mudouData = !!novaData && novaData !== proximaVisitaBst;

  const confirmar = async () => {
    if (!novaData || !modo) return;
    setCarregando(true);
    setErro(null);
    setSucesso(null);
    try {
      const r = await ajustarProximaAplicacaoBst(novaData, modo);
      setSucesso(
        modo === "intervalo"
          ? `Pronto — o intervalo entre aplicações agora é de ${r.novo_intervalo} dias.`
          : `Pronto — a contagem passa a valer a partir de ${fmtBr(novaData)}.`
      );
      setModo("");
      onAjustado();
    } catch (e: any) {
      setErro(e.message || "Não foi possível ajustar a próxima aplicação.");
    } finally {
      setCarregando(false);
    }
  };

  return (
    <div className="space-y-3">
      <p style={{ fontSize: "0.85rem", margin: 0 }}>
        Data da aplicação de BST — próxima aplicação agendada: <strong>{fmtBr(proximaVisitaBst)}</strong>;
        {" "}intervalo entre aplicações: <strong>{intervaloBstDias ?? "—"} dias</strong>.
      </p>

      <div>
        <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Definir nova data de aplicação</label><br />
        <input type="date" style={inputStyle} value={novaData} onChange={(e) => { setNovaData(e.target.value); setModo(""); setSucesso(null); }} />
      </div>

      {mudouData && (
        <div className="card" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.8rem", margin: "0 0 0.6rem" }}>
            Mudar a próxima aplicação para <strong>{fmtBr(novaData)}</strong> altera o intervalo desde a última
            aplicação e o prazo de {intervaloBstDias ?? "—"} dias definido em Parâmetros. O que você deseja?
          </p>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", marginBottom: "0.4rem", cursor: "pointer" }}>
            <input type="radio" name="modo-ajuste-bst" checked={modo === "intervalo"} onChange={() => setModo("intervalo")} />
            1) Definir novo intervalo entre aplicações
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", marginBottom: "0.8rem", cursor: "pointer" }}>
            <input type="radio" name="modo-ajuste-bst" checked={modo === "referencia"} onChange={() => setModo("referencia")} />
            2) Considerar essa nova data a referência para a contagem de {intervaloBstDias ?? "—"} dias definidos em parâmetros
          </label>
          {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", margin: "0 0 0.6rem" }}>{erro}</p>}
          <button className="btn-primary" disabled={!modo || carregando} onClick={confirmar}>
            {carregando ? "…" : "Salvar ajuste"}
          </button>
        </div>
      )}

      {!mudouData && erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
      {!mudouData && sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.82rem" }}>{sucesso}</p>}
    </div>
  );
}

/** Card clicável "Próxima aplicação BST" — usado em Produção > Relatórios de BST. */
export function CaixaProximaAplicacaoBst({ proximaVisitaBst, onClick }: { proximaVisitaBst: string | null; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="card"
      style={{ textAlign: "left", cursor: "pointer", width: "100%", border: "1px solid var(--border)" }}
      title="Clique para ajustar manualmente a próxima aplicação"
    >
      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.3rem" }}>
        <CalendarClock size={12} /> Próxima aplicação BST
      </div>
      <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{fmtBr(proximaVisitaBst)}</div>
    </button>
  );
}
