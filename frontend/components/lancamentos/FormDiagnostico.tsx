"use client";
// Lançamento do diagnóstico de gestação — origem → situação → animais → resultado. Só entra aqui quem tem diagnóstico a
// lançar (a tocar, a reconfirmar, reconfirmadas); vazia, PEV, apta e "a descartar" nunca aparecem. A classificação e o
// prazo AINDA NÃO vêm do backend (rules/fase_toque.py, GET /reproducao/diagnostico/candidatas): a mesma conta da Agenda
// Reprodutiva, então as duas telas não discordam. O AINDA NÃO só informa; nunca impede o lançamento.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { fetchCandidatasDiagnostico, salvarDiagnostico, type CandidatasDiagnostico, type ItemCardAgendaReprodutiva } from "@/lib/api";
import { useCardsAgendaReprodutivaLeitura } from "@/components/CardsAgendaReprodutivaConfiguraveis";
import { CelulaExame, LegendaToque, SeloAindaNao } from "@/components/reproducao/FaseToque";
import { useToast } from "@/components/Toast";
import { Campo, inputStyle } from "@/components/lancamentos/comumForms";
import { PopupVinculoFinanceiro, type OrigemPopupVinculo } from "@/components/lancamentos/PopupVinculoFinanceiro";
import { invalidarEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { FASES, ROTULO_FASE_PLURAL, seloBreve, type FaseToque } from "@/lib/fasesToque";
import {
  NOTA_RESULTADO, NOTA_SITUACAO, RESULTADOS_POR_SITUACAO, agruparPorLote, alternarTodasNoPrazo, avisoAindaNao, buscarItens,
  filtrarPorOrigem, loteDe, mensagemResultado, metodosDisponiveis, pedeMetodo, resumoSelecao, selecaoPadrao, todasNoPrazoMarcadas,
  type FalhaDeSalvamento, type OrigemSelecao, type ResultadoDiagnostico,
} from "@/lib/diagnosticoLancamento";

const SEM_ANIMAIS: CandidatasDiagnostico["situacoes"] = { a_tocar: [], a_reconfirmar: [], reconfirmada: [] };

const hojeIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const ORIGENS: { id: OrigemSelecao; rotulo: string; titulo: string }[] = [
  { id: "animais", rotulo: "Animais", titulo: "Escolher animal por animal" },
  { id: "lotes", rotulo: "Lotes", titulo: "Escolher um ou mais lotes — já vêm marcados os que estão no prazo" },
  { id: "agenda", rotulo: "Agenda do veterinário", titulo: "Escolher a partir dos cards da Agenda do veterinário — mesma lista do roteiro" },
];

const rotuloSecao: React.CSSProperties = {
  fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--text-muted)",
  display: "flex", alignItems: "center", gap: "0.55rem",
};
const numeroPasso: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center", width: "1.35rem", height: "1.35rem", borderRadius: "50%",
  border: "1.5px solid var(--ft-ouro)", color: "var(--ft-ouro-txt)", fontSize: "0.72rem", fontWeight: 800,
};
const passo: React.CSSProperties = { display: "flex", flexDirection: "column", gap: "0.6rem", padding: "0.95rem 0", borderTop: "1px solid var(--border)" };
const notaTxt: React.CSSProperties = { fontSize: "0.76rem", lineHeight: 1.5, color: "var(--text-muted)", margin: 0 };

function Passo({ n, id, titulo, direita, children }: { n: number; id: string; titulo: string; direita?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section style={n === 1 ? { ...passo, borderTop: 0, paddingTop: 0 } : passo} aria-labelledby={id}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
        <div id={id} style={rotuloSecao}><span style={numeroPasso} aria-hidden="true">{n}</span>{titulo}</div>
        {direita}
      </div>
      {children}
    </section>
  );
}

export function FormDiagnostico({ onSalvo, onIrParaInseminacao }: {
  onSalvo?: () => void;
  /** Depois de salvar Negativo: abre o lançamento de inseminação já com estes animais marcados. */
  onIrParaInseminacao?: (numeros: string[]) => void;
}) {
  const toast = useToast();
  const [cand, setCand] = useState<CandidatasDiagnostico | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erroCarga, setErroCarga] = useState<string | null>(null);

  const [origem, setOrigem] = useState<OrigemSelecao>("animais");
  const [situacao, setSituacao] = useState<FaseToque>("a_tocar");
  const [lotesSel, setLotesSel] = useState<Set<string>>(new Set());
  const [cardsSel, setCardsSel] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");

  const [resultadoEscolhido, setResultado] = useState<ResultadoDiagnostico | "">("");
  const [data, setData] = useState(hojeIso);
  const [metodoEscolhido, setMetodo] = useState("");

  const [salvando, setSalvando] = useState(false);
  const [progresso, setProgresso] = useState<{ feitos: number; total: number } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [negativosSalvos, setNegativosSalvos] = useState<string[]>([]);
  const [popupOrigem, setPopupOrigem] = useState<OrigemPopupVinculo | null>(null);
  // Quem falhou ao salvar: volta marcado depois da recarga (o recorte recalculado não pode desfazer isso). Fica numa
  // referência + um contador que dispara o efeito uma única vez — zerar um estado reexecutaria o efeito e refaria a
  // marcação padrão por cima.
  const falhasParaMarcar = useRef<Set<string> | null>(null);
  const [rodadaFalhas, setRodadaFalhas] = useState(0);

  // Vindo da Agenda ("Registrar toque", "Lançar toque/retoque"): abre já na situação do animal, com ele marcado.
  const preMarcar = useRef<string | null>(null);
  const prefillAplicado = useRef(false);
  useEffect(() => { preMarcar.current = new URLSearchParams(window.location.search).get("numero_matriz"); }, []);

  const carregar = useCallback(async () => {
    setErroCarga(null);
    try {
      const r = await fetchCandidatasDiagnostico();
      setCand(r);
      return r;
    } catch (e) {
      setErroCarga(e instanceof Error && e.message ? e.message : "Erro ao carregar os animais do diagnóstico");
      return null;
    } finally {
      setCarregando(false);
    }
  }, []);
  useEffect(() => { carregar(); }, [carregar]);

  // Primeira carga: se veio um animal da Agenda, vai para a situação dele; senão, para a primeira situação com animais.
  useEffect(() => {
    if (!cand || prefillAplicado.current) return;
    prefillAplicado.current = true;
    const numero = preMarcar.current;
    const fase = numero ? FASES.find((f) => cand.situacoes[f].some((i) => i.numero_matriz === numero)) : undefined;
    if (fase) { setSituacao(fase); return; }
    preMarcar.current = null;
    const primeira = FASES.find((f) => cand.totais[f] > 0);
    if (primeira) setSituacao(primeira);
  }, [cand]);

  const cardsAgenda = useCardsAgendaReprodutivaLeitura(undefined, origem === "agenda");

  const todos = useMemo(() => cand?.situacoes ?? SEM_ANIMAIS, [cand]);
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

  // Lotes disponíveis na situação aberta (com a contagem de quem está nela).
  const opcoesLote = useMemo(() => {
    const m = new Map<string, number>();
    for (const i of todos[situacao]) m.set(loteDe(i), (m.get(loteDe(i)) ?? 0) + 1);
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b, "pt-BR", { numeric: true }));
  }, [todos, situacao]);

  // Cards da Agenda que têm animais nesta situação (PEV, vazias e a descartar nunca entram: não estão aqui).
  const cardsComAnimais = useMemo(() => {
    const nesta = new Set(todos[situacao].map((i) => i.numero_matriz));
    return cardsAgenda.cards
      .map((c) => ({ id: c.id, nome: c.nome, n: (cardsAgenda.itensPorCard[c.id] || []).filter((i) => nesta.has(i.numero_matriz)).length }))
      .filter((c) => c.n > 0);
  }, [cardsAgenda.cards, cardsAgenda.itensPorCard, todos, situacao]);

  // Marcação inicial sempre que muda o recorte (origem, situação, lotes, cards ou os próprios animais).
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

  // O resultado escolhido tem de existir na situação aberta (trocou de situação, escolhe de novo) e o método, na lista
  // do resultado (Cio de repasse só com adesivo e só para Negativo): valores derivados, sem efeito para "limpar".
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
  const alternar = (n: string) => setSel((p) => alternarSet(p, n));

  async function salvar() {
    setErro(null); setSucesso(null); setNegativosSalvos([]);
    if (!nSel || !resultado || !data) { setErro("Marque ao menos um animal e escolha o resultado e a data do diagnóstico."); return; }
    const numeros = marcados.map((i) => i.numero_matriz);
    const metodoEnviado = pedeMetodo(situacao, resultado) && metodo ? metodo : undefined;
    const dataSalva = data;
    const resultadoSalvo = resultado;
    setSalvando(true);
    setProgresso({ feitos: 0, total: numeros.length });
    const salvos: string[] = [];
    const falhas: FalhaDeSalvamento[] = [];
    const servicoIds: number[] = [];
    // Um animal por chamada: quem falhou fica marcado para tentar de novo, e o que já salvou não se perde.
    for (const numero of numeros) {
      try {
        const r = await salvarDiagnostico({ numero_matriz: numero, data_diagnostico: dataSalva, resultado: resultadoSalvo, metodo: metodoEnviado });
        salvos.push(numero);
        if (r?.id && resultadoSalvo !== "aborto") servicoIds.push(r.id);
      } catch (e) {
        falhas.push({ numero, motivo: e instanceof Error && e.message ? e.message : "erro ao salvar" });
      }
      setProgresso({ feitos: salvos.length + falhas.length, total: numeros.length });
    }
    invalidarEstadosReprodutivos();
    await carregar();
    setSalvando(false);
    setProgresso(null);
    const msg = mensagemResultado(salvos.length, falhas, resultadoSalvo === "aborto" ? "Aborto" : "Diagnóstico");
    setSucesso(msg.ok);
    setErro(msg.erro);
    if (salvos.length) toast(salvos.length > 1 ? `Diagnóstico salvo para ${salvos.length} animais.` : "Diagnóstico salvo.");
    if (falhas.length) {
      // Fica só quem falhou, marcado, para tentar de novo.
      preMarcar.current = null;
      falhasParaMarcar.current = new Set(falhas.map((f) => f.numero));
      setRodadaFalhas((r) => r + 1);
      return;
    }
    setResultado(""); setMetodo("");
    if (resultadoSalvo === "negativo") setNegativosSalvos(salvos);
    if (servicoIds.length) setPopupOrigem({ tipo: "servico", ids: servicoIds, produto: "Diagnóstico de gestação — visita reprodutiva", data: dataSalva, responsavel: null });
    onSalvo?.();
  }

  const textoSalvar = salvando && progresso ? `Salvando ${progresso.feitos} de ${progresso.total}…` : `Salvar${nSel ? ` (${nSel})` : ""}`;
  const semSalvar = salvando || nSel === 0 || !resultado || !data;
  const nomeSituacao = ROTULO_FASE_PLURAL[situacao];

  return (
    <>
      <div style={{ display: "flex", flexDirection: "column" }}>
        <Passo n={1} id="dg-p1" titulo="De onde vêm os animais">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Origem da seleção">
            {ORIGENS.map((o) => (
              <button key={o.id} type="button" className="ft-pilula" aria-pressed={origem === o.id} title={o.titulo} onClick={() => setOrigem(o.id)}>
                {o.rotulo}
              </button>
            ))}
          </div>
          {origem === "lotes" && (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Lotes">
              {opcoesLote.length === 0 && <p style={notaTxt}>Nenhum lote com animais nesta situação.</p>}
              {opcoesLote.map(([lote, n]) => (
                <button key={lote} type="button" className="ft-pilula" aria-pressed={lotesSel.has(lote)} onClick={() => setLotesSel((p) => alternarSet(p, lote))}>
                  {lote}<b>{n}</b>
                </button>
              ))}
            </div>
          )}
          {origem === "agenda" && (
            <>
              {cardsAgenda.carregando && <p style={notaTxt}>Carregando os cards da Agenda do veterinário…</p>}
              {cardsAgenda.erro && <p role="alert" style={{ ...notaTxt, color: "var(--red)" }}>{cardsAgenda.erro}</p>}
              <div className="flex flex-wrap gap-2" role="group" aria-label="Cards da Agenda do veterinário">
                {cardsComAnimais.map((c) => (
                  <button key={c.id} type="button" className="ft-pilula" aria-pressed={cardsSel.has(c.id)} onClick={() => setCardsSel((p) => alternarSet(p, c.id))}>
                    {c.nome}<b>{c.n}</b>
                  </button>
                ))}
              </div>
              {!cardsAgenda.carregando && cardsComAnimais.length === 0 && (
                <p style={notaTxt}>Nenhum card configurado tem animais nesta situação. Veja Insights › Agenda reprodutiva.</p>
              )}
              <p style={notaTxt}>Só aparecem os cards com animais servidos. PEV, Vazias, Vazias atrasadas e A descartar não entram no diagnóstico.</p>
            </>
          )}
        </Passo>

        <Passo n={2} id="dg-p2" titulo="Situação do animal">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Situação">
            {FASES.map((f) => (
              <button key={f} type="button" className="ft-pilula" aria-pressed={situacao === f} onClick={() => setSituacao(f)}>
                {ROTULO_FASE_PLURAL[f]}<b>{porSituacao[f].length}</b>
              </button>
            ))}
          </div>
          <p style={notaTxt}>{NOTA_SITUACAO[situacao](cand?.parametros ?? null)}</p>
        </Passo>

        <Passo n={3} id="dg-p3" titulo="Animais" direita={
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">
            {nSel} de {daOrigem.length} {nSel === 1 ? "marcado" : "marcados"}
          </span>
        }>
          <input type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar matriz ou lote" aria-label="Buscar matriz ou lote" style={inputStyle} />
          {carregando && <p style={notaTxt}>Carregando os animais…</p>}
          {erroCarga && <p role="alert" style={{ ...notaTxt, color: "var(--red)" }}>{erroCarga}</p>}
          {!carregando && !erroCarga && visiveis.length === 0 && (
            <p style={notaTxt}>
              {origem === "lotes" && lotesSel.size === 0 ? "Marque um ou mais lotes acima."
                : origem === "agenda" && cardsSel.size === 0 ? "Marque um ou mais cards da Agenda acima."
                : busca ? "Nenhum animal bate com a busca."
                : `Nenhum animal em “${nomeSituacao}”.`}
            </p>
          )}
          {visiveis.length > 0 && (
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", maxHeight: "21rem", overflow: "auto" }}>
              <table className="tabela-compacta" style={{ width: "100%" }}>
                <thead style={{ position: "sticky", top: 0, zIndex: 1 }}>
                  <tr>
                    <th scope="col" style={{ width: "2.4rem" }}>
                      <input type="checkbox" checked={todasNoPrazoMarcadas(visiveis, sel)} onChange={() => setSel(alternarTodasNoPrazo(visiveis, sel))}
                        aria-label="Selecionar todas as que estão no prazo" disabled={situacao === "reconfirmada" || !visiveis.some((i) => !i.ainda_nao)} style={{ width: "1.05rem", height: "1.05rem" }} />
                    </th>
                    <th scope="col">Matriz</th><th scope="col">Categoria</th><th scope="col" title="Dias desde a inseminação">Dias da IA</th>
                    <th scope="col" title="Data e resultado do toque">Toque</th><th scope="col" title="Data e resultado do retoque">Retoque</th><th scope="col">Prazo</th>
                  </tr>
                </thead>
                <tbody>
                  {grupos.map((g) => (
                    <React.Fragment key={g.lote}>
                      <tr><th scope="rowgroup" colSpan={7} style={{ textAlign: "left", background: "var(--surface-2)", color: "var(--text-muted)", fontSize: "0.66rem", letterSpacing: "0.1em", textTransform: "uppercase", padding: "0.3rem 0.5rem" }}>{g.lote} · {g.itens.length}</th></tr>
                      {g.itens.map((it) => {
                        const esperando = !!it.ainda_nao;
                        const reconf = !!it.data_reconfirmacao || !!it.diagnostico_reconfirmacao;
                        const classe = esperando ? `ft-linha-ainda${seloBreve(it.dias_para_prazo) ? " ft-linha-breve" : ""}` : undefined;
                        return (
                          <tr key={it.numero_matriz} className={classe}>
                            <td><input type="checkbox" checked={sel.has(it.numero_matriz)} onChange={() => alternar(it.numero_matriz)} aria-label={`Selecionar ${it.numero_matriz}`} style={{ width: "1.05rem", height: "1.05rem" }} /></td>
                            <td style={{ fontWeight: 800 }}>{it.numero_matriz}</td>
                            <td>{it.categoria ?? "—"}</td>
                            <td style={{ fontVariantNumeric: "tabular-nums" }}>{it.dias_desde_servico ?? "—"}</td>
                            <td><CelulaExame data={it.data_diagnostico} diagnostico={it.diagnostico} /></td>
                            <td>{reconf ? <CelulaExame data={it.data_reconfirmacao} diagnostico={it.diagnostico_reconfirmacao} /> : <CelulaExame data={null} diagnostico={null} />}</td>
                            <td style={{ whiteSpace: "nowrap" }}>
                              {esperando ? <SeloAindaNao dias={it.dias_para_prazo} prazoTipo={it.prazo_tipo} /> : <span style={{ fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ft-verde)" }}>No prazo</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <LegendaToque parametros={cand?.parametros} />
          <p style={notaTxt}>“Selecionar todas” marca só as que estão no prazo. As marcadas com AINDA NÃO podem ser lançadas mesmo assim, uma a uma.</p>
        </Passo>

        <Passo n={4} id="dg-p4" titulo="Resultado">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.5rem" }} role="group" aria-label="Resultado do diagnóstico">
            {RESULTADOS_POR_SITUACAO[situacao].map((r) => {
              const ativo = resultado === r.valor;
              return (
                <button key={r.valor} type="button" aria-pressed={ativo} onClick={() => setResultado(r.valor)}
                  style={{
                    display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "0.15rem", textAlign: "left", minHeight: "3.6rem", padding: "0.65rem 0.8rem",
                    borderRadius: "var(--r-sm)", cursor: "pointer", color: "var(--text)",
                    border: `1px solid ${ativo ? "var(--ft-ouro)" : "var(--border)"}`, background: ativo ? "var(--ft-ouro-tint)" : "var(--surface)",
                    boxShadow: ativo ? "inset 0 0 0 1px var(--ft-ouro)" : "none",
                  }}>
                  <b style={{ fontSize: "0.85rem" }}>{r.nome}</b>
                  <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.dica}</span>
                </button>
              );
            })}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3" style={{ maxWidth: "36rem" }}>
            <Campo label="Data do diagnóstico"><input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} /></Campo>
            {pedeMetodo(situacao, resultado) && (
              <Campo label="Método">
                <select style={inputStyle} value={metodo} onChange={(e) => setMetodo(e.target.value)}>
                  <option value="">Não informar</option>
                  {metodos.map((m) => <option key={m} value={m}>{m === "Cio de repasse" ? "Cio de repasse (adesivo pintado)" : m}</option>)}
                </select>
              </Campo>
            )}
          </div>
          <p style={notaTxt}>{resultado ? NOTA_RESULTADO[resultado] : "Escolha o resultado para ver o que acontece com os animais."}</p>
          {metodo === "Cio de repasse" && (
            <p style={notaTxt}><strong>Cio de repasse:</strong> a vaca voltou ao cio com o adesivo pintado; ninguém a examinou, por isso só vale para Negativo.</p>
          )}
          {ainda > 0 && (
            <div role="status" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", padding: "0.6rem 0.8rem", border: "1px solid var(--ft-ouro)", background: "var(--ft-ouro-tint)", borderRadius: "var(--r-sm)", fontSize: "0.78rem", color: "var(--ft-ouro-txt)" }}>
              <AlertTriangle size={15} style={{ marginTop: "0.1rem", flexShrink: 0 }} aria-hidden="true" />
              <span>{avisoAindaNao(ainda)}</span>
            </div>
          )}
        </Passo>

        {/* Barra fixa no fim da gaveta: o que vai ser salvo, o botão e o retorno do último salvamento (inclusive o atalho
            "Lançar inseminação"), sempre à vista, mesmo com a lista longa. */}
        <div style={{
          position: "sticky", bottom: "-0.9rem", margin: "0 -0.9rem -0.9rem", zIndex: 2,
          borderTop: "1px solid var(--border)", background: "var(--surface-2)",
        }}>
          {(erro || sucesso || (negativosSalvos.length > 0 && onIrParaInseminacao)) && (
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", padding: "0.55rem 0.9rem", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem", flex: 1, minWidth: "14rem" }}>
                {sucesso && <span role="status" style={{ color: "var(--green-light)", fontSize: "0.8rem" }}>✓ {sucesso}</span>}
                {erro && <span role="alert" style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</span>}
              </div>
              {negativosSalvos.length > 0 && onIrParaInseminacao && (
                <button type="button" className="btn-primary-gold" onClick={() => onIrParaInseminacao(negativosSalvos)}>
                  Lançar inseminação para {negativosSalvos.length === 1 ? "este animal" : `estas ${negativosSalvos.length} vacas`}
                </button>
              )}
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: "0.9rem", flexWrap: "wrap", padding: "0.75rem 0.9rem" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.1rem" }} aria-live="polite">
              <span style={{ fontSize: "0.85rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{nSel} {nSel === 1 ? "animal" : "animais"} · {nomeSituacao}</span>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                {opcaoEscolhida ? `Resultado: ${opcaoEscolhida.nome}${resultado === "negativo" ? " · depois de salvar você poderá lançar a inseminação" : ""}` : "Falta escolher o resultado"}
              </span>
            </div>
            <span style={{ flex: 1 }} />
            <button type="button" className="btn-primary-gold" onClick={salvar} disabled={semSalvar}>{textoSalvar}</button>
          </div>
        </div>
      </div>

      {popupOrigem && <PopupVinculoFinanceiro origem={popupOrigem} onFechar={() => setPopupOrigem(null)} />}
    </>
  );
}
