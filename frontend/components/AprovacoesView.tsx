"use client";
import { useEffect, useState } from "react";
import { Check, X, RefreshCw, Inbox, Pencil, Plus } from "lucide-react";
import {
  fetchAprovacoes, aprovarLancamento, rejeitarLancamento, editarLancamentoPendente, ehAdmin,
  fetchFornecedores, type LancamentoPendente,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import NovoFornecedorRapido from "@/components/NovoFornecedorRapido";

const OCULTAR = new Set(["_ops", "_nome"]);
const rotuloCampo = (k: string) => k.replace(/_/g, " ");
const valorCampo = (v: any) => {
  if (ehArrayDeObjetos(v)) return v.map((it: any) => it?.produto ? `${it.produto}${it.quantidade ? ` (${it.quantidade}x)` : ""} — R$ ${Number(it.valor_total ?? 0).toFixed(2)}` : JSON.stringify(it)).join("; ");
  return Array.isArray(v) ? v.join(", ") : String(v);
};
// "itens" da despesa/receita é lista de objetos (produto/quantidade/valor) — não
// dá pra editar como texto separado por vírgula sem corromper a estrutura.
function ehArrayDeObjetos(v: any) { return Array.isArray(v) && v.some((x) => x && typeof x === "object"); }

// Campos com lista fixa de opções — evita erro de digitação (ex.: unidade).
const OPCOES_CAMPO: Record<string, string[]> = {
  unidade: ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"],
  cria_sexo: ["F", "M"],
  resultado: ["reconfirmada", "retoque", "negativo"],
  tipo_servico: ["IA", "Monta natural"],
  tipo_baixa: ["morte", "descarte_voluntario", "descarte_involuntario"],
};

// Lançamentos financeiros do robô (documento lido) — o fornecedor/cliente
// precisa vir do cadastro real, nunca texto livre (mesma regra do site).
const TIPOS_FINANCEIROS = new Set(["despesa", "receita"]);

const inputStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.82rem", width: "100%",
};

/**
 * Fila de aprovação dos lançamentos enviados pelo Telegram (pesagem, parto,
 * secagem, troca de lote…). Só a conta principal (admin) aprova: aprovar cria
 * o registro de verdade; rejeitar descarta. Antes de aprovar, dá para EDITAR
 * os dados (ex.: corrigir a unidade). Usada no site e no app.
 */
export function AprovacoesView({ compacto = false }: { compacto?: boolean }) {
  const [itens, setItens] = useState<LancamentoPendente[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [editVals, setEditVals] = useState<Record<string, string>>({});
  const [fornecedoresCadastro, setFornecedoresCadastro] = useState<string[]>([]);
  const [abrirNovoFornecedor, setAbrirNovoFornecedor] = useState(false);
  const admin = ehAdmin();

  const carregar = () => fetchAprovacoes().then(setItens).catch((e) => setErro(e.message));
  useEffect(() => {
    if (!admin) return;
    carregar();
    fetchFornecedores().then((d) => setFornecedoresCadastro((d || []).map((f: any) => f.nome))).catch(() => {});
  }, [admin]);

  if (!admin) {
    return <div className="card"><p style={{ color: "var(--text-muted)" }}>Só a conta principal pode ver e aprovar os lançamentos pendentes.</p></div>;
  }

  const campos = (it: LancamentoPendente) => Object.entries(it.dados).filter(([k]) => !OCULTAR.has(k));

  // Fornecedor/cliente de despesa/receita só pode ser um já cadastrado — nunca
  // texto livre (evita repetir o bug de "Comercial Montividiu" nunca cadastrado).
  const ehCampoFornecedor = (it: LancamentoPendente, k: string) => TIPOS_FINANCEIROS.has(it.tipo) && k === "fornecedor_cliente";
  const fornecedorInvalido = (it: LancamentoPendente, valor: string) => {
    const v = (valor || "").trim();
    return !!v && !fornecedoresCadastro.includes(v);
  };

  const iniciarEdicao = (it: LancamentoPendente) => {
    const vals: Record<string, string> = {};
    campos(it).forEach(([k, v]) => { vals[k] = valorCampo(v); });
    setEditVals(vals);
    setEditId(it.id);
    setErro(null);
  };

  const salvarEdicao = async (it: LancamentoPendente) => {
    setOcupado(it.id); setErro(null);
    try {
      // Reconstrói os dados: o que era lista continua lista (separada por vírgula).
      const novos: Record<string, any> = {};
      campos(it).forEach(([k, orig]) => {
        if (ehArrayDeObjetos(orig)) { novos[k] = orig; return; }
        const txt = (editVals[k] ?? "").trim();
        novos[k] = Array.isArray(orig) ? txt.split(/[,\s]+/).filter(Boolean) : txt;
      });
      await editarLancamentoPendente(it.id, novos);
      setEditId(null);
      await carregar();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(null); }
  };

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
        {(itens || []).map((it) => {
          const editando = editId === it.id;
          const fornecedorInvalidoAtual = campos(it).some(([k, v]) => ehCampoFornecedor(it, k) && fornecedorInvalido(it, valorCampo(v)));
          const fornecedorInvalidoEdicao = editando && campos(it).some(([k]) => ehCampoFornecedor(it, k) && fornecedorInvalido(it, editVals[k] ?? ""));
          return (
          <div key={it.id} className="card">
            <div className="flex items-center justify-between" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 700 }}>{it.rotulo}</span>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                {it.solicitante_nome ? `por ${it.solicitante_nome} · ` : ""}{it.criado_em ? new Date(it.criado_em).toLocaleString("pt-BR") : ""}
              </span>
            </div>

            {!editando ? (
              <table style={{ width: "100%", maxWidth: 520, fontSize: "0.82rem", marginTop: "0.5rem" }}>
                <tbody>
                  {campos(it).map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ padding: "0.12rem 0.6rem 0.12rem 0", color: "var(--text-muted)", textTransform: "capitalize", whiteSpace: "nowrap" }}>{rotuloCampo(k)}</td>
                      <td style={{ fontWeight: 600, color: ehCampoFornecedor(it, k) && fornecedorInvalido(it, valorCampo(v)) ? "var(--red)" : undefined }}>{valorCampo(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2" style={{ marginTop: "0.6rem" }}>
                {campos(it).map(([k, orig]) => (
                  <div key={k}>
                    <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "capitalize" }}>
                      {rotuloCampo(k)}{Array.isArray(orig) && !ehArrayDeObjetos(orig) ? " (separe por vírgula)" : ""}
                    </label>
                    {ehArrayDeObjetos(orig) ? (
                      <p style={{ ...inputStyle, background: "transparent", border: "none", padding: "0.35rem 0" }}>{valorCampo(orig)}</p>
                    ) : ehCampoFornecedor(it, k) ? (
                      <>
                        <div className="flex items-center gap-2">
                          <select style={inputStyle} value={editVals[k] ?? ""} onChange={(e) => setEditVals((s) => ({ ...s, [k]: e.target.value }))}>
                            <option value="">—</option>
                            {fornecedoresCadastro.map((f) => <option key={f} value={f}>{f}</option>)}
                          </select>
                          <button type="button" className="btn-ghost" title="Cadastrar novo fornecedor/cliente" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoFornecedor(true)}>
                            <Plus size={13} /> Novo
                          </button>
                        </div>
                        {fornecedorInvalido(it, editVals[k] ?? "") && (
                          <p style={{ color: "var(--red)", fontSize: "0.72rem", marginTop: "0.2rem" }}>* Fornecedor não cadastrado — selecione um da lista ou cadastre um novo.</p>
                        )}
                      </>
                    ) : OPCOES_CAMPO[k] ? (
                      <select style={inputStyle} value={editVals[k] ?? ""} onChange={(e) => setEditVals((s) => ({ ...s, [k]: e.target.value }))}>
                        {!OPCOES_CAMPO[k].includes(editVals[k] ?? "") && <option value={editVals[k] ?? ""}>{editVals[k] || "—"}</option>}
                        {OPCOES_CAMPO[k].map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input style={inputStyle} value={editVals[k] ?? ""} onChange={(e) => setEditVals((s) => ({ ...s, [k]: e.target.value }))} />
                    )}
                  </div>
                ))}
                {abrirNovoFornecedor && (
                  <Modal title="Novo fornecedor/cliente" onClose={() => setAbrirNovoFornecedor(false)} width="480px">
                    <NovoFornecedorRapido
                      tipoSugerido={it.tipo === "receita" ? "receita" : "despesa"}
                      onCriado={(f) => {
                        setFornecedoresCadastro((s) => Array.from(new Set([...s, f.nome])));
                        setEditVals((s) => ({ ...s, fornecedor_cliente: f.nome }));
                        setAbrirNovoFornecedor(false);
                      }}
                      onCancelar={() => setAbrirNovoFornecedor(false)}
                    />
                  </Modal>
                )}
              </div>
            )}

            {it.erro && !editando && <p style={{ color: "var(--red)", fontSize: "0.78rem", marginTop: "0.4rem" }}>Tentativa anterior falhou: {it.erro} — toque em <strong>Editar</strong> para corrigir.</p>}
            {fornecedorInvalidoAtual && !editando && (
              <p style={{ color: "var(--red)", fontSize: "0.78rem", marginTop: "0.4rem" }}>* Fornecedor não cadastrado — toque em <strong>Editar</strong> para selecionar um da lista.</p>
            )}

            <div className="flex gap-2 mt-3" style={{ flexWrap: "wrap" }}>
              {editando ? (
                <>
                  <button className="btn-primary" disabled={ocupado === it.id || fornecedorInvalidoEdicao} title={fornecedorInvalidoEdicao ? "Corrija o fornecedor/cliente antes de salvar" : undefined} onClick={() => salvarEdicao(it)} style={{ fontSize: "0.82rem" }}>
                    <Check size={14} /> {ocupado === it.id ? "…" : "Salvar"}
                  </button>
                  <button className="btn-ghost" disabled={ocupado === it.id} onClick={() => setEditId(null)} style={{ fontSize: "0.82rem" }}>Cancelar</button>
                </>
              ) : (
                <>
                  <button className="btn-primary" disabled={ocupado === it.id || fornecedorInvalidoAtual} title={fornecedorInvalidoAtual ? "Corrija o fornecedor/cliente antes de aprovar" : "Aprovar e criar o registro de verdade"} onClick={() => decidir(it.id, "aprovar")} style={{ fontSize: "0.82rem" }}>
                    <Check size={14} /> {ocupado === it.id ? "…" : "Aprovar"}
                  </button>
                  <button className="btn-ghost" disabled={ocupado === it.id} onClick={() => iniciarEdicao(it)} title="Corrigir os dados antes de aprovar" style={{ fontSize: "0.82rem" }}>
                    <Pencil size={13} /> Editar
                  </button>
                  <button className="btn-ghost" disabled={ocupado === it.id} onClick={() => decidir(it.id, "rejeitar")} title="Rejeitar (não cria nada)" style={{ fontSize: "0.82rem" }}>
                    <X size={14} /> Rejeitar
                  </button>
                </>
              )}
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}
