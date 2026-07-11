"use client";
import { CheckCheck } from "lucide-react";
import { AprovacoesView } from "@/components/AprovacoesView";

export default function AprovacoesPage() {
  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <CheckCheck size={22} style={{ color: "var(--dourado-light)" }} /> Aprovações
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Lançamentos de campo enviados pelo Telegram, aguardando sua aprovação.
        </p>
      </div>
      <AprovacoesView />
    </div>
  );
}
