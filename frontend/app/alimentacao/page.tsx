"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, Wheat, ChevronDown, ChevronRight, ListOrdered, PieChart, CalendarClock, Package } from "lucide-react";
import { fetchAlimentacao, fetchNecessidadeMensal, fetchEstadoBaixaAlimentacao } from "@/lib/api";

const TRATOS = 2; // 2 tratos por dia
const fmt = (v: number) => Number(v.toFixed(2)).toLocaleString("pt-BR");
const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");

function StatusBaixa() {
  const [estado, setEstado] = useState<{ ultima_data_deducao: string | null } | null>(null);
  useEffect(() => { fetchEstadoBaixaAlimentacao().then(setEstado).catch(() => {}); }, []);
  if (!estado) return null;
  return (
    <div className="card mb-4 flex items-center gap-2" style={{ background: "rgba(94,26,46,0.18)" }}>
      <Package size={15} style={{ color: "var(--dourado-light)" }} />
      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
        Baixa automática de estoque: última atualização em <strong style={{ color: "var(--text)" }}>{fmtDia(estado.ultima_data_deducao)}</strong>.
        O sistema desconta o consumo acumulado do estoque sozinho, conforme os dias que passaram desde a última vez — sem precisar de botão.
      </p>
    </div>
  );
}

function ConsumoDiario({ a, error }: { a: any; error: string | null }) {
  const total: any[] = a?.consumo_total ?? [];
  const maxTotal = total.reduce((m, x) => Math.max(m, x.consumo_dia), 0) || 1;
  return (
    <div className="card">
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
  );
}

function PlanoPorLote({ a }: { a: any }) {
  const porLote: any[] = a?.por_lote ?? [];
  const [abertos, setAbertos] = useState<Set<number>>(new Set());
  const toggle = (l: number) => setAbertos((p) => { const n = new Set(p); n.has(l) ? n.delete(l) : n.add(l); return n; });
  return (
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
                <div style={{ overflowX: "auto" }}>
                  <table className="fazenda-table" style={{ margin: 0, minWidth: 440 }}>
                    <thead><tr><th>Ingrediente</th><th style={{ textAlign: "right" }}>Por cabeça</th><th style={{ textAlign: "right" }}>Lote/dia</th><th style={{ textAlign: "right" }}>Lote/trato</th></tr></thead>
                    <tbody>
                      {l.itens.map((i: any) => (
                        <tr key={i.ingrediente}>
                          <td style={{ fontSize: "0.82rem", whiteSpace: "nowrap" }}>{i.ingrediente}</td>
                          <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>{fmt(i.por_cabeca)} {i.unidade}</td>
                          <td style={{ textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>{fmt(i.consumo_dia)} {i.unidade}</td>
                          <td style={{ textAlign: "right", color: "var(--text-muted)", whiteSpace: "nowrap" }}>{fmt(i.consumo_dia / TRATOS)} {i.unidade}</td>
                        </tr>
                      ))}
                      {!l.itens.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Sem dieta para este lote.</td></tr>}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function NecessidadeMensal() {
  const [dados, setDados] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetchNecessidadeMensal().then(setDados).catch((e) => setError(e.message)); }, []);

  if (error) return <div className="alert-critico"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>;
  if (!dados) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  const itens: any[] = dados.itens ?? [];
  return (
    <div className="card">
      <div className="card-header mb-3">Necessidade mensal (30 dias)</div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Projeção simples: consumo diário × 30. Itens marcados como ensacados em Configurações {"›"} Cadastro {"›"} Itens de estoque
        aparecem convertidos em sacos (arredondado para cima).
      </p>
      <table className="fazenda-table">
        <thead><tr><th>Ingrediente</th><th style={{ textAlign: "right" }}>Necessidade (30d)</th><th style={{ textAlign: "right" }}>Sacos (30d)</th><th>Vínculo com estoque</th></tr></thead>
        <tbody>
          {itens.map((i) => (
            <tr key={i.ingrediente}>
              <td style={{ fontWeight: 600, fontSize: "0.85rem" }}>{i.ingrediente}</td>
              <td style={{ textAlign: "right", fontWeight: 700 }}>{fmt(i.necessidade_mes)} {i.unidade}</td>
              <td style={{ textAlign: "right" }}>{i.sacos_mes ?? "—"}</td>
              <td style={{ fontSize: "0.76rem", color: i.item_estoque_vinculado ? "var(--green-light)" : "var(--amber)" }}>
                {i.item_estoque_vinculado ? (i.ensacado ? `Ensacado (${i.kg_por_saco} kg/saco)` : "Vinculado (a granel)") : "Sem item de estoque com esse nome"}
              </td>
            </tr>
          ))}
          {!itens.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)" }}>Sem dieta carregada.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

const ABAS = [
  ["consumo", "Consumo Diário", ListOrdered],
  ["lote", "Plano por Lote", PieChart],
  ["mensal", "Necessidade mensal", CalendarClock],
] as const;

export default function AlimentacaoPage() {
  const [aba, setAba] = useState<(typeof ABAS)[number][0]>("consumo");
  const [a, setA] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { fetchAlimentacao().then(setA).catch((e) => setError(e.message)); }, []);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Wheat size={22} style={{ color: "var(--dourado-light)" }} /> Alimentação</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Dieta por lote cruzada com o efetivo — consumo por cabeça, por lote/dia e por lote/trato ({TRATOS} tratos/dia).</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload do DIETA.csv</a>.</span></div>}

      <StatusBaixa />

      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        {ABAS.map(([id, label, Icon]) => (
          <button key={id} onClick={() => setAba(id)}
            style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
              border: "1px solid " + (aba === id ? "var(--dourado)" : "var(--border)"),
              background: aba === id ? "rgba(94,26,46,0.4)" : "transparent",
              color: aba === id ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: aba === id ? 700 : 500 }}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {!a && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {a && aba === "consumo" && <ConsumoDiario a={a} error={error} />}
      {a && aba === "lote" && <PlanoPorLote a={a} />}
      {aba === "mensal" && <NecessidadeMensal />}
    </div>
  );
}
