"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, Pencil, Check, Loader2 } from "lucide-react";
import { atualizarParametro, ehAdmin, fetchParametros } from "@/lib/api";

type Item = { chave: string; label: string; valor: number | string | boolean | null; unidade: string | null; tipo?: string; opcoes?: { valor: string; label: string }[] };
type Grupo = { titulo: string; itens: Item[] };

// Grade de cards editáveis de parâmetros (tabela `parametro_fazenda`,
// agrupada por `grupo` no backend) — extraído de app/parametros/page.tsx
// para ser reaproveitado tanto em "Parâmetros gerais" quanto em "Parâmetros
// financeiros" (cada um mostra um subconjunto dos grupos via `filtro`, sem
// duplicar lógica de carregar/editar/salvar).
export function GruposParametrosCards({ filtro }: { filtro: (idGrupo: string) => boolean }) {
  const [grupos, setGrupos] = useState<Record<string, Grupo> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<Set<string>>(new Set());
  const [valores, setValores] = useState<Record<string, number | string | boolean>>({});
  const [salvando, setSalvando] = useState<string | null>(null);
  const [salvoOk, setSalvoOk] = useState<string | null>(null);
  const podeEditar = ehAdmin();

  const carregar = () => fetchParametros().then((d) => setGrupos(d.grupos)).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const concluirEdicao = async (id: string, g: Grupo) => {
    const alterados = g.itens.filter((it) => it.chave in valores && valores[it.chave] !== it.valor);
    setEditando((p) => { const s = new Set(p); s.delete(id); return s; });
    if (!alterados.length) return;
    setSalvando(id);
    try {
      for (const it of alterados) {
        await atualizarParametro(it.chave, valores[it.chave]);
      }
      await carregar();
      // Avisa quem mostra o efeito dos parâmetros (ex.: rotina da lista de espera, que roda ao salvar).
      window.dispatchEvent(new Event("parametros-salvos"));
      setSalvoOk(id);
      setTimeout(() => setSalvoOk(null), 2000);
    } catch (e: any) {
      setError(e.message || "Erro ao salvar parâmetro");
    } finally {
      setSalvando(null);
    }
  };

  const inputStyle = {
    width: "5rem", textAlign: "right" as const, background: "var(--surface-2)", color: "var(--text)",
    border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.2rem 0.4rem", fontSize: "0.82rem",
  };

  if (error) return <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{error}</span></div>;
  if (!grupos) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  const entradas = Object.entries(grupos).filter(([id]) => filtro(id));
  if (!entradas.length) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {entradas.map(([id, g]) => {
        const edit = editando.has(id);
        return (
        <div key={id} className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span>{g.titulo}</span>
            {podeEditar && (
              <button
                onClick={() => edit ? concluirEdicao(id, g) : setEditando((p) => new Set(p).add(id))}
                disabled={salvando === id}
                title={edit ? "Concluir" : "Editar"}
                style={{ background: "none", border: "none", color: "var(--dourado-light)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem" }}>
                {salvando === id ? <><Loader2 size={13} className="animate-spin" /> Salvando…</>
                  : edit ? <><Check size={13} /> Concluir</> : <><Pencil size={13} /> Editar</>}
              </button>
            )}
          </div>
          <table className="fazenda-table">
            <tbody>
              {g.itens.map((it) => {
                const valorAtual = valores[it.chave] ?? it.valor;
                return (
                <tr key={it.chave}>
                  <td style={{ fontSize: "0.82rem" }}>{it.label}</td>
                  <td style={{ textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>
                    {edit && it.tipo === "bool" ? (
                      <select value={String(valorAtual)} onChange={(e) => setValores((p) => ({ ...p, [it.chave]: e.target.value === "true" }))}
                        style={inputStyle}>
                        <option value="true">Sim</option>
                        <option value="false">Não</option>
                      </select>
                    ) : edit && it.tipo === "select" ? (
                      <select value={String(valorAtual ?? "")} onChange={(e) => setValores((p) => ({ ...p, [it.chave]: e.target.value }))}
                        style={{ ...inputStyle, width: "min(34rem, 100%)", whiteSpace: "normal", textAlign: "left" }}>
                        {(it.opcoes || []).map((o) => <option key={o.valor} value={o.valor}>{o.label}</option>)}
                      </select>
                    ) : edit && it.tipo === "date" ? (
                      <input type="date" defaultValue={String(valorAtual ?? "")}
                        onChange={(e) => setValores((p) => ({ ...p, [it.chave]: e.target.value }))}
                        style={inputStyle} />
                    ) : edit && it.tipo === "texto" ? (
                      <input type="text" defaultValue={String(valorAtual ?? "")}
                        onChange={(e) => setValores((p) => ({ ...p, [it.chave]: e.target.value }))}
                        style={inputStyle} />
                    ) : edit ? (
                      <input type="number" defaultValue={Number(valorAtual)}
                        onChange={(e) => setValores((p) => ({ ...p, [it.chave]: Number(e.target.value) }))}
                        style={inputStyle} />
                    ) : it.tipo === "bool" ? (
                      <>{valorAtual ? "Sim" : "Não"}</>
                    ) : it.tipo === "select" ? (
                      <span style={{ whiteSpace: "normal", display: "inline-block", maxWidth: "34rem", textAlign: "right" }}>
                        {(it.opcoes || []).find((o) => o.valor === String(valorAtual))?.label ?? String(valorAtual)}
                      </span>
                    ) : (
                      <>{String(valorAtual)}</>
                    )}
                    {it.unidade && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginLeft: "0.25rem" }}>{it.unidade}</span>}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
          {salvoOk === id && <p style={{ fontSize: "0.68rem", color: "var(--verde, #2f9e5c)", marginTop: "0.5rem" }}>Salvo — já vale para relatórios, agenda e alertas.</p>}
        </div>
        );
      })}
    </div>
  );
}
