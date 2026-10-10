"use client";
// Aba de Exclusão: wrapper da Fase 2. A tela nova (ExclusaoPage) fica atrás da
// flag por fazenda `exclusao_v2` (ParametroFazenda) até o dono validar — enquanto
// desligada, cai na tela antiga (FormExclusaoLegado), que é o comportamento seguro.
import { useEffect, useState } from "react";
import { fetchExclusaoV2 } from "@/lib/api";
import { ExclusaoPage } from "@/components/exclusao/ExclusaoPage";
import { FormExclusaoLegado } from "@/components/FormExclusaoLegado";

export function FormExclusao({ ocultarTipos }: { ocultarTipos?: string[] } = {}) {
  const [v2, setV2] = useState(false);
  useEffect(() => {
    let vivo = true;
    fetchExclusaoV2().then((r) => { if (vivo) setV2(!!r.ativa); }).catch(() => {});
    return () => { vivo = false; };
  }, []);

  return v2
    ? <ExclusaoPage ocultarTipos={ocultarTipos} />
    : <FormExclusaoLegado ocultarTipos={ocultarTipos} />;
}