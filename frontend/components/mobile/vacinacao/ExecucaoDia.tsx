"use client";
// Abrir um dia ("Vacina · B19 · 25/12") no celular: baixa o pacote offline e
// guarda no aparelho; preparação com ciência nominal do que não foi conferido
// (enviada ao servidor, pela fila offline se preciso: POST /dias/{id}/ciencia);
// quem aplica (veterinários do cadastro ou texto livre, CRMV pedido); modo
// tronco ou grupo; incluir animais com consentimento; trocar produto/dose;
// carência desconhecida (administrador decide; os demais seguem "tanque · sem
// aceite", como o servidor faz); leitura de exame; fechar o dia.
// Cada registro vai para a fila do aparelho com chave de idempotência e é
// enviado em lote quando houver sinal (lib/filaSanitario.ts).
import { useEffect, useMemo, useState } from "react";
import { Hand, Plus, RefreshCw, Syringe, Users } from "lucide-react";
import { MobConfirmModal, MobGaveta, MobVoltar } from "@/components/mobile/ui";
import { LegendaOrigem } from "@/components/sanitario/comum";
import { decidirCarenciaDia, desfazerRegistros, fecharDia, mensagemDoErro, pacoteOffline } from "@/lib/apiSanitario";
import { enviarOuEnfileirar } from "@/lib/offline";
import {
  descartarDaFila, dispositivoUid, enfileirarRegistros, guardarAvisoOfflineHoras, lerResultados, marcarCampoAtivo, useFilaSanitario,
  type NovoRegistroSan,
} from "@/lib/filaSanitario";
import {
  alvosPendentes, chaveAC, chaveAnimal, corpoCiencia, dosePorPeso, horaAgora, itensPreparacao, produtoEfetivo,
  type AlvoDia, type RegistroCampo,
} from "@/lib/sanitarioCampo";
import {
  ROTULO_ESTADO_DIA, fmtData, fmtDataHora, hojeISO, novaChave, textoProduto, type PacoteOffline, type ProdutoIn,
} from "@/lib/sanitarioTipos";
import { AdicionarAnimais } from "./AdicionarAnimais";
import { ModoGrupo } from "./ModoGrupo";
import { ModoTronco, type AplicacaoTronco } from "./ModoTronco";
import { ResultadoExame } from "./ResultadoExame";
import { TrocarProduto } from "./TrocarProduto";
import {
  CarenciaCampo, EscolhaAplicador, FaixaSan, PainelFila, Rotulo, aplicadorEu, rotuloCrmv, camposAplicador, useComCopia, useEuCampo,
  type Aplicador,
} from "./comum";
import { useExecDia, type FeitoExec } from "./estadoExec";

export function chavePacote(diaId: number): string {
  return `san_pacote_${diaId}`;
}

export function ExecucaoDia({ diaId, onVoltar }: { diaId: number; onVoltar: () => void }) {
  const pac = useComCopia<PacoteOffline>(chavePacote(diaId), () => pacoteOffline(diaId));
  const pacote = pac.dados;
  const eu = useEuCampo();
  const [exec, setExec] = useExecDia(diaId);
  const fila = useFilaSanitario();
  const filaIds = useMemo(() => new Set(fila.itens.map((i) => i.id)), [fila.itens]);
  const [adicionar, setAdicionar] = useState(false);
  const [trocar, setTrocar] = useState<number | null>(null);
  const [carenciaDe, setCarenciaDe] = useState<number | null>(null);
  const [fechar, setFechar] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [trocandoAplicador, setTrocandoAplicador] = useState(false);

  useEffect(() => {
    if (pacote?.regras_aviso?.aviso_offline_horas) guardarAvisoOfflineHoras(pacote.regras_aviso.aviso_offline_horas);
    marcarCampoAtivo();
  }, [pacote]);

  const caixas = useMemo(() => new Map((pacote?.caixas || []).map((c) => [c.caixa_id, c])), [pacote]);
  const feitosSet = useMemo(() => exec.feitos.map((f) => chaveAC(f.animal, f.caixa_id)), [exec.feitos]);
  const alvos = useMemo(() => (pacote ? alvosPendentes(pacote, exec.extras, feitosSet, Object.keys(exec.naoAplicar)) : []),
    [pacote, exec.extras, feitosSet, exec.naoAplicar]);

  if (!pacote) {
    return (
      <div>
        <MobVoltar titulo="Vacinação" onVoltar={onVoltar} />
        {pac.carregando ? <p className="mob-san-txt">Baixando o dia para o celular…</p> : (
          <FaixaSan tipo="alerta">Este dia ainda não foi baixado neste celular. Abra com sinal uma vez para guardar o pacote e trabalhar sem sinal.
            <button type="button" className="mob-btn-2" style={{ marginTop: "0.5rem" }} onClick={pac.recarregar}>Tentar de novo</button>
          </FaixaSan>
        )}
      </div>
    );
  }

  const dia = pacote.dia;
  const hoje = hojeISO();
  const pedeCrmv = pacote.caixas.some((c) => (c.regras as { legal_crmv_pedir?: boolean }).legal_crmv_pedir);
  const vets = pacote.veterinarios || [];
  const admin = !!eu?.administrador;
  const prep = itensPreparacao(pacote);

  // ── carência sem decisão (por caixa do dia, considerando a troca de produto) ──
  const carenciaPendente = pacote.caixas.filter((c) => {
    if (c.tipo === "exame") return false;
    if (exec.carencia[String(c.caixa_id)]) return false;
    const troca = exec.trocas[String(c.caixa_id)];
    const dc = dia.caixas.find((x) => x.caixa_id === c.caixa_id);
    if (dc?.carencia_decisao?.modo && !troca) return false;
    const r = c.regras as { carencia_precisa_decisao?: string | null };
    return !!r.carencia_precisa_decisao || (troca && troca.modo !== "estoque" && troca.modo !== "vazio");
  });

  async function registrar(itens: { alvo: AlvoDia; caixas: number[]; peso?: AplicacaoTronco["peso"]; resultados?: AplicacaoTronco["resultados"] }[]) {
    if (!pacote) return;
    const grupo = novaChave("g");
    const novos: NovoRegistroSan[] = [];
    const feitos: FeitoExec[] = [];
    const carenciaUsada = new Set<string>();
    const data = hojeISO();
    const hora = horaAgora();
    const em = new Date().toISOString();
    for (const it of itens) {
      for (const c of it.caixas) {
        const cx = caixas.get(c);
        const troca: ProdutoIn | undefined = exec.trocas[String(c)];
        const prod = produtoEfetivo(cx?.produto, troca);
        const car = exec.carencia[String(c)];
        const leitura = it.resultados?.[c];
        const chave = novaChave("app");
        const registro: RegistroCampo = {
          chave_idempotencia: chave, dia_id: diaId, caixa_id: c, data, hora,
          ...(it.alvo.animal_id != null ? { animal_id: it.alvo.animal_id } : { numero_animal: it.alvo.numero }),
          ...(troca ? { produto: troca } : {}),
          // Peso estimado NÃO vai: o servidor estima pela categoria e marca "estimado".
          peso_kg: cx?.tipo !== "exame" && dosePorPeso(prod) && it.peso && !it.peso.estimado ? it.peso.valor : null,
          ...camposAplicador(exec.aplicador),
          ...(leitura ? { resultado: leitura.resultado, resultado_valor: leitura.valor } : {}),
          consentimento: it.alvo.consent[String(c)] ?? null,
          ...(car?.enviar && !carenciaUsada.has(String(c)) ? { carencia: { modo: car.modo, leite_dias: car.leite_dias, carne_dias: car.carne_dias } } : {}),
        };
        if (car?.enviar) carenciaUsada.add(String(c));
        novos.push({ registro, numero: it.alvo.numero, caixa: cx?.nome_curto || cx?.nome || `#${c}`, dia_nome: dia.nome });
        feitos.push({ chave, animal: it.alvo.animal, numero: it.alvo.numero, caixa_id: c, em, grupo, caixa: cx?.nome_curto || "" });
      }
    }
    await enfileirarRegistros(novos);
    setExec((e) => ({
      ...e, feitos: [...e.feitos, ...feitos].slice(-500),
      carencia: Object.fromEntries(Object.entries(e.carencia).map(([k, v]) => [k, carenciaUsada.has(k) ? { ...v, enviar: false } : v])),
    }));
  }

  async function desfazer(chaveGrupo: string): Promise<string | null> {
    const [g, numero] = [chaveGrupo.slice(0, chaveGrupo.lastIndexOf("|")), chaveGrupo.slice(chaveGrupo.lastIndexOf("|") + 1)];
    const lista = exec.feitos.filter((f) => f.grupo === g && f.numero === numero);
    const naFila = lista.filter((f) => filaIds.has(f.chave));
    if (naFila.length) await descartarDaFila(naFila.map((f) => f.chave));
    const enviados = lista.filter((f) => !filaIds.has(f.chave));
    const resultados = lerResultados();
    const ids = enviados.map((f) => resultados.find((r) => r.chave === f.chave)?.registro_id).filter((x): x is number => typeof x === "number");
    const desfeitas = new Set(naFila.map((f) => f.chave));
    let aviso: string | null = null;
    if (ids.length) {
      try {
        const r = await desfazerRegistros(ids) as { desfeitos?: number[]; recusados?: { registro_id: number; motivo: string }[] };
        const ok = new Set(r.desfeitos || []);
        for (const f of enviados) {
          const rid = resultados.find((x) => x.chave === f.chave)?.registro_id;
          if (rid && ok.has(rid)) desfeitas.add(f.chave);
        }
        if (r.recusados?.length) aviso = `Não deu para desfazer: ${r.recusados[0].motivo}.`;
      } catch (e) {
        aviso = mensagemDoErro(e, "Sem sinal para desfazer o que já foi enviado.");
      }
    } else if (enviados.length) {
      aviso = "Já foi enviado e o servidor ainda não confirmou. Tente de novo em instantes.";
    }
    setExec((e) => ({ ...e, feitos: e.feitos.filter((f) => !desfeitas.has(f.chave)) }));
    return aviso ?? (desfeitas.size ? `${numero}: registro desfeito.` : null);
  }

  // ── cabeçalho comum ──
  const cabecalho = (
    <>
      <MobVoltar titulo={dia.nome} subtitulo={`${dia.data === hoje ? "Hoje" : fmtData(dia.data)}${dia.hora ? ` às ${dia.hora}` : ""} · ${ROTULO_ESTADO_DIA[dia.estado] || dia.estado}`}
        onVoltar={onVoltar} />
      <p className="mob-san-txt" style={{ marginTop: "-0.5rem", marginBottom: "0.6rem", display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <span>{pac.doCache ? "Sem sinal: usando o dia guardado neste celular" : "Dia guardado neste celular"} ({fmtDataHora(pacote.gerado_em)}).</span>
        <button type="button" className="mob-btn-2" style={{ width: "auto", minHeight: 48, padding: "0 0.9rem" }} onClick={pac.recarregar}>
          <RefreshCw size={16} aria-hidden="true" /> Atualizar
        </button>
      </p>
      {dia.data > hoje && <FaixaSan tipo="atencao">Este dia está marcado para {fmtData(dia.data)}. Registrar hoje grava a data de hoje.</FaixaSan>}
      {dia.estado === "fechado" && <FaixaSan tipo="atencao">Dia fechado: o que for registrado entra como “lançado após o fechamento”.</FaixaSan>}
      {dia.estado === "cancelado" && <FaixaSan tipo="alerta">Dia cancelado{dia.motivo_cancelamento ? `: ${dia.motivo_cancelamento}` : ""}. Os registros serão recusados.</FaixaSan>}
    </>
  );

  // ── 1. preparação ──
  if (!exec.preparacao.concluida) {
    return <Preparacao cabecalho={cabecalho} itens={prep} marcados={exec.preparacao.marcados}
      onMarcar={(m) => setExec((e) => ({ ...e, preparacao: { ...e.preparacao, marcados: m } }))}
      onConcluir={(ciencia) => {
        setExec((e) => ({ ...e, preparacao: { ...e.preparacao, ciencia, concluida: true } }));
        // A ciência nominal vai para o servidor (sanitario_log) — sem sinal,
        // entra na fila offline do app e segue sozinha depois.
        if (ciencia) enviarOuEnfileirar(`/sanitario/dias/${diaId}/ciencia`, corpoCiencia(ciencia, dispositivoUid()),
          `Ciência da preparação · ${dia.nome || "dia"}`).catch((e) => setMsg(mensagemDoErro(e, "Ciência não enviada.")));
      }} />;
  }

  // ── 2. quem aplica ──
  if (!exec.aplicador || trocandoAplicador) {
    return (
      <AplicadorPasso cabecalho={cabecalho} vets={vets} pedeCrmv={pedeCrmv} inicial={exec.aplicador}
        onConfirmar={(a) => { setExec((e) => ({ ...e, aplicador: a })); setTrocandoAplicador(false); }} />
    );
  }

  // ── 3. modo ──
  if (!exec.modo) {
    return (
      <div>
        {cabecalho}
        <Rotulo>Como vai aplicar?</Rotulo>
        <div className="mob-san-chips">
          <button type="button" className="mob-san-chip" style={{ minHeight: 88 }} onClick={() => setExec((e) => ({ ...e, modo: "tronco" }))}>
            <span>Tronco<small>Um animal por vez, no brete.</small></span><Syringe size={24} aria-hidden="true" />
          </button>
          <button type="button" className="mob-san-chip" style={{ minHeight: 88 }} onClick={() => setExec((e) => ({ ...e, modo: "grupo" }))}>
            <span>Grupo<small>Confirma todos de uma vez. Dá para incluir animais na hora.</small></span><Users size={24} aria-hidden="true" />
          </button>
        </div>
      </div>
    );
  }

  // ── 4. execução ──
  const naoAplicados = Object.entries(exec.naoAplicar);
  const jaNoDia = new Set(alvos.filter((a) => pacote.caixas.every((c) => a.caixas.includes(c.caixa_id))).map((a) => a.animal));
  const filaDoDia = fila.itens.filter((i) => i.corpo.registro.dia_id === diaId).length;
  return (
    <div>
      {cabecalho}
      <div className="mob-san-dupla" style={{ marginTop: 0 }} role="group" aria-label="Modo">
        <button type="button" className="mob-san-chip" aria-pressed={exec.modo === "tronco"} onClick={() => setExec((e) => ({ ...e, modo: "tronco" }))}>Tronco</button>
        <button type="button" className="mob-san-chip" aria-pressed={exec.modo === "grupo"} onClick={() => setExec((e) => ({ ...e, modo: "grupo" }))}>Grupo</button>
      </div>
      <p className="mob-san-txt" style={{ margin: "0.6rem 0" }}>
        Aplicando: <b>{exec.aplicador.nome || "—"}</b>{exec.aplicador.crmv ? ` · ${rotuloCrmv(exec.aplicador.crmv)}` : ""}{" "}
        <button type="button" className="mob-btn-2" style={{ width: "auto", minHeight: 48, padding: "0 0.9rem", display: "inline-flex" }}
          onClick={() => setTrocandoAplicador(true)}>Trocar</button>
      </p>

      {carenciaPendente.map((c) => (
        admin ? (
          <FaixaSan key={c.caixa_id} tipo="atencao">
            <b>Carência de {c.nome_curto} sem decisão.</b> {String((c.regras as { carencia_precisa_decisao?: string }).carencia_precisa_decisao || "Produto trocado: carência desconhecida.")}
            <button type="button" className="mob-btn" style={{ marginTop: "0.5rem" }} onClick={() => setCarenciaDe(c.caixa_id)}>Decidir o leite</button>
          </FaixaSan>
        ) : (
          <FaixaSan key={c.caixa_id} tipo="atencao">
            <b>Carência de {c.nome_curto} sem aceite:</b> o leite segue para o tanque e fica no registro até o administrador decidir.
          </FaixaSan>
        )
      ))}

      {exec.modo === "tronco" ? (
        <ModoTronco pacote={pacote} alvos={alvos} exec={exec} eu={eu} filaIds={filaIds}
          onAplicar={(a) => registrar([a])}
          onNaoAplicar={(alvo, motivo) => setExec((e) => ({ ...e, naoAplicar: { ...e.naoAplicar, [alvo.animal]: { numero: alvo.numero, motivo, em: new Date().toISOString() } } }))}
          onTrocar={(c) => setTrocar(c)} onDesfazer={desfazer} />
      ) : (
        <ModoGrupo pacote={pacote} alvos={alvos} exec={exec} filaIds={filaIds}
          onAplicar={(lista) => registrar(lista.map((alvo) => ({ alvo, caixas: alvo.caixas })))} onDesfazer={desfazer} />
      )}

      <button type="button" className="mob-btn-2" style={{ marginTop: "0.9rem" }} onClick={() => setAdicionar(true)}>
        <Plus size={18} aria-hidden="true" /> Adicionar animais
      </button>
      {exec.modo === "grupo" && (
        <div className="mob-san-chips" style={{ marginTop: "0.5rem" }}>
          {pacote.caixas.filter((c) => c.tipo !== "exame").map((c) => (
            <button key={c.caixa_id} type="button" className="mob-san-chip" onClick={() => setTrocar(c.caixa_id)}>
              <span>Produto de {c.nome_curto}<small>{textoProduto(produtoEfetivo(c.produto, exec.trocas[String(c.caixa_id)]),
                pacote.estoques.find((x) => x.id === produtoEfetivo(c.produto, exec.trocas[String(c.caixa_id)]).estoque_id)?.nome)}</small></span>
            </button>
          ))}
        </div>
      )}
      <div style={{ marginTop: "0.8rem" }}><LegendaOrigem /></div>

      {naoAplicados.length > 0 && (
        <>
          <Rotulo>Não aplicados ({naoAplicados.length})</Rotulo>
          {naoAplicados.map(([k, v]) => (
            <div key={k} className="mob-san-linha" data-estado="atencao" style={{ cursor: "default" }}>
              <span style={{ flex: 1 }}><b>{v.numero}</b><span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>{v.motivo || "sem motivo"}</span></span>
              <button type="button" className="mob-btn-2" style={{ width: "auto", minHeight: 48, padding: "0 0.8rem" }}
                onClick={() => setExec((e) => { const n = { ...e.naoAplicar }; delete n[k]; return { ...e, naoAplicar: n }; })}>Voltar à fila</button>
            </div>
          ))}
        </>
      )}

      <div style={{ marginTop: "1rem" }}><PainelFila diaId={diaId} eu={eu} /></div>
      <ResultadoExame pacote={pacote} eu={eu} />

      {dia.estado !== "fechado" && dia.estado !== "cancelado" && (
        <button type="button" className="mob-btn-2" style={{ marginTop: "1rem" }} onClick={() => setFechar(true)}>Fechar o dia</button>
      )}
      {msg && <FaixaSan tipo="info">{msg}</FaixaSan>}

      <MobGaveta aberto={adicionar} titulo="Adicionar animais" onFechar={() => setAdicionar(false)}>
        <AdicionarAnimais pacote={pacote} jaNoDia={jaNoDia} onVoltar={() => setAdicionar(false)}
          onConfirmar={(extras) => {
            setExec((e) => ({ ...e, extras: [...e.extras, ...extras],
              naoAplicar: Object.fromEntries(Object.entries(e.naoAplicar).filter(([k]) => !extras.some((x) => chaveAnimal(x.animal_id, x.numero) === k))) }));
            setAdicionar(false);
            setMsg(`${extras.length} ${extras.length > 1 ? "animais incluídos" : "animal incluído"} no curral.`);
          }} />
      </MobGaveta>
      <MobGaveta aberto={trocar != null} titulo={`Produto de ${caixas.get(trocar ?? -1)?.nome_curto ?? ""}`} onFechar={() => setTrocar(null)}>
        {trocar != null && (
          <TrocarProduto titulo="Vale para os próximos animais deste dia, neste celular." atual={exec.trocas[String(trocar)] ?? null}
            padraoTexto={textoProduto(caixas.get(trocar)?.produto as ProdutoIn, pacote.estoques.find((x) => x.id === (caixas.get(trocar)?.produto as ProdutoIn)?.estoque_id)?.nome)}
            estoquesPacote={pacote.estoques} onVoltar={() => setTrocar(null)}
            onAplicar={(p) => {
              const c = trocar;
              setExec((e) => { const t = { ...e.trocas }; if (p) t[String(c)] = p; else delete t[String(c)]; return { ...e, trocas: t }; });
              setTrocar(null);
              if (p && p.modo !== "estoque" && p.modo !== "vazio" && admin) setCarenciaDe(c);
            }} />
        )}
      </MobGaveta>
      <MobGaveta aberto={carenciaDe != null} titulo="Carência" onFechar={() => setCarenciaDe(null)}>
        {carenciaDe != null && (
          <CarenciaCampo nome={caixas.get(carenciaDe)?.nome_curto || ""}
            motivo={(caixas.get(carenciaDe)?.regras as { carencia_precisa_decisao?: string | null })?.carencia_precisa_decisao}
            sugestao={{ leite_dias: (caixas.get(carenciaDe)?.regras as { car_leite_dias?: number | null })?.car_leite_dias ?? null,
              carne_dias: (caixas.get(carenciaDe)?.regras as { car_carne_dias?: number | null })?.car_carne_dias ?? null }}
            onVoltar={() => setCarenciaDe(null)}
            onDecidir={async (d) => {
              const c = carenciaDe;
              setCarenciaDe(null);
              let enviar = true;
              // Com sinal e sem troca de produto, a decisão vai já para o dia; sem
              // sinal, segue no primeiro registro desta vacina (o servidor grava o aceite).
              if (!exec.trocas[String(c)]) {
                try { await decidirCarenciaDia(diaId, c, d.modo, d.leite_dias, d.carne_dias); enviar = false; } catch { enviar = true; }
              }
              setExec((e) => ({ ...e, carencia: { ...e.carencia, [String(c)]: { ...d, enviar } } }));
            }} />
        )}
      </MobGaveta>
      {fechar && (
        <MobConfirmModal titulo="Fechar o dia?" textoConfirmar="Fechar" onCancelar={() => setFechar(false)}
          onConfirmar={async () => {
            setFechar(false);
            try {
              await fecharDia(diaId, "voltar");
              setMsg("Dia fechado. Quem faltou voltou para a caixa.");
              pac.recarregar();
            } catch (e) { setMsg(mensagemDoErro(e, "Precisa de sinal para fechar o dia.")); }
          }}>
          {filaDoDia > 0 ? `Ainda há ${filaDoDia} registro(s) deste dia no celular; o que chegar depois entra como “lançado após o fechamento”. ` : ""}
          Quem não foi aplicado volta para a caixa.
        </MobConfirmModal>
      )}
    </div>
  );
}

function Preparacao({ cabecalho, itens, marcados, onMarcar, onConcluir }: {
  cabecalho: React.ReactNode; itens: { id: string; texto: string; detalhe?: string | null }[]; marcados: string[];
  onMarcar: (m: string[]) => void; onConcluir: (ciencia: { nome: string; em: string; itens: string[] } | null) => void;
}) {
  const [nome, setNome] = useState(() => aplicadorEu().nome);
  const [ciente, setCiente] = useState(false);
  const set = new Set(marcados);
  const faltam = itens.filter((i) => !set.has(i.id));
  return (
    <div>
      {cabecalho}
      <Rotulo>Preparação antes do curral</Rotulo>
      {itens.map((i) => (
        <label key={i.id} className="mob-san-linha" data-estado={set.has(i.id) ? "ok" : undefined}>
          <input type="checkbox" checked={set.has(i.id)} onChange={() => onMarcar(set.has(i.id) ? marcados.filter((x) => x !== i.id) : [...marcados, i.id])} />
          <span><b>{i.texto}</b>{i.detalhe && <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>{i.detalhe}</span>}</span>
        </label>
      ))}
      {faltam.length > 0 ? (
        <div className="mob-card" style={{ padding: "0.9rem", marginTop: "0.6rem" }}>
          <b>{faltam.length} {faltam.length > 1 ? "itens não conferidos" : "item não conferido"}.</b>
          <p className="mob-san-txt">Para começar assim, registre a ciência com o seu nome.</p>
          <input className="mob-input" style={{ marginTop: "0.5rem" }} value={nome} onChange={(e) => setNome(e.target.value)} aria-label="Seu nome" />
          <label className="mob-san-linha" style={{ marginTop: "0.5rem" }}>
            <input type="checkbox" checked={ciente} onChange={(e) => setCiente(e.target.checked)} />
            <span>Estou ciente de que estes itens não foram conferidos.</span>
          </label>
          <button type="button" className="mob-btn" disabled={!ciente || !nome.trim()}
            onClick={() => onConcluir({ nome: nome.trim(), em: new Date().toISOString(), itens: faltam.map((f) => f.texto) })}>
            <Hand size={18} aria-hidden="true" /> Ciente, começar
          </button>
        </div>
      ) : (
        <button type="button" className="mob-btn" style={{ marginTop: "0.6rem" }} onClick={() => onConcluir(null)}>Tudo conferido, começar</button>
      )}
    </div>
  );
}

function AplicadorPasso({ cabecalho, vets, pedeCrmv, inicial, onConfirmar }: {
  cabecalho: React.ReactNode; vets: { pessoa_id: number; nome: string; crmv: string | null }[]; pedeCrmv: boolean;
  inicial: Aplicador | null; onConfirmar: (a: Aplicador) => void;
}) {
  const [a, setA] = useState<Aplicador | null>(inicial);
  return (
    <div>
      {cabecalho}
      <Rotulo>Quem está aplicando</Rotulo>
      <EscolhaAplicador valor={a} onChange={setA} vets={vets} pedeCrmv={pedeCrmv} />
      <button type="button" className="mob-btn" style={{ marginTop: "0.9rem" }} disabled={!a || (a.tipo === "texto" && !a.nome.trim())}
        onClick={() => a && onConfirmar(a)}>Continuar</button>
    </div>
  );
}
