"use client";
import { useEffect, useMemo, useState } from "react";
import { History, AlertTriangle, Search } from "lucide-react";
import { fetchMovimentacoes, formatDate } from "@/lib/api";

type Movimento = {
  id: number; numero_matriz: string; lote_origem: string | null; lote_destino: string;
  data_movimento: string; hora_movimento: string | null; motivo: string;
  observacao: string | null; responsavel: string | null;
};

const selStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
};

export default function HistoricoMovimentacoes() {
  const [movs, setMovs] = useState<Movimento[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  useEffect(() => { fetchMovimentacoes().then(setMovs).catch((e) => setError(e.message)); }, []);

  const filtrados = useMemo(() => {
    if (!movs) return [];
    if (!busca) return movs;
    return movs.filter((m) => m.numero_matriz.toLowerCase().includes(busca.toLowerCase()));
  }, [movs, busca]);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><History size={22} style={{ color: "var(--dourado)" }} /> Histórico de movimentações</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Relatório de todas as transferências de animais entre lotes.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
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
                  <th>Motivo</th><th>Responsável</th><th>Observação</th>
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
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{m.responsavel || "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{m.observacao || "—"}</td>
                  </tr>
                ))}
                {!filtrados.length && <tr><td colSpan={8} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma movimentação registrada.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
