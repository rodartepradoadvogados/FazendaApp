"use client";
import { useEffect, useState } from "react";
import { fetchRegrasV2 } from "@/lib/api";

/**
 * A fazenda atual usa as regras novas do Financeiro (Fase A, flag
 * `financeiro_regras_v2`)? `false` enquanto carrega ou se a consulta falhar —
 * a tela continua no comportamento antigo, que é o seguro.
 */
export function useRegrasV2(): boolean {
  const [ativa, setAtiva] = useState(false);
  useEffect(() => {
    let vivo = true;
    fetchRegrasV2().then((r) => { if (vivo) setAtiva(!!r.ativa); }).catch(() => {});
    return () => { vivo = false; };
  }, []);
  return ativa;
}
