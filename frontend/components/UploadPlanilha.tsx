"use client";
import { useState } from "react";
import { Download } from "lucide-react";

// Upload de planilha (Excel/.xlsx ou CSV) — usado em Controle leiteiro (por
// animal ou por lote, um botão de modelo cada), Qualidade do leite (um modelo
// só) e Pesagem corporal. O parser do backend identifica o formato sozinho.
export function UploadPlanilha({ modelos, onImportar }: {
  modelos: { label: string; baixar: () => Promise<void> }[];
  onImportar: (file: File) => Promise<{ criados: number; erros: string[] }>;
}) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<{ criados: number; erros: string[] } | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function importar() {
    if (!arquivo) return;
    setEnviando(true); setErro(null); setResultado(null);
    try {
      const r = await onImportar(arquivo);
      setResultado(r);
      setArquivo(null);
    } catch (e: any) {
      setErro(e.message || "Erro ao importar planilha");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
      <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.5rem" }}>Importar de planilha (Excel ou CSV)</p>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        {modelos.map((m) => (
          <button key={m.label} type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => m.baixar().catch(() => setErro("Erro ao baixar o modelo."))}>
            <Download size={13} /> {m.label}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
        <input type="file" accept=".xlsx,.xlsm,.csv" onChange={(e) => { setArquivo(e.target.files?.[0] || null); setResultado(null); setErro(null); }} style={{ fontSize: "0.8rem" }} />
        <button type="button" className="btn-primary" disabled={!arquivo || enviando} onClick={importar}>{enviando ? "Importando…" : "Importar"}</button>
      </div>
      {resultado && (
        <p style={{ fontSize: "0.78rem", marginTop: "0.6rem", color: resultado.erros.length ? "var(--amber)" : "var(--green-light)" }}>
          {resultado.criados} lançamento(s) criado(s){resultado.erros.length ? ` — ${resultado.erros.length} linha(s) com erro:` : "."}
          {resultado.erros.length > 0 && (
            <ul style={{ marginTop: "0.3rem", paddingLeft: "1.1rem", color: "var(--text-muted)" }}>
              {resultado.erros.slice(0, 10).map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}
    </div>
  );
}
