"use client";
// ─────────────────────────────────────────────────────────────────────────────
// TELA AGENDA do app móvel (/app) — "Hoje, <data>" com as tarefas do dia
// (e as atrasadas ainda pendentes) em cartões grandes de tocar. Cada cartão
// tem um check circular que marca/desmarca "realizado" no MESMO endpoint do
// site desktop (POST/DELETE /agenda/realizados). Funciona offline: a lista vem
// do cache e o "realizado" entra na fila de envio.
// ─────────────────────────────────────────────────────────────────────────────
import { useCallback, useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { MobCard, MobTitulo, MobCheck, MobAviso, corCategoria } from "@/components/mobile/ui";
import { fetchAgenda, fetchApresentacaoDieta, today, type ApresentacaoDieta } from "@/lib/api";
import { fetchComCache, cacheEm, enviarOuEnfileirar, useOnline } from "@/lib/offline";

/** Soma `n` dias a uma data ISO ("YYYY-MM-DD") e devolve outra ISO. */
function maisDias(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().split("T")[0];
}

type Evento = {
  id: string;
  data: string;
  categoria: string;
  descricao: string;
  numero_animal?: string | null;
  observacao?: string | null;
  lote?: string | null;
  tipo?: string | null;
  animais?: string[] | null;
  produto?: string | null;
  dose?: number | null;
  unidade?: string | null;
  via?: string | null;
  dia?: number | null;
  hormonio?: string | null;
  protocolo?: string | null;
  grupo?: string | null;
  grupo_titulo?: string | null;
  ref?: string | null;
};

// Um grupo de aplicações do mesmo protocolo/dia/data (lote) — para oferecer
// "lote ou individual" no app. Cada item continua sendo um evento próprio.
type GrupoSan = { grupo: string; titulo: string; produto: string | null; data: string; categoria: string; itens: Evento[] };
type Renderavel = { kind: "evento"; e: Evento } | { kind: "grupo"; g: GrupoSan };

// Agrupa os eventos de protocolo sanitário que compartilham `grupo`; os demais
// passam direto. O grupo aparece na posição do seu primeiro item.
function montarLista(evs: Evento[]): Renderavel[] {
  const grupos = new Map<string, GrupoSan>();
  const saida: Renderavel[] = [];
  for (const e of evs) {
    if (e.tipo === "protocolo_sanitario" && e.grupo) {
      let g = grupos.get(e.grupo);
      if (!g) {
        g = { grupo: e.grupo, titulo: e.grupo_titulo || e.descricao, produto: e.produto || null, data: e.data, categoria: e.categoria, itens: [] };
        grupos.set(e.grupo, g);
        saida.push({ kind: "grupo", g });
      }
      g.itens.push(e);
    } else {
      saida.push({ kind: "evento", e });
    }
  }
  return saida;
}

type Agenda = { eventos?: Evento[] };

// Categoria do backend ("Reprodutivo", "Gestão/Financeiro", "alimentacao"…)
// → chave de cor (corCategoria) + rótulo em MAIÚSCULAS do cartão.
function catInfo(categoria: string): { chave: string; rotulo: string } {
  const c = (categoria || "").toLowerCase();
  if (c === "reprodutivo") return { chave: "reprodutivo", rotulo: "REPRODUTIVO" };
  if (c === "sanidade") return { chave: "sanidade", rotulo: "SANIDADE" };
  if (c === "produção" || c === "producao") return { chave: "producao", rotulo: "PRODUÇÃO" };
  if (c === "alimentação" || c === "alimentacao") return { chave: "alimentacao", rotulo: "ALIMENTAÇÃO" };
  if (c === "gestão/financeiro" || c === "financeiro") return { chave: "financeiro", rotulo: "FINANCEIRO" };
  return { chave: "atividades", rotulo: (categoria || "ATIVIDADE").toUpperCase() };
}

// Identificação em negrito + detalhe cinza de cada cartão, a partir do evento.
function linhas(e: Evento): { principal: string; detalhe: string | null } {
  if (e.numero_animal) return { principal: `Nº ${e.numero_animal}`, detalhe: e.descricao || e.observacao || null };
  if (e.tipo === "protocolo_iatf" && e.animais?.length) {
    return { principal: e.descricao, detalhe: `${e.animais.length} animal${e.animais.length !== 1 ? "is" : ""}` };
  }
  if (e.lote) return { principal: `Lote ${e.lote}`, detalhe: e.descricao || e.observacao || null };
  return { principal: e.descricao, detalhe: e.observacao || null };
}

function resumo(e: Evento): string {
  const { principal } = linhas(e);
  return `${principal} — ${e.descricao}`.slice(0, 80);
}

function fmtData(iso: string, opts: Intl.DateTimeFormatOptions): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", opts);
}

function num(v?: number | null, casas = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}

function fmtCacheEm(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function AgendaMovel() {
  const online = useOnline();
  const hoje = today();
  const chaveCache = `agenda_mob_${hoje}`;

  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [doCache, setDoCache] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(false);
  // Ids marcados como "feito" nesta sessão (otimista) — mantém o cartão visível
  // para permitir desfazer, já que o backend some com ele no próximo reload.
  const [feitos, setFeitos] = useState<Set<string>>(new Set());
  const [aviso, setAviso] = useState<{ tipo: "ok" | "offline" | "erro"; msg: string } | null>(null);
  // Protocolo IATF: cartões expansíveis. Primeiro pergunta LOTE ou INDIVIDUAL;
  // em lote confirma todas de uma vez, individual é vaca por vaca (Sim/Não).
  const [iatfAberto, setIatfAberto] = useState<Set<string>>(new Set());
  const [iatfChecks, setIatfChecks] = useState<Record<string, Set<string>>>({});
  const [iatfModo, setIatfModo] = useState<Record<string, "lote" | "individual">>({});
  // Vacas já confirmadas individualmente dentro de um cartão (some da lista).
  const [iatfVacasFeitas, setIatfVacasFeitas] = useState<Record<string, Set<string>>>({});

  // Grupos de protocolo sanitário (aplicação em lote): mesma pergunta lote/individual.
  const [sanAberto, setSanAberto] = useState<Set<string>>(new Set());
  const [sanModo, setSanModo] = useState<Record<string, "lote" | "individual">>({});

  // Alerta de nova dieta: cartão expansível que mostra a apresentação da dieta
  // (produtos, por cabeça, total/dia, total/trato e kg no vagão) para o funcionário.
  const [dietaAberta, setDietaAberta] = useState<Set<string>>(new Set());
  const [dietaApres, setDietaApres] = useState<Record<string, ApresentacaoDieta | null>>({});
  function abrirDieta(e: Evento) {
    setDietaAberta((p) => { const n = new Set(p); n.has(e.id) ? n.delete(e.id) : n.add(e.id); return n; });
    if (e.ref && !(e.id in dietaApres)) {
      setDietaApres((d) => ({ ...d, [e.id]: null }));
      fetchApresentacaoDieta(Number(e.ref)).then((a) => setDietaApres((d) => ({ ...d, [e.id]: a }))).catch(() => setDietaApres((d) => ({ ...d, [e.id]: null })));
    }
  }

  const abrirSan = (grupo: string) => setSanAberto((p) => { const n = new Set(p); n.has(grupo) ? n.delete(grupo) : n.add(grupo); return n; });

  // Confirma um item (uma matriz) do grupo — usa o id próprio do evento, então
  // o backend dá a baixa de estoque daquela aplicação como já fazia.
  async function confirmarSanItem(it: Evento) {
    if (feitos.has(it.id)) return;
    setAviso(null);
    setFeitos((p) => new Set(p).add(it.id));
    try {
      const r = await enviarOuEnfileirar("/agenda/realizados", { evento_id: it.id }, `Concluir: ${resumo(it)}`, "POST");
      if (!r.enviado) setAviso({ tipo: "offline", msg: "Guardado — será enviado quando conectar." });
    } catch (err) {
      setFeitos((p) => { const n = new Set(p); n.delete(it.id); return n; });
      setAviso({ tipo: "erro", msg: err instanceof Error ? err.message : "Não foi possível salvar." });
    }
  }
  // Confirma todas as matrizes pendentes do grupo (lote).
  async function confirmarSanLote(g: GrupoSan) {
    for (const it of g.itens) {
      if (!feitos.has(it.id)) await confirmarSanItem(it);
    }
    setAviso({ tipo: "ok", msg: `Aplicação confirmada em ${g.itens.length} animal(is).` });
  }

  const abrirIatf = (id: string, animais: string[]) => {
    setIatfAberto((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
    setIatfChecks((p) => (p[id] ? p : { ...p, [id]: new Set(animais) }));
  };
  const toggleVaca = (id: string, numero: string) => setIatfChecks((p) => {
    const atual = new Set(p[id] || []);
    atual.has(numero) ? atual.delete(numero) : atual.add(numero);
    return { ...p, [id]: atual };
  });

  async function confirmarIatf(e: Evento, animaisSel: string[], individual = false) {
    if (!animaisSel.length) return;
    setAviso(null);
    // Só marca o cartão inteiro como feito no modo lote; individual mantém o
    // cartão para confirmar as demais vacas.
    if (!individual) setFeitos((p) => new Set(p).add(e.id));
    try {
      const r = await enviarOuEnfileirar("/agenda/realizados",
        { evento_id: e.id, animais: animaisSel },
        `IATF ${e.descricao} — ${animaisSel.length} vaca(s)`, "POST");
      if (individual) setIatfVacasFeitas((p) => { const n = new Set(p[e.id] || []); animaisSel.forEach((a) => n.add(a)); return { ...p, [e.id]: n }; });
      if (!r.enviado) setAviso({ tipo: "offline", msg: "Guardado — será enviado quando conectar." });
      else setAviso({ tipo: "ok", msg: `Confirmado em ${animaisSel.length} vaca(s).` });
    } catch (err) {
      if (!individual) setFeitos((p) => { const n = new Set(p); n.delete(e.id); return n; });
      setAviso({ tipo: "erro", msg: err instanceof Error ? err.message : "Não foi possível salvar." });
    }
  }

  const carregar = useCallback(async () => {
    setCarregando(true);
    const { dados, doCache } = await fetchComCache<Agenda>(chaveCache, () => fetchAgenda(hoje));
    setAgenda(dados);
    setDoCache(doCache);
    // fetchComCache engole o erro e cai no cache; se falhou ONLINE é erro de
    // verdade (servidor/permissão 403), não "offline".
    setErro(doCache && navigator.onLine);
    setFeitos(new Set());
    setCarregando(false);
  }, [chaveCache, hoje]);

  useEffect(() => { carregar(); }, [carregar]);

  // Só hoje e as atrasadas ainda pendentes (data <= hoje), atrasadas primeiro.
  const eventos = (agenda?.eventos || [])
    .filter((e) => e.data <= hoje)
    .sort((a, b) => (a.data < b.data ? -1 : a.data > b.data ? 1 : 0));

  const pendentes = eventos.filter((e) => !feitos.has(e.id)).length;

  async function alternar(e: Evento) {
    const jaFeito = feitos.has(e.id);
    setAviso(null);
    // Atualiza otimista na hora.
    setFeitos((p) => {
      const n = new Set(p);
      jaFeito ? n.delete(e.id) : n.add(e.id);
      return n;
    });
    // Dar baixa num evento sanitário de um animal COM medicamento padrão:
    // gera a aplicação (que dá a saída de estoque) em vez de só marcar feito.
    const darBaixaSanidade = !jaFeito && e.tipo === "evento_sanitario" && e.numero_animal && e.produto && e.dose != null && e.unidade;
    try {
      let r;
      if (darBaixaSanidade) {
        r = await enviarOuEnfileirar("/sanidade/aplicacoes", {
          data_aplicacao: hoje, animais: [e.numero_animal],
          itens: [{ produto: e.produto, quantidade: e.dose, unidade: e.unidade, via: e.via || undefined }],
        }, `Aplicação ${e.produto} — animal ${e.numero_animal}`, "POST");
      } else if (jaFeito) {
        r = await enviarOuEnfileirar(`/agenda/realizados/${encodeURIComponent(e.id)}`, {}, `Desfazer: ${resumo(e)}`, "DELETE");
      } else {
        r = await enviarOuEnfileirar("/agenda/realizados", { evento_id: e.id }, `Concluir: ${resumo(e)}`, "POST");
      }
      if (!r.enviado) setAviso({ tipo: "offline", msg: "Guardado — será enviado quando conectar." });
      else if (darBaixaSanidade) setAviso({ tipo: "ok", msg: "Aplicação lançada e estoque baixado." });
    } catch (err) {
      // Servidor recusou (ex.: 403 sem permissão) — desfaz o otimista.
      setFeitos((p) => {
        const n = new Set(p);
        jaFeito ? n.add(e.id) : n.delete(e.id);
        return n;
      });
      setAviso({ tipo: "erro", msg: err instanceof Error ? err.message : "Não foi possível salvar." });
    }
  }

  const cacheISO = cacheEm(chaveCache);

  // Próximos 2 dias (amanhã e depois de amanhã) para consulta antecipada.
  const d1 = maisDias(hoje, 1);
  const d2 = maisDias(hoje, 2);
  const eventosDe = (dia: string) => (agenda?.eventos || []).filter((e) => e.data === dia);

  // Cartão de um GRUPO de protocolo sanitário (lote) — pergunta lote/individual,
  // depois confirma todas ou uma matriz por vez.
  function renderGrupoSanitario(g: GrupoSan) {
    const { chave, rotulo } = catInfo(g.categoria);
    const aberto = sanAberto.has(g.grupo);
    const modo = sanModo[g.grupo];
    const feitasCount = g.itens.filter((it) => feitos.has(it.id)).length;
    const tudoFeito = feitasCount === g.itens.length;
    return (
      <MobCard key={g.grupo} style={{ marginBottom: "0.6rem" }}>
        <button type="button" onClick={() => abrirSan(g.grupo)}
          style={{ width: "100%", background: "none", border: "none", padding: 0, textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "0.68rem", fontWeight: 800, letterSpacing: "0.06em", color: corCategoria(chave), marginBottom: "0.2rem" }}>{rotulo}</div>
            <div style={{ fontSize: "1.1rem", fontWeight: 800, lineHeight: 1.2, color: tudoFeito ? "var(--mob-muted)" : "var(--mob-text)", textDecoration: tudoFeito ? "line-through" : "none" }}>{g.titulo}</div>
            <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.15rem" }}>
              {g.itens.length} animal{g.itens.length !== 1 ? "is" : ""}{g.produto ? ` · ${g.produto}` : ""}{feitasCount ? ` · ${feitasCount} feito(s)` : ""}
            </div>
          </div>
          <ChevronRight size={20} style={{ color: "var(--mob-muted)", transform: aberto ? "rotate(90deg)" : "none", transition: "transform .15s", flexShrink: 0 }} />
        </button>

        {aberto && (
          <div style={{ marginTop: "0.7rem", borderTop: "1px solid var(--mob-border)", paddingTop: "0.6rem" }}>
            {g.produto && (
              <div style={{ fontSize: "0.82rem", marginBottom: "0.6rem" }}><strong>Aplicar:</strong> {g.produto}</div>
            )}
            {!modo ? (
              <>
                <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginBottom: "0.55rem" }}>Como deseja confirmar a aplicação?</p>
                <div style={{ display: "flex", gap: "0.6rem" }}>
                  <button type="button" className="mob-btn" style={{ flex: 1 }} onClick={() => setSanModo((p) => ({ ...p, [g.grupo]: "lote" }))}>Em lote (todas)</button>
                  <button type="button" className="mob-btn mob-btn-sec" style={{ flex: 1 }} onClick={() => setSanModo((p) => ({ ...p, [g.grupo]: "individual" }))}>Individual</button>
                </div>
              </>
            ) : modo === "lote" ? (
              <>
                <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginBottom: "0.5rem" }}>Animais do lote:</p>
                {g.itens.map((it) => (
                  <div key={it.id} style={{ padding: "0.45rem 0.2rem", borderBottom: "1px solid var(--mob-border)", fontWeight: 800, fontSize: "1.02rem", color: feitos.has(it.id) ? "var(--mob-muted)" : "var(--mob-text)", textDecoration: feitos.has(it.id) ? "line-through" : "none" }}>
                    {it.numero_animal}
                  </div>
                ))}
                <button type="button" className="mob-btn" style={{ marginTop: "0.7rem" }} disabled={tudoFeito} onClick={() => confirmarSanLote(g)}>
                  Confirmar todas ({g.itens.length - feitasCount} pendente{g.itens.length - feitasCount !== 1 ? "s" : ""})
                </button>
              </>
            ) : (
              <>
                <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginBottom: "0.5rem" }}>Confirme animal por animal — aplicado?</p>
                {g.itens.map((it) => {
                  const jaFeita = feitos.has(it.id);
                  return (
                    <div key={it.id} style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.2rem", borderBottom: "1px solid var(--mob-border)" }}>
                      <span style={{ fontWeight: 800, fontSize: "1.05rem", flex: 1, color: jaFeita ? "var(--mob-muted)" : "var(--mob-text)", textDecoration: jaFeita ? "line-through" : "none" }}>{it.numero_animal}</span>
                      {jaFeita ? (
                        <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--mob-verde)" }}>✓ Aplicado</span>
                      ) : (
                        <button type="button" className="mob-btn" style={{ width: "auto", padding: "0.4rem 1.1rem" }} onClick={() => confirmarSanItem(it)}>Sim</button>
                      )}
                    </div>
                  );
                })}
                {tudoFeito && <p style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--mob-verde)", marginTop: "0.6rem" }}>Todos os animais confirmados.</p>}
              </>
            )}
          </div>
        )}
      </MobCard>
    );
  }

  function renderRenderavel(r: Renderavel) {
    return r.kind === "grupo" ? renderGrupoSanitario(r.g) : renderCartao(r.e);
  }

  function renderCartao(e: Evento) {
    const { chave, rotulo } = catInfo(e.categoria);
    const feito = feitos.has(e.id);
    const atrasada = e.data < hoje;

    // Protocolo IATF: cartão expansível com as vacas e aplicação individual.
    if (e.tipo === "protocolo_iatf" && e.animais?.length) {
      const aberto = iatfAberto.has(e.id);
      const sel = iatfChecks[e.id] || new Set(e.animais);
      return (
        <MobCard key={e.id} style={{ marginBottom: "0.6rem" }}>
          <button type="button" onClick={() => abrirIatf(e.id, e.animais!)}
            style={{ width: "100%", background: "none", border: "none", padding: 0, textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: "0.68rem", fontWeight: 800, letterSpacing: "0.06em", color: corCategoria(chave), marginBottom: "0.2rem" }}>{rotulo}</div>
              <div style={{ fontSize: "1.1rem", fontWeight: 800, lineHeight: 1.2, color: feito ? "var(--mob-muted)" : "var(--mob-text)", textDecoration: feito ? "line-through" : "none" }}>{e.descricao}</div>
              <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.15rem" }}>
                {e.animais!.length} animal{e.animais!.length !== 1 ? "is" : ""}{e.hormonio ? ` · ${e.hormonio}` : ""}
              </div>
            </div>
            <ChevronRight size={20} style={{ color: "var(--mob-muted)", transform: aberto ? "rotate(90deg)" : "none", transition: "transform .15s", flexShrink: 0 }} />
          </button>

          {aberto && (() => {
            const modo = iatfModo[e.id];
            const feitasVaca = iatfVacasFeitas[e.id] || new Set<string>();
            const pendentes = e.animais!.filter((n) => !feitasVaca.has(n));
            return (
              <div style={{ marginTop: "0.7rem", borderTop: "1px solid var(--mob-border)", paddingTop: "0.6rem" }}>
                {e.hormonio && (
                  <div style={{ fontSize: "0.82rem", marginBottom: "0.6rem" }}>
                    <strong>Aplicar:</strong> {e.hormonio}
                  </div>
                )}

                {/* Antes de tudo: aplicação em lote ou individual? */}
                {!modo ? (
                  <>
                    <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginBottom: "0.55rem" }}>Como deseja confirmar a aplicação?</p>
                    <div style={{ display: "flex", gap: "0.6rem" }}>
                      <button type="button" className="mob-btn" style={{ flex: 1 }} onClick={() => setIatfModo((p) => ({ ...p, [e.id]: "lote" }))}>Em lote (todas)</button>
                      <button type="button" className="mob-btn mob-btn-sec" style={{ flex: 1 }} onClick={() => setIatfModo((p) => ({ ...p, [e.id]: "individual" }))}>Individual</button>
                    </div>
                  </>
                ) : modo === "lote" ? (
                  <>
                    <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginBottom: "0.5rem" }}>Marque as vacas que receberam:</p>
                    {e.animais!.map((numero) => (
                      <label key={numero} style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.55rem 0.2rem", borderBottom: "1px solid var(--mob-border)", cursor: "pointer" }}>
                        <input type="checkbox" checked={sel.has(numero)} onChange={() => toggleVaca(e.id, numero)} style={{ width: 20, height: 20 }} />
                        <span style={{ fontWeight: 800, fontSize: "1.05rem" }}>{numero}</span>
                      </label>
                    ))}
                    <button type="button" className="mob-btn" style={{ marginTop: "0.7rem" }}
                      disabled={feito || !sel.size} onClick={() => confirmarIatf(e, Array.from(sel))}>
                      Confirmar aplicação ({sel.size}/{e.animais!.length})
                    </button>
                  </>
                ) : (
                  <>
                    <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginBottom: "0.5rem" }}>
                      Confirme vaca por vaca — aplicado?
                    </p>
                    {e.animais!.map((numero) => {
                      const jaFeita = feitasVaca.has(numero);
                      return (
                        <div key={numero} style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.2rem", borderBottom: "1px solid var(--mob-border)" }}>
                          <span style={{ fontWeight: 800, fontSize: "1.05rem", flex: 1, color: jaFeita ? "var(--mob-muted)" : "var(--mob-text)", textDecoration: jaFeita ? "line-through" : "none" }}>{numero}</span>
                          {jaFeita ? (
                            <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--mob-verde)" }}>✓ Aplicado</span>
                          ) : (
                            <button type="button" className="mob-btn" style={{ width: "auto", padding: "0.4rem 1.1rem" }}
                              onClick={() => confirmarIatf(e, [numero], true)}>Sim</button>
                          )}
                        </div>
                      );
                    })}
                    {!pendentes.length && (
                      <p style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--mob-verde)", marginTop: "0.6rem" }}>Todas as vacas confirmadas.</p>
                    )}
                  </>
                )}
              </div>
            );
          })()}
        </MobCard>
      );
    }

    // Alerta de nova dieta: cartão expansível que abre a apresentação para o
    // funcionário conferir o vagão (produtos, por cabeça, total/dia e /trato).
    if (e.tipo === "nova_dieta") {
      const aberto = dietaAberta.has(e.id);
      const a = dietaApres[e.id];
      return (
        <MobCard key={e.id} style={{ marginBottom: "0.6rem" }}>
          <button type="button" onClick={() => abrirDieta(e)}
            style={{ width: "100%", background: "none", border: "none", padding: 0, textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: "0.68rem", fontWeight: 800, letterSpacing: "0.06em", color: corCategoria(chave), marginBottom: "0.2rem" }}>{rotulo}</div>
              <div style={{ fontSize: "1.1rem", fontWeight: 800, lineHeight: 1.2, color: feito ? "var(--mob-muted)" : "var(--mob-text)", textDecoration: feito ? "line-through" : "none" }}>{e.descricao}</div>
              <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.15rem" }}>Toque para ver os produtos e o vagão</div>
            </div>
            <ChevronRight size={20} style={{ color: "var(--mob-muted)", transform: aberto ? "rotate(90deg)" : "none", transition: "transform .15s", flexShrink: 0 }} />
          </button>
          {aberto && (
            <div style={{ marginTop: "0.7rem", borderTop: "1px solid var(--mob-border)", paddingTop: "0.6rem" }}>
              {a === null ? (
                <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>Carregando dieta…</p>
              ) : a ? (
                <>
                  <div style={{ fontSize: "0.82rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                    Lote {a.lote}{a.nome ? ` · ${a.nome}` : ""} — {a.qtd_animais} {a.qtd_animais === 1 ? "animal" : "animais"} · {a.num_tratos} tratos
                  </div>
                  {a.itens.map((it, i) => (
                    <div key={i} style={{ padding: "0.5rem 0", borderTop: i ? "1px solid var(--mob-border)" : "none" }}>
                      <div style={{ fontWeight: 800, fontSize: "0.98rem" }}>{it.alimento}</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", marginTop: "0.2rem", fontSize: "0.82rem" }}>
                        <span style={{ color: "var(--mob-verde)", fontWeight: 800 }}>{num(it.total_trato)} {it.unidade}/trato</span>
                        <span style={{ color: "var(--mob-ambar)", fontWeight: 700 }}>{num(it.total_dia)} {it.unidade}/dia</span>
                        <span style={{ color: "var(--mob-muted)" }}>{it.por_cabeca != null ? `${num(it.por_cabeca, 3)} ${it.unidade}/cab` : "—/cab"}</span>
                      </div>
                    </div>
                  ))}
                  <div style={{ marginTop: "0.6rem", padding: "0.55rem 0.7rem", background: "var(--mob-surface)", border: "1px solid var(--mob-border)", borderRadius: 10, fontSize: "0.85rem", fontWeight: 800 }}>
                    Vagão do lote: <span style={{ color: "var(--mob-verde)" }}>{num(a.vagao_kg_trato)} kg/trato</span> · {num(a.vagao_kg_dia)} kg/dia
                  </div>
                </>
              ) : (
                <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>Não foi possível carregar a dieta.</p>
              )}
              <div style={{ marginTop: "0.7rem", display: "flex", justifyContent: "flex-end" }}>
                <MobCheck feito={feito} onClick={() => alternar(e)} />
              </div>
            </div>
          )}
        </MobCard>
      );
    }

    const { principal, detalhe } = linhas(e);
    return (
      <MobCard key={e.id} style={{ marginBottom: "0.6rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "0.68rem", fontWeight: 800, letterSpacing: "0.06em", color: corCategoria(chave), marginBottom: "0.2rem" }}>
              {rotulo}
            </div>
            <div style={{ fontSize: "1.15rem", fontWeight: 800, lineHeight: 1.2, color: feito ? "var(--mob-muted)" : "var(--mob-text)", textDecoration: feito ? "line-through" : "none" }}>
              {principal}
            </div>
            {detalhe && (
              <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.15rem", overflow: "hidden", textOverflow: "ellipsis" }}>
                {detalhe}
              </div>
            )}
            {atrasada && (
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--mob-vermelho)", marginTop: "0.25rem" }}>
                Atrasada · {fmtData(e.data, { day: "2-digit", month: "2-digit" })}
              </div>
            )}
          </div>
          <MobCheck feito={feito} onClick={() => alternar(e)} />
        </div>
      </MobCard>
    );
  }

  // Seção recolhível de um dia seguinte (amanhã / depois de amanhã).
  function DiaSeguinte({ dia, prefixo }: { dia: string; prefixo: string }) {
    const evs = eventosDe(dia);
    return (
      <details style={{ marginTop: "0.7rem" }}>
        <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: "0.95rem", padding: "0.85rem 1rem", background: "var(--mob-surface)", border: "1px solid var(--mob-border)", borderRadius: 14, listStyle: "none", display: "flex", justifyContent: "space-between", alignItems: "center", boxShadow: "var(--mob-sombra)" }}>
          <span>{prefixo}, {fmtData(dia, { day: "numeric", month: "long" })}</span>
          <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)", fontWeight: 700 }}>{evs.length}</span>
        </summary>
        <div style={{ marginTop: "0.6rem" }}>
          {evs.length === 0
            ? <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem", padding: "0.3rem 0.2rem" }}>Nada agendado.</p>
            : montarLista(evs).map(renderRenderavel)}
        </div>
      </details>
    );
  }

  return (
    <div>
      <MobTitulo badge={`${pendentes} ${pendentes === 1 ? "Tarefa" : "Tarefas"}`}>
        Hoje, {fmtData(hoje, { day: "numeric", month: "long" }).replace(/ de (.)/, (_, l) => ` de ${l.toUpperCase()}`)}
      </MobTitulo>

      {/* Modo offline: agenda veio do cache */}
      {doCache && !online && cacheISO && (
        <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", margin: "0 0 0.8rem" }}>
          Sem internet — mostrando agenda de {fmtCacheEm(cacheISO)}.
        </p>
      )}

      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}

      {carregando && !agenda ? (
        <p style={{ color: "var(--mob-muted)", padding: "1.5rem 0" }}>Carregando agenda…</p>
      ) : erro && !agenda ? (
        <MobAviso tipo="erro">Não foi possível carregar a agenda. Tente novamente mais tarde.</MobAviso>
      ) : (
        <>
          {erro && agenda && (
            <p style={{ fontSize: "0.78rem", color: "var(--mob-ambar)", margin: "0 0 0.8rem" }}>
              Não foi possível atualizar — mostrando a última agenda salva.
            </p>
          )}

          {!agenda ? (
            <p style={{ color: "var(--mob-muted)", padding: "1.5rem 0" }}>
              Sem internet e sem agenda salva ainda. Conecte-se uma vez para baixar.
            </p>
          ) : eventos.length === 0 ? (
            <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--mob-muted)" }}>
              <p style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--mob-text)" }}>Nada pendente para hoje 🎉</p>
              <p style={{ fontSize: "0.85rem", marginTop: "0.4rem" }}>
                Toda a agenda do dia está em dia. Bom trabalho!
              </p>
            </div>
          ) : (
            montarLista(eventos).map(renderRenderavel)
          )}

          {/* Consulta antecipada: os dois dias seguintes, recolhidos. */}
          {agenda && (
            <>
              <DiaSeguinte dia={d1} prefixo="Amanhã" />
              <DiaSeguinte dia={d2} prefixo="Depois de amanhã" />
            </>
          )}
        </>
      )}
    </div>
  );
}
