"use client";
import { MessageSquare } from "lucide-react";
import { PortalView } from "@/components/PortalView";

export default function PortalPage() {
  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <MessageSquare size={22} style={{ color: "var(--dourado-light)" }} /> Portal
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Comunicação interna — mensagens, e-mails e tarefas delegadas entre a equipe.
        </p>
      </div>
      <PortalView />
    </div>
  );
}
