"use client";
// Sub-tela ALIMENTAÇÃO do app de campo — o FORNECIMENTO (consumo) de um
// lote, alternando entre digitar o nº de animais (o backend já devolve a
// quantidade por cabeça — só multiplica) e digitar os quilos direto. Quando a
// fazenda lança o consumo por trato (Parâmetros > Alimentação), cada
// lançamento diz de qual trato da dieta é. A SOBRA do cocho saiu daqui
// (21/10/2026): é lançada à parte, em Lançar > Sobra do cocho
// (FormSobraCocho.tsx), porque se refere a um ciclo de 24h e não ao dia.
// Mesma regra de negócio da tela do site (specs/sessao-3-consumo-e-sobra.md,
// Frente D): só os alimentos da DIETA ATIVA do lote entram na lista — sem
// isso, não há o que lançar. Envio pela fila offline (enviarOuEnfileirar),
// nunca fetch direto — é o próprio celular no curral, sem garantia de sinal.
import { useEffect, useMemo, useState } from "react";
import { MobCampo, MobAviso, MobCard } from "@/components/mobile/ui";
import { enviarOuEnfileirar } from "@/lib/offline";
import {
  fetchLotes, fetchDietaDoLote, fetchConsumoDoDia,
  type ItemDietaDoLote, type ConsumoDoDia, type ConsumoItemIn, type DietaDoLote,
} from "@/lib/api";
import { useCache, useRascunho, hoje, BotoesEscolha, RascunhoAviso, type Aviso } from "./comum";

type Lote = { id: number; codigo: string; nome: string };
// Rascunho — nº de animais/kg por alimento são exatamente o tipo de dado que
// se perde numa interrupção (docs/agents/design-implementation.md §5,
// acabamento-de-campo.html). Data fica de fora (sempre volta a "hoje", não
// vale a pena persistir). `trato` só é usado quando a fazenda lança por trato.
type DraftAlimentacao = { loteSel: string; modoConsumo: "animais" | "kg"; numAnimais: string; qtdKg: Record<string, string>; trato?: string };

/** Vibração curta de confirmação — mesmo reforço tátil usado no resto do app
 * (comum.tsx tem a mesma função, mas não é exportada; duplicar 4 linhas é
 * mais simples do que reescrever o envio do consumo sobre `useEnvio`). */
function vibrar(padrao: number | number[]) {
  try {
    navigator.vibrate?.(padrao);
  } catch {
    // ignora — vibração é só reforço, nunca deve derrubar o envio.
  }
}

export function FormAlimentacao() {
  const lotes = useCache<Lote[]>("lotes", () => fetchLotes() as Promise<Lote[]>, []);
  const rascunho = useRascunho<DraftAlimentacao>("alimentacao", { loteSel: "", modoConsumo: "animais", numAnimais: "", qtdKg: {}, trato: "" });
  const { loteSel, modoConsumo, numAnimais, qtdKg } = rascunho.valor;
  const trato = rascunho.valor.trato ?? "";
  const atualizar = (patch: Partial<DraftAlimentacao>) => rascunho.setValor((atual) => ({ ...atual, ...patch }));
  const setLoteSel = (v: string) => atualizar({ loteSel: v }); // guarda o CÓDIGO (2 dígitos) do lote, igual ao select
  const setModoConsumo = (v: "animais" | "kg") => atualizar({ modoConsumo: v });
  const setNumAnimais = (v: string) => atualizar({ numAnimais: v });
  const setQtdKg = (v: Record<string, string> | ((atual: Record<string, string>) => Record<string, string>)) =>
    atualizar({ qtdKg: typeof v === "function" ? v(qtdKg) : v });
  const setTrato = (v: string) => atualizar({ trato: v });
  const [data, setData] = useState(hoje());

  // undefined = ainda carregando · null = carregou e não há dieta ativa
  const [dietaInfo, setDietaInfo] = useState<DietaDoLote | null | undefined>(undefined);
  const [consumoHoje, setConsumoHoje] = useState<ConsumoDoDia | null>(null);
  // Sobe a cada lançamento salvo com sucesso, só para forçar o refetch de
  // "já lançado hoje" abaixo — não há endpoint de invalidação de cache aqui.
  const [versao, setVersao] = useState(0);

  const [avisoConsumo, setAvisoConsumo] = useState<Aviso>(null);
  const [avisosEstoque, setAvisosEstoque] = useState<string[]>([]);
  const [enviandoConsumo, setEnviandoConsumo] = useState(false);

  const rotuloLote = (codigo: string) => {
    const lo = lotes.dados.find((x) => x.codigo === codigo);
    return lo ? `${lo.codigo} - ${lo.nome}` : `Lote ${codigo}`;
  };

  // Dieta ativa do lote escolhido — é ela, e só ela, que decide os alimentos
  // oferecidos (B3 da spec). Troca de lote limpa o que já estava digitado em
  // kg: os alimentos mudam, os valores antigos não fazem mais sentido.
  useEffect(() => {
    setDietaInfo(undefined);
    setQtdKg({});
    setTrato("");
    if (!loteSel) return;
    let vivo = true;
    fetchDietaDoLote(Number(loteSel))
      .then((r) => { if (vivo) setDietaInfo(r); })
      .catch(() => { if (vivo) setDietaInfo(null); });
    return () => { vivo = false; };
  }, [loteSel]);

  // O que já foi lançado hoje nesse lote (consumo somado + sobra do ciclo que
  // fecha hoje, se houver). Refeito ao trocar lote/data e após cada envio.
  useEffect(() => {
    if (!loteSel) { setConsumoHoje(null); return; }
    let vivo = true;
    fetchConsumoDoDia(Number(loteSel), data)
      .then((r) => { if (vivo) setConsumoHoje(r); })
      .catch(() => { if (vivo) setConsumoHoje(null); });
    return () => { vivo = false; };
  }, [loteSel, data, versao]);

  const lotesOrdenados = useMemo(
    () => [...lotes.dados].sort((a, b) => a.codigo.localeCompare(b.codigo, undefined, { numeric: true })),
    [lotes.dados],
  );
  const itens = dietaInfo?.itens ?? [];
  const numAnimaisNum = Number(numAnimais) || 0;
  // Parâmetro "lançar consumo por trato": cada fornecimento diz de qual trato
  // (1..N da dieta ativa). Desligado = lançamento do dia, como sempre.
  const porTrato = !!dietaInfo?.consumo_por_trato;
  const numTratos = dietaInfo?.num_tratos ?? 2;

  function itensParaEnviar(): ConsumoItemIn[] {
    if (modoConsumo === "animais") {
      // Backend já resolveu o por-cabeça (independe de base_quantidade ser
      // "total" ou "animal") — aqui é só multiplicar pelo nº de animais.
      return itens
        .filter((i) => i.por_cabeca != null)
        .map((i) => ({ alimento: i.alimento, alimento_id: i.alimento_id, quantidade: Math.round(i.por_cabeca! * numAnimaisNum * 100) / 100, unidade: i.unidade }));
    }
    return itens
      .filter((i) => Number(qtdKg[i.alimento]) > 0)
      .map((i) => ({ alimento: i.alimento, alimento_id: i.alimento_id, quantidade: Number(qtdKg[i.alimento]), unidade: i.unidade }));
  }

  async function salvarConsumo() {
    if (!loteSel) return setAvisoConsumo({ tipo: "erro", msg: "Selecione o lote." });
    if (!dietaInfo || itens.length === 0) return setAvisoConsumo({ tipo: "erro", msg: "Este lote não tem dieta ativa." });
    if (porTrato && !trato) return setAvisoConsumo({ tipo: "erro", msg: "Informe de qual trato é este fornecimento." });
    if (modoConsumo === "animais" && !(numAnimaisNum > 0)) return setAvisoConsumo({ tipo: "erro", msg: "Informe o número de animais." });
    const itensEnvio = itensParaEnviar();
    if (itensEnvio.length === 0) {
      return setAvisoConsumo({
        tipo: "erro",
        msg: modoConsumo === "animais" ? "Nenhum alimento da dieta calcula por cabeça — lance em kg." : "Informe a quantidade de ao menos um alimento.",
      });
    }
    setEnviandoConsumo(true);
    setAvisoConsumo(null);
    setAvisosEstoque([]);
    try {
      const corpo = {
        lote: Number(loteSel), data, num_animais: modoConsumo === "animais" ? numAnimaisNum : null, origem: modoConsumo, itens: itensEnvio,
        ...(porTrato ? { trato: Number(trato) } : {}),
      };
      const descricao = `Consumo — ${rotuloLote(loteSel)}: ${itensEnvio.length} alimento(s) (${data}${porTrato ? `, trato ${trato}` : ""})`;
      const { enviado, resposta } = await enviarOuEnfileirar("/alimentacao/consumo", corpo, descricao);
      setAvisoConsumo(enviado
        ? { tipo: "ok", msg: "Consumo lançado." }
        : { tipo: "offline", msg: "Sem internet — guardado, será enviado automaticamente ao conectar." });
      // Avisos de estoque (saldo negativo etc.) só existem quando o envio foi
      // de verdade na hora — em fila offline ainda não sabemos o resultado.
      if (enviado && Array.isArray(resposta?.avisos) && resposta.avisos.length > 0) setAvisosEstoque(resposta.avisos);
      vibrar(enviado ? 20 : [15, 60, 15]);
      if (modoConsumo === "kg") setQtdKg({});
      if (porTrato) setTrato("");
      if (enviado) setVersao((v) => v + 1);
    } catch (e) {
      setAvisoConsumo({ tipo: "erro", msg: e instanceof Error ? e.message : "Erro ao lançar consumo." });
      vibrar([25, 60, 25, 60, 25]);
    } finally {
      setEnviandoConsumo(false);
    }
  }

  if (lotes.pronto && lotes.dados.length === 0) {
    return <p style={{ color: "var(--mob-muted)", fontSize: "0.95rem", lineHeight: 1.5 }}>Nenhum lote cadastrado.</p>;
  }

  const corFaixa = consumoHoje?.dentro_da_faixa == null ? "var(--mob-muted)" : consumoHoje.dentro_da_faixa ? "var(--mob-verde)" : "var(--mob-vermelho)";

  return (
    <>
      <RascunhoAviso mostrar={rascunho.salvo} />
      <MobCampo label="Lote">
        <select className="mob-input" value={loteSel} onChange={(e) => setLoteSel(e.target.value)}>
          <option value="">Selecione o lote…</option>
          {lotesOrdenados.map((l) => <option key={l.codigo} value={l.codigo}>{l.codigo} - {l.nome}</option>)}
        </select>
      </MobCampo>
      <MobCampo label="Data">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>

      {loteSel && dietaInfo === undefined && (
        <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem" }}>Carregando dieta do lote…</p>
      )}
      {loteSel && dietaInfo === null && (
        <MobAviso tipo="erro">Este lote não tem dieta ativa no momento — cadastre a dieta no site antes de lançar o consumo.</MobAviso>
      )}
      {loteSel && dietaInfo && itens.length === 0 && (
        <MobAviso tipo="erro">A dieta ativa deste lote não tem alimentos cadastrados.</MobAviso>
      )}

      {loteSel && dietaInfo && itens.length > 0 && (
        <>
          {/* ── Já lançado hoje ─────────────────────────────────────────── */}
          <div className="mob-secao">Já lançado hoje</div>
          <MobCard style={{ marginBottom: "1rem" }}>
            {consumoHoje && consumoHoje.itens.length > 0 ? (
              <div style={{ display: "grid", gap: "0.4rem" }}>
                {consumoHoje.itens.map((i) => (
                  <div key={i.alimento} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem" }}>
                    <span>{i.alimento}</span>
                    <strong>{i.quantidade} {i.unidade}</strong>
                  </div>
                ))}
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", color: "var(--mob-muted)", marginTop: "0.2rem", paddingTop: "0.4rem", borderTop: "1px solid var(--mob-border)" }}>
                  <span>Total fornecido</span>
                  <span>{consumoHoje.kg_fornecido_total.toFixed(1)} kg</span>
                </div>
                {(consumoHoje.por_trato?.length ?? 0) > 0 && (
                  <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>
                    {consumoHoje.por_trato!.map((t) => `Trato ${t.trato}: ${t.kg.toFixed(1)} kg`).join(" · ")}
                    {(consumoHoje.kg_sem_trato ?? 0) > 0 && ` · sem trato: ${consumoHoje.kg_sem_trato!.toFixed(1)} kg`}
                  </div>
                )}
              </div>
            ) : (
              <span style={{ color: "var(--mob-muted)", fontSize: "0.9rem" }}>Nada lançado ainda hoje.</span>
            )}
            {consumoHoje?.sobra_pct != null && (
              <div style={{ marginTop: "0.6rem", fontSize: "0.85rem", fontWeight: 700, color: corFaixa }}>
                Sobra do ciclo que fecha hoje: {consumoHoje.sobra_pct.toFixed(1)}% {consumoHoje.dentro_da_faixa ? "— dentro da faixa" : "— fora da faixa"}
              </div>
            )}
          </MobCard>

          {/* ── Cartão 1: lançar consumo ─────────────────────────────────── */}
          <div className="mob-secao">Lançar consumo</div>
          <MobCard style={{ marginBottom: "1rem" }}>
            {porTrato && (
              <MobCampo label="De qual trato é este fornecimento?">
                <BotoesEscolha
                  opcoes={Array.from({ length: numTratos }, (_, i) => ({ valor: String(i + 1), label: `Trato ${i + 1}` }))}
                  valor={trato}
                  onChange={setTrato}
                />
              </MobCampo>
            )}
            <MobCampo label="Como informar a quantidade?">
              <BotoesEscolha
                opcoes={[{ valor: "animais", label: "Nº de animais" }, { valor: "kg", label: "Kg direto" }]}
                valor={modoConsumo}
                onChange={setModoConsumo}
              />
            </MobCampo>

            {modoConsumo === "animais" && (
              <MobCampo label="Número de animais">
                <input type="number" inputMode="numeric" className="mob-input" style={{ fontSize: "1.3rem", fontWeight: 700 }}
                  value={numAnimais} onChange={(e) => setNumAnimais(e.target.value)} placeholder="0" />
              </MobCampo>
            )}

            <div style={{ display: "grid", gap: "0.6rem", marginTop: "0.4rem" }}>
              {itens.map((item) => (
                <ItemConsumo key={item.alimento} item={item} modo={modoConsumo}
                  numAnimais={numAnimaisNum} valorKg={qtdKg[item.alimento] || ""}
                  onMudarKg={(v) => setQtdKg((s) => ({ ...s, [item.alimento]: v }))} />
              ))}
            </div>

            <button className="mob-btn" style={{ marginTop: "0.9rem" }} onClick={salvarConsumo} disabled={enviandoConsumo}>
              {enviandoConsumo ? "Salvando…" : "Lançar consumo"}
            </button>
            {avisoConsumo && <MobAviso tipo={avisoConsumo.tipo}>{avisoConsumo.msg}</MobAviso>}
            {avisosEstoque.map((a, idx) => <MobAviso key={idx} tipo="offline">{a}</MobAviso>)}
          </MobCard>

          <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)", lineHeight: 1.45 }}>
            A sobra do cocho é lançada à parte, em <strong>Lançar › Sobra do cocho</strong> — ela se refere a um ciclo de 24h
            (entre os tratos cadastrados na dieta), não só ao dia.
          </p>
        </>
      )}
    </>
  );
}

/** Uma linha por alimento da dieta — no modo "animais" mostra o valor já
 * calculado (só leitura); no modo "kg" é um campo numérico. Alimento que não
 * converte para kg (litro, dose, unidade) ganha um aviso curto: ele fica de
 * fora do rateio da sobra por alimento (B12 da spec), então quem lança
 * precisa saber disso antes de estranhar o relatório depois. */
function ItemConsumo({ item, modo, numAnimais, valorKg, onMudarKg }: {
  item: ItemDietaDoLote; modo: "animais" | "kg"; numAnimais: number; valorKg: string; onMudarKg: (v: string) => void;
}) {
  const semConversao = !item.converte_para_kg;
  const computado = item.por_cabeca != null ? Math.round(item.por_cabeca * numAnimais * 100) / 100 : null;
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.8rem", padding: "0.6rem 0", borderBottom: "1px solid var(--mob-border)" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>{item.alimento}</div>
        <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)" }}>
          {modo === "animais"
            ? (item.por_cabeca != null ? `${item.por_cabeca} ${item.unidade}/cabeça` : "sem cálculo automático — lance em kg")
            : `programado: ${item.quantidade} ${item.unidade}`}
          {semConversao && <span style={{ color: "var(--mob-ambar)" }}> · sem conversão p/ kg</span>}
        </div>
      </div>
      {modo === "animais" ? (
        <strong style={{ fontSize: "1.05rem", flexShrink: 0 }}>{computado != null ? `${computado} ${item.unidade}` : "—"}</strong>
      ) : (
        <input type="number" inputMode="decimal" className="mob-input" style={{ width: "6.5rem", flexShrink: 0, textAlign: "right" }}
          value={valorKg} onChange={(e) => onMudarKg(e.target.value)} placeholder="0" />
      )}
    </div>
  );
}
