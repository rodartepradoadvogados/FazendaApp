"use client";
// Sub-tela SOBRA DO COCHO do app de campo — separada do fornecimento
// (decisão do dono, 21/10/2026): a sobra é UMA leitura por ciclo de 24h, e o
// ciclo é definido pela posição da leitura cadastrada na dieta do lote
// ("entre quais tratos a sobra é lida" — ver lib/tratos.ts). Antes de gravar,
// a tela SEMPRE mostra o período pré-montado ("A sobra se refere aos tratos 2
// e 3 do dia 20/10 e ao trato 1 do dia 21/10?") com Confirmar / Selecionar
// outro período / Cancelar. O resumo é montado aqui mesmo (lib/tratos.ts), a
// partir da dieta em cache — funciona sem sinal; com sinal, o servidor
// confirma o mesmo período e mostra o fornecido na janela (base da sobra %).
// Envio pela fila offline (enviarOuEnfileirar), como todo o Lançar.
import { useEffect, useMemo, useState } from "react";
import { MobCampo, MobAviso, MobCard } from "@/components/mobile/ui";
import { fetchComCache } from "@/lib/offline";
import { fetchLotes, fetchDietaDoLote, fetchJanelaSobra, type DietaDoLote, type JanelaSobra } from "@/lib/api";
import { descreverJanela, janelaSobra, opcoesPosicaoLeitura } from "@/lib/tratos";
import { useCache, useEnvio, useRascunho, hoje, RascunhoAviso } from "./comum";

type Lote = { id: number; codigo: string; nome: string };
type DraftSobra = { loteSel: string; kgSobra: string };
// Escolha feita em "Selecionar outro período": undefined = a posição da
// dieta; "civil" = o dia inteiro do fornecimento (comportamento antigo).
type Escolha = number | "civil" | undefined;

export function FormSobraCocho() {
  const lotes = useCache<Lote[]>("lotes", () => fetchLotes() as Promise<Lote[]>, []);
  const rascunho = useRascunho<DraftSobra>("sobra_cocho", { loteSel: "", kgSobra: "" });
  const { loteSel, kgSobra } = rascunho.valor;
  const atualizar = (patch: Partial<DraftSobra>) => rascunho.setValor((atual) => ({ ...atual, ...patch }));
  const [data, setData] = useState(hoje());
  // Dieta por lote (cache em memória da tela). Ausente = carregando ·
  // null = lote sem dieta ativa.
  const [dietas, setDietas] = useState<Record<string, DietaDoLote | null>>({});
  const dieta: DietaDoLote | null | undefined = loteSel in dietas ? dietas[loteSel] : undefined;
  const [confirmando, setConfirmando] = useState(false);
  const [outroPeriodo, setOutroPeriodo] = useState(false);
  const [escolha, setEscolha] = useState<Escolha>(undefined);
  // Resposta do servidor guardada com a chave do período pedido — só vale
  // enquanto a chave é a do período na tela (sem limpar estado em efeito).
  const [respostaJanela, setRespostaJanela] = useState<{ chave: string; janela: JanelaSobra } | null>(null);
  const { aviso, setAviso, enviar, enviando, erroValidacao } = useEnvio();

  useEffect(() => {
    if (!loteSel) return;
    let vivo = true;
    fetchComCache<DietaDoLote | null>(`lancar_dieta_do_lote_${loteSel}`, () => fetchDietaDoLote(Number(loteSel)))
      .then((r) => { if (vivo) setDietas((atual) => ({ ...atual, [loteSel]: r.dados ?? null })); });
    return () => { vivo = false; };
  }, [loteSel]);

  const n = dieta?.num_tratos ?? 2;
  // Dieta sem posição cadastrada (dieta antiga) = comportamento de sempre:
  // a data é o próprio dia do fornecimento.
  const posicaoDieta = dieta?.sobra_posicao_leitura ?? null;
  const posicao = escolha === undefined ? posicaoDieta : escolha === "civil" ? null : escolha;
  const janelaLocal = useMemo(() => janelaSobra(data, n, posicao), [data, n, posicao]);
  const chaveJanela = `${loteSel}|${data}|${escolha ?? ""}`;
  const janelaServidor = respostaJanela?.chave === chaveJanela ? respostaJanela.janela : null;
  const descricao = janelaServidor?.descricao ?? descreverJanela(janelaLocal.itens);

  // Com sinal, o servidor confere o período (pela dieta vigente na data) e
  // devolve o fornecido na janela e a sobra já lançada para o ciclo.
  useEffect(() => {
    if (!confirmando || !loteSel) return;
    let vivo = true;
    fetchJanelaSobra({
      lote: Number(loteSel), data,
      posicao_leitura: typeof escolha === "number" ? escolha : null, dia_civil: escolha === "civil",
    }).then((j) => { if (vivo) setRespostaJanela({ chave: chaveJanela, janela: j }); }).catch(() => { /* offline — fica o resumo local */ });
    return () => { vivo = false; };
  }, [confirmando, loteSel, data, escolha, chaveJanela]);

  const rotuloLote = (codigo: string) => {
    const lo = lotes.dados.find((x) => x.codigo === codigo);
    return lo ? `${lo.codigo} - ${lo.nome}` : `Lote ${codigo}`;
  };
  const lotesOrdenados = useMemo(
    () => [...lotes.dados].sort((a, b) => a.codigo.localeCompare(b.codigo, undefined, { numeric: true })),
    [lotes.dados],
  );

  function pedirConfirmacao() {
    setAviso(null);
    if (!loteSel) return erroValidacao("Selecione o lote.");
    if (kgSobra.trim() === "" || !(Number(kgSobra) >= 0)) return erroValidacao("Informe a sobra em quilos.");
    setEscolha(undefined);
    setOutroPeriodo(false);
    setConfirmando(true);
  }

  function confirmar() {
    const corpo = {
      lote: Number(loteSel), data, kg_sobra: Number(kgSobra),
      ...(escolha === "civil" ? { dia_civil: true } : typeof escolha === "number" ? { posicao_leitura: escolha } : {}),
    };
    // Relançar para o mesmo ciclo SUBSTITUI a sobra anterior (é medição, não
    // acúmulo) — o backend faz a troca; aqui só envia.
    enviar("/alimentacao/sobra", corpo, `Sobra — ${rotuloLote(loteSel)}: ${kgSobra} kg (${descricao.replace(/^A sobra se refere /, "").replace(/\?$/, "")})`, () => {
      setConfirmando(false);
      atualizar({ kgSobra: "" });
    }, { ok: "Sobra lançada." });
  }

  if (lotes.pronto && lotes.dados.length === 0) {
    return <p style={{ color: "var(--mob-muted)", fontSize: "0.95rem", lineHeight: 1.5 }}>Nenhum lote cadastrado.</p>;
  }

  const semPosicao = posicaoDieta == null && n > 1;
  const pctPrevia = janelaServidor && janelaServidor.kg_fornecido_janela > 0 && kgSobra !== ""
    ? (Number(kgSobra) / janelaServidor.kg_fornecido_janela) * 100 : null;

  return (
    <>
      <RascunhoAviso mostrar={rascunho.salvo} />
      <MobCampo label="Lote">
        <select className="mob-input" value={loteSel} onChange={(e) => { atualizar({ loteSel: e.target.value }); setConfirmando(false); }}>
          <option value="">Selecione o lote…</option>
          {lotesOrdenados.map((l) => <option key={l.codigo} value={l.codigo}>{l.codigo} - {l.nome}</option>)}
        </select>
      </MobCampo>

      {loteSel && dieta === undefined && <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem" }}>Carregando dieta do lote…</p>}
      {loteSel && dieta === null && (
        <MobAviso tipo="offline">Este lote não tem dieta ativa — a sobra vale pelo dia inteiro, com 2 tratos 50/50.</MobAviso>
      )}

      {loteSel && dieta !== undefined && (
        <MobCard>
          <MobCampo label={semPosicao ? "Data da sobra (dia do fornecimento)" : "Data da leitura da sobra"}>
            <input type="date" className="mob-input" value={data} onChange={(e) => { setData(e.target.value); setConfirmando(false); }} />
          </MobCampo>
          <MobCampo label="Sobra (kg totais)">
            <input type="number" inputMode="decimal" className="mob-input" style={{ fontSize: "1.3rem", fontWeight: 700 }}
              value={kgSobra} onChange={(e) => { atualizar({ kgSobra: e.target.value }); }} placeholder="0" />
          </MobCampo>
          <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", margin: "-0.3rem 0 0.7rem" }}>
            Uma sobra por ciclo de 24h — relançar o mesmo período substitui, não soma.
          </p>

          {!confirmando ? (
            <button className="mob-btn" onClick={pedirConfirmacao} disabled={enviando}>Lançar sobra</button>
          ) : (
            <div style={{ border: "2px solid var(--mob-dourado)", borderRadius: "var(--r-app)", padding: "0.8rem" }}>
              <p style={{ margin: 0, fontSize: "1rem", fontWeight: 800, lineHeight: 1.35 }}>{descricao}</p>
              {janelaServidor && (
                <p style={{ margin: "0.4rem 0 0", fontSize: "0.82rem", color: "var(--mob-muted)" }}>
                  Fornecido nesse período: <strong>{janelaServidor.kg_fornecido_janela.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} kg</strong>
                  {pctPrevia != null && <> · sobra de <strong>{pctPrevia.toFixed(1)}%</strong></>}
                  {janelaServidor.kg_sobra_existente != null && <><br />Já há {janelaServidor.kg_sobra_existente} kg lançados para esse período — confirmar substitui.</>}
                </p>
              )}

              {outroPeriodo && (
                <div style={{ marginTop: "0.7rem" }}>
                  <MobCampo label={escolha === "civil" ? "Dia do fornecimento" : "Data da leitura"}>
                    <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
                  </MobCampo>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.4rem" }}>
                    {opcoesPosicaoLeitura(n).map((o) => (
                      <button key={o.valor} type="button" className={posicao === o.valor && escolha !== "civil" ? "mob-btn" : "mob-btn mob-btn-sec"}
                        style={{ fontSize: "0.85rem", padding: "0.6rem 0.4rem" }} onClick={() => setEscolha(o.valor)}>
                        Lida entre {o.rotulo}
                      </button>
                    ))}
                    <button type="button" className={posicao == null ? "mob-btn" : "mob-btn mob-btn-sec"}
                      style={{ fontSize: "0.85rem", padding: "0.6rem 0.4rem" }} onClick={() => setEscolha("civil")}>
                      Dia inteiro do fornecimento
                    </button>
                  </div>
                </div>
              )}

              <div style={{ display: "grid", gap: "0.5rem", marginTop: "0.8rem" }}>
                <button className="mob-btn" onClick={confirmar} disabled={enviando}>{enviando ? "Salvando…" : "Confirmar"}</button>
                {!outroPeriodo && (
                  <button className="mob-btn mob-btn-sec" onClick={() => setOutroPeriodo(true)} disabled={enviando}>Selecionar outro período</button>
                )}
                <button className="mob-btn mob-btn-sec" onClick={() => { setConfirmando(false); setEscolha(undefined); setOutroPeriodo(false); }} disabled={enviando}>Cancelar</button>
              </div>
            </div>
          )}
          {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
        </MobCard>
      )}
    </>
  );
}
