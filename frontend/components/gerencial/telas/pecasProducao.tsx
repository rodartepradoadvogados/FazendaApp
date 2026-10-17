"use client";
// Peças comuns aos lançamentos reais de Produção (Controle leiteiro, Pesagem corporal, Secagem) que não existem no kit nem em
// utilProducao.tsx: escolha de arquivo de planilha (com arrastar e soltar), estado vazio de tabela, nota com ícone, dica de teclado.
// Só apresentação — quem lê a planilha e chama a API é cada formulário.
import React, { useState } from "react";
import { Info } from "lucide-react";
import { Tecla } from "./utilProducao";

export const BOTAO_COM_ICONE: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: "0.4rem" };

/** Caixa tracejada que é, de verdade, o campo de arquivo: clicar escolhe, arrastar e soltar também. */
export function EscolhaArquivo({ id, arquivo, onEscolher, aceita, rotulo = "Planilha preenchida", detalhe }: {
  id: string; arquivo: File | null; onEscolher: (f: File | null) => void; aceita: string; rotulo?: string; detalhe?: string;
}) {
  const [sobre, setSobre] = useState(false);
  const kb = arquivo ? Math.max(1, Math.round(arquivo.size / 1024)) : 0;
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setSobre(true); }}
      onDragLeave={() => setSobre(false)}
      onDrop={(e) => { e.preventDefault(); setSobre(false); onEscolher(e.dataTransfer.files?.[0] ?? null); }}
      style={{
        display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap", padding: "0.8rem 1rem", minHeight: "3.2rem",
        border: `1.5px dashed ${sobre ? "var(--ft-ouro)" : "var(--border-strong, var(--border))"}`, borderRadius: "var(--r-sm)",
        background: sobre ? "var(--ft-ouro-tint)" : "var(--surface-2)",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "0.1rem", minWidth: 0, flex: "1 1 16rem" }}>
        <label htmlFor={id} style={{ fontSize: "0.85rem", fontWeight: 700 }}>
          {arquivo ? arquivo.name : `${rotulo}: arraste o arquivo para cá ou escolha`}
        </label>
        <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
          {arquivo ? `${kb} KB${detalhe ? ` · ${detalhe}` : ""}` : `Aceita ${aceita}`}
        </span>
      </div>
      <input id={id} type="file" accept={aceita} onChange={(e) => onEscolher(e.target.files?.[0] ?? null)} style={{ fontSize: "0.8rem", maxWidth: "100%" }} />
    </div>
  );
}

/** Lista que ainda não tem o que mostrar (nenhum lote marcado, nenhuma busca): diz o que fazer. */
export function EstadoVazio({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ border: "1px dashed var(--border-strong, var(--border))", borderRadius: "var(--r-sm)", background: "var(--surface-2)", padding: "1.2rem", color: "var(--text-muted)", fontSize: "0.82rem" }}>
      {children}
    </div>
  );
}

/** Ajuda curta com ícone (mesma voz de `Ajuda`, para o que merece destaque). */
export function NotaInfo({ children }: { children: React.ReactNode }) {
  return (
    <p className="gv-ajuda" style={{ display: "flex", alignItems: "flex-start", gap: "0.4rem" }}>
      <Info size={13} aria-hidden="true" style={{ flexShrink: 0, marginTop: "0.15rem" }} />
      <span>{children}</span>
    </p>
  );
}

/** Dica de teclado ao lado do título do passo: Enter avança de campo. */
export function DicaEnter({ avanca }: { avanca: string }) {
  return (
    <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
      <Tecla>Enter</Tecla> avança para {avanca} · <Tecla>Shift</Tecla>+<Tecla>Enter</Tecla> volta
    </span>
  );
}
