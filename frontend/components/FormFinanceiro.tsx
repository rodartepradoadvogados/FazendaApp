"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Upload, FileText, X, Check, AlertTriangle, Loader2 } from "lucide-react";
import { fetchOpcoesFinanceiro, criarLancamentoFinanceiro, importarXmlFinanceiro, formatBRL } from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label style={lbl}>{label}</label>{children}</div>;
}

type Parcela = { data_vencimento: string; valor: string };

type Opcoes = {
  contas_gerenciais: { codigo: string | null; descricao: string | null }[];
  centros_custo: string[];
  fornecedores: string[];
  contas_bancarias: string[];
  tipos_documento: string[];
};

const OPCOES_VAZIAS: Opcoes = { contas_gerenciais: [], centros_custo: [], fornecedores: [], contas_bancarias: [], tipos_documento: [] };

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

/** Lançamento financeiro completo: parcelamento, conta bancária, documento, produto e importação de XML de nota. */
export function FormFinanceiro({ responsaveis }: { responsaveis: string[] }) {
  const [opcoes, setOpcoes] = useState<Opcoes>(OPCOES_VAZIAS);
  useEffect(() => { fetchOpcoesFinanceiro().then(setOpcoes).catch(() => {}); }, []);

  const [tipo, setTipo] = useState<"despesa" | "receita">("despesa");
  const [descricao, setDescricao] = useState("");
  const [centroCusto, setCentroCusto] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [tipoDocumento, setTipoDocumento] = useState("");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [dataEmissao, setDataEmissao] = useState("");
  const [dataPrevistaEntrada, setDataPrevistaEntrada] = useState("");
  const [dataPedido, setDataPedido] = useState("");
  const [entregue, setEntregue] = useState(false);
  const [quantidade, setQuantidade] = useState("");
  const [valorUnitario, setValorUnitario] = useState("");
  const [valorTotal, setValorTotal] = useState("");
  const [valorTotalEditadoManual, setValorTotalEditadoManual] = useState(false);

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

  // Produto: quantidade × valor unitário = valor total automático (a menos que o usuário sobrescreva).
  useEffect(() => {
    const q = Number(quantidade), v = Number(valorUnitario);
    if (quantidade && valorUnitario && !valorTotalEditadoManual) {
      setValorTotal((q * v).toFixed(2));
    }
  }, [quantidade, valorUnitario, valorTotalEditadoManual]);

  // Regenera as parcelas (divisão igual) quando ligar o parcelamento ou mudar quantidade/valor/data.
  useEffect(() => {
    if (!parcelado) { setParcelas([]); return; }
    const n = Math.max(1, Math.round(Number(qtdParcelas) || 0));
    const total = Number(valorTotal) || 0;
    setParcelas(dividirParcelas(total, n, dataPrevistaEntrada || dataEmissao));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parcelado, qtdParcelas]);

  const somaParcelas = useMemo(() => parcelas.reduce((a, p) => a + (Number(p.valor) || 0), 0), [parcelas]);
  const diferencaPagamento = useMemo(() => (valorPago && valorTotal ? Math.round((Number(valorPago) - Number(valorTotal)) * 100) / 100 : 0), [valorPago, valorTotal]);

  function limpar() {
    setDescricao(""); setCentroCusto(""); setFornecedor(""); setResponsavel(""); setTipoDocumento("");
    setNumeroDocumento(""); setDataEmissao(""); setDataPrevistaEntrada(""); setDataPedido(""); setEntregue(false);
    setQuantidade(""); setValorUnitario(""); setValorTotal(""); setValorTotalEditadoManual(false);
    setParcelado(false); setQtdParcelas("2"); setParcelas([]);
    setJaPago(false); setDataPagamento(""); setValorPago(""); setContaBancaria(""); setNumeroDocumentoPagamento("");
    setXmlTexto(""); setXmlAberto(false);
  }

  function aplicarXml(dados: any) {
    if (dados.numero_documento) setNumeroDocumento(dados.numero_documento);
    if (dados.data_emissao) setDataEmissao(dados.data_emissao);
    if (dados.fornecedor_cliente) setFornecedor(dados.fornecedor_cliente);
    if (dados.descricao) setDescricao(dados.descricao);
    if (dados.quantidade != null) setQuantidade(String(dados.quantidade));
    if (dados.valor_unitario != null) setValorUnitario(String(dados.valor_unitario));
    if (dados.valor_total != null) { setValorTotal(String(dados.valor_total)); setValorTotalEditadoManual(true); }
    setTipoDocumento("Nota fiscal");
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
      descricao: descricao || null,
      centro_custo: centroCusto || null,
      fornecedor_cliente: fornecedor || null,
      responsavel: responsavel || null,
      tipo_documento: tipoDocumento || null,
      numero_documento: numeroDocumento || null,
      data_emissao: dataEmissao || null,
      data_prevista_entrada: dataPrevistaEntrada || null,
      data_pedido: dataPedido || null,
      entregue,
      quantidade: quantidade ? Number(quantidade) : null,
      valor_unitario: valorUnitario ? Number(valorUnitario) : null,
      valor_total: Number(valorTotal) || 0,
      parcelas: parcelado ? parcelas.map((p) => ({ data_vencimento: p.data_vencimento, valor: Number(p.valor) || 0 })) : [],
      data_pagamento: !parcelado && jaPago ? dataPagamento || null : null,
      valor_pago: !parcelado && jaPago ? Number(valorPago) || 0 : null,
      conta_bancaria: !parcelado && jaPago ? contaBancaria || null : null,
      numero_documento_pagamento: !parcelado && jaPago ? numeroDocumentoPagamento || null : null,
    };
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!valorTotal || Number(valorTotal) <= 0) { setErro("Informe o valor total."); return; }
    if (!parcelado && jaPago && diferencaPagamento !== 0 && !confirmando) { setConfirmando(true); return; }
    setSalvando(true);
    try {
      const r = await criarLancamentoFinanceiro(montarPayload());
      setSucesso(`Lançamento ${r.numero_lancamento} salvo com sucesso.`);
      limpar();
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar lançamento");
    } finally {
      setSalvando(false); setConfirmando(false);
    }
  }

  const contasGerenciaisNomes = useMemo(
    () => Array.from(new Set(opcoes.contas_gerenciais.map((c) => c.descricao).filter(Boolean))) as string[],
    [opcoes]
  );

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
        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>Os campos importados ficam abaixo, todos editáveis antes de salvar.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Tipo">
          <select style={inputStyle} value={tipo} onChange={(e) => setTipo(e.target.value as any)}>
            <option value="despesa">Despesa (conta a pagar)</option>
            <option value="receita">Receita (conta a receber)</option>
          </select>
        </Campo>
        <Campo label="Descrição (conta gerencial / produto)">
          <input list="fin-contas" style={inputStyle} value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="ex.: Ração concentrada, Leite indústria…" />
          <datalist id="fin-contas">{contasGerenciaisNomes.map((c) => <option key={c} value={c} />)}</datalist>
        </Campo>
        <Campo label="Centro de custo">
          <input list="fin-centros" style={inputStyle} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)} />
          <datalist id="fin-centros">{opcoes.centros_custo.map((c) => <option key={c} value={c} />)}</datalist>
        </Campo>
        <Campo label="Fornecedor / cliente">
          <input list="fin-fornecedores" style={inputStyle} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)} />
          <datalist id="fin-fornecedores">{opcoes.fornecedores.map((f) => <option key={f} value={f} />)}</datalist>
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

        <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={quantidade} onChange={(e) => setQuantidade(e.target.value)} /></Campo>
        <Campo label="Valor unitário (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={valorUnitario} onChange={(e) => setValorUnitario(e.target.value)} /></Campo>
        <Campo label="Valor total (R$)">
          <input type="number" inputMode="decimal" style={inputStyle} value={valorTotal}
            onChange={(e) => { setValorTotal(e.target.value); setValorTotalEditadoManual(true); }} />
        </Campo>
      </div>

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
            {Math.abs(somaParcelas - (Number(valorTotal) || 0)) > 0.01 && (
              <p style={{ color: "var(--amber)", fontSize: "0.75rem", marginTop: "0.4rem" }}>
                <AlertTriangle size={12} style={{ display: "inline", marginRight: "0.2rem" }} />
                Soma das parcelas ({formatBRL(somaParcelas)}) difere do valor total ({formatBRL(Number(valorTotal) || 0)}).
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
                  {diferencaPagamento < 0 ? `Desconto de ${formatBRL(Math.abs(diferencaPagamento))}` : `Acréscimo de ${formatBRL(diferencaPagamento)}`} em relação ao valor total.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {erro &&<p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Salvar lançamento"}
        </button>
      </div>

      {confirmando && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" style={{ width: "420px", maxWidth: "95vw" }}>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle size={18} style={{ color: "var(--amber)" }} /><strong>Confirmar diferença de valor</strong></div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
              Valor total: <strong style={{ color: "var(--text)" }}>{formatBRL(Number(valorTotal) || 0)}</strong><br />
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
