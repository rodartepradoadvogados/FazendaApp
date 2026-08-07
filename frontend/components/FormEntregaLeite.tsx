"use client";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Pencil, Trash2, Check, X } from "lucide-react";
import { criarEntregaLeiteMensal, fetchEntregaLeiteMensal, atualizarEntregaLeite, confirmarExclusao, ehAdmin } from "@/lib/api";
import { Campo, inputStyle, nota } from "@/components/lancamentos/comumForms";

type EntregaLeite = {
  id: number;
  competencia: string;
  quantidade_litros: number;
  observacao: string | null;
  usuario_nome: string | null;
};

// Mês (competência "YYYY-MM") no formato mm/aaaa para exibição na tabela.
function formatarCompetencia(competencia: string): string {
  const [ano, mes] = competencia.split("-");
  return mes && ano ? `${mes}/${ano}` : competencia;
}

export function FormEntregaLeite() {
  const admin = ehAdmin();
  const [competencia, setCompetencia] = useState(() => new Date().toISOString().slice(0, 7));
  const [quantidade, setQuantidade] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Entregas já lançadas — G6: editar (corrigir a competência/valor errado)
  // e excluir (via motor genérico de exclusões, tipo "entrega_leite").
  const [registros, setRegistros] = useState<EntregaLeite[] | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [editVals, setEditVals] = useState({ competencia: "", quantidade: "", observacao: "" });

  const carregarRegistros = useCallback(() => {
    fetchEntregaLeiteMensal().then((d) => setRegistros(d.registros ?? [])).catch(() => setRegistros([]));
  }, []);
  useEffect(carregarRegistros, [carregarRegistros]);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!competencia) { setErro("Selecione o mês."); return; }
    if (!quantidade || Number(quantidade) <= 0) { setErro("Informe a quantidade entregue (litros)."); return; }

    setSalvando(true);
    try {
      await criarEntregaLeiteMensal({ competencia, quantidade_litros: Number(quantidade.replace(",", ".")), observacao: observacao || undefined });
      setSucesso(`Entrega de ${competencia} lançada com sucesso.`);
      setQuantidade(""); setObservacao("");
      carregarRegistros();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar entrega mensal do leite");
    } finally {
      setSalvando(false);
    }
  }

  const iniciarEdicao = (r: EntregaLeite) => {
    setEditId(r.id);
    setEditVals({ competencia: r.competencia, quantidade: String(r.quantidade_litros), observacao: r.observacao || "" });
  };

  const salvarEdicao = async (r: EntregaLeite) => {
    setOcupado(r.id); setErro(null);
    try {
      await atualizarEntregaLeite(r.id, {
        competencia: editVals.competencia,
        quantidade_litros: Number(editVals.quantidade.replace(",", ".")),
        observacao: editVals.observacao.trim() || null,
      });
      setEditId(null);
      carregarRegistros();
    } catch (e: any) { setErro(e.message || "Erro ao editar entrega de leite"); }
    finally { setOcupado(null); }
  };

  // Passa pelo fluxo central e auditado de exclusão (POST /exclusoes/confirmar)
  // — admin exclui na hora, operador solicita e aguarda aprovação (mesmo
  // padrão de app/sanidade/page.tsx).
  const excluir = async (r: EntregaLeite) => {
    const msg = admin
      ? `Excluir a entrega de ${formatarCompetencia(r.competencia)}? Isso não pode ser desfeito.`
      : `Solicitar a exclusão da entrega de ${formatarCompetencia(r.competencia)}? Um administrador precisa aprovar antes de ser excluída de fato.`;
    if (!window.confirm(msg)) return;
    setOcupado(r.id); setErro(null); setAvisoExclusao(null);
    try {
      const resultado = await confirmarExclusao("entrega_leite", String(r.id));
      if (resultado.status === "excluido") {
        carregarRegistros();
      } else {
        setAvisoExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
    } catch (e: any) { setErro(e.message || "Erro ao excluir"); }
    finally { setOcupado(null); }
  };

  const inp: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "5px", padding: "0.25rem 0.4rem", fontSize: "0.75rem", width: "100%" };

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Mês (competência)"><input type="month" style={inputStyle} value={competencia} onChange={(e) => setCompetencia(e.target.value)} /></Campo>
        <Campo label="Quantidade entregue (litros)"><input type="number" inputMode="decimal" style={inputStyle} value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="soma das notinhas/app do laticínio no mês" /></Campo>
        <Campo label="Observação" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>
      <p style={nota}>Some as notinhas de entrega (ou o total do app do laticínio) do mês inteiro e lance aqui uma vez por mês — o relatório de Produção compara com o controle leiteiro projetado e a receita recebida.</p>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>

      <div className="card mt-4" style={{ padding: 0 }}>
        <div className="card-header m-3">Entregas lançadas</div>
        {avisoExclusao && <p style={{ color: "var(--green-light)", fontSize: "0.78rem", margin: "0 0.75rem 0.5rem" }}>{avisoExclusao}</p>}
        <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
          <table className="fazenda-table" style={{ margin: 0 }}>
            <thead>
              <tr><th>Mês</th><th style={{ textAlign: "right" }}>Litros</th><th>Observação</th><th style={{ textAlign: "right" }}>Ações</th></tr>
            </thead>
            <tbody>
              {(registros ?? []).map((r) => {
                const editando = editId === r.id;
                return (
                  <Fragment key={r.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{formatarCompetencia(r.competencia)}</td>
                      <td style={{ textAlign: "right" }}>{r.quantidade_litros} L</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.observacao || "—"}</td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        {!editando && (
                          <span style={{ display: "inline-flex", gap: "0.3rem" }}>
                            <button title="Editar" onClick={() => iniciarEdicao(r)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2 }}><Pencil size={14} /></button>
                            <button title={admin ? "Excluir" : "Solicitar exclusão"} disabled={ocupado === r.id} onClick={() => excluir(r)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}><Trash2 size={14} /></button>
                          </span>
                        )}
                      </td>
                    </tr>
                    {editando && (
                      <tr>
                        <td colSpan={4} style={{ background: "var(--surface-2)", padding: "0.6rem" }}>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                            <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Mês</label>
                              <input type="month" style={inp} value={editVals.competencia} onChange={(e) => setEditVals((s) => ({ ...s, competencia: e.target.value }))} /></div>
                            <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Litros</label>
                              <input type="number" inputMode="decimal" style={inp} value={editVals.quantidade} onChange={(e) => setEditVals((s) => ({ ...s, quantidade: e.target.value }))} /></div>
                            <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Observação</label>
                              <input style={inp} value={editVals.observacao} onChange={(e) => setEditVals((s) => ({ ...s, observacao: e.target.value }))} /></div>
                          </div>
                          <div className="flex gap-2 mt-2">
                            <button className="btn-primary" disabled={ocupado === r.id} onClick={() => salvarEdicao(r)} style={{ fontSize: "0.78rem" }}><Check size={13} /> {ocupado === r.id ? "…" : "Salvar"}</button>
                            <button className="btn-ghost" disabled={ocupado === r.id} onClick={() => setEditId(null)} style={{ fontSize: "0.78rem" }}><X size={13} /> Cancelar</button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {!(registros ?? []).length && <tr><td colSpan={4} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma entrega lançada ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
