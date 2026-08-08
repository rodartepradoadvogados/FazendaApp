"use client";
import { createContext, useContext, useEffect, ReactNode, useState } from "react";
import type { ColunaExport } from "@/lib/export";

// Espelha o registro de sub-navegação (ver SubNavContext.tsx): toda tela que
// já usa <ExportarBotoes> (ver componente) registra aqui os mesmos dados —
// sem precisar de nenhuma mudança nas ~40 telas que já chamam
// ExportarBotoes. Consumido hoje só pelo cabeçalho do portal "Insights e
// Administração" (ver components/insights/InsightsLayout.tsx), que mostra
// um único "Exportar" no topo em vez do par de botões embutido na página.
export type ExportValue = {
  titulo: string; colunas: ColunaExport[]; linhas: Record<string, unknown>[]; nomeArquivoBase: string;
} | null;

const ExportContext = createContext<{ exportAtual: ExportValue; setExportAtual: (v: ExportValue) => void } | null>(null);

export function ExportProvider({ children }: { children: ReactNode }) {
  const [exportAtual, setExportAtual] = useState<ExportValue>(null);
  return <ExportContext.Provider value={{ exportAtual, setExportAtual }}>{children}</ExportContext.Provider>;
}

export function useExportRegister(value: ExportValue) {
  const ctx = useContext(ExportContext);
  useEffect(() => {
    ctx?.setExportAtual(value);
    return () => ctx?.setExportAtual(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value?.titulo, value?.nomeArquivoBase, value?.colunas, value?.linhas]);
}

export function useExportAtual(): ExportValue {
  return useContext(ExportContext)?.exportAtual ?? null;
}
