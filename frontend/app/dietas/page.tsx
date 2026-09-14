"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Copy, Plus, Trash2 } from "lucide-react";
import {
  listarSimulacoes, excluirSimulacao, duplicarSimulacao, SimulacaoResumo, StatusSimulacao,
} from "@/lib/dietas";

const ROTULO_STATUS: Record<StatusSimulacao, string> = {
  rascunho: "Rascunho", concluida: "Concluída", aplicada: "Aplicada", arquivada: "Arquivada",
};
const COR_STATUS: Record<StatusSimulacao, string> = {
  rascunho: "var(--text-muted)", concluida: "var(--blue)", aplicada: "var(--green)", arquivada: "var(--text-muted)",
};

function fmtData(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR") + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
function fmtNum(v: number | null, casas = 1): string {
  return v == null || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

export default function ListaSimulacoesPage() {
  const router = useRouter();
  const [itens, setItens] = useState<SimulacaoResumo[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [filtroLote, setFiltroLote] = useState("");
  const [filtroStatus, setFiltroStatus] = useState<string>("");
  const [ocupado, setOcupado] = useState<number | null>(null);

  function carregar() {
    setErro(null);
    listarSimulacoes({
      lote: filtroLote.trim() ? Number(filtroLote) : undefined,
      status: (filtroStatus as StatusSimulacao) || undefined,
    })
      .then(setItens)
      .catch((e) => { setItens([]); setErro(e.message); });
  }

  useEffect(() => { carregar(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [filtroLote, filtroStatus]);

  async function onExcluir(sim: SimulacaoResumo) {
    if (!confirm(`Excluir a simulação "${sim.nome}"? Esta ação não pode ser desfeita.`)) return;
    setOcupado(sim.id);
    try {
      await excluirSimulacao(sim.id);
      carregar();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setOcupado(null);
    }
  }

  async function onDuplicar(sim: SimulacaoResumo) {
    const nome = prompt("Nome da cópia:", `${sim.nome} (cópia)`);
    if (!nome) return;
    setOcupado(sim.id);
    try {
      const { cabecalho } = await duplicarSimulacao(sim.id, nome);
      router.push(`/dietas/${cabecalho.id}`);
    } catch (e: any) {
      alert(e.message);
    } finally {
      setOcupado(null);
    }
  }

  return (
    <div style={{ maxWidth: "82rem", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.8rem", marginBottom: "1.1rem" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.3rem", fontWeight: 800, color: "var(--text)" }}>Simulações de dieta</h1>
          <p style={{ margin: "0.2rem 0 0", fontSize: "0.85rem", color: "var(--text-muted)" }}>
            Formule, salve e aplique dietas de gado leiteiro com o motor NASEM/NRC Dairy 2021.
          </p>
        </div>
        <button type="button" className="btn-primary-gold" onClick={() => router.push("/dietas/nova")}>
          <Plus size={16} /> Nova simulação
        </button>
      </div>

      <div className="card" style={{ marginBottom: "1rem", display: "flex", gap: "0.8rem", flexWrap: "wrap", alignItems: "flex-end" }}>
        <div>
          <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Lote</label>
          <input
            type="number" value={filtroLote} onChange={(e) => setFiltroLote(e.target.value)} placeholder="Todos"
            style={{ width: "7rem", padding: "0.4rem 0.55rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }}
          />
        </div>
        <div>
          <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Status</label>
          <select
            value={filtroStatus} onChange={(e) => setFiltroStatus(e.target.value)}
            style={{ padding: "0.4rem 0.55rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }}
          >
            <option value="">Todos</option>
            {Object.entries(ROTULO_STATUS).map(([v, r]) => <option key={v} value={v}>{r}</option>)}
          </select>
        </div>
      </div>

      {erro && <div className="alert-critico" style={{ marginBottom: "1rem" }}>{erro}</div>}

      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table className="fazenda-table">
          <thead>
            <tr>
              <th>Nome</th><th>Lote</th><th>Status</th><th>Etapa</th><th>CMS (kg/d)</th>
              <th>Balanço ELl (Mcal/d)</th><th>Custo (R$/d)</th><th>Atualizado</th><th>Usuário</th><th></th>
            </tr>
          </thead>
          <tbody>
            {itens === null && <tr><td colSpan={10} style={{ textAlign: "center", color: "var(--text-muted)" }}>Carregando…</td></tr>}
            {itens !== null && itens.length === 0 && (
              <tr><td colSpan={10}><div className="empty-state">Nenhuma simulação ainda. Clique em "Nova simulação" para começar.</div></td></tr>
            )}
            {itens?.map((sim) => (
              <tr key={sim.id} className="row-clickable" onClick={() => router.push(`/dietas/${sim.id}`)}>
                <td style={{ fontWeight: 600 }}>{sim.nome}</td>
                <td>{sim.lote ?? "—"}</td>
                <td>
                  <span style={{ color: COR_STATUS[sim.status], fontWeight: 600, fontSize: "0.8rem" }}>{ROTULO_STATUS[sim.status]}</span>
                </td>
                <td>{sim.etapa_atual}/10</td>
                <td>{fmtNum(sim.cms_kg_dia)}</td>
                <td>{fmtNum(sim.balanco_ell_mcal, 2)}</td>
                <td>{fmtNum(sim.custo_dia, 2)}</td>
                <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{fmtData(sim.atualizado_em)}</td>
                <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{sim.usuario_nome ?? "—"}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <div style={{ display: "flex", gap: "0.3rem", justifyContent: "flex-end" }}>
                    <button type="button" className="btn-ghost" title="Duplicar" disabled={ocupado === sim.id} onClick={() => onDuplicar(sim)} style={{ padding: "0.3rem 0.5rem" }}>
                      <Copy size={14} />
                    </button>
                    {sim.status !== "aplicada" && (
                      <button type="button" className="btn-ghost" title="Excluir" disabled={ocupado === sim.id} onClick={() => onExcluir(sim)} style={{ padding: "0.3rem 0.5rem", color: "var(--red)" }}>
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
