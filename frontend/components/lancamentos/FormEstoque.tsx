"use client";
import React, { useEffect, useMemo, useState } from "react";
import { Dna } from "lucide-react";
import { fetchPedido, fetchPedidos, fetchPlanoContas, movimentarEstoque, FINALIDADES_ESTOQUE } from "@/lib/api";
import { pedirLancamentoFinanceiro } from "@/lib/estoqueFinanceiroBridge";
import { EstoquePicker } from "@/components/EstoquePicker";
import { Campo, inputStyle, type EstoqueItem } from "@/components/lancamentos/comumForms";
import { UNIDADES } from "@/components/lancamentos/_shared";

const MOVIMENTOS_ESTOQUE = ["Aplicação", "Saída de ajuste", "Entrada de ajuste", "Entrada de cortesia", "Doação"];
// Movimentos que reduzem o estoque (baixa).
const MOV_BAIXA = new Set(["Aplicação", "Saída de ajuste", "Doação"]);
const MOVIMENTOS_SOMENTE_ESTOCAVEL = new Set(["Doação", "Entrada de cortesia"]);

const MOVIMENTOS_SAIDA = MOVIMENTOS_ESTOQUE.filter((m) => MOV_BAIXA.has(m));
const MOVIMENTOS_ENTRADA = MOVIMENTOS_ESTOQUE.filter((m) => !MOV_BAIXA.has(m));

export function FormEstoque({ estoque, onIrParaFinanceiro }: { estoque: EstoqueItem[]; onIrParaFinanceiro?: (leaf: "financeiro_despesa" | "financeiro_receita") => void }) {
  const [produto, setProduto] = useState("");
  const [tipo, setTipo] = useState<"entrada" | "saida" | "">("");
  const [mov, setMov] = useState("");
  const [qtd, setQtd] = useState("");
  const [unidade, setUnidade] = useState("");
  const [dataMov, setDataMov] = useState(() => new Date().toISOString().slice(0, 10));
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Filtros para achar o produto certo mais rápido. Por padrão só mostra
  // itens estocáveis (itens não estocáveis existem só para lançamento
  // financeiro, sem controle de quantidade) — "Somente itens em estoque"
  // deixa de ser um filtro fixo e vira uma opção que dá para desmarcar.
  const [busca, setBusca] = useState("");
  const [somenteEstocaveis, setSomenteEstocaveis] = useState(true);
  const [fCategoria, setFCategoria] = useState("");
  const [fFinalidade, setFFinalidade] = useState("");
  const [fPrincipioAtivo, setFPrincipioAtivo] = useState("");
  const [fContaGerencial, setFContaGerencial] = useState("");
  const [planoContas, setPlanoContas] = useState<{ codigo: string; nome: string }[]>([]);
  useEffect(() => { fetchPlanoContas().then(setPlanoContas).catch(() => {}); }, []);

  const itensBase = useMemo(() => somenteEstocaveis ? estoque.filter((e) => e.estocavel !== false) : estoque, [estoque, somenteEstocaveis]);
  const nomeConta = (codigo: string) => planoContas.find((c) => c.codigo === codigo)?.nome || codigo;

  // Cada filtro se aplica sobre os outros três (nunca sobre si mesmo) — assim
  // as OPÇÕES de cada seletor também se restringem conforme os demais já
  // escolhidos ("os filtros se comunicam"), não só a lista final de itens.
  const passaFiltros = (e: EstoqueItem, exceto?: keyof EstoqueItem) =>
    (exceto === "categoria" || !fCategoria || e.categoria === fCategoria) &&
    (exceto === "finalidade" || !fFinalidade || e.finalidade === fFinalidade) &&
    (exceto === "principio_ativo" || !fPrincipioAtivo || e.principio_ativo === fPrincipioAtivo) &&
    (exceto === "conta_gerencial_despesa_padrao" || !fContaGerencial || e.conta_gerencial_despesa_padrao === fContaGerencial);

  const opcoesPara = (campo: keyof EstoqueItem) =>
    Array.from(new Set(itensBase.filter((e) => passaFiltros(e, campo)).map((e) => e[campo]).filter(Boolean))).sort() as string[];

  const categorias = useMemo(() => opcoesPara("categoria"), [itensBase, fFinalidade, fPrincipioAtivo, fContaGerencial]);
  const finalidades = useMemo(() => opcoesPara("finalidade"), [itensBase, fCategoria, fPrincipioAtivo, fContaGerencial]);
  const principiosAtivos = useMemo(() => opcoesPara("principio_ativo"), [itensBase, fCategoria, fFinalidade, fContaGerencial]);
  const contasUsadas = useMemo(() => opcoesPara("conta_gerencial_despesa_padrao"), [itensBase, fCategoria, fFinalidade, fPrincipioAtivo]);

  const itensFiltrados = useMemo(() => itensBase.filter((e) =>
    passaFiltros(e) && (!busca.trim() || e.nome.toLowerCase().includes(busca.trim().toLowerCase()))
  ), [itensBase, fCategoria, fFinalidade, fPrincipioAtivo, fContaGerencial, busca]);

  // Vínculo opcional a um item de Pedido de compra — só entrada de estoque faz
  // sentido vincular (uma saída não "atende" um pedido de compra). É só a
  // partir deste vínculo que o pedido passa a refletir aqui em Estoque.
  const [pedidosCompra, setPedidosCompra] = useState<{ id: number; numero_pedido: string; fornecedor_cliente: string | null }[]>([]);
  const [pedidoId, setPedidoId] = useState("");
  const [itensPedido, setItensPedido] = useState<{ id: number; produto_servico: string }[]>([]);
  const [pedidoItemId, setPedidoItemId] = useState("");

  useEffect(() => {
    if (tipo !== "entrada") return;
    fetchPedidos({ tipo: "compra" })
      .then((lista: any[]) => setPedidosCompra(lista.filter((p) => p.status !== "cancelado" && p.status !== "atendido")))
      .catch(() => {});
  }, [tipo]);
  useEffect(() => {
    if (!pedidoId) { setItensPedido([]); setPedidoItemId(""); return; }
    fetchPedido(Number(pedidoId)).then((p: any) => setItensPedido(p.itens || [])).catch(() => {});
  }, [pedidoId]);

  // Valor do movimento (opcional) e gerar lançamento financeiro a partir dele.
  const [lancarValor, setLancarValor] = useState(false);
  const [valorUnitario, setValorUnitario] = useState("");
  const [gerarFinanceiro, setGerarFinanceiro] = useState(false);

  const item = estoque.find((e) => e.nome === produto);
  const q = Number(qtd) || 0;
  const baixa = MOV_BAIXA.has(mov);
  const restante = item ? (item.quantidade ?? 0) + (baixa ? -q : q) : null;
  const valorTotalCalc = lancarValor && valorUnitario ? q * Number(valorUnitario) : null;

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!produto || !tipo || !mov || !q) { setErro("Selecione o produto, o tipo de movimento e a quantidade."); return; }
    setSalvando(true);
    try {
      const r = await movimentarEstoque({
        nome: produto, movimento: mov, quantidade: q, unidade: unidade || item?.unidade || undefined, data_movimento: dataMov, observacao: observacao || undefined,
        pedido_id: tipo === "entrada" && pedidoId ? Number(pedidoId) : null,
        pedido_item_id: tipo === "entrada" && pedidoItemId ? Number(pedidoItemId) : null,
      });
      setSucesso(`Estoque de ${produto} atualizado: ${r.quantidade} ${r.unidade || ""}.`);
      if (gerarFinanceiro) {
        pedirLancamentoFinanceiro({
          tipo: tipo === "entrada" ? "despesa" : "receita",
          produto,
          quantidade: q,
          unidade: unidade || item?.unidade || null,
          valor_unitario: lancarValor && valorUnitario ? Number(valorUnitario) : null,
          valor_total: valorTotalCalc,
          codigo_conta_gerencial: (tipo === "entrada" ? item?.conta_gerencial_despesa_padrao : item?.conta_gerencial_receita_padrao) || null,
          data_emissao: dataMov,
          observacao: observacao || undefined,
        });
        onIrParaFinanceiro?.(tipo === "entrada" ? "financeiro_despesa" : "financeiro_receita");
      }
      setMov(""); setQtd(""); setObservacao(""); setPedidoId(""); setPedidoItemId("");
      setLancarValor(false); setValorUnitario(""); setGerarFinanceiro(false);
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar movimento de estoque");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
        <Campo label="Categoria">
          <select style={inputStyle} value={fCategoria} onChange={(e) => setFCategoria(e.target.value)}>
            <option value="">Todas</option>
            {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </Campo>
        <Campo label="Medicamento / finalidade">
          <select style={inputStyle} value={fFinalidade} onChange={(e) => setFFinalidade(e.target.value)}>
            <option value="">Todas</option>
            {finalidades.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </Campo>
        <Campo label="Princípio ativo">
          <select style={inputStyle} value={fPrincipioAtivo} onChange={(e) => setFPrincipioAtivo(e.target.value)}>
            <option value="">Todos</option>
            {principiosAtivos.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Campo>
        <Campo label="Conta gerencial">
          <select style={inputStyle} value={fContaGerencial} onChange={(e) => setFContaGerencial(e.target.value)}>
            <option value="">Todas</option>
            {contasUsadas.map((c) => <option key={c} value={c}>{nomeConta(c)}</option>)}
          </select>
        </Campo>
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", marginBottom: "0.9rem", cursor: "pointer" }}>
        <input type="checkbox" checked={somenteEstocaveis} onChange={(e) => setSomenteEstocaveis(e.target.checked)} /> Somente itens em estoque
      </label>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Buscar / selecionar item">
          <EstoquePicker
            itens={itensFiltrados}
            value={produto}
            onChange={setProduto}
            placeholder="Buscar item…"
            finalidades={FINALIDADES_ESTOQUE}
            incluirNaoEstocaveis={!somenteEstocaveis}
          />
          {itensFiltrados.length !== itensBase.length && (
            <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{itensFiltrados.length} de {itensBase.length} itens no filtro atual</span>
          )}
          {item?.estoque_semen_id != null && (
            <span style={{ fontSize: "0.68rem", color: "var(--dourado-light)", display: "flex", alignItems: "center", gap: "0.25rem", marginTop: "0.2rem" }}>
              <Dna size={11} /> Vinculado ao Estoque de sêmen — este movimento também ajusta as doses do touro.
            </span>
          )}
        </Campo>
        <Campo label="Tipo de movimento">
          <select style={inputStyle} value={tipo} onChange={(e) => { setTipo(e.target.value as any); setMov(""); }}>
            <option value="" disabled>Selecione…</option>
            <option value="entrada">Entrada</option>
            <option value="saida">Saída</option>
          </select>
        </Campo>
        <Campo label="Movimento">
          <select style={inputStyle} value={mov} onChange={(e) => setMov(e.target.value)} disabled={!tipo}>
            <option value="" disabled>{tipo ? "Selecione…" : "Escolha o tipo primeiro"}</option>
            {(tipo === "entrada" ? MOVIMENTOS_ENTRADA : tipo === "saida" ? MOVIMENTOS_SAIDA : [])
              .filter((m) => item?.estocavel !== false || !MOVIMENTOS_SOMENTE_ESTOCAVEL.has(m))
              .map((m) => <option key={m}>{m}</option>)}
          </select>
        </Campo>
        <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={qtd} onChange={(e) => setQtd(e.target.value)} /></Campo>
        <Campo label="Unidade">
          <select style={inputStyle} value={unidade || item?.unidade || "unidade"} onChange={(e) => setUnidade(e.target.value)}>
            {UNIDADES.map((u) => <option key={u}>{u}</option>)}
          </select>
        </Campo>
        <Campo label="Data"><input type="date" style={inputStyle} value={dataMov} onChange={(e) => setDataMov(e.target.value)} /></Campo>
        {tipo === "entrada" && (
          <>
            <Campo label="Vincular a um pedido de compra (opcional)">
              <select style={inputStyle} value={pedidoId} onChange={(e) => { setPedidoId(e.target.value); setPedidoItemId(""); }}>
                <option value="">— Nenhum —</option>
                {pedidosCompra.map((p) => <option key={p.id} value={p.id}>{p.numero_pedido} — {p.fornecedor_cliente || "sem contraparte"}</option>)}
              </select>
            </Campo>
            {pedidoId && (
              <Campo label="Item do pedido">
                <select style={inputStyle} value={pedidoItemId} onChange={(e) => setPedidoItemId(e.target.value)}>
                  <option value="">— Nenhum —</option>
                  {itensPedido.map((i) => <option key={i.id} value={i.id}>{i.produto_servico}</option>)}
                </select>
                <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginTop: "0.2rem" }}>
                  É só a partir deste vínculo que o pedido passa a refletir aqui em Estoque.
                </span>
              </Campo>
            )}
          </>
        )}
        <Campo label="Lançar valor deste movimento?">
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem" }}>
            <input type="checkbox" checked={lancarValor} onChange={(e) => setLancarValor(e.target.checked)} /> Informar valor unitário
          </label>
        </Campo>
        {lancarValor && (
          <Campo label="Valor unitário (R$)">
            <input type="number" inputMode="decimal" style={inputStyle} value={valorUnitario} onChange={(e) => setValorUnitario(e.target.value)} />
          </Campo>
        )}
        <Campo label="Gerar movimentação financeira?" full>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem" }}>
            <input type="checkbox" checked={gerarFinanceiro} onChange={(e) => setGerarFinanceiro(e.target.checked)} />
            Ao salvar, abrir um lançamento de {tipo === "saida" ? "receita (Contas a receber)" : "despesa (Contas a pagar)"} já com produto, quantidade e valor deste balanço
          </label>
        </Campo>
        <Campo label="Observação" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>
      {item && mov && (
        <p style={{ fontSize: "0.78rem", marginTop: "0.3rem" }}>
          {baixa ? "Baixa" : "Entrada"} · Estoque atual: <strong>{item.quantidade ?? 0} {item.unidade || ""}</strong> → depois:{" "}
          <strong style={{ color: (restante ?? 0) < 0 ? "var(--red)" : "var(--green-light)" }}>{restante} {item.unidade || ""}</strong>
          {(restante ?? 0) < 0 && <span style={{ color: "var(--red)" }}> (insuficiente!)</span>}
          {valorTotalCalc != null && <> · Valor do movimento: <strong>{valorTotalCalc.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}</strong></>}
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}
