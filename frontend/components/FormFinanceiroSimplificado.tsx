"use client";
import { cloneElement, isValidElement, useEffect, useId, useMemo, useState } from "react";
import { AlertTriangle, Check, Plus, Trash2, X } from "lucide-react";
import {
  fetchOpcoesFinanceiro, fetchEstoque, fetchFornecedores, fetchPlanoContas, fetchContasCorrentes, fetchCentrosCusto,
  criarLancamentoFinanceiro, fetchPossiveisDuplicados, formatBRL, type LancamentoParecido, type ContaCorrenteCadastro,
} from "@/lib/api";
import { CampoMoeda } from "@/components/CampoMoeda";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import type { ContaPlano } from "@/lib/contaGerencial";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  const idGerado = useId();
  const ehElemento = isValidElement<{ id?: string }>(children);
  const id = ehElemento ? (children.props.id ?? idGerado) : undefined;
  const filho = ehElemento ? cloneElement(children, { id }) : children;
  return <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label htmlFor={id} style={lbl}>{label}</label>{filho}</div>;
}

type ItemSimples = {
  tipoItem: "produto" | "servico";
  produto: string; // nome do estoque (produto, escolhido no picker) ou descrição livre (serviço)
  codigoContaGerencial: string;
  nomeContaGerencial: string;
  quantidade: string; // só usado quando tipoItem === "produto"
  valorTotal: string;
};
const itemVazio = (): ItemSimples => ({
  tipoItem: "produto", produto: "", codigoContaGerencial: "", nomeContaGerencial: "", quantidade: "", valorTotal: "",
});

const hoje = () => new Date().toISOString().slice(0, 10);

/**
 * Lançamento financeiro SIMPLIFICADO: fornecedor/cliente, um ou mais itens
 * (produto do estoque com quantidade, ou serviço em texto livre), uma única
 * data (vira emissão + vencimento + pagamento) e a conta bancária — sem
 * desconto/acréscimo, parcelamento, anexo, vínculo com Pedido/Patrimônio/vale.
 * O centro de custo não é um campo aqui: usa o centro de custo marcado como
 * padrão em Configurações > Parâmetros financeiros > Centro de custo (ver
 * `ParametrosFinanceiros.tsx::CentrosCusto`) — sem nenhum marcado, bloqueia o
 * salvamento em vez de adivinhar. Mesmo endpoint de sempre (POST
 * /financeiro/lancamentos) e mesma checagem de duplicados do formulário
 * completo (ver FormFinanceiro.tsx::salvar).
 */
export function FormFinanceiroSimplificado({ tipo, onSujo, onSalvo }: {
  tipo: "despesa" | "receita";
  onSujo?: (sujo: boolean) => void;
  onSalvo?: (mensagem: string) => void;
}) {
  const [fornecedoresCadastro, setFornecedoresCadastro] = useState<string[]>([]);
  const [fornecedoresOpcoes, setFornecedoresOpcoes] = useState<string[]>([]);
  useEffect(() => {
    fetchFornecedores().then((d) => setFornecedoresCadastro((d || []).map((f: any) => f.nome))).catch(() => {});
    fetchOpcoesFinanceiro().then((d) => setFornecedoresOpcoes(d.fornecedores || [])).catch(() => {});
  }, []);
  const fornecedoresDisponiveis = useMemo(
    () => Array.from(new Set([...fornecedoresOpcoes, ...fornecedoresCadastro])).sort((a, b) => a.localeCompare(b, "pt-BR")),
    [fornecedoresOpcoes, fornecedoresCadastro]
  );

  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  useEffect(() => { fetchPlanoContas().then(setPlanoContas).catch(() => {}); }, []);
  function contaGerencialPadrao(codigo: string | null | undefined) {
    if (!codigo) return null;
    const conta = planoContas.find((c) => c.codigo === codigo);
    return conta ? { codigo, nome: conta.nome } : null;
  }

  const [produtosEstoque, setProdutosEstoque] = useState<(EstoqueItemPicker & {
    conta_gerencial_despesa_padrao: string | null; conta_gerencial_receita_padrao: string | null;
  })[]>([]);
  useEffect(() => {
    fetchEstoque().then((d) => setProdutosEstoque((d.itens || []).map((i: any) => ({
      nome: i.nome, categoria: i.categoria ?? null, quantidade: i.quantidade ?? null, unidade: i.unidade ?? null,
      estocavel: i.estocavel ?? null, finalidade: i.finalidade ?? null,
      conta_gerencial_despesa_padrao: i.conta_gerencial_despesa_padrao ?? null,
      conta_gerencial_receita_padrao: i.conta_gerencial_receita_padrao ?? null,
    })))).catch(() => {});
  }, []);

  const [contasCorrentes, setContasCorrentes] = useState<ContaCorrenteCadastro[]>([]);
  useEffect(() => { fetchContasCorrentes().then(setContasCorrentes).catch(() => {}); }, []);
  const contasCorrentesAtivas = useMemo(() => contasCorrentes.filter((c) => c.ativo), [contasCorrentes]);

  // Centro de custo padrão (Configurações > Parâmetros financeiros > Centro
  // de custo) — não é um campo desta tela, e sem 1 marcado o salvamento fica
  // bloqueado (ver aviso abaixo) em vez de adivinhar um valor.
  const [centroCustoPadrao, setCentroCustoPadrao] = useState<string | null | undefined>(undefined); // undefined = ainda carregando
  const carregarCentroCustoPadrao = () =>
    fetchCentrosCusto().then((lista) => setCentroCustoPadrao(lista.find((c: any) => c.padrao)?.nome ?? null)).catch(() => setCentroCustoPadrao(null));
  useEffect(() => { carregarCentroCustoPadrao(); }, []);

  const [fornecedor, setFornecedor] = useState("");
  const [data, setData] = useState(hoje());
  const [contaBancaria, setContaBancaria] = useState("");
  const [itens, setItens] = useState<ItemSimples[]>([itemVazio()]);

  function atualizarItem(idx: number, patch: Partial<ItemSimples>) {
    setItens((arr) => arr.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }
  function acrescentarItem() { setItens((arr) => [...arr, itemVazio()]); }
  function removerItem(idx: number) { setItens((arr) => (arr.length > 1 ? arr.filter((_, i) => i !== idx) : arr)); }

  const itensValidos = useMemo(
    () => itens.filter((i) => i.produto.trim() && (Number(i.valorTotal) || 0) > 0),
    [itens]
  );
  const valorTotal = useMemo(() => itensValidos.reduce((s, i) => s + (Number(i.valorTotal) || 0), 0), [itensValidos]);

  const sujo = useMemo(
    () => Boolean(itens.some((i) => i.produto.trim() || i.valorTotal.trim()) || fornecedor || contaBancaria || data !== hoje()),
    [itens, fornecedor, contaBancaria, data]
  );
  useEffect(() => { onSujo?.(sujo); }, [sujo, onSujo]);

  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [duplicados, setDuplicados] = useState<LancamentoParecido[]>([]);
  const [confirmandoDuplicado, setConfirmandoDuplicado] = useState(false);
  const [verificandoDuplicado, setVerificandoDuplicado] = useState(false);

  function limpar() {
    setFornecedor(""); setData(hoje()); setContaBancaria(""); setItens([itemVazio()]);
  }

  function montarPayload() {
    return {
      tipo,
      itens: itensValidos.map((i) => ({
        codigo_conta_gerencial: i.codigoContaGerencial || null,
        nome_conta_gerencial: i.nomeContaGerencial || null,
        centro_custo: null,
        produto: i.produto.trim(),
        tipo_item: i.tipoItem,
        descricao: null,
        quantidade: i.tipoItem === "produto" && i.quantidade ? Number(i.quantidade) : null,
        valor_unitario: null,
        valor_total: Number(i.valorTotal) || 0,
        vale: null,
      })),
      centro_custo: centroCustoPadrao,
      classificacao: null,
      fornecedor_cliente: fornecedor || null,
      responsavel: null,
      tipo_documento: null,
      numero_documento: null,
      numero_os_orcamento: null,
      numero_boleto: null,
      data_emissao: data || null,
      data_vencimento: data || null,
      data_prevista_entrada: null,
      data_pedido: null,
      pedido_id: null,
      entregue: null,
      desconto: 0,
      acrescimo: 0,
      parcelas: [],
      // "Nasce pago": a mesma data escolhida também vira o pagamento — sem
      // parcelamento, sempre à vista (ver FormFinanceiro.tsx::montarPayload
      // para o equivalente no formulário completo, aqui sem o toggle "Já
      // foi pago", que não existe neste modo).
      data_pagamento: data || null,
      valor_pago: valorTotal,
      conta_bancaria: contaBancaria || null,
      numero_documento_pagamento: null,
      forma_pagamento: null,
      criar_patrimonio: null,
    };
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!centroCustoPadrao) {
      setErro("Nenhum centro de custo padrão configurado — configure em Parâmetros financeiros > Centro de custo antes de usar o lançamento simplificado.");
      return;
    }
    if (!fornecedor.trim()) { setErro(`Selecione o ${tipo === "receita" ? "cliente" : "fornecedor"}.`); return; }
    if (!itensValidos.length) { setErro("Informe ao menos um produto ou serviço, com valor maior que zero."); return; }
    if (itensValidos.some((i) => i.tipoItem === "produto" && !(Number(i.quantidade) > 0))) {
      setErro("Informe a quantidade (maior que zero) de cada produto."); return;
    }
    if (!data) { setErro("Informe a data do lançamento."); return; }
    if (!contaBancaria) { setErro("Selecione a conta bancária."); return; }

    if (!confirmandoDuplicado) {
      setVerificandoDuplicado(true);
      try {
        const achados = await fetchPossiveisDuplicados({ tipo, valor_total: valorTotal, fornecedor_cliente: fornecedor, data_emissao: data || undefined });
        if (achados.length) { setDuplicados(achados); setConfirmandoDuplicado(true); return; }
      } finally {
        setVerificandoDuplicado(false);
      }
    }

    setSalvando(true);
    try {
      const r = await criarLancamentoFinanceiro(montarPayload());
      const avisoEstoque = (r.avisos_estoque || []).length ? ` ${r.avisos_estoque.join(" ")}` : "";
      const mensagem = `Lançamento ${r.numero_lancamento} salvo com sucesso.${avisoEstoque}`;
      setSucesso(mensagem);
      limpar();
      onSujo?.(false);
      onSalvo?.(mensagem);
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar lançamento");
    } finally {
      setSalvando(false); setConfirmandoDuplicado(false); setDuplicados([]);
    }
  }

  return (
    <>
      {centroCustoPadrao === null && (
        <div className="alert-critico mb-3">
          <AlertTriangle size={18} />
          <span>Nenhum centro de custo padrão configurado — configure em Configurações &gt; Parâmetros financeiros &gt; Centro de custo antes de usar o lançamento simplificado.</span>
        </div>
      )}

      <div className="card">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Campo label={tipo === "receita" ? "Cliente" : "Fornecedor"}>
            <select style={inputStyle} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Selecione…</option>
              {fornecedoresDisponiveis.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </Campo>
          <Campo label="Data">
            <input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} />
            <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginTop: "0.2rem" }}>
              Vira emissão, vencimento e pagamento ao mesmo tempo — este modo nasce sempre pago/recebido, sem parcelamento.
            </span>
          </Campo>
          <Campo label="Conta bancária">
            <select style={inputStyle} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
              <option value="">Selecione…</option>
              {contasCorrentesAtivas.map((c) => <option key={c.id} value={c.rotulo}>{c.rotulo}</option>)}
            </select>
          </Campo>
        </div>
      </div>

      <div className="card mt-3">
        <p className="card-header mb-2">Itens</p>
        {itens.map((it, idx) => (
          <div key={idx} style={{ position: "relative", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.7rem", marginBottom: "0.6rem" }}>
            {itens.length > 1 && (
              <button type="button" title="Remover este item" onClick={() => removerItem(idx)} className="btn-ghost" style={{ position: "absolute", top: "0.5rem", right: "0.5rem", fontSize: "0.7rem", color: "var(--red)" }}>
                <Trash2 size={13} />
              </button>
            )}
            <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.5rem" }}>Item {idx + 1}</p>
            <div className="flex items-center gap-2 mb-3">
              {(["produto", "servico"] as const).map((t) => (
                <button key={t} type="button" onClick={() => atualizarItem(idx, { tipoItem: t, produto: "", quantidade: "" })}
                  style={{ fontSize: "0.72rem", padding: "0.25rem 0.7rem", borderRadius: "999px", cursor: "pointer",
                    border: "1px solid " + (it.tipoItem === t ? "var(--dourado)" : "var(--border)"),
                    background: it.tipoItem === t ? "var(--dourado)" : "transparent",
                    color: it.tipoItem === t ? "#1a1a1a" : "var(--text-muted)", fontWeight: it.tipoItem === t ? 700 : 400 }}>
                  {t === "produto" ? "Produto" : "Serviço"}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {it.tipoItem === "produto" ? (
                <>
                  <Campo label="Produto (do estoque)">
                    <EstoquePicker itens={produtosEstoque} value={it.produto} todasFinalidades incluirNaoEstocaveis onChange={(nomeProduto) => {
                      const match = produtosEstoque.find((p) => p.nome === nomeProduto);
                      const patch: Partial<ItemSimples> = { produto: nomeProduto };
                      const conta = contaGerencialPadrao(tipo === "despesa" ? match?.conta_gerencial_despesa_padrao : match?.conta_gerencial_receita_padrao);
                      if (conta) { patch.codigoContaGerencial = conta.codigo; patch.nomeContaGerencial = conta.nome; }
                      atualizarItem(idx, patch);
                    }} />
                  </Campo>
                  <Campo label="Quantidade">
                    <input type="number" min="0" step="any" style={inputStyle} value={it.quantidade} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value })} />
                  </Campo>
                </>
              ) : (
                <Campo label="Descrição do serviço" full>
                  <input style={inputStyle} value={it.produto} onChange={(e) => atualizarItem(idx, { produto: e.target.value })} placeholder="ex.: Frete, Manutenção de cerca…" />
                </Campo>
              )}
              <Campo label="Conta gerencial">
                <SeletorContaGerencial
                  contas={planoContas}
                  tipo={tipo}
                  natureza={it.tipoItem}
                  codigo={it.codigoContaGerencial}
                  nome={it.nomeContaGerencial}
                  onSelect={(codigo, nome) => atualizarItem(idx, { codigoContaGerencial: codigo, nomeContaGerencial: nome })}
                  placeholder="Escolha a conta (só o galho mais baixo)…"
                />
              </Campo>
              <Campo label="Valor total (R$)">
                <CampoMoeda style={inputStyle} value={Number(it.valorTotal) || 0} onChange={(v) => atualizarItem(idx, { valorTotal: v ? String(v) : "" })} />
              </Campo>
            </div>
          </div>
        ))}
        <button type="button" className="btn-ghost" onClick={acrescentarItem} style={{ fontSize: "0.8rem" }}>
          <Plus size={14} /> Adicionar item
        </button>

        <div className="flex items-center justify-between mt-3" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.7rem" }}>
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Valor total do lançamento</span>
          <strong style={{ fontSize: "1rem", color: "var(--dourado-light)" }}>{formatBRL(valorTotal)}</strong>
        </div>
      </div>

      {erro && <div className="alert-critico mt-3"><AlertTriangle size={18} /><span>{erro}</span></div>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.82rem", marginTop: "0.7rem" }}>{sucesso}</p>}

      <div className="mt-3">
        <button type="button" className="btn-primary" disabled={salvando || verificandoDuplicado || centroCustoPadrao === undefined} onClick={salvar}>
          <Check size={14} /> {salvando ? "Salvando…" : verificandoDuplicado ? "Verificando…" : "Salvar lançamento"}
        </button>
      </div>

      {confirmandoDuplicado && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" style={{ width: "560px", maxWidth: "95vw" }}>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle size={18} style={{ color: "var(--amber)" }} /><strong>Possível lançamento duplicado</strong></div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
              Já existe {duplicados.length > 1 ? "lançamentos parecidos" : "um lançamento parecido"} com o mesmo fornecedor/cliente,
              valor próximo e data próxima. Confira antes de salvar de novo.
            </p>
            <div style={{ overflowX: "auto" }}>
              <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
                <thead><tr><th></th><th>Novo lançamento</th>{duplicados.map((d) => <th key={d.id}>Nº {d.numero_lancamento || d.id}</th>)}</tr></thead>
                <tbody>
                  <tr><td style={{ color: "var(--text-muted)" }}>Fornecedor/cliente</td><td>{fornecedor || "—"}</td>{duplicados.map((d) => <td key={d.id}>{d.fornecedor_cliente || "—"}</td>)}</tr>
                  <tr><td style={{ color: "var(--text-muted)" }}>Valor</td><td>{formatBRL(valorTotal)}</td>{duplicados.map((d) => <td key={d.id}>{formatBRL(d.valor_total || 0)}</td>)}</tr>
                  <tr><td style={{ color: "var(--text-muted)" }}>Data</td><td>{data || "—"}</td>{duplicados.map((d) => <td key={d.id}>{d.data_emissao || d.data_competencia || "—"}</td>)}</tr>
                </tbody>
              </table>
            </div>
            <div className="flex items-center gap-3 mt-3">
              <button className="btn-primary" title="Salvar mesmo assim (não é duplicado)" onClick={salvar}><Check size={14} /> Salvar mesmo assim</button>
              <button className="btn-ghost" title="Cancelar e revisar os dados" onClick={() => { setConfirmandoDuplicado(false); setDuplicados([]); }}><X size={14} /> Cancelar</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
