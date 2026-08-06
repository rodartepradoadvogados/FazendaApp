"use client";
import { useEffect, useState } from "react";
import { Package, Pencil, Trash2, AlertTriangle, Plus, Search } from "lucide-react";
import { fetchItensEstoqueCadastro, fetchFornecedores, fetchPlanoContas, excluirItemEstoque } from "@/lib/api";
import NovoItemEstoque, { type ItemEstoqueEditando } from "./NovoItemEstoque";
import { Modal } from "./Modal";
import { onPedidoCadastroDeEstoque, type PrefillNovoEstoque } from "@/lib/alimentoEstoqueBridge";
import { ThOrdenavel, useOrdenacao } from "./Ordenavel";

// Item vindo de GET /cadastro/estoque-itens — na prática o model_dump()
// completo de Estoque + fornecedor_nome (ver ItemEstoqueEditando), mas só os
// campos usados nesta listagem estão tipados aqui.
type Item = {
  id: number; nome: string; categoria: string | null; quantidade: number | null; unidade: string | null;
  unidade_embalagem: string | null; medida_embalagem: string | null; quantidade_embalagem: number | null;
  fornecedor_id: number | null; fornecedor_nome: string | null;
  ativo: boolean | null; estocavel: boolean | null;
  conta_gerencial_despesa_padrao: string | null;
} & Record<string, any>;
type Fornecedor = { id: number; nome: string };
type Conta = { codigo: string; nome: string };

// RMCA físico (Financeiro) entra automaticamente para todo item vinculado à
// conta "3.01.01 Alimentação do rebanho" (ou qualquer conta registrada
// dentro dela) — não é mais uma marcação manual por item.
const entraNoRmca = (it: Item) => (it.conta_gerencial_despesa_padrao || "").startsWith("3.01.01");

const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

// Normaliza texto para busca insensível a maiúsculas e acentos.
const normalizar = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

export default function CadastroEstoqueMeta() {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [contas, setContas] = useState<Conta[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Edição abre o MESMO formulário completo do "+ Novo item" (NovoItemEstoque),
  // num modal — antes era uma edição inline na própria linha da tabela,
  // limitada a só 6 dos ~25 campos do item (unidade de embalagem, unidade de
  // medida, quantidade por embalagem, fornecedor, conta gerencial, estocável).
  const [editando, setEditando] = useState<ItemEstoqueEditando | null>(null);
  const [novoAberto, setNovoAberto] = useState(false);
  const [prefillNovo, setPrefillNovo] = useState<PrefillNovoEstoque | null>(null);
  const [busca, setBusca] = useState("");
  const [erroExclusao, setErroExclusao] = useState<string | null>(null);

  const carregar = () => fetchItensEstoqueCadastro().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchFornecedores().then(setFornecedores).catch(() => {});
    fetchPlanoContas().then(setContas).catch(() => {});
  }, []);
  useEffect(() => onPedidoCadastroDeEstoque((dados) => { setPrefillNovo(dados); setNovoAberto(true); }), []);

  const excluir = async (it: Item) => {
    if (!window.confirm(`Excluir o item de estoque "${it.nome}"? Isso não pode ser desfeito.`)) return;
    setErroExclusao(null);
    try {
      await excluirItemEstoque(it.id);
      await carregar();
    } catch (e: any) {
      setErroExclusao(e.message || "Erro ao excluir item de estoque");
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
      {erroExclusao && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>{erroExclusao}</span></div>}
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
                  <td style={{ fontSize: "0.78rem" }}>{it.unidade_embalagem ?? "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{it.medida_embalagem ?? "—"}</td>
                  <td>{it.quantidade_embalagem ?? "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{it.fornecedor_nome || fornecedores.find((f) => f.id === it.fornecedor_id)?.nome || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{nomeConta(it.conta_gerencial_despesa_padrao)}</td>
                  <td>{it.estocavel === false ? "Não" : "Sim"}</td>
                  <td>{entraNoRmca(it) ? "Sim" : "Não"}</td>
                  <td style={{ textAlign: "right" }}>
                    <div className="flex items-center justify-end gap-2">
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setEditando(it)}>
                        <Pencil size={13} /> Editar
                      </button>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--red)" }} onClick={() => excluir(it)}>
                        <Trash2 size={13} /> Excluir
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!itens.length && <tr><td colSpan={10} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum item de estoque cadastrado ainda — suba o ESTOQUE.csv primeiro.</td></tr>}
              {!!itens.length && !filtrados.length && <tr><td colSpan={10} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
      )}

      {editando && (
        <Modal title={`Editar item — ${editando.nome}`} onClose={() => setEditando(null)} width="960px">
          <NovoItemEstoque
            editando={editando}
            onCriado={() => { setEditando(null); carregar(); }}
            onCancelar={() => setEditando(null)}
          />
        </Modal>
      )}
    </div>
  );
}
