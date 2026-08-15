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
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

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

  return (
    <div className="card mt-4" style={{ padding: 0 }}>
      <div className="card-header m-3">{titulo}</div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", margin: "0 0.75rem 0.5rem" }}>{erro}</p>}
      {aviso && <p style={{ color: "var(--green-light)", fontSize: "0.78rem", margin: "0 0.75rem 0.5rem" }}>{aviso}</p>}
      <div className="overflow-x-auto" style={{ maxHeight: "360px" }}>
        <table className="fazenda-table" style={{ margin: 0 }}>
          <thead>
            <tr>
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
