"use client";
import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { criarAnimalFicha, fetchLotes } from "@/lib/api";
import type { AnimalRow } from "./AnimalModal";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

/** Cadastro rápido de animal — usado dentro do seletor de animais da compra
 * (Lançamentos > Compra/Venda > Comprar animal), para não obrigar o usuário
 * a sair da tela de compra para cadastrar o animal recém-adquirido antes de
 * poder selecioná-lo. Só os campos essenciais — a ficha completa (genealogia,
 * raça, grau de sangue etc.) pode ser complementada depois em Cadastro. */
export default function NovoAnimalRapido({ onCriado, onCancelar }: {
  onCriado: (animal: AnimalRow) => void; onCancelar: () => void;
}) {
  const [numero, setNumero] = useState("");
  const [nome, setNome] = useState("");
  const [sexo, setSexo] = useState("F");
  const [categoriaAbrev, setCategoriaAbrev] = useState("");
  const [grupoPrimario, setGrupoPrimario] = useState("");
  const [dataNasc, setDataNasc] = useState("");
  const [lotes, setLotes] = useState<{ codigo: string; nome: string }[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchLotes().then(setLotes).catch(() => {}); }, []);

  async function salvar() {
    if (!numero.trim()) { setErro("Número/brinco é obrigatório."); return; }
    setErro(null); setSalvando(true);
    try {
      const criado = await criarAnimalFicha({
        numero: numero.trim(), nome: nome.trim() || undefined, sexo: sexo || undefined,
        categoria_abrev: categoriaAbrev.trim() || undefined, grupo_primario: grupoPrimario || undefined,
        data_nasc: dataNasc || undefined,
      });
      onCriado({
        numero: criado.numero, grupo_primario: criado.grupo_primario ?? null,
        categoria_abrev: criado.categoria_abrev ?? null, categoria_completa: null, raca: null,
      });
    } catch (e: any) {
      setErro(e.message || "Erro ao cadastrar animal");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div><label style={labelStyle}>Número/brinco *</label>
          <input style={inputStyle} value={numero} onChange={(e) => setNumero(e.target.value)} placeholder="ex.: 1234" /></div>
        <div><label style={labelStyle}>Nome (opcional)</label>
          <input style={inputStyle} value={nome} onChange={(e) => setNome(e.target.value)} /></div>
        <div><label style={labelStyle}>Sexo</label>
          <select style={inputStyle} value={sexo} onChange={(e) => setSexo(e.target.value)}>
            <option value="F">Fêmea</option>
            <option value="M">Macho</option>
          </select>
        </div>
        <div><label style={labelStyle}>Categoria (opcional)</label>
          <input style={inputStyle} value={categoriaAbrev} onChange={(e) => setCategoriaAbrev(e.target.value)} placeholder="ex.: Novilha, Vaca" /></div>
        <div><label style={labelStyle}>Lote (opcional)</label>
          <select style={inputStyle} value={grupoPrimario} onChange={(e) => setGrupoPrimario(e.target.value)}>
            <option value="">Selecione…</option>
            {lotes.map((l) => <option key={l.codigo} value={l.codigo}>{l.nome || l.codigo}</option>)}
          </select>
        </div>
        <div><label style={labelStyle}>Data de nascimento (opcional)</label>
          <input type="date" style={inputStyle} value={dataNasc} onChange={(e) => setDataNasc(e.target.value)} /></div>
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar e selecionar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}
