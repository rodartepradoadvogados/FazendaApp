"use client";

import { useEffect, useState, useCallback } from "react";
import { Calendar, Filter, Plus, RefreshCw } from "lucide-react";
import { fetchAgenda, addEventoManual, today, formatDate } from "@/lib/api";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";

const CATEGORIAS = ["Reprodutivo", "Sanidade", "Produção", "Gestão/Financeiro", "Atividades"];
const BADGE_CLASS: Record<string, string> = {
  "Reprodutivo":       "badge-reprodutivo",
  "Sanidade":          "badge-sanidade",
  "Produção":          "badge-producao",
  "Gestão/Financeiro": "badge-financeiro",
  "Atividades":        "badge-atividades",
};

export default function AgendaPage() {
  const [data, setData] = useState(today());
  const [agenda, setAgenda] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ data_evento: today(), descricao: "", categoria: "Gestão/Financeiro", numero_animal: "", observacao: "" });
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);
  const [datasAbertas, setDatasAbertas] = useState<Set<string>>(new Set());
  const toggleData = (d: string) => setDatasAbertas(p => { const n = new Set(p); n.has(d) ? n.delete(d) : n.add(d); return n; });

  const carregar = useCallback(async () => {
    setLoading(true);
    try { setAgenda(await fetchAgenda(data)); }
    catch { setAgenda(null); }
    finally { setLoading(false); }
  }, [data]);

  useEffect(() => { carregar(); }, [carregar]);

  const eventosFiltrados = (agenda?.eventos || []).filter((e: any) => {
    if (!filtro) return true;
    return (e.descricao + e.numero_animal + e.categoria).toLowerCase().includes(filtro.toLowerCase());
  });

  const handleAddEvento = async () => {
    try {
      await addEventoManual(form);
      setShowModal(false);
      carregar();
    } catch (e: any) { alert(e.message); }
  };

  return (
    <div className="p-6 animate-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Calendar size={22} style={{ color: "var(--dourado)" }} />
            Agenda
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Eventos preditivos gerados automaticamente pelas regras da fazenda
          </p>
        </div>
        <div className="flex gap-2">
          <input
            type="date"
            value={data}
            onChange={e => setData(e.target.value)}
            className="btn-ghost"
            style={{ padding: "0.4rem 0.75rem", fontSize: "0.875rem", background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: "8px" }}
          />
          <button onClick={carregar} className="btn-ghost" title="Recarregar">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
          <button onClick={() => setShowModal(true)} className="btn-primary">
            <Plus size={16} /> Adicionar
          </button>
        </div>
      </div>

      {/* KPIs bloco */}
      {agenda && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
          {[
            { label: "Candidatas IATF", value: agenda.totais?.candidatas_iatf, color: "var(--blue)",
              list: (agenda.candidatas_iatf || []).map((c: any) => ({ numero: c.numero_matriz, sit_rep: c.sit_rep, del_dias: c.del_dias })) },
            { label: "BST Elegíveis", value: agenda.totais?.bst_elegiveis, color: "var(--amber)",
              list: (agenda.bst_elegiveis || []).map((b: any) => ({ numero: b.numero_matriz, grupo_primario: b.grupo, del_dias: b.del_dias })) },
            { label: "Contas (10d)", value: agenda.totais?.contas_a_pagar, color: "var(--red)" },
            { label: "Total Eventos", value: agenda.totais?.eventos, color: "var(--dourado-light)" },
          ].map((k: any) => {
            const clic = k.list && k.list.length;
            return (
              <div key={k.label} className="kpi-card" style={{ padding: "0.9rem", cursor: clic ? "pointer" : undefined }}
                onClick={() => clic && setModal({ title: k.label, list: k.list })}>
                <p className="kpi-value" style={{ fontSize: "1.6rem", color: k.color }}>{k.value ?? "—"}</p>
                <p className="kpi-label">{k.label}{clic ? " ›" : ""}</p>
              </div>
            );
          })}
        </div>
      )}

      {/* Blocos fixos: IATF */}
      {agenda?.candidatas_iatf?.length > 0 && (
        <div className="card mb-4">
          <div className="card-header mb-3">Candidatas IATF ({agenda.candidatas_iatf.length})</div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Nº Animal</th><th>Sit. Rep.</th><th>DEL</th><th>Motivo</th></tr></thead>
              <tbody>
                {agenda.candidatas_iatf.map((c: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 700 }}>{c.numero_matriz}</td>
                    <td><span className="badge-reprodutivo" style={{ padding: "0.1rem 0.4rem", borderRadius: "4px", fontSize: "0.75rem" }}>{c.sit_rep}</span></td>
                    <td>{c.del_dias ?? "—"}</td>
                    <td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{c.motivo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* BST excluídos */}
      {agenda?.bst_excluidos?.length > 0 && (
        <div className="card mb-4">
          <div className="card-header mb-3" style={{ background: "linear-gradient(135deg, #2a2000, #1a1400)" }}>
            BST — Excluídos ({agenda.bst_excluidos.length})
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Nº Animal</th><th>Grupo</th><th>DEL</th><th>Motivo</th></tr></thead>
              <tbody>
                {agenda.bst_excluidos.slice(0, 15).map((b: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 700 }}>{b.numero_matriz}</td>
                    <td style={{ fontSize: "0.78rem" }}>{b.grupo}</td>
                    <td>{b.del_dias ?? "—"}</td>
                    <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{b.motivo_exclusao}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tabela cronológica */}
      <div className="card">
        <div className="card-header mb-3 flex items-center justify-between">
          <span>Eventos Cronológicos ({eventosFiltrados.length})</span>
          <div className="flex items-center gap-2">
            <Filter size={13} style={{ color: "var(--text-muted)" }} />
            <input
              value={filtro}
              onChange={e => setFiltro(e.target.value)}
              placeholder="Filtrar..."
              style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.25rem 0.6rem", fontSize: "0.78rem", color: "var(--text)", width: "180px" }}
            />
          </div>
        </div>
        {loading ? (
          <p style={{ color: "var(--text-muted)", padding: "2rem", textAlign: "center" }}>Carregando agenda...</p>
        ) : eventosFiltrados.length > 0 ? (
          <div className="space-y-2">
            {(() => {
              const porData = new Map<string, any[]>();
              eventosFiltrados.forEach((e: any) => { (porData.get(e.data) ?? porData.set(e.data, []).get(e.data)!).push(e); });
              return Array.from(porData.keys()).sort().map((data) => {
                const evs = porData.get(data)!; const aberto = datasAbertas.has(data);
                return (
                  <div key={data} style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
                    <button onClick={() => toggleData(data)} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.9rem", background: "var(--surface-2)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                      <span style={{ color: "var(--text-muted)" }}>{aberto ? "▾" : "▸"}</span>
                      <span style={{ fontWeight: 700, minWidth: "6rem" }}>{new Date(data + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" })}</span>
                      <span style={{ flex: 1, fontSize: "0.78rem", color: "var(--text-muted)" }}>{evs.length} evento{evs.length !== 1 ? "s" : ""}</span>
                    </button>
                    {aberto && (
                      <div className="overflow-x-auto">
                        <table className="fazenda-table" style={{ margin: 0 }}>
                          <thead><tr><th>Categoria</th><th>Nº Animal</th><th>Descrição</th><th>Obs.</th><th>Origem</th></tr></thead>
                          <tbody>
                            {evs.map((e: any, i: number) => (
                              <tr key={i}>
                                <td><span className={BADGE_CLASS[e.categoria] || "badge-atividades"} style={{ padding: "0.1rem 0.5rem", borderRadius: "4px", fontSize: "0.7rem", whiteSpace: "nowrap" }}>{e.categoria}</span></td>
                                <td style={{ fontWeight: e.numero_animal ? 700 : 400 }}>{e.numero_animal || "—"}</td>
                                <td style={{ fontSize: "0.83rem" }}>{e.descricao}</td>
                                <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || "—"}</td>
                                <td style={{ fontSize: "0.7rem", color: e.fonte === "manual" ? "var(--amber)" : "var(--text-muted)" }}>{e.fonte === "manual" ? "manual" : "auto"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              });
            })()}
          </div>
        ) : (
          <p style={{ color: "var(--text-muted)", padding: "2rem", textAlign: "center" }}>
            Nenhum evento encontrado. Faça o upload dos CSV na aba Upload.
          </p>
        )}
      </div>

      {/* Modal adicionar evento */}
      {showModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div className="card" style={{ width: "420px", maxWidth: "90vw" }}>
            <div className="card-header mb-4">Adicionar Evento Manual</div>
            <div className="space-y-3">
              {[
                { label: "Data", key: "data_evento", type: "date" },
                { label: "Descrição", key: "descricao", type: "text" },
                { label: "Nº Animal (opcional)", key: "numero_animal", type: "text" },
                { label: "Observação (opcional)", key: "observacao", type: "text" },
              ].map(f => (
                <div key={f.key}>
                  <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>{f.label}</label>
                  <input
                    type={f.type}
                    value={(form as any)[f.key]}
                    onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}
                  />
                </div>
              ))}
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Categoria</label>
                <select
                  value={form.categoria}
                  onChange={e => setForm(p => ({ ...p, categoria: e.target.value }))}
                  style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}
                >
                  {CATEGORIAS.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setShowModal(false)} className="btn-ghost">Cancelar</button>
              <button onClick={handleAddEvento} className="btn-primary" disabled={!form.descricao}>Salvar</button>
            </div>
          </div>
        </div>
      )}

      {modal && <AnimalModal title={modal.title} animais={modal.list} onClose={() => setModal(null)} />}
    </div>
  );
}
