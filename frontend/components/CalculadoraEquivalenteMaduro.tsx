"use client";
// Calculadora avulsa de equivalente maduro — NÃO persiste nada (mesmo padrão
// de POST /financeiro/calcular-juros + RecalculoJuros em
// contador/PainelExtraordinario.tsx). Serve para avaliar um animal de fora
// (ex.: compra) sem sujar a base do rebanho: os pontos entram por DEL, não
// por data de calendário, porque quem avalia uma vaca de fora normalmente
// não sabe a data exata do parto dela.
import { useState } from "react";
import { calcularEquivalenteMaduro, type TrioEquivalenteMaduro } from "@/lib/api";
import { TrioEquivalenteMaduroView, NotaExplicativaEM } from "@/components/TrioEquivalenteMaduro";

const estiloInput: React.CSSProperties = {
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.85rem", width: "100%",
};
const estiloLabel: React.CSSProperties = {
  fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem",
  textTransform: "uppercase", letterSpacing: "0.05em",
};
const estiloBotao: React.CSSProperties = {
  background: "var(--vinho, #7a2632)", color: "#fff", border: "none", borderRadius: "var(--r-sm)",
  padding: "0.5rem 0.9rem", fontSize: "0.8rem", fontWeight: 700, cursor: "pointer",
};

type PontoForm = { del_dias: string; producao_kg: string };

export function CalculadoraEquivalenteMaduro() {
  const [ordemParto, setOrdemParto] = useState("1");
  const [delSecagem, setDelSecagem] = useState("");
  const [pontos, setPontos] = useState<PontoForm[]>([{ del_dias: "", producao_kg: "" }, { del_dias: "", producao_kg: "" }]);
  const [resultado, setResultado] = useState<TrioEquivalenteMaduro | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const atualizarPonto = (i: number, campo: keyof PontoForm, valor: string) => {
    setPontos((ps) => ps.map((p, idx) => (idx === i ? { ...p, [campo]: valor } : p)));
  };

  const calcular = async (e: React.FormEvent) => {
    e.preventDefault();
    setCalculando(true); setErro(null); setResultado(null);
    try {
      const pontosValidos = pontos
        .filter((p) => p.del_dias !== "" && p.producao_kg !== "")
        .map((p) => ({ del_dias: Number(p.del_dias), producao_kg: Number(p.producao_kg) }));
      const r = await calcularEquivalenteMaduro({
        ordem_parto: Number(ordemParto),
        pontos: pontosValidos,
        del_secagem: delSecagem === "" ? null : Number(delSecagem),
      });
      setResultado(r);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setCalculando(false);
    }
  };

  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem" }}>
      <p style={{ margin: "0 0 0.3rem", fontWeight: 700, fontSize: "0.85rem" }}>Calculadora de equivalente maduro</p>
      <p style={{ margin: "0 0 0.9rem", fontSize: "0.78rem", color: "var(--text-muted)" }}>
        Simula o equivalente maduro de um animal SEM gravar nada — útil para avaliar uma vaca de fora (ex.: compra) com
        os fatores já calibrados neste rebanho. Informe pelo menos dois pontos de controle (DEL + produção do dia).
      </p>
      <form onSubmit={calcular} style={{ display: "grid", gap: "0.7rem" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(8rem, 1fr))", gap: "0.7rem" }}>
          <div>
            <label style={estiloLabel}>Ordem de parto</label>
            <input type="number" min={1} style={estiloInput} value={ordemParto} onChange={(e) => setOrdemParto(e.target.value)} required />
          </div>
          <div>
            <label style={estiloLabel}>DEL de secagem (opcional)</label>
            <input
              type="number" min={0} style={estiloInput} value={delSecagem}
              onChange={(e) => setDelSecagem(e.target.value)}
              placeholder="em andamento"
            />
          </div>
        </div>

        <div>
          <label style={estiloLabel}>Pontos de controle (DEL, produção do dia em kg)</label>
          {pontos.map((p, i) => (
            <div key={i} style={{ display: "flex", gap: "0.5rem", marginBottom: "0.4rem" }}>
              <input
                type="number" min={0} style={estiloInput} placeholder="DEL (dias)"
                value={p.del_dias} onChange={(e) => atualizarPonto(i, "del_dias", e.target.value)}
              />
              <input
                type="number" step="0.1" min={0} style={estiloInput} placeholder="Produção (kg)"
                value={p.producao_kg} onChange={(e) => atualizarPonto(i, "producao_kg", e.target.value)}
              />
              {pontos.length > 2 && (
                <button
                  type="button" onClick={() => setPontos((ps) => ps.filter((_, idx) => idx !== i))}
                  style={{ background: "none", border: "none", color: "var(--red)", cursor: "pointer", fontSize: "0.8rem" }}
                >×</button>
              )}
            </div>
          ))}
          <button
            type="button" onClick={() => setPontos((ps) => [...ps, { del_dias: "", producao_kg: "" }])}
            style={{ background: "none", border: "1px dashed var(--border)", borderRadius: "var(--r-sm)", padding: "0.25rem 0.6rem", fontSize: "0.75rem", cursor: "pointer", color: "var(--text-muted)" }}
          >+ adicionar ponto</button>
        </div>

        <div>
          <button type="submit" disabled={calculando} style={{ ...estiloBotao, opacity: calculando ? 0.6 : 1 }}>
            {calculando ? "Calculando…" : "Calcular"}
          </button>
        </div>
      </form>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {resultado && (
        <div style={{ marginTop: "1rem" }}>
          <TrioEquivalenteMaduroView trio={resultado} />
          <NotaExplicativaEM />
        </div>
      )}
    </div>
  );
}
