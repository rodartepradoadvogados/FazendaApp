"use client";
// Lançar › Protocolos › IATF e Reprodutivo › Protocolo IATF (as duas portas abrem este mesmo componente) — em LOTE, em
// dois passos: (1) quem entra no protocolo (ver QuemServico) e (2) a data do D0 com a linha do tempo D0/D7/D9/D11 sempre
// à vista. Um único POST /reproducao/protocolo-iatf com todas as vacas: o servidor valida a aptidão do lote INTEIRO
// antes de gravar (tudo ou nada). Se recusar, a tela diz qual(is) vaca(s) e por quê, e oferece tirar essas e lançar o
// resto ou, se o bloqueio admitir, confirmar. As etapas seguintes (D7/D9/D11) entram na Agenda pelo servidor.
import { useRef, useState } from "react";
import Link from "next/link";
import { CalendarDays } from "lucide-react";
import { ErroApi } from "@/lib/api";
import { enviarOuEnfileirar, useConectividadeReal } from "@/lib/offline";
import {
  dataCurta, dataPorExtenso, etapasComData, lerRecusaAptidao, plural, resumoOrigem, somarDiasIso,
  type AnimalDaLista, type RecusaAptidao,
} from "@/lib/lancamentoLote";
import { hoje } from "../comum";
import { AvisoLote, NotaLote, PassoIndicador, RotuloLote } from "./SelecaoLote";
import { BarraAcao } from "./BarraLote";
import { ResumoLote } from "./ResumoLote";
import { AcoesFim, LinhaQuadro, QuadroLote, ResultadoCabecalho } from "./ResultadoLote";
import { focarAoMontar, usePassos, vibrar } from "./hooks";
import { QuemServico, useQuemServico } from "./QuemServico";

type Resultado =
  | { tipo: "ok" | "offline"; n: number; d0: string; nConf: number; fora: string[] }
  | { tipo: "recusa"; recusa: RecusaAptidao; numeros: string[] };

export function ProtocoloIatf({ animais, animalFixado }: { animais: readonly AnimalDaLista[]; animalFixado: string | null }) {
  const online = useConectividadeReal();
  // O animal da ficha entra marcado (a pessoa acabou de escolhê-lo); o resto começa vazio.
  const q = useQuemServico({ modo: "iatf", animais, chave: "lote_iatf", obrigatorios: animalFixado ? [animalFixado] : [] });
  const { passo, volta, ir } = usePassos<1 | 2 | 3>(1);
  const [dataD0, setDataD0] = useState(hoje());
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  // Vacas que a pessoa tirou do lote depois de uma recusa ("ficou de fora" no resultado).
  const [foraDoLote, setForaDoLote] = useState<string[]>([]);
  const trava = useRef(false);

  const marcadas = q.marcadas;
  const n = marcadas.length;
  const nomesCards = q.cardsComAnimais.filter((c) => q.cardsSel.has(c.id)).map((c) => c.nome);
  const etapas = etapasComData(dataD0);
  const jaInseminadas = marcadas.filter((c) => c.estado === "inseminada").length;
  const nConfirmadas = q.confirmadas.length;

  // `aceitos` = vacas que a pessoa acabou de confirmar na tela de recusa (além das que já confirmou no Passo 1).
  async function lancar(numeros: string[], aceitos: string[], fora: string[], retirar: string[] = []) {
    if (trava.current || !numeros.length) return;
    if (!dataD0) { setErro("Informe a data do D0."); return; }
    trava.current = true;
    setEnviando(true);
    setErro(null);
    const confirmadas = new Set([...numeros.filter((x) => q.confirmadasSet.has(x)), ...aceitos]);
    try {
      const { enviado } = await enviarOuEnfileirar(
        "/reproducao/protocolo-iatf",
        // `forcar` vale para o lote inteiro (o servidor valida tudo ou nada); só vai quando alguém foi confirmado.
        { animais: numeros, data_d0: dataD0, forcar: confirmadas.size > 0 ? true : undefined },
        `Protocolo IATF D0 — ${numeros.length} ${plural(numeros.length, "vaca", "vacas")}`,
      );
      // Só agora, com o envio aceito, saem da seleção — as que a pessoa tirou depois de uma recusa também. Se falhar,
      // ninguém some ao "Voltar e revisar".
      q.removerDaSelecao([...numeros, ...retirar]);
      q.ocultar(numeros);
      setForaDoLote(fora);
      setResultado({ tipo: enviado ? "ok" : "offline", n: numeros.length, d0: dataD0, nConf: confirmadas.size, fora });
      vibrar(enviado ? 20 : [15, 60, 15]);
      if (enviado) q.recarregar();
      ir(3);
    } catch (e) {
      // 409 de aptidão: o servidor recusou o lote inteiro. Em vez da frase genérica, mostra quem e por quê.
      const recusa = e instanceof ErroApi ? lerRecusaAptidao(e.status, e.detalhe, e.message) : null;
      if (recusa) {
        setResultado({ tipo: "recusa", recusa, numeros });
        vibrar([25, 60, 25, 60, 25]);
        ir(3);
      } else {
        setErro(e instanceof Error ? e.message : "Erro ao lançar o protocolo.");
        vibrar([25, 60, 25, 60, 25]);
      }
    } finally {
      trava.current = false;
      setEnviando(false);
    }
  }

  function nova() {
    setResultado(null); setForaDoLote([]); setErro(null); setDataD0(hoje());
    ir(1, true);
  }

  const classeView = `lote lote-view${volta ? " volta" : ""}`;

  // ───────────────────────── Passo 3: resultado ─────────────────────────
  if (passo === 3 && resultado) {
    if (resultado.tipo === "recusa") {
      const { recusa, numeros } = resultado;
      // Quem o servidor apontou; se não disse, o problema vale para o lote todo.
      const problemas = recusa.animais.filter((x) => numeros.includes(x));
      const resto = numeros.filter((x) => !problemas.includes(x));
      const podeTirar = problemas.length > 0 && resto.length > 0;
      return (
        <div key="p3r" ref={focarAoMontar} tabIndex={-1} inert={enviando || undefined} className={classeView}>
          <ResultadoCabecalho tipo="erro" titulo="Nenhuma vaca foi lançada" texto="O servidor recusa o lote inteiro se uma vaca não estiver apta." />
          {/* O texto do servidor costuma já citar a matriz; só se acrescenta o brinco quando ele não aparece na frase. */}
          <AvisoLote tipo="erro">{problemas.length > 0 && !problemas.every((x) => recusa.mensagem.includes(x)) && <><b>{problemas.join(", ")}</b>: </>}{recusa.mensagem}</AvisoLote>
          <AcoesFim>
            {podeTirar && (
              <button type="button" className="lote-cta" disabled={enviando}
                onClick={() => lancar(resto, [], [...foraDoLote, ...problemas], problemas)}>
                {enviando ? "Enviando…" : `Tirar ${problemas.join(", ")} e lançar ${resto.length}`}
              </button>
            )}
            {recusa.confirmavel && (
              <button type="button" className="lote-cta risco" disabled={enviando} onClick={() => lancar(numeros, problemas.length ? problemas : numeros, foraDoLote)}>
                {enviando ? "Enviando…" : `Confirmar${problemas.length ? ` ${problemas.join(", ")}` : ""} e lançar ${numeros.length}`}
              </button>
            )}
            <button type="button" className="lote-cta ghost" onClick={() => ir(1, true)}>Voltar e revisar</button>
          </AcoesFim>
          {erro && <AvisoLote tipo="erro">{erro}</AvisoLote>}
        </div>
      );
    }
    const r = resultado;
    const d0etapas = etapasComData(r.d0);
    const d7 = d0etapas.find((e) => e.dia === 7);
    return (
      <div key="p3" ref={focarAoMontar} tabIndex={-1} className={classeView}>
        {r.tipo === "ok" ? (
          <ResultadoCabecalho tipo="ok" titulo={`${r.n} ${plural(r.n, "vaca", "vacas")} no protocolo`}
            texto={`D7 em ${d7?.dataCurta ?? dataCurta(somarDiasIso(r.d0, 7))} entra na Agenda.${r.nConf ? ` ${r.nConf} com confirmação sua.` : ""}${r.fora.length ? ` ${r.fora.join(", ")} ${plural(r.fora.length, "ficou", "ficaram")} de fora.` : ""}`} />
        ) : (
          <ResultadoCabecalho tipo="offline" titulo={`Protocolo guardado (${r.n} ${plural(r.n, "vaca", "vacas")})`}
            texto="Sem internet — guardado, será enviado ao conectar. As etapas entram na Agenda depois." />
        )}
        {r.tipo === "offline" && (
          <AvisoLote tipo="atencao">Se o servidor recusar alguma vaca ao conectar, nada é lançado: o item fica em <b>Menu › Sincronização</b>, com o motivo.</AvisoLote>
        )}
        <QuadroLote previsto={r.tipo === "offline"} rotulo="Etapas do protocolo">
          {d0etapas.map((e) => (
            <LinhaQuadro key={e.dia} nome={e.dia === 11 ? "D11 · inseminação" : `D${e.dia}`} apoio={e.hormonios}>{e.dataCurta}</LinhaQuadro>
          ))}
        </QuadroLote>
        <AcoesFim>
          <button type="button" className="lote-cta" onClick={nova}>Novo protocolo</button>
          <Link href="/app" className="lote-cta sec" style={{ textDecoration: "none" }}>Ver agenda</Link>
        </AcoesFim>
      </div>
    );
  }

  // ───────────────────────── Passo 2: o protocolo ─────────────────────────
  if (passo === 2) {
    const ehHoje = dataD0 === hoje();
    return (
      <div key="p2" ref={focarAoMontar} tabIndex={-1} inert={enviando || undefined} className={classeView}>
        <PassoIndicador passo={2}>o <b>protocolo</b></PassoIndicador>
        <ResumoLote titulo={`${n} ${plural(n, "vaca", "vacas")}`} sub={resumoOrigem(q.origem, q.lotesSel, nomesCards)} onAlterar={() => ir(1, true)} />

        <RotuloLote>Data do D0</RotuloLote>
        <input type="date" className="mob-input" value={dataD0} onChange={(e) => setDataD0(e.target.value || dataD0)} aria-label="Data do D0" />
        <p className="lote-nota" style={{ marginTop: "0.35rem" }}>{dataPorExtenso(dataD0)}</p>

        <RotuloLote>Protocolo padrão da fazenda</RotuloLote>
        <ol className="lote-tl">
          {etapas.map((e) => (
            <li key={e.dia} className={e.dia === 0 ? "hoje" : e.dia === 11 ? "fim" : undefined}>
              <span className="d" aria-hidden="true">D{e.dia}</span>
              <div className="dt"><b>{e.dia === 11 ? "Inseminação" : `Etapa D${e.dia}`}</b><span>{e.dataCurta}</span></div>
              <div className="hm">{e.hormonios}</div>
              <div className="ag">{e.dia === 0 ? (ehHoje ? "Aplicando agora" : "Primeiro dia") : e.dia === 11 ? "Entra na Agenda · inseminação lançada à parte" : "Entra na Agenda"}</div>
            </li>
          ))}
        </ol>
        <NotaLote>Isso só agenda o protocolo hormonal. A inseminação (D11) é lançada à parte, em Reprodutivo › Inseminação.</NotaLote>

        {jaInseminadas > 0 && (
          <AvisoLote tipo="info"><b>{jaInseminadas} {plural(jaInseminadas, "inseminada recente", "inseminadas recentes")}.</b> Entrar em protocolo troca o resultado da inseminação anterior para negativo.</AvisoLote>
        )}
        {nConfirmadas > 0 && (
          <AvisoLote tipo="atencao"><b>{nConfirmadas} {plural(nConfirmadas, "vaca confirmada por você", "vacas confirmadas por você")}</b> como gestante. O lote inteiro vai com essa confirmação.</AvisoLote>
        )}
        {!online && (
          <AvisoLote tipo="offline"><b>Sem internet.</b> O protocolo vai para a fila e é enviado inteiro ao conectar. Se o servidor recusar alguma vaca nessa hora, o item fica em Menu › Sincronização, com o motivo.</AvisoLote>
        )}
        {erro && <AvisoLote tipo="erro">{erro}</AvisoLote>}

        <BarraAcao>
          <button type="button" className="lote-cta" disabled={!n || enviando} onClick={() => lancar(marcadas.map((c) => c.numero), [], [])}>
            <CalendarDays size={22} strokeWidth={2.2} aria-hidden="true" /> {enviando ? "Enviando…" : `Lançar D0 (${n})`}
          </button>
        </BarraAcao>
      </div>
    );
  }

  // ───────────────────────── Passo 1: quem ─────────────────────────
  return (
    <div key="p1" ref={focarAoMontar} tabIndex={-1} className={classeView}>
      <QuemServico q={q} quando={<><b>quem</b> entra no protocolo</>} onContinuar={() => { setErro(null); ir(2); }} />
    </div>
  );
}
