"use client";
// Cadastro simples de Classificação e Finalidade — vocabulário livre que a
// CowData mantém (não um enum fixo), usado para marcar fornecedores/
// produtos-padrão e como "modo" de cotação (ver CotacoesCowDataCotacoes).
import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import {
  fetchClassificacoesCowData, criarClassificacaoCowData, editarClassificacaoCowData,
  fetchFinalidadesCowData, criarFinalidadeCowData, editarFinalidadeCowData,
  type ClassificacaoCowData, type FinalidadeCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";

function msgErro(e: unknown): string {
  return e instanceof Error ? e.message : "Erro inesperado";
}

function Coluna<T extends { id: number; nome: string; ativo: boolean }>({
  titulo, itens, onCriar, onEditar,
}: {
  titulo: string; itens: T[]; onCriar: (nome: string) => Promise<void>; onEditar: (id: number, nome: string, ativo: boolean) => Promise<void>;
}) {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [novoNome, setNovoNome] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function adicionar() {
    if (!novoNome.trim()) return;
    setSalvando(true); setErro(null);
    try { await onCriar(novoNome.trim()); setNovoNome(""); } catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  return (
    <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", padding: "1rem", flex: 1, minWidth: "280px" }}>
      <div className="card-header mb-3" style={{ color: COR.texto }}>{titulo}</div>
      <div className="flex gap-2 mb-3">
        <input style={{ ...inputStyle, flex: 1 }} placeholder={`Novo ${titulo.toLowerCase()}`} value={novoNome}
          onChange={(e) => setNovoNome(e.target.value)} onKeyDown={(e) => e.key === "Enter" && adicionar()} />
        <button style={btnPrimario} disabled={salvando} onClick={adicionar}><Plus size={14} /> Adicionar</button>
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", marginBottom: "0.6rem" }}>{erro}</p>}
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.4rem" }}>
        {itens.map((item) => (
          <li key={item.id} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.4rem 0.6rem",
            border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", opacity: item.ativo ? 1 : 0.5,
          }}>
            <span style={{ fontSize: "0.82rem", color: COR.texto }}>{item.nome}</span>
            <button style={{ ...btnGhost, fontSize: "0.7rem" }} onClick={() => onEditar(item.id, item.nome, !item.ativo)}>
              {item.ativo ? "Desativar" : "Ativar"}
            </button>
          </li>
        ))}
        {itens.length === 0 && <p style={{ fontSize: "0.78rem", color: COR.mudo }}>Nenhum ainda.</p>}
      </ul>
    </div>
  );
}

export default function CotacoesCowDataClassificacoes() {
  const [classificacoes, setClassificacoes] = useState<ClassificacaoCowData[] | null>(null);
  const [finalidades, setFinalidades] = useState<FinalidadeCowData[] | null>(null);

  async function carregar() {
    const [c, f] = await Promise.all([fetchClassificacoesCowData(), fetchFinalidadesCowData()]);
    setClassificacoes(c); setFinalidades(f);
  }
  useEffect(() => { carregar(); }, []);

  if (!classificacoes || !finalidades) return <p style={{ fontSize: "0.85rem" }}>Carregando…</p>;

  return (
    <div className="flex gap-4" style={{ flexWrap: "wrap" }}>
      <Coluna titulo="Classificações" itens={classificacoes}
        onCriar={async (nome) => { await criarClassificacaoCowData(nome); await carregar(); }}
        onEditar={async (id, nome, ativo) => { await editarClassificacaoCowData(id, { nome, ativo }); await carregar(); }} />
      <Coluna titulo="Finalidades" itens={finalidades}
        onCriar={async (nome) => { await criarFinalidadeCowData(nome); await carregar(); }}
        onEditar={async (id, nome, ativo) => { await editarFinalidadeCowData(id, { nome, ativo }); await carregar(); }} />
    </div>
  );
}
