"use client";
import { useEffect, useState } from "react";
import { SlidersHorizontal, AlertTriangle, Info, Pencil, Check } from "lucide-react";
import { fetchParametros } from "@/lib/api";

type Item = { chave: string; label: string; valor: number; unidade: string };
type Grupo = { titulo: string; itens: Item[] };

export default function ParametrosPage() {
  const [grupos, setGrupos] = useState<Record<string, Grupo> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<Set<string>>(new Set());
  const [valores, setValores] = useState<Record<string, number>>({});
  const toggleEdit = (id: string) => setEditando((p) => { const s = new Set(p); s.has(id) ? s.delete(id) : s.add(id); return s; });

  useEffect(() => {
    fetchParametros().then((d) => setGrupos(d.grupos)).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <SlidersHorizontal size={22} style={{ color: "var(--dourado-light)" }} /> Parâmetros da Fazenda
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Metas e configurações de manejo que orientam os indicadores e alertas (faixas verde/vermelha, agenda e benchmark).
        </p>
      </div>

      <div className="card mb-4" style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", background: "rgba(94,26,46,0.18)" }}>
        <Info size={16} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Estes são os valores de referência atuais da fazenda. Servem de base para as metas dos medidores da capa e para as regras da agenda.
          Por enquanto são fixos; se algum não corresponder à sua realidade, me diga o valor correto que eu ajusto.
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!grupos && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {grupos && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Object.entries(grupos).map(([id, g]) => {
            const edit = editando.has(id);
            return (
            <div key={id} className="card">
              <div className="card-header mb-3 flex items-center justify-between">
                <span>{g.titulo}</span>
                <button onClick={() => toggleEdit(id)} title={edit ? "Concluir" : "Editar"}
                  style={{ background: "none", border: "none", color: "var(--dourado-light)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem" }}>
                  {edit ? <><Check size={13} /> Concluir</> : <><Pencil size={13} /> Editar</>}
                </button>
              </div>
              <table className="fazenda-table">
                <tbody>
                  {g.itens.map((it) => (
                    <tr key={it.chave}>
                      <td style={{ fontSize: "0.82rem" }}>{it.label}</td>
                      <td style={{ textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>
                        {edit ? (
                          <input type="number" defaultValue={valores[it.chave] ?? it.valor}
                            onChange={(e) => setValores((p) => ({ ...p, [it.chave]: Number(e.target.value) }))}
                            style={{ width: "5rem", textAlign: "right", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.2rem 0.4rem", fontSize: "0.82rem" }} />
                        ) : (
                          <>{valores[it.chave] ?? it.valor}</>
                        )}
                        <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginLeft: "0.25rem" }}>{it.unidade}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {edit && <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Ao ligar o banco, o valor salvo passa a valer para todos os relatórios, agenda e alertas.</p>}
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
