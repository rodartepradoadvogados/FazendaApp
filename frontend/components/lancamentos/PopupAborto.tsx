"use client";
import { useState } from "react";
import { Modal } from "@/components/Modal";
import { abrirLactacao } from "@/lib/api";

/**
 * Popup pós-aborto (perda de prenhez) — disparado tanto pelo 3º lançamento de
 * diagnóstico de gestação (ver FormDiagnostico) quanto pelo tipo de parto
 * "Aborto" (ver FormParto). Mesmo texto e mesma ação em ambos os casos.
 */
export function PopupAborto({ numeroMatriz, onFechar }: { numeroMatriz: string; onFechar: () => void }) {
  const [processando, setProcessando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function responder(sim: boolean) {
    if (!sim) { onFechar(); return; }
    setProcessando(true); setErro(null);
    try {
      await abrirLactacao(numeroMatriz);
      onFechar();
    } catch (e: any) {
      setErro(e.message || "Erro ao abrir lactação");
    } finally {
      setProcessando(false);
    }
  }

  return (
    <Modal title="Perda de prenhez (aborto)" onClose={() => responder(false)} width="440px" zIndex={95}>
      <p style={{ fontSize: "0.85rem" }}>
        O animal <strong>{numeroMatriz}</strong> voltará ao status <strong>vazio, em observação</strong>, para ser
        observado na próxima visita reprodutiva.
      </p>
      <p style={{ fontSize: "0.85rem", marginTop: "0.6rem" }}>
        Deseja abrir lactação para o animal <strong>{numeroMatriz}</strong>?
      </p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center justify-end gap-2 mt-3">
        <button className="btn-ghost" onClick={() => responder(false)} disabled={processando}>Não</button>
        <button className="btn-primary" onClick={() => responder(true)} disabled={processando}>
          {processando ? "Abrindo…" : "Sim, abrir lactação"}
        </button>
      </div>
    </Modal>
  );
}
