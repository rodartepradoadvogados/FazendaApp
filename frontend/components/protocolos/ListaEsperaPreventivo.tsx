"use client";
// Protocolos › Aplicar › Sanitário preventivo — LISTA DE ESPERA e assistente
// "Criar agendamento" (fatia 7 do planejamento unificado, R1–R9; mockup
// docs/agents/auditoria-preventivo-agenda/mockups/fluxo-completo.html).
//
// Vocabulário do fluxo aprovado: janela de aplicação, lista de espera,
// agendamento, Desconsiderar. Lista de espera NÃO é a Agenda: a Agenda só
// recebe o agendamento, no dia. Fala com o mesmo backend de cronogramas
// (/sanidade/cronogramas/...), sem tabela ou endpoint paralelo.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowLeft, ArrowRight, Ban, CalendarCheck, CalendarPlus, Check, ChevronDown, Clock, Flag, Info, Plus, Search, X,
} from "lucide-react";
import {
  criarAgendamentoPreventivo, desconsiderarListaEspera, fetchListaEspera, fetchPessoas, formatDate,
  type AnimalListaEspera, type GrupoListaEspera, type ListaEspera,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import {
  ChecklistMontagem, checklistParaPayload, checklistVazio, resumoChecklistDraft, validarChecklist, type ChecklistDraft,
} from "./ChecklistAgendamento";
import { ConferirFinanceiro } from "./FinanceiroAgendamento";
import { textoMotivo } from "./preventivoComum";
import { Indicador, TelaSkeleton } from "@/components/ui";
import type { AnimalRow } from "@/components/AnimalModal";

const MOTIVOS_FORA = ["Aproveitar a visita do veterinário", "Exigência de venda / GTA", "Risco na região (surto)", "Decisão do veterinário", "Outro"];
const MOTIVOS_DESCONSIDERAR = ["Já vacinada em outra fazenda", "Não é fêmea de reposição", "Vai ser descartada", "Outro"];

const inputStyle: React.CSSProperties = {
  fontSize: "0.85rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
const notaStyle: React.CSSProperties = { fontSize: "0.78rem", color: "var(--text-muted)" };

const plural = (n: number, um: string, varios: string) => (n === 1 ? um : varios);
const hojeIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const maisDiasIso = (dias: number) => {
  const d = new Date(); d.setDate(d.getDate() + dias);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const DIAS_SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const diaSemana = (iso: string) => DIAS_SEMANA[new Date(iso + "T00:00:00").getDay()];

function tituloGrupo(g: GrupoListaEspera): string { return g.protocolo_nome; }

function Chips({ rotulo, opcoes, valor, onChange, idBase }: {
  rotulo: string; opcoes: readonly string[]; valor: string; onChange: (v: string) => void; idBase: string;
}) {
  return (
    <div>
      <span id={`${idBase}-l`} style={labelStyle}>{rotulo}</span>
      <div role="radiogroup" aria-labelledby={`${idBase}-l`} style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
        {opcoes.map((o) => {
          const ativo = valor === o;
          return (
            <button
              key={o} type="button" role="radio" aria-checked={ativo} onClick={() => onChange(o)}
              style={{
                fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: 999, cursor: "pointer", minHeight: 36,
                border: `1px solid ${ativo ? "var(--pill-active-border)" : "var(--border)"}`,
                background: ativo ? "var(--pill-active-bg)" : "transparent",
                color: ativo ? "var(--pill-active-fg)" : "var(--text)", fontWeight: ativo ? 700 : 500,
              }}
            >{o}</button>
          );
        })}
      </div>
    </div>
  );
}

function Pill({ cor, children }: { cor: string; children: React.ReactNode }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4, fontSize: "0.72rem", fontWeight: 700, padding: "0.2rem 0.6rem",
      borderRadius: 999, color: cor, border: `1px solid ${cor}`, background: "var(--surface-2)", whiteSpace: "nowrap",
    }}>{children}</span>
  );
}

function SituacaoPill({ situacao, diasAtraso, fechaEm }: { situacao: "atrasada" | "na_janela"; diasAtraso: number; fechaEm: number | null }) {
  if (situacao === "atrasada") {
    return <Pill cor="var(--red)"><AlertTriangle size={12} />Atrasada há {diasAtraso} {plural(diasAtraso, "dia", "dias")}</Pill>;
  }
  return (
    <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
      <Pill cor="var(--green-light)"><Check size={12} />Na janela{fechaEm != null && fechaEm >= 0 ? ` · ${fechaEm} ${plural(fechaEm, "dia restante", "dias restantes")}` : ""}</Pill>
      {fechaEm != null && fechaEm >= 0 && fechaEm <= 7 && <Pill cor="var(--amber)"><Clock size={12} />Fecha em {fechaEm} {plural(fechaEm, "dia", "dias")}</Pill>}
    </span>
  );
}

function situacaoGrupo(g: GrupoListaEspera) {
  return <SituacaoPill situacao={g.situacao} diasAtraso={g.dias_atraso} fechaEm={g.fecha_em} />;
}

function Legenda() {
  return (
    <div role="note" aria-label="Legenda das situações da lista de espera" style={{ ...notaStyle, display: "flex", flexWrap: "wrap", gap: "0.4rem 1rem", margin: "0.8rem 0 0.4rem" }}>
      <span>Na janela: dias restantes</span>
      <span style={{ color: "var(--red)" }}>Atrasada: passou da data devida, a janela segue aberta</span>
      <span style={{ color: "var(--amber)" }}>Fecha em breve: faltam 7 dias ou menos</span>
    </div>
  );
}

type Tela = { tipo: "lista" } | { tipo: "detalhe"; calId: number } | { tipo: "assistente"; calId: number; sel: string[] } | { tipo: "pronto"; resumo: string; dia: string; rascunho?: boolean };

export function ListaEsperaPreventivo(props: {
  animais: AnimalRow[]; avulsa?: React.ReactNode; onAbrirAcompanhamento?: () => void;
}) {
  // `le-raiz` alinha ícone e texto dos botões (.btn-ghost/.btn-secondary) só aqui.
  return <div className="le-raiz"><ListaEsperaConteudo {...props} /></div>;
}

function ListaEsperaConteudo({ animais, avulsa, onAbrirAcompanhamento }: {
  animais: AnimalRow[]; avulsa?: React.ReactNode; onAbrirAcompanhamento?: () => void;
}) {
  const [dados, setDados] = useState<ListaEspera | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tela, setTela] = useState<Tela>({ tipo: "lista" });
  const [recarga, setRecarga] = useState(0);
  const [outras, setOutras] = useState(false);

  useEffect(() => {
    let vivo = true;
    fetchListaEspera().then((d) => { if (vivo) { setDados(d); setErro(null); } }).catch((e) => { if (vivo) setErro(e.message || "Erro ao carregar a lista de espera"); });
    return () => { vivo = false; };
  }, [recarga]);
  const recarregar = useCallback(() => setRecarga((n) => n + 1), []);

  if (erro) return <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{erro}</span></div>;
  if (!dados) return <TelaSkeleton kpis={3} />;

  const grupo = tela.tipo === "detalhe" || tela.tipo === "assistente" ? dados.grupos.find((g) => g.calendario_id === tela.calId) : undefined;

  if (tela.tipo === "assistente") {
    if (!grupo) return <SemGrupo onVoltar={() => setTela({ tipo: "lista" })} />;
    return (
      <AssistenteAgendamento
        grupo={grupo} preSelecionados={tela.sel} animais={animais}
        onSair={() => setTela({ tipo: "detalhe", calId: grupo.calendario_id })}
        onCriado={(resumo, dia, rascunho) => { recarregar(); setTela({ tipo: "pronto", resumo, dia, rascunho }); }}
      />
    );
  }
  if (tela.tipo === "pronto") {
    return (
      <div className="card" role="status">
        <div className="card-header mb-2 flex items-center gap-2"><CalendarCheck size={16} /> {tela.rascunho ? "Rascunho salvo" : "Agendamento criado"}</div>
        <p style={{ fontSize: "0.9rem", marginBottom: "0.4rem" }}>{tela.resumo}</p>
        <p style={notaStyle}>
          {tela.rascunho
            ? "O rascunho fica em Acompanhamento, como Em montagem. Só entra na Agenda depois de confirmado (Continuar montando)."
            : <>Ele entra na Agenda em {formatDate(tela.dia)}.</>}
          {" "}Quem ficou na lista de espera continua aqui e não aparece na Agenda.
        </p>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.9rem" }}>
          <button type="button" className="btn-primary-gold" onClick={() => setTela({ tipo: "lista" })}>Voltar à lista de espera</button>
          {onAbrirAcompanhamento && <button type="button" className="btn-secondary" onClick={onAbrirAcompanhamento}>Ver em Acompanhamento</button>}
        </div>
      </div>
    );
  }
  if (tela.tipo === "detalhe") {
    if (!grupo) return <SemGrupo onVoltar={() => setTela({ tipo: "lista" })} />;
    return (
      <DetalheEspera
        grupo={grupo} onVoltar={() => setTela({ tipo: "lista" })} onMudou={recarregar}
        onCriar={(sel) => setTela({ tipo: "assistente", calId: grupo.calendario_id, sel })}
      />
    );
  }
  return (
    <ListaGrupos
      dados={dados} outras={outras} onOutras={() => setOutras((v) => !v)} avulsa={avulsa}
      onAbrir={(id) => setTela({ tipo: "detalhe", calId: id })}
      onCriar={(g) => setTela({ tipo: "assistente", calId: g.calendario_id, sel: g.animais.map((a) => a.numero_matriz) })}
      onAbrirAcompanhamento={onAbrirAcompanhamento}
    />
  );
}

function SemGrupo({ onVoltar }: { onVoltar: () => void }) {
  return (
    <div className="card">
      <p style={{ fontSize: "0.9rem", marginBottom: "0.8rem" }}>Ninguém na lista de espera deste protocolo. Quem entrar na janela de aplicação aparece aqui.</p>
      <button type="button" className="btn-secondary" onClick={onVoltar}><ArrowLeft size={14} /> Voltar à lista de espera</button>
    </div>
  );
}

// ─────────────────────────── Lista de espera (por protocolo) ───────────────────────────
function ListaGrupos({ dados, outras, onOutras, avulsa, onAbrir, onCriar, onAbrirAcompanhamento }: {
  dados: ListaEspera; outras: boolean; onOutras: () => void; avulsa?: React.ReactNode;
  onAbrir: (calId: number) => void; onCriar: (g: GrupoListaEspera) => void; onAbrirAcompanhamento?: () => void;
}) {
  const [situacao, setSituacao] = useState<"" | "atrasada" | "fecham">("");
  const [lote, setLote] = useState("");
  const [q, setQ] = useState("");
  const [aviso, setAviso] = useState(true);
  useEffect(() => {
    try { if (window.localStorage.getItem("cowdata-le-aviso") === "0") setAviso(false); } catch { /* sem storage: mostra o aviso */ }
  }, []);
  const dispensar = () => { setAviso(false); try { window.localStorage.setItem("cowdata-le-aviso", "0"); } catch { /* ignora */ } };

  const lotes = useMemo(() => Array.from(new Set(dados.grupos.flatMap((g) => g.lotes))).sort(), [dados]);
  const grupos = useMemo(() => dados.grupos.filter((g) => {
    if (situacao === "atrasada" && !g.atrasadas) return false;
    if (situacao === "fecham" && !g.animais.some((a) => a.fecha_em != null && a.fecha_em >= 0 && a.fecha_em <= 7)) return false;
    if (lote && !g.lotes.includes(lote)) return false;
    if (q && !tituloGrupo(g).toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  }), [dados, situacao, lote, q]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.8rem", flexWrap: "wrap", marginBottom: "0.8rem" }}>
        <div>
          <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>Lista de espera</h2>
          <p style={notaStyle}>Animais na janela de aplicação. Aqui eles ficam até serem agendados — não aparecem na Agenda.</p>
        </div>
        <button type="button" className="btn-secondary" aria-expanded={outras} onClick={onOutras}>Outras formas <ChevronDown size={14} /></button>
      </div>

      {outras && (
        <div className="card mb-3">
          <div className="card-header mb-2">Outras formas de aplicar</div>
          <p style={{ ...notaStyle, marginBottom: "0.8rem" }}>Aplicação avulsa (hoje, sem esperar a janela) ou já realizada (lançar depois).</p>
          {avulsa}
        </div>
      )}

      {aviso && (
        <div className="card mb-3" role="note" style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap", padding: "0.6rem 0.9rem" }}>
          <Info size={14} style={{ color: "var(--text-muted)" }} />
          <span style={{ fontSize: "0.82rem" }}><b>Lista de espera ≠ Agenda.</b> A Agenda só recebe o que você agenda, no dia.</span>
          <span style={{ flex: 1 }} />
          <button type="button" className="btn-ghost" onClick={dispensar} aria-label="Dispensar este aviso">Entendi</button>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
        <Indicador categoria="sanidade" rotulo="Aguardando" valor={dados.total} onClick={() => setSituacao("")} title="Na lista de espera" />
        <Indicador categoria="sanidade" rotulo="Atrasadas" valor={dados.atrasadas} cor="var(--red)" onClick={() => setSituacao("atrasada")} title="Passou da data devida; a janela segue aberta" />
        <Indicador categoria="sanidade" rotulo="Fecham em 7 dias" valor={dados.fecham_7d} cor="var(--amber)" onClick={() => setSituacao("fecham")} title="O animal continua na lista" />
      </div>

      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "flex-end", marginBottom: "0.8rem" }}>
        <div style={{ flex: "0 1 220px", minWidth: 150 }}>
          <label htmlFor="le-lote" style={labelStyle}>Lote</label>
          <select id="le-lote" style={inputStyle} value={lote} onChange={(e) => setLote(e.target.value)}>
            <option value="">Todos os lotes</option>
            {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <div style={{ flex: "1 1 200px", minWidth: 160 }}>
          <label htmlFor="le-busca" style={labelStyle}>Buscar protocolo</label>
          <div style={{ position: "relative" }}>
            <Search size={14} style={{ position: "absolute", left: 8, top: 11, color: "var(--text-muted)" }} />
            <input id="le-busca" type="search" style={{ ...inputStyle, paddingLeft: 28 }} placeholder="Buscar protocolo…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        {situacao && <button type="button" className="btn-ghost" onClick={() => setSituacao("")}><X size={14} /> Limpar filtro</button>}
        {dados.agendamentos_ativos > 0 && onAbrirAcompanhamento && (
          <button type="button" className="btn-ghost" onClick={onAbrirAcompanhamento}>
            <CalendarCheck size={14} /> Já agendado: {dados.agendamentos_ativos} {plural(dados.agendamentos_ativos, "agendamento", "agendamentos")} ▸
          </button>
        )}
      </div>

      {!dados.grupos.length ? (
        <div className="card" style={{ textAlign: "center", padding: "1.6rem 1rem" }}>
          <Check size={26} style={{ color: "var(--green-light)", margin: "0 auto 0.5rem" }} />
          <p style={{ fontWeight: 700, marginBottom: "0.2rem" }}>Ninguém na lista de espera. Tudo em dia.</p>
          <p style={notaStyle}>Quando um animal entrar na janela de aplicação, ele aparece aqui.</p>
        </div>
      ) : !grupos.length ? (
        <div className="card"><p style={notaStyle}>Nenhum protocolo com esses filtros.</p></div>
      ) : (
        <div className="card">
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }} aria-label="Protocolos com animais na lista de espera">
            {grupos.map((g) => (
              <li key={g.calendario_id} style={{ display: "flex", gap: "0.8rem", flexWrap: "wrap", alignItems: "center", padding: "0.7rem 0", borderBottom: "1px solid var(--border)" }}>
                <button
                  type="button" onClick={() => onAbrir(g.calendario_id)} aria-label={`Abrir ${tituloGrupo(g)}`}
                  style={{ flex: "1 1 220px", minWidth: 0, textAlign: "left", background: "transparent", border: 0, color: "var(--text)", cursor: "pointer", padding: 0 }}
                >
                  <span style={{ display: "block", fontWeight: 700, fontSize: "0.92rem" }}>{tituloGrupo(g)}</span>
                  <span style={notaStyle}>
                    {g.lotes.length > 2 ? `${g.lotes.length} lotes` : g.lotes.join(", ") || g.categoria_alvo || "—"}
                    {" · "}janela {formatDate(g.janela_de)}{g.janela_ate ? ` → ${formatDate(g.janela_ate)}` : ""}
                  </span>
                </button>
                <div style={{ flex: "0 1 auto" }}>{situacaoGrupo(g)}</div>
                <div style={{ flex: "0 0 auto", textAlign: "center", minWidth: 70 }} aria-label={`${g.quantidade} na espera`}>
                  <b style={{ fontSize: "1.15rem" }}>{g.quantidade}</b>
                  <span style={{ ...notaStyle, display: "block" }}>na espera</span>
                </div>
                <button type="button" className="btn-primary" onClick={() => onCriar(g)}>
                  <CalendarPlus size={14} /> Criar agendamento
                </button>
              </li>
            ))}
          </ul>
          <Legenda />
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Detalhe de um protocolo (escolher animais) ───────────────────────────
function DetalheEspera({ grupo, onVoltar, onCriar, onMudou }: {
  grupo: GrupoListaEspera; onVoltar: () => void; onCriar: (sel: string[]) => void; onMudou: () => void;
}) {
  const [sel, setSel] = useState<Set<string>>(() => new Set(grupo.animais.map((a) => a.numero_matriz)));
  const [desconsiderando, setDesconsiderando] = useState<AnimalListaEspera | null>(null);
  const todos = sel.size === grupo.animais.length;
  const alternar = (n: string) => setSel((p) => { const s = new Set(p); if (s.has(n)) s.delete(n); else s.add(n); return s; });
  const dose = grupo.dose != null ? `${grupo.dose}${grupo.unidade ? ` ${grupo.unidade}` : ""}` : null;

  return (
    <div>
      <button type="button" className="btn-ghost" onClick={onVoltar} style={{ marginBottom: "0.4rem" }}><ArrowLeft size={14} /> Lista de espera</button>
      <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>{tituloGrupo(grupo)}</h2>
      <p style={{ ...notaStyle, marginBottom: "0.9rem" }}>
        {grupo.animais.length} na espera{grupo.lotes.length ? ` · ${grupo.lotes.join(", ")}` : ""}
        {" · "}janela {formatDate(grupo.janela_de)}{grupo.janela_ate ? ` → ${formatDate(grupo.janela_ate)}` : ""}
        {grupo.produto ? ` · ${grupo.produto}` : ""}{dose ? ` · ${dose}` : ""}{grupo.via ? ` · ${grupo.via}` : ""}
      </p>

      <div className="card">
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {grupo.animais.map((a) => (
            <li key={a.numero_matriz} style={{ display: "flex", gap: "0.7rem", flexWrap: "wrap", alignItems: "center", padding: "0.55rem 0", borderBottom: "1px solid var(--border)" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.6rem", flex: "1 1 220px", minWidth: 0, cursor: "pointer" }}>
                <input type="checkbox" checked={sel.has(a.numero_matriz)} onChange={() => alternar(a.numero_matriz)} aria-label={`Marcar ${a.numero_matriz}`} style={{ width: 18, height: 18 }} />
                <span>
                  <b>{a.numero_matriz}{a.nome ? ` ${a.nome}` : ""}</b>
                  <span style={{ ...notaStyle, display: "block" }}>{a.lote || "Sem lote"} · {a.motivo_entrada}</span>
                </span>
              </label>
              <SituacaoPill situacao={a.situacao} diasAtraso={a.dias_atraso} fechaEm={a.fecha_em} />
              <button type="button" className="btn-ghost" onClick={() => setDesconsiderando(a)} aria-label={`Desconsiderar ${a.numero_matriz}`}>
                <Ban size={14} /> Desconsiderar…
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="card" style={{ marginTop: "0.8rem", display: "flex", alignItems: "center", gap: "0.7rem", flexWrap: "wrap", position: "sticky", bottom: 8, zIndex: 5 }} role="region" aria-label="Ações da seleção">
        <b>{sel.size} {plural(sel.size, "selecionado", "selecionados")} de {grupo.animais.length}</b>
        <button type="button" className="btn-ghost" onClick={() => setSel(todos ? new Set() : new Set(grupo.animais.map((a) => a.numero_matriz)))}>
          {todos ? "Desmarcar todos" : "Marcar todos"}
        </button>
        <span style={{ flex: 1 }} />
        {sel.size === 0 && <span style={notaStyle}>Marque pelo menos 1 animal</span>}
        <button type="button" className="btn-primary-gold" disabled={sel.size === 0} onClick={() => onCriar(Array.from(sel))}>
          <CalendarPlus size={14} /> Criar agendamento com os selecionados
        </button>
      </div>
      <p style={{ ...notaStyle, marginTop: "0.8rem", marginBottom: "0.4rem" }}>
        Para incluir um animal que ainda não entrou na janela, use Criar agendamento › Incluir animal de fora da janela.
      </p>
      <Legenda />

      {desconsiderando && (
        <DesconsiderarModal
          grupo={grupo} animal={desconsiderando} onFechar={() => setDesconsiderando(null)}
          onFeito={() => { setDesconsiderando(null); onMudou(); }}
        />
      )}
    </div>
  );
}

function DesconsiderarModal({ grupo, animal, onFechar, onFeito }: {
  grupo: GrupoListaEspera; animal: AnimalListaEspera; onFechar: () => void; onFeito: () => void;
}) {
  const [motivo, setMotivo] = useState("");
  const [outro, setOutro] = useState("");
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const texto = motivo === "Outro" ? outro.trim() : motivo;

  async function confirmar() {
    setTentou(true);
    if (!texto) return;
    setSalvando(true); setErro(null);
    try {
      await desconsiderarListaEspera({ calendario_sanitario_id: grupo.calendario_id, animais: [animal.numero_matriz], motivo: texto });
      onFeito();
    } catch (e: any) { setErro(e.message || "Erro ao desconsiderar"); } finally { setSalvando(false); }
  }

  return (
    <Modal title="Desconsiderar da lista de espera" onClose={onFechar} width="520px"><div className="le-raiz">
      <p style={{ fontSize: "0.88rem", marginBottom: "0.8rem" }}>
        <b>{animal.numero_matriz}{animal.nome ? ` ${animal.nome}` : ""}</b> sai da lista de espera de {tituloGrupo(grupo)}. Não se aplica a ele neste ciclo.
      </p>
      <Chips idBase="desc" rotulo="Motivo (obrigatório; nada vem marcado)" opcoes={MOTIVOS_DESCONSIDERAR} valor={motivo} onChange={setMotivo} />
      {motivo === "Outro" && (
        <input style={{ ...inputStyle, marginTop: "0.6rem" }} aria-label="Descreva o motivo" placeholder="Descreva" value={outro} onChange={(e) => setOutro(e.target.value)} />
      )}
      {tentou && !texto && <p role="alert" style={{ color: "var(--red)", fontSize: "0.78rem", marginTop: "0.5rem" }}>Escolha o motivo para desconsiderar.</p>}
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", flexWrap: "wrap" }}>
        <button type="button" className="btn-primary" onClick={confirmar} disabled={salvando}><Ban size={14} /> {salvando ? "Salvando…" : "Desconsiderar"}</button>
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
      </div>
    </div></Modal>
  );
}

// ─────────────────────────── Assistente "Criar agendamento" ───────────────────────────
const PASSOS = ["Animais", "Quando e com quem", "Checklist", "Conferir e agendar"];
type ForaJanela = { numero: string; motivo: string };

function AssistenteAgendamento({ grupo, preSelecionados, animais, onSair, onCriado }: {
  grupo: GrupoListaEspera; preSelecionados: string[]; animais: AnimalRow[];
  onSair: () => void; onCriado: (resumo: string, dia: string, rascunho?: boolean) => void;
}) {
  const [passo, setPasso] = useState(1);
  const [ck, setCk] = useState<ChecklistDraft>(checklistVazio());
  const [tentouCk, setTentouCk] = useState(false);
  const [sel, setSel] = useState<Set<string>>(() => new Set(preSelecionados));
  const [fora, setFora] = useState<ForaJanela[]>([]);
  const [foraAberto, setForaAberto] = useState(false);
  const [data, setData] = useState(maisDiasIso(3));
  const [hora, setHora] = useState("08:00");
  const [quem, setQuem] = useState<"propria" | "veterinario">("propria");
  const [vetId, setVetId] = useState("");
  const [obs, setObs] = useState("");
  const [pessoas, setPessoas] = useState<any[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchPessoas().then(setPessoas).catch(() => setPessoas([])); }, []);
  const veterinarios = useMemo(
    () => pessoas.filter((p) => p.ativo !== false && (p.tipos || []).includes("Veterinário")).sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
    [pessoas],
  );

  const daJanela = grupo.animais.filter((a) => sel.has(a.numero_matriz));
  const total = daJanela.length + fora.length;
  const lotesDoAgendamento = Array.from(new Set([
    ...daJanela.map((a) => a.lote).filter(Boolean) as string[],
    ...fora.map((f) => animais.find((a) => a.numero === f.numero)?.grupo_primario).filter(Boolean) as string[],
  ]));
  const numerosAgendamento = [...daJanela.map((a) => a.numero_matriz), ...fora.map((f) => f.numero)];
  const vetSel = veterinarios.find((v) => String(v.id) === vetId);
  const responsavel = quem === "veterinario" ? (vetSel?.nome || "veterinário a escolher") : "equipe própria";
  const previa = `${diaSemana(data)} ${formatDate(data)} · ${hora || "sem hora"} · ${tituloGrupo(grupo)}${lotesDoAgendamento.length ? ` — ${lotesDoAgendamento.join(", ")}` : ""} · ${total} ${plural(total, "animal", "animais")} · ${responsavel}`;

  const alternar = (n: string) => setSel((p) => { const s = new Set(p); if (s.has(n)) s.delete(n); else s.add(n); return s; });

  function avancar() {
    setErro(null);
    if (passo === 1 && total === 0) { setErro("Marque pelo menos 1 animal."); return; }
    if (passo === 2) {
      if (!data) { setErro("Escolha a data."); return; }
      if (quem === "veterinario" && !vetId) { setErro("Escolha o veterinário."); return; }
    }
    if (passo === 3) {
      setTentouCk(true);
      const e = validarChecklist(ck);
      if (e) { setErro(e); return; }
    }
    setPasso((p) => Math.min(4, p + 1));
  }

  async function agendar(rascunho = false) {
    setSalvando(true); setErro(null);
    try {
      const r: any = await criarAgendamentoPreventivo({
        calendario_sanitario_id: grupo.calendario_id,
        animais_janela: daJanela.map((a) => a.numero_matriz),
        animais_fora: fora.map((f) => ({ numero_matriz: f.numero, motivo: f.motivo })),
        data_evento: data, hora: hora || null, modo_execucao: quem,
        veterinario_pessoa_id: quem === "veterinario" ? Number(vetId) : null, observacao: obs.trim() || null,
        rascunho, checklist: checklistParaPayload(ck),
      });
      const fin = r.financeiro as import("@/lib/api").BlocoFinanceiro | undefined;
      const extras = [
        fin && fin.contas_ativas > 0 ? `Conta a pagar de ${fin.conta_a_pagar_total.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })} lançada em Financeiro.` : "",
        fin && fin.compras.some((c) => c.estado === "ativo") ? "Compra comunicada em Cotações/Pedidos." : "",
        fin && fin.pagamentos.some((p) => p.estado === "ativo") ? "Pagamento já realizado vinculado." : "",
      ].filter(Boolean).join(" ");
      onCriado(`${tituloGrupo(grupo)}: ${total} ${plural(total, "animal", "animais")} para ${formatDate(r.data_evento)}${r.hora ? ` às ${r.hora}` : ""}, ${responsavel}.${extras ? ` ${extras}` : ""}`, r.data_evento, rascunho);
    } catch (e: any) { setErro(e.message || "Erro ao criar o agendamento"); } finally { setSalvando(false); }
  }

  const avisosData: string[] = [];
  if (data && data < hojeIso()) avisosData.push("Data passada: o agendamento entra como atrasado na Agenda.");
  if (data && grupo.janela_ate && data > grupo.janela_ate) avisosData.push("Depois do fim da janela de aplicação. Permitido: fica registrado.");
  if (data && grupo.janela_de && data < grupo.janela_de) avisosData.push("Antes da abertura da janela de aplicação. Permitido: fica registrado.");

  return (
    <div>
      <button type="button" className="btn-ghost" onClick={onSair}><ArrowLeft size={14} /> Lista de espera</button>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", flexWrap: "wrap", alignItems: "flex-start", margin: "0.3rem 0 0.8rem" }}>
        <div>
          <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>Criar agendamento · {tituloGrupo(grupo)}</h2>
          <p style={notaStyle}>{[grupo.produto, grupo.dose != null ? `${grupo.dose}${grupo.unidade ? ` ${grupo.unidade}` : ""}` : null, grupo.via].filter(Boolean).join(" · ")}</p>
        </div>
        <Pill cor="var(--amber)">Em montagem</Pill>
      </div>

      <ol aria-label="Passos" style={{ display: "flex", gap: "0.9rem", flexWrap: "wrap", listStyle: "none", padding: 0, margin: "0 0 1rem", fontSize: "0.8rem" }}>
        {PASSOS.map((p, i) => {
          const n = i + 1; const atual = n === passo; const feito = n < passo;
          return (
            <li key={p} aria-current={atual ? "step" : undefined} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontWeight: atual ? 700 : 600, color: atual ? "var(--dourado-light)" : "var(--text-muted)" }}>
              <span style={{
                width: 22, height: 22, borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: "0.72rem",
                border: `1px solid ${atual || feito ? "var(--dourado)" : "var(--border)"}`, background: atual ? "var(--pill-active-bg)" : "transparent",
              }}>{feito ? <Check size={12} /> : n}</span>{p}
            </li>
          );
        })}
      </ol>

      {passo === 1 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <section aria-labelledby="as-esq" className="card">
            <h3 id="as-esq" className="card-header mb-2">Na lista de espera (na janela) <span style={{ ...notaStyle, marginLeft: 6 }}>{grupo.animais.length}</span></h3>
            {grupo.animais.length === 0 && <p style={notaStyle}>Ninguém na lista de espera deste protocolo.</p>}
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {grupo.animais.map((a) => (
                <li key={a.numero_matriz} style={{ padding: "0.45rem 0", borderBottom: "1px solid var(--border)" }}>
                  <label style={{ display: "flex", gap: "0.6rem", alignItems: "center", cursor: "pointer" }}>
                    <input type="checkbox" checked={sel.has(a.numero_matriz)} onChange={() => alternar(a.numero_matriz)} aria-label={`Marcar ${a.numero_matriz}`} style={{ width: 18, height: 18 }} />
                    <span><b>{a.numero_matriz}{a.nome ? ` ${a.nome}` : ""}</b><span style={{ ...notaStyle, display: "block" }}>{a.lote || "Sem lote"} · {a.motivo_entrada}</span></span>
                  </label>
                </li>
              ))}
            </ul>
          </section>
          <section aria-labelledby="as-dir" className="card">
            <h3 id="as-dir" className="card-header mb-2">Neste agendamento <span style={{ ...notaStyle, marginLeft: 6 }}>{total}</span></h3>
            {total === 0 && <p style={notaStyle}>Nenhum animal ainda.</p>}
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {daJanela.map((a) => (
                <li key={a.numero_matriz} style={{ display: "flex", gap: "0.5rem", alignItems: "center", padding: "0.45rem 0", borderBottom: "1px solid var(--border)" }}>
                  <span style={{ flex: 1, minWidth: 0 }}><b>{a.numero_matriz}{a.nome ? ` ${a.nome}` : ""}</b><span style={{ ...notaStyle, display: "block" }}>{a.lote || "Sem lote"}</span></span>
                  <span style={{ color: "var(--green-light)", fontSize: "0.75rem", fontWeight: 700, display: "inline-flex", gap: 3, alignItems: "center" }}><Check size={12} />Na janela</span>
                  <button type="button" className="btn-ghost" aria-label={`Tirar ${a.numero_matriz} do agendamento`} onClick={() => alternar(a.numero_matriz)}><X size={14} /></button>
                </li>
              ))}
              {fora.map((f) => {
                const an = animais.find((x) => x.numero === f.numero);
                return (
                  <li key={f.numero} style={{ display: "flex", gap: "0.5rem", alignItems: "center", padding: "0.45rem 0", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ flex: 1, minWidth: 0 }}><b>{f.numero}{(an as any)?.nome ? ` ${(an as any).nome}` : ""}</b><span style={{ ...notaStyle, display: "block" }}>{an?.grupo_primario || "Sem lote"} · {f.motivo}</span></span>
                    <span style={{ color: "var(--amber)", fontSize: "0.75rem", fontWeight: 700, display: "inline-flex", gap: 3, alignItems: "center" }}><Flag size={12} />Fora da janela</span>
                    <button type="button" className="btn-ghost" aria-label={`Tirar ${f.numero} do agendamento`} onClick={() => setFora((p) => p.filter((x) => x.numero !== f.numero))}><X size={14} /></button>
                  </li>
                );
              })}
            </ul>
            <p role="status" style={{ margin: "0.7rem 0", fontWeight: 700, fontSize: "0.85rem" }}>
              {daJanela.length} na janela · {fora.length} fora da janela · {total} {plural(total, "animal", "animais")}
            </p>
            <button type="button" className="btn-secondary" onClick={() => setForaAberto(true)}><Plus size={14} /> Incluir animal de fora da janela</button>
          </section>
        </div>
      )}

      {passo === 2 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
            <div className="grid grid-cols-2 gap-3">
              <div><label htmlFor="as-data" style={labelStyle}>Data</label><input id="as-data" type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} /></div>
              <div><label htmlFor="as-hora" style={labelStyle}>Hora</label><input id="as-hora" type="time" style={inputStyle} value={hora} onChange={(e) => setHora(e.target.value)} /></div>
            </div>
            <Chips idBase="as-quem" rotulo="Quem faz" opcoes={["Veterinário", "Equipe própria"]} valor={quem === "veterinario" ? "Veterinário" : "Equipe própria"} onChange={(v) => { setQuem(v === "Veterinário" ? "veterinario" : "propria"); setVetId(""); }} />
            {quem === "veterinario" && (
              <div>
                <label htmlFor="as-vet" style={labelStyle}>Veterinário</label>
                <select id="as-vet" style={inputStyle} value={vetId} onChange={(e) => setVetId(e.target.value)}>
                  <option value="">Escolha o veterinário</option>
                  {veterinarios.map((v) => <option key={v.id} value={v.id}>{v.nome}</option>)}
                </select>
                {!veterinarios.length && <p style={{ ...notaStyle, marginTop: "0.3rem" }}>Nenhum veterinário cadastrado. Cadastre em Configurações › Cadastro › Pessoas.</p>}
              </div>
            )}
            <div><label htmlFor="as-onde" style={labelStyle}>Onde (curral/lote)</label><input id="as-onde" style={inputStyle} readOnly value={lotesDoAgendamento.join(", ")} /></div>
            <div><label htmlFor="as-obs" style={labelStyle}>Observação (opcional)</label><input id="as-obs" style={inputStyle} value={obs} onChange={(e) => setObs(e.target.value)} placeholder="ex.: tratador separa os animais antes" /></div>
            {avisosData.map((a) => <p key={a} role="status" style={{ display: "flex", gap: 6, alignItems: "flex-start", fontSize: "0.8rem", color: "var(--amber)" }}><AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} />{a}</p>)}
          </div>
          <div className="card">
            <h3 className="card-header mb-2 flex items-center gap-2"><CalendarCheck size={14} /> Como fica na Agenda</h3>
            <p style={{ fontWeight: 600, fontSize: "0.9rem" }}>{previa}</p>
            <p style={{ ...notaStyle, marginTop: "0.6rem" }}>Só o agendamento entra na Agenda, no dia. Os animais da lista de espera nunca aparecem lá.</p>
          </div>
        </div>
      )}

      {passo === 3 && (
        <div>
          <p style={{ ...notaStyle, marginBottom: "0.6rem" }}>
            O que precisa estar resolvido antes do dia. Nada aqui bloqueia o agendamento nem a aplicação: o que ficar pendente pede só a ciência na hora de Aplicar.
          </p>
          <ChecklistMontagem draft={ck} onChange={setCk} veterinarios={veterinarios} produto={grupo.produto} dataEvento={data} hora={hora} tentou={tentouCk}
                             calendarioId={grupo.calendario_id} animais={numerosAgendamento} />
        </div>
      )}

      {passo === 4 && (
        <div>
          <div className="card mb-3">
            <p style={{ fontSize: "1.05rem", fontWeight: 700 }}>{tituloGrupo(grupo)}{lotesDoAgendamento.length ? ` — ${lotesDoAgendamento.join(", ")}` : ""}</p>
            <p style={{ ...notaStyle, marginTop: "0.2rem" }}>{diaSemana(data)} {formatDate(data)}{hora ? `, ${hora}` : ""} · {responsavel}{obs.trim() ? ` · ${obs.trim()}` : ""}</p>
            <p style={{ marginTop: "0.6rem", fontSize: "0.88rem" }}><b>{daJanela.length}</b> na janela · <b>{fora.length}</b> fora da janela · <b>{total}</b> {plural(total, "animal", "animais")}</p>
            {fora.length > 0 && (
              <ul style={{ margin: "0.6rem 0 0", padding: 0, listStyle: "none" }}>
                {fora.map((f) => <li key={f.numero} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: "0.82rem", color: "var(--amber)" }}><Flag size={12} />{f.numero} fora da janela: {f.motivo}</li>)}
              </ul>
            )}
          </div>
          <ConferirFinanceiro calendarioId={grupo.calendario_id} animais={numerosAgendamento} draft={ck.financeiro}
                              estoqueDesc={ck.estoque.estado === "desconsiderado" && textoMotivo(ck.estoque.motivo, ck.estoque.outro) ? { motivo: textoMotivo(ck.estoque.motivo, ck.estoque.outro) } : null} />
          <div className="card">
            <h3 className="card-header mb-2">O que acontece ao agendar</h3>
            <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.85rem", lineHeight: 1.6 }}>
              <li>Checklist: {resumoChecklistDraft(ck, !!hora).resolvidos} de {resumoChecklistDraft(ck, !!hora).total} resolvidos ({resumoChecklistDraft(ck, !!hora).linhas.join("; ")}).</li>
              <li>{total} {plural(total, "animal sai", "animais saem")} da lista de espera e {plural(total, "entra", "entram")} neste agendamento.</li>
              <li>O agendamento aparece na Agenda em {formatDate(data)}, com {responsavel}.</li>
              <li>Quem ficou na lista de espera segue lá, sem aparecer na Agenda.</li>
              <li>Se cancelar depois, os animais da janela voltam para a lista de espera.</li>
            </ul>
          </div>
        </div>
      )}

      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem", marginTop: "0.8rem" }}>{erro}</p>}

      <div className="card" style={{ marginTop: "0.8rem", display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap", position: "sticky", bottom: 8, zIndex: 5 }}>
        {passo > 1 && <button type="button" className="btn-ghost" onClick={() => { setErro(null); setPasso(passo - 1); }}><ArrowLeft size={14} /> Voltar</button>}
        <span style={{ flex: 1 }} />
        {passo === 1 && total === 0 && <span style={notaStyle}>Marque pelo menos 1 animal</span>}
        {passo < 4
          ? <button type="button" className="btn-primary" onClick={avancar} disabled={passo === 1 && total === 0}>Continuar <ArrowRight size={14} /></button>
          : <>
              <button type="button" className="btn-secondary" onClick={() => agendar(true)} disabled={salvando || total === 0} title="Guarda como Em montagem; só entra na Agenda depois de confirmado">Salvar como rascunho</button>
              <button type="button" className="btn-primary-gold" onClick={() => agendar(false)} disabled={salvando || total === 0}><CalendarCheck size={14} /> {salvando ? "Agendando…" : "Criar agendamento"}</button>
            </>}
      </div>

      {foraAberto && (
        <ForaDaJanelaModal
          animais={animais} grupo={grupo}
          jaNoAgendamento={new Set([...daJanela.map((a) => a.numero_matriz), ...fora.map((f) => f.numero)])}
          onFechar={() => setForaAberto(false)}
          onIncluir={(f) => setFora((p) => [...p.filter((x) => x.numero !== f.numero), f])}
        />
      )}
    </div>
  );
}

function ForaDaJanelaModal({ animais, grupo, jaNoAgendamento, onFechar, onIncluir }: {
  animais: AnimalRow[]; grupo: GrupoListaEspera; jaNoAgendamento: Set<string>;
  onFechar: () => void; onIncluir: (f: ForaJanela) => void;
}) {
  const [q, setQ] = useState("");
  const [escolhido, setEscolhido] = useState<string>("");
  const [motivo, setMotivo] = useState("");
  const [outro, setOutro] = useState("");
  const [tentou, setTentou] = useState(false);
  const naEspera = useMemo(() => new Set(grupo.animais.map((a) => a.numero_matriz)), [grupo]);
  const busca = q.trim().toLowerCase();
  const resultados = busca
    ? animais.filter((a) => a.ativo !== false && (a.numero.toLowerCase().includes(busca) || ((a as any).nome || "").toLowerCase().includes(busca) || (a.grupo_primario || "").toLowerCase().includes(busca))).slice(0, 6)
    : [];
  const texto = motivo === "Outro" ? outro.trim() : motivo;
  const an = animais.find((a) => a.numero === escolhido);

  function incluir(outroMais: boolean) {
    setTentou(true);
    if (!escolhido || !texto) return;
    onIncluir({ numero: escolhido, motivo: texto });
    if (outroMais) { setQ(""); setEscolhido(""); setMotivo(""); setOutro(""); setTentou(false); } else onFechar();
  }

  return (
    <Modal title="Incluir animal de fora da janela" onClose={onFechar} width="560px"><div className="le-raiz">
      <p style={{ ...notaStyle, marginBottom: "0.8rem" }}>Por conta da fazenda, com motivo. Não bloqueia: o animal entra marcado “fora da janela” e o motivo fica no histórico.</p>
      <label htmlFor="fj-q" style={labelStyle}>Buscar por brinco, nome ou lote</label>
      <div style={{ position: "relative" }}>
        <Search size={14} style={{ position: "absolute", left: 8, top: 11, color: "var(--text-muted)" }} />
        <input id="fj-q" type="search" autoComplete="off" style={{ ...inputStyle, paddingLeft: 28 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="ex.: 6110" />
      </div>
      {!busca && <p style={{ ...notaStyle, marginTop: "0.4rem" }}>Digite o brinco, o nome ou o lote.</p>}
      {busca && !resultados.length && <p style={{ ...notaStyle, marginTop: "0.4rem" }}>Nenhum animal encontrado.</p>}
      <ul style={{ listStyle: "none", margin: "0.5rem 0 0", padding: 0 }}>
        {resultados.map((a) => {
          const jaEsta = jaNoAgendamento.has(a.numero); const espera = naEspera.has(a.numero);
          return (
            <li key={a.numero} style={{ display: "flex", gap: "0.5rem", alignItems: "center", padding: "0.4rem 0", borderBottom: "1px solid var(--border)" }}>
              <span style={{ flex: 1, minWidth: 0 }}><b>{a.numero}{(a as any).nome ? ` ${(a as any).nome}` : ""}</b><span style={{ ...notaStyle, display: "block" }}>{a.grupo_primario || "Sem lote"}</span></span>
              {jaEsta ? <span style={notaStyle}>já está no agendamento</span>
                : espera ? <span style={notaStyle}>já está na lista de espera (na janela)</span>
                : <button type="button" className="btn-secondary" onClick={() => { setEscolhido(a.numero); setMotivo(""); setTentou(false); }}>Escolher</button>}
            </li>
          );
        })}
      </ul>

      {an && (
        <div style={{ marginTop: "0.9rem", display: "flex", flexDirection: "column", gap: "0.7rem" }}>
          <div className="card" style={{ padding: "0.6rem 0.8rem" }}>
            <b>Animal escolhido: {an.numero}{(an as any).nome ? ` ${(an as any).nome}` : ""}</b>
            <span style={{ ...notaStyle, display: "block" }}>{an.grupo_primario || "Sem lote"}{an.sexo ? ` · ${an.sexo === "F" ? "fêmea" : "macho"}` : ""} · fora da janela deste protocolo</span>
          </div>
          <Chips idBase="fj-mot" rotulo="Motivo (obrigatório; nada vem marcado)" opcoes={MOTIVOS_FORA} valor={motivo} onChange={setMotivo} />
          {motivo === "Outro" && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={outro} onChange={(e) => setOutro(e.target.value)} />}
          {tentou && !texto && <p role="alert" style={{ color: "var(--red)", fontSize: "0.78rem" }}>Escolha o motivo para incluir fora da janela.</p>}
          <p style={{ display: "flex", gap: 6, alignItems: "flex-start", fontSize: "0.8rem", color: "var(--amber)" }}><AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} /><span><b>Fora da janela.</b> Não bloqueia: o animal entra marcado e o motivo fica no histórico.</span></p>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", flexWrap: "wrap" }}>
        {an && <button type="button" className="btn-primary-gold" onClick={() => incluir(false)}><Check size={14} /> Incluir</button>}
        {an && <button type="button" className="btn-secondary" onClick={() => incluir(true)}><Plus size={14} /> Incluir e adicionar outro</button>}
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
      </div>
    </div></Modal>
  );
}
