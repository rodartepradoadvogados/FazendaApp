"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Calendar, Filter, Plus, RefreshCw, ChevronDown, ChevronRight, Target, AlertTriangle, CheckCircle2, Check, X, Syringe, Wheat, Wallet, RotateCcw } from "lucide-react";
import { fetchAgenda, addEventoManual, marcarEventoRealizado, desmarcarEventoRealizado, fetchProtocoloIatfConcluidos, today } from "@/lib/api";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { ExportarBotoes } from "@/components/ExportarBotoes";

const COLUNAS_AGENDA = [
  { header: "Data", key: "data" }, { header: "Categoria", key: "categoria" },
  { header: "Nº Animal", key: "numero_animal" }, { header: "Descrição", key: "descricao" },
  { header: "Obs.", key: "observacao" },
];

const DIAS_PADRAO_FUTURO = 10;
function addDias(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
function diasEntre(aIso: string, bIso: string): number {
  return Math.round((new Date(bIso + "T00:00:00").getTime() - new Date(aIso + "T00:00:00").getTime()) / 86400000);
}

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
  const [fCat, setFCat] = useState("");
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ data_evento: today(), descricao: "", categoria: "Gestão/Financeiro", numero_animal: "", observacao: "" });
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);
  const [datasAbertas, setDatasAbertas] = useState<Set<string>>(new Set());
  const toggleData = (d: string) => setDatasAbertas(p => { const n = new Set(p); n.has(d) ? n.delete(d) : n.add(d); return n; });
  // Painéis recolhíveis (candidatas IATF, BST aptos, BST excluídos) — começam recolhidos.
  const [paineis, setPaineis] = useState<Set<string>>(new Set());
  const togglePainel = (k: string) => setPaineis(p => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });
  // Protocolo IATF: grupo (lançamento+dia) expandido mostra os animais + hormônio do dia.
  const [iatfAbertos, setIatfAbertos] = useState<Set<string>>(new Set());
  const toggleIatf = (id: string) => setIatfAbertos(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const [iatfChecks, setIatfChecks] = useState<Record<string, Set<string>>>({});
  const abrirIatf = (id: string, animais: string[]) => {
    setIatfChecks((p) => (p[id] ? p : { ...p, [id]: new Set(animais) }));
    toggleIatf(id);
  };
  const toggleAnimalIatf = (id: string, numero: string) => setIatfChecks((p) => {
    const atual = new Set(p[id] || []);
    atual.has(numero) ? atual.delete(numero) : atual.add(numero);
    return { ...p, [id]: atual };
  });
  // "Deseja cumprir essa atividade?" — confirmação antes de marcar realizado,
  // em vez de agir no primeiro clique.
  const [confirmando, setConfirmando] = useState<Set<string>>(new Set());
  const pedirConfirmacao = (chave: string) => setConfirmando((p) => new Set(p).add(chave));
  const cancelarConfirmacao = (chave: string) => setConfirmando((p) => { const n = new Set(p); n.delete(chave); return n; });

  // Janela de contas a pagar/receber que o backend calcula: 10 dias por padrão,
  // ou até a data "Até" escolhida (se o usuário ampliar o período).
  const diasJanela = ate ? Math.max(DIAS_PADRAO_FUTURO, diasEntre(data, ate)) : DIAS_PADRAO_FUTURO;

  const carregar = useCallback(async () => {
    setLoading(true);
    try { setAgenda(await fetchAgenda(data, diasJanela)); }
    catch { setAgenda(null); }
    finally { setLoading(false); }
  }, [data, diasJanela]);

  useEffect(() => { carregar(); }, [carregar]);

  // Protocolo IATF concluídos — permite desfazer um grupo (lançamento+dia)
  // marcado como realizado por engano.
  const [iatfConcluidos, setIatfConcluidos] = useState<any[]>([]);
  const carregarConcluidos = useCallback(async () => {
    try { setIatfConcluidos(await fetchProtocoloIatfConcluidos()); } catch { setIatfConcluidos([]); }
  }, []);
  useEffect(() => { carregarConcluidos(); }, [carregarConcluidos]);
  const [desfazendo, setDesfazendo] = useState<Set<string>>(new Set());
  const desfazerIatf = async (id: string) => {
    setDesfazendo((p) => new Set(p).add(id));
    try { await desmarcarEventoRealizado(id); await Promise.all([carregar(), carregarConcluidos()]); }
    catch (e: any) { alert(e.message); }
    finally { setDesfazendo((p) => { const n = new Set(p); n.delete(id); return n; }); }
  };

  const hoje = today();
  const eventosBase = (agenda?.eventos || []).filter((e: any) => {
    if (fCat && e.categoria !== fCat) return false;
    if (de && e.data < de) return false;
    if (ate && e.data > ate) return false;
    if (filtro && !(e.descricao + e.numero_animal + e.categoria).toLowerCase().includes(filtro.toLowerCase())) return false;
    return true;
  });
  // Próximos eventos: por padrão só os próximos 10 dias; se o usuário definir
  // "Até" explicitamente, respeita o período escolhido (pode ser maior ou menor).
  const limiteFuturo = ate || addDias(hoje, DIAS_PADRAO_FUTURO);
  const eventosFuturos = eventosBase.filter((e: any) => e.data >= hoje && e.data <= limiteFuturo);
  const eventosPendentes = eventosBase.filter((e: any) => e.data < hoje);

  const [marcando, setMarcando] = useState<Set<string>>(new Set());
  const marcarRealizado = async (eventoId: string, animais?: string[]) => {
    setMarcando((p) => new Set(p).add(eventoId));
    try {
      await marcarEventoRealizado(eventoId, animais);
      cancelarConfirmacao(eventoId);
      await carregar();
      if (eventoId.startsWith("protocolo_iatf_")) await carregarConcluidos();
    }
    catch (e: any) { alert(e.message); }
    finally { setMarcando((p) => { const n = new Set(p); n.delete(eventoId); return n; }); }
  };

  // Botão "Realizado" com confirmação inline ("Deseja cumprir essa atividade?
  // Sim/Não") em vez de agir direto no primeiro clique.
  const BotaoRealizado = ({ chave, onConfirmar, compacto }: { chave: string; onConfirmar: () => void; compacto?: boolean }) => {
    if (confirmando.has(chave)) {
      return (
        <span className="flex items-center gap-1" style={{ fontSize: "0.68rem" }} onClick={(e) => e.stopPropagation()}>
          Cumpriu?
          <button className="btn-ghost" style={{ color: "var(--green-light)", padding: "0.1rem 0.3rem" }} disabled={marcando.has(chave)} onClick={onConfirmar}>Sim</button>
          <button className="btn-ghost" style={{ padding: "0.1rem 0.3rem" }} onClick={() => cancelarConfirmacao(chave)}>Não</button>
        </span>
      );
    }
    return (
      <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={marcando.has(chave)} onClick={(e) => { e.stopPropagation(); pedirConfirmacao(chave); }}>
        <CheckCircle2 size={12} /> {compacto ? "" : "Realizado"}
      </button>
    );
  };

  const handleAddEvento = async () => {
    try {
      await addEventoManual(form);
      setShowModal(false);
      carregar();
    } catch (e: any) { alert(e.message); }
  };

  // Extrai o valor de "Conta a pagar: X — R$ 1,234.56" (formatação :,.2f do Python — vírgula de milhar, ponto decimal).
  const extrairValor = (desc: string) => { const m = desc.match(/R\$\s*([\d,]+\.\d{2})/); return m ? m[1].replace(/,/g, "") : null; };

  const renderEventos = (lista: any[]) => {
    const porData = new Map<string, any[]>();
    lista.forEach((e: any) => { (porData.get(e.data) ?? porData.set(e.data, []).get(e.data)!).push(e); });
    return Array.from(porData.keys()).sort().map((d) => {
      const evs = porData.get(d)!; const aberto = datasAbertas.has(d);

      // Dentro do dia, agrupa Gestão/Financeiro por referência (nº do lançamento/nota).
      const financeiroPorRef = new Map<string, any[]>();
      const linhas: any[] = [];
      evs.forEach((e: any) => {
        if (e.tipo === "protocolo_iatf") {
          linhas.push({ tipo: "iatf", e });
        } else if (e.categoria === "Gestão/Financeiro" && e.ref) {
          const arr = financeiroPorRef.get(e.ref) ?? [];
          arr.push(e); financeiroPorRef.set(e.ref, arr);
        } else {
          linhas.push({ tipo: "simples", e });
        }
      });
      financeiroPorRef.forEach((itens, ref) => linhas.push({ tipo: "grupo", ref, itens }));

      return (
        <div key={d} style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
          <button onClick={() => toggleData(d)} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.9rem", background: "var(--surface-2)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
            {aberto ? <ChevronDown size={15} style={{ color: "var(--text-muted)" }} /> : <ChevronRight size={15} style={{ color: "var(--text-muted)" }} />}
            <span style={{ fontWeight: 700, minWidth: "8rem" }}>{new Date(d + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short", year: "2-digit" })}</span>
            <span style={{ flex: 1, fontSize: "0.78rem", color: "var(--text-muted)" }}>{evs.length} evento{evs.length !== 1 ? "s" : ""}</span>
          </button>
          {aberto && (
            <div className="overflow-x-auto">
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th>Categoria</th><th>Nº Animal</th><th>Descrição</th><th>Obs.</th><th>Origem</th><th></th></tr></thead>
                <tbody>
                  {linhas.map((linha, i) => {
                    if (linha.tipo === "simples") {
                      const e = linha.e;
                      return (
                        <tr key={i}>
                          <td><span className={BADGE_CLASS[e.categoria] || "badge-atividades"} style={{ padding: "0.1rem 0.5rem", borderRadius: "4px", fontSize: "0.7rem", whiteSpace: "nowrap" }}>{e.categoria}</span></td>
                          <td style={{ fontWeight: e.numero_animal ? 700 : 400 }}>{e.numero_animal || "—"}</td>
                          <td style={{ fontSize: "0.83rem" }}>{e.descricao}</td>
                          <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || "—"}</td>
                          <td style={{ fontSize: "0.7rem", color: e.fonte === "manual" ? "var(--amber)" : "var(--text-muted)" }}>{e.fonte === "manual" ? "manual" : "auto"}</td>
                          <td>
                            {e.categoria === "alimentacao" ? (
                              <a href={`/lancamentos?ir=alimentacao_dieta&lote=${encodeURIComponent(e.lote ?? "")}`} className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                                <Wheat size={12} /> Ir para Dieta
                              </a>
                            ) : (
                              <BotaoRealizado chave={e.id} onConfirmar={() => marcarRealizado(e.id)} />
                            )}
                          </td>
                        </tr>
                      );
                    }
                    if (linha.tipo === "iatf") {
                      const e = linha.e;
                      const abertoIatf = iatfAbertos.has(e.id);
                      const checks = iatfChecks[e.id] || new Set(e.animais);
                      const ehD11 = e.dia === 11;
                      return (
                        <React.Fragment key={`iatf-${i}`}>
                          <tr style={{ cursor: "pointer" }} onClick={() => abrirIatf(e.id, e.animais)}>
                            <td><span className={BADGE_CLASS["Reprodutivo"]} style={{ padding: "0.1rem 0.5rem", borderRadius: "4px", fontSize: "0.7rem", whiteSpace: "nowrap" }}>Reprodutivo</span></td>
                            <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{e.animais.length} animal(is)</td>
                            <td style={{ fontSize: "0.83rem" }}>
                              {abertoIatf ? <ChevronDown size={12} style={{ display: "inline", marginRight: "0.3rem" }} /> : <ChevronRight size={12} style={{ display: "inline", marginRight: "0.3rem" }} />}
                              {e.descricao}
                            </td>
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || "—"}</td>
                            <td style={{ fontSize: "0.7rem", color: "var(--amber)" }}>manual</td>
                            <td onClick={(ev) => ev.stopPropagation()}>
                              {!ehD11 && <BotaoRealizado chave={e.id} onConfirmar={() => marcarRealizado(e.id)} />}
                            </td>
                          </tr>
                          {abertoIatf && (
                            <tr style={{ background: "var(--surface-2)" }}>
                              <td></td>
                              <td colSpan={5}>
                                <div style={{ padding: "0.5rem 0" }}>
                                  <p style={{ fontSize: "0.78rem", marginBottom: "0.4rem" }}>
                                    <Syringe size={12} style={{ display: "inline", marginRight: "0.3rem" }} />
                                    <strong>Hormônio/ação do dia:</strong> {e.hormonio}
                                  </p>
                                  <table className="fazenda-table" style={{ margin: 0 }}>
                                    <thead><tr>{!ehD11 && <th></th>}<th>Nº</th>{ehD11 && <th></th>}</tr></thead>
                                    <tbody>
                                      {e.animais.map((numero: string) => (
                                        <tr key={numero}>
                                          {!ehD11 && (
                                            <td>
                                              <input type="checkbox" checked={checks.has(numero)} onChange={() => toggleAnimalIatf(e.id, numero)} />
                                            </td>
                                          )}
                                          <td style={{ fontWeight: 700 }}>{numero}</td>
                                          {ehD11 && (
                                            <td>
                                              <a
                                                href={`/lancamentos?ir=inseminacao&numero_matriz=${encodeURIComponent(numero)}&protocolo=${encodeURIComponent(e.protocolo || "")}`}
                                                className="btn-ghost" style={{ fontSize: "0.7rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                                              >
                                                <Syringe size={12} /> Ir para Inseminação
                                              </a>
                                            </td>
                                          )}
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                  {!ehD11 && (
                                    <div className="flex items-center gap-2 mt-2">
                                      <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id) || !checks.size}
                                        onClick={() => marcarRealizado(e.id, Array.from(checks))}>
                                        <Check size={12} /> Confirmar realizado ({checks.size}/{e.animais.length})
                                      </button>
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    }
                    // Grupo Gestão/Financeiro por nota/lançamento.
                    const { ref, itens } = linha;
                    const chaveGrupo = `${d}:${ref}`;
                    const abertoGrupo = paineis.has(chaveGrupo);
                    const total = itens.reduce((acc: number, it: any) => acc + (Number(extrairValor(it.descricao)) || 0), 0);
                    return (
                      <React.Fragment key={`g-${i}`}>
                        <tr style={{ cursor: "pointer" }} onClick={() => togglePainel(chaveGrupo)}>
                          <td><span className={BADGE_CLASS["Gestão/Financeiro"]} style={{ padding: "0.1rem 0.5rem", borderRadius: "4px", fontSize: "0.7rem", whiteSpace: "nowrap" }}>Gestão/Financeiro</span></td>
                          <td>—</td>
                          <td style={{ fontSize: "0.83rem" }}>
                            {abertoGrupo ? <ChevronDown size={12} style={{ display: "inline", marginRight: "0.3rem" }} /> : <ChevronRight size={12} style={{ display: "inline", marginRight: "0.3rem" }} />}
                            Nota/lançamento <strong>{ref}</strong> — {itens.length} item{itens.length !== 1 ? "s" : ""} — R$ {total.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                          </td>
                          <td>—</td>
                          <td style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>auto</td>
                          <td onClick={(ev) => ev.stopPropagation()}>
                            <a href={`/financeiro?ir=a_pagar&ref=${encodeURIComponent(ref)}`} className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                              <Wallet size={12} /> Ir para Financeiro
                            </a>
                          </td>
                        </tr>
                        {abertoGrupo && itens.map((it: any, j: number) => (
                          <tr key={`g-${i}-${j}`} style={{ background: "var(--surface-2)" }}>
                            <td></td><td></td>
                            <td colSpan={2} style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{it.descricao}{it.observacao ? ` · ${it.observacao}` : ""}</td>
                            <td></td>
                            <td></td>
                          </tr>
                        ))}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      );
    });
  };

  const candidatas = agenda?.candidatas_iatf || [];
  const bstAptos = agenda?.bst_elegiveis || [];
  const bstExcl = agenda?.bst_excluidos || [];

  // Próxima visita reprodutiva/BST — ancorada no serviço mais recente do
  // rebanho (calculada no backend; ex.: último serviço 03/07 -> visita 24/07).
  const fmtCurta = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) : null);
  const proxVisita = fmtCurta(agenda?.proxima_visita_iatf);
  const proxBST = fmtCurta(agenda?.proxima_visita_bst);

  const ordIatf = useOrdenacao(candidatas);
  const ordBstAptos = useOrdenacao(bstAptos);
  const ordBstExcl = useOrdenacao(bstExcl);
  const [listaAtiva, setListaAtiva] = useState<Set<string>>(new Set());
  const toggleLista = (k: string) => setListaAtiva((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });

  return (
    <div className="p-6 animate-in">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
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
              list: candidatas.map((c: any) => ({ numero: c.numero_matriz, sit_rep: c.sit_rep, del_dias: c.del_dias })) },
            { label: "BST Aptos", value: bstAptos.length, color: "var(--green-light)",
              list: bstAptos.map((b: any) => ({ numero: b.numero_matriz, grupo_primario: b.grupo, del_dias: b.del_dias })) },
            { label: "BST Excluídos", value: agenda.bst_excluidos?.length ?? 0, color: "var(--amber)",
              list: bstExcl.map((b: any) => ({ numero: b.numero_matriz, grupo_primario: b.grupo, del_dias: b.del_dias })) },
            { label: "Total Eventos", value: agenda.totais?.eventos, color: "var(--dourado-light)" },
          ].map((k: any) => {
            const clic = k.list && k.list.length;
            return (
              <div key={k.label} className="kpi-card" style={{ padding: "0.9rem", cursor: clic ? "pointer" : undefined }}
                onClick={() => clic && setModal({ title: k.label, list: k.list })}>
                <p className="kpi-value" style={{ fontSize: "1.6rem", color: k.color }}>{k.value ?? "—"}</p>
                <p className="kpi-label flex items-center gap-1">{k.label}{clic ? <Target size={11} style={{ color: "var(--dourado-light)" }} /> : null}</p>
              </div>
            );
          })}
        </div>
      )}

      {/* Listas lado a lado — cada uma expande/recolhe ao clicar, sem ocupar linhas repetidas */}
      {(candidatas.length > 0 || bstAptos.length > 0 || bstExcl.length > 0) && (
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-2" style={{ flexWrap: "wrap" }}>
            {candidatas.length > 0 && (
              <button onClick={() => toggleLista("iatf")}
                style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (listaAtiva.has("iatf") ? "var(--dourado)" : "var(--border)"),
                  background: listaAtiva.has("iatf") ? "rgba(94,26,46,0.4)" : "transparent",
                  color: listaAtiva.has("iatf") ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: listaAtiva.has("iatf") ? 700 : 500 }}>
                {listaAtiva.has("iatf") ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Candidatas IATF ({candidatas.length}){proxVisita && <span style={{ fontWeight: 400, fontSize: "0.72rem" }}> — próx. visita {proxVisita}</span>}
              </button>
            )}
            {bstAptos.length > 0 && (
              <button onClick={() => toggleLista("bstAptos")}
                style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (listaAtiva.has("bstAptos") ? "var(--green-light)" : "var(--border)"),
                  background: listaAtiva.has("bstAptos") ? "rgba(20,83,45,0.4)" : "transparent",
                  color: listaAtiva.has("bstAptos") ? "var(--green-light)" : "var(--text-muted)", fontWeight: listaAtiva.has("bstAptos") ? 700 : 500 }}>
                {listaAtiva.has("bstAptos") ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                BST — Aptas ({bstAptos.length}){proxBST && <span style={{ fontWeight: 400, fontSize: "0.72rem" }}> — próx. BST {proxBST}</span>}
              </button>
            )}
            {bstExcl.length > 0 && (
              <button onClick={() => toggleLista("bstExcl")}
                style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (listaAtiva.has("bstExcl") ? "var(--amber)" : "var(--border)"),
                  background: listaAtiva.has("bstExcl") ? "rgba(120,90,10,0.35)" : "transparent",
                  color: listaAtiva.has("bstExcl") ? "var(--amber)" : "var(--text-muted)", fontWeight: listaAtiva.has("bstExcl") ? 700 : 500 }}>
                {listaAtiva.has("bstExcl") ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                BST — Excluídos ({bstExcl.length})
              </button>
            )}
          </div>

          {listaAtiva.has("iatf") && (
            <div className="card mb-2" style={{ overflowX: "auto" }}>
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrdenavel label="Nº Animal" campo="numero_matriz" coluna={ordIatf.coluna} dir={ordIatf.dir} ordenar={ordIatf.ordenar} />
                  <ThOrdenavel label="Sit. Rep." campo="sit_rep" coluna={ordIatf.coluna} dir={ordIatf.dir} ordenar={ordIatf.ordenar} />
                  <ThOrdenavel label="DEL" campo="del_dias" coluna={ordIatf.coluna} dir={ordIatf.dir} ordenar={ordIatf.ordenar} />
                  <ThOrdenavel label="Motivo" campo="motivo" coluna={ordIatf.coluna} dir={ordIatf.dir} ordenar={ordIatf.ordenar} />
                </tr></thead>
                <tbody>
                  {ordIatf.linhasOrdenadas.map((c: any, i: number) => (
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
          )}

          {listaAtiva.has("bstAptos") && (
            <div className="card mb-2" style={{ overflowX: "auto" }}>
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrdenavel label="Nº Animal" campo="numero_matriz" coluna={ordBstAptos.coluna} dir={ordBstAptos.dir} ordenar={ordBstAptos.ordenar} />
                  <ThOrdenavel label="Grupo" campo="grupo" coluna={ordBstAptos.coluna} dir={ordBstAptos.dir} ordenar={ordBstAptos.ordenar} />
                  <ThOrdenavel label="DEL" campo="del_dias" coluna={ordBstAptos.coluna} dir={ordBstAptos.dir} ordenar={ordBstAptos.ordenar} />
                </tr></thead>
                <tbody>
                  {ordBstAptos.linhasOrdenadas.map((b: any, i: number) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 700 }}>{b.numero_matriz}</td>
                      <td style={{ fontSize: "0.78rem" }}>{b.grupo}</td>
                      <td>{b.del_dias ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {listaAtiva.has("bstExcl") && (
            <div className="card mb-2" style={{ overflowX: "auto" }}>
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrdenavel label="Nº Animal" campo="numero_matriz" coluna={ordBstExcl.coluna} dir={ordBstExcl.dir} ordenar={ordBstExcl.ordenar} />
                  <ThOrdenavel label="Grupo" campo="grupo" coluna={ordBstExcl.coluna} dir={ordBstExcl.dir} ordenar={ordBstExcl.ordenar} />
                  <ThOrdenavel label="DEL" campo="del_dias" coluna={ordBstExcl.coluna} dir={ordBstExcl.dir} ordenar={ordBstExcl.ordenar} />
                  <ThOrdenavel label="Motivo" campo="motivo_exclusao" coluna={ordBstExcl.coluna} dir={ordBstExcl.dir} ordenar={ordBstExcl.ordenar} />
                </tr></thead>
                <tbody>
                  {ordBstExcl.linhasOrdenadas.map((b: any, i: number) => (
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
          )}
        </div>
      )}

      {/* Protocolo IATF — concluídos recentemente, com opção de desfazer */}
      {iatfConcluidos.length > 0 && (
        <div className="card mb-4">
          <button onClick={() => togglePainel("iatfConcluidos")} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.5rem", background: "none", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left", padding: 0 }}>
            {paineis.has("iatfConcluidos") ? <ChevronDown size={15} style={{ color: "var(--text-muted)" }} /> : <ChevronRight size={15} style={{ color: "var(--text-muted)" }} />}
            <span className="card-header" style={{ margin: 0 }}>Protocolo IATF — concluídos ({iatfConcluidos.length})</span>
          </button>
          {paineis.has("iatfConcluidos") && (
            <div className="overflow-x-auto mt-3">
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th>Protocolo</th><th>Etapa</th><th>Animais</th><th>Concluído em</th><th></th></tr></thead>
                <tbody>
                  {iatfConcluidos.map((g: any) => (
                    <tr key={g.id}>
                      <td style={{ fontSize: "0.83rem" }}>{g.nome_protocolo}</td>
                      <td>D{g.dia}</td>
                      <td style={{ fontSize: "0.78rem" }}>{g.animais.join(", ")}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{g.data_realizacao ? new Date(g.data_realizacao + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td>
                        <button className="btn-ghost" style={{ fontSize: "0.7rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} disabled={desfazendo.has(g.id)} onClick={() => desfazerIatf(g.id)}>
                          <RotateCcw size={12} /> Desfazer
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Filtros da agenda cronológica */}
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtrar agenda</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
            <input type="date" value={de} onChange={e => setDe(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
            <input type="date" value={ate} onChange={e => setAte(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria</label>
            <select value={fCat} onChange={e => setFCat(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }}>
              <option value="">Todas</option>{CATEGORIAS.map(c => <option key={c}>{c}</option>)}
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Buscar</label>
            <input value={filtro} onChange={e => setFiltro(e.target.value)} placeholder="texto ou nº..." style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }} /></div>
        </div>
        {(de || ate || fCat || filtro) && <button className="btn-ghost" style={{ marginTop: "0.75rem", fontSize: "0.75rem" }} onClick={() => { setDe(""); setAte(""); setFCat(""); setFiltro(""); }}>Limpar filtros</button>}
      </div>

      {/* Pendentes (eventos anteriores a hoje ainda em aberto) — sempre visível, mesmo vazia */}
      <div className="card mb-4" style={{ border: eventosPendentes.length ? "1px solid var(--amber)" : "1px solid var(--border)" }}>
        <div className="card-header mb-3 flex items-center justify-between" style={{ color: eventosPendentes.length ? "var(--amber)" : "var(--text-muted)" }}>
          <span className="flex items-center gap-2"><AlertTriangle size={15} /> Agenda de Pendentes ({eventosPendentes.length})</span>
          <ExportarBotoes titulo="Agenda de Pendentes" nomeArquivoBase="agenda_pendentes" colunas={COLUNAS_AGENDA} linhas={eventosPendentes} />
        </div>
        {eventosPendentes.length > 0 ? (
          <div className="space-y-2">{renderEventos(eventosPendentes)}</div>
        ) : (
          <p style={{ color: "var(--text-muted)", padding: "1rem", textAlign: "center", fontSize: "0.85rem" }}>0 pendências — tudo em dia.</p>
        )}
      </div>

      {/* Agenda do dia presente em diante */}
      <div className="card">
        <div className="card-header mb-1 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
          <span>Eventos — hoje e próximos ({eventosFuturos.length})</span>
          <div className="flex items-center gap-2">
            {!ate && <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>próximos {DIAS_PADRAO_FUTURO} dias — defina "Até" para ampliar</span>}
            <ExportarBotoes titulo="Agenda — Eventos" nomeArquivoBase="agenda_eventos" colunas={COLUNAS_AGENDA} linhas={eventosFuturos} />
          </div>
        </div>
        <div style={{ marginTop: "0.75rem" }}>
        {loading ? (
          <p style={{ color: "var(--text-muted)", padding: "2rem", textAlign: "center" }}>Carregando agenda...</p>
        ) : eventosFuturos.length > 0 ? (
          <div className="space-y-2">{renderEventos(eventosFuturos)}</div>
        ) : (
          <p style={{ color: "var(--text-muted)", padding: "2rem", textAlign: "center" }}>
            Nenhum evento futuro no filtro. Faça o upload dos CSV na aba Upload.
          </p>
        )}
        </div>
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
