"use client";
import { useEffect, useState } from "react";
import { FileSpreadsheet, FileText, Loader2, Share2 } from "lucide-react";
import { exportarExcel, exportarPDF, ColunaExport, type OpcoesExportLista } from "@/lib/export";
import { useExportRegister } from "@/components/ExportContext";
import { ehApp } from "@/lib/nativo";

/**
 * Par de botões "Excel" / "PDF" para exportar uma lista/relatório já
 * calculado na tela — mesmo cabeçalho (fazenda, título, usuário, data) nos
 * dois formatos. Usar em qualquer tabela/relatório: só passar as colunas
 * (header + key) e as linhas (mesmos objetos usados para renderizar a tabela).
 * Dentro do app Android o par vira "PDF" + "Compartilhar": Excel não serve no
 * celular (decisão de 24/10/2026) e "Compartilhar" abre a folha do Android.
 * `filtros` (texto dos filtros usados) e `resumo` (ex.: por lote) são
 * opcionais — sem eles o arquivo sai exatamente como antes.
 */
export function ExportarBotoes({
  titulo, colunas, linhas, nomeArquivoBase, disabled, filtros, resumo,
}: {
  titulo: string;
  colunas: ColunaExport[];
  linhas: Record<string, unknown>[];
  nomeArquivoBase: string;
  disabled?: boolean;
  filtros?: OpcoesExportLista["filtros"];
  resumo?: OpcoesExportLista["resumo"];
}) {
  const [gerando, setGerando] = useState<"excel" | "pdf" | "compartilhar" | null>(null);
  const [noApp, setNoApp] = useState(false);
  useEffect(() => { ehApp().then(setNoApp); }, []);
  const semDados = disabled || linhas.length === 0;
  // Registra os mesmos dados no ExportContext — sem efeito hoje na maioria
  // das telas (nada os consome ali); o cabeçalho do portal Insights e
  // Administração usa isso para oferecer um único "Exportar" no topo.
  useExportRegister(disabled ? null : { titulo, colunas, linhas, nomeArquivoBase });

  const rodar = async (formato: "excel" | "pdf" | "compartilhar") => {
    setGerando(formato);
    try {
      const opcoes = filtros || resumo ? { filtros, resumo } : undefined;
      if (formato === "excel") await exportarExcel(titulo, colunas, linhas, nomeArquivoBase, "baixar", opcoes);
      else await exportarPDF(titulo, colunas, linhas, nomeArquivoBase, formato === "compartilhar" ? "compartilhar" : "baixar", opcoes);
    } catch {
      // erro já mostrado ao usuário dentro de exportarExcel/exportarPDF (lib/export.ts)
    } finally {
      setGerando(null);
    }
  };

  const btn: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: "0.35rem", padding: "0.4rem 0.7rem", borderRadius: "var(--r-sm)",
    border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text-muted)",
    fontSize: "0.78rem", fontWeight: 600, cursor: semDados ? "not-allowed" : "pointer", opacity: semDados ? 0.5 : 1,
  };

  return (
    <div style={{ display: "flex", gap: "0.5rem" }}>
      {!noApp && (
        <button type="button" style={btn} disabled={semDados || gerando !== null} onClick={() => rodar("excel")} title="Exportar para Excel">
          {gerando === "excel" ? <Loader2 size={14} className="animate-spin" /> : <FileSpreadsheet size={14} />} Excel
        </button>
      )}
      <button type="button" style={btn} disabled={semDados || gerando !== null} onClick={() => rodar("pdf")} title="Exportar para PDF">
        {gerando === "pdf" ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />} PDF
      </button>
      {noApp && (
        <button type="button" style={btn} disabled={semDados || gerando !== null} onClick={() => rodar("compartilhar")} title="Compartilhar o PDF">
          {gerando === "compartilhar" ? <Loader2 size={14} className="animate-spin" /> : <Share2 size={14} />} Compartilhar
        </button>
      )}
    </div>
  );
}
