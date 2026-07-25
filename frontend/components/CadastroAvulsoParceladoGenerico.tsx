"use client";
// Consolidação de UX (backlog #532): Empreitada e Contrato são dois dos "modelos
// de trabalhador avulso" da Folha de Pagamento e compartilhavam quase todo o
// formulário de lançamento e o card de listagem (pessoa, descrição, valor
// total, forma de pagamento com parcelamento, vale e listagem com parcelas/
// vales). Este componente extrai esse esqueleto comum — cada tela específica
// (EmpreitadaView, ContratoView) vira um wrapper fino que só descreve suas
// diferenças (etapas da empreita, "sem frequência definida" do contrato, etc.)
// via as props abaixo. Nenhum endpoint ou modelo de dado foi alterado — os
// wrappers continuam chamando os mesmos endpoints de sempre.
import { Fragment, useState } from "react";
import { Plus, Pencil, Shuffle } from "lucide-react";
import { formatBRL } from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { ParcelamentoEditor, type Parcela } from "@/components/ParcelamentoEditor";
import ValeAvulsoSection from "@/components/ValeAvulsoSection";
import { lbl, inputSm } from "@/components/estiloCampoAvulso";

export type ParcelaAvulsa = { id: number; data_vencimento: string; valor: number; status: string; numero_lancamento_gerado?: string | null };
export type ValeItemAvulso = { id: number; valor: number; forma_pagamento: string; data_pagamento: string; observacao: string | null };
export type ItemAvulso = {
  id: number; pessoa_id: number; pessoa_nome: string; descricao: string; valor_total: number;
  status: string; observacao: string | null; parcelas: ParcelaAvulsa[]; vales: ValeItemAvulso[];
};

export default function CadastroAvulsoParceladoGenerico<T extends ItemAvulso>({
  itens, error, recarregar,
  pessoas, labelPessoa, placeholderDescricao, msgSelecionePessoa, msgDescricaoObrigatoria,
  formasPagamento, formaPagamentoInicial,
  formasDataUnica = [], textoDataUnica,
  formasSemParcelamento = [], textoSemParcelamento, formasSemCampoData = [],
  renderExtra, validarExtra, resetExtra,
  tituloNovo, descricaoNovo, labelSalvar, salvar,
  tituloVale, descricaoVale, valeOrigemTipo, valeStatusExcluido,
  tituloListagem, textoVazioListagem, statusLabel = (s: string) => s, acaoItem, renderItemExtra,
  onEditarParcela, onRedistribuirParcelas,
}: {
  itens: T[] | null;
  error: string | null;
  recarregar: () => void;
  pessoas: { id: number; nome: string }[];
  labelPessoa: string;
  placeholderDescricao: string;
  /** Mensagem de validação quando a pessoa não foi selecionada (ex.: "Selecione o empreiteiro."). */
  msgSelecionePessoa: string;
  /** Mensagem de validação quando a descrição está vazia (ex.: "Informe a descrição da empreita."). */
  msgDescricaoObrigatoria: string;
  formasPagamento: { id: string; label: string }[];
  formaPagamentoInicial: string;
  /** Formas com data única (1 parcela = valor total, sem editor de parcelamento). */
  formasDataUnica?: string[];
  textoDataUnica?: (valorTotal: number) => string;
  /** Formas sem parcelamento por frequência (ex.: "por etapa" ou "sem frequência definida"). */
  formasSemParcelamento?: string[];
  textoSemParcelamento?: string;
  /** Formas em que nem o campo de data faz sentido (ex.: pagamento por etapa). */
  formasSemCampoData?: string[];
  /** Conteúdo extra do formulário quando a forma está em `formasSemParcelamento` (ex.: etapas da empreita). */
  renderExtra?: (ctx: { formaPagamento: string; valorTotal: number }) => React.ReactNode;
  /** Validação extra antes de salvar (ex.: exigir ao menos uma etapa preenchida). */
  validarExtra?: (ctx: { formaPagamento: string }) => string | null;
  /** Limpa o estado do formulário extra (ex.: etapas) após salvar com sucesso. */
  resetExtra?: () => void;
  tituloNovo: string;
  descricaoNovo: string;
  labelSalvar: string;
  /** Executa o lançamento específico (criarEmpreitada/criarContrato…) e devolve a mensagem de sucesso, ou lança erro. */
  salvar: (dados: {
    pessoaId: string; descricao: string; valorTotal: string; formaPagamento: string;
    parcelasPayload?: { data_vencimento: string; valor: number }[]; observacao: string;
  }) => Promise<string>;
  tituloVale: string;
  descricaoVale: string;
  valeOrigemTipo: "empreitada" | "contrato";
  /** Status que tira um item da lista de origens do vale (ex.: "concluida"/"encerrado"). */
  valeStatusExcluido: string;
  tituloListagem: string;
  textoVazioListagem: string;
  statusLabel?: (status: string) => string;
  acaoItem?: (item: T) => React.ReactNode;
  renderItemExtra?: (item: T) => React.ReactNode;
  /** Edita valor/vencimento de uma parcela pendente (bloqueado se já paga). */
  onEditarParcela?: (parcelaId: number, dados: { data_vencimento: string; valor: number }) => Promise<any>;
  /** Redivide igualmente o valor pendente entre as parcelas ainda não pagas do item. */
  onRedistribuirParcelas?: (itemId: number) => Promise<any>;
}) {
  const [pessoaId, setPessoaId] = useState("");
  const [descricao, setDescricao] = useState("");
  const [valorTotal, setValorTotal] = useState("");
  const [formaPagamento, setFormaPagamento] = useState(formaPagamentoInicial);
  const [dataPrimeiroPagamento, setDataPrimeiroPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [parcelas, setParcelas] = useState<Parcela[]>([]);
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const [editandoParcelaId, setEditandoParcelaId] = useState<number | null>(null);
  const [editParcelaData, setEditParcelaData] = useState("");
  const [editParcelaValor, setEditParcelaValor] = useState("");
  const [parcelaMsg, setParcelaMsg] = useState<string | null>(null);
  const [salvandoParcela, setSalvandoParcela] = useState(false);
  const [redistribuindoId, setRedistribuindoId] = useState<number | null>(null);

  function iniciarEdicaoParcela(p: ParcelaAvulsa) {
    setEditandoParcelaId(p.id);
    setEditParcelaData(p.data_vencimento);
    setEditParcelaValor(String(p.valor));
    setParcelaMsg(null);
  }

  async function salvarEdicaoParcela(parcelaId: number) {
    if (!onEditarParcela) return;
    setParcelaMsg(null);
    if (!editParcelaValor || parseFloat(editParcelaValor) <= 0) { setParcelaMsg("Informe o valor da parcela."); return; }
    setSalvandoParcela(true);
    try {
      await onEditarParcela(parcelaId, { data_vencimento: editParcelaData, valor: parseFloat(editParcelaValor) });
      setEditandoParcelaId(null);
      recarregar();
    } catch (e: any) {
      setParcelaMsg(e.message || "Erro ao editar parcela.");
    } finally {
      setSalvandoParcela(false);
    }
  }

  async function redistribuir(itemId: number) {
    if (!onRedistribuirParcelas) return;
    setRedistribuindoId(itemId);
    try {
      await onRedistribuirParcelas(itemId);
      recarregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao redistribuir parcelas." });
    } finally {
      setRedistribuindoId(null);
    }
  }

  const isDataUnica = formasDataUnica.includes(formaPagamento);
  const isSemParcelamento = formasSemParcelamento.includes(formaPagamento);
  const isSemCampoData = formasSemCampoData.includes(formaPagamento);
  const usaParcelamentoEditor = !isDataUnica && !isSemParcelamento;
  const valorTotalNum = parseFloat(valorTotal) || 0;

  async function salvarItem() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: msgSelecionePessoa }); return; }
    if (!descricao.trim()) { setMsg({ tipo: "erro", texto: msgDescricaoObrigatoria }); return; }
    if (!valorTotal || valorTotalNum <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor total." }); return; }
    if (usaParcelamentoEditor && !parcelas.length) { setMsg({ tipo: "erro", texto: "Gere as parcelas do pagamento." }); return; }
    if (isDataUnica && !dataPrimeiroPagamento) { setMsg({ tipo: "erro", texto: "Informe a data do pagamento." }); return; }
    if (validarExtra) {
      const erroExtra = validarExtra({ formaPagamento });
      if (erroExtra) { setMsg({ tipo: "erro", texto: erroExtra }); return; }
    }
    setSalvando(true);
    try {
      const parcelasPayload = isSemParcelamento
        ? undefined
        : isDataUnica
        ? [{ data_vencimento: dataPrimeiroPagamento, valor: valorTotalNum }]
        : parcelas.map((p) => ({ data_vencimento: p.data_vencimento, valor: parseFloat(p.valor) || 0 }));
      const texto = await salvar({ pessoaId, descricao: descricao.trim(), valorTotal, formaPagamento, parcelasPayload, observacao: observacao || "" });
      setMsg({ tipo: "sucesso", texto });
      setPessoaId(""); setDescricao(""); setValorTotal(""); setObservacao(""); setParcelas([]);
      resetExtra?.();
      recarregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar." });
    } finally {
      setSalvando(false);
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      <SecaoRecolhivel titulo={tituloNovo} icon={Plus} defaultAberta={false} descricao={descricaoNovo}>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label style={lbl}>{labelPessoa}</label>
            <select style={inputSm} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Selecione…</option>
              {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
          <div style={{ gridColumn: "span 2" }}>
            <label style={lbl}>Descrição</label>
            <input style={inputSm} value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder={placeholderDescricao} />
          </div>
          <div>
            <label style={lbl}>Valor total (R$)</label>
            <input type="number" step="0.01" style={inputSm} value={valorTotal} onChange={(e) => setValorTotal(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Forma de pagamento</label>
            <select style={inputSm} value={formaPagamento} onChange={(e) => { setFormaPagamento(e.target.value); setParcelas([]); }}>
              {formasPagamento.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
          </div>
          {!isSemCampoData && (
            <div>
              <label style={lbl}>{isDataUnica ? "Data do pagamento" : "Data do primeiro pagamento"}</label>
              <input type="date" style={inputSm} value={dataPrimeiroPagamento} onChange={(e) => setDataPrimeiroPagamento(e.target.value)} />
            </div>
          )}
        </div>

        {isDataUnica ? (
          <p className="mb-3" style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>
            {textoDataUnica ? textoDataUnica(valorTotalNum) : ""}
          </p>
        ) : isSemParcelamento ? (
          renderExtra
            ? renderExtra({ formaPagamento, valorTotal: valorTotalNum })
            : textoSemParcelamento && <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginBottom: "0.8rem" }}>{textoSemParcelamento}</p>
        ) : (
          <div className="mb-3">
            <ParcelamentoEditor
              valorTotal={valorTotalNum} frequencia={formaPagamento} primeiraData={dataPrimeiroPagamento}
              parcelas={parcelas} setParcelas={setParcelas}
            />
          </div>
        )}

        <div><label style={lbl}>Observação</label>
          <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvarItem} disabled={salvando}>
          {salvando ? "Salvando…" : labelSalvar}
        </button>
      </SecaoRecolhivel>

      <SecaoRecolhivel titulo={tituloVale} icon={Plus} defaultAberta={false} descricao={descricaoVale}>
        <ValeAvulsoSection
          origemTipo={valeOrigemTipo}
          origens={(itens ?? []).filter((i) => i.status !== valeStatusExcluido).map((i) => ({ id: i.id, label: `${i.pessoa_nome} — ${i.descricao}` }))}
          onLancado={recarregar}
        />
      </SecaoRecolhivel>

      <div className="card mt-4">
        <div className="card-header mb-3">{tituloListagem}</div>
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{textoVazioListagem}</p>}
        {itens && itens.map((item) => (
          <div key={item.id} style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.8rem", marginBottom: "0.8rem" }}>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <strong>{item.pessoa_nome}</strong> — {item.descricao}
                <span style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginLeft: "0.5rem" }}>({statusLabel(item.status)})</span>
              </div>
              <div className="flex items-center gap-2">
                <span style={{ fontWeight: 700 }}>{formatBRL(item.valor_total)}</span>
                {acaoItem?.(item)}
              </div>
            </div>
            {item.parcelas.length > 0 && (
              <>
                {onRedistribuirParcelas && item.parcelas.filter((p) => p.status !== "pago").length >= 2 && (
                  <button className="btn-ghost mt-2" style={{ fontSize: "0.72rem" }} disabled={redistribuindoId === item.id}
                    title="Redivide igualmente o valor pendente entre as parcelas ainda não pagas"
                    onClick={() => redistribuir(item.id)}>
                    <Shuffle size={12} /> {redistribuindoId === item.id ? "Redistribuindo…" : "Redistribuir parcelas pendentes"}
                  </button>
                )}
                <table className="fazenda-table" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
                  <thead><tr><th>Vencimento</th><th>Valor</th><th>Status</th>{onEditarParcela && <th>Ações</th>}</tr></thead>
                  <tbody>
                    {item.parcelas.map((p) => (
                      <Fragment key={p.id}>
                        <tr>
                          <td>{p.data_vencimento}</td><td>{formatBRL(p.valor)}</td><td>{p.status}</td>
                          {onEditarParcela && (
                            <td>
                              {p.status !== "pago" && (
                                <button className="btn-ghost" title="Editar esta parcela" style={{ fontSize: "0.72rem" }}
                                  onClick={() => iniciarEdicaoParcela(p)}>
                                  <Pencil size={12} />
                                </button>
                              )}
                            </td>
                          )}
                        </tr>
                        {editandoParcelaId === p.id && (
                          <tr>
                            <td colSpan={onEditarParcela ? 4 : 3} style={{ background: "var(--surface-2)", padding: "0.6rem" }}>
                              <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-2">
                                <div><label style={lbl}>Vencimento</label>
                                  <input type="date" style={inputSm} value={editParcelaData} onChange={(e) => setEditParcelaData(e.target.value)} /></div>
                                <div><label style={lbl}>Valor (R$)</label>
                                  <input type="number" step="0.01" style={inputSm} value={editParcelaValor} onChange={(e) => setEditParcelaValor(e.target.value)} /></div>
                              </div>
                              {parcelaMsg && <p style={{ color: "var(--red)", fontSize: "0.78rem", margin: "0 0 0.5rem" }}>{parcelaMsg}</p>}
                              <div style={{ display: "flex", gap: "0.5rem" }}>
                                <button className="btn-primary" style={{ fontSize: "0.75rem" }} disabled={salvandoParcela} onClick={() => salvarEdicaoParcela(p.id)}>
                                  {salvandoParcela ? "Salvando…" : "Salvar"}
                                </button>
                                <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => setEditandoParcelaId(null)}>Cancelar</button>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </>
            )}
            {renderItemExtra?.(item)}
            {item.vales.length > 0 && (
              <table className="fazenda-table" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
                <thead><tr><th>Vale</th><th>Data</th><th>Forma</th></tr></thead>
                <tbody>
                  {item.vales.map((v) => (
                    <tr key={v.id}><td>{formatBRL(v.valor)}</td><td>{v.data_pagamento}</td><td>{v.forma_pagamento}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
