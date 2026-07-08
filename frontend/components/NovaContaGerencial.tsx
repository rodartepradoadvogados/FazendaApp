"use client";
import { useState } from "react";
import { Check, X } from "lucide-react";
import { criarContaGerencial } from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

/** Cadastro rápido de conta gerencial — usado dentro do modal do lançamento financeiro. */
export default function NovaContaGerencial({ tipoSugerido, onCriado, onCancelar }: {
  tipoSugerido?: "despesa" | "receita"; onCriado: (conta: { codigo: string; nome: string }) => void; onCancelar: () => void;
}) {
  const [codigo, setCodigo] = useState(tipoSugerido === "receita" ? "2." : "3.");
  const [nome, setNome] = useState("");
  const [tipoFixoVariavel, setTipoFixoVariavel] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar() {
    if (!codigo.trim() || !nome.trim()) { setErro("Código e nome são obrigatórios."); return; }
    setErro(null); setSalvando(true);
    try {
      const criada = await criarContaGerencial({ codigo: codigo.trim(), nome: nome.trim(), tipo_fixo_variavel: tipoFixoVariavel || undefined });
      onCriado(criada);
    } catch (e: any) {
      setErro(e.message || "Erro ao cadastrar conta gerencial");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Código</label><input style={inputStyle} value={codigo} onChange={(e) => setCodigo(e.target.value)} placeholder="ex.: 3.01.01.09" /></div>
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: Concentrado protéico" /></div>
        <div><label style={labelStyle}>Tipo</label>
          <select style={inputStyle} value={tipoFixoVariavel} onChange={(e) => setTipoFixoVariavel(e.target.value)}>
            <option value="">—</option><option value="Fixa">Fixa</option><option value="Variável">Variável</option>
          </select></div>
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
