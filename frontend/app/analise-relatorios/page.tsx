"use client";
import { FileBarChart, Hammer } from "lucide-react";

export default function AnaliseRelatoriosPage() {
  return (
    <div className="px-6 pt-6">
      <div className="p-6 animate-in">
        <div className="mb-4">
          <h1 className="text-2xl font-bold flex items-center gap-2"><FileBarChart size={22} style={{ color: "var(--dourado)" }} /> Relatórios</h1>
        </div>
        <div className="card" style={{ textAlign: "center", padding: "3rem 1.5rem" }}>
          <Hammer size={32} style={{ color: "var(--text-muted)", marginBottom: "0.8rem" }} />
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", margin: 0 }}>Esta seção está em construção.</p>
        </div>
      </div>
    </div>
  );
}
