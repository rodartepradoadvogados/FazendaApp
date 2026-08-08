"use client";
// Checklist guiado de primeiro acesso — aparece na Capa até o usuário
// concluir os 4 passos ou dispensar. Ver backend/fazenda/api/routers/onboarding.py.
import { useEffect, useState } from "react";
import { CheckCircle2, Circle, X, ArrowRight } from "lucide-react";
import { fetchOnboarding, concluirPassoOnboarding, dispensarOnboarding, type OnboardingEstado } from "@/lib/api";

export function OnboardingChecklist() {
  const [estado, setEstado] = useState<OnboardingEstado | null>(null);

  useEffect(() => { fetchOnboarding().then(setEstado).catch(() => {}); }, []);

  if (!estado || estado.dispensado || estado.tudo_concluido) return null;

  const concluidos = estado.passos.filter((p) => p.concluido).length;

  async function marcarFeito(chave: string) {
    try { setEstado(await concluirPassoOnboarding(chave)); } catch { /* mantém o estado anterior */ }
  }
  async function dispensar() {
    try { setEstado(await dispensarOnboarding()); } catch { /* idem */ }
  }

  return (
    <div className="mb-4" style={{ background: "var(--surface-2)", border: "1px solid var(--dourado)", borderRadius: "var(--r-sm)", padding: "0.9rem 1.1rem" }}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <p style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text)" }}>Primeiros passos</p>
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{concluidos} de {estado.passos.length} concluídos</p>
        </div>
        <button onClick={dispensar} className="btn-ghost" aria-label="Dispensar checklist" style={{ padding: "0.2rem" }}>
          <X size={15} />
        </button>
      </div>
      <div className="flex flex-col gap-1.5">
        {estado.passos.map((p) => (
          <div key={p.chave} className="flex items-center gap-2" style={{ fontSize: "0.85rem" }}>
            <button
              onClick={() => marcarFeito(p.chave)}
              disabled={p.concluido}
              aria-label={p.concluido ? "Concluído" : "Marcar como feito"}
              style={{ display: "flex", background: "none", border: "none", padding: 0, cursor: p.concluido ? "default" : "pointer" }}
            >
              {p.concluido
                ? <CheckCircle2 size={17} style={{ color: "var(--green-light)" }} />
                : <Circle size={17} style={{ color: "var(--text-muted)" }} />}
            </button>
            <a href={p.rota} style={{
              color: p.concluido ? "var(--text-muted)" : "var(--text)",
              textDecoration: p.concluido ? "line-through" : "none",
              display: "flex", alignItems: "center", gap: "0.3rem",
            }}>
              {p.label}
              {!p.concluido && <ArrowRight size={13} style={{ color: "var(--dourado-light)" }} />}
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
