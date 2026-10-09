"use client";
// Relatórios › Entrega ao contador › Fechamento do mês — "Setembro está pronto para fechar?"
// O checklist é calculado AO VIVO no servidor (GET /financeiro/fechamento/{mes}):
// sem conta, natureza, contas automáticas, saldo de abertura, faturas do
// cartão, folha, conciliação e depreciação. "Fechar" (administrador) grava uma
// linha na trilha APPEND-ONLY com o retrato SHA-256 dos totais; com a flag
// financeiro_regras_v2, o mês fechado trava editar/baixar/excluir lançamento
// com competência ou pagamento nele, até alguém reabrir com motivo.
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight, Clock, Info, Lock, LockOpen } from "lucide-react";
import { ehAdmin } from "@/lib/api";
import {
  fecharMes, fetchFechamentoMes, fetchMesesFechamento, reabrirMes, type ItemChecklist, type MesesResposta, type SituacaoMes,
} from "@/lib/fechamentoApi";
import { ESTADO_INICIAL, brl, mesCurto } from "@/lib/relatorioContexto";
import {
  contagemChecklist, descreverItem, estadoBotaoFechar, fraseFechamento, nomeMes, tituloFechamento,
} from "@/lib/relatorioFechamento";
import type { RelatorioParaExportar } from "@/lib/export";
import { NotasMetodo, RelatorioShell } from "./RelatorioShell";
import { CSS_ENTREGA } from "./estilosEntrega";
import { Pill, useContextoMensal } from "./entregaComum";
import type { PropsRelatorio } from "./comum";

const MAX_ITENS = 8;
const dataBr = (iso: string) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");
const dataHoraBr = (iso: string | null) => {
  if (!iso) return "—";
  // A trilha grava UTC: mostra no fuso de quem lê.
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? dataBr(iso) : d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
};
const TRAVAS = {
  cc: "todos", reg: "comp" as const, cmp: "nada" as const,
  porque: "O fechamento é por mês e vale para a fazenda inteira (todos os centros).",
};
const LINKS: Record<string, string> = {
  parametros_contas_automaticas: "/parametros?sub=financeiro&pf=automaticas",
  parametros_contas_correntes: "/parametros?sub=financeiro",
};

export default function FechamentoMesView(props: PropsRelatorio) {
  const { hoje, centros } = props;
  const admin = ehAdmin();
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, "todos"), [hoje]);
  // O fechamento é sempre de UM mês e da fazenda inteira.
  const ctx = useContextoMensal(padrao, hoje, TRAVAS);
  const mes = ctx.periodo.val;

  const [dados, setDados] = useState<SituacaoMes | null>(null);
  const [meses, setMeses] = useState<MesesResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const recarregar = useCallback(() => setTentativa((t) => t + 1), []);
  useEffect(() => {
    let vivo = true;
    Promise.all([fetchFechamentoMes(mes), fetchMesesFechamento(undefined, 24)])
      .then(([d, m]) => { if (vivo) { setDados(d); setMeses(m); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [mes, tentativa]);

  const atual = dados && dados.mes === mes ? dados : null;
  const estado = !atual && !erro ? "carregando" : erro && !atual ? "erro" : "ok";

  // ── ações (fechar / reabrir) ──
  const [form, setForm] = useState<"fechar" | "reabrir" | null>(null);
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [msgAcao, setMsgAcao] = useState<{ ok: boolean; t: string } | null>(null);
  // Trocou de mês: fecha o formulário e limpa a mensagem (ajuste durante o render).
  const [mesVisto, setMesVisto] = useState(mes);
  if (mesVisto !== mes) { setMesVisto(mes); setForm(null); setMotivo(""); setMsgAcao(null); }
  const botao = atual ? estadoBotaoFechar(atual, admin, dataBr) : null;
  const enviar = async (acao: "fechar" | "reabrir") => {
    setEnviando(true); setMsgAcao(null);
    try {
      if (acao === "fechar") await fecharMes(mes, { forcar: !!botao?.comPendencias, motivo: motivo.trim() || null });
      else await reabrirMes(mes, motivo.trim());
      setMsgAcao({ ok: true, t: acao === "fechar" ? `${nomeMes(mes)} fechado. A trilha guardou o retrato dos totais.` : `${nomeMes(mes)} reaberto. O motivo ficou na trilha.` });
      setForm(null); setMotivo("");
      recarregar();
    } catch (e) {
      setMsgAcao({ ok: false, t: (e as Error).message });
    } finally { setEnviando(false); }
  };

  const exportar = (): RelatorioParaExportar | null => atual && ({
    titulo: `Fechamento de ${nomeMes(mes)}`, pergunta: tituloFechamento(mes, atual.status),
    contexto: { periodo: ctx.periodo.label, comparacao: null, regime: "mês do gasto (competência)", centro: "todos os centros" },
    colunas: [{ header: "Conferência", tipo: "texto" }, { header: "Situação", tipo: "texto" }, { header: "Itens", tipo: "num" }, { header: "O que procura", tipo: "texto" }],
    linhas: atual.checklist.map((c) => ({ valores: [c.nome, c.ok ? "ok" : c.bloqueia ? "pendente" : "aviso", c.quantidade, c.txt] })),
    notas: [
      `Situação do mês: ${atual.status === "fechado" ? "fechado" : atual.status === "em_curso" ? "em curso" : "aberto"}.`,
      atual.evento_atual?.acao === "fechar" ? `Fechado em ${dataHoraBr(atual.evento_atual.criado_em)} por ${atual.evento_atual.usuario} · retrato SHA-256 ${atual.evento_atual.retrato_sha256}.` : "",
      ...atual.trilha_do_mes.map((e) => `${e.acao === "fechar" ? "Fechou" : "Reabriu"} em ${dataHoraBr(e.criado_em)} · ${e.usuario}${e.motivo ? ` · motivo: ${e.motivo}` : ""}`),
    ].filter(Boolean),
    nomeArquivoBase: `fechamento_${mes}`,
  });

  const irDestino = (destino: string | null) => {
    if (!destino) return;
    if (LINKS[destino]) { window.location.assign(LINKS[destino]); return; }
    props.onIrRelatorio(destino);
  };

  const conferencia = (c: ItemChecklist) => {
    const tom = c.ok ? "ok" : c.bloqueia ? "aten" : "info";
    return (
      <li key={c.id}>
        <span className={`ce-ic ${tom}`}>{c.ok ? <CheckCircle2 size={18} aria-hidden /> : <AlertTriangle size={18} aria-hidden />}</span>
        <div>
          <b>{c.nome}</b>
          <small>{c.ok ? "nenhum problema" : `${c.quantidade} ${c.quantidade === 1 ? "item" : "itens"} · ${c.txt}`}{c.resumo ? ` · ${c.resumo}` : ""}</small>
        </div>
        <Pill tom={c.ok ? "ok" : c.bloqueia ? "aten" : "info"} icone={null}>{c.ok ? "ok" : c.bloqueia ? "pendente" : "aviso"}</Pill>
        {!c.ok && (
          <ul className="ce-sub" aria-label={`Itens: ${c.nome}`}>
            {c.itens.slice(0, MAX_ITENS).map((i, k) => {
              const d = descreverItem(c.id, i);
              return (
                <li key={k}>
                  <span><span className="t">{d.titulo}</span><span className="s">{d.sub}</span></span>
                  {k === 0 && c.destino && c.rotulo_acao && (
                    <button type="button" className="rl-btn" onClick={() => irDestino(c.destino)}>{c.rotulo_acao} <ChevronRight size={13} aria-hidden /></button>
                  )}
                </li>
              );
            })}
            {c.itens.length > MAX_ITENS && <li className="ce-mais">… e mais {c.itens.length - MAX_ITENS}</li>}
          </ul>
        )}
      </li>
    );
  };

  const cont = atual ? contagemChecklist(atual.checklist) : null;
  const ret = atual?.retrato_fechamento ?? null;

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Entrega ao contador" nome="Fechamento do mês"
      pergunta={atual ? tituloFechamento(mes, atual.status) : `${nomeMes(mes)} está pronto para fechar?`}
      onIrGrupo={props.onIrGrupo} estado={estado} erro={erro} onTentarDeNovo={() => { setErro(null); recarregar(); }}
      frase={atual ? fraseFechamento(atual, dataHoraBr) : []} exportar={exportar}
      avisos={atual && !atual.regras_v2 ? (
        <div className="rl-aviso info" role="status"><Info size={18} aria-hidden /><div>
          <b>Regras antigas dos relatórios: o fechamento só confere, não trava.</b>
          <p>As conferências abaixo valem como lista do que falta. Fechar e travar a edição do mês entra com as regras novas — <a href="/parametros?sub=financeiro">Parâmetros financeiros</a>.</p>
        </div></div>
      ) : null}>
      <style>{CSS_ENTREGA}</style>
      {atual && cont && (<>
        {atual.status === "fechado" && (
          <div className="rl-aviso info" role="status"><Lock size={18} aria-hidden /><div>
            <b>Mês fechado: lançamentos com competência ou pagamento em {nomeMes(mes)} estão travados.</b>
            <p>Os relatórios deste mês não mudam mais, a não ser que um administrador reabra com motivo (fica registrado na trilha).</p>
          </div></div>
        )}
        {atual.mudou_desde_o_fechamento && ret && (
          <div className="rl-aviso" role="status"><AlertTriangle size={18} aria-hidden /><div>
            <b>Os totais de {nomeMes(mes)} mudaram depois do fechamento.</b>
            <p>Resultado no fechamento {brl(ret.dre_competencia.linhas.RESULTADO_LIQUIDO ?? 0)} · hoje {brl(atual.retrato_atual.dre_competencia.linhas.RESULTADO_LIQUIDO ?? 0)}.
              Alguma mudança passou por fora da trava (ex.: classificação de conta no plano). Confira e, se preciso, reabra e feche de novo.</p>
          </div></div>
        )}
        <section className="rl-painel" aria-labelledby="fm-cf">
          <h3 className="rl-tit" id="fm-cf">Conferências automáticas · {cont.ok} de {cont.total} ok</h3>
          <ul className="ce-lst">{atual.checklist.map(conferencia)}</ul>
          <div aria-live="polite">
            {msgAcao && (msgAcao.ok
              ? <div className="ce-ok" role="status" style={{ marginTop: ".7rem" }}><CheckCircle2 size={18} aria-hidden /><div><b>{msgAcao.t}</b></div></div>
              : <p className="ce-erro" role="alert" style={{ marginTop: ".6rem" }}>{msgAcao.t}</p>)}
          </div>
          {atual.status !== "fechado" && botao && (
            <div className="ce-acts">
              {botao.mostra && form !== "fechar" && (
                <button type="button" className="ce-btn-pri" aria-disabled={!botao.habilitado} disabled={!botao.habilitado}
                  onClick={() => (botao.comPendencias ? setForm("fechar") : enviar("fechar"))}>
                  <Lock size={15} aria-hidden /> {botao.comPendencias ? `Fechar ${nomeMes(mes)} com pendências…` : `Fechar ${nomeMes(mes)}`}
                </button>
              )}
              <span className="hint">{botao.dica}</span>
            </div>
          )}
          {atual.status === "fechado" && admin && form !== "reabrir" && (
            <div className="ce-acts">
              <button type="button" className="rl-btn" onClick={() => setForm("reabrir")}><LockOpen size={15} aria-hidden /> Reabrir com motivo</button>
              <span className="hint">Reabrir destrava a edição do mês e fica na trilha.</span>
            </div>
          )}
          {form && (
            <form className="ce-form" onSubmit={(e) => { e.preventDefault(); enviar(form); }}>
              <label htmlFor="fm-motivo">{form === "fechar" ? `Por que fechar ${nomeMes(mes)} com ${cont.pendentes} ${cont.pendentes === 1 ? "pendência" : "pendências"}?` : `Por que reabrir ${nomeMes(mes)}?`}</label>
              <textarea id="fm-motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} required minLength={5} maxLength={500}
                placeholder={form === "fechar" ? "Ex.: o contador pediu o fechamento; a conciliação do Sicredi fica para outubro." : "Ex.: nota do tanque lançada no centro errado; corrigir para Leite."} />
              <div className="ce-acts" style={{ marginTop: 0 }}>
                <button type="submit" className="ce-btn-pri" disabled={enviando || motivo.trim().length < 5}>
                  {form === "fechar" ? <><Lock size={15} aria-hidden /> Fechar assim mesmo</> : <><LockOpen size={15} aria-hidden /> Reabrir</>}
                </button>
                <button type="button" className="rl-btn" onClick={() => { setForm(null); setMotivo(""); }}>Cancelar</button>
                <span className="hint">O motivo fica na trilha de auditoria, com seu nome e a hora.</span>
              </div>
            </form>
          )}
        </section>

        <div className="rl-dois">
          <section className="rl-painel rl-noprint" aria-labelledby="fm-me">
            <h3 className="rl-tit" id="fm-me">Meses</h3>
            <div className="ce-meses">
              {(meses?.meses ?? []).map((m) => (
                <button key={m.mes} type="button" className={`ce-mes${m.status === "fechado" ? " fechado" : ""}`} aria-current={m.mes === mes ? "true" : undefined}
                  onClick={() => ctx.mudar({ per: `m:${m.mes}` })} aria-label={`${nomeMes(m.mes)}: ${m.status === "fechado" ? "fechado" : m.status === "em_curso" ? "em curso" : "aberto"}`}>
                  <b>{mesCurto(m.mes)}</b>
                  <span>{m.status === "fechado" ? <Lock size={12} aria-hidden /> : <LockOpen size={12} aria-hidden />}{m.status === "fechado" ? "fechado" : m.status === "em_curso" ? "em curso" : m.reaberto ? "reaberto" : "aberto"}</span>
                </button>
              ))}
            </div>
          </section>
          <section className="rl-painel" aria-labelledby="fm-rt">
            <h3 className="rl-tit" id="fm-rt">{ret ? "Retrato guardado no fechamento" : "Totais do mês hoje"}</h3>
            <dl className="ce-dl">
              {(() => {
                const r = ret ?? atual.retrato_atual;
                const res = r.dre_competencia.linhas.RESULTADO_LIQUIDO ?? 0, resK = r.dre_caixa.linhas.RESULTADO_LIQUIDO ?? 0;
                return (<>
                  <dt>Resultado pelo mês do gasto</dt><dd style={res < 0 ? { color: "var(--st-venc-fg)" } : undefined}>{brl(res)}</dd>
                  <dt>Resultado pelo dia do pagamento</dt><dd style={resK < 0 ? { color: "var(--st-venc-fg)" } : undefined}>{brl(resK)}</dd>
                  <dt>Entrou no caixa</dt><dd>{brl(r.caixa.entradas)}</dd>
                  <dt>Saiu do caixa</dt><dd>{brl(r.caixa.saidas)}</dd>
                  <dt>Sem classificação</dt><dd>{brl(r.dre_competencia.nao_classificado)}</dd>
                </>);
              })()}
            </dl>
            <p className="ce-hash" style={{ margin: ".6rem 0 0" }} title="SHA-256 do retrato dos totais">
              {atual.evento_atual?.acao === "fechar" ? `SHA-256 ${atual.evento_atual.retrato_sha256}` : `Retrato de agora: ${atual.retrato_atual_sha256.slice(0, 16)}…`}
            </p>
          </section>
        </div>

        <section className="rl-painel" aria-labelledby="fm-tr">
          <h3 className="rl-tit" id="fm-tr">Trilha de auditoria</h3>
          {(meses?.trilha ?? []).length === 0 ? <p style={{ margin: 0, fontSize: ".84rem", color: "var(--text-muted)" }}>Nenhum mês foi fechado ainda.</p> : (
            <ul className="ce-lst">
              {(meses?.trilha ?? []).slice(0, 12).map((e) => (
                <li key={e.id}>
                  <span className="ce-ic neu"><Clock size={16} aria-hidden /></span>
                  <div>
                    <b>{e.acao === "fechar" ? "Fechou" : "Reabriu"} {nomeMes(e.mes)}{e.pendencias_no_fechamento ? ` com ${e.pendencias_no_fechamento} ${e.pendencias_no_fechamento === 1 ? "pendência" : "pendências"}` : ""}</b>
                    <small>{dataHoraBr(e.criado_em)} · {e.usuario || "—"}{e.motivo ? ` · motivo: “${e.motivo}”` : ""}</small>
                  </div>
                  <span />
                </li>
              ))}
            </ul>
          )}
        </section>
        <NotasMetodo titulo="O que cada conferência procura e o que o fechamento trava"
          entra={atual.checklist.map((c): [string, string] => [c.nome, `${c.txt}${c.bloqueia ? "" : " (aviso: não impede fechar)"}`])}
          naoEntra={[
            "Fechar não muda nenhum número: grava quem, quando e o retrato (SHA-256) dos totais da DRE e do caixa.",
            "Com o mês fechado (e as regras novas ligadas), editar, dar baixa, estornar, mudar a natureza ou excluir lançamento com competência ou pagamento no mês responde “reabra com motivo”.",
            "Mudanças no plano de contas (linha da DRE de uma conta) valem para todos os meses e não são travadas: o aviso “os totais mudaram depois do fechamento” mostra se isso aconteceu.",
          ]} />
      </>)}
    </RelatorioShell>
  );
}
