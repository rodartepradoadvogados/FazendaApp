"use client";
// Área de arrastar-e-soltar reutilizável para qualquer anexo do sistema —
// antes cada tela reimplementava o próprio onDrop/onDragOver (ex.:
// FormFinanceiro.tsx tinha duas cópias, DocumentosFiscais.tsx/PainelDocumentos.tsx
// e o anexo de FormEditarLancamento não tinham nenhuma). Este componente
// concentra o padrão visual e de eventos; quem precisar de algo bem
// específico (ex.: câmera do celular) continua livre para adicionar por
// cima, como o dropzone de FormFinanceiro.tsx.
import { useRef, useState } from "react";
import { Upload } from "lucide-react";

export function Dropzone({
  onFiles, accept, multiple, label, hint, disabled, compact, cores,
}: {
  onFiles: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  label?: string;
  hint?: string;
  disabled?: boolean;
  compact?: boolean;
  // Sobrescreve as cores (só necessário em telas com paleta própria, fora
  // das variáveis globais — ex.: Painel do Contador/CowData, que usam hex
  // fixo em vez de var(--*) de propósito, ver app/contador/layout.tsx).
  cores?: { borda?: string; bordaAtiva?: string; fundo?: string; fundoAtivo?: string; texto?: string; destaque?: string };
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [sobre, setSobre] = useState(false);
  const c = {
    borda: cores?.borda || "var(--border)", bordaAtiva: cores?.bordaAtiva || "var(--dourado)",
    fundo: cores?.fundo || "var(--surface-2)", fundoAtivo: cores?.fundoAtivo || "rgba(224,166,60,0.08)",
    texto: cores?.texto || "var(--text-muted)", destaque: cores?.destaque || "var(--dourado-light)",
  };

  function tratar(files: FileList | null) {
    if (!files || !files.length) return;
    onFiles(multiple ? Array.from(files) : [files[0]]);
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setSobre(true); }}
      onDragLeave={() => setSobre(false)}
      onDrop={(e) => {
        e.preventDefault();
        setSobre(false);
        if (disabled) return;
        tratar(e.dataTransfer.files);
      }}
      className="card"
      style={{
        border: `1px dashed ${sobre ? c.bordaAtiva : c.borda}`,
        background: sobre ? c.fundoAtivo : c.fundo,
        padding: compact ? "0.55rem" : "0.8rem",
        textAlign: "center",
        opacity: disabled ? 0.6 : 1,
        transition: "border-color .15s, background .15s",
      }}
    >
      <div className="flex items-center justify-center gap-2" style={{ flexWrap: "wrap" }}>
        <Upload size={compact ? 13 : 15} style={{ color: c.destaque }} />
        <span style={{ fontSize: compact ? "0.75rem" : "0.8rem", color: c.texto }}>
          {label || "Arraste o arquivo aqui, ou"}
        </span>
        <button
          type="button" className="btn-ghost" disabled={disabled}
          style={{ fontSize: compact ? "0.74rem" : "0.78rem" }}
          onClick={() => inputRef.current?.click()}
        >
          selecionar arquivo{multiple ? "(s)" : ""}
        </button>
      </div>
      <input
        ref={inputRef} type="file" accept={accept} multiple={multiple} disabled={disabled}
        onChange={(e) => { tratar(e.target.files); e.target.value = ""; }}
        style={{ display: "none" }}
      />
      {hint && <p style={{ fontSize: "0.68rem", color: c.texto, marginTop: "0.35rem" }}>{hint}</p>}
    </div>
  );
}
