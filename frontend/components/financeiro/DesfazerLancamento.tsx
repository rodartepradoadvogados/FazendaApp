"use client";
// "Desfazer" o lançamento que acabou de ser salvo. Não é um caminho novo de exclusão: é o MESMO fluxo de
// Excluir lançamento (impacto → risco → motivo/confirmação → trilha; o operador gera pedido para o
// administrador), só que aberto na hora, com o lançamento já escolhido.
import { useEffect, useState } from "react";
import { Check, ClipboardList } from "lucide-react";
import { Modal } from "@/components/Modal";
import { ehAdmin, impactoExclusao } from "@/lib/api";
import type { ImpactoExclusao } from "@/lib/exclusao";
import { PainelImpacto } from "@/components/exclusao/PainelImpacto";
import { DecisaoExclusao } from "@/components/exclusao/DecisaoExclusao";

export function DesfazerLancamentoModal({ idConta, numero, onClose, onDesfeito }: {
  /** Id de QUALQUER linha do lançamento (parcela): a exclusão leva a nota inteira, com as parcelas. */
  idConta: number; numero: string; onClose: () => void; onDesfeito?: () => void;
}) {
  const [impacto, setImpacto] = useState<ImpactoExclusao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [motivo, setMotivo] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [resultado, setResultado] = useState<{ status: string; comprovante?: string; id?: number } | null>(null);
  // O modal só existe depois de um clique (nunca no 1º render do servidor): ler o papel direto é seguro.
  const [souAdmin] = useState(() => ehAdmin());
  useEffect(() => {
    impactoExclusao("financeiro", String(idConta)).then((i) => setImpacto(i as ImpactoExclusao)).catch((e) => setErro(e.message || "Não foi possível calcular o que seria desfeito."));
  }, [idConta]);

  return (
    <Modal title={`Desfazer o lançamento ${numero}`} onClose={onClose} width="760px">
      <div className="exc-page" style={{ padding: 0 }}>
        {erro && <div className="alert-critico mb-3" role="alert"><span>{erro}</span></div>}
        {resultado ? (
          <section className="exc-resultado" aria-live="polite">
            {resultado.status === "excluido" ? (
              <>
                <div className="exc-ok"><Check size={20} /></div>
                <h2 className="exc-h">Lançamento desfeito</h2>
                {resultado.comprovante && <p className="exc-comprovante">Comprovante <b>{resultado.comprovante}</b></p>}
                <p className="muted">As parcelas, os itens e a entrada no estoque deste lançamento foram revertidos. Ficou registrado na trilha.</p>
              </>
            ) : (
              <>
                <div className="exc-ok"><ClipboardList size={20} /></div>
                <h2 className="exc-h">{resultado.status === "ja_pedido" ? "Você já tinha pedido" : "Pedido enviado ao administrador"}</h2>
                <p className="muted">O lançamento continua valendo até o administrador decidir. Acompanhe em Excluir lançamento › Meus pedidos.</p>
              </>
            )}
            <button type="button" className="btn-primary" onClick={onClose}>Fechar</button>
          </section>
        ) : !impacto ? (
          !erro && <p className="muted" role="status">Calculando o que será desfeito…</p>
        ) : (
          <div className="exc-impacto">
            <PainelImpacto impacto={impacto} />
            <DecisaoExclusao
              impacto={impacto} motivo={motivo} confirmacao={confirmacao} souAdmin={souAdmin}
              aoMotivo={setMotivo} aoConfirmacao={setConfirmacao}
              aoPronto={(r) => { setResultado(r); if (r.status === "excluido") onDesfeito?.(); }}
              aoErro={setErro} aoVoltar={onClose}
            />
          </div>
        )}
      </div>
    </Modal>
  );
}
