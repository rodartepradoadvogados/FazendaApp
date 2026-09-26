"use client";
// Cadastro simples de Classificação e Finalidade — vocabulário livre que a
// CowData mantém (não um enum fixo), usado para marcar fornecedores/
// produtos-padrão e como "modo" de cotação (ver CotacoesCowDataCotacoes).
import { useEffect, useState } from "react";
import { Check, Pencil, Plus, Trash2, X } from "lucide-react";
import {
  fetchClassificacoesCowData, criarClassificacaoCowData, editarClassificacaoCowData, excluirClassificacaoCowData,
  fetchFinalidadesCowData, criarFinalidadeCowData, editarFinalidadeCowData, excluirFinalidadeCowData,
  type ClassificacaoCowData, type FinalidadeCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";

function msgErro(e: unknown): string {
  return e instanceof Error ? e.message : "Erro inesperado";
}

function Coluna<T extends { id: number; nome: string; ativo: boolean }>({
  titulo, itens, onCriar, onEditar, onExcluir,
}: {
  titulo: string; itens: T[];
  onCriar: (nome: string) => Promise<void>;
  onEditar: (id: number, nome: string, ativo: boolean) => Promise<void>;
  onExcluir: (id: number) => Promise<void>;
}) {
  const { cor: COR, inputStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [novoNome, setNovoNome] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Edição inline por linha — pencil abre um input curto no lugar do nome,
  // mesmo padrão de outros cadastros simples deste painel (Pencil +
  // salvar/cancelar), mas sem modal: é só um nome, não vale abrir um popup
  // por cima da tela pra isso.
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [nomeEdicao, setNomeEdicao] = useState("");
  const [salvandoEdicao, setSalvandoEdicao] = useState(false);
  const [erroLinha, setErroLinha] = useState<Record<number, string>>({});
  const [excluindoId, setExcluindoId] = useState<number | null>(null);

  async function adicionar() {
    if (!novoNome.trim()) return;
    setSalvando(true); setErro(null);
    try { await onCriar(novoNome.trim()); setNovoNome(""); } catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  function abrirEdicao(item: T) { setEditandoId(item.id); setNomeEdicao(item.nome); setErroLinha((s) => ({ ...s, [item.id]: "" })); }
  function cancelarEdicao() { setEditandoId(null); setNomeEdicao(""); }

  async function salvarEdicao(item: T) {
    const nome = nomeEdicao.trim();
    if (!nome) return;
    setSalvandoEdicao(true);
    try {
      await onEditar(item.id, nome, item.ativo);
      setEditandoId(null); setNomeEdicao("");
    } catch (e) { setErroLinha((s) => ({ ...s, [item.id]: msgErro(e) })); } finally { setSalvandoEdicao(false); }
  }

  async function excluir(item: T) {
    if (!window.confirm(`Excluir "${item.nome}"? Isso não pode ser desfeito.`)) return;
    setExcluindoId(item.id); setErroLinha((s) => ({ ...s, [item.id]: "" }));
    try { await onExcluir(item.id); } catch (e) { setErroLinha((s) => ({ ...s, [item.id]: msgErro(e) })); } finally { setExcluindoId(null); }
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
            display: "flex", flexDirection: "column", gap: "0.3rem", padding: "0.4rem 0.6rem",
            border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", opacity: item.ativo ? 1 : 0.5,
          }}>
            {editandoId === item.id ? (
              <div className="flex items-center gap-2">
                <input autoFocus style={{ ...inputStyle, flex: 1 }} value={nomeEdicao}
                  onChange={(e) => setNomeEdicao(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") salvarEdicao(item); if (e.key === "Escape") cancelarEdicao(); }} />
                <button style={{ ...btnGhost, fontSize: "0.7rem" }} disabled={salvandoEdicao} onClick={() => salvarEdicao(item)} title="Salvar">
                  <Check size={13} />
                </button>
                <button style={{ ...btnGhost, fontSize: "0.7rem" }} disabled={salvandoEdicao} onClick={cancelarEdicao} title="Cancelar">
                  <X size={13} />
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <span style={{ fontSize: "0.82rem", color: COR.texto }}>{item.nome}</span>
                <div className="flex items-center gap-1">
                  <button style={{ ...btnGhost, fontSize: "0.7rem" }} onClick={() => abrirEdicao(item)} title="Renomear">
                    <Pencil size={12} />
                  </button>
                  <button style={{ ...btnGhost, fontSize: "0.7rem" }} onClick={() => onEditar(item.id, item.nome, !item.ativo)}>
                    {item.ativo ? "Desativar" : "Ativar"}
                  </button>
                  <button style={{ ...btnGhost, fontSize: "0.7rem", color: "var(--red)" }} disabled={excluindoId === item.id}
                    onClick={() => excluir(item)} title="Excluir">
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            )}
            {erroLinha[item.id] && <p style={{ color: "var(--red)", fontSize: "0.72rem" }}>{erroLinha[item.id]}</p>}
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
        onEditar={async (id, nome, ativo) => { await editarClassificacaoCowData(id, { nome, ativo }); await carregar(); }}
        onExcluir={async (id) => { await excluirClassificacaoCowData(id); await carregar(); }} />
      <Coluna titulo="Finalidades" itens={finalidades}
        onCriar={async (nome) => { await criarFinalidadeCowData(nome); await carregar(); }}
        onEditar={async (id, nome, ativo) => { await editarFinalidadeCowData(id, { nome, ativo }); await carregar(); }}
        onExcluir={async (id) => { await excluirFinalidadeCowData(id); await carregar(); }} />
    </div>
  );
}
