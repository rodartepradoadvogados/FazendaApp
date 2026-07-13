"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Calendar, Filter, Plus, RefreshCw, ChevronDown, ChevronRight, Target, AlertTriangle, CheckCircle2, Check, X, Syringe, Wheat, Wallet, RotateCcw, ExternalLink } from "lucide-react";
import { fetchAgenda, addEventoManual, marcarEventoRealizado, desmarcarEventoRealizado, fetchProtocoloIatfConcluidos, fetchProtocoloInducaoConcluidos, fetchAnimais, fetchLotes, today } from "@/lib/api";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";
import { SelecaoAnimaisTabela } from "@/components/SelecaoAnimaisTabela";
import { SelecaoLotesTabela, LoteRow } from "@/components/SelecaoLotesTabela";
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
const TIPOS_EVENTO = ["Compra", "Venda", "Serviço", "Outro"];
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
  const [erro, setErro] = useState<string | null>(null);
  // Mensagem transitória de sucesso/erro exibida sob o cabeçalho (substitui alert()).
  const [feedback, setFeedback] = useState<{ msg: string; erro?: boolean } | null>(null);
  const mostrarFeedback = (msg: string, erro = false) => {
    setFeedback({ msg, erro });
    setTimeout(() => setFeedback((f) => (f && f.msg === msg ? null : f)), 4000);
  };
  const [filtro, setFiltro] = useState("");
  const [fCat, setFCat] = useState("");
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({
    data_evento: today(), descricao: "", categoria: "Gestão/Financeiro", observacao: "",
    tipo_evento: "", recorrente: false, recorrenciaNumero: "", recorrenciaFrequencia: "dias" as "dias" | "meses",
  });
  const [vinculo, setVinculo] = useState<"nenhum" | "animal" | "lote">("nenhum");
  const [animaisSelecionados, setAnimaisSelecionados] = useState<Set<string>>(new Set());
  const [lotesSelecionados, setLotesSelecionados] = useState<Set<string>>(new Set());
  const [animaisTodos, setAnimaisTodos] = useState<AnimalRow[]>([]);
  const [lotesTodos, setLotesTodos] = useState<LoteRow[]>([]);
  const [pickerAberto, setPickerAberto] = useState<"animal" | "lote" | null>(null);
  const abrirPicker = async (tipo: "animal" | "lote") => {
    if (tipo === "animal" && !animaisTodos.length) fetchAnimais().then(setAnimaisTodos).catch(() => {});
    if (tipo === "lote" && !lotesTodos.length) fetchLotes().then(setLotesTodos).catch(() => {});
    setVinculo(tipo);
    setPickerAberto(tipo);
  };
  const toggleAnimalSelecionado = (numero: string) => setAnimaisSelecionados((p) => { const n = new Set(p); n.has(numero) ? n.delete(numero) : n.add(numero); return n; });
  const toggleTodosAnimais = () => setAnimaisSelecionados((p) => (p.size === animaisTodos.length ? new Set() : new Set(animaisTodos.map((a) => a.numero))));
  const toggleLoteSelecionado = (codigo: string) => setLotesSelecionados((p) => { const n = new Set(p); n.has(codigo) ? n.delete(codigo) : n.add(codigo); return n; });
  const toggleTodosLotes = () => setLotesSelecionados((p) => (p.size === lotesTodos.length ? new Set() : new Set(lotesTodos.map((l) => l.codigo))));
  const pickerColunasAnimais = [
    { header: "Nº", render: (a: AnimalRow) => a.numero },
    { header: "Grupo", render: (a: AnimalRow) => a.grupo_primario || "—" },
    { header: "Categoria", render: (a: AnimalRow) => a.categoria_abrev || a.categoria_completa || "—" },
  ];
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
  // Indução de lactação: mesmo padrão do protocolo IATF (grupo lançamento+dia
  // expandido mostra os animais + medicamentos/observação de manejo do dia).
  const [inducaoAbertos, setInducaoAbertos] = useState<Set<string>>(new Set());
  const toggleInducao = (id: string) => setInducaoAbertos(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const [inducaoChecks, setInducaoChecks] = useState<Record<string, Set<string>>>({});
  const abrirInducao = (id: string, animais: string[]) => {
    setInducaoChecks((p) => (p[id] ? p : { ...p, [id]: new Set(animais) }));
    toggleInducao(id);
  };
  const toggleAnimalInducao = (id: string, numero: string) => setInducaoChecks((p) => {
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
    try { setAgenda(await fetchAgenda(data, diasJanela)); setErro(null); }
    catch (e: any) { setAgenda(null); setErro(e?.message || "erro desconhecido"); }
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
  // Indução de lactação concluídas — mesma ideia (desfazer se marcado por engano).
  const [inducaoConcluidos, setInducaoConcluidos] = useState<any[]>([]);
  const carregarConcluidosInducao = useCallback(async () => {
    try { setInducaoConcluidos(await fetchProtocoloInducaoConcluidos()); } catch { setInducaoConcluidos([]); }
  }, []);
  useEffect(() => { carregarConcluidosInducao(); }, [carregarConcluidosInducao]);
  const [desfazendo, setDesfazendo] = useState<Set<string>>(new Set());
  const desfazerIatf = async (id: string) => {
    setDesfazendo((p) => new Set(p).add(id));
    try { await desmarcarEventoRealizado(id); await Promise.all([carregar(), carregarConcluidos(), carregarConcluidosInducao()]); mostrarFeedback("Desfeito."); }
    catch (e: any) { mostrarFeedback(e.message, true); }
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

  // Protocolo IATF: qual medicamento/frasco foi aplicado em cada hormônio do
  // dia (ex.: D9). Chave = eventoId → índice do hormônio → estoque_id escolhido.
  const [medIatf, setMedIatf] = useState<Record<string, Record<number, number | null>>>({});
  const escolherMedIatf = (eventoId: string, idx: number, estoqueId: number | null) =>
    setMedIatf((p) => ({ ...p, [eventoId]: { ...(p[eventoId] || {}), [idx]: estoqueId } }));

  const [marcando, setMarcando] = useState<Set<string>>(new Set());
  const marcarRealizado = async (eventoId: string, animais?: string[], hormonios?: any[]) => {
    setMarcando((p) => new Set(p).add(eventoId));
    try {
      // Monta os medicamentos aplicados (com o frasco escolhido) a partir dos
      // hormônios do dia e da seleção do usuário.
      const sel = medIatf[eventoId] || {};
      const medicamentos = (hormonios || []).map((h: any, idx: number) => {
        const estoqueId = sel[idx] ?? (h.opcoes?.length === 1 ? h.opcoes[0].estoque_id : null);
        const op = (h.opcoes || []).find((o: any) => o.estoque_id === estoqueId);
        return { produto: op?.nome || h.produto, estoque_id: estoqueId ?? undefined, dose: h.dose, unidade: h.unidade, via: h.via };
      }).filter((m: any) => m.produto);
      await marcarEventoRealizado(eventoId, animais, medicamentos);
      cancelarConfirmacao(eventoId);
      await carregar();
      if (eventoId.startsWith("protocolo_iatf_")) await carregarConcluidos();
      if (eventoId.startsWith("protocolo_inducao_")) await carregarConcluidosInducao();
      mostrarFeedback("Atividade marcada como realizada.");
    }
    catch (e: any) { mostrarFeedback(e.message, true); }
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
      <button className="btn-ghost" style={{ fontSize: "0.68rem" }} title="Marcar como realizado" disabled={marcando.has(chave)} onClick={(e) => { e.stopPropagation(); pedirConfirmacao(chave); }}>
        <CheckCircle2 size={12} /> {compacto ? "" : "Realizado"}
      </button>
    );
  };

  const fecharModalNovoEvento = () => {
    setShowModal(false);
    setVinculo("nenhum");
    setAnimaisSelecionados(new Set());
    setLotesSelecionados(new Set());
    setForm({ data_evento: today(), descricao: "", categoria: "Gestão/Financeiro", observacao: "", tipo_evento: "", recorrente: false, recorrenciaNumero: "", recorrenciaFrequencia: "dias" });
  };

  const handleAddEvento = async () => {
    try {
      const numeroIntervalo = Math.max(1, Math.round(Number(form.recorrenciaNumero) || 0));
      await addEventoManual({
        data_evento: form.data_evento,
        descricao: form.descricao,
        categoria: form.categoria,
        observacao: form.observacao || undefined,
        numero_animal: vinculo === "animal" && animaisSelecionados.size ? Array.from(animaisSelecionados).join(",") : undefined,
        lotes: vinculo === "lote" && lotesSelecionados.size ? Array.from(lotesSelecionados).join(",") : undefined,
        tipo_evento: form.tipo_evento || undefined,
        recorrente: form.recorrente,
        intervalo_dias: form.recorrente && form.recorrenciaFrequencia === "dias" ? numeroIntervalo : undefined,
        intervalo_meses: form.recorrente && form.recorrenciaFrequencia === "meses" ? numeroIntervalo : undefined,
      });
      fecharModalNovoEvento();
      carregar();
      mostrarFeedback("Evento adicionado.");
    } catch (e: any) { mostrarFeedback(e.message, true); }
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
        } else if (e.tipo === "protocolo_inducao") {
          linhas.push({ tipo: "inducao", e });
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
                          <td style={{ fontWeight: e.numero_animal ? 700 : 400 }}>{e.numero_animal || (e.lote ? `Lote: ${e.lote}` : "—")}</td>
                          <td style={{ fontSize: "0.83rem" }}>{e.descricao}</td>
                          <td style={{ color: "var(--text-muted)", fontSize: "0.78rem", whiteSpace: "pre-line", maxWidth: "26rem" }}>{e.observacao || "—"}</td>
                          <td style={{ fontSize: "0.7rem", color: e.fonte === "manual" ? "var(--amber)" : "var(--text-muted)" }}>{e.fonte === "manual" ? "manual" : "auto"}</td>
                          <td>
                            {(e as any).link ? (
                              <div className="flex flex-col gap-1" style={{ alignItems: "flex-start" }}>
                                <a href={(e as any).link} className="btn-primary" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", whiteSpace: "nowrap" }} title="Abrir a tela de importação">
                                  <ExternalLink size={12} /> Importar agora
                                </a>
                                <BotaoRealizado chave={e.id} onConfirmar={() => marcarRealizado(e.id)} />
                              </div>
                            ) : e.categoria === "alimentacao" ? (
                              <a href={`/lancamentos?ir=alimentacao_dieta&lote=${encodeURIComponent(e.lote ?? "")}`} className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                                <Wheat size={12} /> Ir para Dieta
                              </a>
                            ) : (e as any).tipo === "evento_sanitario" || (e as any).tipo === "calendario_sanitario" ? (
                              (() => {
                                // Sempre vai para a tela de Preventiva (não a de Curativa) — é o
                                // único formulário que já sabe tratar exame (sem produto/dose) e
                                // vacina/tratamento (com baixa de estoque) da forma certa.
                                const ev = e as any;
                                const p = new URLSearchParams({ ir: "preventivo_aplicacao", evento_agenda: e.id });
                                if (ev.evento_sanitario_id) p.set("evento_sanitario_id", String(ev.evento_sanitario_id));
                                if (e.numero_animal) p.set("numero_matriz", e.numero_animal);
                                if (e.data) p.set("data", e.data);
                                return (
                                  <a href={`/lancamentos?${p.toString()}`} className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} title="Aplicar/confirmar (gera a aplicação, a saída de estoque, ou só marca o exame como feito)">
                                    <Syringe size={12} /> Dar baixa (aplicar)
                                  </a>
                                );
                              })()
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
                              {!ehD11 && <BotaoRealizado chave={e.id} onConfirmar={() => marcarRealizado(e.id, undefined, e.hormonios)} />}
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
                                  {!ehD11 && (e.hormonios?.length ?? 0) > 0 && (
                                    <div style={{ marginTop: "0.6rem", background: "var(--surface)", border: "1px solid var(--dourado)", borderRadius: 8, padding: "0.55rem 0.7rem" }}>
                                      <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.35rem" }}>
                                        Qual medicamento/frasco você está usando?
                                      </div>
                                      {e.hormonios.map((h: any, idx: number) => {
                                        const sel = medIatf[e.id]?.[idx] ?? (h.opcoes?.length === 1 ? h.opcoes[0].estoque_id : "");
                                        return (
                                          <div key={idx} className="flex items-center gap-2" style={{ marginBottom: "0.3rem", flexWrap: "wrap" }}>
                                            <span style={{ fontSize: "0.76rem", minWidth: 130 }}>
                                              {h.produto}{h.dose ? ` · ${h.dose}${h.unidade || ""}` : ""}
                                            </span>
                                            {(h.opcoes?.length ?? 0) === 0 ? (
                                              <span style={{ fontSize: "0.72rem", color: "var(--amber)" }}>Sem medicamento em estoque para este princípio.</span>
                                            ) : (
                                              <select style={{ width: "auto", minWidth: 220, fontSize: "0.76rem", padding: "0.3rem 0.5rem", borderRadius: 6, background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }} value={sel ?? ""}
                                                onChange={(ev) => escolherMedIatf(e.id, idx, ev.target.value ? Number(ev.target.value) : null)}>
                                                <option value="">Selecione o frasco…</option>
                                                {h.opcoes.map((o: any) => (
                                                  <option key={o.estoque_id} value={o.estoque_id}>
                                                    {o.nome}{o.marca ? ` · ${o.marca}` : ""} — saldo {o.saldo} {o.unidade || ""}{!o.estoque_inicializado ? " (sem estoque inicial)" : ""}
                                                  </option>
                                                ))}
                                              </select>
                                            )}
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                  {!ehD11 && (
                                    <div className="flex items-center gap-2 mt-2">
                                      <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id) || !checks.size}
                                        onClick={() => marcarRealizado(e.id, Array.from(checks), e.hormonios)}>
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
                    if (linha.tipo === "inducao") {
                      const e = linha.e;
                      const abertoInducao = inducaoAbertos.has(e.id);
                      const checks = inducaoChecks[e.id] || new Set(e.animais);
                      return (
                        <React.Fragment key={`inducao-${i}`}>
                          <tr style={{ cursor: "pointer" }} onClick={() => abrirInducao(e.id, e.animais)}>
                            <td><span className={BADGE_CLASS["Produção"]} style={{ padding: "0.1rem 0.5rem", borderRadius: "4px", fontSize: "0.7rem", whiteSpace: "nowrap" }}>Produção</span></td>
                            <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{e.animais.length} animal(is)</td>
                            <td style={{ fontSize: "0.83rem" }}>
                              {abertoInducao ? <ChevronDown size={12} style={{ display: "inline", marginRight: "0.3rem" }} /> : <ChevronRight size={12} style={{ display: "inline", marginRight: "0.3rem" }} />}
                              {e.descricao}
                            </td>
                            <td style={{ color: "var(--amber)", fontSize: "0.78rem", fontWeight: e.observacao ? 700 : 400 }}>{e.observacao || "—"}</td>
                            <td style={{ fontSize: "0.7rem", color: "var(--amber)" }}>manual</td>
                            <td onClick={(ev) => ev.stopPropagation()}>
                              <BotaoRealizado chave={e.id} onConfirmar={() => marcarRealizado(e.id)} />
                            </td>
                          </tr>
                          {abertoInducao && (
                            <tr style={{ background: "var(--surface-2)" }}>
                              <td></td>
                              <td colSpan={5}>
                                <div style={{ padding: "0.5rem 0" }}>
                                  <p style={{ fontSize: "0.78rem", marginBottom: "0.2rem" }}>
                                    <Syringe size={12} style={{ display: "inline", marginRight: "0.3rem" }} />
                                    <strong>Medicamento(s) do dia:</strong> {e.medicamentos}
                                  </p>
                                  {e.observacao && (
                                    <p style={{ fontSize: "0.78rem", marginBottom: "0.4rem", color: "var(--amber)" }}>
                                      <strong>Observação para o funcionário:</strong> {e.observacao}
                                    </p>
                                  )}
                                  <table className="fazenda-table" style={{ margin: 0 }}>
                                    <thead><tr><th></th><th>Nº</th></tr></thead>
                                    <tbody>
                                      {e.animais.map((numero: string) => (
                                        <tr key={numero}>
                                          <td><input type="checkbox" checked={checks.has(numero)} onChange={() => toggleAnimalInducao(e.id, numero)} /></td>
                                          <td style={{ fontWeight: 700 }}>{numero}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                  <div className="flex items-center gap-2 mt-2">
                                    <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id) || !checks.size}
                                      onClick={() => marcarRealizado(e.id, Array.from(checks))}>
                                      <Check size={12} /> Confirmar realizado ({checks.size}/{e.animais.length})
                                    </button>
                                  </div>
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
  const bstNuncaAplicados = agenda?.bst_nunca_aplicados || [];

  // Próxima visita reprodutiva/BST — ancorada no serviço mais recente do
  // rebanho (calculada no backend; ex.: último serviço 03/07 -> visita 24/07).
  const fmtCurta = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) : null);
  const proxVisita = fmtCurta(agenda?.proxima_visita_iatf);
  const proxBST = fmtCurta(agenda?.proxima_visita_bst);

  const ordIatf = useOrdenacao(candidatas);
  const ordBstAptos = useOrdenacao(bstAptos);
  const ordBstExcl = useOrdenacao(bstExcl);
  const ordBstNunca = useOrdenacao(bstNuncaAplicados);
  const [listaAtiva, setListaAtiva] = useState<Set<string>>(new Set());
  const toggleLista = (k: string) => setListaAtiva((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });

  // Ação rápida "Adicionar à agenda" a partir de uma linha de candidata/apta —
  // cria o evento manual já vinculado ao animal, sem precisar abrir o modal geral.
  const [agendandoNumero, setAgendandoNumero] = useState<string | null>(null);
  const agendarAnimal = async (numero: string, descricao: string, categoria: string) => {
    setAgendandoNumero(numero);
    try {
      await addEventoManual({ data_evento: today(), descricao, categoria, numero_animal: numero });
      carregar();
      mostrarFeedback(`Evento adicionado à agenda para o animal ${numero}.`);
    } catch (e: any) { mostrarFeedback(e.message, true); }
    finally { setAgendandoNumero(null); }
  };
  const BotaoAgendar = ({ numero, descricao, categoria }: { numero: string; descricao: string; categoria: string }) => (
    <button className="btn-ghost" disabled={agendandoNumero === numero} title="Adicionar à agenda" onClick={() => agendarAnimal(numero, descricao, categoria)}
      style={{ fontSize: "0.72rem", padding: "0.15rem 0.5rem" }}>
      <Plus size={12} /> {agendandoNumero === numero ? "…" : "Agendar"}
    </button>
  );

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
        <div className="flex items-end gap-2">
          <div>
            <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Data de referência</label>
            <input
              type="date"
              value={data}
              onChange={e => setData(e.target.value)}
              className="btn-ghost"
              title="Data de referência: ancora toda a agenda — eventos, contas e visitas são calculados a partir dela."
              style={{ padding: "0.4rem 0.75rem", fontSize: "0.875rem", background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: "8px" }}
            />
          </div>
          <button onClick={carregar} className="btn-ghost" title="Recarregar">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
          <button onClick={() => setShowModal(true)} className="btn-primary">
            <Plus size={16} /> Adicionar
          </button>
        </div>
      </div>

      {/* Erro de carregamento — distinto do estado "sem dados" */}
      {erro && (
        <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Não foi possível carregar a agenda: {erro}</span></div>
      )}

      {/* Feedback transitório de ações (sucesso em verde, erro em vermelho) */}
      {feedback && (
        <div className="mb-4" style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", padding: "0.5rem 0.9rem", borderRadius: "8px",
          background: feedback.erro ? "rgba(192,57,43,0.15)" : "rgba(20,83,45,0.35)",
          border: "1px solid " + (feedback.erro ? "var(--red)" : "var(--green-light)"),
          color: feedback.erro ? "var(--red)" : "var(--green-light)" }}>
          {feedback.erro ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />} {feedback.msg}
        </div>
      )}

      {/* KPIs bloco */}
      {loading && !agenda ? (
        <div className="mb-5"><p style={{ color: "var(--text-muted)", padding: "1rem" }}>Carregando…</p></div>
      ) : agenda && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
          {[
            { label: "Candidatas IATF", value: agenda.totais?.candidatas_iatf, color: "var(--blue)",
              list: candidatas.map((c: any) => ({ numero: c.numero_matriz, sit_rep: c.sit_rep, del_dias: c.del_dias })) },
            { label: "BST Aptos", value: bstAptos.length, color: "var(--green-light)",
              list: bstAptos.map((b: any) => ({ numero: b.numero_matriz, grupo_primario: b.grupo, del_dias: b.del_dias })) },
            { label: "BST Excluídos", value: bstExcl.length, color: "var(--amber)",
              list: bstExcl.map((b: any) => ({ numero: b.numero_matriz, grupo_primario: b.grupo, del_dias: b.del_dias })) },
            { label: "BST Nunca aplicadas", value: bstNuncaAplicados.length, color: "var(--blue)",
              list: bstNuncaAplicados.map((b: any) => ({ numero: b.numero_matriz, grupo_primario: b.grupo, del_dias: b.del_dias })) },
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
      {(candidatas.length > 0 || bstAptos.length > 0 || bstExcl.length > 0 || bstNuncaAplicados.length > 0) && (
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-2" style={{ flexWrap: "wrap" }}>
            {candidatas.length > 0 && (
              <button onClick={() => toggleLista("iatf")} title="Mostrar/ocultar as fêmeas candidatas à IATF"
                style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (listaAtiva.has("iatf") ? "var(--dourado)" : "var(--border)"),
                  background: listaAtiva.has("iatf") ? "rgba(94,26,46,0.4)" : "transparent",
                  color: listaAtiva.has("iatf") ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: listaAtiva.has("iatf") ? 700 : 500 }}>
                {listaAtiva.has("iatf") ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Candidatas IATF ({candidatas.length}){proxVisita && <span style={{ fontWeight: 400, fontSize: "0.72rem" }}> — próx. visita {proxVisita}</span>}
              </button>
            )}
            {bstAptos.length > 0 && (
              <button onClick={() => toggleLista("bstAptos")} title="Mostrar/ocultar as fêmeas aptas ao BST"
                style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (listaAtiva.has("bstAptos") ? "var(--green-light)" : "var(--border)"),
                  background: listaAtiva.has("bstAptos") ? "rgba(20,83,45,0.4)" : "transparent",
                  color: listaAtiva.has("bstAptos") ? "var(--green-light)" : "var(--text-muted)", fontWeight: listaAtiva.has("bstAptos") ? 700 : 500 }}>
                {listaAtiva.has("bstAptos") ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                BST — Aptas ({bstAptos.length}){proxBST && <span style={{ fontWeight: 400, fontSize: "0.72rem" }}> — próx. BST {proxBST}</span>}
              </button>
            )}
            {bstExcl.length > 0 && (
              <button onClick={() => toggleLista("bstExcl")} title="Mostrar/ocultar as fêmeas excluídas do BST e o motivo"
                style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (listaAtiva.has("bstExcl") ? "var(--amber)" : "var(--border)"),
                  background: listaAtiva.has("bstExcl") ? "rgba(120,90,10,0.35)" : "transparent",
                  color: listaAtiva.has("bstExcl") ? "var(--amber)" : "var(--text-muted)", fontWeight: listaAtiva.has("bstExcl") ? 700 : 500 }}>
                {listaAtiva.has("bstExcl") ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                BST — Excluídos ({bstExcl.length})
              </button>
            )}
            {bstNuncaAplicados.length > 0 && (
              <button onClick={() => toggleLista("bstNunca")} title="Mostrar/ocultar as fêmeas aptas ao BST que nunca receberam aplicação"
                style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
                  border: "1px solid " + (listaAtiva.has("bstNunca") ? "var(--blue)" : "var(--border)"),
                  background: listaAtiva.has("bstNunca") ? "rgba(30,64,124,0.35)" : "transparent",
                  color: listaAtiva.has("bstNunca") ? "var(--blue)" : "var(--text-muted)", fontWeight: listaAtiva.has("bstNunca") ? 700 : 500 }}>
                {listaAtiva.has("bstNunca") ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                BST — Nunca aplicadas ({bstNuncaAplicados.length})
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
                  <th></th>
                </tr></thead>
                <tbody>
                  {ordIatf.linhasOrdenadas.map((c: any, i: number) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 700 }}>{c.numero_matriz}</td>
                      <td><span className="badge-reprodutivo" style={{ padding: "0.1rem 0.4rem", borderRadius: "4px", fontSize: "0.75rem" }}>{c.sit_rep}</span></td>
                      <td>{c.del_dias ?? "—"}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{c.motivo}</td>
                      <td><BotaoAgendar numero={c.numero_matriz} descricao="IATF: candidata a novo serviço" categoria="Reprodutivo" /></td>
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
                  <th></th>
                </tr></thead>
                <tbody>
                  {ordBstAptos.linhasOrdenadas.map((b: any, i: number) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 700 }}>{b.numero_matriz}</td>
                      <td style={{ fontSize: "0.78rem" }}>{b.grupo}</td>
                      <td>{b.del_dias ?? "—"}</td>
                      <td><BotaoAgendar numero={b.numero_matriz} descricao="Aplicar BST (Lactotropin/Boostin)" categoria="Sanidade" /></td>
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

          {listaAtiva.has("bstNunca") && (
            <div className="card mb-2" style={{ overflowX: "auto" }}>
              <table className="fazenda-table">
                <thead><tr>
                  <th></th>
                  <ThOrdenavel label="Nº Animal" campo="numero_matriz" coluna={ordBstNunca.coluna} dir={ordBstNunca.dir} ordenar={ordBstNunca.ordenar} />
                  <ThOrdenavel label="Grupo" campo="grupo" coluna={ordBstNunca.coluna} dir={ordBstNunca.dir} ordenar={ordBstNunca.ordenar} />
                  <ThOrdenavel label="DEL" campo="del_dias" coluna={ordBstNunca.coluna} dir={ordBstNunca.dir} ordenar={ordBstNunca.ordenar} />
                  <th>Motivo</th>
                  <th></th>
                </tr></thead>
                <tbody>
                  {ordBstNunca.linhasOrdenadas.map((b: any, i: number) => (
                    <tr key={i}>
                      <td>
                        {b.requer_reanalise && (
                          <span title="Excluída manualmente do BST — revisar" style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: "var(--amber)" }} />
                        )}
                      </td>
                      <td style={{ fontWeight: 700 }}>{b.numero_matriz}</td>
                      <td style={{ fontSize: "0.78rem" }}>{b.grupo}</td>
                      <td>{b.del_dias ?? "—"}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{b.requer_reanalise ? (b.motivo_exclusao || "Revisar") : "Nunca aplicada — apta na próxima"}</td>
                      <td><BotaoAgendar numero={b.numero_matriz} descricao="Aplicar BST (Lactotropin/Boostin) — nunca aplicada" categoria="Sanidade" /></td>
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

      {/* Indução de lactação — concluídas recentemente, com opção de desfazer */}
      {inducaoConcluidos.length > 0 && (
        <div className="card mb-4">
          <button onClick={() => togglePainel("inducaoConcluidos")} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.5rem", background: "none", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left", padding: 0 }}>
            {paineis.has("inducaoConcluidos") ? <ChevronDown size={15} style={{ color: "var(--text-muted)" }} /> : <ChevronRight size={15} style={{ color: "var(--text-muted)" }} />}
            <span className="card-header" style={{ margin: 0 }}>Indução de lactação — concluídas ({inducaoConcluidos.length})</span>
          </button>
          {paineis.has("inducaoConcluidos") && (
            <div className="overflow-x-auto mt-3">
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th>Protocolo</th><th>Dia</th><th>Animais</th><th>Concluído em</th><th></th></tr></thead>
                <tbody>
                  {inducaoConcluidos.map((g: any) => (
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
        {loading ? (
          <p style={{ color: "var(--text-muted)", padding: "1rem", textAlign: "center", fontSize: "0.85rem" }}>Carregando…</p>
        ) : eventosPendentes.length > 0 ? (
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
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50, padding: "1rem" }}>
          <div className="card" style={{ width: "520px", maxWidth: "95vw", maxHeight: "90vh", overflowY: "auto" }}>
            <div className="card-header mb-4">Adicionar Evento Manual</div>
            <div className="space-y-3">
              {[
                { label: "Data", key: "data_evento", type: "date" },
                { label: "Descrição", key: "descricao", type: "text" },
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
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Vincular a (opcional)</label>
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                  {[
                    { v: "nenhum", label: "Nenhum (tarefa livre)" },
                    { v: "animal", label: "Animal(is)" },
                    { v: "lote", label: "Lote(s)" },
                  ].map((o) => (
                    <button key={o.v} type="button" title={o.label}
                      onClick={() => { setVinculo(o.v as any); if (o.v === "nenhum") { setAnimaisSelecionados(new Set()); setLotesSelecionados(new Set()); } }}
                      style={{ fontSize: "0.75rem", padding: "0.3rem 0.7rem", borderRadius: "999px", cursor: "pointer",
                        border: "1px solid " + (vinculo === o.v ? "var(--dourado)" : "var(--border)"),
                        background: vinculo === o.v ? "var(--dourado)" : "transparent",
                        color: vinculo === o.v ? "#1a1a1a" : "var(--text-muted)", fontWeight: vinculo === o.v ? 700 : 400 }}>
                      {o.label}
                    </button>
                  ))}
                </div>
                {vinculo === "animal" && (
                  <div className="mt-2">
                    <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => abrirPicker("animal")}>
                      {animaisSelecionados.size ? `${animaisSelecionados.size} animal(is) selecionado(s) — alterar` : "Selecionar animais…"}
                    </button>
                  </div>
                )}
                {vinculo === "lote" && (
                  <div className="mt-2">
                    <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => abrirPicker("lote")}>
                      {lotesSelecionados.size ? `${lotesSelecionados.size} lote(s) selecionado(s) — alterar` : "Selecionar lotes…"}
                    </button>
                  </div>
                )}
              </div>

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

              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Tipo de evento (opcional)</label>
                <select
                  value={form.tipo_evento}
                  onChange={e => setForm(p => ({ ...p, tipo_evento: e.target.value }))}
                  style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}
                >
                  <option value="">—</option>
                  {TIPOS_EVENTO.map(t => <option key={t}>{t}</option>)}
                </select>
              </div>

              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Observação (opcional)</label>
                <input
                  type="text" value={form.observacao}
                  onChange={e => setForm(p => ({ ...p, observacao: e.target.value }))}
                  style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}
                />
              </div>

              <div>
                <label className="flex items-center gap-2" style={{ fontSize: "0.82rem" }}>
                  <input type="checkbox" checked={form.recorrente} onChange={e => setForm(p => ({ ...p, recorrente: e.target.checked }))} /> Repetir este evento
                </label>
                {form.recorrente && (
                  <div className="flex items-center gap-2 mt-2">
                    <span style={{ fontSize: "0.8rem" }}>A cada</span>
                    <input type="number" min={1} value={form.recorrenciaNumero}
                      onChange={e => setForm(p => ({ ...p, recorrenciaNumero: e.target.value }))}
                      style={{ width: "5rem", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.5rem", color: "var(--text)", fontSize: "0.875rem" }} />
                    <select value={form.recorrenciaFrequencia}
                      onChange={e => setForm(p => ({ ...p, recorrenciaFrequencia: e.target.value as "dias" | "meses" }))}
                      style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}>
                      <option value="dias">dias</option>
                      <option value="meses">meses</option>
                    </select>
                  </div>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={fecharModalNovoEvento} className="btn-ghost">Cancelar</button>
              <button onClick={handleAddEvento} className="btn-primary" disabled={!form.descricao || (form.recorrente && !form.recorrenciaNumero)}>Salvar</button>
            </div>
          </div>
        </div>
      )}

      {/* Picker de animais ou lotes para o vínculo do evento manual */}
      {pickerAberto && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 55, padding: "1rem" }}>
          <div className="card" style={{ width: "640px", maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="card-header mb-3">{pickerAberto === "animal" ? "Selecionar animal(is)" : "Selecionar lote(s)"}</div>
            {pickerAberto === "animal" ? (
              <SelecaoAnimaisTabela animais={animaisTodos} selecionados={animaisSelecionados} toggle={toggleAnimalSelecionado} toggleTodos={toggleTodosAnimais} colunas={pickerColunasAnimais} />
            ) : (
              <SelecaoLotesTabela lotes={lotesTodos} selecionados={lotesSelecionados} toggle={toggleLoteSelecionado} toggleTodos={toggleTodosLotes} />
            )}
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setPickerAberto(null)} className="btn-primary">OK</button>
            </div>
          </div>
        </div>
      )}

      {modal && <AnimalModal title={modal.title} animais={modal.list} onClose={() => setModal(null)} />}
    </div>
  );
}
