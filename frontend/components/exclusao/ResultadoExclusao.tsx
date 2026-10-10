"use client";
// Resultado (Fase 2) — comprovante para o admin; "pedido enviado" para o operador.
import { Check, ClipboardList } from "lucide-react";

export function ResultadoExclusao({ resultado, aoReiniciar }: {
  resultado: { status: string; comprovante?: string; id?: number } | null;
  aoReiniciar: () => void;
}) {
  if (!resultado) return null;

  const ehExcluido = resultado.status === "excluido";
  const ehSolicitado = ["solicitado", "ja_pedido", "apoiado"].includes(resultado.status);

  return (
    <section className="exc-resultado" aria-live="polite">
      {ehExcluido && (
        <>
          <div className="exc-ok"><Check size={20} /></div>
          <h2 className="exc-h">Excluído</h2>
          {resultado.comprovante && <p className="exc-comprovante">Comprovante <b>{resultado.comprovante}</b></p>}
          <p className="muted">Ficou registrado na trilha: quem, quando e o quê.</p>
        </>
      )}
      {ehSolicitado && (
        <>
          <div className="exc-ok"><ClipboardList size={20} /></div>
          <h2 className="exc-h">{resultado.status === "ja_pedido" ? "Você já tinha pedido" : "Pedido enviado"}</h2>
          <p className="muted">O administrador decide. Acompanhe em Meus pedidos.</p>
        </>
      )}
      <button className="btn-primary" onClick={aoReiniciar}>Apagar outro</button>
    </section>
  );
}