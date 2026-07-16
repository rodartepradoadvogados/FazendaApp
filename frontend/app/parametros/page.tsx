"use client";
import { useEffect, useState } from "react";
import { SlidersHorizontal, AlertTriangle, Info, Pencil, Check, Loader2 } from "lucide-react";
import { atualizarParametro, ehAdmin, fetchParametros } from "@/lib/api";
import CadastroMotivosVenda from "@/components/CadastroMotivosVenda";

type Item = { chave: string; label: string; valor: number | string | boolean | null; unidade: string | null; tipo?: string };
type Grupo = { titulo: string; itens: Item[] };

export default function ParametrosPage() {
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
    border: "1px solid var(--border)", borderRadius: "6px", padding: "0.2rem 0.4rem", fontSize: "0.82rem",
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <SlidersHorizontal size={22} style={{ color: "var(--dourado-light)" }} /> Parâmetros da Fazenda
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Metas e configurações de manejo que orientam os indicadores, a agenda e os relatórios (faixas verde/vermelha, previsões e alertas).
        </p>
      </div>

      <div className="card mb-4" style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", background: "rgba(94,26,46,0.18)" }}>
        <Info size={16} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Estes são os valores de referência atuais da fazenda. Servem de base para as metas dos medidores da capa e para as regras da agenda.
          {podeEditar
            ? " O valor salvo passa a valer para todos os relatórios, agenda e alertas."
            : " Somente administradores podem editar."}
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{error}</span></div>}
      {!grupos && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {grupos && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Object.entries(grupos).map(([id, g]) => {
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
                        ) : edit && it.tipo === "date" ? (
                          <input type="date" defaultValue={String(valorAtual ?? "")}
                            onChange={(e) => setValores((p) => ({ ...p, [it.chave]: e.target.value }))}
                            style={inputStyle} />
                        ) : edit ? (
                          <input type="number" defaultValue={Number(valorAtual)}
                            onChange={(e) => setValores((p) => ({ ...p, [it.chave]: Number(e.target.value) }))}
                            style={inputStyle} />
                        ) : it.tipo === "bool" ? (
                          <>{valorAtual ? "Sim" : "Não"}</>
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
      )}

      <div className="mt-4">
        <CadastroMotivosVenda />
      </div>
    </div>
  );
}
