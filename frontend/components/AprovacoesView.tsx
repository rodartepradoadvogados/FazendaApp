"use client";
import { useEffect, useState } from "react";
import { Check, X, RefreshCw, Inbox, Pencil, Plus, Trash2 } from "lucide-react";
import {
  fetchAprovacoes, aprovarLancamento, rejeitarLancamento, editarLancamentoPendente, ehAdmin,
  fetchFornecedores, fetchOpcoesFinanceiro, fetchPlanoContas, formatBRL, type LancamentoPendente,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import NovoFornecedorRapido from "@/components/NovoFornecedorRapido";
import NovaContaGerencial from "@/components/NovaContaGerencial";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import type { ContaPlano } from "@/lib/contaGerencial";

const OCULTAR = new Set(["_ops", "_nome"]);
const rotuloCampo = (k: string) => k.replace(/_/g, " ");
const valorCampo = (v: any) => {
  if (ehArrayDeObjetos(v)) return v.map((it: any) => it?.produto ? `${it.produto}${it.quantidade ? ` (${it.quantidade}x)` : ""} — R$ ${Number(it.valor_total ?? 0).toFixed(2)}` : JSON.stringify(it)).join("; ");
  return Array.isArray(v) ? v.join(", ") : String(v);
};
// "itens" da despesa/receita é lista de objetos (produto/quantidade/valor) — não
// dá pra editar como texto separado por vírgula sem corromper a estrutura.
function ehArrayDeObjetos(v: any) { return Array.isArray(v) && v.some((x) => x && typeof x === "object"); }
const hoje = () => new Date().toISOString().slice(0, 10);

// Campos com lista fixa de opções — evita erro de digitação (ex.: unidade).
const OPCOES_CAMPO: Record<string, string[]> = {
  unidade: ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"],
  cria_sexo: ["F", "M"],
  resultado: ["reconfirmada", "retoque", "negativo"],
  tipo_servico: ["IA", "Monta natural"],
  tipo_baixa: ["morte", "descarte_voluntario", "descarte_involuntario"],
};
// Campos de data — viram <input type="date"> em vez de texto livre.
const DATA_CAMPO = (k: string) => k === "data" || k.startsWith("data_");

// Lançamentos financeiros do robô (documento lido) — o fornecedor/cliente
// precisa vir do cadastro real, nunca texto livre (mesma regra do site), e o
// valor/produto/parcelamento/pagamento ganham a mesma UI rica do Financeiro.
const TIPOS_FINANCEIROS = new Set(["despesa", "receita"]);
// Estes campos do payload financeiro têm edição dedicada (abaixo) — somem do
// formulário genérico de campo-a-campo para não duplicar a UI.
const CAMPOS_FINANCEIROS_DEDICADOS = new Set([
  "itens", "valor_total", "parcelas", "forma_pagamento", "conta_bancaria", "numero_documento_pagamento",
]);

const inputStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.82rem", width: "100%",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };

type ItemEdit = {
  produto: string; codigo_conta_gerencial: string; nome_conta_gerencial: string;
  quantidade: string; valor_unitario: string; valor_total: string;
};
const itemVazio = (): ItemEdit => ({ produto: "", codigo_conta_gerencial: "", nome_conta_gerencial: "", quantidade: "", valor_unitario: "", valor_total: "" });
type ParcelaEdit = { data_vencimento: string; valor: string };

function dividirParcelas(valorTotal: number, qtd: number, primeiraData: string): ParcelaEdit[] {
  if (qtd <= 0) return [];
  const base = Math.floor((valorTotal / qtd) * 100) / 100;
  const resto = Math.round((valorTotal - base * qtd) * 100) / 100;
  const inicio = primeiraData ? new Date(primeiraData + "T00:00:00") : new Date();
  return Array.from({ length: qtd }, (_, i) => {
    const d = new Date(inicio); d.setMonth(d.getMonth() + i);
    const valor = i === qtd - 1 ? base + resto : base;
    return { data_vencimento: d.toISOString().slice(0, 10), valor: valor.toFixed(2) };
  });
}

/**
 * Fila de aprovação dos lançamentos enviados pelo Telegram (pesagem, parto,
 * secagem, troca de lote…). Só a conta principal (admin) aprova: aprovar cria
 * o registro de verdade; rejeitar descarta. Antes de aprovar, dá para EDITAR
 * os dados (ex.: corrigir a unidade). Despesa/receita (documento lido) ganham
 * a mesma UI rica do Financeiro: produto/conta gerencial, parcelamento e
 * marcação de "já pago". Usada no site e no app.
 */
export function AprovacoesView({ compacto = false }: { compacto?: boolean }) {
  const [itens, setItens] = useState<LancamentoPendente[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [editVals, setEditVals] = useState<Record<string, string>>({});
  const [fornecedoresCadastro, setFornecedoresCadastro] = useState<string[]>([]);
  const [abrirNovoFornecedor, setAbrirNovoFornecedor] = useState(false);
  const [abrirNovaConta, setAbrirNovaConta] = useState<number | null>(null);
  const [tiposDocumento, setTiposDocumento] = useState<string[]>([]);
  const [formasPagamento, setFormasPagamento] = useState<string[]>([]);
  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  // Estado dedicado do lançamento financeiro em edição (produtos/parcelas/pagamento).
  const [editItens, setEditItens] = useState<ItemEdit[]>([]);
  const [parcelado, setParcelado] = useState(false);
  const [qtdParcelas, setQtdParcelas] = useState(2);
  const [parcelas, setParcelas] = useState<ParcelaEdit[]>([]);
  const [jaPago, setJaPago] = useState(false);
  const [dataPagamento, setDataPagamento] = useState(hoje());
  const [formaPagamento, setFormaPagamento] = useState("");
  const [contaBancariaPag, setContaBancariaPag] = useState("");
  const [numeroDocPagamento, setNumeroDocPagamento] = useState("");
  const admin = ehAdmin();

  const carregar = () => fetchAprovacoes().then(setItens).catch((e) => setErro(e.message));
  useEffect(() => {
    if (!admin) return;
    carregar();
    fetchFornecedores().then((d) => setFornecedoresCadastro((d || []).map((f: any) => f.nome))).catch(() => {});
    fetchOpcoesFinanceiro().then((o) => {
      setTiposDocumento(o?.tipos_documento || []);
      setFormasPagamento(o?.formas_pagamento || []);
    }).catch(() => {});
    fetchPlanoContas().then(setPlanoContas).catch(() => {});
  }, [admin]);

  if (!admin) {
    return <div className="card"><p style={{ color: "var(--text-muted)" }}>Só a conta principal pode ver e aprovar os lançamentos pendentes.</p></div>;
  }

  const ehFinanceiro = (it: LancamentoPendente) => TIPOS_FINANCEIROS.has(it.tipo);
  const campos = (it: LancamentoPendente) => Object.entries(it.dados).filter(([k]) => !OCULTAR.has(k));
  const camposEditaveis = (it: LancamentoPendente) => campos(it).filter(([k]) => !(ehFinanceiro(it) && CAMPOS_FINANCEIROS_DEDICADOS.has(k)));

  // Fornecedor/cliente de despesa/receita só pode ser um já cadastrado — nunca
  // texto livre (evita repetir o bug de "Comercial Montividiu" nunca cadastrado).
  const ehCampoFornecedor = (it: LancamentoPendente, k: string) => TIPOS_FINANCEIROS.has(it.tipo) && k === "fornecedor_cliente";
  const fornecedorInvalido = (it: LancamentoPendente, valor: string) => {
    const v = (valor || "").trim();
    return !!v && !fornecedoresCadastro.includes(v);
  };

  const valorTotalItens = (lista: ItemEdit[]) => lista.reduce((s, it) => s + (Number(it.valor_total) || 0), 0);

  const iniciarEdicao = (it: LancamentoPendente) => {
    const vals: Record<string, string> = {};
    camposEditaveis(it).forEach(([k, v]) => { vals[k] = valorCampo(v); });
    // Data com valor vazio já entra com hoje (default pedido pelo usuário).
    Object.keys(vals).forEach((k) => { if (DATA_CAMPO(k) && !vals[k]) vals[k] = hoje(); });
    // tipo_documento antigo do OCR vem em minúsculo/sem espaço ("nota_fiscal") —
    // troca pelo rótulo do cadastro quando reconhece, pra já abrir certo no dropdown.
    if (ehFinanceiro(it) && vals["tipo_documento"]) {
      const bruto = vals["tipo_documento"].toLowerCase();
      const achado = tiposDocumento.find((o) => o.toLowerCase() === bruto || o.toLowerCase().replace(/\s+/g, "_") === bruto);
      if (achado) vals["tipo_documento"] = achado;
    }
    setEditVals(vals);

    if (ehFinanceiro(it)) {
      const itensOrig = Array.isArray(it.dados.itens) ? it.dados.itens : [];
      setEditItens(itensOrig.length ? itensOrig.map((i: any) => ({
        produto: i.produto || "", codigo_conta_gerencial: i.codigo_conta_gerencial || "", nome_conta_gerencial: i.nome_conta_gerencial || "",
        quantidade: i.quantidade != null ? String(i.quantidade) : "", valor_unitario: i.valor_unitario != null ? String(i.valor_unitario) : "",
        valor_total: i.valor_total != null ? String(i.valor_total) : "",
      })) : [{ ...itemVazio(), valor_total: it.dados.valor_total != null ? String(it.dados.valor_total) : "" }]);

      const parcelasOrig = Array.isArray(it.dados.parcelas) ? it.dados.parcelas : [];
      setParcelado(parcelasOrig.length > 0);
      setQtdParcelas(parcelasOrig.length || 2);
      setParcelas(parcelasOrig.map((p: any) => ({ data_vencimento: p.data_vencimento, valor: String(p.valor) })));

      setJaPago(!!it.dados.data_pagamento && !parcelasOrig.length);
      setDataPagamento(it.dados.data_pagamento || hoje());
      setFormaPagamento(it.dados.forma_pagamento || "");
      setContaBancariaPag(it.dados.conta_bancaria || "");
      setNumeroDocPagamento(it.dados.numero_documento_pagamento || "");
    }
    setEditId(it.id);
    setErro(null);
  };

  const regerarParcelas = (it: LancamentoPendente, qtd: number) => {
    const total = valorTotalItens(editItens);
    setParcelas(dividirParcelas(total, qtd, editVals["data_emissao"] || hoje()));
    setQtdParcelas(qtd);
  };

  const salvarEdicao = async (it: LancamentoPendente) => {
    setOcupado(it.id); setErro(null);
    try {
      const novos: Record<string, any> = {};
      camposEditaveis(it).forEach(([k, orig]) => {
        if (ehArrayDeObjetos(orig)) { novos[k] = orig; return; }
        const txt = (editVals[k] ?? "").trim();
        novos[k] = Array.isArray(orig) ? txt.split(/[,\s]+/).filter(Boolean) : txt;
      });

      if (ehFinanceiro(it)) {
        const itensValidos = editItens.filter((i) => i.produto.trim());
        novos.itens = itensValidos.map((i) => ({
          produto: i.produto.trim(),
          codigo_conta_gerencial: i.codigo_conta_gerencial || undefined,
          nome_conta_gerencial: i.nome_conta_gerencial || undefined,
          quantidade: i.quantidade ? Number(i.quantidade) : undefined,
          valor_unitario: i.valor_unitario ? Number(i.valor_unitario) : undefined,
          valor_total: Number(i.valor_total) || (i.quantidade && i.valor_unitario ? Number(i.quantidade) * Number(i.valor_unitario) : 0),
        }));
        novos.valor_total = valorTotalItens(editItens);
        if (parcelado) {
          novos.parcelas = parcelas.map((p) => ({ data_vencimento: p.data_vencimento, valor: Number(p.valor) || 0 }));
          novos.data_pagamento = null; novos.forma_pagamento = null; novos.conta_bancaria = null; novos.numero_documento_pagamento = null;
        } else {
          novos.parcelas = [];
          if (jaPago) {
            novos.data_pagamento = dataPagamento; novos.forma_pagamento = formaPagamento || null;
            novos.conta_bancaria = contaBancariaPag || null; novos.numero_documento_pagamento = numeroDocPagamento || null;
          } else {
            novos.data_pagamento = null; novos.forma_pagamento = null; novos.conta_bancaria = null; novos.numero_documento_pagamento = null;
          }
        }
      }

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
          const financeiro = ehFinanceiro(it);
          const fornecedorInvalidoAtual = campos(it).some(([k, v]) => ehCampoFornecedor(it, k) && fornecedorInvalido(it, valorCampo(v)));
          const fornecedorInvalidoEdicao = editando && camposEditaveis(it).some(([k]) => ehCampoFornecedor(it, k) && fornecedorInvalido(it, editVals[k] ?? ""));
          return (
          <div key={it.id} className="card">
            <div className="flex items-center justify-between" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 700 }}>{it.rotulo}</span>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                {it.solicitante_nome ? `por ${it.solicitante_nome} · ` : ""}{it.criado_em ? new Date(it.criado_em).toLocaleString("pt-BR") : ""}
              </span>
            </div>

            {!editando ? (
              <table style={{ width: "100%", maxWidth: 560, fontSize: "0.82rem", marginTop: "0.5rem" }}>
                <tbody>
                  {campos(it).map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ padding: "0.12rem 0.6rem 0.12rem 0", color: "var(--text-muted)", textTransform: "capitalize", whiteSpace: "nowrap" }}>{rotuloCampo(k)}</td>
                      <td style={{ fontWeight: 600, color: ehCampoFornecedor(it, k) && fornecedorInvalido(it, valorCampo(v)) ? "var(--red)" : undefined }}>
                        {k === "valor_total" ? formatBRL(Number(v) || 0) : valorCampo(v)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2" style={{ marginTop: "0.6rem" }}>
                {camposEditaveis(it).map(([k, orig]) => (
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
                    ) : financeiro && k === "tipo_documento" ? (
                      <select style={inputStyle} value={editVals[k] ?? ""} onChange={(e) => setEditVals((s) => ({ ...s, [k]: e.target.value }))}>
                        {!tiposDocumento.includes(editVals[k] ?? "") && <option value={editVals[k] ?? ""}>{editVals[k] || "—"}</option>}
                        {tiposDocumento.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : DATA_CAMPO(k) ? (
                      <input type="date" style={inputStyle} value={editVals[k] ?? ""} onChange={(e) => setEditVals((s) => ({ ...s, [k]: e.target.value }))} />
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

              {financeiro && (
                <div style={{ marginTop: "0.8rem", borderTop: "1px solid var(--border)", paddingTop: "0.7rem" }}>
                  <p style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "0.4rem" }}>Produtos/serviços</p>
                  <div style={{ display: "grid", gap: "0.5rem" }}>
                    {editItens.map((item, idx) => (
                      <div key={idx} className="grid grid-cols-2 md:grid-cols-6 gap-2" style={{ alignItems: "end", background: "var(--surface-2)", padding: "0.5rem", borderRadius: 8 }}>
                        <div style={{ gridColumn: "span 2" }}>
                          <label style={lbl}>Produto/serviço</label>
                          <input style={inputStyle} value={item.produto} onChange={(e) => setEditItens((s) => s.map((x, i) => i === idx ? { ...x, produto: e.target.value } : x))} />
                        </div>
                        <div style={{ gridColumn: "span 2" }}>
                          <label style={lbl}>Conta gerencial</label>
                          <SeletorContaGerencial
                            contas={planoContas} tipo={it.tipo === "receita" ? "receita" : "despesa"}
                            codigo={item.codigo_conta_gerencial} nome={item.nome_conta_gerencial}
                            onSelect={(codigo, nome) => setEditItens((s) => s.map((x, i) => i === idx ? { ...x, codigo_conta_gerencial: codigo, nome_conta_gerencial: nome } : x))}
                          />
                          <button type="button" className="btn-ghost" style={{ fontSize: "0.68rem", marginTop: "0.2rem" }} onClick={() => setAbrirNovaConta(idx)}>
                            <Plus size={11} /> Nova conta
                          </button>
                        </div>
                        <div><label style={lbl}>Qtd.</label><input type="number" style={inputStyle} value={item.quantidade} onChange={(e) => setEditItens((s) => s.map((x, i) => i === idx ? { ...x, quantidade: e.target.value } : x))} /></div>
                        <div><label style={lbl}>Vlr. unit.</label><input type="number" step="0.01" style={inputStyle} value={item.valor_unitario} onChange={(e) => setEditItens((s) => s.map((x, i) => i === idx ? { ...x, valor_unitario: e.target.value } : x))} /></div>
                        <div>
                          <label style={lbl}>Vlr. total (R$)</label>
                          <div className="flex items-center gap-1">
                            <input type="number" step="0.01" style={inputStyle} value={item.valor_total} onChange={(e) => setEditItens((s) => s.map((x, i) => i === idx ? { ...x, valor_total: e.target.value } : x))} />
                            <button type="button" className="btn-ghost" disabled={editItens.length <= 1} title="Remover item" style={{ padding: "0.3rem" }} onClick={() => setEditItens((s) => s.filter((_, i) => i !== idx))}>
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </div>
                        {abrirNovaConta === idx && (
                          <Modal title="Nova conta gerencial" onClose={() => setAbrirNovaConta(null)} width="480px">
                            <NovaContaGerencial
                              tipoSugerido={it.tipo === "receita" ? "receita" : "despesa"}
                              onCriado={(c) => {
                                setPlanoContas((s) => [...s, { codigo: c.codigo, nome: c.nome } as ContaPlano]);
                                setEditItens((s) => s.map((x, i) => i === idx ? { ...x, codigo_conta_gerencial: c.codigo, nome_conta_gerencial: c.nome } : x));
                                setAbrirNovaConta(null);
                              }}
                              onCancelar={() => setAbrirNovaConta(null)}
                            />
                          </Modal>
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => setEditItens((s) => [...s, itemVazio()])}>
                      <Plus size={13} /> Adicionar item
                    </button>
                    <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>Total: {formatBRL(valorTotalItens(editItens))}</span>
                  </div>

                  <div style={{ marginTop: "0.8rem", borderTop: "1px solid var(--border)", paddingTop: "0.6rem" }}>
                    <label className="flex items-center gap-2" style={{ fontSize: "0.82rem" }}>
                      <input type="checkbox" checked={parcelado} onChange={(e) => {
                        setParcelado(e.target.checked);
                        if (e.target.checked) { setJaPago(false); regerarParcelas(it, qtdParcelas); }
                      }} />
                      Parcelar este lançamento
                    </label>
                    {parcelado && (
                      <div style={{ marginTop: "0.5rem" }}>
                        <div className="flex items-center gap-2" style={{ marginBottom: "0.5rem" }}>
                          <label style={{ fontSize: "0.78rem" }}>Nº de parcelas</label>
                          <input type="number" min={2} style={{ ...inputStyle, width: 80 }} value={qtdParcelas} onChange={(e) => regerarParcelas(it, Math.max(2, Number(e.target.value) || 2))} />
                        </div>
                        <div style={{ overflowX: "auto" }}>
                          <table className="fazenda-table">
                            <thead><tr><th>Parcela</th><th>Vencimento</th><th>Valor</th></tr></thead>
                            <tbody>
                              {parcelas.map((p, i) => (
                                <tr key={i}>
                                  <td>{i + 1}/{parcelas.length}</td>
                                  <td><input type="date" style={inputStyle} value={p.data_vencimento} onChange={(e) => setParcelas((s) => s.map((x, j) => j === i ? { ...x, data_vencimento: e.target.value } : x))} /></td>
                                  <td><input type="number" step="0.01" style={inputStyle} value={p.valor} onChange={(e) => setParcelas((s) => s.map((x, j) => j === i ? { ...x, valor: e.target.value } : x))} /></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {!parcelado && (
                      <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", marginTop: "0.6rem" }}>
                        <input type="checkbox" checked={jaPago} onChange={(e) => setJaPago(e.target.checked)} />
                        Já foi {it.tipo === "receita" ? "recebido" : "pago"}
                      </label>
                    )}
                    {!parcelado && jaPago && (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2" style={{ marginTop: "0.5rem" }}>
                        <div><label style={lbl}>Data do pagamento</label><input type="date" style={inputStyle} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
                        <div>
                          <label style={lbl}>Forma de pagamento</label>
                          <select style={inputStyle} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)}>
                            <option value="">—</option>
                            {formasPagamento.map((f) => <option key={f} value={f}>{f}</option>)}
                          </select>
                        </div>
                        <div><label style={lbl}>Conta bancária</label><input style={inputStyle} value={contaBancariaPag} onChange={(e) => setContaBancariaPag(e.target.value)} /></div>
                        <div><label style={lbl}>Nº doc. pagamento</label><input style={inputStyle} value={numeroDocPagamento} onChange={(e) => setNumeroDocPagamento(e.target.value)} /></div>
                      </div>
                    )}
                  </div>
                </div>
              )}
              </>
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
