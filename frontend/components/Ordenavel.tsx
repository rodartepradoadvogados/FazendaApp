"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

// Ordenação por coluna (asc/desc ao clicar no cabeçalho) — o mais simples
// possível, igual ao clique na primeira linha de uma planilha.
export function useOrdenacao<T extends Record<string, any>>(linhas: T[]) {
  const [coluna, setColuna] = useState<string | null>(null);
  const [dir, setDir] = useState<1 | -1>(1);
  const ordenar = (c: string) => {
    if (c === coluna) setDir((d) => (d === 1 ? -1 : 1));
    else { setColuna(c); setDir(1); }
  };
  const linhasOrdenadas = useMemo(() => {
    if (!coluna) return linhas;
    return [...linhas].sort((a, b) => {
      const av = a[coluna]; const bv = b[coluna];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [linhas, coluna, dir]);
  return { linhasOrdenadas, coluna, dir, ordenar };
}

export function ThOrdenavel({ label, campo, coluna, dir, ordenar, alinhar, sticky }: {
  label: string; campo: string; coluna: string | null; dir: 1 | -1; ordenar: (c: string) => void; alinhar?: "left" | "right" | "center";
  /** Cabeçalho congelado ao rolar — usado em tabelas dentro de um popup/modal
   * de rolagem própria (ex.: AnimalModal), onde a lista pode ser longa. */
  sticky?: boolean;
}) {
  const ativo = coluna === campo;
  return (
    <th onClick={() => ordenar(campo)}
      style={{
        cursor: "pointer", userSelect: "none", whiteSpace: "nowrap", textAlign: alinhar,
        ...(sticky ? { position: "sticky", top: 0, zIndex: 1, background: "var(--thead-bg)" } : undefined),
      }}>
      <span className="flex items-center gap-1" style={{ justifyContent: alinhar === "right" ? "flex-end" : undefined }}>
        {label}
        {ativo ? (dir === 1 ? <ChevronDown size={12} /> : <ChevronUp size={12} />) : null}
      </span>
    </th>
  );
}
