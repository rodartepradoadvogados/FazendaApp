"use client";
import { useEffect, useState } from "react";
import { SlidersHorizontal, AlertTriangle, Info } from "lucide-react";
import { fetchParametros } from "@/lib/api";

type Item = { chave: string; label: string; valor: number; unidade: string };
type Grupo = { titulo: string; itens: Item[] };

export default function ParametrosPage() {
  const [grupos, setGrupos] = useState<Record<string, Grupo> | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          {Object.entries(grupos).map(([id, g]) => (
            <div key={id} className="card">
              <div className="card-header mb-3">{g.titulo}</div>
              <table className="fazenda-table">
                <tbody>
                  {g.itens.map((it) => (
                    <tr key={it.chave}>
                      <td style={{ fontSize: "0.82rem" }}>{it.label}</td>
                      <td style={{ textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>
                        {it.valor}<span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginLeft: "0.25rem" }}>{it.unidade}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
