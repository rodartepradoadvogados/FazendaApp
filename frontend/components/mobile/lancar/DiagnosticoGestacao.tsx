"use client";
// Diagnóstico de gestação no app — dois passos: (1) quem vai ser diagnosticado (origem → situação → animais) e
// (2) o que o toque encontrou (resultado, data, método). Mesmas regras do site (components/lancamentos/FormDiagnostico.tsx):
// só entra animal com diagnóstico a lançar, resultado por situação, AINDA NÃO só avisa e "Cio de repasse" só em fazenda
// com adesivo. A diferença é a fila offline: o lançamento sai por enviarOuEnfileirar (um POST por animal), e a lista de
// candidatos vem de fetchComCache, então o curral sem sinal continua funcionando com a última lista conhecida.
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Check } from "lucide-react";
import { MobAviso } from "@/components/mobile/ui";
import { fetchCandidatasDiagnostico, type CandidatasDiagnostico, type ItemCardAgendaReprodutiva } from "@/lib/api";
import { enviarOuEnfileirar, fetchComCache } from "@/lib/offline";
import { useCardsAgendaReprodutivaLeitura } from "@/components/CardsAgendaReprodutivaConfiguraveis";
import { CelulaExame, LegendaToque, SeloAindaNao } from "@/components/reproducao/FaseToque";
import { FASES, ROTULO_FASE_PLURAL, seloBreve, type FaseToque } from "@/lib/fasesToque";
import {
  NOTA_RESULTADO, NOTA_SITUACAO, RESULTADOS_POR_SITUACAO, agruparPorLote, alternarTodasNoPrazo, avisoAindaNao, buscarItens,
  filtrarPorOrigem, loteDe, metodosDisponiveis, pedeMetodo, resumoSelecao, selecaoPadrao, todasNoPrazoMarcadas,
  type OrigemSelecao, type ResultadoDiagnostico,
} from "@/lib/diagnosticoLancamento";
import { hoje, MobPill, LinhaPills } from "./comum";

const SEM_ANIMAIS: CandidatasDiagnostico["situacoes"] = { a_tocar: [], a_reconfirmar: [], reconfirmada: [] };
const CHAVE_CACHE = "reproducao_candidatas_diagnostico";
const ORIGENS: { id: OrigemSelecao; rotulo: string }[] = [
  { id: "animais", rotulo: "Animais" }, { id: "lotes", rotulo: "Lotes" }, { id: "agenda", rotulo: "Agenda do vet." },
];
const NOME_CURTO: Record<FaseToque, string> = { a_tocar: "A tocar", a_reconfirmar: "A reconfirmar", reconfirmada: "Reconfirm." };

const rotulo: React.CSSProperties = {
  fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--mob-muted)", margin: "0.9rem 0 0.4rem",
};
const caixa = (marcada: boolean): React.CSSProperties => ({
  flex: "none", width: 30, height: 30, border: `2px solid ${marcada ? "var(--mob-acao)" : "var(--mob-muted)"}`, display: "inline-flex",
  alignItems: "center", justifyContent: "center", background: marcada ? "var(--mob-acao)" : "var(--mob-surface)", color: "#fff",
});
// A barra de ação fica acima da barra de navegação do app (fixa, ~58px).
const barraFixa: React.CSSProperties = {
  position: "sticky", bottom: "calc(58px + env(safe-area-inset-bottom))", zIndex: 40, margin: "0.8rem -1rem 0", padding: "0.6rem 1rem 0.7rem",
  background: "var(--mob-surface)", borderTop: "1px solid var(--mob-border)", display: "flex", flexDirection: "column", gap: "0.45rem",
};

export function DiagnosticoGestacao({ animalFixado, onIrParaInseminacao }: {
  animalFixado: string | null;
  /** Depois de salvar Negativo: abre a Inseminação já com estes animais. */
  onIrParaInseminacao?: (numeros: string[]) => void;
}) {
  const [passo, setPasso] = useState<1 | 2>(1);
  const [cand, setCand] = useState<CandidatasDiagnostico | null>(null);
  const [doCache, setDoCache] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [origem, setOrigem] = useState<OrigemSelecao>("animais");
  const [situacao, setSituacao] = useState<FaseToque>("a_tocar");
  const [lotesSel, setLotesSel] = useState<Set<string>>(new Set());
  const [cardsSel, setCardsSel] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");
  const [resultadoEscolhido, setResultado] = useState<ResultadoDiagnostico | "">("");
  const [data, setData] = useState(hoje());
  const [metodoEscolhido, setMetodo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro" | "offline"; msg: string } | null>(null);
  // Animais já lançados que o servidor ainda não reflete (guardados na fila sem internet): somem da lista para ninguém
  // lançar duas vezes.
  const [ocultos, setOcultos] = useState<Set<string>>(new Set());
  const falhasParaMarcar = useRef<Set<string> | null>(null);
  const [rodadaFalhas, setRodadaFalhas] = useState(0);
  const preMarcar = useRef<string | null>(animalFixado);
  const primeiraCarga = useRef(true);

  async function carregar() {
    const { dados, doCache: velho } = await fetchComCache<CandidatasDiagnostico>(CHAVE_CACHE, () => fetchCandidatasDiagnostico());
    if (dados) { setCand(dados); setDoCache(velho); if (!velho) setOcultos(new Set()); }
    setCarregando(false);
    return dados;
  }
  useEffect(() => { carregar(); }, []);

  useEffect(() => {
    if (!cand || !primeiraCarga.current) return;
    primeiraCarga.current = false;
    const numero = preMarcar.current;
    const fase = numero ? FASES.find((f) => cand.situacoes[f].some((i) => i.numero_matriz === numero)) : undefined;
    if (fase) { setSituacao(fase); return; }
    preMarcar.current = null;
    const primeira = FASES.find((f) => cand.totais[f] > 0);
    if (primeira) setSituacao(primeira);
  }, [cand]);

  const cardsAgenda = useCardsAgendaReprodutivaLeitura(undefined, origem === "agenda");
  const todos = useMemo(() => {
    const o = {} as Record<FaseToque, ItemCardAgendaReprodutiva[]>;
    for (const f of FASES) o[f] = (cand?.situacoes ?? SEM_ANIMAIS)[f].filter((i) => !ocultos.has(i.numero_matriz));
    return o;
  }, [cand, ocultos]);
  const numerosDaAgenda = useMemo(() => {
    const s = new Set<string>();
    cardsSel.forEach((id) => (cardsAgenda.itensPorCard[id] || []).forEach((i) => s.add(i.numero_matriz)));
    return s;
  }, [cardsSel, cardsAgenda.itensPorCard]);
  const porSituacao = useMemo(() => {
    const o = {} as Record<FaseToque, ItemCardAgendaReprodutiva[]>;
    for (const f of FASES) o[f] = filtrarPorOrigem(todos[f], origem, lotesSel, numerosDaAgenda);
    return o;
  }, [todos, origem, lotesSel, numerosDaAgenda]);
  const daOrigem = porSituacao[situacao];
  const visiveis = useMemo(() => buscarItens(daOrigem, busca), [daOrigem, busca]);
  const grupos = useMemo(() => agruparPorLote(visiveis), [visiveis]);

  const opcoesLote = useMemo(() => {
    const m = new Map<string, number>();
    for (const i of todos[situacao]) m.set(loteDe(i), (m.get(loteDe(i)) ?? 0) + 1);
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b, "pt-BR", { numeric: true }));
  }, [todos, situacao]);
  const cardsComAnimais = useMemo(() => {
    const nesta = new Set(todos[situacao].map((i) => i.numero_matriz));
    return cardsAgenda.cards
      .map((c) => ({ id: c.id, nome: c.nome, n: (cardsAgenda.itensPorCard[c.id] || []).filter((i) => nesta.has(i.numero_matriz)).length }))
      .filter((c) => c.n > 0);
  }, [cardsAgenda.cards, cardsAgenda.itensPorCard, todos, situacao]);

  const chaveRecorte = `${origem}|${situacao}|${[...lotesSel].sort().join(",")}|${[...cardsSel].sort().join(",")}|${daOrigem.map((i) => i.numero_matriz).join(",")}`;
  useEffect(() => {
    const falhas = falhasParaMarcar.current;
    if (falhas) {
      falhasParaMarcar.current = null;
      setSel(new Set([...falhas].filter((n) => daOrigem.some((i) => i.numero_matriz === n))));
      return;
    }
    let inicial = selecaoPadrao(daOrigem, origem, situacao);
    const pre = preMarcar.current;
    if (pre && daOrigem.some((i) => i.numero_matriz === pre)) { inicial = new Set([pre]); preMarcar.current = null; }
    setSel(inicial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chaveRecorte, rodadaFalhas]);
  // Resultado e método derivados (sem efeito para "limpar"): o resultado precisa existir na situação aberta e o método,
  // na lista do resultado (Cio de repasse só com adesivo e só para Negativo).
  const resultado: ResultadoDiagnostico | "" =
    resultadoEscolhido && RESULTADOS_POR_SITUACAO[situacao].some((r) => r.valor === resultadoEscolhido) ? resultadoEscolhido : "";
  const metodos = metodosDisponiveis(!!cand?.usa_adesivo, resultado);
  const metodo = metodos.includes(metodoEscolhido) ? metodoEscolhido : "";

  const { marcados, ainda } = useMemo(() => resumoSelecao(daOrigem, sel), [daOrigem, sel]);
  const nSel = marcados.length;
  const opcaoEscolhida = resultado ? RESULTADOS_POR_SITUACAO[situacao].find((r) => r.valor === resultado) : undefined;
  const alternarSet = (set: ReadonlySet<string>, v: string) => {
    const s = new Set(set);
    if (s.has(v)) s.delete(v); else s.add(v);
    return s;
  };

  async function salvar(depoisInseminar: boolean) {
    if (!nSel || !resultado || !data) { setAviso({ tipo: "erro", msg: "Marque os animais, escolha o resultado e a data." }); return; }
    const numeros = marcados.map((i) => i.numero_matriz);
    const metodoEnviado = pedeMetodo(situacao, resultado) && metodo ? metodo : undefined;
    const nomeResultado = opcaoEscolhida?.nome ?? resultado;
    setSalvando(true);
    setAviso(null);
    const salvos: string[] = [];
    const guardados: string[] = [];
    const falhas: { numero: string; motivo: string }[] = [];
    for (const numero of numeros) {
      try {
        const { enviado } = await enviarOuEnfileirar(
          "/reproducao/diagnostico",
          { numero_matriz: numero, data_diagnostico: data, resultado, metodo: metodoEnviado },
          `Diagnóstico ${nomeResultado} — matriz ${numero}`,
        );
        (enviado ? salvos : guardados).push(numero);
      } catch (e) {
        falhas.push({ numero, motivo: e instanceof Error ? e.message : "erro ao salvar" });
      }
    }
    const feitos = [...salvos, ...guardados];
    setOcultos((o) => new Set([...o, ...feitos]));
    setSalvando(false);
    if (falhas.length) {
      falhasParaMarcar.current = new Set(falhas.map((f) => f.numero));
      setRodadaFalhas((r) => r + 1);
      setPasso(1);
      const lista = falhas.map((f) => `${f.numero} (${f.motivo})`).join("; ");
      setAviso({ tipo: "erro", msg: `${feitos.length ? `Salvos: ${feitos.length}. ` : ""}Não salvou: ${lista}. Eles continuam marcados.` });
      return;
    }
    setResultado(""); setMetodo(""); setPasso(1);
    setAviso(guardados.length
      ? { tipo: "offline", msg: `${guardados.length} sem internet — guardado${guardados.length > 1 ? "s" : ""}, será enviado ao conectar.${salvos.length ? ` Salvos agora: ${salvos.length}.` : ""}` }
      : { tipo: "ok", msg: `Diagnóstico salvo para ${salvos.length} ${salvos.length === 1 ? "animal" : "animais"}.` });
    carregar();
    if (depoisInseminar && resultado === "negativo") onIrParaInseminacao?.(feitos);
  }

  const lista = (
    <>
      {grupos.map((g) => (
        <Fragment key={g.lote}>
          <div style={{ ...rotulo, margin: "0.7rem 0 0.3rem" }}>{g.lote} · {g.itens.length}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {g.itens.map((it) => {
              const marcado = sel.has(it.numero_matriz);
              const esperando = !!it.ainda_nao;
              const reconf = !!it.data_reconfirmacao || !!it.diagnostico_reconfirmacao;
              return (
                <button key={it.numero_matriz} type="button" aria-pressed={marcado}
                  onClick={() => setSel((p) => alternarSet(p, it.numero_matriz))}
                  className={esperando ? `ft-cartao-ainda${seloBreve(it.dias_para_prazo) ? " ft-cartao-breve" : ""}` : undefined}
                  style={{
                    display: "flex", alignItems: "center", gap: "0.85rem", minHeight: 68, padding: "0.5rem 0.75rem", textAlign: "left", width: "100%", cursor: "pointer",
                    background: "var(--mob-surface)", color: "var(--mob-text)",
                    border: `1px solid ${marcado ? "var(--mob-acao)" : "var(--mob-border)"}`, boxShadow: marcado ? "inset 0 0 0 1px var(--mob-acao)" : "none",
                  }}>
                  <span style={caixa(marcado)} aria-hidden="true">{marcado && <Check size={18} strokeWidth={3.2} />}</span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: "block", fontSize: "1.35rem", fontWeight: 800, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{it.numero_matriz}</span>
                    <span style={{ display: "flex", flexWrap: "wrap", gap: "0.15rem 0.7rem", fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: 4 }}>
                      <span>{it.categoria ?? "—"} · IA {it.dias_desde_servico ?? "—"} d</span>
                      <span>Toque <CelulaExame data={it.data_diagnostico} diagnostico={it.diagnostico} /></span>
                      <span>Retoque {reconf ? <CelulaExame data={it.data_reconfirmacao} diagnostico={it.diagnostico_reconfirmacao} /> : <CelulaExame data={null} diagnostico={null} />}</span>
                    </span>
                    {esperando && <span style={{ display: "block", marginTop: 4 }}><SeloAindaNao dias={it.dias_para_prazo} prazoTipo={it.prazo_tipo} /></span>}
                  </span>
                </button>
              );
            })}
          </div>
        </Fragment>
      ))}
    </>
  );

  if (passo === 1) {
    return (
      <>
        <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", margin: "0 0 0.2rem" }}>Passo 1 de 2 · quem vai ser diagnosticado</p>
        {doCache && <MobAviso tipo="offline">Sem internet: mostrando a lista do último acesso.</MobAviso>}
        {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}

        <div style={rotulo}>Origem</div>
        <div role="group" aria-label="Origem" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
          {ORIGENS.map((o) => (
            <button key={o.id} type="button" className="ft-botao-mob" aria-pressed={origem === o.id} onClick={() => setOrigem(o.id)} style={{ minHeight: 52 }}>{o.rotulo}</button>
          ))}
        </div>
        {origem === "lotes" && (
          <div style={{ marginTop: "0.6rem" }}>
            <LinhaPills>
              {opcoesLote.map(([l, n]) => <MobPill key={l} ativa={lotesSel.has(l)} onClick={() => setLotesSel((p) => alternarSet(p, l))}>{l} ({n})</MobPill>)}
              {!opcoesLote.length && <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum lote com animais nesta situação.</p>}
            </LinhaPills>
          </div>
        )}
        {origem === "agenda" && (
          <div style={{ marginTop: "0.6rem" }}>
            {cardsAgenda.carregando && <p style={{ fontSize: "0.85rem", color: "var(--mob-muted)" }}>Carregando a agenda…</p>}
            <LinhaPills>
              {cardsComAnimais.map((c) => <MobPill key={c.id} ativa={cardsSel.has(c.id)} onClick={() => setCardsSel((p) => alternarSet(p, c.id))}>{c.nome} ({c.n})</MobPill>)}
            </LinhaPills>
            {!cardsAgenda.carregando && !cardsComAnimais.length && <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>Nenhum card da agenda tem animais nesta situação.</p>}
          </div>
        )}

        <div style={rotulo}>Situação</div>
        <div role="group" aria-label="Situação" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
          {FASES.map((f) => (
            <button key={f} type="button" className="ft-botao-mob" aria-pressed={situacao === f} onClick={() => setSituacao(f)}><b>{porSituacao[f].length}</b>{NOME_CURTO[f]}</button>
          ))}
        </div>
        <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", margin: "0.5rem 0 0" }}>{NOTA_SITUACAO[situacao](cand?.parametros ?? null)}</p>

        <input type="search" className="mob-input" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar matriz ou lote" aria-label="Buscar matriz ou lote" style={{ marginTop: "0.8rem" }} />

        {situacao !== "reconfirmada" && visiveis.some((i) => !i.ainda_nao) && (
          <button type="button" aria-pressed={todasNoPrazoMarcadas(visiveis, sel)} onClick={() => setSel(alternarTodasNoPrazo(visiveis, sel))}
            style={{ marginTop: "0.7rem", minHeight: 56, width: "100%", display: "flex", alignItems: "center", gap: "0.85rem", padding: "0 0.9rem", textAlign: "left", fontSize: "0.95rem", fontWeight: 700, cursor: "pointer", background: "var(--mob-surface)", color: "var(--mob-text)", border: "1.5px solid var(--mob-border)" }}>
            <span style={caixa(todasNoPrazoMarcadas(visiveis, sel))} aria-hidden="true">{todasNoPrazoMarcadas(visiveis, sel) && <Check size={18} strokeWidth={3.2} />}</span>
            Selecionar todas no prazo
          </button>
        )}

        {carregando && <p style={{ fontSize: "0.85rem", color: "var(--mob-muted)", marginTop: "0.8rem" }}>Carregando os animais…</p>}
        {!carregando && !visiveis.length && (
          <p style={{ fontSize: "0.85rem", color: "var(--mob-muted)", marginTop: "0.8rem" }}>
            {origem === "lotes" && !lotesSel.size ? "Toque em um ou mais lotes."
              : origem === "agenda" && !cardsSel.size ? "Toque em um ou mais cards da agenda."
              : busca ? "Nenhum animal bate com a busca."
              : `Nenhum animal em “${ROTULO_FASE_PLURAL[situacao]}”.`}
          </p>
        )}
        <div aria-live="polite">{lista}</div>
        {visiveis.length > 0 && <LegendaToque parametros={cand?.parametros} />}

        <div style={barraFixa}>
          <span aria-live="polite" style={{ fontSize: "0.8rem", color: "var(--mob-muted)", textAlign: "center", fontVariantNumeric: "tabular-nums" }}>
            {nSel} de {daOrigem.length} marcados · os AINDA NÃO só entram marcando um a um
          </span>
          <button type="button" className="mob-btn" disabled={nSel === 0} onClick={() => { setAviso(null); setPasso(2); }}>Continuar{nSel ? ` (${nSel})` : ""}</button>
        </div>
      </>
    );
  }

  return (
    <>
      <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", margin: "0 0 0.4rem" }}>Passo 2 de 2 · o que o toque encontrou</p>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "0.7rem 0.85rem", background: "var(--mob-surface)", border: "1px solid var(--mob-border)" }}>
        <div>
          <div style={{ fontSize: "1.2rem", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{nSel} {nSel === 1 ? "animal" : "animais"}</div>
          <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>{ROTULO_FASE_PLURAL[situacao]} · {ORIGENS.find((o) => o.id === origem)?.rotulo}</div>
        </div>
        <button type="button" onClick={() => setPasso(1)} style={{ minHeight: 48, padding: "0 0.9rem", background: "transparent", border: "1.5px solid var(--mob-border)", color: "var(--mob-text)", fontWeight: 700, fontSize: "0.85rem", cursor: "pointer" }}>Alterar</button>
      </div>

      <div style={rotulo}>Resultado</div>
      <div role="group" aria-label="Resultado do diagnóstico" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {RESULTADOS_POR_SITUACAO[situacao].map((r) => {
          const ativo = resultado === r.valor;
          return (
            <button key={r.valor} type="button" aria-pressed={ativo} onClick={() => setResultado(r.valor)}
              style={{
                minHeight: 64, display: "flex", flexDirection: "column", alignItems: "flex-start", justifyContent: "center", gap: 2, padding: "0.5rem 0.9rem", textAlign: "left", cursor: "pointer",
                background: ativo ? "var(--ft-ouro-tint)" : "var(--mob-surface)", color: "var(--mob-text)",
                border: `1.5px solid ${ativo ? "var(--ft-ouro)" : "var(--mob-border)"}`, boxShadow: ativo ? "inset 0 0 0 1.5px var(--ft-ouro)" : "none",
              }}>
              <b style={{ fontSize: "1rem" }}>{r.nome}</b>
              <span style={{ fontSize: "0.8rem", color: "var(--mob-muted)", fontWeight: 500 }}>{r.dica}</span>
            </button>
          );
        })}
      </div>

      <div style={rotulo}>Data{pedeMetodo(situacao, resultado) ? " e método" : ""}</div>
      <label htmlFor="dg-data" style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--mob-muted)" }}>Data do diagnóstico</label>
      <input id="dg-data" type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      {pedeMetodo(situacao, resultado) && (
        <>
          <label htmlFor="dg-metodo" style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "var(--mob-muted)", marginTop: "0.6rem" }}>Método</label>
          <select id="dg-metodo" className="mob-input" value={metodo} onChange={(e) => setMetodo(e.target.value)}>
            <option value="">Não informar</option>
            {metodos.map((m) => <option key={m} value={m}>{m === "Cio de repasse" ? "Cio de repasse (adesivo pintado)" : m}</option>)}
          </select>
        </>
      )}
      <p style={{ fontSize: "0.8rem", lineHeight: 1.5, color: "var(--mob-muted)", margin: "0.6rem 0 0" }}>{resultado ? NOTA_RESULTADO[resultado] : "Escolha o resultado para ver o que acontece com os animais."}</p>
      {ainda > 0 && <MobAviso tipo="offline">{avisoAindaNao(ainda)}</MobAviso>}
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}

      <div style={barraFixa}>
        <button type="button" className="mob-btn" disabled={salvando || !resultado || !nSel} onClick={() => salvar(false)}>
          {salvando ? "Salvando…" : `Salvar (${nSel})`}
        </button>
        {resultado === "negativo" && onIrParaInseminacao && (
          <button type="button" className="mob-btn mob-btn-sec" disabled={salvando} onClick={() => salvar(true)}>Salvar e lançar inseminação ({nSel})</button>
        )}
      </div>
    </>
  );
}
