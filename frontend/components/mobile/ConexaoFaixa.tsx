"use client";
// Faixa de conexão do app de campo — indicador PERSISTENTE (sempre montado,
// dentro do cabeçalho fixo — ver app/app/layout.tsx) do estado da fila
// offline (lib/offline.ts): online/sincronizando/offline/pendente. Só LÊ o
// estado que a fila já mantém (useConectividadeReal, usePendentes,
// useSincProgresso) — nenhuma lógica de fila/retry é tocada aqui.
//
// 4 estados, do mais urgente para o mais discreto:
//  1. sincronizando  — barra de progresso real ("3 de 8"), não um spinner
//     genérico (ver useSincProgresso em lib/offline.ts).
//  2. offline        — servidor inalcançável agora (ping real, não só a
//     rádio do aparelho — useConectividadeReal).
//  3. pendente       — online, mas a fila ainda tem itens aguardando a
//     próxima rodada de sincronização automática.
//  4. em dia         — online e fila vazia: colapsa numa lasquinha verde
//     fina (persistente, mas discreta) em vez de sumir — o objetivo é nunca
//     deixar de haver ALGUM sinal visível do estado da conexão.
import { CloudUpload, WifiOff } from "lucide-react";
import type { ProgressoSync } from "@/lib/offline";

export function ConexaoFaixa({ online, pendentes, progresso }: { online: boolean; pendentes: number; progresso: ProgressoSync }) {
  // 1) Sincronizando — barra de progresso de verdade.
  if (progresso) {
    const pct = progresso.total > 0 ? Math.round((progresso.feitos / progresso.total) * 100) : 100;
    return (
      <div className="mob-faixa-conexao mob-faixa-sync" role="status" aria-live="polite">
        <div className="mob-faixa-sync-topo">
          <span>Sincronizando…</span>
          <span>{progresso.feitos} de {progresso.total}</span>
        </div>
        <div className="mob-faixa-progresso" aria-hidden="true">
          <div className="mob-faixa-progresso-preenchido" style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  }

  // 2) Offline — servidor inalcançável (ping real, ver useConectividadeReal).
  if (!online) {
    return (
      <div className="mob-faixa-conexao mob-faixa-offline" role="status" aria-live="polite">
        <WifiOff size={13} />
        Sem conexão com o servidor — os lançamentos ficam guardados no aparelho{pendentes > 0 ? ` (${pendentes})` : ""}
      </div>
    );
  }

  // 3) Online, mas ainda há itens aguardando a próxima rodada automática.
  if (pendentes > 0) {
    return (
      <div className="mob-faixa-conexao mob-faixa-pendente" role="status" aria-live="polite">
        <CloudUpload size={13} />
        {pendentes} lançamento{pendentes > 1 ? "s" : ""} aguardando envio
      </div>
    );
  }

  // 4) Tudo em dia — lasquinha fina e persistente, sem texto (não é preciso
  // gritar quando está tudo bem; só continuar visível/presente).
  return <div className="mob-faixa-conexao mob-faixa-ok" aria-hidden="true" />;
}
