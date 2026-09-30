"use client";
import { Lock } from "lucide-react";

// Aviso "Somente leitura" de Sanidade › Preventiva (fluxo aprovado no mockup
// fluxo-completo): vacina e exame são agendados e aplicados em Protocolos ou
// na Agenda, no dia — Sanidade só consulta.
export function FaixaPreventivoLeitura() {
  return (
    <div role="note" className="card mb-4" style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", borderLeft: "3px solid var(--dourado)" }}>
      <Lock size={16} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />
      <div style={{ flex: "1 1 280px", fontSize: "0.82rem" }}>
        <strong>Somente leitura.</strong>{" "}
        <span style={{ color: "var(--text-muted)" }}>
          Vacina e exame são agendados e aplicados em Protocolos ou na Agenda, no dia.
        </span>
      </div>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <a className="btn-primary" href="/protocolos?aba=aplicar" style={{ fontSize: "0.78rem", textDecoration: "none" }}>Abrir em Protocolos</a>
        <a className="btn-secondary" href="/agenda" style={{ fontSize: "0.78rem", textDecoration: "none" }}>Abrir na Agenda</a>
      </div>
    </div>
  );
}

// Link pequeno para linhas de tabela ("Abrir em Protocolos ▸").
export function LinkAbrirEmProtocolos({ aba = "acompanhamento" }: { aba?: "cadastro" | "aplicar" | "acompanhamento" | "concluidos" }) {
  return <a href={`/protocolos?aba=${aba}`} style={{ fontSize: "0.72rem", color: "var(--dourado-light)", whiteSpace: "nowrap" }}>Abrir em Protocolos ▸</a>;
}
