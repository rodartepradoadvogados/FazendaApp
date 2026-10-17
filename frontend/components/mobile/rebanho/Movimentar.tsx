"use client";
// Tela LANÇAR › "Movimentar animais" — em LOTE, em dois passos no mesmo desenho do Diagnóstico:
// (1) quem vai mudar de lote (origem Animais / Lotes / Sugestões → cartão-checkbox) e
// (2) para onde vão (lote de destino com a contagem "42 → 45", quadro De → Para, motivo, data, observação).
// Um único POST /movimentacoes/mover com todos os brincos (o servidor sempre aceitou a lista; a tela é que mandava um).
// Offline-first: a lista vem de fetchComCache e o envio sai por enviarOuEnfileirar. A seleção fica guardada como
// rascunho (se o app for interrompido no meio, não se perde) e persiste ao trocar de origem — mover costuma juntar
// animais de lugares diferentes.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, ArrowRightLeft } from "lucide-react";
import { fetchAnimais, fetchLotes, fetchMotivosMovimentacao, fetchSugestoesMovimentacao, today } from "@/lib/api";
import { enviarOuEnfileirar, fetchComCache, useConectividadeReal } from "@/lib/offline";
import {
  adultosParaLoteDeBezerras, agruparSugestoesPorDestino, alternarItem, codigoDoGrupo, comparaNumero, contagemDepois, contagemPorLote, contarForaDoFiltro,
  dataPorExtenso, definirVarios, destinoSugeridoPara, interpretarRespostaMover, normalizar, origemDoEnvio, plural, podarSelecao,
  projetarMovimentacao, rotuloDoGrupo, rotuloDoLote, soAnimais, todosMarcados,
  type AnimalMovivel, type LoteBasico, type OrigemLote, type SugestaoMov,
} from "@/lib/lancamentoLote";
import { RascunhoAviso } from "@/components/mobile/lancar/comum";
import {
  AvisoLote, CabecalhoGrupo, CampoBusca, CartaoAnimal, NotaLote, PassoIndicador, PilulaLote, PilulasLote, RotuloLote, SeletorOrigem, VazioLote,
} from "@/components/mobile/lancar/lote/SelecaoLote";
import { BarraAcao, BarraContinuar } from "@/components/mobile/lancar/lote/BarraLote";
import { ColapsavelLote, OpcaoLote, ResumoLote } from "@/components/mobile/lancar/lote/ResumoLote";
import { AcoesFim, LinhaQuadro, QuadroLote, ResultadoCabecalho } from "@/components/mobile/lancar/lote/ResultadoLote";
import { usePassos, useSelecaoPersistida } from "@/components/mobile/lancar/lote/hooks";
import { useToastLote } from "@/components/mobile/lancar/lote/SheetLote";

type Lote = LoteBasico & { id?: number };
type Resultado = {
  tipo: "ok" | "offline" | "erro";
  destino: Lote;
  movidos: string[];
  naoEncontrados: string[];
  motivo: string;
  antes: Map<string, number>;
  depois: Map<string, number>;
};

const ORIGENS_MOV: { id: OrigemLote; rotulo: string }[] = [
  { id: "animais", rotulo: "Animais" }, { id: "lotes", rotulo: "Lotes" }, { id: "agenda", rotulo: "Sugestões" },
];
const LIMITE_LISTA = 40;
const MOTIVO_OUTRO = "Outro motivo";

function vibrar(padrao: number | number[]) {
  try { navigator.vibrate?.(padrao); } catch { /* sem suporte — segue sem vibrar */ }
}

export default function Movimentar() {
  const online = useConectividadeReal();
  const { toast, mostrar } = useToastLote();
  const [animais, setAnimais] = useState<AnimalMovivel[]>([]);
  const [doCache, setDoCache] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [lotes, setLotes] = useState<Lote[]>([]);
  const [motivos, setMotivos] = useState<string[]>([]);
  const [sugestoes, setSugestoes] = useState<SugestaoMov[] | null>(null);

  const { passo, volta, ir } = usePassos<1 | 2 | 3>(1);
  const [origem, setOrigem] = useState<OrigemLote>("animais");
  const [lotesSel, setLotesSel] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");
  const { sel, definir } = useSelecaoPersistida("lote_movimentar");

  const [destinoCodigo, setDestinoCodigo] = useState<string | null>(null);
  const [motivo, setMotivo] = useState("");
  const [motivoLivre, setMotivoLivre] = useState("");
  const [motivoAberto, setMotivoAberto] = useState(false);
  const [obsAberta, setObsAberta] = useState(false);
  const [data, setData] = useState(today());
  const [obs, setObs] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);

  // Cada lista tem uma busca (com cache) e um "aplicar" que a guarda no estado; o efeito de abertura só atualiza o
  // estado dentro do .then, e o refresh depois de mover reaproveita as mesmas peças.
  const buscarAnimais = () => fetchComCache<AnimalMovivel[]>("animais_todos", () => fetchAnimais({ incluirMachos: true }));
  function aplicarAnimais(r: { dados: AnimalMovivel[] | null; doCache: boolean }) {
    if (r.dados) { setAnimais(soAnimais(r.dados)); setDoCache(r.doCache); }
    setCarregando(false);
  }
  const buscarLotes = () => fetchComCache<Lote[]>("lotes", () => fetchLotes());
  function aplicarLotes(r: { dados: Lote[] | null }) {
    if (r.dados) setLotes([...r.dados].sort((a, b) => comparaNumero(a.codigo, b.codigo)));
  }
  useEffect(() => {
    buscarAnimais().then(aplicarAnimais);
    buscarLotes().then(aplicarLotes);
    fetchComCache<string[]>("motivos_mov", () => fetchMotivosMovimentacao()).then(({ dados }) => { if (dados) setMotivos(dados); });
    fetchComCache<{ sugestoes: SugestaoMov[] }>("sugestoes_mov", () => fetchSugestoesMovimentacao()).then(({ dados }) => setSugestoes(dados?.sugestoes ?? []));
  }, []);

  const porNumero = useMemo(() => new Map(animais.map((a) => [a.numero, a])), [animais]);
  const contagem = useMemo(() => contagemPorLote(animais, lotes), [animais, lotes]);
  // Só conta o que ainda existe: rascunho de um animal que saiu do rebanho não infla o "N marcados".
  const marcados = useMemo(
    () => [...sel].map((n) => porNumero.get(n)).filter((a): a is AnimalMovivel => !!a).sort((a, b) => comparaNumero(a.numero, b.numero)),
    [sel, porNumero],
  );

  // Toda alteração passa por aqui: grava o rascunho já sem os números que não existem mais.
  function mudarSelecao(novo: Set<string>) {
    definir(porNumero.size ? podarSelecao(novo, new Set(porNumero.keys())) : novo);
  }

  // ── Passo 1: o que aparece em cada origem ──
  type Grupo = { chave: string; titulo: string; itens: AnimalMovivel[]; todo?: { rotulo: string } };
  const { grupos, totalAchados, dicaVazia } = useMemo(() => {
    const ordenar = (l: AnimalMovivel[]) => [...l].sort((a, b) => comparaNumero(a.numero, b.numero));
    const porLote = (lista: AnimalMovivel[]) => {
      const m = new Map<string, AnimalMovivel[]>();
      for (const a of lista) m.set(rotuloDoGrupo(a.grupo_primario), [...(m.get(rotuloDoGrupo(a.grupo_primario)) ?? []), a]);
      return [...m.entries()].sort(([x], [y]) => comparaNumero(x, y));
    };
    if (origem === "animais") {
      const q = normalizar(busca);
      if (!q) {
        const jaMarcados = ordenar(marcados);
        return {
          grupos: jaMarcados.length ? [{ chave: "marcados", titulo: "Já marcados", itens: jaMarcados }] : ([] as Grupo[]),
          totalAchados: 0, dicaVazia: "Digite o brinco, o nome ou o lote. Quem você marca fica guardado se trocar de origem.",
        };
      }
      const achados = animais.filter((a) => normalizar(a.numero).includes(q) || normalizar(a.nome).includes(q) || normalizar(a.grupo_primario).includes(q));
      const mostrados = ordenar(achados).slice(0, LIMITE_LISTA);
      return {
        grupos: porLote(mostrados).map(([lote, itens]) => ({ chave: lote, titulo: lote, itens, todo: { rotulo: "todos" } })) as Grupo[],
        totalAchados: achados.length, dicaVazia: `Nenhum animal bate com “${busca}”.`,
      };
    }
    if (origem === "lotes") {
      const g = [...lotesSel].sort(comparaNumero).map((codigo) => {
        const lote = lotes.find((l) => l.codigo === codigo);
        const itens = ordenar(animais.filter((a) => codigoDoGrupo(a.grupo_primario, lotes) === codigo));
        return { chave: codigo, titulo: lote ? rotuloDoLote(lote) : codigo, itens, todo: { rotulo: "todos" } };
      });
      return { grupos: g as Grupo[], totalAchados: 0, dicaVazia: "Toque em um ou mais lotes para ver os animais." };
    }
    const g = agruparSugestoesPorDestino(sugestoes ?? []).map((d) => ({
      chave: d.codigo, titulo: `Sugeridas para ${d.rotulo}`,
      itens: ordenar(d.itens.map((s) => porNumero.get(s.numero_matriz)).filter((a): a is AnimalMovivel => !!a)),
      todo: { rotulo: "as" },
    })).filter((x) => x.itens.length);
    return { grupos: g as Grupo[], totalAchados: 0, dicaVazia: sugestoes === null ? "Carregando as sugestões…" : "Nenhuma sugestão de movimentação agora." };
  }, [origem, busca, marcados, animais, lotes, lotesSel, sugestoes, porNumero]);

  const numerosVisiveis = useMemo(() => grupos.flatMap((g) => g.itens.map((a) => a.numero)), [grupos]);
  const fora = contarForaDoFiltro(new Set(marcados.map((a) => a.numero)), numerosVisiveis);
  const sugestaoDe = (numero: string) => sugestoes?.find((s) => s.numero_matriz === numero);

  function alternarAnimal(numero: string) { mudarSelecao(alternarItem(sel, numero)); }
  function alternarGrupo(itens: AnimalMovivel[]) {
    const ids = itens.map((a) => a.numero);
    mudarSelecao(definirVarios(sel, ids, !todosMarcados(sel, ids)));
  }

  function rotuloTodo(g: Grupo, ids: string[]): string {
    const todos = todosMarcados(sel, ids);
    if (g.todo?.rotulo === "as") return `${todos ? "Desmarcar" : "Marcar"} ${ids.length > 1 ? `as ${ids.length}` : "a vaca"}`;
    return `${todos ? "Desmarcar" : "Marcar"} ${ids.length > 1 ? "todos" : "o animal"}`;
  }

  // ── Passo 2 ──
  const lotesDestino = lotes;
  const destino = lotesDestino.find((l) => l.codigo === destinoCodigo) ?? null;
  const projecao = useMemo(
    () => (destino ? projetarMovimentacao(marcados, destino, lotes, contagem) : null),
    [destino, marcados, lotes, contagem],
  );
  const origensDistintas = new Set(marcados.map((a) => rotuloDoGrupo(a.grupo_primario))).size;
  const sugerido = useMemo(() => (origem === "agenda" ? destinoSugeridoPara(marcados, sugestoes ?? []) : null), [origem, marcados, sugestoes]);
  const adultos = destino ? adultosParaLoteDeBezerras(marcados, destino) : [];
  const nMover = projecao?.movem.length ?? 0;
  const motivoFinal = motivo === MOTIVO_OUTRO ? (motivoLivre.trim() || MOTIVO_OUTRO) : motivo;
  const textoOrigem = origem === "lotes" ? `Lotes ${[...lotesSel].sort(comparaNumero).join(", ")}` : origem === "agenda" ? "Sugestões da Agenda" : "Escolhidos por busca";

  function continuar() {
    if (!marcados.length) return;
    setErro(null);
    // Quando todos os marcados vêm de sugestões que apontam para o mesmo lote, o destino já vem escolhido.
    setDestinoCodigo(sugerido);
    ir(2);
  }

  async function enviar() {
    if (!destino || !projecao || !nMover || enviando) return;
    setEnviando(true);
    setErro(null);
    const brincos = projecao.movem.map((a) => a.numero);
    const antes = contagem;
    try {
      const { enviado, resposta } = await enviarOuEnfileirar(
        "/movimentacoes/mover",
        {
          data_movimento: data, motivo: motivoFinal || undefined, observacao: obs.trim() || undefined,
          lote_destino_codigo: destino.codigo, animais: brincos, origem: origemDoEnvio(projecao.movem, destino.codigo, sugestoes ?? []),
        },
        `Movimentação — ${brincos.length} ${plural(brincos.length, "animal", "animais")} → ${rotuloDoLote(destino)}`,
      );
      // Enviado não é o mesmo que "moveu de verdade": brinco que o servidor não acha volta em `nao_encontrados`
      // (mesma checagem de app/app/page.tsx::aceitarSugestaoMov).
      const { movidos, naoEncontrados } = enviado ? interpretarRespostaMover(brincos, resposta) : { movidos: brincos, naoEncontrados: [] as string[] };
      const conjuntoMovidos = new Set(movidos);
      const depois = contagemDepois(animais, lotes, conjuntoMovidos, destino);
      setAnimais((lista) => lista.map((a) => (conjuntoMovidos.has(a.numero) ? { ...a, grupo_primario: rotuloDoLote(destino) } : a)));
      mudarSelecao(new Set([...sel].filter((n) => !conjuntoMovidos.has(n))));
      const tipo: Resultado["tipo"] = !enviado ? "offline" : naoEncontrados.length ? "erro" : "ok";
      setResultado({ tipo, destino, movidos, naoEncontrados, motivo: motivoFinal, antes, depois });
      vibrar(tipo === "ok" ? 20 : tipo === "offline" ? [15, 60, 15] : [25, 60, 25, 60, 25]);
      ir(3);
      // Depois de mover online, as listas em cache (Lançar, Lotes, Indicadores) ficariam com o lote antigo.
      if (enviado) {
        buscarAnimais().then(aplicarAnimais);
        buscarLotes().then(aplicarLotes);
        fetchComCache("animais", () => fetchAnimais());
      }
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao mover os animais.");
      vibrar([25, 60, 25, 60, 25]);
    } finally {
      setEnviando(false);
    }
  }

  function novaMovimentacao() {
    setResultado(null); setDestinoCodigo(null); setMotivo(""); setMotivoLivre(""); setObs(""); setData(today());
    setBusca(""); setErro(null); setOrigem("animais"); setLotesSel(new Set());
    ir(1, true);
  }
  function conferir(brinco: string) {
    setResultado(null); setOrigem("animais"); setBusca(brinco);
    mudarSelecao(new Set([...sel, brinco]));
    ir(1, true);
  }

  const classeView = `lote lote-view${volta ? " volta" : ""}`;

  // ───────────────────────── Passo 3: resultado ─────────────────────────
  if (passo === 3 && resultado) {
    const r = resultado;
    const n = r.movidos.length;
    const afetados = lotes.filter((l) => (r.antes.get(l.codigo) ?? 0) !== (r.depois.get(l.codigo) ?? 0));
    const previsto = r.tipo === "offline";
    return (
      <div key="p3" className={classeView}>
        {r.tipo === "ok" && <ResultadoCabecalho tipo="ok" titulo={`${n} ${plural(n, "animal movido", "animais movidos")} para ${rotuloDoLote(r.destino)}`} texto={r.motivo ? `Motivo: ${r.motivo}` : "Movimentação salva."} />}
        {r.tipo === "offline" && <ResultadoCabecalho tipo="offline" titulo={`${n} ${plural(n, "movimentação guardada", "movimentações guardadas")}`} texto="Sem internet — guardado, será enviado ao conectar." />}
        {r.tipo === "erro" && (
          <ResultadoCabecalho tipo="erro" titulo={`${n} ${plural(n, "movido", "movidos")} · ${r.naoEncontrados.length} não ${plural(r.naoEncontrados.length, "encontrado", "encontrados")}`}
            texto={`O servidor não achou o ${plural(r.naoEncontrados.length, "brinco", "brincos")} ${r.naoEncontrados.join(", ")}. Confira o número; ${plural(r.naoEncontrados.length, "ele continua marcado", "eles continuam marcados")}.`} />
        )}
        {afetados.length > 0 && (
          <QuadroLote previsto={previsto} rotulo="Contagem dos lotes">
            {afetados.map((l) => {
              const a = r.antes.get(l.codigo) ?? 0;
              const d = r.depois.get(l.codigo) ?? 0;
              return (
                <LinhaQuadro key={l.codigo} nome={rotuloDoLote(l)} apoio={previsto ? "previsto ao conectar" : "contagem atual"}>
                  <span className="v">{a}</span><ArrowRight size={16} strokeWidth={2.4} aria-hidden="true" /><span>{d}</span>
                  <span className={`delta ${d > a ? "mais" : "menos"}`}>{d > a ? "+" : "−"}{Math.abs(d - a)}</span>
                </LinhaQuadro>
              );
            })}
          </QuadroLote>
        )}
        <AcoesFim>
          {r.tipo === "erro" ? (
            <>
              <button type="button" className="lote-cta" onClick={() => conferir(r.naoEncontrados[0])}>Conferir {r.naoEncontrados[0]}</button>
              <button type="button" className="lote-cta sec" onClick={novaMovimentacao}>Nova movimentação</button>
            </>
          ) : (
            <>
              <button type="button" className="lote-cta" onClick={novaMovimentacao}>Nova movimentação</button>
              <Link href="/app/rebanho?aba=lotes" className="lote-cta sec" style={{ textDecoration: "none" }}>Ver lotes</Link>
            </>
          )}
        </AcoesFim>
      </div>
    );
  }

  // ───────────────────────── Passo 2: para onde vão ─────────────────────────
  if (passo === 2) {
    const n = marcados.length;
    return (
      <div key="p2" className={classeView}>
        <PassoIndicador passo={2}>para <b>onde</b> vão</PassoIndicador>
        <ResumoLote titulo={`${n} ${plural(n, "animal", "animais")}`} sub={`${textoOrigem} · ${origensDistintas} ${plural(origensDistintas, "lote", "lotes")} de origem`} onAlterar={() => ir(1, true)} />

        <RotuloLote>Lote de destino</RotuloLote>
        <div className="lote-opcoes" role="group" aria-label="Lote de destino">
          {lotesDestino.map((l) => {
            const base = contagem.get(l.codigo) ?? 0;
            const proj = projetarMovimentacao(marcados, l, lotes, contagem);
            const nao = proj.movem.length === 0;
            const sub = [
              `${base} ${plural(base, "animal", "animais")} hoje`,
              proj.jaAqui.length ? `${proj.jaAqui.length} ${plural(proj.jaAqui.length, "marcado já está", "marcados já estão")} aqui` : "",
              sugerido === l.codigo ? "sugerido pela Agenda" : "",
            ].filter(Boolean).join(" · ");
            return (
              <OpcaoLote key={l.codigo} nome={rotuloDoLote(l)} sub={sub} selecionado={destinoCodigo === l.codigo} bloqueada={nao}
                numero={nao ? <span className="velho">{base}</span> : <><span className="velho">{base}</span><span className="ar"><ArrowRight size={18} strokeWidth={2.4} aria-hidden="true" /></span><span className="novo">{base + proj.movem.length}</span></>}
                onClick={() => {
                  if (nao) { vibrar(18); mostrar("Todos os marcados já estão neste lote."); return; }
                  setErro(null); setDestinoCodigo(l.codigo);
                }} />
            );
          })}
          {!lotesDestino.length && <VazioLote>Nenhum lote cadastrado.</VazioLote>}
        </div>

        <RotuloLote>De → Para</RotuloLote>
        {!destino || !projecao ? (
          <NotaLote>Escolha o lote de destino para ver o que muda em cada lote.</NotaLote>
        ) : (
          <div className="lote-dp">
            {projecao.porOrigem.map((o) => (
              <div className="lin" key={o.codigo || "sem"}>
                <div className="fluxo">
                  <div><div className="lt">{o.rotulo}</div><div className="qt"><b>{o.antes}</b> → <b>{o.depois}</b></div></div>
                  <div className="seta"><ArrowRight size={26} strokeWidth={2.4} aria-hidden="true" /></div>
                  <div className="dir"><div className="lt">{rotuloDoLote(destino)}</div><div className="qt">+{o.animais.length} {plural(o.animais.length, "animal", "animais")}</div></div>
                </div>
                <div className="brincos">
                  {o.animais.slice(0, 8).map((a) => <span className="bq" key={a.numero}>{a.numero}</span>)}
                  {o.animais.length > 8 && <span className="bq mais">+{o.animais.length - 8}</span>}
                </div>
              </div>
            ))}
            {projecao.jaAqui.length > 0 && (
              <div className="lin">
                <div className="lt" style={{ fontSize: "0.9rem" }}>{rotuloDoLote(destino)} · já {plural(projecao.jaAqui.length, "está aqui", "estão aqui")}</div>
                <div className="brincos">{projecao.jaAqui.map((a) => <span className="bq aqui" key={a.numero}>{a.numero}</span>)}</div>
                <div className="aqui-nota">Não {plural(projecao.jaAqui.length, "conta", "contam")} na movimentação.</div>
              </div>
            )}
            <div className="lin">
              <div className="fluxo" style={{ gridTemplateColumns: "1fr auto" }}>
                <div>
                  <div className="lt">{rotuloDoLote(destino)} depois</div>
                  <div className="qt">{projecao.movem.length} {plural(projecao.movem.length, "animal chega", "animais chegam")}</div>
                </div>
                <div className="lt" style={{ fontSize: "1.5rem", fontVariantNumeric: "tabular-nums" }}>
                  <span style={{ color: "var(--mob-muted)", fontWeight: 700 }}>{projecao.destinoAntes}</span> → <span style={{ color: "var(--ft-ouro-txt)" }}>{projecao.destinoDepois}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        <RotuloLote>Motivo <span style={{ textTransform: "none", letterSpacing: 0, fontWeight: 600 }}>(opcional)</span></RotuloLote>
        <ColapsavelLote titulo={motivoFinal || "Nenhum motivo"} dica={motivoFinal ? "Toque para trocar" : "Toque para escolher"} aberto={motivoAberto} onAlternar={() => setMotivoAberto((v) => !v)}>
          <PilulasLote>
            {motivos.map((m) => <PilulaLote key={m} ativa={motivo === m} onClick={() => setMotivo(motivo === m ? "" : m)}>{m}</PilulaLote>)}
          </PilulasLote>
          {motivo === MOTIVO_OUTRO && (
            <input type="text" className="mob-input" value={motivoLivre} onChange={(e) => setMotivoLivre(e.target.value)} placeholder="Escreva o motivo" aria-label="Motivo" style={{ marginTop: "0.6rem" }} />
          )}
          {!motivos.length && <NotaLote>Os motivos vêm do cadastro da fazenda (Configurações).</NotaLote>}
        </ColapsavelLote>

        <RotuloLote>Data</RotuloLote>
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value || data)} aria-label="Data da movimentação" />
        <p className="lote-nota" style={{ marginTop: "0.35rem" }}>{dataPorExtenso(data)}</p>

        <div style={{ marginTop: "0.8rem" }}>
          <ColapsavelLote titulo="Observação" dica="Opcional" aberto={obsAberta} onAlternar={() => setObsAberta((v) => !v)}>
            <textarea className="mob-input" value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Ex.: saiu do lote por mastite tratada" aria-label="Observação" />
          </ColapsavelLote>
        </div>
        <NotaLote>O novo lote fica fixado à mão: o próximo relatório do Ideagri não desfaz a mudança.</NotaLote>

        {adultos.length > 0 && destino && (
          <AvisoLote tipo="atencao">Entre os marcados há {adultos.length === 1 ? "um animal que não é bezerra" : `${adultos.length} animais que não são bezerras`}. Confira o lote de destino.</AvisoLote>
        )}
        {!online && <AvisoLote tipo="offline"><b>Sem internet.</b> A movimentação vai para a fila e é enviada ao conectar. Os números acima são previstos.</AvisoLote>}
        {erro && <AvisoLote tipo="erro">{erro}</AvisoLote>}

        <BarraAcao>
          <button type="button" className="lote-cta" disabled={!destino || nMover === 0 || enviando} onClick={enviar}>
            <ArrowRightLeft size={22} strokeWidth={2.4} aria-hidden="true" />
            {enviando ? "Enviando…" : !destino ? "Escolha o lote de destino" : nMover ? `Movimentar ${nMover} ${plural(nMover, "animal", "animais")}` : "Nada a movimentar"}
          </button>
        </BarraAcao>
        {toast}
      </div>
    );
  }

  // ───────────────────────── Passo 1: quem ─────────────────────────
  return (
    <div key="p1" className={classeView}>
      <PassoIndicador passo={1}><b>quem</b> vai mudar de lote</PassoIndicador>
      <RascunhoAviso mostrar={sel.size > 0 && passo === 1} />
      {doCache && <AvisoLote tipo="offline">Sem internet: mostrando a lista do último acesso.</AvisoLote>}

      <RotuloLote>Origem</RotuloLote>
      <SeletorOrigem valor={origem} onChange={setOrigem} opcoes={ORIGENS_MOV} />

      {origem === "lotes" && (
        <PilulasLote>
          {lotes.filter((l) => (contagem.get(l.codigo) ?? 0) > 0).map((l) => (
            <PilulaLote key={l.codigo} ativa={lotesSel.has(l.codigo)} n={contagem.get(l.codigo) ?? 0}
              onClick={() => setLotesSel((p) => alternarItem(p, l.codigo))}>{rotuloDoLote(l)}</PilulaLote>
          ))}
        </PilulasLote>
      )}
      {origem === "agenda" && <NotaLote>Sugestões de movimentação que a Agenda já calculou. Toque para marcar.</NotaLote>}
      {origem === "animais" && <CampoBusca valor={busca} onChange={setBusca} placeholder="Buscar brinco, nome ou lote" />}

      {carregando && <p className="lote-nota">Carregando os animais…</p>}
      <div aria-live="polite">
        {!carregando && !grupos.length && (origem === "animais" && !busca.trim() ? <NotaLote>{dicaVazia}</NotaLote> : <VazioLote>{dicaVazia}</VazioLote>)}
        {grupos.map((g) => {
          const ids = g.itens.map((a) => a.numero);
          return (
            <section key={g.chave} aria-label={g.titulo}>
              <CabecalhoGrupo titulo={g.titulo} n={g.itens.length}
                todo={g.todo ? { marcado: todosMarcados(sel, ids), rotulo: rotuloTodo(g, ids), onClick: () => alternarGrupo(g.itens) } : undefined} />
              <div className="lote-lista">
                {g.itens.map((a) => {
                  const s = origem === "agenda" ? sugestaoDe(a.numero) : undefined;
                  return (
                    <CartaoAnimal key={a.numero} brinco={a.numero} nome={a.nome ?? undefined} marcado={sel.has(a.numero)} onClick={() => alternarAnimal(a.numero)}
                      linha2={
                        <>
                          {origem !== "lotes" && <span className="lote-chip lote-atual" title="Lote atual">lote <b>{rotuloDoGrupo(a.grupo_primario)}</b></span>}
                          <span>{a.categoria_abrev || a.categoria_completa || ""}{origem === "lotes" && a.del_dias != null ? ` · DEL ${a.del_dias}` : ""}</span>
                        </>
                      }
                      extra={s?.motivo ? <span className="lote-sug">{s.motivo}</span> : undefined} />
                  );
                })}
              </div>
            </section>
          );
        })}
        {origem === "animais" && totalAchados > LIMITE_LISTA && <p className="lote-rodape-lista">Mostrando {LIMITE_LISTA} de {totalAchados}. Escreva mais para afinar.</p>}
      </div>

      <BarraContinuar n={marcados.length} fora={fora} onContinuar={continuar} />
    </div>
  );
}
