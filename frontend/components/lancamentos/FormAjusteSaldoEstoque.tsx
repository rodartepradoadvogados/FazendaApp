"use client";
import React, { useEffect, useMemo, useState } from "react";
import { fetchPlanoContas, movimentarEstoque } from "@/lib/api";
import { EstoquePicker } from "@/components/EstoquePicker";
import { Campo, inputStyle, type EstoqueItem } from "@/components/lancamentos/comumForms";
import { UNIDADES } from "@/components/lancamentos/_shared";

/**
 * Ajuste de saldo atual: tela simplificada de contagem — o usuário informa
 * a quantidade REAL contada no estoque (não a diferença), e o sistema
 * compara com a quantidade cadastrada para descobrir sozinho se o ajuste é
 * entrada ou saída, reaproveitando os mesmos movimentos "Entrada de ajuste"
 * / "Saída de ajuste" já usados em Entradas/saídas.
 */
export function FormAjusteSaldoEstoque({ estoque }: { estoque: EstoqueItem[] }) {
  const [produto, setProduto] = useState("");
  const [qtdContada, setQtdContada] = useState("");
  const [unidade, setUnidade] = useState("");
  const [dataMov, setDataMov] = useState(() => new Date().toISOString().slice(0, 10));
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const [planoContas, setPlanoContas] = useState<{ codigo: string; nome: string }[]>([]);
  useEffect(() => { fetchPlanoContas().then(setPlanoContas).catch(() => {}); }, []);
  const nomeConta = (codigo: string | null | undefined) => (codigo ? planoContas.find((c) => c.codigo === codigo)?.nome || codigo : null);

  // Só faz sentido ajustar saldo de item que de fato controla quantidade.
  const itensEstocaveis = useMemo(() => estoque.filter((e) => e.estocavel !== false), [estoque]);
  const item = estoque.find((e) => e.nome === produto);

  // Ao trocar de produto, começa com a quantidade cadastrada (o usuário só
  // altera para o valor que contou de verdade) e a unidade padrão do item.
  useEffect(() => {
    if (!item) { setQtdContada(""); setUnidade(""); return; }
    setQtdContada(item.quantidade != null ? String(item.quantidade) : "");
    setUnidade(item.unidade || "");
  }, [produto]); // eslint-disable-line react-hooks/exhaustive-deps

  const atual = item?.quantidade ?? 0;
  const contada = qtdContada === "" ? null : Number(qtdContada);
  const delta = contada != null ? contada - atual : null;
  const ehEntrada = delta != null && delta > 0;
  const ehSaida = delta != null && delta < 0;

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!produto || contada == null || delta == null) { setErro("Selecione o produto e informe a quantidade contada."); return; }
    if (delta === 0) { setErro("A quantidade contada é igual ao saldo atual — não há ajuste a lançar."); return; }
    setSalvando(true);
    try {
      const r = await movimentarEstoque({
        nome: produto,
        movimento: ehEntrada ? "Entrada de ajuste" : "Saída de ajuste",
        quantidade: Math.abs(delta),
        unidade: unidade || item?.unidade || undefined,
        data_movimento: dataMov,
        observacao: observacao || undefined,
      });
      setSucesso(`Estoque de ${produto} ajustado: ${r.quantidade} ${r.unidade || ""}.`);
      setProduto(""); setQtdContada(""); setUnidade(""); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar ajuste de saldo");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Produto" full>
          <EstoquePicker itens={itensEstocaveis} value={produto} onChange={setProduto} placeholder="Buscar item…" incluirNaoEstocaveis={false} />
        </Campo>
        {item && (
          <>
            <Campo label="Categoria"><input readOnly disabled style={{ ...inputStyle, opacity: 0.75 }} value={item.categoria || "—"} /></Campo>
            {item.principio_ativo && (
              <Campo label="Princípio ativo"><input readOnly disabled style={{ ...inputStyle, opacity: 0.75 }} value={item.principio_ativo} /></Campo>
            )}
            <Campo label="Conta gerencial" full>
              <input readOnly disabled style={{ ...inputStyle, opacity: 0.75 }} value={nomeConta(item.conta_gerencial_despesa_padrao) || nomeConta(item.conta_gerencial_receita_padrao) || "—"} />
            </Campo>
            <Campo label="Quantidade contada agora">
              <input type="number" inputMode="decimal" style={inputStyle} value={qtdContada} onChange={(e) => setQtdContada(e.target.value)} />
            </Campo>
            <Campo label="Unidade">
              <select style={inputStyle} value={unidade || item.unidade || "unidade"} onChange={(e) => setUnidade(e.target.value)}>
                {UNIDADES.map((u) => <option key={u}>{u}</option>)}
              </select>
            </Campo>
            <Campo label="Data do ajuste"><input type="date" style={inputStyle} value={dataMov} onChange={(e) => setDataMov(e.target.value)} /></Campo>
            <Campo label="Observação" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
          </>
        )}
      </div>

      {item && contada != null && (
        <p style={{ fontSize: "0.85rem", marginTop: "0.6rem" }}>
          Saldo cadastrado: <strong>{atual} {item.unidade || ""}</strong> · Contado agora: <strong>{contada} {unidade || item.unidade || ""}</strong>
          {delta === 0 ? (
            <span style={{ color: "var(--text-muted)" }}> · sem alteração</span>
          ) : (
            <>
              {" · "}
              <strong style={{ color: ehEntrada ? "var(--green-light)" : "var(--red)" }}>
                {ehEntrada ? "Entrada" : "Saída"} de {Math.abs(delta as number)} {unidade || item.unidade || ""}
              </strong>
            </>
          )}
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando || !item || delta === 0}>{salvando ? "Salvando…" : "Salvar ajuste"}</button>
      </div>
    </>
  );
}
