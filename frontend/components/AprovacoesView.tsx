"use client";
import { useEffect, useState } from "react";
import { Check, X, RefreshCw, Inbox } from "lucide-react";
import {
  fetchAprovacoes, aprovarLancamento, rejeitarLancamento, ehAdmin,
  type LancamentoPendente,
} from "@/lib/api";

const OCULTAR = new Set(["_ops", "_nome"]);
const rotuloCampo = (k: string) => k.replace(/_/g, " ");
const valorCampo = (v: any) => (Array.isArray(v) ? v.join(", ") : String(v));

/**
 * Fila de aprovação dos lançamentos enviados pelo Telegram (pesagem, parto,
 * secagem, troca de lote…). Só a conta principal (admin) aprova: aprovar cria
 * o registro de verdade; rejeitar descarta. Usada no site e no app.
 */
export function AprovacoesView({ compacto = false }: { compacto?: boolean }) {
  const [itens, setItens] = useState<LancamentoPendente[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const admin = ehAdmin();

  const carregar = () => fetchAprovacoes().then(setItens).catch((e) => setErro(e.message));
  useEffect(() => { if (admin) carregar(); }, [admin]);

  if (!admin) {
    return <div className="card"><p style={{ color: "var(--text-muted)" }}>Só a conta principal pode ver e aprovar os lançamentos pendentes.</p></div>;
  }

  const decidir = async (id: number, acao: "aprovar" | "rejeitar") => {
    setOcupado(id); setErro(null);
    try {
      await (acao === "aprovar" ? aprovarLancamento(id) : rejeitarLancamento(id));
      await carregar();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(null); }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
          Lançamentos enviados pelo Telegram, aguardando sua aprovação. <strong style={{ color: "var(--text)" }}>Aprovar</strong> cria o registro de verdade.
        </p>
        <button className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={carregar} title="Atualizar a lista">
          <RefreshCw size={13} /> Atualizar
        </button>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.6rem" }}>{erro}</p>}

      {itens && !itens.length && (
        <div className="card" style={{ textAlign: "center", padding: "2rem 1rem", color: "var(--text-muted)" }}>
          <Inbox size={28} style={{ marginBottom: "0.5rem", opacity: 0.6 }} />
          <p>Nenhum lançamento aguardando aprovação. 👍</p>
        </div>
      )}

      <div className="space-y-3">
        {(itens || []).map((it) => (
          <div key={it.id} className="card">
            <div className="flex items-center justify-between" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 700 }}>{it.rotulo}</span>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                {it.solicitante_nome ? `por ${it.solicitante_nome} · ` : ""}{it.criado_em ? new Date(it.criado_em).toLocaleString("pt-BR") : ""}
              </span>
            </div>

            <table style={{ width: "100%", maxWidth: 520, fontSize: "0.82rem", marginTop: "0.5rem" }}>
              <tbody>
                {Object.entries(it.dados).filter(([k]) => !OCULTAR.has(k)).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ padding: "0.12rem 0.6rem 0.12rem 0", color: "var(--text-muted)", textTransform: "capitalize", whiteSpace: "nowrap" }}>{rotuloCampo(k)}</td>
                    <td style={{ fontWeight: 600 }}>{valorCampo(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {it.erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", marginTop: "0.4rem" }}>Tentativa anterior falhou: {it.erro}</p>}

            <div className="flex gap-2 mt-3">
              <button className="btn-primary" disabled={ocupado === it.id} onClick={() => decidir(it.id, "aprovar")} title="Aprovar e criar o registro de verdade" style={{ fontSize: "0.82rem" }}>
                <Check size={14} /> {ocupado === it.id ? "…" : "Aprovar"}
              </button>
              <button className="btn-ghost" disabled={ocupado === it.id} onClick={() => decidir(it.id, "rejeitar")} title="Rejeitar (não cria nada)" style={{ fontSize: "0.82rem" }}>
                <X size={14} /> Rejeitar
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
