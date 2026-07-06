"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, Wheat, ChevronDown, ChevronRight } from "lucide-react";
import { fetchAlimentacao } from "@/lib/api";

const TRATOS = 2; // 2 tratos por dia
const fmt = (v: number) => Number(v.toFixed(2)).toLocaleString("pt-BR");

export default function AlimentacaoPage() {
  const [a, setA] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [abertos, setAbertos] = useState<Set<number>>(new Set());

  useEffect(() => {
    fetchAlimentacao().then(setA).catch((e) => setError(e.message));
  }, []);

  const total: any[] = a?.consumo_total ?? [];
  const porLote: any[] = a?.por_lote ?? [];
  const maxTotal = total.reduce((m, x) => Math.max(m, x.consumo_dia), 0) || 1;
  const toggle = (l: number) => setAbertos((p) => { const n = new Set(p); n.has(l) ? n.delete(l) : n.add(l); return n; });

  return (
    <div className="p-6 animate-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Wheat size={22} style={{ color: "var(--dourado-light)" }} /> Alimentação</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Dieta por lote cruzada com o efetivo — consumo por cabeça, por lote/dia e por lote/trato ({TRATOS} tratos/dia).</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload do DIETA.csv</a>.</span></div>}
      {!a && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {a && <>
        {/* Consumo total do rebanho */}
        <div className="card mb-4">
          <div className="card-header mb-3">Consumo Diário do Rebanho (por ingrediente)</div>
          <table className="fazenda-table">
            <thead><tr><th>Ingrediente</th><th></th><th style={{ textAlign: "right" }}>Por dia</th><th style={{ textAlign: "right" }}>Por trato</th></tr></thead>
            <tbody>
              {total.map((x) => (
                <tr key={x.ingrediente}>
                  <td style={{ fontWeight: 600, fontSize: "0.85rem", minWidth: "9rem" }}>{x.ingrediente}</td>
                  <td style={{ width: "40%" }}>
                    <div style={{ background: "var(--surface-2)", borderRadius: "4px", height: "14px", overflow: "hidden" }}><div style={{ width: `${(x.consumo_dia / maxTotal) * 100}%`, height: "100%", background: "var(--dourado)", minWidth: "2px" }} /></div>
                  </td>
                  <td style={{ textAlign: "right", fontWeight: 700 }}>{fmt(x.consumo_dia)} {x.unidade}</td>
                  <td style={{ textAlign: "right", color: "var(--text-muted)" }}>{fmt(x.consumo_dia / TRATOS)} {x.unidade}</td>
                </tr>
              ))}
              {!total.length && !error && <tr><td colSpan={4} style={{ color: "var(--text-muted)" }}>Sem dieta carregada.</td></tr>}
            </tbody>
          </table>
        </div>

        {/* Por lote — cartões expansíveis */}
        <div className="card">
          <div className="card-header mb-3">Plano por Lote <span style={{ fontWeight: 400, fontSize: "0.72rem", color: "var(--text-muted)" }}>(clique para expandir)</span></div>
          <div className="space-y-2">
            {porLote.map((l) => {
              const aberto = abertos.has(l.lote);
              return (
                <div key={l.lote} style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
                  <button onClick={() => toggle(l.lote)} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.6rem 0.9rem", background: "var(--surface-2)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                    {aberto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    <span style={{ fontWeight: 700, minWidth: "1.5rem" }}>{l.lote}</span>
                    <span style={{ flex: 1 }}>{l.categoria}</span>
                    <span style={{ fontSize: "0.8rem", color: l.efetivo === 0 ? "var(--text-muted)" : "var(--dourado-light)" }}>{l.efetivo} cab.</span>
                  </button>
                  {aberto && (
                    <table className="fazenda-table" style={{ margin: 0 }}>
                      <thead><tr><th>Ingrediente</th><th style={{ textAlign: "right" }}>Por cabeça</th><th style={{ textAlign: "right" }}>Lote/dia</th><th style={{ textAlign: "right" }}>Lote/trato</th></tr></thead>
                      <tbody>
                        {l.itens.map((i: any) => (
                          <tr key={i.ingrediente}>
                            <td style={{ fontSize: "0.82rem" }}>{i.ingrediente}</td>
                            <td style={{ textAlign: "right" }}>{fmt(i.por_cabeca)} {i.unidade}</td>
                            <td style={{ textAlign: "right", fontWeight: 700 }}>{fmt(i.consumo_dia)} {i.unidade}</td>
                            <td style={{ textAlign: "right", color: "var(--text-muted)" }}>{fmt(i.consumo_dia / TRATOS)} {i.unidade}</td>
                          </tr>
                        ))}
                        {!l.itens.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Sem dieta para este lote.</td></tr>}
                      </tbody>
                    </table>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </>}
    </div>
  );
}
