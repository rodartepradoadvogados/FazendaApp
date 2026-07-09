"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Upload, FileText, X, Check, AlertTriangle, Loader2, Plus, Trash2 } from "lucide-react";
import {
  fetchOpcoesFinanceiro, fetchEstoque, fetchServicosCadastro, fetchFornecedores, criarLancamentoFinanceiro, importarXmlFinanceiro, formatBRL,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import NovoItemEstoque from "@/components/NovoItemEstoque";
import NovaContaGerencial from "@/components/NovaContaGerencial";
import NovoServicoRapido from "@/components/NovoServicoRapido";
import NovoFornecedorRapido from "@/components/NovoFornecedorRapido";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label style={lbl}>{label}</label>{children}</div>;
}

type Parcela = { data_vencimento: string; valor: string };
type TipoItem = "produto" | "servico";
type Item = {
  codigo_conta_gerencial: string; nome_conta_gerencial: string;
  tipo_item: TipoItem; produto: string; descricao: string;
  quantidade: string; valor_unitario: string; valor_total: string; valorTotalManual: boolean;
};
const itemVazio = (): Item => ({
  codigo_conta_gerencial: "", nome_conta_gerencial: "", tipo_item: "produto", produto: "", descricao: "",
  quantidade: "", valor_unitario: "", valor_total: "", valorTotalManual: false,
});

type Opcoes = {
  contas_gerenciais: { codigo: string; nome: string }[];
  centros_custo: string[];
  fornecedores: string[];
  produtos: string[];
  contas_bancarias: string[];
  tipos_documento: string[];
};

const OPCOES_VAZIAS: Opcoes = { contas_gerenciais: [], centros_custo: [], fornecedores: [], produtos: [], contas_bancarias: [], tipos_documento: [] };

function dividirParcelas(valorTotal: number, qtd: number, primeiraData: string): Parcela[] {
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
 * Lançamento financeiro completo: vários produtos/serviços por nota, desconto
 * e/ou acréscimo sobre o total, parcelamento, conta bancária, documento e
 * importação de XML (reconhece múltiplos itens e as parcelas da NF-e).
 */
export function FormFinanceiro({ tipo, responsaveis, onSujo }: { tipo: "despesa" | "receita"; responsaveis: string[]; onSujo?: (sujo: boolean) => void }) {
  const [opcoes, setOpcoes] = useState<Opcoes>(OPCOES_VAZIAS);
  const carregarOpcoes = () => fetchOpcoesFinanceiro().then(setOpcoes).catch(() => {});
  useEffect(() => { carregarOpcoes(); }, []);

  const [produtosEstoque, setProdutosEstoque] = useState<{ nome: string; fornecedor_nome: string | null }[]>([]);
  const carregarEstoque = () => fetchEstoque().then((d) => setProdutosEstoque((d.itens || []).map((i: any) => ({ nome: i.nome, fornecedor_nome: i.fornecedor_nome ?? null })))).catch(() => {});
  useEffect(() => { carregarEstoque(); }, []);
  const [fornecedoresCadastro, setFornecedoresCadastro] = useState<string[]>([]);
  useEffect(() => { fetchFornecedores().then((d) => setFornecedoresCadastro((d || []).map((f: any) => f.nome))).catch(() => {}); }, []);
  const fornecedoresDisponiveis = useMemo(
    () => Array.from(new Set([...opcoes.fornecedores, ...fornecedoresCadastro])).sort(),
    [opcoes.fornecedores, fornecedoresCadastro]
  );
  const [servicos, setServicos] = useState<{ id: number; nome: string; ativo: boolean }[]>([]);
  const carregarServicos = () => fetchServicosCadastro().then(setServicos).catch(() => {});
  useEffect(() => { carregarServicos(); }, []);
  const sugestoesServico = useMemo(() => servicos.filter((s) => s.ativo).map((s) => s.nome).sort(), [servicos]);

  // Modal "+ Adicionar" (novo produto de estoque, novo serviço ou nova conta
  // gerencial), aberto a partir de um item específico da nota — o item fica
  // marcado em `adicionarPara` para saber onde aplicar o resultado ao salvar.
  const [adicionarPara, setAdicionarPara] = useState<number | null>(null);
  const [modoAdicionar, setModoAdicionar] = useState<"produto" | "servico" | "conta">("produto");
  const [abrirNovoFornecedor, setAbrirNovoFornecedor] = useState(false);

  const [itens, setItens] = useState<Item[]>([itemVazio()]);
  const [centroCusto, setCentroCusto] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [tipoDocumento, setTipoDocumento] = useState("");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [dataEmissao, setDataEmissao] = useState("");
  const [dataPrevistaEntrada, setDataPrevistaEntrada] = useState("");
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

  const [xmlAberto, setXmlAberto] = useState(false);
  const [xmlTexto, setXmlTexto] = useState("");
  const [importando, setImportando] = useState(false);
  const [erroXml, setErroXml] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [confirmando, setConfirmando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const contasFiltradas = useMemo(
    () => opcoes.contas_gerenciais.filter((c) => c.codigo.startsWith(tipo === "receita" ? "2" : "3")),
    [opcoes, tipo]
  );

  function atualizarItem(idx: number, patch: Partial<Item>) {
    setItens((arr) => arr.map((it, i) => {
      if (i !== idx) return it;
      const novo = { ...it, ...patch };
      const q = Number(novo.quantidade), v = Number(novo.valor_unitario);
      if (novo.quantidade && novo.valor_unitario && !novo.valorTotalManual && !("valor_total" in patch)) {
        novo.valor_total = (q * v).toFixed(2);
      }
      return novo;
    }));
  }
  function escolherContaGerencial(idx: number, valor: string) {
    const match = contasFiltradas.find((c) => `${c.codigo} — ${c.nome}` === valor);
    atualizarItem(idx, match ? { codigo_conta_gerencial: match.codigo, nome_conta_gerencial: match.nome } : { codigo_conta_gerencial: "", nome_conta_gerencial: valor });
  }
  function acrescentarItem() { setItens((arr) => [...arr, itemVazio()]); }
  function removerItem(idx: number) { setItens((arr) => (arr.length > 1 ? arr.filter((_, i) => i !== idx) : arr)); }

  const valorBruto = useMemo(() => itens.reduce((a, i) => a + (Number(i.valor_total) || 0), 0), [itens]);
  const valorLiquido = useMemo(() => Math.round((valorBruto - (Number(desconto) || 0) + (Number(acrescimo) || 0)) * 100) / 100, [valorBruto, desconto, acrescimo]);

  // Regenera as parcelas (divisão igual) quando ligar o parcelamento ou mudar quantidade.
  useEffect(() => {
    if (!parcelado) { setParcelas([]); return; }
    const n = Math.max(1, Math.round(Number(qtdParcelas) || 0));
    setParcelas(dividirParcelas(valorLiquido, n, dataPrevistaEntrada || dataEmissao));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parcelado, qtdParcelas]);

  const somaParcelas = useMemo(() => parcelas.reduce((a, p) => a + (Number(p.valor) || 0), 0), [parcelas]);
  const diferencaPagamento = useMemo(() => (valorPago ? Math.round((Number(valorPago) - valorLiquido) * 100) / 100 : 0), [valorPago, valorLiquido]);

  function limpar() {
    setItens([itemVazio()]);
    setCentroCusto(""); setFornecedor(""); setResponsavel(""); setTipoDocumento("");
    setNumeroDocumento(""); setDataEmissao(""); setDataPrevistaEntrada(""); setDataPedido(""); setEntregue(false);
    setDesconto(""); setAcrescimo("");
    setParcelado(false); setQtdParcelas("2"); setParcelas([]);
    setJaPago(false); setDataPagamento(""); setValorPago(""); setContaBancaria(""); setNumeroDocumentoPagamento("");
    setXmlTexto(""); setXmlAberto(false);
  }

  function aplicarXml(dados: any) {
    if (dados.numero_documento) setNumeroDocumento(dados.numero_documento);
    if (dados.data_emissao) setDataEmissao(dados.data_emissao);
    if (dados.fornecedor_cliente) setFornecedor(dados.fornecedor_cliente);
    setTipoDocumento("Nota fiscal");
    if (Array.isArray(dados.itens) && dados.itens.length) {
      setItens(dados.itens.map((it: any) => ({
        codigo_conta_gerencial: "", nome_conta_gerencial: "", tipo_item: "produto",
        produto: it.produto || "", descricao: "",
        quantidade: it.quantidade != null ? String(it.quantidade) : "",
        valor_unitario: it.valor_unitario != null ? String(it.valor_unitario) : "",
        valor_total: it.valor_total != null ? String(it.valor_total) : "",
        valorTotalManual: it.valor_total != null,
      })));
    } else if (dados.valor_total != null) {
      setItens([{ ...itemVazio(), produto: "Importado do XML", valor_total: String(dados.valor_total), valorTotalManual: true }]);
    }
    if (Array.isArray(dados.parcelas) && dados.parcelas.length) {
      setParcelado(true);
      setQtdParcelas(String(dados.parcelas.length));
      setParcelas(dados.parcelas.map((p: any) => ({ data_vencimento: p.data_vencimento || "", valor: p.valor != null ? String(p.valor) : "" })));
    }
  }

  async function importarXml(texto: string) {
    if (!texto.trim()) return;
    setImportando(true); setErroXml(null);
    try {
      const dados = await importarXmlFinanceiro(texto);
      aplicarXml(dados);
      setXmlAberto(false);
    } catch (e: any) {
      setErroXml(e.message || "Erro ao ler o XML");
    } finally {
      setImportando(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) file.text().then(importarXml);
  }
  function onFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) file.text().then(importarXml);
  }

  function montarPayload() {
    return {
      tipo,
      itens: itens
        .filter((i) => i.produto.trim())
        .map((i) => ({
          codigo_conta_gerencial: i.codigo_conta_gerencial || null,
          nome_conta_gerencial: i.nome_conta_gerencial || null,
          produto: i.produto.trim(),
          tipo_item: i.tipo_item,
          descricao: i.descricao || null,
          quantidade: i.quantidade ? Number(i.quantidade) : null,
          valor_unitario: i.valor_unitario ? Number(i.valor_unitario) : null,
          valor_total: Number(i.valor_total) || 0,
        })),
      centro_custo: centroCusto || null,
      fornecedor_cliente: fornecedor || null,
      responsavel: responsavel || null,
      tipo_documento: tipoDocumento || null,
      numero_documento: numeroDocumento || null,
      data_emissao: dataEmissao || null,
      data_prevista_entrada: dataPrevistaEntrada || null,
      data_pedido: dataPedido || null,
      entregue,
      desconto: Number(desconto) || 0,
      acrescimo: Number(acrescimo) || 0,
      parcelas: parcelado ? parcelas.map((p) => ({ data_vencimento: p.data_vencimento, valor: Number(p.valor) || 0 })) : [],
      data_pagamento: !parcelado && jaPago ? dataPagamento || null : null,
      valor_pago: !parcelado && jaPago ? Number(valorPago) || 0 : null,
      conta_bancaria: !parcelado && jaPago ? contaBancaria || null : null,
      numero_documento_pagamento: !parcelado && jaPago ? numeroDocumentoPagamento || null : null,
    };
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    const validos = itens.filter((i) => i.produto.trim());
    if (!validos.length) { setErro("Informe ao menos um produto ou serviço."); return; }
    if (valorLiquido <= 0) { setErro("O valor líquido do lançamento deve ser positivo."); return; }
    if (!parcelado && jaPago && diferencaPagamento !== 0 && !confirmando) { setConfirmando(true); return; }
    setSalvando(true);
    try {
      const r = await criarLancamentoFinanceiro(montarPayload());
      setSucesso(`Lançamento ${r.numero_lancamento} salvo com sucesso.`);
      limpar();
      onSujo?.(false);
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar lançamento");
    } finally {
      setSalvando(false); setConfirmando(false);
    }
  }

  return (
    <>
      {/* Importação de XML de nota */}
      <div
        onDrop={onDrop} onDragOver={(e) => e.preventDefault()}
        className="card mb-3"
        style={{ border: "1px dashed var(--border)", background: "var(--surface-2)", padding: "0.8rem", textAlign: "center" }}
      >
        <div className="flex items-center justify-center gap-2" style={{ flexWrap: "wrap" }}>
          <FileText size={16} style={{ color: "var(--dourado-light)" }} />
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Arraste o XML da nota aqui, ou</span>
          <button type="button" className="btn-ghost" onClick={() => fileInputRef.current?.click()} style={{ fontSize: "0.78rem" }}>
            <Upload size={13} /> selecionar arquivo
          </button>
          <button type="button" className="btn-ghost" onClick={() => setXmlAberto((v) => !v)} style={{ fontSize: "0.78rem" }}>colar código XML</button>
          {importando && <Loader2 size={14} className="animate-spin" style={{ color: "var(--dourado-light)" }} />}
        </div>
        <input ref={fileInputRef} type="file" accept=".xml,text/xml" onChange={onFileSelect} style={{ display: "none" }} />
        {xmlAberto && (
          <div style={{ marginTop: "0.6rem", textAlign: "left" }}>
            <textarea value={xmlTexto} onChange={(e) => setXmlTexto(e.target.value)} placeholder="Cole aqui o conteúdo do XML da nota fiscal…"
              style={{ ...inputStyle, minHeight: "6rem", fontFamily: "monospace", fontSize: "0.72rem" }} />
            <button type="button" className="btn-primary" style={{ marginTop: "0.4rem" }} onClick={() => importarXml(xmlTexto)} disabled={importando}>Importar XML</button>
          </div>
        )}
        {erroXml && <p style={{ color: "var(--red)", fontSize: "0.75rem", marginTop: "0.4rem" }}>{erroXml}</p>}
        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>Reconhece vários produtos/serviços da mesma nota — os campos ficam abaixo, todos editáveis.</p>
      </div>

      {/* Produtos / serviços da nota */}
      <div className="mt-3 space-y-3">
        {itens.map((it, idx) => (
          <div key={idx} className="card" style={{ background: "var(--surface-2)", position: "relative" }}>
            {itens.length > 1 && (
              <button type="button" onClick={() => removerItem(idx)} className="btn-ghost" style={{ position: "absolute", top: "0.5rem", right: "0.5rem", fontSize: "0.7rem", color: "var(--red)" }}>
                <Trash2 size={13} />
              </button>
            )}
            <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.5rem" }}>Produto/serviço {idx + 1}</p>
            <div className="flex items-center gap-2 mb-3">
              {(["produto", "servico"] as const).map((t) => (
                <button key={t} type="button" onClick={() => atualizarItem(idx, { tipo_item: t, produto: "" })}
                  style={{ fontSize: "0.72rem", padding: "0.25rem 0.7rem", borderRadius: "999px", cursor: "pointer",
                    border: "1px solid " + (it.tipo_item === t ? "var(--dourado)" : "var(--border)"),
                    background: it.tipo_item === t ? "var(--dourado)" : "transparent",
                    color: it.tipo_item === t ? "#1a1a1a" : "var(--text-muted)", fontWeight: it.tipo_item === t ? 700 : 400 }}>
                  {t === "produto" ? "Produto" : "Serviço"}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Campo label="Conta gerencial">
                <input list={`fin-contas-${idx}`} style={inputStyle}
                  value={it.codigo_conta_gerencial ? `${it.codigo_conta_gerencial} — ${it.nome_conta_gerencial}` : it.nome_conta_gerencial}
                  onChange={(e) => escolherContaGerencial(idx, e.target.value)} placeholder="ex.: 3.01.01.01 — Concentrado protéico" />
                <datalist id={`fin-contas-${idx}`}>{contasFiltradas.map((c) => <option key={c.codigo} value={`${c.codigo} — ${c.nome}`} />)}</datalist>
              </Campo>
              {it.tipo_item === "servico" ? (
                <Campo label="Serviço">
                  <input list={`fin-servicos-${idx}`} style={inputStyle} value={it.produto} onChange={(e) => atualizarItem(idx, { produto: e.target.value })} placeholder="ex.: Frete" />
                  <datalist id={`fin-servicos-${idx}`}>{sugestoesServico.map((s) => <option key={s} value={s} />)}</datalist>
                </Campo>
              ) : (
                <Campo label="Produto">
                  <select style={inputStyle} value={it.produto} onChange={(e) => {
                    const nomeProduto = e.target.value;
                    atualizarItem(idx, { produto: nomeProduto });
                    const match = produtosEstoque.find((p) => p.nome === nomeProduto);
                    if (match?.fornecedor_nome) setFornecedor(match.fornecedor_nome);
                  }}>
                    <option value="">Selecione…</option>
                    {produtosEstoque.slice().sort((a, b) => a.nome.localeCompare(b.nome)).map((p) => <option key={p.nome} value={p.nome}>{p.nome}</option>)}
                  </select>
                </Campo>
              )}
              <Campo label="Descrição (opcional)">
                <input style={inputStyle} value={it.descricao} onChange={(e) => atualizarItem(idx, { descricao: e.target.value })} />
              </Campo>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
              <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={it.quantidade} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value })} /></Campo>
              <Campo label="Valor unitário (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={it.valor_unitario} onChange={(e) => atualizarItem(idx, { valor_unitario: e.target.value })} /></Campo>
              <Campo label="Valor total (R$)">
                <input type="number" inputMode="decimal" style={inputStyle} value={it.valor_total}
                  onChange={(e) => atualizarItem(idx, { valor_total: e.target.value, valorTotalManual: true })} />
              </Campo>
            </div>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", marginTop: "0.6rem" }}
              onClick={() => { setAdicionarPara(idx); setModoAdicionar(it.tipo_item === "servico" ? "servico" : "produto"); }}>
              <Plus size={13} /> Adicionar {it.tipo_item === "servico" ? "serviço" : "produto"} ou conta gerencial novo(a)
            </button>
          </div>
        ))}
        <button type="button" className="btn-ghost" onClick={acrescentarItem} style={{ fontSize: "0.8rem" }}>
          <Plus size={14} /> Acrescentar produto ou serviço
        </button>
      </div>

      {/* Dados da nota (uma vez por lançamento) */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mt-4">
        <Campo label={tipo === "receita" ? "Cliente" : "Fornecedor"}>
          <div className="flex items-center gap-2">
            <select style={inputStyle} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Selecione…</option>
              {fornecedoresDisponiveis.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoFornecedor(true)}>
              <Plus size={13} /> Novo
            </button>
          </div>
        </Campo>
        <Campo label="Centro de custo">
          <input list="fin-centros" style={inputStyle} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)} />
          <datalist id="fin-centros">{opcoes.centros_custo.map((c) => <option key={c} value={c} />)}</datalist>
        </Campo>
        <Campo label="Responsável pelo lançamento">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
            <option value="">Selecione…</option>
            {responsaveis.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Campo>
        <Campo label="Tipo de documento">
          <select style={inputStyle} value={tipoDocumento} onChange={(e) => setTipoDocumento(e.target.value)}>
            <option value="">Selecione…</option>
            {(opcoes.tipos_documento.length ? opcoes.tipos_documento : ["Nota fiscal", "Recibo", "Folha de pagamento", "Fatura", "Contrato"]).map((t) => <option key={t}>{t}</option>)}
          </select>
        </Campo>

        <Campo label="Número do documento"><input style={inputStyle} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} /></Campo>
        <Campo label="Data de emissão"><input type="date" style={inputStyle} value={dataEmissao} onChange={(e) => setDataEmissao(e.target.value)} /></Campo>
        <Campo label="Data prevista de entrada"><input type="date" style={inputStyle} value={dataPrevistaEntrada} onChange={(e) => setDataPrevistaEntrada(e.target.value)} /></Campo>
        <Campo label="Data do pedido"><input type="date" style={inputStyle} value={dataPedido} onChange={(e) => setDataPedido(e.target.value)} /></Campo>

        <Campo label="Entregue?">
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", marginTop: "0.4rem" }}>
            <input type="checkbox" checked={entregue} onChange={(e) => setEntregue(e.target.checked)} /> Já entregue / recebido
          </label>
        </Campo>
        <Campo label="Desconto (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={desconto} onChange={(e) => setDesconto(e.target.value)} placeholder="0,00" /></Campo>
        <Campo label="Acréscimo (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={acrescimo} onChange={(e) => setAcrescimo(e.target.value)} placeholder="0,00" /></Campo>
        <div>
          <label style={lbl}>Valor líquido da nota</label>
          <div style={{ ...inputStyle, fontWeight: 700, color: "var(--dourado-light)" }}>{formatBRL(valorLiquido)}</div>
        </div>
      </div>
      {(Number(desconto) > 0 || Number(acrescimo) > 0) && (
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
          Bruto dos produtos: {formatBRL(valorBruto)}
          {Number(desconto) > 0 && <> · desconto de {formatBRL(Number(desconto))}</>}
          {Number(acrescimo) > 0 && <> · acréscimo de {formatBRL(Number(acrescimo))}</>}
        </p>
      )}

      {/* Parcelamento */}
      <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
          <input type="checkbox" checked={parcelado} onChange={(e) => setParcelado(e.target.checked)} /> Lançamento parcelado
        </label>
        {parcelado && (
          <div style={{ marginTop: "0.6rem" }}>
            <Campo label="Quantidade de parcelas">
              <input type="number" min={1} style={{ ...inputStyle, maxWidth: "8rem" }} value={qtdParcelas} onChange={(e) => setQtdParcelas(e.target.value)} />
            </Campo>
            <table className="fazenda-table mt-2">
              <thead><tr><th>Parcela</th><th>Vencimento</th><th style={{ textAlign: "right" }}>Valor (R$)</th></tr></thead>
              <tbody>
                {parcelas.map((p, i) => (
                  <tr key={i}>
                    <td>{i + 1}/{parcelas.length}</td>
                    <td><input type="date" style={inputStyle} value={p.data_vencimento}
                      onChange={(e) => setParcelas((arr) => arr.map((x, j) => j === i ? { ...x, data_vencimento: e.target.value } : x))} /></td>
                    <td><input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }} value={p.valor}
                      onChange={(e) => setParcelas((arr) => arr.map((x, j) => j === i ? { ...x, valor: e.target.value } : x))} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {Math.abs(somaParcelas - valorLiquido) > 0.01 && (
              <p style={{ color: "var(--amber)", fontSize: "0.75rem", marginTop: "0.4rem" }}>
                <AlertTriangle size={12} style={{ display: "inline", marginRight: "0.2rem" }} />
                Soma das parcelas ({formatBRL(somaParcelas)}) difere do valor líquido ({formatBRL(valorLiquido)}).
              </p>
            )}
            <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
              Cada parcela nasce em aberto (conta a {tipo === "despesa" ? "pagar" : "receber"}) — dê baixa individualmente quando for paga/recebida.
            </p>
          </div>
        )}
      </div>

      {/* Pagamento imediato (só para lançamento não parcelado) */}
      {!parcelado && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
            <input type="checkbox" checked={jaPago} onChange={(e) => setJaPago(e.target.checked)} /> Já foi {tipo === "despesa" ? "pago" : "recebido"}
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
              {diferencaPagamento !== 0 && (
                <p style={{ gridColumn: "1 / -1", fontSize: "0.78rem", color: diferencaPagamento < 0 ? "var(--green-light)" : "var(--amber)" }}>
                  {diferencaPagamento < 0 ? `Desconto de ${formatBRL(Math.abs(diferencaPagamento))}` : `Acréscimo de ${formatBRL(diferencaPagamento)}`} em relação ao valor líquido (na baixa do pagamento, diferente do desconto/acréscimo da nota acima).
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Salvar lançamento"}
        </button>
      </div>

      {adicionarPara !== null && (
        <Modal title="Adicionar produto, serviço ou conta gerencial" onClose={() => setAdicionarPara(null)} width="900px">
          <div className="flex items-center gap-2 mb-3">
            <button type="button" onClick={() => setModoAdicionar("produto")}
              style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
                border: "1px solid " + (modoAdicionar === "produto" ? "var(--dourado)" : "var(--border)"),
                background: modoAdicionar === "produto" ? "rgba(94,26,46,0.4)" : "transparent",
                color: modoAdicionar === "produto" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoAdicionar === "produto" ? 700 : 500 }}>
              Novo produto (estoque)
            </button>
            <button type="button" onClick={() => setModoAdicionar("servico")}
              style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
                border: "1px solid " + (modoAdicionar === "servico" ? "var(--dourado)" : "var(--border)"),
                background: modoAdicionar === "servico" ? "rgba(94,26,46,0.4)" : "transparent",
                color: modoAdicionar === "servico" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoAdicionar === "servico" ? 700 : 500 }}>
              Novo serviço
            </button>
            <button type="button" onClick={() => setModoAdicionar("conta")}
              style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
                border: "1px solid " + (modoAdicionar === "conta" ? "var(--dourado)" : "var(--border)"),
                background: modoAdicionar === "conta" ? "rgba(94,26,46,0.4)" : "transparent",
                color: modoAdicionar === "conta" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoAdicionar === "conta" ? 700 : 500 }}>
              Nova conta gerencial
            </button>
          </div>
          {modoAdicionar === "produto" ? (
            <NovoItemEstoque
              onCriado={(item) => {
                if (item?.nome && adicionarPara !== null) atualizarItem(adicionarPara, { produto: item.nome });
                carregarEstoque();
                setAdicionarPara(null);
              }}
              onCancelar={() => setAdicionarPara(null)}
            />
          ) : modoAdicionar === "servico" ? (
            <NovoServicoRapido
              onCriado={(servico) => {
                if (servico?.nome && adicionarPara !== null) atualizarItem(adicionarPara, { produto: servico.nome });
                carregarServicos();
                setAdicionarPara(null);
              }}
              onCancelar={() => setAdicionarPara(null)}
            />
          ) : (
            <NovaContaGerencial
              tipoSugerido={tipo}
              onCriado={(conta) => {
                if (adicionarPara !== null) atualizarItem(adicionarPara, { codigo_conta_gerencial: conta.codigo, nome_conta_gerencial: conta.nome });
                carregarOpcoes();
                setAdicionarPara(null);
              }}
              onCancelar={() => setAdicionarPara(null)}
            />
          )}
        </Modal>
      )}

      {abrirNovoFornecedor && (
        <Modal title={`Novo ${tipo === "receita" ? "cliente" : "fornecedor"}`} onClose={() => setAbrirNovoFornecedor(false)} width="480px">
          <NovoFornecedorRapido
            tipoSugerido={tipo}
            onCriado={(f) => {
              if (f?.nome) setFornecedor(f.nome);
              carregarOpcoes();
              fetchFornecedores().then((d) => setFornecedoresCadastro((d || []).map((x: any) => x.nome))).catch(() => {});
              setAbrirNovoFornecedor(false);
            }}
            onCancelar={() => setAbrirNovoFornecedor(false)}
          />
        </Modal>
      )}

      {confirmando && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" style={{ width: "420px", maxWidth: "95vw" }}>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle size={18} style={{ color: "var(--amber)" }} /><strong>Confirmar diferença de valor</strong></div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
              Valor líquido: <strong style={{ color: "var(--text)" }}>{formatBRL(valorLiquido)}</strong><br />
              Valor {tipo === "despesa" ? "pago" : "recebido"}: <strong style={{ color: "var(--text)" }}>{formatBRL(Number(valorPago) || 0)}</strong><br />
              {diferencaPagamento < 0 ? "Desconto" : "Acréscimo"}: <strong style={{ color: diferencaPagamento < 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(Math.abs(diferencaPagamento))}</strong>
            </p>
            <div className="flex items-center gap-3 mt-3">
              <button className="btn-primary" onClick={salvar}><Check size={14} /> Confirmar e salvar</button>
              <button className="btn-ghost" onClick={() => setConfirmando(false)}><X size={14} /> Cancelar</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
