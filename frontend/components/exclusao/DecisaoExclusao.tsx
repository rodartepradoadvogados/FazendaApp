"use client";
// Decisão proporcional ao risco (Fase 2). O SERVIDOR repete as exigências — a tela
// só mostra. baixo = botão; médio = motivo; alto = motivo + digitar a confirmação.
import { useState } from "react";
import { confirmarExclusao } from "@/lib/api";
import {
  riscoItem, exigeMotivo, exigeConfirmacao, confirmacaoEsperada, RISCO_TXT, porqueDe,
  type ImpactoExclusao,
} from "@/lib/exclusao";

export function DecisaoExclusao({ impacto, motivo, confirmacao, souAdmin, aoMotivo, aoConfirmacao, aoPronto, aoErro, aoVoltar }: {
  impacto: ImpactoExclusao;
  motivo: string;
  confirmacao: string;
  souAdmin: boolean;
  aoMotivo: (v: string) => void;
  aoConfirmacao: (v: string) => void;
  aoPronto: (r: { status: string; comprovante?: string; id?: number }) => void;
  aoErro: (m: string) => void;
  aoVoltar: () => void;
}) {
  const [enviando, setEnviando] = useState(false);

  // Bloqueado → nada a decidir.
  if ((impacto.bloqueia ?? []).length > 0) {
    return (
      <div className="exc-decisao">
        <p className="exc-bloqueado">Não dá para apagar enquanto houver bloqueio. Resolva o que está acima e tente de novo.</p>
        <button className="btn-secondary" onClick={aoVoltar}>Voltar</button>
      </div>
    );
  }

  const risco = riscoItem(impacto);
  const [rotulo, texto] = RISCO_TXT[risco];
  const pedeMotivo = exigeMotivo(risco, souAdmin);
  const pedeConfirmacao = exigeConfirmacao(risco);
  const esperado = confirmacaoEsperada(impacto.item.tipo, impacto.item.id);
  const porques = porqueDe([impacto]);

  const liberado =
    (!pedeMotivo || motivo.trim().length > 0) &&
    (!pedeConfirmacao || confirmacao.trim() === esperado);

  const confirmar = async () => {
    setEnviando(true);
    try {
      const r = await confirmarExclusao(impacto.item.tipo, impacto.item.id, motivo.trim() || undefined, confirmacao.trim() || undefined);
      aoPronto(r);
    } catch (e: any) {
      aoErro(e.message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="exc-decisao">
      <div className={`exc-risco exc-risco-${risco}`}>
        <strong>{rotulo}</strong>
        <p>{texto}</p>
        {porques.length > 0 && <p className="muted">Porque: {porques.join("; ")}.</p>}
      </div>

      {pedeMotivo && (
        <label className="exc-campo">
          Por que está apagando? <small>(fica na trilha)</small>
          <textarea className="exc-input" value={motivo} onChange={(e) => aoMotivo(e.target.value)} rows={2} />
        </label>
      )}

      {pedeConfirmacao && (
        <label className="exc-campo">
          Para confirmar, digite <b>{esperado}</b>
          <input className="exc-input" value={confirmacao} onChange={(e) => aoConfirmacao(e.target.value)} autoCapitalize="characters" spellCheck={false} />
        </label>
      )}

      <div className="exc-acoes">
        <button className="btn-primary" disabled={!liberado || enviando} onClick={confirmar}>
          {enviando ? "Apagando…" : "Apagar"}
        </button>
        <button className="btn-secondary" onClick={aoVoltar}>Voltar</button>
      </div>
    </div>
  );
}