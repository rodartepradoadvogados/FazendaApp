"use client";
// Passo 1 ("quem") de Inseminação e Protocolo IATF — a mesma tela para as duas, só muda o modo: origem (Animais / Lotes /
// Agenda do vet.), situação (Aptas / Atrasadas / IATF D11 ou PEV / Todas, com a contagem escopada pela origem), busca e
// cartão-checkbox por lote. A situação de cada vaca vem do estado reprodutivo ao vivo (GET /indicadores/estados-
// reprodutivos), a mesma fonte das listas do Rebanho. Gestante e inseminada recente só entram por confirmação
// individual num sheet; vaca em protocolo aparece travada. Nada vem marcado sozinho e a seleção persiste ao trocar de
// origem/filtro (exceção: o animal que a pessoa acabou de escolher na ficha ou vindo do diagnóstico negativo).
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Lock } from "lucide-react";
import { fetchEstadosReprodutivos, type EstadosReprodutivos } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { useCardsAgendaReprodutivaLeitura } from "@/components/CardsAgendaReprodutivaConfiguraveis";
import {
  FILTROS_SITUACAO, NOTA_SITUACAO_SERVICO, agruparCandidatasPorLote, alternarItem, buscarCandidatas, contagensPorSituacao, contarForaDoFiltro,
  definirVarios, existeEmOutraSituacao, frasePertenceOutraSituacao, lotesComCandidatas, marcaveisEmBloco, montarCandidatas, passaFiltro,
  plural, podarSelecao, recortarPorOrigem, rotuloMarcarTodas, todosMarcados,
  type AnimalDaLista, type CandidataServico, type FiltroSituacao, type ModoServico, type OrigemLote,
} from "@/lib/lancamentoLote";
import { RascunhoAviso } from "../comum";
import {
  AvisoLote, BotaoMarcarTodas, CabecalhoGrupo, CampoBusca, CartaoAnimal, ChipSituacao, NotaLote, PassoIndicador, PilulaLote, PilulasLote, RotuloLote,
  SeletorOrigem, VazioLote,
} from "./SelecaoLote";
import { BarraContinuar } from "./BarraLote";
import { SheetLote, useToastLote } from "./SheetLote";
import { useSelecaoPersistida } from "./hooks";

const CHAVE_CACHE_ESTADOS = "estados_reprodutivos";

function vibrar(padrao: number | number[]) {
  try { navigator.vibrate?.(padrao); } catch { /* sem suporte — segue sem vibrar */ }
}

/** Todo o estado do Passo 1; o Passo 2 de cada tela lê daqui `marcadas`, `confirmadas` e o resumo da origem. */
export function useQuemServico(opts: { modo: ModoServico; animais: readonly AnimalDaLista[]; chave: string; obrigatorios?: readonly string[] }) {
  const { modo, animais } = opts;
  const [estados, setEstados] = useState<EstadosReprodutivos | null>(null);
  const [doCache, setDoCache] = useState(false);
  const [carregando, setCarregando] = useState(true);
  // Já lançados que o servidor ainda não reflete (guardados na fila sem internet): somem da lista para ninguém
  // lançar duas vezes — mesmo cuidado do Diagnóstico.
  const [ocultos, setOcultos] = useState<Set<string>>(new Set());

  const [origem, setOrigem] = useState<OrigemLote>("animais");
  const [situacao, setSituacao] = useState<FiltroSituacao>(opts.obrigatorios?.length ? "todas" : "aptas");
  const [lotesSel, setLotesSel] = useState<Set<string>>(new Set());
  const [cardsSel, setCardsSel] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");
  const selecao = useSelecaoPersistida(opts.chave, opts.obrigatorios);
  const confirmacoes = useSelecaoPersistida(`${opts.chave}_confirmadas`);
  const [confirmando, setConfirmando] = useState<CandidataServico | null>(null);
  const { toast, mostrar } = useToastLote();

  // A busca devolve os dados e `aplicar` os guarda no estado: assim o efeito de abertura só atualiza o estado dentro
  // do .then (nunca de forma síncrona), e o recarregar depois de salvar reaproveita as duas peças.
  const buscar = () => fetchComCache<EstadosReprodutivos>(CHAVE_CACHE_ESTADOS, () => fetchEstadosReprodutivos());
  function aplicar(r: { dados: EstadosReprodutivos | null; doCache: boolean }) {
    if (r.dados) { setEstados(r.dados); setDoCache(r.doCache); if (!r.doCache) setOcultos(new Set()); }
    setCarregando(false);
  }
  function recarregar() { buscar().then(aplicar); }
  useEffect(() => {
    buscar().then(aplicar);
  }, []);

  const mapaEstados = useMemo(() => new Map((estados?.animais ?? []).map((e) => [e.numero, e])), [estados]);
  const candidatas = useMemo(
    () => montarCandidatas(animais, mapaEstados, modo).filter((c) => !ocultos.has(c.numero)),
    [animais, mapaEstados, modo, ocultos],
  );
  const universo = useMemo(() => new Set(candidatas.map((c) => c.numero)), [candidatas]);

  const cardsAgenda = useCardsAgendaReprodutivaLeitura(undefined, origem === "agenda");
  const numerosAgenda = useMemo(() => {
    const s = new Set<string>();
    cardsSel.forEach((id) => (cardsAgenda.itensPorCard[id] || []).forEach((i) => s.add(i.numero_matriz)));
    return s;
  }, [cardsSel, cardsAgenda.itensPorCard]);
  const cardsComAnimais = useMemo(
    () => cardsAgenda.cards.map((c) => {
      const itens = cardsAgenda.itensPorCard[c.id] || [];
      return { id: c.id, nome: c.nome, n: itens.filter((i) => universo.has(i.numero_matriz)).length, fora: itens.filter((i) => !universo.has(i.numero_matriz)).length };
    }).filter((c) => c.n > 0),
    [cardsAgenda.cards, cardsAgenda.itensPorCard, universo],
  );
  const foraDosCards = cardsComAnimais.filter((c) => cardsSel.has(c.id)).reduce((m, c) => Math.max(m, c.fora), 0);

  const naOrigem = useMemo(
    () => recortarPorOrigem(candidatas, { origem, lotes: lotesSel, numerosAgenda }),
    [candidatas, origem, lotesSel, numerosAgenda],
  );
  const contagens = useMemo(() => contagensPorSituacao(naOrigem), [naOrigem]);
  const naSituacao = useMemo(() => naOrigem.filter((c) => passaFiltro(c, situacao)), [naOrigem, situacao]);
  const visiveis = useMemo(() => buscarCandidatas(naSituacao, busca), [naSituacao, busca]);
  const grupos = useMemo(() => agruparCandidatasPorLote(visiveis), [visiveis]);
  // Lotes com candidata para a situação de hoje (a contagem é de vacas que podem receber serviço).
  const opcoesLote = useMemo(() => lotesComCandidatas(candidatas.filter((c) => passaFiltro(c, situacao))), [candidatas, situacao]);
  const outrasSituacoes = useMemo(() => (busca.trim() ? existeEmOutraSituacao(candidatas, visiveis, busca) : []), [candidatas, visiveis, busca]);
  const emBloco = useMemo(() => marcaveisEmBloco(visiveis, situacao), [visiveis, situacao]);

  const sel = useMemo(() => (estados ? podarSelecao(selecao.sel, universo) : selecao.sel), [selecao.sel, universo, estados]);
  const marcadas = useMemo(() => candidatas.filter((c) => sel.has(c.numero)), [candidatas, sel]);
  const confirmadas = useMemo(() => marcadas.filter((c) => confirmacoes.sel.has(c.numero)), [marcadas, confirmacoes.sel]);
  const fora = contarForaDoFiltro(sel, visiveis.map((c) => c.numero));

  function alternar(c: CandidataServico) {
    if (c.status.travada) { vibrar(18); mostrar(c.status.curto ?? "Esta vaca não pode ser marcada agora."); return; }
    if (sel.has(c.numero)) {
      selecao.definir(alternarItem(selecao.sel, c.numero));
      if (confirmacoes.sel.has(c.numero)) confirmacoes.definir(alternarItem(confirmacoes.sel, c.numero));
      return;
    }
    if (c.status.confirmar) { setConfirmando(c); return; }
    selecao.definir(alternarItem(selecao.sel, c.numero));
  }
  function aceitarConfirmacao() {
    if (!confirmando) return;
    selecao.definir(new Set([...selecao.sel, confirmando.numero]));
    confirmacoes.definir(new Set([...confirmacoes.sel, confirmando.numero]));
    setConfirmando(null);
  }
  function marcarEmBloco() {
    const ids = emBloco.map((c) => c.numero);
    selecao.definir(definirVarios(selecao.sel, ids, !todosMarcados(sel, ids)));
  }
  /** Tira da seleção (e das confirmações) o que acabou de ser lançado. */
  function removerDaSelecao(numeros: readonly string[]) {
    const fora = new Set(numeros);
    selecao.definir(new Set([...selecao.sel].filter((n) => !fora.has(n))));
    confirmacoes.definir(new Set([...confirmacoes.sel].filter((n) => !fora.has(n))));
  }
  function ocultar(numeros: readonly string[]) { setOcultos((o) => new Set([...o, ...numeros])); }
  function tirarUma(numero: string) { removerDaSelecao([numero]); }
  function verEmTodas() { setSituacao("todas"); setOrigem("animais"); }

  return {
    modo, estados, doCache, carregando, recarregar,
    origem, setOrigem, situacao, setSituacao, lotesSel, setLotesSel, cardsSel, setCardsSel, busca, setBusca,
    cardsAgenda, cardsComAnimais, foraDosCards, numerosAgenda,
    candidatas, naOrigem, contagens, visiveis, grupos, opcoesLote, outrasSituacoes, emBloco,
    sel, marcadas, confirmadas, confirmacoes, fora, rascunho: selecao.sel.size > 0,
    alternar, marcarEmBloco, removerDaSelecao, ocultar, tirarUma, verEmTodas, aceitarConfirmacao, confirmando, setConfirmando,
    toast, mostrar,
  };
}

export type QuemServicoEstado = ReturnType<typeof useQuemServico>;

/** Passo 1 desenhado. `quando` = a frase depois de "Passo 1 de 2 · ". */
export function QuemServico({ q, quando, onContinuar }: { q: QuemServicoEstado; quando: ReactNode; onContinuar: () => void }) {
  const { modo } = q;
  const filtros = FILTROS_SITUACAO[modo];
  const semDados = !q.carregando && !q.estados;
  return (
    <>
      <PassoIndicador passo={1}>{quando}</PassoIndicador>
      <RascunhoAviso mostrar={q.rascunho} />
      {q.doCache && <AvisoLote tipo="offline">Sem internet: mostrando a lista do último acesso.</AvisoLote>}
      {semDados && <AvisoLote tipo="erro">Não consegui carregar a situação das vacas e não há lista guardada. Conecte-se e tente de novo.</AvisoLote>}

      <RotuloLote>Origem</RotuloLote>
      <SeletorOrigem valor={q.origem} onChange={q.setOrigem} />
      {q.origem === "lotes" && (
        <>
          <PilulasLote>
            {q.opcoesLote.map(([lote, n]) => (
              <PilulaLote key={lote} ativa={q.lotesSel.has(lote)} n={n} onClick={() => q.setLotesSel((p) => alternarItem(p, lote))}>{lote}</PilulaLote>
            ))}
          </PilulasLote>
          {q.opcoesLote.length > 0
            ? <NotaLote>Só lotes com candidatas. O número é de vacas que podem receber serviço.</NotaLote>
            : <NotaLote>Nenhum lote com candidatas nesta situação.</NotaLote>}
        </>
      )}
      {q.origem === "agenda" && (
        <>
          {q.cardsAgenda.carregando && <NotaLote>Carregando a agenda…</NotaLote>}
          {q.cardsAgenda.erro && <NotaLote>{q.cardsAgenda.erro}</NotaLote>}
          <PilulasLote>
            {q.cardsComAnimais.map((c) => (
              <PilulaLote key={c.id} ativa={q.cardsSel.has(c.id)} n={c.n} onClick={() => q.setCardsSel((p) => alternarItem(p, c.id))}>{c.nome}</PilulaLote>
            ))}
          </PilulasLote>
          {!q.cardsAgenda.carregando && !q.cardsAgenda.erro && !q.cardsComAnimais.length && <NotaLote>Nenhum card da agenda tem candidatas agora.</NotaLote>}
          {q.situacao === "d11" && <NotaLote>O D11 não vem de card da Agenda. Use Animais ou Lotes.</NotaLote>}
          {q.foraDosCards > 0 && <NotaLote>{q.foraDosCards} {plural(q.foraDosCards, "animal do card não entra", "animais do card não entram")} na lista (bezerras e novilhas ainda não aptas).</NotaLote>}
        </>
      )}

      <RotuloLote>Situação</RotuloLote>
      <div role="group" aria-label="Situação" className="lote-seg" style={{ gridTemplateColumns: `repeat(${filtros.length}, 1fr)` }}>
        {filtros.map((f) => (
          <button key={f.id} type="button" className="lote-btn-ft" aria-pressed={q.situacao === f.id} onClick={() => q.setSituacao(f.id)}>
            <b>{q.contagens[f.id]}</b>{f.rotulo}
          </button>
        ))}
      </div>
      <NotaLote>{NOTA_SITUACAO_SERVICO[q.situacao]}</NotaLote>

      <CampoBusca valor={q.busca} onChange={q.setBusca} placeholder="Buscar matriz, nome ou lote" />

      {q.emBloco.length > 0 && (
        <BotaoMarcarTodas marcado={todosMarcados(q.sel, q.emBloco.map((c) => c.numero))} rotulo={rotuloMarcarTodas(q.situacao)} n={q.emBloco.length} onClick={q.marcarEmBloco} />
      )}

      {q.outrasSituacoes.length > 0 && (
        <AvisoLote tipo="info">
          {q.outrasSituacoes.map((c) => <div key={c.numero} style={{ marginBottom: "0.4rem" }}>{frasePertenceOutraSituacao(c)}</div>)}
          <button type="button" className="lote-btn56" onClick={q.verEmTodas}>Ver em Todas</button>
        </AvisoLote>
      )}

      {q.carregando && <NotaLote>Carregando as vacas…</NotaLote>}
      <div aria-live="polite">
        {!q.carregando && !q.grupos.length && (
          <VazioLote>
            {q.origem === "lotes" && !q.lotesSel.size ? "Toque em um ou mais lotes."
              : q.origem === "agenda" && !q.cardsSel.size ? "Toque em um ou mais cards da agenda."
              : q.busca ? "Nenhum animal bate com a busca nesta situação."
              : "Nenhum animal nesta situação."}
          </VazioLote>
        )}
        {q.grupos.map((g) => (
          <section key={g.lote} aria-label={g.lote}>
            <CabecalhoGrupo titulo={g.lote} n={g.itens.length} />
            <div className="lote-lista">
              {g.itens.map((c) => <CartaoVaca key={c.numero} c={c} q={q} />)}
            </div>
          </section>
        ))}
      </div>
      {q.visiveis.length > 0 && <p className="lote-rodape-lista">Bezerras e novilhas ainda não aptas não aparecem. Se uma vaca não puder receber serviço, o servidor recusa ao enviar.</p>}

      <BarraContinuar n={q.marcadas.length} fora={q.fora} onContinuar={onContinuar} />

      {q.confirmando && (
        <SheetLote titulo={`${q.confirmando.numero}${q.confirmando.nome ? ` ${q.confirmando.nome}` : ""}: marcar mesmo assim?`} onFechar={() => q.setConfirmando(null)}>
          <p>{q.confirmando.status.texto}</p>
          <div className="dois">
            <button type="button" className="lote-cta" onClick={() => q.setConfirmando(null)}>Deixar de fora</button>
            <button type="button" className="lote-cta risco" onClick={q.aceitarConfirmacao}>Marcar mesmo assim</button>
          </div>
        </SheetLote>
      )}
      {q.toast}
    </>
  );
}

function CartaoVaca({ c, q }: { c: CandidataServico; q: QuemServicoEstado }) {
  const marcada = q.sel.has(c.numero);
  const confirmada = marcada && q.confirmacoes.sel.has(c.numero);
  const bits: string[] = [];
  if (c.del != null) bits.push(`DEL ${c.del}`);
  if (c.estado === "apta" || c.estado === "atrasada") bits.push(c.diasIA != null ? `última IA há ${c.diasIA} d` : "sem IA neste ciclo");
  if (c.estado === "inseminada" && c.diasIA != null) bits.push(`IA há ${c.diasIA} d`);
  const aviso = c.status.curto ?? c.status.texto;
  return (
    <CartaoAnimal
      brinco={c.numero} nome={c.nome || undefined} marcado={marcada} travado={c.status.travada} confirmar={c.status.confirmar}
      onClick={() => q.alternar(c)}
      linha2={
        <>
          {c.status.chip && <ChipSituacao tom={c.status.chip.tom}>{c.status.chip.rotulo}</ChipSituacao>}
          {bits.length > 0 && <span>{bits.join(" · ")}</span>}
        </>
      }
      extra={
        confirmada ? <span className="lote-sug alerta">Confirmado por você</span>
          : aviso && !marcada ? <span className={`lote-sug${c.status.confirmar ? " alerta" : ""}`}>{c.status.confirmar && <Lock size={13} strokeWidth={2.6} aria-hidden="true" />} {aviso}</span>
          : undefined
      }
    />
  );
}
