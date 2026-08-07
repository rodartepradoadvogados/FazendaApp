"use client";
// Lançamentos recorrentes (Financeiro > Ações > Lançamentos recorrentes) —
// contas que se repetem todo mês com valor às vezes fixo, às vezes variável
// (energia, internet, telefone, assinatura, aluguel). Cadastra-se UMA vez os
// dados fixos (fornecedor, conta gerencial, centro de custo, forma de
// pagamento/conta bancária padrão, dia de vencimento) e, todo período, o
// botão "Gerar lançamento" pede só os dados variáveis (valor, emissão,
// boleto) — ver POST /financeiro/recorrentes/{id}/gerar no backend, que
// reaproveita a mesma criação de lançamento de sempre (aparece no extrato
// como qualquer outro, dá pra dar baixa normalmente).
//
// Decisão de design: formulário DEDICADO (não o FormFinanceiro pré-preenchido)
// — o FormFinanceiro é grande (XML, múltiplos itens, parcelamento, vínculo
// sanitário...) e a maior parte não se aplica a "só entrar com o valor deste
// mês"; um formulário enxuto próprio tem bem menos atrito para esse fluxo.
import { Fragment, useEffect, useMemo, useState } from "react";
import { Repeat, Plus, Pencil, Zap, AlertTriangle, Check, X } from "lucide-react";
import {
  fetchLancamentosRecorrentes, criarLancamentoRecorrente, atualizarLancamentoRecorrente, gerarLancamentoRecorrente,
  fetchOpcoesFinanceiro, fetchPlanoContas, fetchFornecedores, formatDate, formatBRL,
  type LancamentoRecorrente, type LancamentoRecorrentePayload,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import { Modal } from "@/components/Modal";
import { CampoMoeda } from "@/components/CampoMoeda";
import type { ContaPlano } from "@/lib/contaGerencial";
import { RESPONSAVEIS } from "@/lib/constants";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };

type Form = {
  descricao: string; tipo: "receita" | "despesa";
  fornecedor_cliente: string; centro_custo: string;
  codigo_conta_gerencial: string; nome_conta_gerencial: string;
  tipo_item: "produto" | "servico";
  responsavel_padrao: string; tipo_documento_padrao: string;
  forma_pagamento_padrao: string; conta_bancaria_padrao: string;
  dia_vencimento: string; observacao: string; ativo: boolean;
};
const formVazio: Form = {
  descricao: "", tipo: "despesa", fornecedor_cliente: "", centro_custo: "Pecuária Leiteira",
  codigo_conta_gerencial: "", nome_conta_gerencial: "", tipo_item: "servico",
  responsavel_padrao: "", tipo_documento_padrao: "", forma_pagamento_padrao: "", conta_bancaria_padrao: "",
  dia_vencimento: "", observacao: "", ativo: true,
};

function paraPayload(f: Form): LancamentoRecorrentePayload {
  const s = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    descricao: f.descricao.trim(), tipo: f.tipo,
    fornecedor_cliente: s(f.fornecedor_cliente), centro_custo: s(f.centro_custo),
    codigo_conta_gerencial: s(f.codigo_conta_gerencial), nome_conta_gerencial: s(f.nome_conta_gerencial),
    tipo_item: f.tipo_item,
    responsavel_padrao: s(f.responsavel_padrao), tipo_documento_padrao: s(f.tipo_documento_padrao),
    forma_pagamento_padrao: s(f.forma_pagamento_padrao), conta_bancaria_padrao: s(f.conta_bancaria_padrao),
    dia_vencimento: f.dia_vencimento ? Number(f.dia_vencimento) : null,
    periodicidade: "mensal",
    observacao: s(f.observacao), ativo: f.ativo,
  };
}

export default function LancamentosRecorrentesView({ onFeito }: { onFeito?: () => void }) {
  const [itens, setItens] = useState<LancamentoRecorrente[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const [opcoes, setOpcoes] = useState<{ centros_custo: string[]; fornecedores: string[]; contas_bancarias: string[]; tipos_documento: string[]; formas_pagamento: string[] }>(
    { centros_custo: [], fornecedores: [], contas_bancarias: [], tipos_documento: [], formas_pagamento: [] },
  );
  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  const [fornecedoresCadastro, setFornecedoresCadastro] = useState<string[]>([]);
  const fornecedoresDisponiveis = useMemo(
    () => Array.from(new Set([...opcoes.fornecedores, ...fornecedoresCadastro])).sort((a, b) => a.localeCompare(b, "pt-BR")),
    [opcoes.fornecedores, fornecedoresCadastro],
  );

  const carregar = () => fetchLancamentosRecorrentes().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchOpcoesFinanceiro().then(setOpcoes).catch(() => {});
    fetchPlanoContas().then(setPlanoContas).catch(() => {});
    fetchFornecedores().then((d: any[]) => setFornecedoresCadastro((d || []).map((f) => f.nome))).catch(() => {});
  }, []);

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (m: LancamentoRecorrente) => {
    setForm({
      descricao: m.descricao, tipo: m.tipo, fornecedor_cliente: m.fornecedor_cliente ?? "",
      centro_custo: m.centro_custo ?? "", codigo_conta_gerencial: m.codigo_conta_gerencial ?? "",
      nome_conta_gerencial: m.nome_conta_gerencial ?? "", tipo_item: m.tipo_item ?? "servico",
      responsavel_padrao: m.responsavel_padrao ?? "", tipo_documento_padrao: m.tipo_documento_padrao ?? "",
      forma_pagamento_padrao: m.forma_pagamento_padrao ?? "", conta_bancaria_padrao: m.conta_bancaria_padrao ?? "",
      dia_vencimento: m.dia_vencimento != null ? String(m.dia_vencimento) : "", observacao: m.observacao ?? "", ativo: m.ativo,
    });
    setEditando(m.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.descricao.trim()) { setMsg("Descrição é obrigatória."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = paraPayload(form);
      if (editando === "novo") await criarLancamentoRecorrente(dados);
      else if (typeof editando === "number") await atualizarLancamentoRecorrente(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(itens ?? []);
  const [gerarPara, setGerarPara] = useState<LancamentoRecorrente | null>(null);

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Repeat size={16} /> Lançamentos recorrentes</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo modelo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Cadastre uma vez os dados fixos de uma conta que se repete todo mês (energia, internet, telefone, assinatura, aluguel) e,
        a cada período, use "Gerar lançamento" para lançar só o valor, a data de emissão e o boleto daquele mês.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <FormModelo form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
          opcoes={opcoes} planoContas={planoContas} fornecedores={fornecedoresDisponiveis} />
      )}

      {itens && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <ThOrdenavel label="Descrição" campo="descricao" coluna={coluna} dir={dir} ordenar={ordenar} />
              <ThOrdenavel label="Tipo" campo="tipo" coluna={coluna} dir={dir} ordenar={ordenar} />
              <ThOrdenavel label="Fornecedor/Cliente" campo="fornecedor_cliente" coluna={coluna} dir={dir} ordenar={ordenar} />
              <ThOrdenavel label="Centro de custo" campo="centro_custo" coluna={coluna} dir={dir} ordenar={ordenar} />
              <ThOrdenavel label="Dia venc." campo="dia_vencimento" coluna={coluna} dir={dir} ordenar={ordenar} alinhar="right" />
              <ThOrdenavel label="Último lançamento" campo="ultimo_numero_lancamento" coluna={coluna} dir={dir} ordenar={ordenar} />
              <th>Ativo</th>
              <th></th>
            </tr></thead>
            <tbody>
              {linhasOrdenadas.map((m) => (
                <Fragment key={m.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{m.descricao}</td>
                    <td style={{ textTransform: "capitalize" }}>{m.tipo}</td>
                    <td style={{ fontSize: "0.78rem" }}>{m.fornecedor_cliente || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{m.centro_custo || "—"}</td>
                    <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{m.dia_vencimento ?? "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>
                      {m.ultimo_numero_lancamento
                        ? <>{m.ultimo_numero_lancamento}{m.ultima_geracao_em && <span style={{ color: "var(--text-muted)" }}> ({formatDate(m.ultima_geracao_em)})</span>}</>
                        : <span style={{ color: "var(--text-muted)" }}>ainda não gerado</span>}
                    </td>
                    <td style={{ fontSize: "0.78rem", color: m.ativo ? "var(--green-light)" : "var(--text-muted)" }}>{m.ativo ? "Sim" : "Não"}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button className="btn-primary" title="Gerar o lançamento deste período a partir deste modelo"
                        style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", marginRight: "0.4rem" }}
                        onClick={() => setGerarPara(m)} disabled={!m.ativo}>
                        <Zap size={13} /> Gerar
                      </button>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(m)}>
                        <Pencil size={13} /> Editar
                      </button>
                    </td>
                  </tr>
                  {editando === m.id && (
                    <tr><td colSpan={8} style={{ padding: 0 }}>
                      <FormModelo form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                        opcoes={opcoes} planoContas={planoContas} fornecedores={fornecedoresDisponiveis} />
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && (
                <tr><td colSpan={8} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum lançamento recorrente cadastrado ainda.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {gerarPara && (
        <ModalGerar modelo={gerarPara} onClose={() => setGerarPara(null)}
          onGerado={() => { setGerarPara(null); carregar(); onFeito?.(); }} />
      )}
    </div>
  );
}

function FormModelo({ form, setForm, onSalvar, onCancelar, salvando, msg, opcoes, planoContas, fornecedores }: {
  form: Form; setForm: (f: Form) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
  opcoes: { centros_custo: string[]; contas_bancarias: string[]; tipos_documento: string[]; formas_pagamento: string[] };
  planoContas: ContaPlano[]; fornecedores: string[];
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>Descrição do modelo (ex.: "Energia CPFL")</label>
          <input style={inputStyle} value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
        </div>
        <div>
          <label style={labelStyle}>Tipo</label>
          <div className="flex items-center gap-2">
            {(["despesa", "receita"] as const).map((t) => (
              <button key={t} type="button" onClick={() => setForm({ ...form, tipo: t, codigo_conta_gerencial: "", nome_conta_gerencial: "" })}
                style={{ fontSize: "0.72rem", padding: "0.25rem 0.7rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (form.tipo === t ? "var(--dourado)" : "var(--border)"),
                  background: form.tipo === t ? "var(--dourado)" : "transparent",
                  color: form.tipo === t ? "#1a1a1a" : "var(--text-muted)", fontWeight: form.tipo === t ? 700 : 400 }}>
                {t === "despesa" ? "A pagar" : "A receber"}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label style={labelStyle}>Item</label>
          <div className="flex items-center gap-2">
            {(["servico", "produto"] as const).map((t) => (
              <button key={t} type="button" onClick={() => setForm({ ...form, tipo_item: t })}
                style={{ fontSize: "0.72rem", padding: "0.25rem 0.7rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (form.tipo_item === t ? "var(--dourado)" : "var(--border)"),
                  background: form.tipo_item === t ? "var(--dourado)" : "transparent",
                  color: form.tipo_item === t ? "#1a1a1a" : "var(--text-muted)", fontWeight: form.tipo_item === t ? 700 : 400 }}>
                {t === "servico" ? "Serviço" : "Produto"}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label style={labelStyle}>Fornecedor / cliente</label>
          <input style={inputStyle} list="fornecedores-recorrente" value={form.fornecedor_cliente}
            onChange={(e) => setForm({ ...form, fornecedor_cliente: e.target.value })} />
          <datalist id="fornecedores-recorrente">{fornecedores.map((f) => <option key={f} value={f} />)}</datalist>
        </div>
        <div>
          <label style={labelStyle}>Centro de custo</label>
          <select style={inputStyle} value={form.centro_custo} onChange={(e) => setForm({ ...form, centro_custo: e.target.value })}>
            <option value="">Selecione…</option>
            {opcoes.centros_custo.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>Conta gerencial</label>
          <SeletorContaGerencial
            contas={planoContas} tipo={form.tipo === "despesa" ? "despesa" : "receita"} natureza={form.tipo_item}
            codigo={form.codigo_conta_gerencial} nome={form.nome_conta_gerencial}
            onSelect={(codigo, nome) => setForm({ ...form, codigo_conta_gerencial: codigo, nome_conta_gerencial: nome })}
            placeholder="Escolha a conta (só o galho mais baixo)…"
          />
        </div>
        <div>
          <label style={labelStyle}>Dia de vencimento típico</label>
          <input type="number" min={1} max={31} style={inputStyle} value={form.dia_vencimento}
            onChange={(e) => setForm({ ...form, dia_vencimento: e.target.value })} placeholder="ex.: 10" />
        </div>
        <div>
          <label style={labelStyle}>Periodicidade</label>
          <select style={inputStyle} value="mensal" disabled title="Por enquanto só mensal é suportado">
            <option value="mensal">Mensal</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Tipo de documento padrão</label>
          <select style={inputStyle} value={form.tipo_documento_padrao} onChange={(e) => setForm({ ...form, tipo_documento_padrao: e.target.value })}>
            <option value="">Selecione…</option>
            {opcoes.tipos_documento.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Forma de pagamento padrão</label>
          <select style={inputStyle} value={form.forma_pagamento_padrao} onChange={(e) => setForm({ ...form, forma_pagamento_padrao: e.target.value })}>
            <option value="">Selecione…</option>
            {opcoes.formas_pagamento.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Conta bancária padrão</label>
          <select style={inputStyle} value={form.conta_bancaria_padrao} onChange={(e) => setForm({ ...form, conta_bancaria_padrao: e.target.value })}>
            <option value="">Selecione…</option>
            {opcoes.contas_bancarias.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Responsável padrão</label>
          <select style={inputStyle} value={form.responsavel_padrao} onChange={(e) => setForm({ ...form, responsavel_padrao: e.target.value })}>
            <option value="">Selecione…</option>
            {RESPONSAVEIS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div className="flex items-end">
          <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo
          </label>
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>Observação (opcional)</label>
          <textarea style={{ ...inputStyle, minHeight: "2.4rem" }} value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} />
        </div>
      </div>
      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onSalvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}

// Formulário enxuto de "gerar lançamento deste período" — só os dados
// variáveis; o resto já vem do modelo (ver ModalGerar → gerarLancamentoRecorrente).
function ModalGerar({ modelo, onClose, onGerado }: { modelo: LancamentoRecorrente; onClose: () => void; onGerado: () => void }) {
  const hoje = new Date().toISOString().slice(0, 10);
  const [valor, setValor] = useState("");
  const [dataEmissao, setDataEmissao] = useState(hoje);
  const [dataVencimento, setDataVencimento] = useState("");
  const [numeroBoleto, setNumeroBoleto] = useState("");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [observacao, setObservacao] = useState("");
  const [jaPago, setJaPago] = useState(false);
  const [dataPagamento, setDataPagamento] = useState(hoje);
  const [valorPago, setValorPago] = useState("");
  const [contaBancaria, setContaBancaria] = useState(modelo.conta_bancaria_padrao ?? "");
  const [formaPagamento, setFormaPagamento] = useState(modelo.forma_pagamento_padrao ?? "");
  const [numeroDocumentoPagamento, setNumeroDocumentoPagamento] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const salvar = async () => {
    setErro(null);
    const v = Number(valor);
    if (!v || v <= 0) { setErro("Informe o valor deste período."); return; }
    setSalvando(true);
    try {
      const r = await gerarLancamentoRecorrente(modelo.id, {
        valor: v,
        data_emissao: dataEmissao || null,
        data_vencimento: dataVencimento || null,
        numero_boleto: numeroBoleto || null,
        numero_documento: numeroDocumento || null,
        observacao: observacao || null,
        ja_pago: jaPago,
        data_pagamento: jaPago ? dataPagamento || null : null,
        valor_pago: jaPago ? Number(valorPago) || v : null,
        conta_bancaria: jaPago ? contaBancaria || null : null,
        forma_pagamento: jaPago ? formaPagamento || null : null,
        numero_documento_pagamento: jaPago ? numeroDocumentoPagamento || null : null,
      });
      alert(`Lançamento ${r.numero_lancamento} gerado com sucesso.`);
      onGerado();
    } catch (e: any) {
      setErro(e.message || "Erro ao gerar o lançamento");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <Modal title={`Gerar lançamento — ${modelo.descricao}`} onClose={onClose} width="560px">
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        {modelo.fornecedor_cliente ? `${modelo.fornecedor_cliente} · ` : ""}{modelo.centro_custo || "Sem centro de custo"}
        {modelo.dia_vencimento ? ` · vencimento padrão dia ${modelo.dia_vencimento}` : ""}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <label style={labelStyle}>Valor (R$)</label>
          <CampoMoeda style={inputStyle} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} autoFocus />
        </div>
        <div>
          <label style={labelStyle}>Data de emissão</label>
          <input type="date" style={inputStyle} value={dataEmissao} onChange={(e) => setDataEmissao(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Data de vencimento</label>
          <input type="date" style={inputStyle} value={dataVencimento} onChange={(e) => setDataVencimento(e.target.value)}
            placeholder={modelo.dia_vencimento ? `dia ${modelo.dia_vencimento} (padrão)` : ""} />
          <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
            Deixe em branco para usar o vencimento padrão do modelo.
          </p>
        </div>
        <div>
          <label style={labelStyle}>Nº do boleto (opcional)</label>
          <input style={inputStyle} value={numeroBoleto} onChange={(e) => setNumeroBoleto(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Nº do documento (opcional)</label>
          <input style={inputStyle} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>Observação deste período (opcional)</label>
          <input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} placeholder="ex.: leitura 1234 kWh" />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}>
            <input type="checkbox" checked={jaPago} onChange={(e) => setJaPago(e.target.checked)} /> Já nasce pago/recebido
          </label>
        </div>
        {jaPago && <>
          <div>
            <label style={labelStyle}>Data do pagamento</label>
            <input type="date" style={inputStyle} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Valor pago (R$)</label>
            <CampoMoeda style={inputStyle} value={Number(valorPago) || 0}
              onChange={(v) => setValorPago(v ? String(v) : "")} placeholder={valor || "igual ao valor acima"} />
          </div>
          <div>
            <label style={labelStyle}>Conta bancária</label>
            <input style={inputStyle} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Forma de pagamento</label>
            <input style={inputStyle} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)} />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={labelStyle}>Nº do documento de pagamento (opcional)</label>
            <input style={inputStyle} value={numeroDocumentoPagamento} onChange={(e) => setNumeroDocumentoPagamento(e.target.value)} />
          </div>
        </>}
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Gerando…" : "Gerar lançamento"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onClose}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </Modal>
  );
}
