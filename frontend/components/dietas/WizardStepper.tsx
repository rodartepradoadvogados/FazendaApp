"use client";
import { Lock } from "lucide-react";

export const ETAPAS_WIZARD: { n: number; titulo: string; desabilitada?: boolean }[] = [
  { n: 1, titulo: "Banco de alimentos" },
  { n: 2, titulo: "Animal / lote" },
  { n: 3, titulo: "Exigências" },
  { n: 4, titulo: "Balanço ao vivo" },
  { n: 5, titulo: "Energia" },
  { n: 6, titulo: "Proteína · PDR/PNDR" },
  { n: 7, titulo: "Carboidratos e fibra" },
  { n: 8, titulo: "Modelo ruminal", desabilitada: true },
  { n: 9, titulo: "Aminoácidos", desabilitada: true },
  { n: 10, titulo: "Relatório final" },
];

export function WizardStepper({ etapaAtual, onSelecionar }: { etapaAtual: number; onSelecionar: (n: number) => void }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
      {ETAPAS_WIZARD.map((e) => {
        const ativa = e.n === etapaAtual;
        const desabilitada = !!e.desabilitada;
        return (
          <button
            key={e.n}
            type="button"
            disabled={desabilitada}
            title={desabilitada ? "Chega numa fase futura do módulo de Formulação de Dietas" : `Etapa ${e.n} — ${e.titulo}`}
            onClick={() => !desabilitada && onSelecionar(e.n)}
            style={{
              display: "flex", alignItems: "center", gap: "0.35rem",
              padding: "0.4rem 0.7rem", borderRadius: "var(--r-sm)", fontSize: "0.76rem", fontWeight: 600,
              cursor: desabilitada ? "not-allowed" : "pointer",
              border: `1px solid ${ativa ? "var(--gold)" : "var(--border)"}`,
              background: ativa ? "color-mix(in srgb, var(--gold) 16%, transparent)" : "var(--surface)",
              color: desabilitada ? "var(--text-muted)" : ativa ? "var(--gold-deep)" : "var(--text)",
              opacity: desabilitada ? 0.55 : 1,
              whiteSpace: "nowrap",
            }}
          >
            <span style={{
              display: "inline-flex", alignItems: "center", justifyContent: "center", width: "1.1rem", height: "1.1rem",
              borderRadius: "50%", fontSize: "0.65rem", fontWeight: 700,
              background: ativa ? "var(--gold)" : "var(--surface-2)", color: ativa ? "var(--wine)" : "var(--text-muted)",
            }}>
              {e.n}
            </span>
            {e.titulo}
            {desabilitada && <Lock size={11} />}
          </button>
        );
      })}
    </div>
  );
}
