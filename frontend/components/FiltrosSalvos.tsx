"use client";
// Widget reutilizável de "filtros salvos" — usado hoje em Financeiro
// (Extrato completo, Fluxo de caixa, DRE, Livro caixa, Contas a pagar/
// receber/pagas/recebidas), mas genérico o bastante para qualquer outra tela
// de relatório adotar depois: basta escolher uma `tela` própria e passar o
// estado atual dos filtros (objeto livre).
import { useEffect, useState } from "react";
import { Bookmark, Trash2 } from "lucide-react";
import { fetchFiltrosSalvos, criarFiltroSalvo, excluirFiltroSalvo, type FiltroSalvo } from "@/lib/api";

export function FiltrosSalvos({ tela, valor, aoAplicar }: {
  tela: string;
  valor: Record<string, any>;
  aoAplicar: (filtros: Record<string, any>) => void;
}) {
  const [lista, setLista] = useState<FiltroSalvo[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => { fetchFiltrosSalvos(tela).then(setLista).catch(() => {}); };
  useEffect(() => { carregar(); }, [tela]);

  async function salvarAtual() {
    const nome = window.prompt("Nome para este filtro:");
    if (!nome || !nome.trim()) return;
    setSalvando(true); setErro(null);
    try {
      await criarFiltroSalvo({ tela, nome: nome.trim(), filtros: valor });
      carregar();
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar filtro");
    } finally {
      setSalvando(false);
    }
  }

  async function excluir(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm("Excluir este filtro salvo?")) return;
    await excluirFiltroSalvo(id);
    carregar();
  }

  const pillStyle: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.76rem", fontWeight: 600,
    background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 999,
    padding: "0.25rem 0.6rem", cursor: "pointer", color: "var(--text)",
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
      {lista.map((f) => (
        <button key={f.id} type="button" onClick={() => aoAplicar(f.filtros)} style={pillStyle} title="Aplicar este filtro salvo">
          <Bookmark size={12} /> {f.nome}
          <span onClick={(e) => excluir(f.id, e)} style={{ display: "flex", color: "var(--text-muted)" }} title="Excluir">
            <Trash2 size={11} />
          </span>
        </button>
      ))}
      <button type="button" onClick={salvarAtual} disabled={salvando}
        style={{ ...pillStyle, background: "none", border: "1px dashed var(--border)", color: "var(--text-muted)" }}>
        <Bookmark size={12} /> {salvando ? "Salvando…" : "Salvar filtro atual"}
      </button>
      {erro && <span style={{ fontSize: "0.72rem", color: "var(--red)" }}>{erro}</span>}
    </div>
  );
}
