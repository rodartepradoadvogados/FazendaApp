"use client";
import { useEffect, useState } from "react";
import { Package, Pencil, Check, X, AlertTriangle } from "lucide-react";
import { fetchItensEstoqueCadastro, atualizarMetaEstoque, fetchFornecedores } from "@/lib/api";

type Item = {
  id: number; nome: string; categoria: string | null; quantidade: number | null; unidade: string | null;
  ensacado: boolean | null; kg_por_saco: number | null; fornecedor_id: number | null;
};
type Fornecedor = { id: number; nome: string };

const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.3rem 0.5rem", fontSize: "0.78rem" };

export default function CadastroEstoqueMeta() {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | null>(null);
  const [ensacado, setEnsacado] = useState(false);
  const [kgPorSaco, setKgPorSaco] = useState("");
  const [fornecedorId, setFornecedorId] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = () => fetchItensEstoqueCadastro().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchFornecedores().then(setFornecedores).catch(() => {}); }, []);

  const abrirEdicao = (it: Item) => {
    setEditando(it.id); setEnsacado(!!it.ensacado); setKgPorSaco(it.kg_por_saco?.toString() ?? ""); setFornecedorId(it.fornecedor_id?.toString() ?? "");
  };

  const salvar = async (id: number) => {
    setSalvando(true);
    try {
      await atualizarMetaEstoque(id, {
        ensacado, kg_por_saco: kgPorSaco.trim() === "" ? null : Number(kgPorSaco),
        fornecedor_id: fornecedorId.trim() === "" ? null : Number(fornecedorId),
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
      <div className="card-header mb-3 flex items-center gap-2"><Package size={16} /> Itens de estoque — metadados</div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Marque quais itens são ensacados e quantos kg tem cada saco — a Alimentação usa isso para converter a
        necessidade calculada em número de sacos. Quantidade e movimentações continuam vindo do Estoque normalmente.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {itens && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Item</th><th>Categoria</th><th>Ensacado</th><th>Kg/saco</th><th>Fornecedor</th><th></th></tr></thead>
            <tbody>
              {itens.map((it) => (
                <tr key={it.id}>
                  <td style={{ fontWeight: 700 }}>{it.nome}</td>
                  <td style={{ fontSize: "0.78rem" }}>{it.categoria || "—"}</td>
                  {editando === it.id ? (
                    <>
                      <td><input type="checkbox" checked={ensacado} onChange={(e) => setEnsacado(e.target.checked)} /></td>
                      <td><input type="number" style={{ ...inputStyle, width: "5.5rem" }} value={kgPorSaco} onChange={(e) => setKgPorSaco(e.target.value)} disabled={!ensacado} /></td>
                      <td>
                        <select style={inputStyle} value={fornecedorId} onChange={(e) => setFornecedorId(e.target.value)}>
                          <option value="">—</option>
                          {fornecedores.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
                        </select>
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="btn-primary" style={{ fontSize: "0.72rem", padding: "0.25rem 0.5rem", marginRight: "0.3rem" }} onClick={() => salvar(it.id)} disabled={salvando}><Check size={13} /></button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", padding: "0.25rem 0.5rem" }} onClick={() => setEditando(null)}><X size={13} /></button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{it.ensacado ? "Sim" : "Não"}</td>
                      <td>{it.kg_por_saco ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{fornecedores.find((f) => f.id === it.fornecedor_id)?.nome || "—"}</td>
                      <td style={{ textAlign: "right" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(it)}>
                          <Pencil size={13} /> Editar
                        </button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
              {!itens.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum item de estoque cadastrado ainda — suba o ESTOQUE.csv primeiro.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
