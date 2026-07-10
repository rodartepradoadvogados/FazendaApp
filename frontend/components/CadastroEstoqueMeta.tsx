"use client";
import { useEffect, useState } from "react";
import { Package, Pencil, Check, X, AlertTriangle, Plus } from "lucide-react";
import { fetchItensEstoqueCadastro, atualizarMetaEstoque, fetchFornecedores } from "@/lib/api";
import NovoItemEstoque from "./NovoItemEstoque";

const UNIDADES_EMBALAGEM = ["Saca", "Pote", "Frasco", "Pacote", "Bag", "Fardo", "Garrafa", "Unidade"];
const MEDIDAS_EMBALAGEM = ["kg/saca", "litros/garrafa", "mililitros/frasco", "unidades/fardo", "potes/caixa", "unidades"];

type Item = {
  id: number; nome: string; categoria: string | null; quantidade: number | null; unidade: string | null;
  unidade_embalagem: string | null; medida_embalagem: string | null; quantidade_embalagem: number | null;
  fornecedor_id: number | null; fornecedor_nome: string | null;
  ativo: boolean | null; estocavel: boolean | null;
};
type Fornecedor = { id: number; nome: string };

const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.3rem 0.5rem", fontSize: "0.78rem" };

export default function CadastroEstoqueMeta() {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | null>(null);
  const [unidadeEmbalagem, setUnidadeEmbalagem] = useState("");
  const [medidaEmbalagem, setMedidaEmbalagem] = useState("");
  const [quantidadeEmbalagem, setQuantidadeEmbalagem] = useState("");
  const [fornecedorId, setFornecedorId] = useState("");
  const [estocavel, setEstocavel] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [novoAberto, setNovoAberto] = useState(false);

  const carregar = () => fetchItensEstoqueCadastro().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchFornecedores().then(setFornecedores).catch(() => {}); }, []);

  const abrirEdicao = (it: Item) => {
    setEditando(it.id);
    setUnidadeEmbalagem(it.unidade_embalagem ?? "");
    setMedidaEmbalagem(it.medida_embalagem ?? "");
    setQuantidadeEmbalagem(it.quantidade_embalagem?.toString() ?? "");
    setFornecedorId(it.fornecedor_id?.toString() ?? "");
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
        Itens vindos de upload de CSV também aparecem aqui.
      </p>

      {novoAberto && <NovoItemEstoque onCriado={() => { setNovoAberto(false); carregar(); }} onCancelar={() => setNovoAberto(false)} />}

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {itens && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Item</th><th>Categoria</th><th>Unidade</th><th>Unidade de medida</th><th>Quantidade</th><th>Fornecedor principal</th><th>Estocável</th><th></th></tr></thead>
            <tbody>
              {itens.map((it) => (
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
                      <td><input type="checkbox" checked={estocavel} onChange={(e) => setEstocavel(e.target.checked)} /></td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
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
                      <td>{it.estocavel === false ? "Não" : "Sim"}</td>
                      <td style={{ textAlign: "right" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(it)}>
                          <Pencil size={13} /> Editar
                        </button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
              {!itens.length && <tr><td colSpan={8} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum item de estoque cadastrado ainda — suba o ESTOQUE.csv primeiro.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
