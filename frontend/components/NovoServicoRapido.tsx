"use client";
import { useState } from "react";
import { Check, X } from "lucide-react";
import { criarServicoCadastro } from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

/** Cadastro rápido de serviço — usado dentro do modal do lançamento financeiro. */
export default function NovoServicoRapido({ onCriado, onCancelar, prefillNome }: {
  onCriado: (servico: { nome: string }) => void; onCancelar: () => void; prefillNome?: string;
}) {
  const [nome, setNome] = useState(prefillNome || "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar() {
    if (!nome.trim()) { setErro("Nome é obrigatório."); return; }
    setErro(null); setSalvando(true);
    try {
      const criado = await criarServicoCadastro({ nome: nome.trim() });
      onCriado(criado);
    } catch (e: any) {
      setErro(e.message || "Erro ao cadastrar serviço");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <div className="grid grid-cols-1 gap-3 mb-3">
        <div><label style={labelStyle}>Nome do serviço</label><input style={inputStyle} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: Manutenção de cerca elétrica" /></div>
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}
