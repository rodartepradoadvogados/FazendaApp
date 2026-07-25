"use client";
import { useState } from "react";
import { X, Link2 } from "lucide-react";
import { fetchLancamentosPorData, vincularEventoSanitarioReprodutivo, confirmarExclusao, formatBRL } from "@/lib/api";
import { pedirLancamentoFinanceiroDeEvento } from "@/lib/vinculoSanitarioFinanceiroBridge";

export type OrigemPopupVinculo = {
  tipo: "sanidade" | "exame" | "servico";
  ids: number[];
  produto: string;
  data: string;
  responsavel?: string | null;
};

/**
 * "Você deseja: 1) lançar este evento em contas a pagar; 2) associar este
 * evento a uma conta paga/a pagar; 3) não se aplica" — disparado ao salvar
 * uma vacina/exame (Sanitário Preventivo) ou um diagnóstico de gestação, para
 * garantir rastreabilidade entre o lançamento sanitário/reprodutivo e o
 * financeiro (ver PlanoContaGerencial.pede_vinculo_sanitario_reprodutivo e
 * POST /financeiro/vincular-evento-sanitario-reprodutivo).
 */
export function PopupVinculoFinanceiro({
  origem, onFechar, onCancelar,
}: {
  origem: OrigemPopupVinculo;
  onFechar: () => void;
  /** Opcional — quando presente, mostra um 4º botão "Cancelar" que desfaz o
   * lançamento recém-salvo (exclui os registros de `origem.ids`, mesma trilha
   * de auditoria/aprovação da Exclusão) e volta para a tela de lançamento
   * pronta para editar, em vez de só fechar o popup. */
  onCancelar?: () => void;
}) {
  const [associando, setAssociando] = useState(false);
  const [candidatos, setCandidatos] = useState<{ numero_lancamento: string; fornecedor_cliente: string | null; descricao: string | null; valor_total: number; status: string }[] | null>(null);
  const [vinculando, setVinculando] = useState(false);
  const [cancelando, setCancelando] = useState(false);

  function lancarEmContasAPagar() {
    pedirLancamentoFinanceiroDeEvento({
      tipo: origem.tipo, ids: origem.ids, produto: origem.produto,
      data_emissao: origem.data, responsavel: origem.responsavel,
    });
    window.location.href = "/lancamentos?ir=financeiro_despesa";
  }

  function abrirAssociar() {
    setAssociando(true);
    fetchLancamentosPorData(origem.data, "despesa").then(setCandidatos).catch(() => setCandidatos([]));
  }

  async function associarA(numeroLancamento: string) {
    setVinculando(true);
    try {
      await vincularEventoSanitarioReprodutivo({ tipo: origem.tipo, ids: origem.ids, numero_lancamento: numeroLancamento });
    } catch { /* ignore */ }
    setVinculando(false);
    onFechar();
  }

  async function cancelar() {
    if (!onCancelar) return;
    setCancelando(true);
    try {
      await Promise.all(origem.ids.map((id) => confirmarExclusao(origem.tipo, String(id))));
    } catch { /* ignore — o botão "Cancelar" não deve travar por falha de rede aqui */ }
    setCancelando(false);
    onCancelar();
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
      <div className="card" style={{ width: "520px", maxWidth: "95vw" }}>
        <div className="flex items-center gap-2 mb-2"><Link2 size={18} style={{ color: "var(--dourado)" }} /><strong>Vincular ao financeiro?</strong></div>
        {!associando ? (
          <>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
              Você deseja:
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <button type="button" className="btn-primary" style={{ fontSize: "0.82rem", justifyContent: "flex-start" }} onClick={lancarEmContasAPagar}>
                1) Lançar este evento em contas a pagar
              </button>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.82rem", justifyContent: "flex-start", border: "1px solid var(--border)" }} onClick={abrirAssociar}>
                2) Associar este evento a uma conta paga/a pagar
              </button>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.82rem", justifyContent: "flex-start" }} onClick={onFechar}>
                3) Não se aplica
              </button>
              {onCancelar && (
                <button type="button" className="btn-ghost" disabled={cancelando}
                  style={{ fontSize: "0.82rem", justifyContent: "flex-start", color: "var(--red)", border: "1px solid var(--red)" }}
                  onClick={cancelar}>
                  <X size={14} /> {cancelando ? "Cancelando…" : "Cancelar — não salvar, voltar para editar"}
                </button>
              )}
            </div>
          </>
        ) : (
          <>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
              Lançamentos com data de emissão igual à deste evento ({new Date(origem.data + "T00:00:00").toLocaleDateString("pt-BR")}):
            </p>
            <div style={{ maxHeight: "40vh", overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {candidatos === null && <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Carregando…</p>}
              {candidatos?.length === 0 && <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhum lançamento com essa data de emissão.</p>}
              {candidatos?.map((c) => (
                <button key={c.numero_lancamento} type="button" className="btn-ghost" disabled={vinculando}
                  style={{ textAlign: "left", fontSize: "0.82rem", padding: "0.5rem 0.7rem", border: "1px solid var(--border)", borderRadius: 6 }}
                  onClick={() => associarA(c.numero_lancamento)}>
                  <strong>{c.numero_lancamento}</strong> — {c.fornecedor_cliente || c.descricao || "—"}
                  <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>{formatBRL(c.valor_total)} · {c.status}</div>
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3 mt-3">
              <button className="btn-ghost" onClick={() => setAssociando(false)}><X size={14} /> Voltar</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
