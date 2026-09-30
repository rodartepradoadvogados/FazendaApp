"use client";
// Protocolos › Acompanhamento (sanitário preventivo): o que já está agendado.
// Fatia 8 do planejamento unificado; mockup fluxo-completo (proto-acomp.js).
//
// Só o AGENDAMENTO aparece aqui (a lista de espera fica em Aplicar e nunca na
// Agenda). Aplicar abre a MESMA gaveta que a Agenda abre no dia; adiar exige
// motivo em chips; cancelar exige motivo e diz o que fazer com os animais;
// rascunho ("Em montagem") continua de onde parou.
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, Ban, CalendarClock, CalendarDays, CalendarPlus, Check, ChevronLeft, ChevronRight, Clock, ListChecks, ListOrdered, Pencil, Search, Syringe, Undo2 } from "lucide-react";
import {
  adiarAgendamentoPreventivo, cancelarAgendamentoPreventivo, confirmarRascunhoAgendamento, editarChecklistAgendamento, ehAdmin,
  estornarAplicacaoPreventiva, fetchAcompanhamentoPreventivo, fetchContextoAplicar, reabrirAgendamentoParaEditar, tirarAnimalDoAgendamento,
  type MotivoTirarAnimal,
  type AcompanhamentoPreventivo as Dados, type AgendamentoAcompanhamento, type ContextoAplicar, type ItemChecklistAg,
} from "@/lib/api";
import { GavetaLancamento } from "@/components/lancamentos/GavetaLancamento";
import { Indicador, TelaSkeleton } from "@/components/ui";
import { GavetaAplicar } from "./GavetaAplicar";
import { BannerReagentes, dataHoraLocal, FASE_ROTULO, VERBO_APLICAR } from "./exameComum";
import { FinanceiroVivo } from "./FinanceiroAgendamento";
import {
  ChecklistItensExistentes, ChecklistMontagem, checklistParaPayload, checklistVazio, validarChecklist, type ChecklistDraft,
} from "./ChecklistAgendamento";
import {
  brl, Chips, ChecklistSelo, dataCurta, diaSemana, EstadoAgPill, ForaJanelaBadge, hojeIso, inputStyle, labelStyle, maisDiasIso,
  MOTIVOS_ADIAR, MOTIVOS_CANCELAR, MOTIVOS_ESTORNO, notaStyle, Pill, plural, textoMotivo, dataHoraCurta,
} from "./preventivoComum";

type Painel = { tipo: "detalhe" | "aplicar" | "montar"; id: number } | null;

export function AcompanhamentoPreventivo({ onIrLista, onVerConcluidos }: { onIrLista: () => void; onVerConcluidos: () => void }) {
  const [dados, setDados] = useState<Dados | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [recarga, setRecarga] = useState(0);
  const [protocolo, setProtocolo] = useState("");
  const [estado, setEstado] = useState("");
  const [busca, setBusca] = useState("");
  const [painel, setPainel] = useState<Painel>(null);
  const [visao, setVisao] = useState<"lista" | "calendario">(() => {
    try { return localStorage.getItem("acomp_visao") === "calendario" ? "calendario" : "lista"; } catch { return "lista"; }
  });
  const escolherVisao = (v: "lista" | "calendario") => { setVisao(v); try { localStorage.setItem("acomp_visao", v); } catch { /* sem armazenamento: segue */ } };
  const recarregar = useCallback(() => setRecarga((n) => n + 1), []);

  useEffect(() => {
    let vivo = true;
    fetchAcompanhamentoPreventivo().then((d) => { if (vivo) { setDados(d); setErro(null); } })
      .catch((e) => { if (vivo) setErro(e.message || "Erro ao carregar o acompanhamento"); });
    return () => { vivo = false; };
  }, [recarga]);

  const protocolos = useMemo(() => {
    const m = new Map<number, string>();
    (dados?.agendamentos || []).forEach((a) => m.set(a.calendario_sanitario_id, a.protocolo_nome));
    return Array.from(m.entries());
  }, [dados]);

  const lista = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const ordem: Record<string, number> = { atrasado: 0, hoje: 1, adiado: 2, agendado: 3, em_montagem: 4 };
    return (dados?.agendamentos || [])
      .filter((a) => (!protocolo || String(a.calendario_sanitario_id) === protocolo) && (!estado || a.estado_visual === estado)
        && (!q || `${a.protocolo_nome} ${a.lotes.join(" ")} ${a.responsavel.nome}`.toLowerCase().includes(q)))
      .sort((a, b) => (ordem[a.estado_visual] - ordem[b.estado_visual]) || `${a.data_evento} ${a.hora || ""}`.localeCompare(`${b.data_evento} ${b.hora || ""}`));
  }, [dados, protocolo, estado, busca]);

  if (erro) return <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{erro}</span></div>;
  if (!dados) return <TelaSkeleton kpis={3} />;

  return (
    <div className="le-raiz">
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", flexWrap: "wrap", alignItems: "flex-start", marginBottom: "0.9rem" }}>
        <div>
          <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>Acompanhamento do preventivo</h2>
          <p style={notaStyle}>O que já está agendado. Aplique aqui ou pela Agenda, no dia da aplicação.</p>
        </div>
        <button type="button" className="btn-secondary" onClick={onIrLista}><ListChecks size={14} /> Lista de espera</button>
      </div>

      <BannerReagentes />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
        <Indicador categoria="sanidade" icon={Clock} valor={dados.totais.hoje} rotulo="Hoje · para aplicar" cor={dados.totais.hoje ? "var(--amber)" : undefined}
                   onClick={() => setEstado(estado === "hoje" ? "" : "hoje")} title="Filtrar os de hoje" />
        <Indicador categoria="sanidade" icon={AlertTriangle} valor={dados.totais.atrasados} rotulo="Atrasados · passou o dia, ninguém aplicou" cor={dados.totais.atrasados ? "var(--red)" : undefined}
                   onClick={() => setEstado(estado === "atrasado" ? "" : "atrasado")} title="Filtrar os atrasados" />
        <Indicador categoria="sanidade" icon={CalendarClock} valor={dados.totais.agendados} rotulo="Agendados · ao todo, incluindo hoje"
                   onClick={() => setEstado(estado === "agendado" ? "" : "agendado")} title="Filtrar os agendados" />
      </div>

      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginBottom: "0.8rem", alignItems: "center" }}>
        <div style={{ flex: "0 1 240px" }}>
          <label className="sr-only" htmlFor="ac-p">Protocolo</label>
          <select id="ac-p" style={inputStyle} value={protocolo} onChange={(e) => setProtocolo(e.target.value)}>
            <option value="">Todos os protocolos</option>
            {protocolos.map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
          </select>
        </div>
        <div style={{ flex: "0 1 200px" }}>
          <label className="sr-only" htmlFor="ac-e">Estado</label>
          <select id="ac-e" style={inputStyle} value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="">Todos os estados</option>
            <option value="em_montagem">Em montagem</option><option value="agendado">Agendado</option><option value="hoje">Hoje</option>
            <option value="atrasado">Atrasado</option><option value="adiado">Adiado</option>
          </select>
        </div>
        <div style={{ position: "relative", flex: "1 1 220px" }}>
          <Search size={14} style={{ position: "absolute", left: 8, top: 11, color: "var(--text-muted)" }} />
          <input type="search" aria-label="Buscar protocolo, lote ou responsável" style={{ ...inputStyle, paddingLeft: 28 }} placeholder="Buscar protocolo, lote ou responsável…" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </div>
        <div role="group" aria-label="Visão" style={{ display: "inline-flex", gap: 4 }}>
          <button type="button" className={visao === "lista" ? "btn-secondary" : "btn-ghost"} aria-pressed={visao === "lista"} onClick={() => escolherVisao("lista")}><ListOrdered size={14} /> Lista</button>
          <button type="button" className={visao === "calendario" ? "btn-secondary" : "btn-ghost"} aria-pressed={visao === "calendario"} data-testid="visao-calendario" onClick={() => escolherVisao("calendario")}><CalendarDays size={14} /> Calendário</button>
        </div>
      </div>

      {visao === "calendario" && (
        <CalendarioAcompanhamento agendamentos={lista} hoje={dados.hoje || hojeIso()} onAbrir={(id) => setPainel({ tipo: "detalhe", id })} />
      )}

      {visao === "calendario" ? null : !lista.length ? (
        <div className="card" style={{ textAlign: "center", padding: "2rem 1rem" }}>
          <CalendarClock size={28} style={{ color: "var(--text-muted)", margin: "0 auto 0.6rem" }} />
          <p style={{ fontWeight: 700 }}>{dados.agendamentos.length ? "Nada com esses filtros" : "Nada agendado"}</p>
          <p style={{ ...notaStyle, margin: "0.3rem 0 0.9rem" }}>{dados.agendamentos.length ? "Tire um filtro para ver o resto." : "Veja a lista de espera para montar o primeiro agendamento."}</p>
          {!dados.agendamentos.length && <button type="button" className="btn-primary-gold" onClick={onIrLista}><ListChecks size={14} /> Ver lista de espera</button>}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="fazenda-table" aria-label="Agendamentos do preventivo">
            <thead><tr><th>Estado</th><th>Protocolo</th><th>Para quem</th><th>Data e hora</th><th>Responsável</th><th>Checklist</th><th><span className="sr-only">Ações</span></th></tr></thead>
            <tbody>
              {lista.map((a) => (
                <tr key={a.id} tabIndex={0} style={{ cursor: "pointer" }} onClick={() => setPainel({ tipo: "detalhe", id: a.id })}
                    onKeyDown={(e) => { if (e.key === "Enter") setPainel({ tipo: "detalhe", id: a.id }); }} aria-label={`Abrir ${a.protocolo_nome}`}
                    className={a.estado_visual === "atrasado" ? "row-atrasada" : undefined}>
                  <td><EstadoAgPill estado={a.estado_visual} /></td>
                  <td>
                    <b style={{ fontSize: "0.85rem" }}>{a.protocolo_nome}</b>
                    <span style={{ ...notaStyle, display: "block" }}>{a.lotes.length > 2 ? `${a.lotes.length} lotes` : a.lotes.join(", ") || "—"}</span>
                    {a.fase && (
                      <span style={{ display: "inline-flex", marginTop: 4 }} title={a.fase === "leitura" && a.leitura_prevista_em ? `Leitura a partir de ${dataHoraLocal(a.leitura_prevista_em)}` : undefined}>
                        <Pill cor={a.fase === "leitura" ? "var(--dourado-light)" : "var(--text-muted)"}>{FASE_ROTULO[a.fase]}</Pill>
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: "0.82rem" }}>
                    {a.animais_total} {plural(a.animais_total, "animal", "animais")}
                    {a.animais_fora_janela > 0 && <div><ForaJanelaBadge n={a.animais_fora_janela} /></div>}
                    {!!a.animais_ja_aplicados && <div><Pill cor="var(--red)" title="Já têm o produto aplicado neste ciclo (Sanidade). A gaveta Aplicar pede a decisão de cada um.">{a.animais_ja_aplicados} {plural(a.animais_ja_aplicados, "animal já aplicado", "animais já aplicados")}</Pill></div>}
                  </td>
                  <td style={{ fontSize: "0.82rem" }}>
                    {diaSemana(a.data_evento)} {dataCurta(a.data_evento).slice(0, 5)}
                    <span style={{ ...notaStyle, display: "block" }}>
                      {a.hora || "sem hora"}{a.estado_visual === "adiado" && a.data_antes_do_adiamento ? ` · antes ${dataCurta(a.data_antes_do_adiamento).slice(0, 5)}` : ""}
                    </span>
                  </td>
                  <td style={{ fontSize: "0.82rem" }}>{a.responsavel.nome}{a.responsavel.crmv && <span style={{ ...notaStyle, display: "block" }}>{a.responsavel.crmv}</span>}</td>
                  <td>
                    <ChecklistSelo ck={a.checklist} />
                    {a.financeiro && (a.financeiro.contas_ativas > 0 || a.financeiro.custo_previsto != null || a.financeiro.custo_a_informar) && (
                      <span style={{ ...notaStyle, display: "block", marginTop: 2 }}>
                        {a.financeiro.custo_previsto != null ? `Custo ${brl(a.financeiro.custo_previsto)}` : "Custo a informar"}
                        {a.financeiro.contas_ativas > 0 ? ` · conta a pagar ${brl(a.financeiro.conta_a_pagar_total)}` : ""}
                      </span>
                    )}
                  </td>
                  <td onClick={(e) => e.stopPropagation()} style={{ whiteSpace: "nowrap" }}>
                    {a.status === "em_montagem" ? (
                      <button type="button" className="btn-secondary" onClick={() => setPainel({ tipo: "montar", id: a.id })}><Pencil size={14} /> Continuar montando</button>
                    ) : (
                      <button type="button" className={a.data_evento > (dados.hoje || hojeIso()) ? "btn-secondary" : "btn-primary-gold"} onClick={() => setPainel({ tipo: "aplicar", id: a.id })}>
                        <Syringe size={14} /> {a.fase ? `${VERBO_APLICAR[a.fase]}${a.data_evento > (dados.hoje || hojeIso()) ? " antes" : ""}` : a.data_evento > (dados.hoje || hojeIso()) ? "Aplicar antes" : "Aplicar"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div role="note" style={{ ...notaStyle, display: "flex", flexWrap: "wrap", gap: "0.4rem 1rem", margin: "0.7rem 0" }}>
            <span style={{ color: "var(--green-light)" }}>Checklist resolvido</span><span style={{ color: "var(--amber)" }}>Itens pendentes: aplicar pede só a ciência</span>
            <span style={{ color: "var(--red)" }}>Veterinário não confirmou</span><span style={{ color: "var(--amber)" }}>Fora da janela: incluído por conta da fazenda</span>
          </div>
        </div>
      )}

      {painel?.tipo === "aplicar" && (
        <GavetaAplicar cronogramaId={painel.id} canal="Protocolos" onFechar={() => setPainel(null)} onMudou={recarregar}
                       onVerConcluidos={onVerConcluidos} />
      )}
      {painel && painel.tipo !== "aplicar" && (
        <GavetaAgendamento
          id={painel.id} modoInicial={painel.tipo} onFechar={() => setPainel(null)} onMudou={recarregar}
          onAplicar={() => setPainel({ tipo: "aplicar", id: painel.id })}
        />
      )}
    </div>
  );
}

// ───────────────────────── visão Calendário (mês) ─────────────────────────
const MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
const COR_ESTADO: Record<string, string> = { atrasado: "var(--red)", hoje: "var(--amber)", agendado: "var(--dourado-light)", adiado: "var(--text-muted)", em_montagem: "var(--amber)" };
const isoDia = (a: number, m: number, d: number) => `${a}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

function CalendarioAcompanhamento({ agendamentos, hoje, onAbrir }: { agendamentos: AgendamentoAcompanhamento[]; hoje: string; onAbrir: (id: number) => void }) {
  const [ano0, mes0] = hoje.split("-").map(Number);
  const [ref, setRef] = useState({ ano: ano0, mes: mes0 - 1 });
  const [sel, setSel] = useState<string>(hoje);
  const porDia = useMemo(() => {
    const m = new Map<string, AgendamentoAcompanhamento[]>();
    agendamentos.forEach((a) => { const l = m.get(a.data_evento) || []; l.push(a); m.set(a.data_evento, l); });
    return m;
  }, [agendamentos]);
  const primeiro = new Date(ref.ano, ref.mes, 1).getDay();
  const dias = new Date(ref.ano, ref.mes + 1, 0).getDate();
  const celulas: (number | null)[] = [...Array(primeiro).fill(null), ...Array.from({ length: dias }, (_, i) => i + 1)];
  while (celulas.length % 7) celulas.push(null);
  const mover = (d: number) => setRef((r) => { const t = new Date(r.ano, r.mes + d, 1); return { ano: t.getFullYear(), mes: t.getMonth() }; });
  const doDia = porDia.get(sel) || [];
  const noMes = agendamentos.filter((a) => a.data_evento.startsWith(`${ref.ano}-${String(ref.mes + 1).padStart(2, "0")}`)).length;
  return (
    <div className="card" data-testid="calendario-acompanhamento" style={{ padding: "0.8rem", marginBottom: "0.9rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.6rem" }}>
        <button type="button" className="btn-ghost" aria-label="Mês anterior" onClick={() => mover(-1)}><ChevronLeft size={16} /></button>
        <b style={{ flex: 1, textAlign: "center", fontSize: "0.95rem" }}>{MESES[ref.mes]} de {ref.ano} <span style={notaStyle}>· {noMes} {plural(noMes, "agendamento", "agendamentos")}</span></b>
        <button type="button" className="btn-ghost" aria-label="Próximo mês" onClick={() => mover(1)}><ChevronRight size={16} /></button>
      </div>
      <div role="grid" aria-label="Agendamentos do mês" style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: 4 }}>
        {["dom", "seg", "ter", "qua", "qui", "sex", "sáb"].map((d) => <div key={d} role="columnheader" style={{ ...notaStyle, textAlign: "center", textTransform: "uppercase", fontSize: "0.68rem" }}>{d}</div>)}
        {celulas.map((d, i) => {
          if (d == null) return <div key={`v${i}`} />;
          const iso = isoDia(ref.ano, ref.mes, d);
          const ags = porDia.get(iso) || [];
          const ativo = iso === sel;
          return (
            <button key={iso} type="button" role="gridcell" aria-selected={ativo} aria-label={`${d} de ${MESES[ref.mes]}: ${ags.length} ${plural(ags.length, "agendamento", "agendamentos")}`} onClick={() => setSel(iso)}
                    style={{ minHeight: 56, padding: "0.25rem", textAlign: "left", cursor: "pointer", borderRadius: "var(--r-sm)", display: "flex", flexDirection: "column", gap: 2, overflow: "hidden",
                             border: `1px solid ${ativo ? "var(--dourado)" : iso === hoje ? "var(--amber)" : "var(--border)"}`, background: ativo ? "var(--pill-active-bg)" : "var(--surface-2)", color: ativo ? "var(--pill-active-fg)" : "var(--text)" }}>
              <span style={{ fontSize: "0.75rem", fontWeight: iso === hoje ? 800 : 600 }}>{d}</span>
              {ags.slice(0, 2).map((a) => <span key={a.id} className="hidden sm:block" style={{ fontSize: "0.66rem", lineHeight: 1.2, borderLeft: `3px solid ${COR_ESTADO[a.estado_visual]}`, paddingLeft: 3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.protocolo_nome}</span>)}
              {ags.length > 2 && <span className="hidden sm:block" style={{ fontSize: "0.66rem", color: "var(--text-muted)" }}>+{ags.length - 2}</span>}
              {ags.length > 0 && <span className="sm:hidden" style={{ fontSize: "0.7rem", fontWeight: 800, color: COR_ESTADO[ags[0].estado_visual] }}>● {ags.length}</span>}
            </button>
          );
        })}
      </div>
      <div style={{ marginTop: "0.8rem" }}>
        <b style={{ fontSize: "0.85rem" }}>{diaSemana(sel)} {dataCurta(sel)}</b>
        {!doDia.length ? <p style={{ ...notaStyle, marginTop: 4 }}>Nada agendado neste dia.</p> : (
          <ul style={{ listStyle: "none", margin: "0.4rem 0 0", padding: 0 }}>
            {doDia.map((a) => (
              <li key={a.id} style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap", padding: "0.5rem 0", borderTop: "1px solid var(--border)" }}>
                <EstadoAgPill estado={a.estado_visual} />
                <span style={{ flex: 1, minWidth: 150 }}><b style={{ fontSize: "0.85rem" }}>{a.protocolo_nome}</b>
                  <span style={{ ...notaStyle, display: "block" }}>{a.hora || "sem hora"} · {a.animais_total} {plural(a.animais_total, "animal", "animais")} · {a.responsavel.nome}{a.fase ? ` · ${FASE_ROTULO[a.fase]}` : ""}</span></span>
                <button type="button" className="btn-secondary" onClick={() => onAbrir(a.id)}>Abrir</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ───────────────────────── detalhe / adiar / cancelar / continuar ─────────────────────────
type Acao = "adiar" | "cancelar" | "estornarIno" | "reabrir" | null;

function GavetaAgendamento({ id, modoInicial, onFechar, onMudou, onAplicar }: {
  id: number; modoInicial: "detalhe" | "montar"; onFechar: () => void; onMudou: () => void; onAplicar: () => void;
}) {
  const [ctx, setCtx] = useState<ContextoAplicar | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aba, setAba] = useState<"animais" | "checklist" | "historico">("animais");
  const [acao, setAcao] = useState<Acao>(null);
  const [montando, setMontando] = useState(modoInicial === "montar");
  const carregar = useCallback(() => { fetchContextoAplicar(id).then(setCtx).catch((e) => setErro(e.message)); }, [id]);
  useEffect(() => { carregar(); }, [carregar]);

  const titulo = montando ? "Continuar montando" : "Agendamento";
  return (
    <GavetaLancamento aberto onFechar={onFechar} titulo={titulo} icone={CalendarClock}>
      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      {!ctx && !erro && <TelaSkeleton kpis={0} />}
      {ctx && montando && <ContinuarMontando ctx={ctx} onFeito={() => { onMudou(); onFechar(); }} onVoltar={() => { setMontando(false); carregar(); }} />}
      {ctx && !montando && (
        <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
          <div>
            <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>{ctx.protocolo_nome}</h2>
            <p style={notaStyle}>{diaSemana(ctx.data_evento)} {dataCurta(ctx.data_evento)}{ctx.hora ? ` ${ctx.hora}` : ""} · {ctx.animais.length} {plural(ctx.animais.length, "animal", "animais")} · {ctx.responsavel.nome}{ctx.responsavel.crmv ? ` (${ctx.responsavel.crmv})` : ""}</p>
          </div>
          <ul style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "0.6rem", listStyle: "none", margin: 0, padding: 0 }}>
            <li className="card" style={{ padding: "0.5rem 0.7rem" }}><span style={notaStyle}>Responsável</span><b style={{ display: "block", fontSize: "0.9rem" }}>{ctx.responsavel.nome}</b></li>
            <li className="card" style={{ padding: "0.5rem 0.7rem" }}><span style={notaStyle}>Checklist</span><b style={{ display: "block" }}>{ctx.checklist.resolvidos}/{ctx.checklist.total}</b></li>
            <li className="card" style={{ padding: "0.5rem 0.7rem" }}><span style={notaStyle}>Produto</span><b style={{ display: "block", fontSize: "0.9rem" }}>{ctx.produto || "—"}</b></li>
            {ctx.financeiro && (
              <li className="card" style={{ padding: "0.5rem 0.7rem" }}>
                <span style={notaStyle}>Custo previsto</span>
                <b style={{ display: "block", fontSize: "0.9rem", color: ctx.financeiro.custo_previsto == null ? "var(--amber)" : undefined }}>{brl(ctx.financeiro.custo_previsto)}</b>
              </li>
            )}
            {ctx.financeiro && (
              <li className="card" style={{ padding: "0.5rem 0.7rem" }}>
                <span style={notaStyle}>Conta a pagar</span>
                <b style={{ display: "block", fontSize: "0.9rem" }}>{ctx.financeiro.contas_ativas > 0 ? brl(ctx.financeiro.conta_a_pagar_total) : ctx.financeiro.pagamento_vinculado_total > 0 ? "pago (vinculado)" : "nenhuma"}</b>
              </li>
            )}
          </ul>
          <p style={notaStyle}>Dose: {ctx.dose_texto}{ctx.via ? ` · via ${ctx.via}` : ""}. {ctx.carencia.texto}.</p>
          {ctx.exame?.inoculacao && (
            <div className="card" data-testid="bloco-inoculacao" style={{ padding: "0.6rem 0.9rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              <b style={{ fontSize: "0.9rem" }}>Inoculação registrada</b>
              <span style={notaStyle}>
                {dataCurta(ctx.exame.inoculacao.data)} {ctx.exame.inoculacao.hora || ""} · {ctx.exame.inoculacao.aplicador_nome || "—"}{ctx.exame.inoculacao.aplicador_crmv ? ` (${ctx.exame.inoculacao.aplicador_crmv})` : ""}
                {ctx.exame.inoculacao.lote_texto ? ` · frasco ${ctx.exame.inoculacao.lote_texto}` : ""}
              </span>
              <span style={{ fontSize: "0.85rem" }}>Leitura a partir de <b>{dataHoraLocal(ctx.exame.leitura_prevista_em)}</b> (72 h), até {dataHoraLocal(ctx.exame.leitura_limite_em)}.</span>
              {ehAdmin() && ctx.estado === "agendado" && <div><button type="button" className="btn-ghost" onClick={() => setAcao("estornarIno")}><Undo2 size={14} /> Estornar inoculação (administrador)</button></div>}
            </div>
          )}
          {acao === "estornarIno" && ctx.exame?.inoculacao && (
            <PainelEstornarInoculacao aplicacaoId={ctx.exame.inoculacao.aplicacao_id} onVoltar={() => setAcao(null)} onFeito={() => { onMudou(); onFechar(); }} />
          )}

          {acao === "reabrir" && <PainelReabrir ctx={ctx} onVoltar={() => setAcao(null)} onFeito={() => { onMudou(); setAcao(null); setMontando(true); carregar(); }} />}
          {acao === "adiar" && <PainelAdiar ctx={ctx} onVoltar={() => setAcao(null)} onFeito={() => { onMudou(); onFechar(); }} />}
          {acao === "cancelar" && <PainelCancelar ctx={ctx} onVoltar={() => setAcao(null)} onFeito={() => { onMudou(); onFechar(); }} />}

          <div role="tablist" aria-label="Detalhe do agendamento" style={{ display: "flex", gap: "0.4rem", borderBottom: "1px solid var(--border)" }}>
            {([["animais", "Animais"], ["checklist", "Checklist"], ["historico", "Histórico"]] as const).map(([k, n]) => (
              <button key={k} type="button" role="tab" aria-selected={aba === k} onClick={() => setAba(k)}
                      style={{ padding: "0.5rem 0.9rem", background: "transparent", border: "none", cursor: "pointer", fontSize: "0.85rem", fontWeight: aba === k ? 700 : 500,
                               color: aba === k ? "var(--dourado-light)" : "var(--text-muted)", borderBottom: aba === k ? "2px solid var(--dourado)" : "2px solid transparent" }}>{n}</button>
            ))}
          </div>
          {aba === "animais" && (
            <AbaAnimais ctx={ctx} podeTirar={(ctx.estado === "agendado" || ctx.estado === "em_montagem") && !ctx.exame?.inoculacao} onMudou={() => { carregar(); onMudou(); }} />
          )}
          {aba === "checklist" && <AbaChecklist ctx={ctx} onMudou={() => { carregar(); onMudou(); }} />}
          {aba === "historico" && (
            ctx.log.length ? (
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {ctx.log.slice().reverse().map((l) => (
                  <li key={l.id} style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border)", fontSize: "0.85rem" }}>
                    <b>{l.acao}</b>
                    {l.detalhe && <span style={{ ...notaStyle, display: "block" }}>{l.detalhe}</span>}
                    {l.motivo && <span style={{ ...notaStyle, display: "block" }}>Motivo: {l.motivo}</span>}
                    <span style={{ ...notaStyle, display: "block" }}>{l.usuario_nome || "Sistema"} · {dataHoraCurta(l.criado_em)}{l.canal ? ` · ${l.canal}` : ""}</span>
                  </li>
                ))}
              </ul>
            ) : <p style={notaStyle}>Sem registros ainda.</p>
          )}

          <div style={{ position: "sticky", bottom: "-0.9rem", margin: "0 -0.9rem -0.9rem", padding: "0.75rem 0.9rem", background: "var(--surface)", borderTop: "1px solid var(--border)", display: "flex", gap: "0.6rem", flexWrap: "wrap", zIndex: 2 }}>
            {ctx.estado === "agendado" && <button type="button" className="btn-primary-gold" onClick={onAplicar}><Syringe size={14} /> {ctx.exame ? VERBO_APLICAR[ctx.exame.fase] : "Aplicar"}</button>}
            {ctx.estado === "em_montagem" && <button type="button" className="btn-primary-gold" onClick={() => setMontando(true)}><Pencil size={14} /> Continuar montando</button>}
            {ctx.estado === "agendado" && <button type="button" className="btn-secondary" onClick={() => setAcao("adiar")}><Clock size={14} /> Adiar</button>}
            {ctx.estado === "agendado" && !ctx.exame?.inoculacao && <button type="button" className="btn-secondary" data-testid="reabrir-editar" onClick={() => setAcao("reabrir")}><Pencil size={14} /> Reabrir para editar</button>}
            <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => setAcao("cancelar")}><Ban size={14} /> Cancelar…</button>
          </div>
        </div>
      )}
    </GavetaLancamento>
  );
}

function AbaChecklist({ ctx, onMudou }: { ctx: ContextoAplicar; onMudou: () => void }) {
  const id = ctx.cronograma_id;
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const encerrado = ctx.estado !== "agendado" && ctx.estado !== "em_montagem";
  const veterinarios = ctx.pessoas.filter((p) => p.veterinario);
  async function salvar(corpo: Parameters<typeof editarChecklistAgendamento>[1]) {
    setOcupado(true); setErro(null);
    try { await editarChecklistAgendamento(id, corpo); onMudou(); }
    catch (e: any) { setErro(e.message || "Erro ao salvar o checklist"); } finally { setOcupado(false); }
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <ChecklistItensExistentes
        itens={ctx.checklist.itens} ocupado={ocupado} veterinario={ctx.checklist.veterinario} veterinarios={veterinarios}
        onAcao={(item, acao, motivo) => salvar({ itens: [{ item_id: item.id, acao, motivo: motivo || null }] })}
        onConfirmarVet={encerrado ? undefined : (v) => salvar({ veterinario: { estado: "confirmado", pessoa_id: v.pessoaId, quando: v.quando, observacao: v.nota } })}
      />
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      <div>
        <h3 style={{ fontSize: "0.9rem", fontWeight: 700, marginBottom: "0.2rem" }}>Compra e financeiro</h3>
        <FinanceiroVivo cronogramaId={id} dataEvento={ctx.data_evento} vetNome={ctx.responsavel.modo === "veterinario" ? ctx.responsavel.nome : null}
                        readOnly={encerrado} onMudou={onMudou} />
      </div>
      <p style={notaStyle}>Nada aqui bloqueia a aplicação: o que ficar pendente pede só a ciência na hora de Aplicar.</p>
    </div>
  );
}

function PainelReabrir({ ctx, onVoltar, onFeito }: { ctx: ContextoAplicar; onVoltar: () => void; onFeito: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [outro, setOutro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  async function reabrir() {
    setSalvando(true); setErro(null);
    try { await reabrirAgendamentoParaEditar(ctx.cronograma_id, textoMotivo(motivo, outro) || null); onFeito(); }
    catch (e: any) { setErro(e.message || "Erro ao reabrir"); } finally { setSalvando(false); }
  }
  return (
    <div className="card" role="group" aria-label="Reabrir para editar" style={{ display: "flex", flexDirection: "column", gap: "0.8rem", borderLeft: "4px solid var(--dourado)" }}>
      <h3 className="card-header">Reabrir para editar</h3>
      <p style={{ ...notaStyle, display: "flex", gap: 6 }}><ArrowRight size={13} style={{ marginTop: 2, flexShrink: 0 }} />O agendamento volta para “Em montagem” e sai da Agenda até você confirmar de novo. Os animais, o checklist e a data ficam como estão.</p>
      <Chips idBase="rb-m" rotulo="O que vai mudar? (opcional)" opcoes={["Trocar animais", "Trocar veterinário", "Mudar data ou hora", "Outro"]} valor={motivo} onChange={setMotivo} />
      {motivo === "Outro" && <input style={inputStyle} aria-label="Descreva" placeholder="Descreva" value={outro} onChange={(e) => setOutro(e.target.value)} />}
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={reabrir}><Pencil size={14} /> {salvando ? "Reabrindo…" : "Reabrir para editar"}</button>
        <button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button>
      </div>
    </div>
  );
}

const MOTIVOS_TIRAR: readonly MotivoTirarAnimal[] = ["Vendido", "Doente", "Não localizado", "Outro"];
const DESTINO_TXT = { espera: "voltou à lista de espera", baixado: "ficou baixado (não volta à lista de espera)", saiu: "saiu do agendamento" } as const;

/** Animais do agendamento; cada um pode ser tirado (motivo em chips): volta à lista de espera, ou fica "baixado" se vendido. */
function AbaAnimais({ ctx, podeTirar, onMudou }: { ctx: ContextoAplicar; podeTirar: boolean; onMudou: () => void }) {
  const [tirando, setTirando] = useState<string | null>(null);
  const [motivo, setMotivo] = useState("");
  const [outro, setOutro] = useState("");
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const ultimo = ctx.animais.length <= 1;

  async function tirar(numero: string) {
    setTentou(true);
    if (!motivo || (motivo === "Outro" && !outro.trim())) return;
    setSalvando(true); setErro(null);
    try {
      const r = await tirarAnimalDoAgendamento(ctx.cronograma_id, { numero_matriz: numero, motivo: motivo as MotivoTirarAnimal, motivo_outro: motivo === "Outro" ? outro.trim() : null });
      setAviso(`Animal ${numero} ${DESTINO_TXT[r.destino]}.`); setTirando(null); setMotivo(""); setOutro(""); setTentou(false); onMudou();
    } catch (e: any) { setErro(e.message || "Não foi possível tirar o animal"); } finally { setSalvando(false); }
  }
  return (
    <div>
      {aviso && <p role="status" style={{ color: "var(--green-light)", fontSize: "0.85rem", marginBottom: "0.4rem" }}>{aviso}</p>}
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {ctx.animais.map((a) => (
          <li key={a.numero_matriz} style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ flex: 1, minWidth: 140 }}><b>{a.numero_matriz}{a.nome ? ` ${a.nome}` : ""}</b><span style={{ ...notaStyle, display: "block" }}>{a.lote || "Sem lote"}{a.motivo ? ` · ${a.motivo}` : ""}</span></span>
              {a.origem === "fora_janela" ? <ForaJanelaBadge n={1} /> : <span style={{ color: "var(--green-light)", fontSize: "0.75rem", fontWeight: 700 }}><Check size={12} style={{ display: "inline" }} /> Na janela</span>}
              {podeTirar && (
                <button type="button" className="btn-ghost" disabled={ultimo} title={ultimo ? "Último animal: cancele o agendamento" : undefined}
                        aria-label={`Tirar ${a.numero_matriz} do agendamento`} onClick={() => { setTirando(tirando === a.numero_matriz ? null : a.numero_matriz); setMotivo(""); setOutro(""); setTentou(false); setErro(null); }}>
                  <Ban size={14} /> Tirar…
                </button>
              )}
            </div>
            {tirando === a.numero_matriz && (
              <div className="card" role="group" aria-label={`Tirar ${a.numero_matriz}`} style={{ marginTop: "0.5rem", padding: "0.7rem 0.9rem", display: "flex", flexDirection: "column", gap: "0.6rem", borderLeft: "4px solid var(--amber)" }}>
                <Chips idBase={`tr-${a.numero_matriz}`} rotulo="Por que sai? (obrigatório)" opcoes={MOTIVOS_TIRAR} valor={motivo} onChange={setMotivo} erro={tentou && !motivo ? "Escolha o motivo." : null} />
                {motivo === "Outro" && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={outro} onChange={(e) => setOutro(e.target.value)} />}
                <p style={notaStyle}>{a.origem === "fora_janela" ? "Incluído fora da janela: só sai do agendamento (não há lista de espera para onde voltar)." : motivo === "Vendido" ? "Vendido: fica baixado, não volta à lista de espera." : "Da janela: volta à lista de espera, com o motivo."}</p>
                {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button type="button" className="btn-primary" disabled={salvando} onClick={() => tirar(a.numero_matriz)}><Ban size={14} /> {salvando ? "Tirando…" : "Tirar do agendamento"}</button>
                  <button type="button" className="btn-ghost" onClick={() => setTirando(null)}>Voltar</button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PainelEstornarInoculacao({ aplicacaoId, onVoltar, onFeito }: { aplicacaoId: number; onVoltar: () => void; onFeito: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [outro, setOutro] = useState("");
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const texto = textoMotivo(motivo, outro);
  async function estornar() {
    setTentou(true);
    if (!texto) return;
    setSalvando(true); setErro(null);
    try { await estornarAplicacaoPreventiva(aplicacaoId, texto); onFeito(); }
    catch (e: any) { setErro(e.message || "Erro ao estornar"); } finally { setSalvando(false); }
  }
  return (
    <div className="card" role="group" aria-label="Estornar inoculação" style={{ display: "flex", flexDirection: "column", gap: "0.8rem", borderLeft: "4px solid var(--red)" }}>
      <h3 className="card-header">Estornar inoculação</h3>
      <p style={{ ...notaStyle, color: "var(--amber)" }}>A tuberculina volta ao estoque e o agendamento volta à data anterior. A inoculação original fica preservada como “Estornada”, com quem estornou e por quê.</p>
      <Chips idBase="ei-m" rotulo="Motivo (obrigatório)" opcoes={MOTIVOS_ESTORNO} valor={motivo} onChange={setMotivo} erro={tentou && !texto ? "Escolha o motivo." : null} />
      {motivo === "Outro motivo" && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={outro} onChange={(e) => setOutro(e.target.value)} />}
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="button" className="btn-primary" style={{ background: "var(--red)" }} disabled={salvando} onClick={estornar}><Undo2 size={14} /> {salvando ? "Estornando…" : "Estornar"}</button>
        <button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button>
      </div>
    </div>
  );
}

function PainelAdiar({ ctx, onVoltar, onFeito }: { ctx: ContextoAplicar; onVoltar: () => void; onFeito: () => void }) {
  const base = ctx.data_evento > hojeIso() ? ctx.data_evento : hojeIso();
  const [quando, setQuando] = useState<"amanha" | "sete" | "outra">("amanha");
  const [outra, setOutra] = useState("");
  const [motivo, setMotivo] = useState("");
  const [outro, setOutro] = useState("");
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const nova = quando === "amanha" ? maisDiasIso(1, base) : quando === "sete" ? maisDiasIso(7, base) : outra;
  const texto = textoMotivo(motivo, outro);

  async function adiar() {
    setTentou(true);
    if (!nova || !texto) return;
    setSalvando(true); setErro(null);
    try { await adiarAgendamentoPreventivo(ctx.cronograma_id, { nova_data: nova, motivo: texto }); onFeito(); }
    catch (e: any) { setErro(e.message || "Erro ao adiar"); } finally { setSalvando(false); }
  }
  return (
    <div className="card" role="group" aria-label="Adiar" style={{ display: "flex", flexDirection: "column", gap: "0.8rem", borderLeft: "4px solid var(--dourado)" }}>
      <h3 className="card-header">Adiar agendamento</h3>
      <Chips idBase="ad-q" rotulo="Nova data" opcoes={["Amanhã", "+ 7 dias", "Escolher data"]} valor={quando === "amanha" ? "Amanhã" : quando === "sete" ? "+ 7 dias" : "Escolher data"}
             onChange={(v) => setQuando(v === "Amanhã" ? "amanha" : v === "+ 7 dias" ? "sete" : "outra")} />
      {quando === "outra" ? <input type="date" style={{ ...inputStyle, width: "auto" }} aria-label="Nova data" value={outra} min={hojeIso()} onChange={(e) => setOutra(e.target.value)} />
        : <p style={notaStyle}>Nova data: <b>{dataCurta(nova)}</b></p>}
      <Chips idBase="ad-m" rotulo="Por que adiar? (obrigatório)" opcoes={MOTIVOS_ADIAR} valor={motivo} onChange={setMotivo} erro={tentou && !texto ? "Escolha o motivo." : null} />
      {motivo === "Outro" && <input style={inputStyle} aria-label="O que aconteceu" placeholder="O que aconteceu? (obrigatório)" value={outro} onChange={(e) => setOutro(e.target.value)} />}
      <p style={{ ...notaStyle, display: "flex", gap: 6 }}><ArrowRight size={13} style={{ marginTop: 2, flexShrink: 0 }} />Os animais, o checklist e o responsável ficam como estão; só a data muda. A Agenda acompanha.</p>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="button" className="btn-primary" disabled={salvando} onClick={adiar}><Clock size={14} /> {salvando ? "Adiando…" : "Adiar"}</button>
        <button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button>
      </div>
    </div>
  );
}

function PainelCancelar({ ctx, onVoltar, onFeito }: { ctx: ContextoAplicar; onVoltar: () => void; onFeito: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [outro, setOutro] = useState("");
  const [destino, setDestino] = useState<"espera" | "naoSeAplica">("espera");
  const [conta, setConta] = useState<"manter" | "cancelar" | "">("");
  const [pagamento, setPagamento] = useState<"manter" | "desvincular" | "">("");
  const [cotacao, setCotacao] = useState<"manter" | "cancelar" | "">("");
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const texto = textoMotivo(motivo, outro);
  const fin = ctx.financeiro;
  const contas = (fin?.vinculos || []).filter((v) => v.tipo === "conta" && v.estado === "ativo");
  const pagamentos = (fin?.vinculos || []).filter((v) => v.tipo === "pagamento" && v.estado === "ativo");
  const cotacoes = (fin?.vinculos || []).filter((v) => v.tipo === "cotacao" && v.estado === "ativo");
  const pedidos = (fin?.vinculos || []).filter((v) => v.tipo === "pedido" && v.estado === "ativo");
  const daJanela = ctx.animais.filter((a) => a.origem === "janela").length;
  const fora = ctx.animais.length - daJanela;
  const faltaDestino = (contas.length > 0 && !conta) || (pagamentos.length > 0 && !pagamento) || (cotacoes.length > 0 && !cotacao);

  async function cancelar() {
    setTentou(true);
    if (!texto || faltaDestino) return;
    setSalvando(true); setErro(null);
    try {
      await cancelarAgendamentoPreventivo(ctx.cronograma_id, texto, destino, {
        conta: contas.length ? (conta as "manter" | "cancelar") : undefined,
        pagamento: pagamentos.length ? (pagamento as "manter" | "desvincular") : undefined,
        cotacao: cotacoes.length ? (cotacao as "manter" | "cancelar") : undefined,
      });
      onFeito();
    } catch (e: any) { setErro(e.message || "Erro ao cancelar"); } finally { setSalvando(false); }
  }
  const lista = (vs: typeof contas, comValor = true) => (
    <ul style={{ margin: "0 0 0.4rem", paddingLeft: "1.1rem", fontSize: "0.82rem" }}>
      {vs.map((v) => <li key={v.id}>{v.rotulo || "—"}{comValor ? ` · ${brl(v.valor)}` : ""}{v.vencimento && v.tipo === "conta" ? ` · vence ${dataCurta(v.vencimento)}` : ""}{v.numero_lancamento ? ` · ${v.numero_lancamento}` : ""}{v.alvo?.paga ? " · já paga" : ""}</li>)}
    </ul>
  );
  return (
    <div className="card" role="group" aria-label="Cancelar agendamento" style={{ display: "flex", flexDirection: "column", gap: "0.8rem", borderLeft: "4px solid var(--red)" }}>
      <h3 className="card-header">Cancelar agendamento</h3>
      <p style={{ ...notaStyle, display: "flex", gap: 6, color: "var(--amber)" }}>
        <AlertTriangle size={14} style={{ marginTop: 2, flexShrink: 0 }} />
        Cancelar {destino === "espera" ? `devolve os ${daJanela} animais da janela à lista de espera` : "desconsidera todos os animais (eles não voltam à lista de espera)"}
        {fora ? `, e libera os ${fora} de fora da janela` : ""}, e mantém o histórico. Nada foi baixado do estoque.
      </p>
      <Chips idBase="cn-m" rotulo="Motivo (obrigatório)" opcoes={MOTIVOS_CANCELAR} valor={motivo} onChange={setMotivo} erro={tentou && !texto ? "Escolha o motivo." : null} />
      {motivo === "Outro motivo" && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={outro} onChange={(e) => setOutro(e.target.value)} />}
      <Chips idBase="cn-d" rotulo="O que fazer com os animais" opcoes={["Voltam à lista de espera", "Desconsiderar"]} valor={destino === "espera" ? "Voltam à lista de espera" : "Desconsiderar"}
             onChange={(v) => setDestino(v === "Desconsiderar" ? "naoSeAplica" : "espera")} />
      {contas.length > 0 && (
        <div>
          <span style={labelStyle}>Conta a pagar deste agendamento</span>
          {lista(contas)}
          <Chips idBase="cn-c" rotulo="O que fazer com a conta (obrigatório)" opcoes={["Manter a conta", "Cancelar a conta"]} valor={conta === "manter" ? "Manter a conta" : conta === "cancelar" ? "Cancelar a conta" : ""}
                 onChange={(v) => setConta(v === "Cancelar a conta" ? "cancelar" : "manter")} erro={tentou && !conta ? "Escolha o destino da conta a pagar." : null} />
          <p style={{ ...notaStyle, marginTop: "0.3rem" }}>{conta === "cancelar" ? "A conta sai de Contas a pagar e dos totais (fica registrada aqui como Cancelada). Se já foi paga, estorne a baixa antes." : "A conta continua em Contas a pagar."}</p>
        </div>
      )}
      {pagamentos.length > 0 && (
        <div>
          <span style={labelStyle}>Pagamento já realizado vinculado</span>
          {lista(pagamentos)}
          <Chips idBase="cn-p" rotulo="O que fazer com o vínculo (obrigatório)" opcoes={["Manter o vínculo", "Desvincular"]} valor={pagamento === "manter" ? "Manter o vínculo" : pagamento === "desvincular" ? "Desvincular" : ""}
                 onChange={(v) => setPagamento(v === "Desvincular" ? "desvincular" : "manter")} erro={tentou && !pagamento ? "Escolha o destino do pagamento vinculado." : null} />
          <p style={{ ...notaStyle, marginTop: "0.3rem" }}>O lançamento pago continua no Financeiro; só o vínculo com este agendamento muda.</p>
        </div>
      )}
      {cotacoes.length > 0 && (
        <div>
          <span style={labelStyle}>Cotação deste agendamento</span>
          {lista(cotacoes, false)}
          <Chips idBase="cn-q" rotulo="O que fazer com a cotação (obrigatório)" opcoes={["Manter a cotação", "Cancelar a cotação"]} valor={cotacao === "manter" ? "Manter a cotação" : cotacao === "cancelar" ? "Cancelar a cotação" : ""}
                 onChange={(v) => setCotacao(v === "Cancelar a cotação" ? "cancelar" : "manter")} erro={tentou && !cotacao ? "Escolha o destino da cotação." : null} />
        </div>
      )}
      {pedidos.length > 0 && <p style={notaStyle}>O pedido {pedidos.map((p) => p.numero_lancamento).join(", ")} continua em Pedidos; cancele por lá se precisar.</p>}
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="button" className="btn-primary" style={{ background: "var(--red)" }} disabled={salvando} onClick={cancelar}><Ban size={14} /> {salvando ? "Cancelando…" : "Cancelar agendamento"}</button>
        <button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button>
      </div>
    </div>
  );
}

// Rascunho ("Em montagem"): define data, hora, responsável e checklist e confirma.
function ContinuarMontando({ ctx, onFeito, onVoltar }: { ctx: ContextoAplicar; onFeito: () => void; onVoltar: () => void }) {
  const [data, setData] = useState(ctx.data_evento >= hojeIso() ? ctx.data_evento : hojeIso());
  const [hora, setHora] = useState(ctx.hora || "");
  const [quem, setQuem] = useState<"propria" | "veterinario">(ctx.responsavel.modo === "veterinario" ? "veterinario" : "propria");
  const [vetId, setVetId] = useState(ctx.responsavel.pessoa_id ? String(ctx.responsavel.pessoa_id) : "");
  const [ck, setCk] = useState<ChecklistDraft>(checklistVazio());
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const veterinarios = ctx.pessoas.filter((p) => p.veterinario);
  const erroCk = validarChecklist(ck);

  async function confirmar() {
    setTentou(true); setErro(null);
    if (!data) { setErro("Escolha a data."); return; }
    if (quem === "veterinario" && !vetId) { setErro("Escolha o veterinário."); return; }
    if (erroCk) { setErro(erroCk); return; }
    setSalvando(true);
    try {
      await confirmarRascunhoAgendamento(ctx.cronograma_id, {
        data_evento: data, hora: hora || null, modo_execucao: quem, veterinario_pessoa_id: quem === "veterinario" ? Number(vetId) : null,
        checklist: checklistParaPayload(ck),
      });
      onFeito();
    } catch (e: any) { setErro(e.message || "Erro ao confirmar o agendamento"); } finally { setSalvando(false); }
  }
  return (
    <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div>
        <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>{ctx.protocolo_nome}</h2>
        <p style={notaStyle}>Rascunho com {ctx.animais.length} {plural(ctx.animais.length, "animal", "animais")}. Defina quando e com quem e confirme: só então entra na Agenda.</p>
      </div>
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
        <div className="grid grid-cols-2 gap-3">
          <div><label htmlFor="cm-data" style={labelStyle}>Data</label><input id="cm-data" type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} /></div>
          <div><label htmlFor="cm-hora" style={labelStyle}>Hora</label><input id="cm-hora" type="time" style={inputStyle} value={hora} onChange={(e) => setHora(e.target.value)} /></div>
        </div>
        <Chips idBase="cm-quem" rotulo="Quem faz" opcoes={["Veterinário", "Equipe própria"]} valor={quem === "veterinario" ? "Veterinário" : "Equipe própria"} onChange={(v) => { setQuem(v === "Veterinário" ? "veterinario" : "propria"); }} />
        {quem === "veterinario" && (
          <div>
            <label htmlFor="cm-vet" style={labelStyle}>Veterinário</label>
            <select id="cm-vet" style={inputStyle} value={vetId} onChange={(e) => setVetId(e.target.value)}>
              <option value="">Escolha o veterinário</option>
              {veterinarios.map((v) => <option key={v.id} value={v.id}>{v.nome}{v.crmv ? ` (${v.crmv})` : ""}</option>)}
            </select>
          </div>
        )}
      </div>
      <h3 style={{ fontSize: "0.9rem", fontWeight: 700 }}>Checklist</h3>
      <ChecklistMontagem draft={ck} onChange={setCk} veterinarios={veterinarios} produto={ctx.produto} dataEvento={data} hora={hora} tentou={tentou} />
      <h3 style={{ fontSize: "0.9rem", fontWeight: 700 }}>Compra e financeiro</h3>
      <div className="card" style={{ padding: "0.4rem 1rem" }}>
        <FinanceiroVivo cronogramaId={ctx.cronograma_id} dataEvento={data} vetNome={veterinarios.find((v) => String(v.id) === (ck.vet.pessoaId || vetId))?.nome || null} />
      </div>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={confirmar}><CalendarPlus size={14} /> {salvando ? "Confirmando…" : "Confirmar agendamento"}</button>
        <button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button>
      </div>
    </div>
  );
}
