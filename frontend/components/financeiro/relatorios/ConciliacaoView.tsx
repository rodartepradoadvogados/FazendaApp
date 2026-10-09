"use client";
// Relatórios › Entrega ao contador › Conciliação bancária — "O banco bate com o sistema?"
// Importa o extrato (OFX ou CSV) de uma conta corrente, sugere o par de cada
// linha no sistema (lançamento pago ou transferência: mesmo sinal, valor ao
// centavo, data ± 3 dias, texto só desempata) e deixa confirmar, desfazer,
// marcar "sem lançamento" ou criar o lançamento que falta já pareado. As
// sugestões e os saldos vêm do servidor (GET /financeiro/conciliacao); o que
// fica pendente alimenta o checklist do Fechamento do mês.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, Check, CheckCircle2, Info, Plus, Undo2, Upload } from "lucide-react";
import { criarLancamentoFinanceiro, fetchPlanoContas } from "@/lib/api";
import {
  confirmarSugestoes, desfazerLinha, fetchConciliacao, importarExtrato, marcarSemLancamento, parearLinha,
  type ConciliacaoResposta, type LinhaExtrato,
} from "@/lib/fechamentoApi";
import { ESTADO_INICIAL, brl } from "@/lib/relatorioContexto";
import { ROTULO_SITUACAO, fraseConciliacao, linhasConciliacao, nomeMes, somaDiferencas, type LinhaTela, type SituacaoLinha } from "@/lib/relatorioFechamento";
import type { RelatorioParaExportar } from "@/lib/export";
import { Conferencia, NotasMetodo, RelatorioShell, VazioQueEnsina, type KpiDef } from "./RelatorioShell";
import { CSS_ENTREGA } from "./estilosEntrega";
import { Pill, useContextoMensal, type TomPill } from "./entregaComum";
import type { PropsRelatorio } from "./comum";

const TRAVAS = {
  cc: "todos", reg: "caixa" as const, cmp: "nada" as const,
  porque: "A conciliação compara o extrato do mês com o que passou pelo banco no sistema (dia do pagamento), conta a conta.",
};
const TOM: Record<SituacaoLinha, TomPill> = {
  conciliado: "ok", sugerido: "info", so_extrato: "aten", sem_lancamento: "neu", so_sistema: "info", valor_diferente: "ruim",
};
const dm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const dmy = (iso: string | null) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");
const valor = (v: number | null) => (v == null ? <span className="mut">—</span> : <span className={v < 0 ? "neg" : undefined}>{brl(v)}</span>);
type ContaPlano = { codigo: string; nome: string; ativa?: boolean };

export default function ConciliacaoView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, "todos"), [hoje]);
  const ctx = useContextoMensal(padrao, hoje, TRAVAS);
  const mes = ctx.periodo.val;

  // Conta escolhida na URL (?conta=): link compartilhável e Voltar funcionam.
  const [contaId, setContaIdEstado] = useState<number | null>(() =>
    typeof window === "undefined" ? null : Number(new URLSearchParams(window.location.search).get("conta")) || null);
  useEffect(() => {
    const aoVoltar = () => setContaIdEstado(Number(new URLSearchParams(window.location.search).get("conta")) || null);
    window.addEventListener("popstate", aoVoltar);
    return () => window.removeEventListener("popstate", aoVoltar);
  }, []);
  const escolherConta = (id: number) => {
    const q = new URLSearchParams(window.location.search);
    q.set("conta", String(id));
    window.history.pushState(window.history.state, "", `${window.location.pathname}?${q}${window.location.hash}`);
    setContaIdEstado(id);
  };

  const [dados, setDados] = useState<ConciliacaoResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const recarregar = useCallback(() => setTentativa((t) => t + 1), []);
  useEffect(() => {
    let vivo = true;
    fetchConciliacao(mes, contaId)
      .then((d) => { if (vivo) { setDados(d); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [mes, contaId, tentativa]);

  const atual = dados && dados.mes === mes ? dados : null;
  const s = atual?.situacao ?? null;
  const linhas = useMemo(() => linhasConciliacao(s), [s]);
  const fila = linhas.filter((l) => l.situacao === "sugerido");
  const estado = !atual && !erro ? "carregando" : erro && !atual ? "erro" : atual && !atual.contas.length ? "vazio" : "ok";

  // ── ações ──
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const acao = async (chave: string, f: () => Promise<unknown>, ok: string) => {
    setOcupado(chave); setMsg(null);
    try { await f(); setMsg({ ok: true, t: ok }); recarregar(); } catch (e) { setMsg({ ok: false, t: (e as Error).message }); } finally { setOcupado(null); }
  };
  const arquivo = useRef<HTMLInputElement>(null);
  const importar = async (f: File | undefined) => {
    if (!f || !s) return;
    await acao("importar", async () => {
      const r = await importarExtrato(s.conta_corrente_id, f);
      setMsg({ ok: true, t: `Extrato ${r.formato.toUpperCase()} importado: ${r.linhas_novas} ${r.linhas_novas === 1 ? "linha nova" : "linhas novas"}${r.linhas_repetidas ? `, ${r.linhas_repetidas} já importadas antes` : ""}.` });
    }, "Extrato importado.");
    if (arquivo.current) arquivo.current.value = "";
  };

  // ── criar o lançamento que falta (atalho "sem lançamento no sistema") ──
  const [criando, setCriando] = useState<LinhaExtrato | null>(null);
  const [plano, setPlano] = useState<ContaPlano[] | null>(null);
  const [novo, setNovo] = useState({ conta: "", descricao: "", fornecedor: "", centro: "" });
  const abrirCriar = (l: LinhaExtrato) => {
    setCriando(l);
    setNovo({ conta: "", descricao: l.historico || "", fornecedor: "", centro: ccPadrao !== "todos" ? ccPadrao : "" });
    if (!plano) fetchPlanoContas().then((p: ContaPlano[]) => setPlano(p.filter((c) => c.ativa !== false))).catch(() => setPlano([]));
  };
  const criarEParear = async () => {
    if (!criando || !s) return;
    const l = criando, abs = Math.abs(l.valor);
    await acao(`criar${l.id}`, async () => {
      const r = await criarLancamentoFinanceiro({
        tipo: l.valor > 0 ? "receita" : "despesa",
        itens: [{ produto: novo.descricao || "Lançamento do extrato", codigo_conta_gerencial: novo.conta || null, valor_total: abs, tipo_item: "servico" }],
        fornecedor_cliente: novo.fornecedor || null, centro_custo: novo.centro || null, numero_documento: l.documento || null,
        data_emissao: l.data, data_competencia: l.data, data_pagamento: l.data, valor_pago: abs,
        conta_corrente_id: s.conta_corrente_id, conta_bancaria: s.conta, forma_pagamento: l.valor > 0 ? "transferencia" : "debito",
      });
      const id = (r?.ids && r.ids[0]) ?? r?.id;
      if (id) await parearLinha(l.id, { lancamento_id: id });
      setCriando(null);
    }, "Lançamento criado e pareado com a linha do extrato.");
  };

  const sinalCor = (v: number | null | undefined) => (v != null && v < 0 ? { color: "var(--st-venc-fg)" } : undefined);
  const kpis: KpiDef[] = s ? [
    s.saldos.diferenca != null
      ? { chave: "dif", rotulo: "Diferença no fim do mês", valor: s.saldos.diferenca, formato: "brl", bom: "neutro",
          selo: s.saldos.bate ? <Pill tom="ok">banco e sistema batem</Pill> : <Pill tom="ruim">não bate</Pill>,
          sub: `Extrato ${brl(s.saldos.saldo_extrato ?? 0)} · sistema ${brl(s.saldos.saldo_sistema ?? 0)} em ${dmy(s.saldos.data)}${s.saldos.pendente_saldo_abertura ? " · conta sem saldo de abertura" : ""}` }
      : { chave: "dif", rotulo: "Movimento do mês: extrato − sistema", valor: s.movimento.diferenca, formato: "brl", bom: "neutro",
          sub: `Extrato ${brl(s.movimento.extrato)} · sistema ${brl(s.movimento.sistema)} · o extrato não trouxe saldo` },
    { chave: "ok", rotulo: "Conciliadas", valor: s.contagem.pareadas, formato: "num", bom: "neutro", sub: `de ${s.contagem.linhas} linhas do extrato${s.contagem.sem_lancamento ? ` · ${s.contagem.sem_lancamento} sem lançamento` : ""}` },
    { chave: "ext", rotulo: "Pendentes no extrato", valor: s.contagem.pendentes, formato: "num", bom: "neutro", sub: s.contagem.sugestoes_exatas ? `${s.contagem.sugestoes_exatas} com par sugerido na fila` : "nenhuma sugestão exata" },
    { chave: "sis", rotulo: "Só no sistema", valor: s.contagem.so_no_sistema, formato: "num", bom: "neutro", sub: "pago no sistema, ainda não visto no extrato (cheque a compensar, data errada?)" },
  ] : [];

  const exportar = (): RelatorioParaExportar | null => s && ({
    titulo: "Conciliação bancária", pergunta: "O banco bate com o sistema?",
    contexto: { periodo: ctx.periodo.label, comparacao: null, regime: "dia do pagamento (caixa)", centro: s.conta },
    colunas: [{ header: "Data", tipo: "texto" }, { header: "Movimento", tipo: "texto" }, { header: "No extrato", tipo: "brl" }, { header: "No sistema", tipo: "brl" }, { header: "Situação", tipo: "texto" }],
    linhas: linhas.map((l) => ({ valores: [dmy(l.data), l.sub ? `${l.descricao} (${l.sub})` : l.descricao, l.extrato, l.sistema, ROTULO_SITUACAO[l.situacao]] })),
    notas: [
      s.saldos.diferenca != null ? `Saldo do extrato ${brl(s.saldos.saldo_extrato ?? 0)} × sistema ${brl(s.saldos.saldo_sistema ?? 0)} em ${dmy(s.saldos.data)}: diferença ${brl(s.saldos.diferenca)}.` : "O extrato não trouxe saldo: comparação pelo movimento do mês.",
      `Movimento do mês: extrato ${brl(s.movimento.extrato)} × sistema ${brl(s.movimento.sistema)}.`,
    ],
    nomeArquivoBase: `conciliacao_${mes}`,
  });

  const acoesLinha = (l: LinhaTela) => {
    const x = l.linha;
    if (l.situacao === "so_sistema") return <span className="mut" style={{ fontSize: ".76rem" }}>a compensar?</span>;
    if (!x) return null;
    if (l.situacao === "conciliado" || l.situacao === "sem_lancamento") {
      return <button type="button" className="rl-btn" disabled={!!ocupado} onClick={() => acao(`d${x.id}`, () => desfazerLinha(x.id), "Pareamento desfeito: a linha voltou para pendente.")}><Undo2 size={13} aria-hidden /> Desfazer</button>;
    }
    const par = l.mov;
    return (<>
      {par && (
        <button type="button" className="rl-btn" disabled={!!ocupado}
          onClick={() => acao(`p${x.id}`, () => parearLinha(x.id, par.tipo === "lancamento" ? { lancamento_id: par.id } : { transferencia_id: par.id }),
            l.situacao === "valor_diferente" ? "Pareado com valor diferente: lance a diferença (juros, tarifa) para o saldo bater." : "Pareamento confirmado.")}>
          <Check size={13} aria-hidden /> {l.situacao === "valor_diferente" ? "Parear mesmo assim" : "Confirmar"}
        </button>
      )}
      {l.situacao !== "sugerido" && <button type="button" className="rl-btn" disabled={!!ocupado} onClick={() => abrirCriar(x)}><Plus size={13} aria-hidden /> Lançar no sistema</button>}
      {l.situacao !== "sugerido" && <button type="button" className="rl-btn" disabled={!!ocupado} onClick={() => acao(`s${x.id}`, () => marcarSemLancamento(x.id), "Linha marcada como sem lançamento.")}>Sem lançamento</button>}
    </>);
  };

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Entrega ao contador" nome="Conciliação bancária"
      pergunta="O banco bate com o sistema?" onIrGrupo={props.onIrGrupo}
      estado={estado} erro={erro} onTentarDeNovo={() => { setErro(null); recarregar(); }}
      vazio={<VazioQueEnsina titulo="Nenhuma conta corrente cadastrada" texto="A conciliação compara o extrato de cada conta corrente com o que passou por ela no sistema. Cadastre a conta (e o saldo de abertura) primeiro."
        itens={[{ texto: "Conta corrente cadastrada", pronto: false, acao: <a href="/parametros?sub=financeiro">Cadastrar em Parâmetros financeiros</a> },
          { texto: "Saldo de abertura conferido com o extrato", pronto: false }, { texto: "Extrato do mês em OFX ou CSV", pronto: false }]} />}
      frase={s ? fraseConciliacao(s, mes, (v) => brl(v)) : []} kpis={kpis} exportar={exportar}>
      <style>{CSS_ENTREGA}</style>
      {atual && s && (<>
        <div className="ce-topo rl-noprint">
          <div className="rl-seg" role="group" aria-label="Conta corrente">
            {atual.contas.map((c) => (
              <button key={c.id} type="button" aria-pressed={c.id === s.conta_corrente_id} onClick={() => escolherConta(c.id)} title={c.rotulo}>{c.banco}{atual.contas.filter((x) => x.banco === c.banco).length > 1 ? ` · ${c.rotulo.split("Conta corrente ")[1] ?? c.id}` : ""}</button>
            ))}
          </div>
          <div className="rl-acoes">
            <input ref={arquivo} id="ce-arquivo" className="ce-file" type="file" accept=".ofx,.qfx,.csv,.txt,text/csv,application/x-ofx"
              onChange={(e) => importar(e.target.files?.[0])} />
            <button type="button" className="rl-btn" disabled={!!ocupado} onClick={() => arquivo.current?.click()} aria-describedby="ce-arq-dica">
              <Upload size={15} aria-hidden /> {ocupado === "importar" ? "Importando…" : "Importar extrato (OFX ou CSV)"}
            </button>
            <span id="ce-arq-dica" className="rl-sr">Arquivo OFX ou CSV exportado do banco; linhas já importadas não duplicam.</span>
          </div>
        </div>
        <p style={{ margin: 0, fontSize: ".8rem", color: "var(--text-muted)" }}>{s.conta} · {nomeMes(mes)}</p>
        <div aria-live="polite">
          {msg && (msg.ok
            ? <div className="ce-ok" role="status"><CheckCircle2 size={18} aria-hidden /><div><b>{msg.t}</b></div></div>
            : <p className="ce-erro" role="alert">{msg.t}</p>)}
        </div>

        {fila.length > 0 && (
          <section className="rl-painel" aria-labelledby="co-fila">
            <h3 className="rl-tit" id="co-fila">Fila de pareamentos · {fila.length} {fila.length === 1 ? "sugestão" : "sugestões"} com valor exato</h3>
            <ul className="ce-fila">
              {fila.slice(0, 12).map((l) => (
                <li key={l.chave}>
                  <div className="lado"><b>{dm(l.data)} · {brl(l.extrato ?? 0)}</b><small>{l.descricao}</small></div>
                  <span className="seta" aria-hidden><ArrowLeftRight size={16} /></span>
                  <div className="lado"><b>{l.mov ? `${dm(l.mov.data)} · ${brl(l.mov.valor)}` : "—"}</b><small>{l.sub}{l.mov?.dias ? ` · ${l.mov.dias} ${l.mov.dias === 1 ? "dia" : "dias"} de diferença` : ""}</small></div>
                  <div className="ce-acts" style={{ marginTop: 0 }}>{acoesLinha(l)}</div>
                </li>
              ))}
            </ul>
            <div className="ce-acts">
              <button type="button" className="ce-btn-pri" disabled={!!ocupado}
                onClick={() => acao("todas", () => confirmarSugestoes(s.conta_corrente_id, mes), `${fila.length} ${fila.length === 1 ? "pareamento confirmado" : "pareamentos confirmados"}.`)}>
                <Check size={15} aria-hidden /> Confirmar {fila.length === 1 ? "a sugestão" : `as ${fila.length} sugestões`}
              </button>
              <span className="hint">Só valor igual ao centavo, data até 3 dias e mesmo sinal. Cada uma pode ser desfeita depois.</span>
            </div>
          </section>
        )}

        {criando && (
          <section className="rl-painel" aria-labelledby="co-novo">
            <h3 className="rl-tit" id="co-novo">Lançar no sistema a linha de {dm(criando.data)} · {brl(criando.valor)}</h3>
            <form className="ce-form" style={{ maxWidth: "none" }} onSubmit={(e) => { e.preventDefault(); criarEParear(); }}>
              <p style={{ margin: 0, fontSize: ".8rem", color: "var(--text-muted)" }}>
                Cria {criando.valor > 0 ? "uma receita recebida" : "uma despesa paga"} em {dmy(criando.data)} nesta conta, pelo valor do extrato, e já pareia com a linha.
              </p>
              <div className="linha">
                <div><label htmlFor="co-conta">Conta gerencial</label>
                  <select id="co-conta" value={novo.conta} onChange={(e) => setNovo({ ...novo, conta: e.target.value })}>
                    <option value="">{plano ? "Escolher a conta…" : "Carregando o plano…"}</option>
                    {(plano ?? []).map((c) => <option key={c.codigo} value={c.codigo}>{c.codigo} · {c.nome}</option>)}
                  </select></div>
                <div><label htmlFor="co-desc">Descrição</label><input id="co-desc" value={novo.descricao} maxLength={200} onChange={(e) => setNovo({ ...novo, descricao: e.target.value })} /></div>
                <div><label htmlFor="co-forn">{criando.valor > 0 ? "Cliente" : "Fornecedor"}</label><input id="co-forn" value={novo.fornecedor} maxLength={120} onChange={(e) => setNovo({ ...novo, fornecedor: e.target.value })} /></div>
                <div><label htmlFor="co-cc">Centro de custo</label>
                  <select id="co-cc" value={novo.centro} onChange={(e) => setNovo({ ...novo, centro: e.target.value })}>
                    <option value="">Sem centro</option>
                    {centros.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select></div>
              </div>
              <div className="ce-acts" style={{ marginTop: 0 }}>
                <button type="submit" className="ce-btn-pri" disabled={!!ocupado}><Plus size={15} aria-hidden /> Lançar e parear</button>
                <button type="button" className="rl-btn" onClick={() => setCriando(null)}>Cancelar</button>
                {!novo.conta && <span className="hint">Sem conta, o lançamento entra em “não classificado” até ser classificado.</span>}
              </div>
            </form>
          </section>
        )}

        <section className="rl-painel" aria-labelledby="co-tab">
          <h3 className="rl-tit" id="co-tab">Extrato × sistema</h3>
          {!s.importado && (
            <VazioQueEnsina titulo={`O extrato de ${nomeMes(mes)} ainda não foi importado`}
              texto="Exporte o extrato do banco em OFX (preferível: traz o saldo) ou CSV e importe aqui. Os movimentos que o sistema já tem nesta conta aparecem abaixo, esperando o extrato."
              acoes={<button type="button" className="rl-btn" onClick={() => arquivo.current?.click()}><Upload size={14} aria-hidden /> Importar extrato</button>} />
          )}
          {linhas.length > 0 && (
            <div className="rl-tw" style={{ marginTop: s.importado ? 0 : ".75rem", maxHeight: 560, overflowY: "auto" }}>
              <table className="fazenda-table rl-tab ce-tab">
                <caption className="rl-sr">Extrato × sistema — {s.conta} — {nomeMes(mes)}</caption>
                <thead><tr>
                  <th scope="col">Data</th><th scope="col">Movimento</th><th scope="col" className="r">No extrato</th>
                  <th scope="col" className="r">No sistema</th><th scope="col">Situação</th><th scope="col"><span className="rl-sr">Ação</span></th>
                </tr></thead>
                <tbody>
                  {linhas.map((l) => (
                    <tr key={l.chave} className={criando && l.linha?.id === criando.id ? "foco" : undefined}>
                      <td className="tnum">{dm(l.data)}</td>
                      <td>{l.descricao}{l.sub && <small>{l.sub}</small>}</td>
                      <td className="r">{valor(l.extrato)}</td>
                      <td className="r">{valor(l.sistema)}</td>
                      <td><Pill tom={TOM[l.situacao]} icone={l.situacao === "conciliado" ? undefined : l.situacao === "so_extrato" || l.situacao === "valor_diferente" ? undefined : null}>{ROTULO_SITUACAO[l.situacao]}</Pill></td>
                      <td><div className="acao">{acoesLinha(l)}</div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {s.importado && linhas.length === 0 && <p style={{ margin: 0, fontSize: ".84rem", color: "var(--text-muted)" }}>Nenhum movimento neste mês, nem no extrato nem no sistema.</p>}
        </section>

        {atual.resumo.length > 1 && (
          <section className="rl-painel" aria-labelledby="co-res">
            <h3 className="rl-tit" id="co-res">Saldo do extrato × saldo do sistema, por conta</h3>
            <div className="rl-tw">
              <table className="fazenda-table rl-tab ce-tab">
                <caption className="rl-sr">Saldos por conta — {nomeMes(mes)}</caption>
                <thead><tr><th scope="col">Conta</th><th scope="col" className="r">Extrato</th><th scope="col" className="r">Sistema</th><th scope="col" className="r">Diferença</th><th scope="col">Situação</th></tr></thead>
                <tbody>{atual.resumo.map((r) => (
                  <tr key={r.conta_corrente_id}>
                    <td><button type="button" className="rl-linkbtn" onClick={() => escolherConta(r.conta_corrente_id)}>{r.conta}</button><small>em {dmy(r.saldos.data)}</small></td>
                    <td className="r">{valor(r.saldos.saldo_extrato)}</td><td className="r">{valor(r.saldos.saldo_sistema)}</td>
                    <td className="r" style={sinalCor(r.saldos.diferenca)}>{r.saldos.diferenca == null ? <span className="mut">—</span> : brl(r.saldos.diferenca)}</td>
                    <td>{r.conciliada ? (r.tem_movimento ? <Pill tom="ok">conciliada</Pill> : <Pill tom="neu">sem movimento</Pill>) : !r.importado ? <Pill tom="aten">sem extrato</Pill> : <Pill tom="aten">{r.pendentes} pendente{r.pendentes === 1 ? "" : "s"}</Pill>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>
        )}

        <NotasMetodo titulo="Como a conciliação funciona"
          entra={[
            ["Extrato", "OFX (1.x e 2.x) ou CSV dos bancos brasileiros (BB, Sicredi, Sicoob, Itaú, Bradesco, Santander, Caixa, Inter, Nubank). Guarda só data, valor, histórico e nº do documento; o arquivo não fica salvo. Reimportar não duplica."],
            ["Casamento", "Mesma conta, mesmo sinal, valor igual ao centavo e data até 3 dias para os lados; o texto do banco só desempata. Um lançamento casa com uma linha só. Valor até 10% diferente aparece como “valor diferente”, nunca entra na confirmação em lote."],
            ["Só no extrato", "Tarifa, IOF, TED ou débito que ninguém lançou: “Lançar no sistema” cria o lançamento já pago e pareado; “Sem lançamento” marca o que não deve virar lançamento (ex.: estorno do próprio banco)."],
            ["Só no sistema", "Pago no sistema e ainda não visto no extrato: cheque a compensar, data de pagamento errada ou conta errada."],
            ["Saldos", "O saldo do extrato é o que o banco informou (OFX: saldo final; CSV: linha de saldo). O do sistema é o saldo da conta na mesma data: saldo de abertura + o que passou pela conta."],
          ]}
          naoEntra={["A conciliação não muda nenhum número de relatório: só marca o que o banco confirmou. As pendências entram no checklist do Fechamento do mês."]}>
          {(atual.importacoes ?? []).length > 0 && (
            <p style={{ margin: ".6rem 0 0", display: "flex", gap: ".35rem", alignItems: "flex-start" }}>
              <Info size={14} aria-hidden style={{ marginTop: 2 }} /> Últimas importações desta conta: {(atual.importacoes ?? []).slice(0, 3).map((i) => `${i.formato.toUpperCase()} ${dmy(i.data_inicio)}–${dmy(i.data_fim)} (${i.linhas_novas} novas)`).join(" · ")}.
            </p>
          )}
        </NotasMetodo>
        <Conferencia fecha={Math.abs(somaDiferencas(linhas) - s.movimento.diferenca) < 0.015}
          texto={`Movimento do mês no extrato (${brl(s.movimento.extrato)}) − no sistema (${brl(s.movimento.sistema)}) = ${brl(s.movimento.diferenca)} = soma das diferenças da lista acima (${brl(somaDiferencas(linhas))}).`} />
      </>)}
    </RelatorioShell>
  );
}
