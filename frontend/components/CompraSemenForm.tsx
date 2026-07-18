"use client";
import { useEffect, useMemo, useState } from "react";
import { Check, Search, Warehouse, Database, FlaskConical, Plus, X } from "lucide-react";
import {
  fetchFornecedores, fetchPlanoContas, fetchOpcoesFinanceiro,
  fetchEstoqueSemen, fetchTouros, criarCompraSemen, fetchComprasSemen,
  formatBRL, ehAdmin, type Touro, type ItemCompraSemen,
} from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";
import type { ContaPlano } from "@/lib/contaGerencial";
import { SeletorContaGerencial } from "./SeletorContaGerencial";
import { ParcelasEditor, CampoQtdParcelas, dividirParcelas, type Parcela } from "./ParcelasEditor";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
const hoje = () => new Date().toISOString().split("T")[0];

const cardBtn = (ativo: boolean): React.CSSProperties => ({
  display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.55rem 0.9rem", borderRadius: "8px",
  border: `1px solid ${ativo ? "var(--dourado)" : "var(--border)"}`,
  background: ativo ? "var(--dourado-transp, rgba(197,160,74,0.12))" : "var(--surface-2)",
  color: ativo ? "var(--dourado-light)" : "var(--text)", cursor: "pointer", fontSize: "0.85rem", fontWeight: ativo ? 700 : 400,
});

function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label style={lbl}>{label}</label>{children}</div>;
}

const PREFIXOS_CONTA_SEMEN = ["3.01.02.01"];

type EstoqueSemenItem = {
  id: number; touro_nome: string; codigo?: string | null; naab?: string | null;
  central?: string | null; tipo: string; doses: number; valor_unitario?: number | null;
  local_armazenamento?: string | null; observacao?: string | null; ativo: boolean;
};
type Fornecedor = { id: number; nome: string; tipo: string; ativo: boolean };
type Registro = {
  id: number; touro_nome: string; naab: string | null; origem: string; doses: number;
  valor_unitario: number; vendedor: string; data_compra: string;
  numero_lancamento_gerado: string | null; usuario_nome?: string | null;
};

// Um item já adicionado ao carrinho da compra (aguardando confirmação final).
type ItemCarrinho = {
  origem: "estoque" | "naab"; estoqueSemenId?: number; naab?: string; touroNome: string; central?: string | null;
  doses: number; valor: number; tipoValor: string;
};

const valorTotalItem = (it: ItemCarrinho) => (it.tipoValor === "total" ? it.valor : it.valor * it.doses);
const valorUnitarioItem = (it: ItemCarrinho) => (it.tipoValor === "total" ? (it.doses ? it.valor / it.doses : 0) : it.valor);

/**
 * Lançamentos > Compra/Venda > Comprar sêmen — permite adicionar UM OU MAIS
 * sêmens/touros à MESMA compra (carrinho de itens), todos vinculados à
 * mesma nota fiscal/parcelamento/pagamento — análogo ao lançamento
 * financeiro com múltiplos produtos, mas aqui cada item vira uma linha de
 * CompraSemen própria (com seu próprio touro, doses e valor/dose), somando
 * ao EstoqueSemen escolhido (ou criando uma linha nova casada por NAAB).
 */
export default function CompraSemenForm() {
  const [origem, setOrigem] = useState<"estoque" | "naab" | null>(null);
  const [estoque, setEstoque] = useState<EstoqueSemenItem[] | null>(null);
  const [naab, setNaab] = useState<Touro[] | null>(null);
  const [erroNaab, setErroNaab] = useState<string | null>(null);
  const [buscaTouro, setBuscaTouro] = useState("");

  const [touroSel, setTouroSel] = useState<{ estoqueSemenId?: number; naab?: string; touroNome: string; central?: string | null } | null>(null);
  const [doses, setDoses] = useState("");
  const [valor, setValor] = useState("");
  const [tipoValor, setTipoValor] = useState("por_dose");

  // Carrinho de itens (touros/sêmens) desta compra — todos ligados à mesma
  // nota fiscal/parcelamento montados uma única vez abaixo.
  const [itens, setItens] = useState<ItemCarrinho[]>([]);
  const [adicionandoItem, setAdicionandoItem] = useState(true);

  const [vendedor, setVendedor] = useState("");
  const [data, setData] = useState(hoje());
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");

  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  const [opcoes, setOpcoes] = useState<{ centros_custo: string[]; contas_bancarias: string[]; tipos_documento: string[] }>({ centros_custo: [], contas_bancarias: [], tipos_documento: [] });
  const [codigoConta, setCodigoConta] = useState("");
  const [nomeConta, setNomeConta] = useState("");
  const [descricao, setDescricao] = useState("");
  const [centroCusto, setCentroCusto] = useState("");
  const [tipoDocumento, setTipoDocumento] = useState("");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [dataEmissao, setDataEmissao] = useState("");
  const [dataVencimento, setDataVencimento] = useState("");
  const [dataPrevista, setDataPrevista] = useState("");
  const [dataPedido, setDataPedido] = useState("");
  const [entregue, setEntregue] = useState(false);
  const [desconto, setDesconto] = useState("");
  const [acrescimo, setAcrescimo] = useState("");

  const [parcelado, setParcelado] = useState(false);
  const [qtdParcelas, setQtdParcelas] = useState("2");
  const [parcelas, setParcelas] = useState<Parcela[]>([]);

  const [jaPago, setJaPago] = useState(false);
  const [dataPagamento, setDataPagamento] = useState("");
  const [valorPago, setValorPago] = useState("");
  const [contaBancaria, setContaBancaria] = useState("");
  const [numeroDocumentoPagamento, setNumeroDocumentoPagamento] = useState("");

  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const fornecedoresLista = useMemo(() => fornecedores.filter((f) => f.tipo !== "cliente" && f.ativo).map((f) => f.nome).sort((a, b) => a.localeCompare(b)), [fornecedores]);

  const [historico, setHistorico] = useState<Registro[] | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);
  const admin = ehAdmin();

  const carregar = () => {
    fetchFornecedores().then(setFornecedores).catch(() => {});
    fetchPlanoContas().then(setPlanoContas).catch(() => {});
    fetchOpcoesFinanceiro().then(setOpcoes).catch(() => {});
    fetchEstoqueSemen().then(setEstoque).catch(() => setEstoque([]));
    fetchComprasSemen().then(setHistorico).catch(() => {});
  };
  useEffect(carregar, []);

  useEffect(() => {
    if (origem === "naab" && naab === null) {
      setErroNaab(null);
      fetchTouros().then(setNaab).catch((e: any) => { setNaab([]); setErroNaab(e.message || "Erro ao carregar o catálogo NAAB"); });
    }
  }, [origem, naab]);

  // Só a conta 3.01.02.01 — Sêmen é permitida; auto-seleciona assim que o
  // plano de contas chega (poupa um clique já que não há outra opção).
  useEffect(() => {
    if (codigoConta || !planoContas.length) return;
    const conta = planoContas.find((c) => c.codigo === "3.01.02.01" && (c.ativa ?? true));
    if (conta) { setCodigoConta(conta.codigo); setNomeConta(conta.nome); }
  }, [planoContas, codigoConta]);

  const dosesNum = Number(doses) || 0;
  const valorNum = Number(valor) || 0;
  const valorUnitarioAtual = tipoValor === "por_dose" ? valorNum : (dosesNum ? valorNum / dosesNum : 0);

  const valorBrutoItens = useMemo(() => Math.round(itens.reduce((acc, it) => acc + valorTotalItem(it), 0) * 100) / 100, [itens]);
  const dosesTotalItens = useMemo(() => itens.reduce((acc, it) => acc + it.doses, 0), [itens]);
  const valorLiquido = Math.round((valorBrutoItens - (Number(desconto) || 0) + (Number(acrescimo) || 0)) * 100) / 100;

  useEffect(() => {
    if (!parcelado) { setParcelas([]); return; }
    const n = Math.max(1, Math.round(Number(qtdParcelas) || 0));
    setParcelas(dividirParcelas(valorLiquido, n, dataPrevista || dataEmissao));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parcelado, qtdParcelas]);

  const escolherOrigem = (o: "estoque" | "naab") => { setOrigem(o); setTouroSel(null); setBuscaTouro(""); };

  const estoqueFiltrado = useMemo(() => {
    const q = buscaTouro.trim().toLowerCase();
    const base = estoque ?? [];
    if (!q) return base;
    return base.filter((e) => `${e.touro_nome} ${e.codigo || ""} ${e.naab || ""} ${e.central || ""}`.toLowerCase().includes(q));
  }, [estoque, buscaTouro]);

  const naabFiltrado = useMemo(() => {
    const q = buscaTouro.trim().toLowerCase();
    const base = naab ?? [];
    if (!q) return base;
    return base.filter((t) => `${t.nome || ""} ${t.naab} ${t.central || ""} ${t.raca || ""}`.toLowerCase().includes(q));
  }, [naab, buscaTouro]);

  const limparSelecaoAtual = () => {
    setOrigem(null); setTouroSel(null); setBuscaTouro(""); setDoses(""); setValor(""); setTipoValor("por_dose");
  };

  const adicionarItem = () => {
    setMsg(null);
    if (!touroSel) { setMsg({ tipo: "erro", texto: "Escolha o touro (estoque ou NAAB)." }); return; }
    if (!dosesNum) { setMsg({ tipo: "erro", texto: "Informe o número de doses." }); return; }
    if (!valorNum) { setMsg({ tipo: "erro", texto: "Informe o valor da compra." }); return; }
    setItens((prev) => [...prev, {
      origem: origem!, estoqueSemenId: touroSel.estoqueSemenId, naab: touroSel.naab,
      touroNome: touroSel.touroNome, central: touroSel.central, doses: dosesNum, valor: valorNum, tipoValor,
    }]);
    limparSelecaoAtual();
    setAdicionandoItem(false);
  };

  const removerItem = (idx: number) => setItens((prev) => prev.filter((_, i) => i !== idx));

  const limpar = () => {
    limparSelecaoAtual();
    setItens([]); setAdicionandoItem(true);
    setVendedor(""); setResponsavel(""); setObservacao("");
    setCodigoConta(""); setNomeConta(""); setDescricao(""); setCentroCusto(""); setTipoDocumento("");
    setNumeroDocumento(""); setDataEmissao(""); setDataVencimento(""); setDataPrevista(""); setDataPedido("");
    setEntregue(false); setDesconto(""); setAcrescimo(""); setParcelado(false); setQtdParcelas("2"); setParcelas([]);
    setJaPago(false); setDataPagamento(""); setValorPago(""); setContaBancaria(""); setNumeroDocumentoPagamento("");
  };

  const salvar = async () => {
    setMsg(null);
    if (!itens.length) { setMsg({ tipo: "erro", texto: "Adicione ao menos um sêmen/touro à compra." }); return; }
    if (!vendedor.trim()) { setMsg({ tipo: "erro", texto: "Informe o vendedor." }); return; }
    if (!codigoConta) { setMsg({ tipo: "erro", texto: "Selecione a conta gerencial." }); return; }

    setSalvando(true);
    try {
      const itensPayload: ItemCompraSemen[] = itens.map((it) => ({
        origem: it.origem, estoque_semen_id: it.estoqueSemenId, naab: it.naab,
        touro_nome: it.touroNome, central: it.central || undefined,
        valor: it.valor, tipo_valor: it.tipoValor, doses: it.doses,
      }));
      const r = await criarCompraSemen({
        itens: itensPayload,
        vendedor: vendedor.trim(), data_compra: data,
        observacao: observacao || undefined, responsavel: responsavel || undefined,
        codigo_conta_gerencial: codigoConta,
        descricao: descricao || undefined, centro_custo: centroCusto || undefined,
        tipo_documento: tipoDocumento || undefined, numero_documento: numeroDocumento || undefined,
        data_emissao: dataEmissao || undefined, data_vencimento: !parcelado ? (dataVencimento || undefined) : undefined,
        data_prevista_entrada: dataPrevista || undefined, data_pedido: dataPedido || undefined, entregue,
        desconto: Number(desconto) || 0, acrescimo: Number(acrescimo) || 0,
        parcelas: parcelado ? parcelas.map((p) => ({ data_vencimento: p.data_vencimento, valor: Number(p.valor) || 0 })) : [],
        data_pagamento: !parcelado && jaPago ? dataPagamento || undefined : undefined,
        valor_pago: !parcelado && jaPago ? Number(valorPago) || 0 : undefined,
        conta_bancaria: !parcelado && jaPago ? contaBancaria || undefined : undefined,
        numero_documento_pagamento: !parcelado && jaPago ? numeroDocumentoPagamento || undefined : undefined,
      });
      const nomes = itens.map((it) => it.touroNome).join(", ");
      setMsg({ tipo: "sucesso", texto: `${(r as any).doses_compradas} dose(s) de sêmen registrada(s) e somada(s) ao estoque de ${nomes}.` });
      limpar();
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao registrar compra de sêmen" });
    } finally {
      setSalvando(false);
    }
  };

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };

  return (
    <div className="animate-in">
      <div className="card mb-4">
        <div className="card-header mb-3">1. Sêmens/touros desta compra</div>

        {!!itens.length && (
          <div className="overflow-x-auto mb-3">
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr>
                <th>Touro</th><th>Origem</th><th style={{ textAlign: "right" }}>Doses</th>
                <th style={{ textAlign: "right" }}>Valor/dose</th><th style={{ textAlign: "right" }}>Valor total</th><th></th>
              </tr></thead>
              <tbody>
                {itens.map((it, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 700 }}>{it.touroNome}{it.naab ? ` (${it.naab})` : ""}</td>
                    <td style={{ fontSize: "0.8rem", textTransform: "capitalize" }}>{it.origem}</td>
                    <td style={{ textAlign: "right" }}>{it.doses}</td>
                    <td style={{ textAlign: "right" }}>{formatBRL(valorUnitarioItem(it))}</td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{formatBRL(valorTotalItem(it))}</td>
                    <td style={{ textAlign: "right" }}>
                      <button type="button" title="Remover" onClick={() => removerItem(idx)}
                        style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}>
                        <X size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
              Total desta compra: <strong style={{ color: "var(--dourado-light)" }}>{dosesTotalItens} dose(s)</strong> por <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(valorBrutoItens)}</strong>
            </p>
          </div>
        )}

        {!adicionandoItem && (
          <button type="button" className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}
            onClick={() => setAdicionandoItem(true)}>
            <Plus size={14} /> Adicionar outro sêmen/touro a esta compra
          </button>
        )}

        {adicionandoItem && (
          <>
            {!!itens.length && (
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                Deseja adicionar mais um sêmen/touro à mesma compra (mesma nota fiscal/boletos)?
              </p>
            )}
            <div className="flex flex-wrap gap-3 mb-3">
              <button type="button" style={cardBtn(origem === "estoque")} onClick={() => escolherOrigem("estoque")}>
                <Warehouse size={16} /> Touro já cadastrado (estoque da fazenda)
              </button>
              <button type="button" style={cardBtn(origem === "naab")} onClick={() => escolherOrigem("naab")}>
                <Database size={16} /> Banco de dados NAAB
              </button>
              {!!itens.length && (
                <button type="button" className="btn-secondary" onClick={() => { limparSelecaoAtual(); setAdicionandoItem(false); }}>
                  Cancelar
                </button>
              )}
            </div>

            {origem && (
              <div className="mb-3" style={{ position: "relative", maxWidth: 340 }}>
                <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
                <input style={{ ...selStyle, paddingLeft: "1.6rem", width: "100%" }} value={buscaTouro} onChange={(e) => setBuscaTouro(e.target.value)}
                  placeholder={origem === "estoque" ? "Buscar touro, código, NAAB…" : "Buscar touro, NAAB, central, raça…"} />
              </div>
            )}

            {origem === "estoque" && (
              <div className="overflow-x-auto">
                {!estoque && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
                {estoque && (
                  <table className="fazenda-table" style={{ margin: 0 }}>
                    <thead><tr><th></th><th>Touro</th><th>Código</th><th>NAAB</th><th>Central</th><th style={{ textAlign: "right" }}>Doses atuais</th></tr></thead>
                    <tbody>
                      {estoqueFiltrado.map((e) => {
                        const sel = touroSel?.estoqueSemenId === e.id;
                        return (
                          <tr key={e.id} style={{ cursor: "pointer" }} className="row-clickable"
                            onClick={() => setTouroSel({ estoqueSemenId: e.id, touroNome: e.touro_nome, central: e.central })}>
                            <td><input type="radio" checked={sel} onChange={() => setTouroSel({ estoqueSemenId: e.id, touroNome: e.touro_nome, central: e.central })} /></td>
                            <td style={{ fontWeight: 700 }}>{e.touro_nome}</td>
                            <td style={{ fontSize: "0.8rem" }}>{e.codigo || "—"}</td>
                            <td style={{ fontSize: "0.8rem" }}>{e.naab || "—"}</td>
                            <td style={{ fontSize: "0.8rem" }}>{e.central || "—"}</td>
                            <td style={{ textAlign: "right", fontWeight: 600 }}>{e.doses}</td>
                          </tr>
                        );
                      })}
                      {!estoqueFiltrado.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)", textAlign: "center", padding: "0.75rem" }}>Nenhum touro em estoque encontrado.</td></tr>}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {origem === "naab" && (
              <div className="overflow-x-auto">
                {erroNaab && <p style={{ color: "var(--red)" }}>Não foi possível carregar o catálogo NAAB: {erroNaab}.</p>}
                {!naab && !erroNaab && <p style={{ color: "var(--text-muted)" }}>Carregando catálogo NAAB…</p>}
                {naab && (
                  <table className="fazenda-table" style={{ margin: 0 }}>
                    <thead><tr><th></th><th>NAAB</th><th>Touro</th><th>Central</th><th>Raça</th><th style={{ textAlign: "right" }}>TPI</th></tr></thead>
                    <tbody>
                      {naabFiltrado.slice(0, 200).map((t) => {
                        const sel = touroSel?.naab === t.naab;
                        return (
                          <tr key={t.id ?? t.naab} style={{ cursor: "pointer" }} className="row-clickable"
                            onClick={() => setTouroSel({ naab: t.naab, touroNome: t.nome || t.naab, central: t.central })}>
                            <td><input type="radio" checked={sel} onChange={() => setTouroSel({ naab: t.naab, touroNome: t.nome || t.naab, central: t.central })} /></td>
                            <td style={{ fontWeight: 700 }}>{t.naab}</td>
                            <td style={{ fontSize: "0.8rem" }}>{t.nome || "—"}</td>
                            <td style={{ fontSize: "0.8rem" }}>{t.central || "—"}</td>
                            <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{t.raca || "—"}</td>
                            <td style={{ textAlign: "right", fontWeight: 600, color: "var(--dourado-light)" }}>{t.tpi ?? "—"}</td>
                          </tr>
                        );
                      })}
                      {!naabFiltrado.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)", textAlign: "center", padding: "0.75rem" }}>Nenhum touro do catálogo NAAB encontrado.</td></tr>}
                    </tbody>
                  </table>
                )}
                {naab && naabFiltrado.length > 200 && (
                  <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Mostrando 200 de {naabFiltrado.length} — refine a busca para ver mais.</p>
                )}
              </div>
            )}

            {touroSel && (
              <div className="mt-3">
                <p style={{ fontSize: "0.8rem", color: "var(--dourado-light)", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <FlaskConical size={14} /> Touro selecionado: <strong>{touroSel.touroNome}</strong>
                  {touroSel.naab && ` (NAAB ${touroSel.naab})`}
                  {!touroSel.estoqueSemenId && " — nova linha de estoque será criada ao salvar"}
                </p>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-2" style={{ maxWidth: "620px" }}>
                  <Campo label="Nº de doses">
                    <input type="number" min={1} style={inputStyle} value={doses} onChange={(e) => setDoses(e.target.value)} />
                  </Campo>
                  <Campo label="O valor informado é...">
                    <div className="flex gap-4 mt-1" style={{ fontSize: "0.82rem" }}>
                      <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
                        <input type="radio" name="tipo_valor_semen" checked={tipoValor === "por_dose"} onChange={() => setTipoValor("por_dose")} />
                        Por dose
                      </label>
                      <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
                        <input type="radio" name="tipo_valor_semen" checked={tipoValor === "total"} onChange={() => setTipoValor("total")} />
                        Total
                      </label>
                    </div>
                  </Campo>
                  <Campo label={tipoValor === "total" ? "Valor total (R$)" : "Valor por dose (R$)"}>
                    <input type="number" step="0.01" style={inputStyle} value={valor} onChange={(e) => setValor(e.target.value)} />
                  </Campo>
                </div>
                {!!dosesNum && !!valorNum && (
                  <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                    Resumo deste item: <strong style={{ color: "var(--text)" }}>{dosesNum}</strong> dose(s) × {formatBRL(valorUnitarioAtual)} =
                    {" "}<strong style={{ color: "var(--dourado-light)" }}>{formatBRL(valorUnitarioAtual * dosesNum)}</strong>
                  </p>
                )}
                <button type="button" className="btn-primary" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={adicionarItem}>
                  <Plus size={14} /> Adicionar sêmen/touro a esta compra
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {!!itens.length && !adicionandoItem && (
        <div className="card mb-4">
          <div className="card-header mb-3">2. Dados da compra</div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
            <Campo label="Vendedor (fornecedor)">
              <select style={inputStyle} value={vendedor} onChange={(e) => setVendedor(e.target.value)}>
                <option value="">Selecione…</option>
                {fornecedoresLista.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
              {!fornecedoresLista.length && <p style={{ fontSize: "0.7rem", color: "var(--amber)", marginTop: "0.2rem" }}>
                Cadastre fornecedores em Configurações → Cadastro → Pessoas/Fornecedores.
              </p>}
            </Campo>
            <Campo label="Data da compra">
              <input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} />
            </Campo>
          </div>

          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
            Total da nota: <strong style={{ color: "var(--text)" }}>{dosesTotalItens}</strong> dose(s) em <strong>{itens.length}</strong> item(ns) =
            {" "}<strong style={{ color: "var(--dourado-light)" }}>{formatBRL(valorLiquido)}</strong>
            {(Number(desconto) > 0 || Number(acrescimo) > 0) && " (já com desconto/acréscimo)"}
          </p>

          <Campo label="Conta gerencial" full>
            <SeletorContaGerencial
              contas={planoContas}
              tipo="despesa"
              prefixosPermitidos={PREFIXOS_CONTA_SEMEN}
              codigo={codigoConta}
              nome={nomeConta}
              onSelect={(codigo, nome) => { setCodigoConta(codigo); setNomeConta(nome); }}
              placeholder="Sêmen (3.01.02.01)…"
            />
          </Campo>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 mb-3">
            <Campo label="Descrição (opcional)"><input style={inputStyle} value={descricao} onChange={(e) => setDescricao(e.target.value)} /></Campo>
            <Campo label="Centro de custo">
              <select style={inputStyle} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
                <option value="">Selecione…</option>
                {opcoes.centros_custo.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Campo>
            <Campo label="Responsável pelo lançamento">
              <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
                <option value="">Selecione...</option>
                {RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
              </select>
            </Campo>
            <Campo label="Tipo de documento">
              <select style={inputStyle} value={tipoDocumento} onChange={(e) => setTipoDocumento(e.target.value)}>
                <option value="">Selecione…</option>
                {(opcoes.tipos_documento.length ? opcoes.tipos_documento : ["Nota fiscal", "Recibo", "Contrato"]).map((t) => <option key={t}>{t}</option>)}
              </select>
            </Campo>
            <Campo label="Número do documento"><input style={inputStyle} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} /></Campo>
            <Campo label="Data de emissão"><input type="date" style={inputStyle} value={dataEmissao} onChange={(e) => setDataEmissao(e.target.value)} /></Campo>
            {!parcelado && (
              <Campo label="Data de vencimento">
                <input type="date" style={inputStyle} value={dataVencimento} onChange={(e) => setDataVencimento(e.target.value)} />
              </Campo>
            )}
            <Campo label="Data prevista de entrada">
              <input type="date" style={inputStyle} value={dataPrevista} onChange={(e) => setDataPrevista(e.target.value)} />
            </Campo>
            <Campo label="Data do pedido"><input type="date" style={inputStyle} value={dataPedido} onChange={(e) => setDataPedido(e.target.value)} /></Campo>
            <Campo label="Já entregue?">
              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", marginTop: "0.4rem" }}>
                <input type="checkbox" checked={entregue} onChange={(e) => setEntregue(e.target.checked)} /> Sim
              </label>
            </Campo>
            <Campo label="Desconto (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={desconto} onChange={(e) => setDesconto(e.target.value)} placeholder="0,00" /></Campo>
            <Campo label="Acréscimo (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={acrescimo} onChange={(e) => setAcrescimo(e.target.value)} placeholder="0,00" /></Campo>
          </div>

          <div className="card mb-3" style={{ background: "var(--surface-2)" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
              <input type="checkbox" checked={parcelado} onChange={(e) => setParcelado(e.target.checked)} /> Lançamento parcelado
            </label>
            {parcelado && (
              <div style={{ marginTop: "0.6rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <CampoQtdParcelas qtd={qtdParcelas} setQtd={setQtdParcelas} />
                <ParcelasEditor parcelas={parcelas} setParcelas={setParcelas} valorReferencia={valorLiquido} tituloContaA="pagar" />
              </div>
            )}
          </div>

          {!parcelado && (
            <div className="card mb-3" style={{ background: "var(--surface-2)" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
                <input type="checkbox" checked={jaPago} onChange={(e) => setJaPago(e.target.checked)} /> Já foi pago
              </label>
              {jaPago && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                  <Campo label="Data de pagamento"><input type="date" style={inputStyle} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></Campo>
                  <Campo label="Valor pago (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={valorPago} onChange={(e) => setValorPago(e.target.value)} /></Campo>
                  <Campo label="Conta bancária">
                    <select style={inputStyle} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
                      <option value="">Selecione…</option>
                      {opcoes.contas_bancarias.map((c) => <option key={c}>{c}</option>)}
                    </select>
                  </Campo>
                  <Campo label="Número do documento de pagamento"><input style={inputStyle} value={numeroDocumentoPagamento} onChange={(e) => setNumeroDocumentoPagamento(e.target.value)} /></Campo>
                </div>
              )}
            </div>
          )}

          <Campo label="Observação (opcional)" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>

          {msg && (
            <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.85rem", margin: "0.75rem 0" }}>{msg.texto}</p>
          )}
          <button className="btn-primary mt-3" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={salvar} disabled={salvando}>
            <Check size={14} /> {salvando ? "Salvando…" : `Registrar compra de ${dosesTotalItens || ""} dose(s)`}
          </button>
        </div>
      )}

      {msg && msg.tipo === "erro" && !(!!itens.length && !adicionandoItem) && (
        <p style={{ color: "var(--red)", fontSize: "0.85rem", margin: "0.75rem 0" }}>{msg.texto}</p>
      )}

      {historico && historico.length > 0 && (
        <div className="card">
          <div className="card-header mb-3">Compras de sêmen registradas</div>
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr>
                <th>Touro</th><th>Origem</th><th>Vendedor</th><th>Data</th>
                <th style={{ textAlign: "right" }}>Doses</th><th style={{ textAlign: "right" }}>Valor/dose</th><th>Lançamento</th>
                {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
              </tr></thead>
              <tbody>
                {historico.map((c) => (
                  <tr key={c.id}>
                    <td style={{ fontWeight: 700 }}>{c.touro_nome}{c.naab ? ` (${c.naab})` : ""}</td>
                    <td style={{ fontSize: "0.8rem", textTransform: "capitalize" }}>{c.origem}</td>
                    <td style={{ fontSize: "0.8rem" }}>{c.vendedor}</td>
                    <td style={{ fontSize: "0.8rem" }}>{c.data_compra}</td>
                    <td style={{ textAlign: "right" }}>{c.doses}</td>
                    <td style={{ textAlign: "right" }}>{formatBRL(c.valor_unitario)}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{c.numero_lancamento_gerado || "—"}</td>
                    {admin && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{c.usuario_nome ?? "—"}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
