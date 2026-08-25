"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { ShoppingCart, Filter, Plus, Pencil, Trash2, ChevronDown, ChevronRight, Receipt, Package, AlertTriangle, Truck, CreditCard, FileText, Upload, X, XCircle, CircleDollarSign, PackageCheck } from "lucide-react";
import {
  fetchPedidos, fetchPedido, criarPedido, atualizarPedido, atualizarStatusPedido, excluirPedido, fetchOpcoesPedidos,
  fetchCentrosCusto, fetchPlanoContas, fetchEstoque, fetchFornecedores, formatBRL, formatDate,
  CATEGORIAS_PEDIDO_ANEXO, anexarArquivoPedido, listarAnexosPedido, excluirAnexoPedido, urlAnexoPedido, type AnexoPedido,
  marcarEntregaItemPedido, type EntregaItemPedidoResultado,
  type PedidoPayload, type PedidoItemPayload,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import NovoItemEstoque from "@/components/NovoItemEstoque";
import NovoFornecedorRapido from "@/components/NovoFornecedorRapido";
import { FormFinanceiro, type PrefillPedido } from "@/components/FormFinanceiro";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import type { ContaPlano } from "@/lib/contaGerencial";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

type PedidoItemRow = PedidoItemPayload & { id: number; valor_atendido: number; quantidade_entregue?: number };
type PedidoRow = {
  id: number; numero_pedido: string; tipo: "compra" | "venda"; fornecedor_cliente: string | null;
  centro_custo: string | null; data_pedido: string; data_prevista: string | null; status: string;
  observacao: string | null; responsavel: string | null; origem_tipo: string | null;
  enviado: boolean | null; codigo_rastreio: string | null; link_rastreio: string | null;
  itens: PedidoItemRow[]; valor_total_estimado: number; valor_atendido: number;
};

const STATUS_INFO: Record<string, { label: string; cor: string }> = {
  aberto: { label: "Aberto", cor: "var(--amber)" },
  parcialmente_atendido: { label: "Parcialmente atendido", cor: "var(--dourado-light)" },
  atendido: { label: "Atendido", cor: "var(--green-light)" },
  cancelado: { label: "Cancelado", cor: "var(--text-muted)" },
};

const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };
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

export default function PedidosPage() {
  const [pedidos, setPedidos] = useState<PedidoRow[] | null>(null);
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
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
    try { await excluirPedido(id); recarregar(); } catch (e: any) { setErro(e.message); }
  }

  async function mudarStatus(id: number, status: string) {
    await atualizarStatusPedido(id, status);
    recarregar();
  }

  const totalEstimado = (pedidos ?? []).reduce((a, p) => a + p.valor_total_estimado, 0);
  const totalAtendido = (pedidos ?? []).reduce((a, p) => a + p.valor_atendido, 0);

  const ord = useOrdenacao(pedidos ?? []);

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

      {/* Valor estimado é o dado de maior peso pra decisão de caixa — vira a
          métrica-âncora em vez de competir em pé de igualdade com Pedidos/
          Valor já atendido/Em aberto, que continuam do lado, menores. */}
      <div className="card mb-4" style={{ padding: "1.1rem 1.3rem" }}>
        <div style={{ fontSize: ".68rem", fontWeight: 700, letterSpacing: ".13em", textTransform: "uppercase", color: "var(--text-muted)" }}>Valor estimado</div>
        <div style={{ fontFamily: "var(--font-heading)", fontSize: "2.6rem", fontWeight: 800, lineHeight: 1, color: "var(--dourado-light)", marginTop: ".25rem", fontVariantNumeric: "tabular-nums" }}>
          {formatBRL(totalEstimado)}
        </div>
        <div style={{ display: "flex", gap: "1.6rem", marginTop: ".9rem", paddingTop: ".8rem", borderTop: "1px solid var(--border)", flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{(pedidos ?? []).length}</div>
            <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Pedidos</div>
          </div>
          <div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--green-light)", fontVariantNumeric: "tabular-nums" }}>{formatBRL(totalAtendido)}</div>
            <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Valor já atendido</div>
          </div>
          <div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--amber)", fontVariantNumeric: "tabular-nums" }}>{(pedidos ?? []).filter((p) => p.status === "aberto").length}</div>
            <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Em aberto</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header mb-3">Pedidos</div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <th></th>
                <ThOrdenavel label="Nº pedido" campo="numero_pedido" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Tipo" campo="tipo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Fornecedor/Cliente" campo="fornecedor_cliente" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Centro custo" campo="centro_custo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Data" campo="data_pedido" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Status" campo="status" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Estimado" campo="valor_total_estimado" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                <ThOrdenavel label="Atendido" campo="valor_atendido" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {ord.linhasOrdenadas.map((p) => (
                <PedidoLinha key={p.id} pedido={p}
                  expandido={expandido === p.id} onToggle={() => setExpandido(expandido === p.id ? null : p.id)}
                  onEditar={() => setEditando(p)} onExcluir={() => excluir(p.id)} onMudarStatus={(s) => mudarStatus(p.id, s)}
                  onAtualizado={recarregar} nomesResponsaveis={nomesResponsaveis} />
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

function PedidoLinha({ pedido, expandido, onToggle, onEditar, onExcluir, onMudarStatus, onAtualizado, nomesResponsaveis }: {
  pedido: PedidoRow; expandido: boolean; onToggle: () => void; onEditar: () => void; onExcluir: () => void; onMudarStatus: (s: string) => void;
  onAtualizado: () => void; nomesResponsaveis: string[];
}) {
  const [detalhe, setDetalhe] = useState<{ lancamentos: any[]; movimentos_estoque: any[] } | null>(null);
  const recarregarDetalhe = () => fetchPedido(pedido.id).then(setDetalhe).catch(() => {});
  useEffect(() => {
    if (expandido && !detalhe) recarregarDetalhe();
  }, [expandido]);

  const [abrirPagamento, setAbrirPagamento] = useState(false);
  // Preenchido só quando o modal de pagamento é aberto AUTOMATICAMENTE por
  // "Marcar entrega" ter voltado `pendencias` não vazias (ver
  // `marcar_entrega_item_pedido` no backend) — dá o destaque visual do que
  // falta, direto no popup, sem o usuário precisar procurar. Abrir pela mão
  // (botão "Lançar pagamento"/ícone $ da linha) não passa por aqui: nesse
  // caso o usuário já sabe o que quer lançar.
  const [pendenciasAbertura, setPendenciasAbertura] = useState<string[]>([]);

  // Cancelamento é a única transição de status que continua manual — todas
  // as outras (parcial/atendido) nascem de "marcar entrega" (ver ação por
  // item, mais abaixo) e nunca mais de um clique direto no badge/select.
  async function cancelar() {
    if (!confirm(`Cancelar o pedido ${pedido.numero_pedido}? Cancelamento é definitivo — depois disso o pedido não aceita mais marcação de entrega.`)) return;
    await onMudarStatus("cancelado");
  }

  async function entregaMarcada(resultado: EntregaItemPedidoResultado) {
    onAtualizado();
    recarregarDetalhe();
    if (resultado.pendencias.length) {
      setPendenciasAbertura(resultado.pendencias);
      setAbrirPagamento(true);
    }
  }

  const prefillPedido: PrefillPedido = {
    id: pedido.id, fornecedorCliente: pedido.fornecedor_cliente,
    itens: pedido.itens.map((i) => ({
      produto: i.produto_servico, tipo_item: i.tipo_item,
      quantidade: i.quantidade, valor_unitario_estimado: i.valor_unitario_estimado,
      valor_total_estimado: i.valor_total_estimado - i.valor_atendido > 0 ? i.valor_total_estimado - i.valor_atendido : i.valor_total_estimado,
      codigo_conta_gerencial: i.codigo_conta_gerencial, nome_conta_gerencial: i.nome_conta_gerencial,
    })),
  };

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
          {pedido.status !== "cancelado" && (
            <button title="Cancelar pedido" onClick={cancelar} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--amber)" }}><XCircle size={14} /></button>
          )}
          <button title="Excluir" onClick={onExcluir} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}><Trash2 size={14} /></button>
          <button title="Lançar em Financeiro" onClick={() => { setPendenciasAbertura([]); setAbrirPagamento(true); }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--green-light)" }}><CircleDollarSign size={14} /></button>
        </td>
      </tr>
      {expandido && (
        <tr>
          <td colSpan={10} style={{ background: "var(--surface-2)", padding: "0.9rem 1.2rem" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.3rem" }}>Itens</div>
                <table className="fazenda-table">
                  <thead><tr><th>Item</th><th>Tipo</th><th style={{ textAlign: "right" }}>Qtd.</th><th style={{ textAlign: "right" }}>Vlr. unit.</th><th style={{ textAlign: "right" }}>Vlr. estimado</th><th style={{ textAlign: "right" }}>Vlr. atendido</th><th style={{ textAlign: "right" }}>Entrega</th></tr></thead>
                  <tbody>
                    {pedido.itens.map((i) => (
                      <tr key={i.id}>
                        <td style={{ fontSize: "0.8rem" }}>{i.produto_servico}</td>
                        <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{i.tipo_item === "servico" ? "Serviço" : "Produto"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{i.quantidade ?? "—"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{i.valor_unitario_estimado != null ? formatBRL(i.valor_unitario_estimado) : "—"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{formatBRL(i.valor_total_estimado)}</td>
                        <td style={{ textAlign: "right", fontSize: "0.8rem", color: "var(--green-light)" }}>{formatBRL(i.valor_atendido)}</td>
                        <td style={{ textAlign: "right" }}>
                          <MarcarEntregaItem pedidoId={pedido.id} item={i} desabilitado={pedido.status === "cancelado"} onEntregaMarcada={entregaMarcada} />
                        </td>
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

              <div className="card" style={{ padding: "0.75rem", display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.75rem", background: "var(--surface)" }}>
                {/* Status deixou de ser escolhido aqui — é consequência de
                    "Marcar entrega" em cada item, acima (ou do ✕ Cancelar
                    pedido, na linha). "Enviado"/rastreio é só exibição do
                    que já foi preenchido antes desta mudança (dado legado,
                    ver PUT /pedidos/{id}/rastreio). */}
                {pedido.enviado && (
                  <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                    <Truck size={13} /> Enviado
                    {pedido.codigo_rastreio && <span>— {pedido.codigo_rastreio}</span>}
                    {pedido.link_rastreio && <a href={pedido.link_rastreio} target="_blank" rel="noreferrer" style={{ color: "var(--dourado-light)" }}>rastrear</a>}
                  </div>
                )}
                <button className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.78rem", marginLeft: "auto" }}
                  onClick={() => { setPendenciasAbertura([]); setAbrirPagamento(true); }}>
                  <CreditCard size={14} /> Lançar pagamento
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}

      {abrirPagamento && (
        <tr><td colSpan={10} style={{ padding: 0 }}>
          <Modal title="Lançar pagamento do pedido" onClose={() => { setAbrirPagamento(false); setPendenciasAbertura([]); }} width="1100px" zIndex={90}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {pendenciasAbertura.length > 0 && (
                <div style={{
                  display: "flex", gap: "0.5rem", alignItems: "flex-start", fontSize: "0.82rem",
                  border: "1px dashed var(--red)", background: "rgba(190,40,40,0.08)", borderRadius: "var(--r-sm)", padding: "0.65rem 0.8rem",
                }}>
                  <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: "0.1rem", color: "var(--red)" }} />
                  <span>
                    Entrega marcada — mas falta{pendenciasAbertura.length > 1 ? "m" : ""} <b>{pendenciasAbertura.map((p) => LABEL_PENDENCIA[p] || p).join(" e ")}</b> para o pedido estar fechado de verdade. Complete abaixo.
                  </span>
                </div>
              )}
              <FormFinanceiro
                tipo={pedido.tipo === "compra" ? "despesa" : "receita"}
                responsaveis={nomesResponsaveis}
                prefillPedido={prefillPedido}
                onSalvo={() => { setAbrirPagamento(false); setPendenciasAbertura([]); onAtualizado(); }}
              />
            </div>
          </Modal>
        </td></tr>
      )}
    </>
  );
}

// Rótulo em português de cada pendência devolvida por PUT
// /pedidos/{id}/itens/{item_id}/entrega — ver `_pendencias_fechamento_pedido`
// no backend (pedidos.py).
const LABEL_PENDENCIA: Record<string, string> = {
  pagamento: "o pagamento (nenhum lançamento vinculado ainda)",
  data_emissao: "a data de emissão da nota/documento",
};

// Ação "Marcar entrega" de um item do pedido (painel expandido) — chama
// PUT /pedidos/{pedido_id}/itens/{item_id}/entrega com o valor ABSOLUTO novo
// de quantidade_entregue (substitui, não soma). Item estocável com aumento
// já dá entrada automática em Estoque no backend (Decisão A1); aqui só
// mostra o resultado (avisos) e repassa pro pai decidir se abre o formulário
// de conclusão (`onEntregaMarcada`, ver `pendencias`).
function MarcarEntregaItem({ pedidoId, item, desabilitado, onEntregaMarcada }: {
  pedidoId: number; item: PedidoItemRow; desabilitado: boolean; onEntregaMarcada: (r: EntregaItemPedidoResultado) => void;
}) {
  const [valor, setValor] = useState(String(item.quantidade_entregue ?? 0));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { setValor(String(item.quantidade_entregue ?? 0)); }, [item.quantidade_entregue]);

  async function confirmar() {
    const quantidade = Number(valor);
    if (Number.isNaN(quantidade) || quantidade < 0) { setErro("Quantidade inválida"); return; }
    setSalvando(true); setErro(null);
    try {
      const resultado = await marcarEntregaItemPedido(pedidoId, item.id, quantidade);
      onEntregaMarcada(resultado);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.15rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
        <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
          {item.quantidade_entregue ?? 0}{item.quantidade != null ? ` / ${item.quantidade}` : ""} entregue{(item.quantidade_entregue ?? 0) === 1 ? "" : "s"}
        </span>
        <input
          type="number" step="0.01" min={0} disabled={desabilitado || salvando}
          style={{ ...inputStyle, width: "5rem", padding: "0.2rem 0.4rem", fontSize: "0.76rem" }}
          value={valor} onChange={(e) => setValor(e.target.value)}
          title="Quantidade entregue"
        />
        <button
          type="button" title="Marcar entrega" disabled={desabilitado || salvando}
          onClick={confirmar}
          style={{ background: "none", border: "none", cursor: desabilitado ? "not-allowed" : "pointer", color: desabilitado ? "var(--text-muted)" : "var(--green-light)", opacity: desabilitado ? 0.5 : 1 }}
        >
          <PackageCheck size={16} />
        </button>
      </div>
      {erro && <span style={{ fontSize: "0.68rem", color: "var(--red)" }}>{erro}</span>}
    </div>
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
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [itens, setItens] = useState<PedidoItemPayload[]>(
    pedido?.itens.map((i) => ({
      tipo_item: i.tipo_item, produto_servico: i.produto_servico, codigo_conta_gerencial: i.codigo_conta_gerencial,
      nome_conta_gerencial: i.nome_conta_gerencial, quantidade: i.quantidade,
      valor_unitario_estimado: i.valor_unitario_estimado, valor_total_estimado: i.valor_total_estimado,
    })) ?? [{ tipo_item: "produto", produto_servico: "", valor_total_estimado: 0 }]
  );
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Produtos do estoque (pra não deixar o campo "produto" em texto livre —
  // mesmo picker + "cadastrar novo" que Financeiro já usa) e fornecedores/
  // clientes recém-cadastrados (a lista `opcoes` só é buscada uma vez lá em
  // cima em PedidosPage; sem isto, cadastrar um fornecedor novo aqui dentro
  // não aparecia no seletor até recarregar a página inteira).
  const [produtosEstoque, setProdutosEstoque] = useState<EstoqueItemPicker[]>([]);
  const carregarEstoque = () => fetchEstoque().then((d: any) => setProdutosEstoque((d.itens || []).map((i: any) => ({
    nome: i.nome, categoria: i.categoria ?? null, quantidade: i.quantidade ?? null, unidade: i.unidade ?? null,
    estocavel: i.estocavel ?? null, finalidade: i.finalidade ?? null,
  })))).catch(() => {});
  useEffect(() => { carregarEstoque(); }, []);
  const [fornecedoresCadastro, setFornecedoresCadastro] = useState<{ nome: string; tipo: string }[]>([]);
  const carregarFornecedores = () => fetchFornecedores().then((d: any[]) => setFornecedoresCadastro((d || []).map((f) => ({ nome: f.nome, tipo: f.tipo })))).catch(() => {});
  useEffect(() => { carregarFornecedores(); }, []);
  const [abrirNovoProduto, setAbrirNovoProduto] = useState<number | null>(null);
  const [abrirNovoFornecedor, setAbrirNovoFornecedor] = useState(false);

  // Anexos (orçamento/OS/outro documento) — se tem validade, a Agenda avisa
  // 2 dias antes do vencimento enquanto o pedido seguir aberto/parcialmente
  // atendido. Igual ao bloco de anexo do FormFinanceiro: arquivo novo fica
  // "staged" e só sobe de fato depois que o pedido é salvo (precisa do id).
  type AnexoStagedPedido = { file: File; categoria: string; data_validade: string };
  const [anexosStaged, setAnexosStaged] = useState<AnexoStagedPedido[]>([]);
  const [anexosExistentes, setAnexosExistentes] = useState<AnexoPedido[]>([]);
  const [categoriaAnexoPadrao, setCategoriaAnexoPadrao] = useState(CATEGORIAS_PEDIDO_ANEXO[0]);
  const anexoInputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (pedido) listarAnexosPedido(pedido.id).then(setAnexosExistentes).catch(() => {});
  }, [pedido?.id]);
  function adicionarAnexosStaged(files: File[]) {
    if (!files.length) return;
    setAnexosStaged((arr) => [...arr, ...files.map((file) => ({ file, categoria: categoriaAnexoPadrao, data_validade: "" }))]);
  }
  async function excluirAnexoExistente(id: number) {
    if (!confirm("Excluir este anexo do pedido?")) return;
    try { await excluirAnexoPedido(id); setAnexosExistentes((arr) => arr.filter((a) => a.id !== id)); } catch (e: any) { setErro(e.message); }
  }

  const opcoesContraparte = useMemo(() => {
    const doProp = tipo === "compra" ? opcoes.fornecedores : opcoes.clientes;
    const tiposAlvo = tipo === "compra" ? ["fornecedor", "fabricante"] : ["cliente"];
    const doCadastro = fornecedoresCadastro.filter((f) => tiposAlvo.includes(f.tipo)).map((f) => f.nome);
    return Array.from(new Set([...doProp, ...doCadastro])).sort();
  }, [tipo, opcoes, fornecedoresCadastro]);
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
      let id: number;
      if (pedido) { await atualizarPedido(pedido.id, dados); id = pedido.id; }
      else { id = (await criarPedido(dados)).id; }
      if (anexosStaged.length) {
        await Promise.all(anexosStaged.map((a) => anexarArquivoPedido(id, a.file, a.categoria, a.data_validade || undefined)));
      }
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
          <div className="flex items-center gap-2">
            <select style={{ ...inputStyle, minWidth: "12rem" }} value={fornecedorCliente} onChange={(e) => setFornecedorCliente(e.target.value)}>
              <option value="">— Nenhum —</option>{opcoesContraparte.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <button type="button" className="btn-ghost" title={`Cadastrar novo ${tipo === "compra" ? "fornecedor" : "cliente"}`} style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoFornecedor(true)}>
              <Plus size={13} /> Novo
            </button>
          </div>
        </div>
        <div><label style={labelStyle}>Centro de custo</label>
          <select style={inputStyle} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
            <option value="">— Nenhum —</option>{centros.map((c) => <option key={c}>{c}</option>)}
          </select></div>
      </div>
      <div className="flex flex-wrap gap-3">
        <div><label style={labelStyle}>Data do pedido</label><input type="date" style={inputStyle} value={dataPedido} onChange={(e) => setDataPedido(e.target.value)} /></div>
        <div><label style={labelStyle}>Data prevista (opcional)</label><input type="date" style={inputStyle} value={dataPrevista} onChange={(e) => setDataPrevista(e.target.value)} /></div>
        <div><label style={labelStyle}>Responsável (opcional)</label>
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
            <option value="">Opcional</option>
            {responsavel && !nomesResponsaveis.includes(responsavel) && <option value={responsavel}>{responsavel}</option>}
            {nomesResponsaveis.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
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
                    <div className="flex items-center gap-2">
                      <div style={{ flex: 1 }}>
                        <EstoquePicker itens={produtosEstoque} value={item.produto_servico} todasFinalidades incluirNaoEstocaveis
                          placeholder="Selecionar produto…"
                          onChange={(nome) => atualizarItem(idx, { produto_servico: nome })} />
                      </div>
                      <button type="button" className="btn-ghost" title="Cadastrar novo produto" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoProduto(idx)}>
                        <Plus size={13} /> Novo
                      </button>
                    </div>
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

      <div>
        <label style={{ ...labelStyle, margin: "0 0 0.3rem" }}>Anexos (orçamento, ordem de serviço ou outro documento)</label>
        {anexosExistentes.length > 0 && (
          <ul style={{ marginBottom: "0.5rem", fontSize: "0.78rem", listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            {anexosExistentes.map((a) => (
              <li key={a.id} className="card" style={{ padding: "0.4rem 0.6rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <FileText size={13} style={{ flexShrink: 0, color: "var(--dourado-light)" }} />
                <a href={urlAnexoPedido(a.id)} target="_blank" rel="noreferrer" style={{ color: "var(--dourado-light)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {a.nome_arquivo}
                </a>
                <span style={{ color: "var(--text-muted)", flexShrink: 0 }}>{a.categoria}</span>
                {a.data_validade && <span style={{ color: "var(--amber)", flexShrink: 0 }}>válido até {formatDate(a.data_validade)}</span>}
                <button type="button" className="btn-ghost" title="Excluir anexo" onClick={() => excluirAnexoExistente(a.id)} style={{ padding: "0.1rem 0.3rem", flexShrink: 0 }}>
                  <X size={12} style={{ color: "var(--red)" }} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <div
          onDrop={(e) => { e.preventDefault(); adicionarAnexosStaged(Array.from(e.dataTransfer.files || [])); }}
          onDragOver={(e) => e.preventDefault()}
          className="card"
          style={{ border: "1px dashed var(--border)", background: "var(--surface-2)", padding: "0.7rem", textAlign: "center" }}
        >
          <div className="flex items-center justify-center gap-2" style={{ flexWrap: "wrap" }}>
            <FileText size={15} style={{ color: "var(--dourado-light)" }} />
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Arraste orçamento/OS/documento aqui, ou</span>
            <select style={{ ...inputStyle, fontSize: "0.76rem" }} value={categoriaAnexoPadrao} onChange={(e) => setCategoriaAnexoPadrao(e.target.value)}>
              {CATEGORIAS_PEDIDO_ANEXO.map((c) => <option key={c}>{c}</option>)}
            </select>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={() => anexoInputRef.current?.click()}>
              <Upload size={12} /> selecionar arquivo(s)
            </button>
          </div>
          <input ref={anexoInputRef} type="file" multiple accept="application/pdf,image/jpeg,image/png"
            onChange={(e) => { adicionarAnexosStaged(Array.from(e.target.files || [])); e.target.value = ""; }}
            style={{ display: "none" }} />
          {anexosStaged.length > 0 && (
            <ul style={{ marginTop: "0.5rem", textAlign: "left", fontSize: "0.76rem", listStyle: "none", padding: 0 }}>
              {anexosStaged.map((a, i) => (
                <li key={i} className="card" style={{ padding: "0.4rem 0.5rem", marginBottom: "0.35rem", background: "var(--surface)" }}>
                  <div className="flex items-center justify-between" style={{ gap: "0.4rem" }}>
                    <a href={URL.createObjectURL(a.file)} target="_blank" rel="noreferrer" style={{ color: "var(--dourado-light)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {a.file.name}
                    </a>
                    <button type="button" className="btn-ghost" title="Remover" onClick={() => setAnexosStaged((arr) => arr.filter((_, j) => j !== i))} style={{ padding: "0.1rem 0.3rem", flexShrink: 0 }}>
                      <X size={12} style={{ color: "var(--red)" }} />
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2" style={{ marginTop: "0.3rem" }}>
                    <select style={{ ...inputStyle, fontSize: "0.74rem", padding: "0.25rem 0.4rem" }} value={a.categoria} title="Tipo deste documento"
                      onChange={(e) => setAnexosStaged((arr) => arr.map((x, j) => j === i ? { ...x, categoria: e.target.value } : x))}>
                      {CATEGORIAS_PEDIDO_ANEXO.map((c) => <option key={c}>{c}</option>)}
                    </select>
                    <input type="date" style={{ ...inputStyle, fontSize: "0.74rem", padding: "0.25rem 0.4rem" }} title="Data de validade (orçamento/OS) — opcional"
                      value={a.data_validade} onChange={(e) => setAnexosStaged((arr) => arr.map((x, j) => j === i ? { ...x, data_validade: e.target.value } : x))} />
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
            Data de validade opcional — se preenchida, a Agenda avisa 2 dias antes do vencimento enquanto o pedido seguir aberto/parcialmente atendido.
          </p>
        </div>
      </div>

      {erro && <div className="alert-critico"><span>{erro}</span></div>}
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancelar}>Cancelar</button>
        <button className="btn-primary" disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>

      {abrirNovoProduto !== null && (
        <Modal title="Novo produto (estoque)" onClose={() => setAbrirNovoProduto(null)} width="900px" zIndex={95}>
          <NovoItemEstoque
            onCriado={(item) => {
              if (item?.nome && abrirNovoProduto !== null) atualizarItem(abrirNovoProduto, { produto_servico: item.nome });
              carregarEstoque();
              setAbrirNovoProduto(null);
            }}
            onCancelar={() => setAbrirNovoProduto(null)}
          />
        </Modal>
      )}
      {abrirNovoFornecedor && (
        <Modal title={`Novo ${tipo === "compra" ? "fornecedor" : "cliente"}`} onClose={() => setAbrirNovoFornecedor(false)} width="480px" zIndex={95}>
          <NovoFornecedorRapido
            tipoSugerido={tipo === "compra" ? "despesa" : "receita"}
            onCriado={(f) => {
              if (f?.nome) setFornecedorCliente(f.nome);
              carregarFornecedores();
              setAbrirNovoFornecedor(false);
            }}
            onCancelar={() => setAbrirNovoFornecedor(false)}
          />
        </Modal>
      )}
    </div>
  );
}
