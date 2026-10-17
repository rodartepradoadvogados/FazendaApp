"use client";
// Lançar › Reprodutivo › Inseminação — em LOTE, em dois passos (mesmo desenho do Diagnóstico):
// (1) quem vai ser inseminada (ver QuemServico) e (2) o que foi feito: data, categoria, touro/sêmen com as doses em
// estoque ("14 → 6") e, se quiser, um touro diferente para uma vaca. Cada vaca vira UMA inseminação — um
// POST /reproducao/servico por animal (decisão do dono), com barra "3 de 8"; se alguma falhar, o resultado diz qual e
// por quê, e "Tentar de novo só essa" reenvia só as que falharam. Categoria "Touro da fazenda" = monta natural (não debita
// dose). Na vaca que está no D11 de um IATF o envio leva o nome do protocolo, e o servidor fecha sozinho a etapa de
// inseminação na Agenda.
import { useState } from "react";
import { ArrowRight, RotateCcw, Syringe } from "lucide-react";
import {
  ErroApi, fetchProtocolosIatfAtivos, fetchSemenDisponivel, fetchTouros, type SemenDisponivel, type Touro,
} from "@/lib/api";
import { enviarOuEnfileirar, fetchComCache, useConectividadeReal } from "@/lib/offline";
import { invalidarEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import {
  corpoServico, dataBr, dataPorExtenso, dosesQueFaltam, dosesQueSobram, plural, resumoOrigem, usoPorTouro,
  type AnimalDaLista, type CategoriaSemen, type OpcaoTouro,
} from "@/lib/lancamentoLote";
import { MobBarraProgresso } from "@/components/mobile/ui";
import { TouroPicker, type TouroPickerItem } from "@/components/TouroPicker";
import { hoje, useCache } from "../comum";
import { AvisoLote, ChipSituacao, NotaLote, PassoIndicador, RotuloLote } from "./SelecaoLote";
import { BarraAcao } from "./BarraLote";
import { ColapsavelLote, OpcaoLote, ResumoLote } from "./ResumoLote";
import { AcoesFim, LinhaQuadro, QuadroLote, ResultadoCabecalho } from "./ResultadoLote";
import { SheetLote } from "./SheetLote";
import { usePassos } from "./hooks";
import { QuemServico, useQuemServico } from "./QuemServico";

const CATEGORIAS: { id: CategoriaSemen; rotulo: string }[] = [
  { id: "convencional", rotulo: "Convencional" }, { id: "sexado", rotulo: "Sexado" }, { id: "fazenda", rotulo: "Touro da fazenda" },
];

type UsoDose = { antes: number; usados: number; previstos: number };
type Falha = { numero: string; motivo: string; confirmavel: boolean };
type Envio = { salvos: string[]; guardados: string[]; falhas: Falha[] };
type Resultado = { total: number; data: string; touro: string; categoria: CategoriaSemen; envio: Envio };

function vibrar(padrao: number | number[]) {
  try { navigator.vibrate?.(padrao); } catch { /* sem suporte — segue sem vibrar */ }
}

export function Inseminacao({ animais, animalFixado, matrizesIniciais }: {
  animais: readonly AnimalDaLista[]; animalFixado: string | null; matrizesIniciais?: string[];
}) {
  const online = useConectividadeReal();
  const semen = useCache<SemenDisponivel | null>("semen_disponivel", () => fetchSemenDisponivel(), null);
  // O animal da ficha e as matrizes do "Diagnóstico Negativo → Salvar e lançar inseminação" entram já marcados: são
  // escolhas que a pessoa acabou de fazer em outra tela. Qualquer outra seleção começa vazia.
  const obrigatorios = [...(animalFixado ? [animalFixado] : []), ...(matrizesIniciais ?? [])];
  const q = useQuemServico({ modo: "ia", animais, chave: "lote_inseminacao", obrigatorios });
  const { passo, volta, ir } = usePassos<1 | 2 | 3>(1);

  const [data, setData] = useState(hoje());
  const [categoria, setCategoria] = useState<CategoriaSemen>("convencional");
  const [touro, setTouro] = useState("");
  const [troca, setTroca] = useState<Record<string, string>>({});
  const [trocando, setTrocando] = useState<string | null>(null);
  const [trocaAberta, setTrocaAberta] = useState(false);
  const [semEstoque, setSemEstoque] = useState(false);
  const [catalogo, setCatalogo] = useState<Touro[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [progresso, setProgresso] = useState<{ feitos: number; total: number } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [doses, setDoses] = useState<Record<string, UsoDose>>({});

  const ehFazenda = categoria === "fazenda";
  const marcadas = q.marcadas;
  const n = marcadas.length;
  const touroDe = (numero: string) => troca[numero] ?? touro;
  const uso = usoPorTouro(marcadas.map((c) => c.numero), touroDe);

  // Touros da categoria com as doses em estoque; o catálogo NAAB (sem estoque) só entra se a pessoa escolher um de lá.
  const doEstoque: OpcaoTouro[] = (semen.dados?.touros ?? []).filter((t) => t.tipo === categoria).map((t) => ({ nome: t.nome, doses: ehFazenda ? null : t.doses }));
  const opcoes: OpcaoTouro[] = [
    ...doEstoque,
    ...[...new Set([touro, ...Object.values(troca)].filter(Boolean))].filter((nome) => !doEstoque.some((t) => t.nome === nome)).map((nome) => ({ nome, doses: ehFazenda ? null : 0, catalogo: true })),
  ];
  const dosesDe = (nome: string) => opcoes.find((t) => t.nome === nome)?.doses ?? null;
  const itensCatalogo: TouroPickerItem[] = catalogo.map((t) => ({ naab: t.naab, nome: t.nome || t.naab, central: t.central, raca: t.raca, tpi: t.tpi }));

  const jaInseminadas = marcadas.filter((c) => c.estado === "inseminada").length;
  const comoGestante = marcadas.filter((c) => q.confirmacoes.sel.has(c.numero) && c.estado === "gestante").length;
  const noD11 = marcadas.filter((c) => c.status.d11).length;
  const nTrocas = marcadas.filter((c) => troca[c.numero] !== undefined).length;
  const nomesCards = q.cardsComAnimais.filter((c) => q.cardsSel.has(c.id)).map((c) => c.nome);

  function mudarCategoria(c: CategoriaSemen) { setCategoria(c); setTouro(""); setTroca({}); setSemEstoque(false); }
  function alternarCatalogo(ligado: boolean) {
    setSemEstoque(ligado);
    if (!ligado) setTouro((t) => (doEstoque.some((x) => x.nome === t) ? t : ""));
    if (ligado && !catalogo.length) fetchComCache<Touro[]>("touros_naab", () => fetchTouros()).then(({ dados }) => { if (dados) setCatalogo(dados); });
  }

  // Nome do protocolo IATF de cada vaca no D11 — o servidor casa pelo nome para fechar a etapa na Agenda. Só é buscado
  // quando há alguma vaca nesse dia; sem internet o envio segue sem o vínculo (a inseminação em si não depende dele).
  async function protocolosDoD11(numeros: string[]): Promise<Map<string, string>> {
    const mapa = new Map<string, string>();
    if (!numeros.length) return mapa;
    const r = await fetchComCache<{ nome_protocolo: string; animais: { numero_matriz: string; pronta_para_inseminar?: boolean }[] }[]>(
      "protocolos_iatf_ativos", () => fetchProtocolosIatfAtivos(),
    );
    for (const p of r.dados ?? []) for (const a of p.animais) if (a.pronta_para_inseminar && numeros.includes(a.numero_matriz)) mapa.set(a.numero_matriz, p.nome_protocolo);
    return mapa;
  }

  async function enviarLista(numeros: string[], forcarTodas: boolean, acumulado: Envio): Promise<Envio> {
    const alvo = q.candidatas.filter((c) => numeros.includes(c.numero));
    const protocolos = await protocolosDoD11(alvo.filter((c) => c.status.d11).map((c) => c.numero));
    const envio: Envio = { salvos: [], guardados: [], falhas: [] };
    setProgresso({ feitos: 0, total: alvo.length });
    for (let i = 0; i < alvo.length; i++) {
      const c = alvo[i];
      const t = touroDe(c.numero);
      try {
        const { enviado } = await enviarOuEnfileirar(
          "/reproducao/servico",
          corpoServico({ numero: c.numero, data, categoria, touro: t, protocolo: protocolos.get(c.numero), confirmada: forcarTodas || q.confirmacoes.sel.has(c.numero) }),
          `${ehFazenda ? "Monta natural" : "Inseminação"} — matriz ${c.numero}${t ? ` (${t})` : ""}`,
        );
        (enviado ? envio.salvos : envio.guardados).push(c.numero);
        // Dose gasta (ou prevista, se ficou na fila) do touro desta vaca.
        const base = dosesDe(t);
        if (!ehFazenda && t && base != null) {
          setDoses((d) => {
            const atual = d[t] ?? { antes: base, usados: 0, previstos: 0 };
            return { ...d, [t]: { ...atual, usados: atual.usados + (enviado ? 1 : 0), previstos: atual.previstos + (enviado ? 0 : 1) } };
          });
        }
      } catch (e) {
        envio.falhas.push({
          numero: c.numero, motivo: e instanceof Error ? e.message : "erro ao salvar",
          confirmavel: e instanceof ErroApi && e.status === 409 && e.confirmavel,
        });
      }
      setProgresso({ feitos: i + 1, total: alvo.length });
    }
    const unido: Envio = {
      salvos: [...acumulado.salvos, ...envio.salvos], guardados: [...acumulado.guardados, ...envio.guardados], falhas: envio.falhas,
    };
    const feitos = [...envio.salvos, ...envio.guardados];
    q.removerDaSelecao(feitos);
    q.ocultar(feitos);
    invalidarEstadosReprodutivos();
    if (envio.salvos.length) fetchComCache<SemenDisponivel>("semen_disponivel", () => fetchSemenDisponivel());
    setProgresso(null);
    return unido;
  }

  async function salvar() {
    if (enviando || !n) return;
    if (!data) { setErro("Informe a data da inseminação."); return; }
    setEnviando(true);
    setErro(null);
    // Estoque de antes de cada touro, para o quadro "antes → depois" do resultado.
    const base: Record<string, UsoDose> = {};
    if (!ehFazenda) for (const nome of Object.keys(uso)) { const d = dosesDe(nome); if (d != null) base[nome] = { antes: d, usados: 0, previstos: 0 }; }
    setDoses(base);
    const envio = await enviarLista(marcadas.map((c) => c.numero), false, { salvos: [], guardados: [], falhas: [] });
    setEnviando(false);
    finalizar(envio, n);
  }

  async function tentarDeNovo(forcarTodas: boolean) {
    if (!resultado || enviando) return;
    setEnviando(true);
    const envio = await enviarLista(resultado.envio.falhas.map((f) => f.numero), forcarTodas, resultado.envio);
    setEnviando(false);
    finalizar(envio, resultado.total);
  }

  function finalizar(envio: Envio, total: number) {
    setResultado({ total, data, touro, categoria, envio });
    vibrar(envio.falhas.length ? [25, 60, 25, 60, 25] : envio.guardados.length ? [15, 60, 15] : 20);
    // Depois de salvar online, a situação das vacas mudou: recarrega para a lista já nascer certa.
    if (envio.salvos.length && !envio.guardados.length) q.recarregar();
    ir(3);
  }

  function nova() {
    setResultado(null); setTouro(""); setTroca({}); setDoses({}); setErro(null); setData(hoje());
    ir(1, true);
  }

  const classeView = `lote lote-view${volta ? " volta" : ""}`;

  // ───────────────────────── Passo 3: resultado ─────────────────────────
  if (passo === 3 && resultado) {
    const { envio } = resultado;
    const ok = envio.salvos.length;
    const gd = envio.guardados.length;
    const fl = envio.falhas.length;
    const nomesDoses = Object.keys(doses);
    const previsto = gd > 0 && ok === 0;
    return (
      <div key="p3" className={classeView}>
        {fl > 0 ? (
          <ResultadoCabecalho tipo="erro" titulo={`Salvas ${ok + gd} · Falhou ${fl} (${envio.falhas.map((f) => f.numero).join(", ")})`}
            texto={`${plural(fl, "Ela continua marcada", "Elas continuam marcadas")}. Motivo: ${envio.falhas[0].motivo}.`} />
        ) : gd > 0 ? (
          <ResultadoCabecalho tipo="offline" titulo={`${gd} ${plural(gd, "inseminação guardada", "inseminações guardadas")}`}
            texto={`Sem internet — guardado, será enviado ao conectar.${ok ? ` Salvas agora: ${ok}.` : ""}`} />
        ) : (
          <ResultadoCabecalho tipo="ok" titulo={`${ok} ${plural(ok, ehFazenda ? "vaca coberta" : "vaca inseminada", ehFazenda ? "vacas cobertas" : "vacas inseminadas")}`}
            texto={`${dataBr(resultado.data)}${resultado.touro ? ` · ${resultado.touro}` : ""}${resultado.categoria === "fazenda" ? " · monta natural" : ""}`} />
        )}
        {fl > 0 && (
          <QuadroLote rotulo="Vacas que não salvaram">
            {envio.falhas.map((f) => {
              const c = q.candidatas.find((x) => x.numero === f.numero);
              return (
                <LinhaQuadro key={f.numero} nome={<><span className="brinco" style={{ fontSize: "1.2rem", fontVariantNumeric: "tabular-nums" }}>{f.numero}</span> {c?.nome}</>} apoio={f.motivo}>
                  <ChipSituacao tom="atrasada">Não salvou</ChipSituacao>
                </LinhaQuadro>
              );
            })}
          </QuadroLote>
        )}
        {nomesDoses.length > 0 && (
          <QuadroLote previsto={previsto} rotulo="Doses de cada touro">
            {nomesDoses.map((nome) => {
              const e = doses[nome];
              const k = e.usados + e.previstos;
              const falta = dosesQueFaltam(e.antes, k);
              return (
                <LinhaQuadro key={nome} nome={nome}
                  apoio={e.previstos > 0 ? "doses previstas ao conectar" : falta ? `faltaram ${falta} ${plural(falta, "dose", "doses")}: confira o estoque` : "doses em estoque"}>
                  <span className="v">{e.antes}</span><ArrowRight size={16} strokeWidth={2.4} aria-hidden="true" /><span>{dosesQueSobram(e.antes, k)}</span>
                </LinhaQuadro>
              );
            })}
          </QuadroLote>
        )}
        <AcoesFim>
          {fl > 0 ? (
            <>
              <button type="button" className="lote-cta" disabled={enviando} onClick={() => tentarDeNovo(false)}>
                <RotateCcw size={20} strokeWidth={2.4} aria-hidden="true" /> {enviando ? "Enviando…" : `Tentar de novo só ${fl === 1 ? envio.falhas[0].numero : `essas ${fl}`}`}
              </button>
              {envio.falhas.every((f) => f.confirmavel) && (
                <button type="button" className="lote-cta risco" disabled={enviando} onClick={() => tentarDeNovo(true)}>Confirmar e tentar de novo</button>
              )}
              <button type="button" className="lote-cta sec" onClick={() => ir(1, true)}>Voltar e conferir</button>
              {progresso && <MobBarraProgresso feitos={progresso.feitos} total={progresso.total} rotulo="Enviando de novo" />}
            </>
          ) : (
            <button type="button" className="lote-cta" onClick={nova}>{ehFazenda ? "Nova cobertura" : "Nova inseminação"}</button>
          )}
        </AcoesFim>
      </div>
    );
  }

  // ───────────────────────── Passo 2: o que foi feito ─────────────────────────
  if (passo === 2) {
    return (
      <div key="p2" className={classeView}>
        <PassoIndicador passo={2}>o <b>que</b> foi feito</PassoIndicador>
        <ResumoLote titulo={`${n} ${plural(n, "vaca", "vacas")}`} sub={resumoOrigem(q.origem, q.lotesSel, nomesCards)} onAlterar={() => ir(1, true)} />

        <RotuloLote>Data da inseminação/cobertura</RotuloLote>
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value || data)} aria-label="Data da inseminação" />
        <p className="lote-nota" style={{ marginTop: "0.35rem" }}>{dataPorExtenso(data)}</p>

        <RotuloLote>Categoria do touro / sêmen</RotuloLote>
        <div role="group" aria-label="Categoria" className="lote-seg" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
          {CATEGORIAS.map((c) => (
            <button key={c.id} type="button" className="lote-btn-ft" aria-pressed={categoria === c.id} onClick={() => mudarCategoria(c.id)} style={{ minHeight: 60, color: categoria === c.id ? undefined : "var(--mob-text)", fontSize: "0.84rem" }}>{c.rotulo}</button>
          ))}
        </div>
        {ehFazenda && <NotaLote>Touro da fazenda: registrado como <b>monta natural</b>, sem debitar dose de sêmen.</NotaLote>}

        <RotuloLote>{ehFazenda ? "Touro (monta natural)" : <>Touro / sêmen <span style={{ textTransform: "none", letterSpacing: 0, fontWeight: 600 }}>(opcional)</span></>}</RotuloLote>
        <div className="lote-opcoes" role="group" aria-label="Touro">
          <OpcaoLote nome="Definir depois" sub={ehFazenda ? "Sem touro informado" : "Sem touro: a inseminação entra sem sêmen informado"} selecionado={touro === ""} onClick={() => setTouro("")} />
          {opcoes.map((t) => {
            const k = uso[t.nome] ?? 0;
            const falta = t.doses != null && k > t.doses;
            return (
              <OpcaoLote key={t.nome} nome={t.nome} selecionado={touro === t.nome} onClick={() => setTouro(t.nome)}
                sub={ehFazenda ? "monta natural, sem baixa de sêmen" : t.catalogo ? "catálogo, sem estoque" : categoria}
                numero={t.doses == null ? undefined : k
                  ? <><span className="velho">{t.doses}</span><span className="ar"><ArrowRight size={16} strokeWidth={2.4} aria-hidden="true" /></span><span className={`novo${falta ? " falta" : ""}`}>{dosesQueSobram(t.doses, k)}</span><span className="un">doses</span></>
                  : <><span>{t.doses}</span><span className="un">doses</span></>} />
            );
          })}
        </div>
        {!doEstoque.length && <NotaLote>{ehFazenda ? "Nenhum touro da fazenda cadastrado." : `Nenhum sêmen ${categoria} em estoque.`}</NotaLote>}
        {Object.entries(uso).map(([nome, k]) => {
          const d = dosesDe(nome);
          return d != null && d < k ? (
            <AvisoLote key={nome} tipo="atencao"><b>{nome}</b> tem {d} {plural(d, "dose", "doses")} e {k} {plural(k, "vaca vai", "vacas vão")} usar. Faltam {k - d}. Dá para lançar; confira o estoque depois.</AvisoLote>
          ) : null;
        })}
        {!ehFazenda && (
          <>
            <label className="lote-cartao" style={{ minHeight: 56, marginTop: "0.6rem", cursor: "pointer" }}>
              <input type="checkbox" checked={semEstoque} onChange={(e) => alternarCatalogo(e.target.checked)} style={{ width: 24, height: 24, accentColor: "var(--mob-acao)" }} />
              <span className="lote-cc" style={{ fontSize: "0.9rem", fontWeight: 600 }}>Incluir touros sem estoque (catálogo NAAB)</span>
            </label>
            {semEstoque && (
              <div style={{ marginTop: "0.5rem" }}>
                <TouroPicker className="mob-input" itens={itensCatalogo} value={touro} placeholder="Buscar touro no catálogo NAAB..."
                  onChangeTexto={setTouro} onSelecionar={(t) => setTouro(t.nome)} />
              </div>
            )}
          </>
        )}

        <RotuloLote>Touro por vaca</RotuloLote>
        <ColapsavelLote titulo={nTrocas ? `${nTrocas} ${plural(nTrocas, "vaca com touro trocado", "vacas com touro trocado")}` : "Todas com o mesmo touro"} dica="Toque para trocar o touro de uma vaca"
          aberto={trocaAberta} onAlternar={() => setTrocaAberta((v) => !v)}>
          <div style={{ display: "grid", gap: "0.4rem" }}>
            {marcadas.map((c) => {
              const t = touroDe(c.numero);
              return (
                <div key={c.numero} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
                  <div style={{ minWidth: 0 }}>
                    <span style={{ fontSize: "1.1rem", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{c.numero}</span>{" "}
                    <span style={{ fontWeight: 600 }}>{c.nome}</span>
                  </div>
                  <button type="button" className="lote-btn56" style={{ fontSize: "0.85rem" }} onClick={() => setTrocando(c.numero)}>
                    {t || "Sem touro"}{troca[c.numero] !== undefined ? " · trocado" : ""}
                  </button>
                </div>
              );
            })}
          </div>
        </ColapsavelLote>

        {(jaInseminadas > 0 || comoGestante > 0) && (
          <NotaLote>
            {jaInseminadas > 0 && <>{jaInseminadas} {plural(jaInseminadas, "inseminada recente", "inseminadas recentes")}: a inseminação anterior {plural(jaInseminadas, "vira", "viram")} negativa. </>}
            {comoGestante > 0 && <>{comoGestante} {plural(comoGestante, "confirmada por você", "confirmadas por você")} como gestante.</>}
          </NotaLote>
        )}
        {noD11 > 0 && <AvisoLote tipo="info">{noD11} {plural(noD11, "vem", "vêm")} de protocolo IATF: a etapa D11 {plural(noD11, "dela", "delas")} na Agenda fecha junto.</AvisoLote>}
        <NotaLote>Cada vaca vira uma inseminação (um envio por animal). Se alguma falhar, só ela fica para tentar de novo.</NotaLote>
        {!online && <AvisoLote tipo="offline"><b>Sem internet.</b> As inseminações vão para a fila e são enviadas ao conectar. As doses mostradas são previstas.</AvisoLote>}
        {erro && <AvisoLote tipo="erro">{erro}</AvisoLote>}

        <BarraAcao>
          {progresso && <MobBarraProgresso feitos={progresso.feitos} total={progresso.total} rotulo="Enviando inseminações" />}
          <button type="button" className="lote-cta" disabled={!n || enviando} onClick={salvar}>
            <Syringe size={22} strokeWidth={2.2} aria-hidden="true" /> {enviando ? "Enviando…" : `${ehFazenda ? "Salvar cobertura" : "Salvar inseminação"} (${n})`}
          </button>
        </BarraAcao>

        {trocando && (
          <SheetLote titulo={`Touro para ${trocando}`} onFechar={() => setTrocando(null)}>
            <div className="lote-opcoes">
              <OpcaoLote nome="Usar o padrão" sub={touro || "sem touro definido"} selecionado={troca[trocando] === undefined}
                onClick={() => { setTroca((p) => { const novo = { ...p }; delete novo[trocando]; return novo; }); setTrocando(null); }} />
              <OpcaoLote nome="Sem touro" selecionado={troca[trocando] === ""} onClick={() => { setTroca((p) => ({ ...p, [trocando]: "" })); setTrocando(null); }} />
              {opcoes.map((t) => (
                <OpcaoLote key={t.nome} nome={t.nome} sub={t.doses != null ? `${t.doses} ${plural(t.doses, "dose", "doses")}` : "monta natural"} selecionado={troca[trocando] === t.nome}
                  onClick={() => { setTroca((p) => ({ ...p, [trocando]: t.nome })); setTrocaAberta(true); setTrocando(null); }} />
              ))}
            </div>
          </SheetLote>
        )}
      </div>
    );
  }

  // ───────────────────────── Passo 1: quem ─────────────────────────
  return (
    <div key="p1" className={classeView}>
      <QuemServico q={q} quando={<><b>quem</b> vai ser inseminada</>} onContinuar={() => { setErro(null); ir(2); }} />
    </div>
  );
}
