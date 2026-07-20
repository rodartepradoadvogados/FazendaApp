"use client";
import { useEffect, useState } from "react";
import { Package, Pencil, Check, X, AlertTriangle, Plus, Search } from "lucide-react";
import { fetchItensEstoqueCadastro, atualizarMetaEstoque, fetchFornecedores, fetchPlanoContas } from "@/lib/api";
import NovoItemEstoque from "./NovoItemEstoque";
import { onPedidoCadastroDeEstoque, type PrefillNovoEstoque } from "@/lib/alimentoEstoqueBridge";
import { ThOrdenavel, useOrdenacao } from "./Ordenavel";

const UNIDADES_EMBALAGEM = ["Saca", "Pote", "Frasco", "Pacote", "Bag", "Fardo", "Garrafa", "Unidade"];
const MEDIDAS_EMBALAGEM = ["kg/saca", "litros/garrafa", "mililitros/frasco", "unidades/fardo", "potes/caixa", "unidades"];

type Item = {
  id: number; nome: string; categoria: string | null; quantidade: number | null; unidade: string | null;
  unidade_embalagem: string | null; medida_embalagem: string | null; quantidade_embalagem: number | null;
  fornecedor_id: number | null; fornecedor_nome: string | null;
  ativo: boolean | null; estocavel: boolean | null;
  conta_gerencial_despesa_padrao: string | null;
};
type Fornecedor = { id: number; nome: string };
type Conta = { codigo: string; nome: string };

// RMCA físico (Financeiro) entra automaticamente para todo item vinculado à
// conta "3.01.01 Alimentação do rebanho" (ou qualquer conta registrada
// dentro dela) — não é mais uma marcação manual por item.
const entraNoRmca = (it: Item) => (it.conta_gerencial_despesa_padrao || "").startsWith("3.01.01");

const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.3rem 0.5rem", fontSize: "0.78rem" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

// Normaliza texto para busca insensível a maiúsculas e acentos.
const normalizar = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

export default function CadastroEstoqueMeta() {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [contas, setContas] = useState<Conta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | null>(null);
  const [unidadeEmbalagem, setUnidadeEmbalagem] = useState("");
  const [medidaEmbalagem, setMedidaEmbalagem] = useState("");
  const [quantidadeEmbalagem, setQuantidadeEmbalagem] = useState("");
  const [fornecedorId, setFornecedorId] = useState("");
  const [contaGerencial, setContaGerencial] = useState("");
  const [estocavel, setEstocavel] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [novoAberto, setNovoAberto] = useState(false);
  const [prefillNovo, setPrefillNovo] = useState<PrefillNovoEstoque | null>(null);
  const [busca, setBusca] = useState("");

  const carregar = () => fetchItensEstoqueCadastro().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchFornecedores().then(setFornecedores).catch(() => {});
    fetchPlanoContas().then(setContas).catch(() => {});
  }, []);
  useEffect(() => onPedidoCadastroDeEstoque((dados) => { setPrefillNovo(dados); setNovoAberto(true); }), []);

  const abrirEdicao = (it: Item) => {
    setEditando(it.id);
    setUnidadeEmbalagem(it.unidade_embalagem ?? "");
    setMedidaEmbalagem(it.medida_embalagem ?? "");
    setQuantidadeEmbalagem(it.quantidade_embalagem?.toString() ?? "");
    setFornecedorId(it.fornecedor_id?.toString() ?? "");
    setContaGerencial(it.conta_gerencial_despesa_padrao ?? "");
    setEstocavel(it.estocavel !== false);
  };

  const salvar = async (id: number) => {
    setSalvando(true);
    try {
      await atualizarMetaEstoque(id, {
        unidade_embalagem: unidadeEmbalagem.trim() === "" ? null : unidadeEmbalagem,
        medida_embalagem: medidaEmbalagem.trim() === "" ? null : medidaEmbalagem,
        quantidade_embalagem: quantidadeEmbalagem.trim() === "" ? null : Number(quantidadeEmbalagem),
        fornecedor_id: fornecedorId.trim() === "" ? null : Number(fornecedorId),
        conta_gerencial_despesa_padrao: contaGerencial.trim() === "" ? null : contaGerencial,
        estocavel,
      });
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSalvando(false);
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((it) => {
    const fornecedorNome = it.fornecedor_nome || fornecedores.find((f) => f.id === it.fornecedor_id)?.nome || "";
    return !termoBusca || normalizar(`${it.nome} ${it.categoria ?? ""} ${fornecedorNome}`).includes(termoBusca);
  });
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(filtrados);
  const nomeConta = (codigo: string | null) => {
    if (!codigo) return "—";
    const conta = contas.find((c) => c.codigo === codigo);
    return conta ? `${conta.codigo} — ${conta.nome}` : codigo;
  };

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Package size={16} /> Itens de estoque</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
          onClick={() => setNovoAberto((v) => !v)}>
          <Plus size={14} /> Novo item
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Informe a unidade de embalagem (saca, pote, garrafa…), a unidade de medida e a quantidade por embalagem de
        cada item — a Alimentação usa isso para converter a necessidade calculada em número de embalagens a comprar.
        Itens vindos de upload de CSV também aparecem aqui. A coluna Conta Gerencial mostra a conta padrão de despesa
        do item; a coluna RMCA é automática — entram no custo físico do indicador RMCA (Financeiro) todos os itens
        vinculados à conta "3.01.01 Alimentação do rebanho" (ou a qualquer conta dentro dela) que tiverem baixa de
        "Saída de ajuste".
      </p>

      {novoAberto && (
        <NovoItemEstoque
          prefill={prefillNovo}
          onCriado={() => { setNovoAberto(false); setPrefillNovo(null); carregar(); }}
          onCancelar={() => { setNovoAberto(false); setPrefillNovo(null); }}
        />
      )}

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar item de estoque…" title="Buscar por item, categoria ou fornecedor" />
          </div>
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <ThOrdenavel label="Item" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Categoria" campo="categoria" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Unidade" campo="unidade_embalagem" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Unidade de medida" campo="medida_embalagem" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Quantidade" campo="quantidade_embalagem" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Fornecedor principal" campo="fornecedor_nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Conta gerencial" campo="conta_gerencial_despesa_padrao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Estocável" campo="estocavel" coluna={coluna} dir={dir} ordenar={ordenar} />
                <th title='Entra no custo físico do RMCA quando a conta gerencial é "3.01.01 Alimentação do rebanho" (ou dentro dela) e tem baixa de Saída de ajuste'>RMCA</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {linhasOrdenadas.map((it) => (
                <tr key={it.id}>
                  <td style={{ fontWeight: 700 }}>{it.nome}{it.ativo === false && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                  <td style={{ fontSize: "0.78rem" }}>{it.categoria || "—"}</td>
                  {editando === it.id ? (
                    <>
                      <td>
                        <select style={inputStyle} value={unidadeEmbalagem} onChange={(e) => setUnidadeEmbalagem(e.target.value)}>
                          <option value="">—</option>
                          {UNIDADES_EMBALAGEM.map((u) => <option key={u} value={u}>{u}</option>)}
                        </select>
                      </td>
                      <td>
                        <select style={inputStyle} value={medidaEmbalagem} onChange={(e) => setMedidaEmbalagem(e.target.value)}>
                          <option value="">—</option>
                          {MEDIDAS_EMBALAGEM.map((m) => <option key={m} value={m}>{m}</option>)}
                        </select>
                      </td>
                      <td><input type="number" style={{ ...inputStyle, width: "5.5rem" }} value={quantidadeEmbalagem} onChange={(e) => setQuantidadeEmbalagem(e.target.value)} /></td>
                      <td>
                        <select style={inputStyle} value={fornecedorId} onChange={(e) => setFornecedorId(e.target.value)}>
                          <option value="">—</option>
                          {fornecedores.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
                        </select>
                      </td>
                      <td>
                        <select style={inputStyle} value={contaGerencial} onChange={(e) => setContaGerencial(e.target.value)}>
                          <option value="">—</option>
                          {contas.map((c) => <option key={c.codigo} value={c.codigo}>{`${c.codigo} — ${c.nome}`}</option>)}
                        </select>
                      </td>
                      <td><input type="checkbox" checked={estocavel} onChange={(e) => setEstocavel(e.target.checked)} /></td>
                      <td>{entraNoRmca(it) ? "Sim" : "Não"}</td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        {unidadeEmbalagem === "Saca" && (medidaEmbalagem !== "kg/saca" || quantidadeEmbalagem.trim() === "") && (
                          <span title="Para contar como ensacado na Alimentação, preencha também &quot;kg/saca&quot; e a quantidade por saca." style={{ marginRight: "0.4rem", display: "inline-flex", verticalAlign: "middle", color: "var(--warning, #d97706)" }}>
                            <AlertTriangle size={14} />
                          </span>
                        )}
                        <button className="btn-primary" style={{ fontSize: "0.72rem", padding: "0.25rem 0.5rem", marginRight: "0.3rem" }} onClick={() => salvar(it.id)} disabled={salvando}><Check size={13} /></button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", padding: "0.25rem 0.5rem" }} onClick={() => setEditando(null)}><X size={13} /></button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td style={{ fontSize: "0.78rem" }}>{it.unidade_embalagem ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{it.medida_embalagem ?? "—"}</td>
                      <td>{it.quantidade_embalagem ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{it.fornecedor_nome || fornecedores.find((f) => f.id === it.fornecedor_id)?.nome || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{nomeConta(it.conta_gerencial_despesa_padrao)}</td>
                      <td>{it.estocavel === false ? "Não" : "Sim"}</td>
                      <td>{entraNoRmca(it) ? "Sim" : "Não"}</td>
                      <td style={{ textAlign: "right" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(it)}>
                          <Pencil size={13} /> Editar
                        </button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
              {!itens.length && <tr><td colSpan={10} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum item de estoque cadastrado ainda — suba o ESTOQUE.csv primeiro.</td></tr>}
              {!!itens.length && !filtrados.length && <tr><td colSpan={10} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
      )}
    </div>
  );
}
