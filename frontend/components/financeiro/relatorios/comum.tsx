"use client";
// Peças comuns às telas novas dos Relatórios (Fase B).
import { useEffect, useState } from "react";
import { fetchRegrasV2 } from "@/lib/api";
import type { FiltroConsultasDrill } from "@/lib/relatorioDre";

/** Flag `financeiro_regras_v2` da fazenda em três estados (null = ainda não se sabe).
 *  Diferente de useRegrasV2 (false enquanto carrega): aqui a tela espera para
 *  não buscar o relatório duas vezes nem piscar a trava do centro de custo. */
export function useRegrasV2Estado(): { ativa: boolean | null; erro: string | null } {
  const [ativa, setAtiva] = useState<boolean | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    fetchRegrasV2().then((r) => { if (vivo) setAtiva(!!r.ativa); })
      .catch((e) => { if (vivo) { setAtiva(false); setErro((e as Error).message); } });
    return () => { vivo = false; };
  }, []);
  return { ativa, erro };
}

/** O que cada tela nova recebe da página do Financeiro. */
export type PropsRelatorio = {
  hoje: string;
  centros: string[];
  /** Centro padrão quando a URL não diz (Pecuária Leiteira, se existir). */
  ccPadrao: string;
  /** Abre Consultas já filtrada (período, regime, centro e conta). */
  onConsultas: (f: FiltroConsultasDrill) => void;
  /** Vai para outro relatório (id da árvore), com o contexto preservado na URL. */
  onIrRelatorio: (id: string, det?: string) => void;
  /** Volta ao primeiro relatório do grupo (migalha). */
  onIrGrupo?: () => void;
};

export const PORQUE_CENTRO_REGRAS_ANTIGAS =
  "Com as regras antigas dos relatórios, a DRE é sempre da fazenda inteira (como na tela anterior). O filtro por centro de custo entra quando as regras novas forem ligadas em Parâmetros financeiros.";
