"use client";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { confirmarExclusao, ehAdmin } from "@/lib/api";

/**
 * G13 — widget compartilhado "últimos lançados": uma mini-tabela de
 * conferência logo abaixo de um formulário de lançamento em Lançamentos, com
 * botão de excluir por linha (via motor genérico de exclusões — admin exclui
 * na hora, operador solicita e aguarda aprovação, mesmo padrão de
 * app/sanidade/page.tsx). Só exclusão — não tem edição inline; quem precisa
 * corrigir um valor lançado usa a tela de relatório/histórico do próprio
 * módulo (ex.: Produção › Pesagens).
 */
export type ColunaUltimosLancados<T> = {
  label: string;
  render: (linha: T) => React.ReactNode;
  alinhar?: "left" | "right";
};

export function UltimosLancados<T extends { id: number }>({
  titulo,
  linhas,
  colunas,
  tipoExclusao,
  onExcluido,
  vazio = "Nenhum lançamento ainda.",
}: {
  titulo: string;
  linhas: T[];
  colunas: ColunaUltimosLancados<T>[];
  tipoExclusao: string;
  onExcluido: () => void;
  vazio?: string;
}) {
  const admin = ehAdmin();
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [excluindoLote, setExcluindoLote] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  // Marcar mais de um lançamento para excluir de uma vez, além do botão de
  // excluir por linha (que continua existindo).
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const toggleSelecionado = (id: number) => setSelecionados((prev) => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  const excluir = async (linha: T) => {
    const msg = admin
      ? "Excluir este lançamento? Isso não pode ser desfeito."
      : "Solicitar a exclusão deste lançamento? Um administrador precisa aprovar antes de ser excluído de fato.";
    if (!window.confirm(msg)) return;
    setOcupado(linha.id);
    setErro(null);
    setAviso(null);
    try {
      const r = await confirmarExclusao(tipoExclusao, String(linha.id));
      if (r.status === "excluido") {
        onExcluido();
      } else {
        setAviso("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
    } catch (e: any) {
      setErro(e.message || "Erro ao excluir");
    } finally {
      setOcupado(null);
    }
  };

  const excluirSelecionados = async () => {
    const ids = Array.from(selecionados);
    if (!ids.length) return;
    const msg = admin
      ? `Excluir ${ids.length} lançamento(s)? Isso não pode ser desfeito.`
      : `Solicitar a exclusão de ${ids.length} lançamento(s)? Um administrador precisa aprovar antes de serem excluídos de fato.`;
    if (!window.confirm(msg)) return;
    setExcluindoLote(true); setErro(null); setAviso(null);
    let excluidos = 0, pendentes = 0;
    for (const id of ids) {
      try {
        const r = await confirmarExclusao(tipoExclusao, String(id));
        if (r.status === "excluido") excluidos++; else pendentes++;
      } catch (e: any) { setErro(e.message || "Erro ao excluir"); }
    }
    setSelecionados(new Set());
    setExcluindoLote(false);
    if (excluidos) onExcluido();
    if (pendentes) setAviso(`${pendentes} solicitação(ões) de exclusão enviada(s) — aguardando aprovação de um administrador.`);
  };

  return (
    <div className="card mt-4" style={{ padding: 0 }}>
      <div className="flex items-center justify-between m-3" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <div className="card-header" style={{ margin: 0 }}>{titulo}</div>
        {linhas.length > 1 && (
          <button
            title="Excluir os lançamentos marcados"
            disabled={!selecionados.size || excluindoLote}
            onClick={excluirSelecionados}
            className="btn-ghost"
            style={{ fontSize: "0.76rem", color: "var(--red)" }}
          >
            <Trash2 size={13} /> {excluindoLote ? "Excluindo…" : `Excluir selecionados (${selecionados.size})`}
          </button>
        )}
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", margin: "0 0.75rem 0.5rem" }}>{erro}</p>}
      {aviso && <p style={{ color: "var(--green-light)", fontSize: "0.78rem", margin: "0 0.75rem 0.5rem" }}>{aviso}</p>}
      <div className="overflow-x-auto" style={{ maxHeight: "360px" }}>
        <table className="fazenda-table" style={{ margin: 0 }}>
          <thead>
            <tr>
              {linhas.length > 1 && <th></th>}
              {colunas.map((coluna) => (
                <th key={coluna.label} style={coluna.alinhar === "right" ? { textAlign: "right" } : undefined}>
                  {coluna.label}
                </th>
              ))}
              <th style={{ textAlign: "right" }}>Ações</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((linha) => (
              <tr key={linha.id}>
                {linhas.length > 1 && (
                  <td><input type="checkbox" checked={selecionados.has(linha.id)} onChange={() => toggleSelecionado(linha.id)} /></td>
                )}
                {colunas.map((coluna) => (
                  <td key={coluna.label} style={coluna.alinhar === "right" ? { textAlign: "right" } : undefined}>
                    {coluna.render(linha)}
                  </td>
                ))}
                <td style={{ textAlign: "right" }}>
                  <button
                    title={admin ? "Excluir" : "Solicitar exclusão"}
                    disabled={ocupado === linha.id}
                    onClick={() => excluir(linha)}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
            {!linhas.length && (
              <tr>
                <td colSpan={colunas.length + 1} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>
                  {vazio}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
