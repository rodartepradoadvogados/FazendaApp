"use client";
import { Fragment, useEffect, useState } from "react";
import { Plus, Pencil, Trash2, AlertTriangle, Check, X } from "lucide-react";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import type { ItemCadastroSimples } from "@/lib/api";

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

type Form = { nome: string; ativo: boolean };
const formVazio: Form = { nome: "", ativo: true };

/**
 * Lista genérica "nome + ativo" com criar/editar/desativar (e, quando
 * `excluirFn` é passado, excluir de fato) — mesmo padrão de CadastroRacas.tsx,
 * reusado pelos 6 cadastros de apoio ao item de estoque (Local de
 * Armazenamento, Categoria, Finalidade, Unidade, Unidade de embalagem,
 * Unidade de medida) para não repetir a mesma tela 6 vezes.
 * "Desativar" (desmarcar "Ativo") continua a forma recomendada de tirar um
 * valor de uso sem apagar o histórico; "Excluir" apaga o registro de fato —
 * seguro aqui porque esses 6 cadastros são só texto livre sugerido (sem FK):
 * um item de estoque que já usa o nome mantém o texto normalmente.
 */
export function ListaCadastroSimples({
  fetchFn, criarFn, atualizarFn, excluirFn, nomeNovo, placeholderNome, semRegistros,
}: {
  fetchFn: () => Promise<ItemCadastroSimples[]>;
  criarFn: (dados: { nome: string; ativo?: boolean }) => Promise<ItemCadastroSimples>;
  atualizarFn: (id: number, dados: { nome: string; ativo: boolean }) => Promise<ItemCadastroSimples>;
  excluirFn?: (id: number) => Promise<any>;
  nomeNovo: string;
  placeholderNome?: string;
  semRegistros: string;
}) {
  const [itens, setItens] = useState<ItemCadastroSimples[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => fetchFn().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(itens ?? []);

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (r: ItemCadastroSimples) => { setForm({ nome: r.nome, ativo: r.ativo }); setEditando(r.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = { nome: form.nome.trim(), ativo: form.ativo };
      if (editando === "novo") await criarFn(dados);
      else if (typeof editando === "number") await atualizarFn(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const excluir = async (r: ItemCadastroSimples) => {
    if (!excluirFn) return;
    if (!window.confirm(`Excluir "${r.nome}"? Isso não pode ser desfeito.`)) return;
    setError(null);
    try {
      await excluirFn(r.id);
      await carregar();
    } catch (e: any) {
      setError(e.message || "Erro ao excluir");
    }
  };

  return (
    <>
      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      <div className="flex justify-end mb-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> {nomeNovo}
        </button>
      </div>
      {editando === "novo" && <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} placeholderNome={placeholderNome} />}
      {itens && (
        <div className="overflow-x-auto">
        <table className="fazenda-table">
          <thead><tr><ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} /><th></th></tr></thead>
          <tbody>
            {linhasOrdenadas.map((r) => (
              <Fragment key={r.id}>
                <tr>
                  <td style={{ fontWeight: 700 }}>{r.nome}{!r.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    <div className="flex items-center justify-end gap-2">
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(r)}>
                        <Pencil size={13} /> Editar
                      </button>
                      {excluirFn && (
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--red)" }} onClick={() => excluir(r)}>
                          <Trash2 size={13} /> Excluir
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                {editando === r.id && (
                  <tr><td colSpan={2} style={{ padding: 0 }}>
                    <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} placeholderNome={placeholderNome} />
                  </td></tr>
                )}
              </Fragment>
            ))}
            {!itens.length && <tr><td colSpan={2} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{semRegistros}</td></tr>}
          </tbody>
        </table>
        </div>
      )}
    </>
  );
}

function FormItem({ form, setForm, onSalvar, onCancelar, salvando, msg, placeholderNome }: {
  form: Form; setForm: (f: Form) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null; placeholderNome?: string;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder={placeholderNome} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
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
