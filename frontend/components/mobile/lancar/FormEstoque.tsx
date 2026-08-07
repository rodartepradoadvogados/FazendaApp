"use client";
// Sub-tela ESTOQUE: movimento de entrada ou saída de um item.
// Endpoint do desktop: POST /estoque/movimentar (usa os movimentos genéricos
// "Entrada de ajuste" / "Saída de ajuste"). Versão simples do formulário do
// site — busca + categoria para achar o item, entrada/saída, quantidade,
// valor opcional e "gerar lançamento financeiro" (abre a tela Financeiro já
// preenchida, faltando só pagamento/parcelamento).
import { useEffect, useMemo, useState } from "react";
import { Dna } from "lucide-react";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { CampoMoeda } from "@/components/CampoMoeda";
import { fetchEstoque, fetchPlanoContas, FINALIDADES_ESTOQUE } from "@/lib/api";
import { pedirLancamentoFinanceiro } from "@/lib/estoqueFinanceiroBridge";
import { EstoquePicker } from "@/components/EstoquePicker";
import { type EstoqueItem, useCache, useEnvio, hoje, MobPill, LinhaPills } from "./comum";
import { fetchComCache } from "@/lib/offline";

const MOVIMENTOS_ENTRADA = ["Entrada de ajuste", "Entrada de cortesia"];
const MOVIMENTOS_SAIDA = ["Aplicação", "Saída de ajuste", "Doação"];
const MOV_BAIXA = new Set(["Aplicação", "Saída de ajuste", "Doação"]);
const SOMENTE_ESTOCAVEL = new Set(["Doação", "Entrada de cortesia"]);

export function FormEstoque({ onIrParaFinanceiro }: { onIrParaFinanceiro?: (tipo: "despesa" | "receita") => void }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const estoque = useCache<EstoqueItem[]>("estoque_itens", () => fetchEstoque().then((d) => d.itens as EstoqueItem[]), []);

  const [somenteEstocaveis, setSomenteEstocaveis] = useState(true);
  const [fCategoria, setFCategoria] = useState("");
  const [fFinalidade, setFFinalidade] = useState("");
  const [fPrincipioAtivo, setFPrincipioAtivo] = useState("");
  const [fContaGerencial, setFContaGerencial] = useState("");
  const [planoContas, setPlanoContas] = useState<{ codigo: string; nome: string }[]>([]);
  useEffect(() => {
    fetchComCache<{ codigo: string; nome: string }[]>("plano_contas", () => fetchPlanoContas()).then(({ dados }) => setPlanoContas(dados || []));
  }, []);
  const nomeConta = (codigo: string) => planoContas.find((c) => c.codigo === codigo)?.nome || codigo;
  const [tipo, setTipo] = useState<"entrada" | "saida">("entrada");
  const [mov, setMov] = useState("");
  const [nome, setNome] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [data, setData] = useState(hoje());
  const [lancarValor, setLancarValor] = useState(false);
  const [valorUnitario, setValorUnitario] = useState("");
  const [gerarFinanceiro, setGerarFinanceiro] = useState(false);

  const itensBase = useMemo(() => somenteEstocaveis ? estoque.dados.filter((e) => e.estocavel !== false) : estoque.dados, [estoque.dados, somenteEstocaveis]);

  // Cada filtro se aplica sobre os outros (nunca sobre si mesmo) — as opções
  // de cada seletor também se restringem conforme os demais já escolhidos.
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

  const itens = useMemo(() => itensBase
    .filter((e) => passaFiltros(e))
    .sort((a, b) => a.nome.localeCompare(b.nome)), [itensBase, fCategoria, fFinalidade, fPrincipioAtivo, fContaGerencial]);

  const item = estoque.dados.find((e) => e.nome === nome);
  const unidade = item?.unidade || "";
  const q = Number(quantidade) || 0;
  const baixa = MOV_BAIXA.has(mov);
  const restante = item ? (item.quantidade ?? 0) + (baixa ? -q : q) : null;
  const valorTotal = lancarValor && valorUnitario ? q * Number(valorUnitario) : null;

  const movimentosDisponiveis = (tipo === "entrada" ? MOVIMENTOS_ENTRADA : MOVIMENTOS_SAIDA)
    .filter((m) => item?.estocavel !== false || !SOMENTE_ESTOCAVEL.has(m));

  function salvar() {
    if (!nome) return erroValidacao("Selecione o item.");
    if (!mov) return erroValidacao("Selecione o movimento.");
    if (!(q > 0)) return erroValidacao("Informe a quantidade.");
    enviar(
      "/estoque/movimentar",
      { nome, movimento: mov, quantidade: q, unidade: unidade || undefined, data_movimento: data },
      `Estoque ${tipo === "entrada" ? "entrada" : "saída"} — ${quantidade} ${unidade} de ${nome}`,
      () => {
        if (gerarFinanceiro) {
          pedirLancamentoFinanceiro({
            tipo: tipo === "entrada" ? "despesa" : "receita",
            produto: nome,
            quantidade: q,
            unidade: unidade || null,
            valor_unitario: lancarValor && valorUnitario ? Number(valorUnitario) : null,
            valor_total: valorTotal,
            codigo_conta_gerencial: (tipo === "entrada" ? item?.conta_gerencial_despesa_padrao : item?.conta_gerencial_receita_padrao) || null,
            data_emissao: data,
          });
          onIrParaFinanceiro?.(tipo === "entrada" ? "despesa" : "receita");
        }
        setQuantidade(""); setValorUnitario(""); setLancarValor(false); setGerarFinanceiro(false);
      },
    );
  }

  return (
    <>
      {categorias.length > 0 && (
        <MobCampo label="Categoria">
          <select className="mob-input" value={fCategoria} onChange={(e) => setFCategoria(e.target.value)}>
            <option value="">Todas</option>
            {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </MobCampo>
      )}
      {finalidades.length > 0 && (
        <MobCampo label="Medicamento / finalidade">
          <select className="mob-input" value={fFinalidade} onChange={(e) => setFFinalidade(e.target.value)}>
            <option value="">Todas</option>
            {finalidades.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </MobCampo>
      )}
      {principiosAtivos.length > 0 && (
        <MobCampo label="Princípio ativo">
          <select className="mob-input" value={fPrincipioAtivo} onChange={(e) => setFPrincipioAtivo(e.target.value)}>
            <option value="">Todos</option>
            {principiosAtivos.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </MobCampo>
      )}
      {contasUsadas.length > 0 && (
        <MobCampo label="Conta gerencial">
          <select className="mob-input" value={fContaGerencial} onChange={(e) => setFContaGerencial(e.target.value)}>
            <option value="">Todas</option>
            {contasUsadas.map((c) => <option key={c} value={c}>{nomeConta(c)}</option>)}
          </select>
        </MobCampo>
      )}
      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9rem", marginBottom: "0.7rem" }}>
        <input type="checkbox" checked={somenteEstocaveis} onChange={(e) => setSomenteEstocaveis(e.target.checked)} style={{ width: 18, height: 18 }} />
        Somente itens em estoque
      </label>

      <LinhaPills>
        <MobPill ativa={tipo === "entrada"} onClick={() => { setTipo("entrada"); setMov(""); }}>Entrada</MobPill>
        <MobPill ativa={tipo === "saida"} onClick={() => { setTipo("saida"); setMov(""); }}>Saída</MobPill>
      </LinhaPills>

      <MobCampo label="Item do estoque">
        <EstoquePicker itens={itens} value={nome} onChange={setNome} placeholder="Selecione o item…"
          finalidades={FINALIDADES_ESTOQUE} incluirNaoEstocaveis />
        {item?.estoque_semen_id != null && (
          <span style={{ fontSize: "0.72rem", color: "var(--mob-dourado-2)", display: "flex", alignItems: "center", gap: "0.25rem", marginTop: "0.3rem" }}>
            <Dna size={12} /> Vinculado ao Estoque de sêmen — este movimento também ajusta as doses do touro.
          </span>
        )}
      </MobCampo>
      <MobCampo label="Movimento">
        <select className="mob-input" value={mov} onChange={(e) => setMov(e.target.value)}>
          <option value="">Selecione…</option>
          {movimentosDisponiveis.map((m) => <option key={m}>{m}</option>)}
        </select>
      </MobCampo>
      <MobCampo label={`Quantidade${unidade ? ` (${unidade})` : ""}`}>
        <input type="number" inputMode="decimal" className="mob-input" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="0" />
      </MobCampo>
      <MobCampo label="Data">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>

      {item && mov && (
        <p style={{ fontSize: "0.82rem", margin: "0.3rem 0 0.8rem" }}>
          Saldo atual: <strong>{item.quantidade ?? 0} {unidade}</strong> → depois:{" "}
          <strong style={{ color: (restante ?? 0) < 0 ? "var(--mob-vermelho)" : "var(--mob-verde)" }}>{restante} {unidade}</strong>
          {(restante ?? 0) < 0 && <span style={{ color: "var(--mob-vermelho)" }}> (insuficiente!)</span>}
        </p>
      )}

      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9rem", marginBottom: "0.7rem" }}>
        <input type="checkbox" checked={lancarValor} onChange={(e) => setLancarValor(e.target.checked)} style={{ width: 18, height: 18 }} />
        Informar valor deste movimento
      </label>
      {lancarValor && (
        <MobCampo label="Valor unitário (R$)">
          <CampoMoeda className="mob-input" value={Number(valorUnitario) || 0} onChange={(v) => setValorUnitario(v ? String(v) : "")} />
        </MobCampo>
      )}
      {valorTotal != null && (
        <p style={{ fontSize: "0.82rem", marginBottom: "0.5rem" }}>Valor do movimento: <strong>{valorTotal.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}</strong></p>
      )}
      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9rem", marginBottom: "0.9rem" }}>
        <input type="checkbox" checked={gerarFinanceiro} onChange={(e) => setGerarFinanceiro(e.target.checked)} style={{ width: 18, height: 18 }} />
        Gerar {tipo === "saida" ? "receita" : "despesa"} no Financeiro com estes dados
      </label>

      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
