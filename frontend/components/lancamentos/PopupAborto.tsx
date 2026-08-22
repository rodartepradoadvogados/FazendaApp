"use client";
import { useState } from "react";
import { Modal } from "@/components/Modal";
import { abrirLactacao } from "@/lib/api";

/**
 * Popup pós-aborto (perda de prenhez) — disparado tanto pelo 3º lançamento de
 * diagnóstico de gestação (ver FormDiagnostico) quanto pelo tipo de parto
 * "Aborto" (ver FormParto). Mesmo texto e mesma pergunta nos dois casos.
 *
 * A RESPOSTA, porém, tem dois destinos diferentes:
 *
 *  * `onResponder` informado (FormParto): o popup só devolve o sim/não e quem
 *    chamou grava tudo de uma vez em POST /reproducao/encerramento-gestacao —
 *    Parto do aborto, perda de prenhez no serviço certo e Lactacao com a data
 *    REAL do evento, numa transação só;
 *  * sem `onResponder` (FormDiagnostico): mantém o caminho antigo
 *    (`abrirLactacao`), que só grava `del_dias = 0`. É uma lactação de
 *    mentira, e por isso o FormParto saiu dele — mas trocar também o
 *    diagnóstico exige que aquele fluxo passe a saber a data do evento, o que
 *    fica para a rodada seguinte.
 */
export function PopupAborto({ numeroMatriz, onFechar, onResponder }: {
  numeroMatriz: string;
  onFechar: () => void;
  onResponder?: (abrirLactacao: boolean) => Promise<void> | void;
}) {
  const [processando, setProcessando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function responder(sim: boolean) {
    if (onResponder) {
      setProcessando(true); setErro(null);
      try {
        await onResponder(sim);
        onFechar();
      } catch (e: any) {
        setErro(e.message || "Erro ao registrar o aborto");
      } finally {
        setProcessando(false);
      }
      return;
    }
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
        {/* Com `onResponder`, "Não" NÃO é cancelar: o aborto é registrado do
            mesmo jeito, só não abre lactação. É a resposta à pergunta acima. */}
        <button className="btn-ghost" onClick={() => responder(false)} disabled={processando}>
          {onResponder ? "Não, só registrar o aborto" : "Não"}
        </button>
        <button className="btn-primary" onClick={() => responder(true)} disabled={processando}>
          {processando ? "Salvando…" : "Sim, abrir lactação"}
        </button>
      </div>
    </Modal>
  );
}
