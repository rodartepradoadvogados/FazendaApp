"use client";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Search, Trash2 } from "lucide-react";
import { fetchMovimentacoes, formatDate, ehAdmin, confirmarExclusao } from "@/lib/api";
import { rotuloOrigemMovimentoLote } from "@/lib/constants";
import { casaBusca } from "@/lib/busca";

type Movimento = {
  id: number; numero_matriz: string; lote_origem: string | null; lote_destino: string;
  data_movimento: string; hora_movimento: string | null; motivo: string;
  observacao: string | null; responsavel: string | null; usuario_nome?: string | null;
  origem: string | null;
};

const selStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
};

// Montado como aba "Movimentações" em Rebanho (app/rebanho/page.tsx) — antes
// deste componente ficava importado por ninguém, órfão, e a tela de histórico
// de transferências entre lotes descrita na auditoria não existia de fato
// (ver plano de fechamento dos 17 gaps de editar/excluir, G4). Por isso não
// tem <h1>/cabeçalho próprio: quem dá o título é a aba que o hospeda.
export default function HistoricoMovimentacoes() {
  const [movs, setMovs] = useState<Movimento[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);
  const admin = ehAdmin();

  const carregar = () => fetchMovimentacoes().then(setMovs).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const filtrados = useMemo(() => {
    if (!movs) return [];
    return movs.filter((m) => casaBusca(m.numero_matriz, busca));
  }, [movs, busca]);

  // Mesmo padrão de frontend/app/sanidade/page.tsx: passa pelo fluxo central
  // e auditado de exclusão (POST /exclusoes/confirmar) em vez de um DELETE
  // próprio — admin exclui na hora, operador vira uma solicitação pendente.
  const excluir = async (m: Movimento) => {
    const msg = admin
      ? `Excluir a movimentação de ${m.numero_matriz} (${m.lote_origem || "—"} → ${m.lote_destino})? Isso não pode ser desfeito.`
      : `Solicitar a exclusão da movimentação de ${m.numero_matriz} (${m.lote_origem || "—"} → ${m.lote_destino})? Um administrador precisa aprovar antes de ser excluída de fato.`;
    if (!window.confirm(msg)) return;
    setOcupado(m.id); setError(null); setAvisoExclusao(null);
    try {
      const r = await confirmarExclusao("movimento_lote", String(m.id));
      if (r.status === "excluido") {
        await carregar();
      } else {
        setAvisoExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
    } catch (e: any) { setError(e.message); }
    finally { setOcupado(null); }
  };

  return (
    <div className="p-6 animate-in">
      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {avisoExclusao && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{avisoExclusao}</p>}
      {!movs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {movs && (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <span>Movimentações</span>
            <div style={{ position: "relative", maxWidth: "220px" }}>
              <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por nº" />
            </div>
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "560px" }}>
            <table className="fazenda-table">
              <thead>
                <tr>
                  <th>Data</th><th>Hora</th><th>Matriz</th><th>Origem</th><th>Destino</th>
                  <th>Motivo</th><th title="Como a movimentação foi lançada: manual, sugestão confirmada num pop-up, aplicada automaticamente ou sugestão passiva da Agenda">Tipo</th>
                  <th>Responsável</th><th>Observação</th>
                  {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
                  <th style={{ textAlign: "right" }}>Ações</th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map((m) => (
                  <tr key={m.id}>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{formatDate(m.data_movimento)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{m.hora_movimento || "—"}</td>
                    <td style={{ fontWeight: 700 }}>{m.numero_matriz}</td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{m.lote_origem || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{m.lote_destino}</td>
                    <td style={{ fontSize: "0.78rem" }}>{m.motivo}</td>
                    <td style={{ fontSize: "0.72rem" }}>
                      <span style={{
                        padding: "0.1rem 0.45rem", borderRadius: "999px", fontSize: "0.68rem", fontWeight: 600,
                        background: m.origem === "manual" ? "var(--surface-3, var(--surface-2))" : "var(--dourado-dim, var(--surface-2))",
                        color: m.origem === "manual" ? "var(--text-muted)" : "var(--dourado-light, var(--text))",
                      }}>
                        {rotuloOrigemMovimentoLote(m.origem)}
                      </span>
                    </td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{m.responsavel || "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{m.observacao || "—"}</td>
                    {admin && <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{m.usuario_nome ?? "—"}</td>}
                    <td style={{ textAlign: "right" }}>
                      <button
                        className="btn-ghost"
                        title="Excluir movimentação"
                        disabled={ocupado === m.id}
                        onClick={() => excluir(m)}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
                {!filtrados.length && <tr><td colSpan={admin ? 11 : 10} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma movimentação registrada.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
