"use client";
import { Briefcase } from "lucide-react";
import ConsultorView from "@/components/ConsultorView";

export default function ConsultorPage() {
  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Briefcase size={22} style={{ color: "var(--dourado-light)" }} /> Consultor
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Produto independente do consultor — fazendas gerenciadas por importação de planilha e modo Simulação.
        </p>
      </div>
      <ConsultorView />
    </div>
  );
}
