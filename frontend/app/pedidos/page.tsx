"use client";
import { useEffect, useMemo, useState } from "react";
import { ShoppingCart, Filter, Plus, Pencil, Trash2, ChevronDown, ChevronRight, Receipt, Package } from "lucide-react";
import {
  fetchPedidos, fetchPedido, criarPedido, atualizarPedido, atualizarStatusPedido, excluirPedido, fetchOpcoesPedidos,
  fetchCentrosCusto, fetchPlanoContas, formatBRL, formatDate,
  type PedidoPayload, type PedidoItemPayload,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import type { ContaPlano } from "@/lib/contaGerencial";
import { Indicador } from "@/components/ui";

type PedidoItemRow = PedidoItemPayload & { id: number; valor_atendido: number };
type PedidoRow = {
  id: number; numero_pedido: string; tipo: "compra" | "venda"; fornecedor_cliente: string | null;
  centro_custo: string | null; data_pedido: string; data_prevista: string | null; status: string;
  observacao: string | null; responsavel: string | null; origem_tipo: string | null;
  itens: PedidoItemRow[]; valor_total_estimado: number; valor_atendido: number;
};

const STATUS_INFO: Record<string, { label: string; cor: string }> = {
  aberto: { label: "Aberto", cor: "var(--amber)" },
  parcialmente_atendido: { label: "Parcialmente atendido", cor: "var(--dourado-light)" },
  atendido: { label: "Atendido", cor: "var(--green-light)" },
  cancelado: { label: "Cancelado", cor: "var(--text-muted)" },
};

const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };

function Badge({ status }: { status: string }) {
  const info = STATUS_INFO[status] || { label: status, cor: "var(--text-muted)" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.72rem", fontWeight: 600,
      color: info.cor, border: `1px solid ${info.cor}`, borderRadius: "999px", padding: "0.15rem 0.55rem",
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: info.cor }} />
      {info.label}
    </span>
  );
}

function KPI({ v, l, c }: { v: string; l: string; c?: string }) {
  return <Indicador categoria="geral" valor={v} rotulo={l} cor={c} />;
}

export default function PedidosPage() {
  const [pedidos, setPedidos] = useState<PedidoRow[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [opcoes, setOpcoes] = useState<{ fornecedores: string[]; clientes: string[]; servicos: string[] }>({ fornecedores: [], clientes: [], servicos: [] });
  const [centros, setCentros] = useState<string[]>([]);
  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);

  const [tipoFiltro, setTipoFiltro] = useState("");
  const [statusFiltro, setStatusFiltro] = useState("");
  const [fornecedorFiltro, setFornecedorFiltro] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");

  const [expandido, setExpandido] = useState<number | null>(null);
  const [editando, setEditando] = useState<PedidoRow | "novo" | null>(null);

  const recarregar = () => fetchPedidos({
    tipo: tipoFiltro || undefined, status: statusFiltro || undefined, fornecedor_cliente: fornecedorFiltro || undefined,
    data_inicio: dataInicio || undefined, data_fim: dataFim || undefined,
  }).then(setPedidos).catch((e) => setErro(e.message));

  useEffect(() => { recarregar(); }, [tipoFiltro, statusFiltro, fornecedorFiltro, dataInicio, dataFim]);
  useEffect(() => {
    fetchOpcoesPedidos().then(setOpcoes).catch(() => {});
    fetchCentrosCusto().then((d) => setCentros(d.filter((c: any) => c.ativo).map((c: any) => c.nome))).catch(() => {});
    fetchPlanoContas().then(setPlanoContas).catch(() => {});
  }, []);

  const todosFornecedoresClientes = useMemo(() => Array.from(new Set([...opcoes.fornecedores, ...opcoes.clientes])).sort(), [opcoes]);

  async function excluir(id: number) {
    if (!confirm("Excluir este pedido? Só é possível se não houver lançamento financeiro vinculado.")) return;
    try { await excluirPedido(id); recarregar(); } catch (e: any) { alert(e.message); }
  }

  async function mudarStatus(id: number, status: string) {
    await atualizarStatusPedido(id, status);
    recarregar();
  }

  const totalEstimado = (pedidos ?? []).reduce((a, p) => a + p.valor_total_estimado, 0);
  const totalAtendido = (pedidos ?? []).reduce((a, p) => a + p.valor_atendido, 0);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><ShoppingCart size={22} style={{ color: "var(--dourado)" }} /> Pedidos</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Intenção de compra ou venda — não gera movimentação de estoque nem lançamento financeiro por si só.
          Só passa a refletir em Estoque/Financeiro quando uma nota fiscal, recibo ou entrada de estoque é lançada e vinculada a este pedido.
        </p>
      </div>

      {erro && <div className="alert-critico mb-4"><span>{erro}</span></div>}

      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={labelStyle}>Tipo</label>
            <select style={inputStyle} value={tipoFiltro} onChange={(e) => setTipoFiltro(e.target.value)}>
              <option value="">Todos</option><option value="compra">Compra</option><option value="venda">Venda</option>
            </select></div>
          <div><label style={labelStyle}>Status</label>
            <select style={inputStyle} value={statusFiltro} onChange={(e) => setStatusFiltro(e.target.value)}>
              <option value="">Todos</option>
              {Object.entries(STATUS_INFO).map(([id, info]) => <option key={id} value={id}>{info.label}</option>)}
            </select></div>
          <div><label style={labelStyle}>Fornecedor / cliente</label>
            <select style={inputStyle} value={fornecedorFiltro} onChange={(e) => setFornecedorFiltro(e.target.value)}>
              <option value="">Todos</option>{todosFornecedoresClientes.map((f) => <option key={f} value={f}>{f}</option>)}
            </select></div>
          <div><label style={labelStyle}>Início</label><input type="date" style={inputStyle} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></div>
          <div><label style={labelStyle}>Fim</label><input type="date" style={inputStyle} value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></div>
          <button className="btn-primary" style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem", marginLeft: "auto" }} onClick={() => setEditando("novo")}>
            <Plus size={14} /> Novo pedido
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <KPI v={String((pedidos ?? []).length)} l="Pedidos" />
        <KPI v={formatBRL(totalEstimado)} l="Valor estimado" c="var(--dourado-light)" />
        <KPI v={formatBRL(totalAtendido)} l="Valor já atendido" c="var(--green-light)" />
        <KPI v={String((pedidos ?? []).filter((p) => p.status === "aberto").length)} l="Em aberto" c="var(--amber)" />
      </div>

      <div className="card">
        <div className="card-header mb-3">Pedidos</div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <th></th><th>Nº pedido</th><th>Tipo</th><th>Fornecedor/Cliente</th><th>Centro custo</th>
                <th>Data</th><th>Status</th><th style={{ textAlign: "right" }}>Estimado</th><th style={{ textAlign: "right" }}>Atendido</th><th></th>
              </tr>
            </thead>
            <tbody>
              {(pedidos ?? []).map((p) => (
                <PedidoLinha key={p.id} pedido={p}
                  expandido={expandido === p.id} onToggle={() => setExpandido(expandido === p.id ? null : p.id)}
                  onEditar={() => setEditando(p)} onExcluir={() => excluir(p.id)} onMudarStatus={(s) => mudarStatus(p.id, s)} />
              ))}
              {pedidos && !pedidos.length && <tr><td colSpan={10} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Nenhum pedido encontrado.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {editando && (
        <Modal onClose={() => setEditando(null)} title={editando === "novo" ? "Novo pedido" : `Editar pedido ${editando.numero_pedido}`}>
          <FormPedido
            pedido={editando === "novo" ? null : editando}
            opcoes={opcoes} centros={centros} planoContas={planoContas}
            onSalvo={() => { setEditando(null); recarregar(); }} onCancelar={() => setEditando(null)} />
        </Modal>
      )}
    </div>
  );
}

function PedidoLinha({ pedido, expandido, onToggle, onEditar, onExcluir, onMudarStatus }: {
  pedido: PedidoRow; expandido: boolean; onToggle: () => void; onEditar: () => void; onExcluir: () => void; onMudarStatus: (s: string) => void;
}) {
  const [detalhe, setDetalhe] = useState<{ lancamentos: any[]; movimentos_estoque: any[] } | null>(null);
  useEffect(() => {
    if (expandido && !detalhe) fetchPedido(pedido.id).then(setDetalhe).catch(() => {});
  }, [expandido]);

  return (
    <>
      <tr className="row-clickable" onClick={onToggle} style={{ cursor: "pointer" }}>
        <td style={{ width: 24 }}>{expandido ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
        <td style={{ fontSize: "0.82rem", fontWeight: 600 }}>{pedido.numero_pedido}</td>
        <td style={{ fontSize: "0.78rem", color: pedido.tipo === "venda" ? "var(--green-light)" : "var(--red)" }}>{pedido.tipo === "venda" ? "Venda" : "Compra"}</td>
        <td style={{ fontSize: "0.82rem" }}>{pedido.fornecedor_cliente || "—"}</td>
        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{pedido.centro_custo || "—"}</td>
        <td style={{ fontSize: "0.78rem" }}>{formatDate(pedido.data_pedido)}</td>
        <td><Badge status={pedido.status} /></td>
        <td style={{ textAlign: "right", fontSize: "0.82rem" }}>{formatBRL(pedido.valor_total_estimado)}</td>
        <td style={{ textAlign: "right", fontSize: "0.82rem", color: "var(--green-light)" }}>{formatBRL(pedido.valor_atendido)}</td>
        <td onClick={(e) => e.stopPropagation()} style={{ display: "flex", gap: "0.4rem", justifyContent: "flex-end" }}>
          <button title="Editar" onClick={onEditar} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}><Pencil size={14} /></button>
          <button title="Excluir" onClick={onExcluir} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}><Trash2 size={14} /></button>
        </td>
      </tr>
      {expandido && (
        <tr>
          <td colSpan={10} style={{ background: "var(--surface-2)", padding: "0.9rem 1.2rem" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.3rem" }}>Itens</div>
                <table className="fazenda-table">
                  <thead><tr><th>Item</th><th>Tipo</th><th style={{ textAlign: "right" }}>Qtd.</th><th style={{ textAlign: "right" }}>Vlr. unit.</th><th style={{ textAlign: "right" }}>Vlr. estimado</th><th style={{ textAlign: "right" }}>Vlr. atendido</th></tr></thead>
                  <tbody>
                    {pedido.itens.map((i) => (
                      <tr key={i.id}>
                        <td style={{ fontSize: "0.8rem" }}>{i.produto_servico}</td>
                        <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{i.tipo_item === "servico" ? "Serviço" : "Produto"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{i.quantidade ?? "—"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{i.valor_unitario_estimado != null ? formatBRL(i.valor_unitario_estimado) : "—"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{formatBRL(i.valor_total_estimado)}</td>
                        <td style={{ textAlign: "right", fontSize: "0.8rem", color: "var(--green-light)" }}>{formatBRL(i.valor_atendido)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {pedido.observacao && <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Obs.: {pedido.observacao}</p>}

              <div className="flex flex-wrap gap-4">
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.3rem", display: "flex", alignItems: "center", gap: "0.3rem" }}><Receipt size={13} /> Lançamentos financeiros vinculados</div>
                  {detalhe && detalhe.lancamentos.length > 0 ? (
                    <ul style={{ fontSize: "0.78rem", paddingLeft: "1.1rem" }}>
                      {detalhe.lancamentos.map((l: any) => <li key={l.id}>{l.numero_lancamento} — {formatBRL(l.valor_total)}</li>)}
                    </ul>
                  ) : <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Nenhum ainda — pedido não reflete em Financeiro.</p>}
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.3rem", display: "flex", alignItems: "center", gap: "0.3rem" }}><Package size={13} /> Movimentos de estoque vinculados</div>
                  {detalhe && detalhe.movimentos_estoque.length > 0 ? (
                    <ul style={{ fontSize: "0.78rem", paddingLeft: "1.1rem" }}>
                      {detalhe.movimentos_estoque.map((m: any) => <li key={m.id}>{m.nome_item} — {m.quantidade} {m.unidade || ""}</li>)}
                    </ul>
                  ) : <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Nenhum ainda — pedido não reflete em Estoque.</p>}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Status manual:</label>
                <select style={inputStyle} value={pedido.status} onChange={(e) => onMudarStatus(e.target.value)}>
                  {Object.entries(STATUS_INFO).map(([id, info]) => <option key={id} value={id}>{info.label}</option>)}
                </select>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function FormPedido({ pedido, opcoes, centros, planoContas, onSalvo, onCancelar }: {
  pedido: PedidoRow | null;
  opcoes: { fornecedores: string[]; clientes: string[]; servicos: string[] };
  centros: string[]; planoContas: ContaPlano[];
  onSalvo: () => void; onCancelar: () => void;
}) {
  const [tipo, setTipo] = useState<"compra" | "venda">(pedido?.tipo ?? "compra");
  const [fornecedorCliente, setFornecedorCliente] = useState(pedido?.fornecedor_cliente ?? "");
  const [centroCusto, setCentroCusto] = useState(pedido?.centro_custo ?? "");
  const [dataPedido, setDataPedido] = useState(pedido?.data_pedido ?? new Date().toISOString().slice(0, 10));
  const [dataPrevista, setDataPrevista] = useState(pedido?.data_prevista ?? "");
  const [observacao, setObservacao] = useState(pedido?.observacao ?? "");
  const [responsavel, setResponsavel] = useState(pedido?.responsavel ?? "");
  const [itens, setItens] = useState<PedidoItemPayload[]>(
    pedido?.itens.map((i) => ({
      tipo_item: i.tipo_item, produto_servico: i.produto_servico, codigo_conta_gerencial: i.codigo_conta_gerencial,
      nome_conta_gerencial: i.nome_conta_gerencial, quantidade: i.quantidade,
      valor_unitario_estimado: i.valor_unitario_estimado, valor_total_estimado: i.valor_total_estimado,
    })) ?? [{ tipo_item: "produto", produto_servico: "", valor_total_estimado: 0 }]
  );
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const opcoesContraparte = tipo === "compra" ? opcoes.fornecedores : opcoes.clientes;
  const tipoConta = tipo === "compra" ? "despesa" : "receita";

  function atualizarItem(idx: number, patch: Partial<PedidoItemPayload>) {
    setItens((prev) => prev.map((it, i) => {
      if (i !== idx) return it;
      const novo = { ...it, ...patch };
      if ((patch.quantidade != null || patch.valor_unitario_estimado != null) && novo.quantidade != null && novo.valor_unitario_estimado != null) {
        novo.valor_total_estimado = Math.round(novo.quantidade * novo.valor_unitario_estimado * 100) / 100;
      }
      return novo;
    }));
  }
  function adicionarItem() { setItens((prev) => [...prev, { tipo_item: "produto", produto_servico: "", valor_total_estimado: 0 }]); }
  function removerItem(idx: number) { setItens((prev) => prev.filter((_, i) => i !== idx)); }

  async function salvar() {
    if (!itens.length || itens.some((i) => !i.produto_servico || !i.valor_total_estimado)) {
      setErro("Informe ao menos um item, com nome e valor estimado."); return;
    }
    setSalvando(true); setErro(null);
    const dados: PedidoPayload = {
      tipo, fornecedor_cliente: fornecedorCliente || null, centro_custo: centroCusto || null,
      data_pedido: dataPedido, data_prevista: dataPrevista || null, observacao: observacao || null,
      responsavel: responsavel || null, itens,
    };
    try {
      if (pedido) await atualizarPedido(pedido.id, dados); else await criarPedido(dados);
      onSalvo();
    } catch (e: any) { setErro(e.message); } finally { setSalvando(false); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div className="flex flex-wrap gap-3">
        <div><label style={labelStyle}>Tipo</label>
          <select style={inputStyle} value={tipo} onChange={(e) => { setTipo(e.target.value as any); setFornecedorCliente(""); }}>
            <option value="compra">Compra</option><option value="venda">Venda</option>
          </select></div>
        <div><label style={labelStyle}>Fornecedor / Cliente</label>
          <select style={{ ...inputStyle, minWidth: "12rem" }} value={fornecedorCliente} onChange={(e) => setFornecedorCliente(e.target.value)}>
            <option value="">— Nenhum —</option>{opcoesContraparte.map((f) => <option key={f} value={f}>{f}</option>)}
          </select></div>
        <div><label style={labelStyle}>Centro de custo</label>
          <select style={inputStyle} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
            <option value="">— Nenhum —</option>{centros.map((c) => <option key={c}>{c}</option>)}
          </select></div>
      </div>
      <div className="flex flex-wrap gap-3">
        <div><label style={labelStyle}>Data do pedido</label><input type="date" style={inputStyle} value={dataPedido} onChange={(e) => setDataPedido(e.target.value)} /></div>
        <div><label style={labelStyle}>Data prevista (opcional)</label><input type="date" style={inputStyle} value={dataPrevista} onChange={(e) => setDataPrevista(e.target.value)} /></div>
        <div><label style={labelStyle}>Responsável (opcional)</label><input style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)} /></div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label style={{ ...labelStyle, margin: 0 }}>Itens</label>
          <button className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem" }} onClick={adicionarItem}><Plus size={12} /> Item</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          {itens.map((item, idx) => (
            <div key={idx} className="card" style={{ padding: "0.6rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <div className="flex flex-wrap gap-2 items-end">
                <div><label style={labelStyle}>Tipo</label>
                  <select style={inputStyle} value={item.tipo_item} onChange={(e) => atualizarItem(idx, { tipo_item: e.target.value as any })}>
                    <option value="produto">Produto</option><option value="servico">Serviço</option>
                  </select></div>
                <div style={{ flex: 1, minWidth: "10rem" }}>
                  <label style={labelStyle}>{item.tipo_item === "servico" ? "Serviço" : "Produto"}</label>
                  {item.tipo_item === "servico" ? (
                    <select style={{ ...inputStyle, width: "100%" }} value={item.produto_servico} onChange={(e) => atualizarItem(idx, { produto_servico: e.target.value })}>
                      <option value="">Selecione…</option>{opcoes.servicos.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  ) : (
                    <input style={{ ...inputStyle, width: "100%" }} value={item.produto_servico} onChange={(e) => atualizarItem(idx, { produto_servico: e.target.value })} placeholder="Nome do produto" />
                  )}
                </div>
                <button title="Remover item" onClick={() => removerItem(idx)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}><Trash2 size={15} /></button>
              </div>
              <div className="flex flex-wrap gap-2 items-end">
                <div><label style={labelStyle}>Quantidade (opcional)</label>
                  <input type="number" step="0.01" style={{ ...inputStyle, width: "7rem" }} value={item.quantidade ?? ""} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value ? Number(e.target.value) : null })} /></div>
                <div><label style={labelStyle}>Vlr. unitário (opcional)</label>
                  <input type="number" step="0.01" style={{ ...inputStyle, width: "8rem" }} value={item.valor_unitario_estimado ?? ""} onChange={(e) => atualizarItem(idx, { valor_unitario_estimado: e.target.value ? Number(e.target.value) : null })} /></div>
                <div><label style={labelStyle}>Vlr. total estimado</label>
                  <input type="number" step="0.01" style={{ ...inputStyle, width: "8rem" }} value={item.valor_total_estimado} onChange={(e) => atualizarItem(idx, { valor_total_estimado: Number(e.target.value) })} /></div>
                <div style={{ flex: 1, minWidth: "12rem" }}><label style={labelStyle}>Conta gerencial (opcional)</label>
                  <SeletorContaGerencial contas={planoContas} tipo={tipoConta} codigo={item.codigo_conta_gerencial || ""} nome={item.nome_conta_gerencial || ""}
                    onSelect={(c, n) => atualizarItem(idx, { codigo_conta_gerencial: c, nome_conta_gerencial: n })} /></div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div><label style={labelStyle}>Observação (opcional)</label><input style={{ ...inputStyle, width: "100%" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

      {erro && <div className="alert-critico"><span>{erro}</span></div>}
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancelar}>Cancelar</button>
        <button className="btn-primary" disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </div>
  );
}
