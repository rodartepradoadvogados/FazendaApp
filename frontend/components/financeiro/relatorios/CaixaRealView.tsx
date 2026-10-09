"use client";
// Relatórios › Caixa › Caixa real — "Quando o caixa aperta?"
// A projeção é a do SERVIDOR (GET /financeiro/caixa-real: saldo de hoje, contas
// em aberto pelo vencimento, fatura aberta do cartão, pagamento agendado), com
// o fundo de reserva (parâmetro ou sugerido) e o fôlego (GET
// /financeiro/caixa-real/folego). A tela só reorganiza: gráfico do saldo dia a
// dia, linha do tempo por semana/dia com o detalhe de cada período e o
// simulador "Posso comprar?" — uma hipótese da pessoa sobre a mesma série.
// Período, comparação, regime e centro ficam travados com o porquê: o caixa
// olha de hoje para a frente e soma todas as contas bancárias.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CalendarClock, Calculator, CheckCircle2, CircleAlert, ExternalLink, Landmark } from "lucide-react";
import { fetchCaixaReal, fetchFundoReservaSugerido, type CaixaReal } from "@/lib/api";
import { fetchFolegoCaixa, type Folego } from "@/lib/apiRelatoriosCaixa";
import { ESTADO_INICIAL, brl } from "@/lib/relatorioContexto";
import {
  agruparItens, diaSemana, dm, dmy, fraseCaixa, lerValorBR, linhaDoTempo, reservaDe, resumoCaixa, simularCompra, somaDias,
  type Periodo as PeriodoCaixa,
} from "@/lib/relatorioCaixa";
import type { LinhaRelatorio, RelatorioParaExportar } from "@/lib/export";
import { Conferencia, NotasMetodo, PainelGrafico, RelatorioShell, VazioQueEnsina, type KpiDef } from "./RelatorioShell";
import { CSS_CAIXA, GraficoSaldo, LegendaSaldo } from "./graficosCaixa";
import { useContextoRelatorio, useDetalheNaUrl, type TravasContexto } from "./useContextoRelatorio";
import type { PropsRelatorio } from "./comum";

const HORIZONTES = [30, 60, 90, 180, 365];
const brl0 = (v: number) => brl(v, 0);

function lerUrl(chave: string): string {
  return typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get(chave) || "";
}
/** Grava sem entrada nova no histórico (a simulação é rascunho, não navegação). */
function gravarUrl(pares: Record<string, string>) {
  const q = new URLSearchParams(window.location.search);
  for (const [k, v] of Object.entries(pares)) { if (v) q.set(k, v); else q.delete(k); }
  window.history.replaceState(window.history.state, "", `${window.location.pathname}?${q.toString()}${window.location.hash}`);
}

export default function CaixaRealView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const [diasUrl, mudarDias] = useDetalheNaUrl("dias");
  const dias = HORIZONTES.includes(Number(diasUrl)) ? Number(diasUrl) : 90;
  const [visUrl, mudarVis] = useDetalheNaUrl("vis");
  const vis: "semana" | "dia" = visUrl === "dia" ? "dia" : "semana";
  const [det, abrirDet] = useDetalheNaUrl("det");

  const travas: TravasContexto = useMemo(() => ({
    per: false, cmp: false, reg: "caixa", cc: "todos", cmpOrcado: false,
    rotuloPeriodo: `próximos ${dias} dias a partir de hoje (${dmy(hoje)})`,
    porque: `O caixa real olha de hoje (${dmy(hoje)}) para a frente e soma todas as contas bancárias: sempre pelo dia do pagamento, sem período, comparação nem centro de custo.`,
  }), [dias, hoje]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);

  const [dados, setDados] = useState<CaixaReal | null>(null);
  const [sugestao, setSugestao] = useState<{ sugerido: number; meses_folga: number; atual: number } | null>(null);
  const [folego, setFolego] = useState<Folego | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    let vivo = true;
    // `hoje` local (nunca toISOString): o servidor usa Brasília, o front manda o dia que a pessoa vê.
    Promise.all([
      fetchCaixaReal(dias, hoje),
      fetchFundoReservaSugerido(6, hoje).catch(() => null),
      fetchFolegoCaixa(hoje).catch(() => null),
    ]).then(([d, s, f]) => { if (vivo) { setDados(d); setSugestao(s); setFolego(f); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [dias, hoje, tentativa]);

  // "Posso comprar?" — rascunho na URL (link compartilhável), sem entrada no histórico.
  const [simValor, setSimValor] = useState(() => lerUrl("sv"));
  const [simData, setSimData] = useState(() => lerUrl("sd") || somaDias(hoje, 15));
  const [simParc, setSimParc] = useState(() => lerUrl("sp") || "1");
  const [simAtiva, setSimAtiva] = useState(() => !!lerUrl("sv"));
  const simular = () => { setSimAtiva(true); gravarUrl({ sv: simValor, sd: simData, sp: simParc }); };
  const limparSim = () => { setSimAtiva(false); setSimValor(""); gravarUrl({ sv: "", sd: "", sp: "" }); };

  const serie = useMemo(() => dados?.serie ?? [], [dados]);
  const reserva = useMemo(() => reservaDe(dados?.fundo_reserva ?? 0, sugestao), [dados, sugestao]);
  const resumo = useMemo(() => (dados ? resumoCaixa(dados, reserva) : null), [dados, reserva]);
  const sim = useMemo(() => (simAtiva && serie.length
    ? simularCompra(serie, { valor: lerValorBR(simValor), data: simData, parcelas: Number(simParc) }, hoje, reserva.valor)
    : null), [simAtiva, serie, simValor, simData, simParc, hoje, reserva.valor]);
  const periodos = useMemo(() => linhaDoTempo(serie, vis), [serie, vis]);
  const contas = dados?.contas ?? [];
  const pendentes = dados?.saldo_abertura_pendente ?? [];
  const saldoPendente = !!dados?.regras_v2 && (pendentes.length > 0 || contas.length === 0);
  const temAlgo = !!dados && (contas.length > 0 || serie.some((p) => p.entradas || p.saidas) || Math.abs(dados.saldo_inicial) > 0.004);
  const estado = !dados && !erro ? "carregando" : erro && !dados ? "erro" : !temAlgo ? "vazio" : "ok";

  // Detalhe de um período (?det=ini~fim): os compromissos dia a dia.
  const [detIni, detFim] = det.includes("~") ? det.split("~") : [det, det];
  const diasDet = det ? serie.filter((p) => p.data >= detIni && p.data <= detFim && p.itens.length) : [];
  const abrirPeriodo = (p: { ini: string; fim: string }) => abrirDet(`${p.ini}~${p.fim}`);
  const periodoDe = (data: string): PeriodoCaixa | undefined => periodos.find((p) => p.ini <= data && data <= p.fim);
  const nomeDet = det ? (detIni === detFim ? `${diaSemana(detIni)} ${dmy(detIni)}` : `${dm(detIni)} a ${dm(detFim)}`) : "";

  const r = resumo;
  const marcos = useMemo(() => serie.filter((p) => p.itens.some((i) => i.fatura_cartao)).map((p) => ({ data: p.data, texto: "vencimento da fatura do cartão" })), [serie]);

  const kpis: KpiDef[] = r ? [
    {
      chave: "menor", rotulo: `Menor saldo nos próximos ${dias} dias`, valor: r.menor.saldo, formato: "brl0", bom: "neutro", negativoEmVermelho: true,
      selo: r.primeiroNegativo ? <span className="rl-selo" style={{ borderColor: "var(--st-venc-line)", background: "var(--st-venc-bg)", color: "var(--st-venc-fg)" }}><CircleAlert size={12} aria-hidden /> aperta em {dm(r.primeiroNegativo)}</span> : undefined,
      sub: <>{diaSemana(r.menor.data)}, {dmy(r.menor.data)} · {r.primeiroNegativo ? `fica negativo a partir de ${dm(r.primeiroNegativo)}` : "não fica negativo"}{reserva.valor > 0 ? ` · reserva${reserva.origem === "sugerida" ? " sugerida" : ""} ${brl0(reserva.valor)}` : ""}</>,
      onAbrir: () => { const p = periodoDe(r.menor.data); if (p) abrirPeriodo(p); },
    },
    {
      chave: "hoje", rotulo: "Saldo hoje", valor: r.saldoHoje, formato: "brl0", bom: "neutro", negativoEmVermelho: true,
      selo: saldoPendente ? <span className="rl-selo"><AlertTriangle size={12} aria-hidden /> sem saldo de abertura</span> : undefined,
      sub: saldoPendente ? "Só a soma dos lançamentos: informe o saldo de abertura para valer o do banco" : contas.length ? contas.map((c) => `${c.nome.split(" · ")[0]} ${brl0(c.saldo)}`).join(" · ") : "Todas as contas bancárias",
      onAbrir: () => document.getElementById("rl-cx-contas")?.scrollIntoView({ behavior: "smooth", block: "start" }),
    },
    {
      chave: "folego", rotulo: "Fôlego", valor: folego?.folego_dias ?? null, formato: "num0", unidade: " dias", bom: "neutro",
      sub: folego?.saida_media_diaria ? `Saldo ÷ ${brl0(folego.saida_media_diaria)}/dia de saída média nos últimos ${folego.dias_janela} dias` : "Sem saídas nos últimos 90 dias para medir",
    },
    {
      chave: "pagar", rotulo: "A pagar × a receber", valor: r.saidas, formato: "brl0", bom: "neutro",
      sub: <>A pagar em {dias} dias · a receber <b style={{ color: "var(--text)" }}>{brl0(r.entradas)}</b> · {r.entradas - r.saidas >= 0 ? "sobra" : "falta"} {brl0(Math.abs(r.entradas - r.saidas))}</>,
      onAbrir: () => document.getElementById("rl-cx-linha")?.scrollIntoView({ behavior: "smooth", block: "start" }),
    },
  ] : [];

  // O que mais pesa nos 12 dias antes do 1º negativo (alerta calmo).
  const aperto = r?.primeiroNegativo ? serie.filter((p) => p.data >= somaDias(r.primeiroNegativo!, -12) && p.data <= r.primeiroNegativo!)
    .flatMap((p) => agruparItens(p.itens).filter((i) => !i.entra).map((i) => ({ ...i, data: p.data })))
    .sort((a, b) => b.valor - a.valor).slice(0, 3) : [];

  const avisos = dados && (<>
    {saldoPendente && (
      <div className="rl-aviso" role="status"><AlertTriangle size={18} aria-hidden /><div>
        <b>Informe o saldo de abertura{pendentes.length ? ` de ${pendentes.map((c) => c.nome.split(" · ")[0]).join(", ")}` : ""}</b>
        <p>O saldo do extrato numa data. Sem ele, o “saldo hoje” é só a soma dos lançamentos ({brl(dados.saldo_inicial)}) e não bate com o banco.{" "}
          <a href="/parametros?sub=financeiro&pf=contas">Gravar em Parâmetros financeiros › Conta corrente</a>.</p>
      </div></div>
    )}
    {r?.primeiroNegativo && (
      <div className="rl-aviso" role="status"><CalendarClock size={18} aria-hidden /><div>
        <b>Com calma: o caixa aperta em {dm(r.primeiroNegativo)}, daqui a {Math.max(0, serie.findIndex((p) => p.data === r.primeiroNegativo))} dias.</b>
        <p>Fica abaixo de zero {r.voltaPositivo ? `até ${dm(somaDias(r.voltaPositivo, -1))} e volta em ${dm(r.voltaPositivo)}` : `até o fim da janela de ${dias} dias`}.
          {aperto.length > 0 && <> O que mais pesa antes disso: {aperto.map((x) => `${x.nome} (${brl0(x.valor)}, ${dm(x.data)})`).join("; ")}.</>}{" "}
          Dá tempo de renegociar uma data, antecipar um recebimento ou usar a reserva.</p>
        <p><button type="button" className="lk" onClick={() => { const p = periodoDe(r.primeiroNegativo!); if (p) abrirPeriodo(p); }}>Ver o que vence nesses dias</button></p>
      </div></div>
    )}
    {!r?.primeiroNegativo && r?.primeiroAbaixoReserva && (
      <div className="rl-aviso info" role="status"><AlertTriangle size={18} aria-hidden /><div>
        <b>O saldo fura a reserva{reserva.origem === "sugerida" ? " sugerida" : ""} de {brl0(reserva.valor)} em {dm(r.primeiroAbaixoReserva)}.</b>
        <p>Ainda há dinheiro, mas a folga acabou nesse dia.</p>
      </div></div>
    )}
    {dados.compromissos_sem_vencimento > 0 && (
      <div className="rl-aviso info" role="status"><AlertTriangle size={18} aria-hidden /><div>
        <b>{dados.compromissos_sem_vencimento} conta(s) em aberto sem vencimento ficaram fora da projeção.</b>
        <p>Não há como pôr no dia certo: o caixa pode estar mais apertado do que aparece. <button type="button" className="lk" onClick={() => props.onIrRelatorio("a_pagar")}>Abrir Contas a pagar</button></p>
      </div></div>
    )}
  </>);

  const exportar = (): RelatorioParaExportar | null => {
    if (!dados || !r) return null;
    const linhas: LinhaRelatorio[] = [{ valores: [dmy(hoje), "Saldo de hoje", null, null, dados.saldo_inicial], total: true }];
    for (const p of (det ? diasDet : serie)) {
      if (!p.itens.length) continue;
      for (const it of agruparItens(p.itens)) {
        linhas.push({ valores: [dmy(p.data), `${it.nome}${it.tags.length ? ` (${it.tags.join(", ")})` : ""}`, it.entra ? it.valor : null, it.entra ? null : it.valor, null] });
      }
      linhas.push({ valores: [dmy(p.data), "Saldo no fim do dia", null, null, p.saldo], nivel: 1 });
    }
    return {
      titulo: det ? `Caixa real — ${nomeDet}` : "Caixa real", pergunta: "Quando o caixa aperta?",
      contexto: { periodo: travas.rotuloPeriodo!, comparacao: null, regime: "pelo dia do pagamento (caixa)", centro: "todas as contas bancárias" },
      colunas: [{ header: "Data", tipo: "texto" }, { header: "O quê", tipo: "texto" }, { header: "Entra", tipo: "brl" }, { header: "Sai", tipo: "brl" }, { header: "Saldo", tipo: "brl" }],
      linhas, nomeArquivoBase: "caixa_real",
      notas: [
        `Menor saldo em ${dias} dias: ${brl(r.menor.saldo)} em ${dmy(r.menor.data)}.${r.primeiroNegativo ? ` 1º dia negativo: ${dmy(r.primeiroNegativo)}.` : ""}`,
        reserva.valor > 0 ? `Reserva${reserva.origem === "sugerida" ? " sugerida" : ""}: ${brl(reserva.valor)}${reserva.meses ? ` (${reserva.meses.toLocaleString("pt-BR")} meses de saída média)` : ""}.` : "",
        folego?.folego_dias != null ? `Fôlego: ${folego.folego_dias} dias (saldo ÷ saída média diária dos últimos 90 dias).` : "",
        "Projeção do servidor (GET /financeiro/caixa-real): contas em aberto pelo vencimento (vencidas entram hoje), fatura aberta do cartão no vencimento e pagamentos agendados na data deles.",
        saldoPendente ? "Saldo de hoje sem o saldo de abertura de alguma conta: é só a soma dos lançamentos." : "",
      ].filter(Boolean),
    };
  };

  const vazioUi = (
    <VazioQueEnsina titulo="Ainda não há caixa para projetar"
      texto="O caixa real parte do saldo das contas bancárias de hoje e soma o que vence daqui para a frente. Veja o que falta:"
      itens={[
        { texto: "Conta corrente cadastrada com o saldo de abertura", pronto: contas.length > 0 && pendentes.length === 0, acao: <a href="/parametros?sub=financeiro&pf=contas">Cadastrar em Parâmetros financeiros › Conta corrente</a> },
        { texto: "Contas a pagar e a receber lançadas com vencimento", pronto: serie.some((p) => p.itens.length > 0), acao: <a href="/financeiro?sub=a_pagar">Lançar uma conta</a> },
      ]} />
  );

  const rotuloReserva = reserva.origem === "parametro" ? `Reserva: até ${brl0(reserva.valor)}${reserva.meses ? ` (${reserva.meses.toLocaleString("pt-BR")} meses de saída)` : ""}`
    : `Reserva sugerida: ${brl0(reserva.valor)} (${reserva.meses} meses de saída)`;

  return (
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Caixa" nome="Caixa real" pergunta="Quando o caixa aperta?"
      onIrGrupo={props.onIrGrupo} niveis={det ? [{ rotulo: nomeDet }] : []} onVoltarNivel={() => abrirDet("")}
      estado={estado} erro={erro} onTentarDeNovo={() => { setErro(null); setTentativa((t) => t + 1); }} vazio={vazioUi}
      frase={!det && r ? fraseCaixa(r, reserva, brl0, saldoPendente) : []} kpis={det ? undefined : kpis} avisos={det ? null : avisos} exportar={exportar}>
      <style>{CSS_CAIXA}</style>
      <div className="rl-acoes rl-noprint" role="group" aria-label="Horizonte da projeção" style={{ justifyContent: "space-between" }}>
        <div className="rl-campo" style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: ".5rem", minWidth: 0, maxWidth: "100%" }}>
          <span className="rl-rot" id="rl-cx-hor">Projetar os próximos</span>
          <div className="rl-seg" role="group" aria-labelledby="rl-cx-hor">
            {HORIZONTES.map((h) => (
              <button key={h} type="button" aria-pressed={dias === h} onClick={() => { if (h !== dias) mudarDias(h === 90 ? "" : String(h)); }}>{h} dias</button>
            ))}
          </div>
        </div>
      </div>
      {!det && r && (<>
        <PainelGrafico titulo="Saldo projetado, dia a dia"
          legenda={<LegendaSaldo reserva={reserva.valor > 0} compra={!!(sim && sim.ok)} marcos={marcos.length > 0} />}
          tabela={{ cabecalho: ["Data", "Saldo previsto", ...(sim && sim.ok ? ["Com a compra"] : [])], linhas: serie
            .map((p, i) => ({ p, i }))
            .filter(({ p, i }) => i % 7 === 0 || p.data === r.primeiroNegativo || p.data === r.menor.data || p.data === r.primeiroAbaixoReserva || i === serie.length - 1)
            .map(({ p, i }) => [dmy(p.data), brl(p.saldo), ...(sim && sim.ok ? [brl(sim.saldos[i])] : [])]) }}>
          <GraficoSaldo serie={serie} reserva={reserva.valor} rotuloReserva={rotuloReserva}
            primeiroAbaixoReserva={r.primeiroAbaixoReserva} primeiroNegativo={r.primeiroNegativo} menor={r.menor}
            comCompra={sim && sim.ok ? sim.saldos : null} marcos={marcos}
            descricao={`Saldo projetado em ${dias} dias: hoje ${brl0(r.saldoHoje)}, menor saldo ${brl0(r.menor.saldo)} em ${dm(r.menor.data)}${r.primeiroNegativo ? `, primeiro dia negativo ${dm(r.primeiroNegativo)}` : ""}${r.primeiroAbaixoReserva ? `, abaixo da reserva a partir de ${dm(r.primeiroAbaixoReserva)}` : ""}.`} />
          {reserva.origem === "sugerida" && (
            <p style={{ margin: ".4rem 0 0", fontSize: ".76rem", color: "var(--text-muted)" }}>
              A faixa usa a reserva <b>sugerida</b> pelo histórico ({sugestao?.meses_folga} meses de saída média); nenhuma reserva foi definida.{" "}
              <a href="/configuracoes?aba=parametros" style={{ color: "var(--text-accent)", fontWeight: 600 }}>Definir em Configurações › Parâmetros</a>.
            </p>
          )}
        </PainelGrafico>

        <section className="rl-painel rl-noprint" aria-labelledby="rl-cx-sim">
          <h3 className="rl-tit" id="rl-cx-sim" style={{ display: "flex", alignItems: "center", gap: ".4rem" }}><Calculator size={15} aria-hidden /> Posso comprar?</h3>
          <form className="rl-ctx-row" onSubmit={(e) => { e.preventDefault(); simular(); }} style={{ marginBottom: ".75rem" }}>
            <div className="rl-campo"><label htmlFor="rl-cx-sv">Valor total (R$)</label>
              <input id="rl-cx-sv" className="rl-in" inputMode="decimal" autoComplete="off" placeholder="ex.: 24.000,00" value={simValor} onChange={(e) => setSimValor(e.target.value)} /></div>
            <div className="rl-campo"><label htmlFor="rl-cx-sd">1ª parcela em</label>
              <input id="rl-cx-sd" className="rl-in" type="date" min={hoje} value={simData} onChange={(e) => setSimData(e.target.value)} /></div>
            <div className="rl-campo"><label htmlFor="rl-cx-sp">Parcelas mensais</label>
              <input id="rl-cx-sp" className="rl-in" type="number" min={1} max={24} value={simParc} onChange={(e) => setSimParc(e.target.value)} style={{ width: "7rem" }} /></div>
            <div className="rl-acoes">
              <button type="submit" className="btn-primary" style={{ minHeight: 36 }}>Simular</button>
              {simAtiva && <button type="button" className="rl-btn" onClick={limparSim}>Limpar</button>}
            </div>
          </form>
          <div aria-live="polite">
            {!sim && <p style={{ margin: 0, fontSize: ".84rem", color: "var(--text-muted)" }}>Informe o valor e a data da compra: a tela mostra o novo menor saldo e se a compra fura a reserva. Nada é lançado.</p>}
            {sim && !sim.ok && <p role="alert" style={{ margin: 0, color: "var(--st-venc-fg)", fontWeight: 600, display: "flex", gap: ".35rem", alignItems: "center" }}><AlertTriangle size={15} aria-hidden /> {sim.erro}</p>}
            {sim && sim.ok && <ResultadoSimulacao sim={sim} reserva={reserva.valor} reservaSugerida={reserva.origem === "sugerida"} dias={dias} />}
          </div>
        </section>
      </>)}

      {!det && r && (
        <section className="rl-painel" aria-labelledby="rl-cx-linha" id="rl-cx-linha">
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: ".5rem", marginBottom: ".6rem" }}>
            <h3 className="rl-tit" style={{ margin: 0 }}>O que entra e sai, {vis === "semana" ? "semana a semana" : "dia a dia"}</h3>
            <div className="rl-seg rl-noprint" role="group" aria-label="Agrupar a linha do tempo">
              <button type="button" aria-pressed={vis === "semana"} onClick={() => vis !== "semana" && mudarVis("")}>Por semana</button>
              <button type="button" aria-pressed={vis === "dia"} onClick={() => vis !== "dia" && mudarVis("dia")}>Por dia</button>
            </div>
          </div>
          <div className="rl-tw">
            <table className="fazenda-table rl-tab">
              <caption className="rl-sr">Linha do tempo do caixa, {vis === "semana" ? "por semana" : "por dia com movimento"}</caption>
              <thead><tr>
                <th scope="col">{vis === "semana" ? "Semana" : "Dia"}</th><th scope="col" className="r rl-cx-larga">Entra</th><th scope="col" className="r rl-cx-larga">Sai</th>
                <th scope="col" className="r">Saldo no fim</th>{vis === "semana" && <th scope="col" className="r rl-opc">Menor saldo</th>}
              </tr></thead>
              <tbody>
                <tr className="tot"><td>Hoje, {dmy(serie[0]?.data ?? hoje)}<span className="sub">saldo de abertura + o que já passou no banco</span></td><td className="rl-cx-larga" /><td className="rl-cx-larga" />
                  <td className={`r${(dados?.saldo_inicial ?? 0) < 0 ? " neg" : ""}`}>{brl(dados?.saldo_inicial ?? 0)}</td>{vis === "semana" && <td className="rl-opc" />}</tr>
                {periodos.map((p) => (
                  <tr key={p.chave} className="clic" onClick={(e) => { if (!(e.target as HTMLElement).closest("button")) abrirPeriodo(p); }}>
                    <td>
                      <button type="button" className="rl-linkbtn" onClick={() => abrirPeriodo(p)} aria-label={`${p.ini === p.fim ? dmy(p.ini) : `${dm(p.ini)} a ${dm(p.fim)}`}: abrir o que vence`}>
                        {p.ini === p.fim ? `${diaSemana(p.ini)} ${dm(p.ini)}` : `${dm(p.ini)} a ${dm(p.fim)}`}
                      </button>
                      <span className="sub">{p.itens ? `${p.itens} compromisso${p.itens > 1 ? "s" : ""}` : "nada vence"}{p.menorSaldo < 0 ? " · fica negativo" : ""}</span>
                      {(p.entradas > 0 || p.saidas > 0) && <span className="sub rl-cx-estreita">{p.entradas ? `entra ${brl(p.entradas)}` : ""}{p.entradas && p.saidas ? " · " : ""}{p.saidas ? `sai ${brl(p.saidas)}` : ""}</span>}
                    </td>
                    <td className="r rl-cx-larga">{p.entradas ? brl(p.entradas) : <span className="mut">—</span>}</td>
                    <td className="r rl-cx-larga">{p.saidas ? brl(p.saidas) : <span className="mut">—</span>}</td>
                    <td className={`r${p.saldoFim < 0 ? " neg" : ""}`}><b>{brl(p.saldoFim)}</b></td>
                    {vis === "semana" && <td className={`r rl-opc${p.menorSaldo < 0 ? " neg" : " mut"}`}>{brl(p.menorSaldo)}</td>}
                  </tr>
                ))}
                {!periodos.length && <tr><td colSpan={5} className="mut" style={{ textAlign: "center", padding: "1rem" }}>Nada vence nos próximos {dias} dias.</td></tr>}
              </tbody>
            </table>
          </div>
          {dados?.agendados_fora_da_janela?.quantidade ? (
            <p style={{ margin: ".55rem 0 0", fontSize: ".76rem", color: "var(--text-muted)" }}>
              {dados.agendados_fora_da_janela.quantidade} pagamento(s) agendado(s) depois desta janela ({brl(dados.agendados_fora_da_janela.total_saidas)} de saída, {brl(dados.agendados_fora_da_janela.total_entradas)} de entrada) não entram nela.
            </p>
          ) : null}
        </section>
      )}

      {det && (
        <section className="rl-painel" aria-labelledby="rl-cx-det">
          <h3 className="rl-tit" id="rl-cx-det">O que vence — {nomeDet}</h3>
          {diasDet.length ? (
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Compromissos de {nomeDet}</caption>
                <thead><tr><th scope="col">Dia</th><th scope="col">O quê</th><th scope="col" className="r">Entra</th><th scope="col" className="r">Sai</th></tr></thead>
                <tbody>
                  {diasDet.map((p) => (
                    <DiaDetalhe key={p.data} data={p.data} saldo={p.saldo} itens={agruparItens(p.itens)} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p style={{ margin: 0, fontSize: ".86rem", color: "var(--text-muted)" }}>Nada vence neste período.</p>}
          <div className="rl-acoes" style={{ marginTop: ".75rem" }}>
            <button type="button" className="rl-btn" onClick={() => props.onIrRelatorio("a_pagar")}><ExternalLink size={14} aria-hidden /> Abrir Contas a pagar</button>
            <button type="button" className="rl-btn" onClick={() => props.onIrRelatorio("a_receber")}><ExternalLink size={14} aria-hidden /> Abrir Contas a receber</button>
            {diasDet.some((p) => p.itens.some((i) => i.agendado)) && (
              <button type="button" className="rl-btn" onClick={() => props.onConsultas({ de: detIni, ate: detFim, periodoPor: "pagamento", origem: `Caixa real › ${nomeDet}` })}>
                <ExternalLink size={14} aria-hidden /> Ver os pagamentos agendados em Consultas
              </button>
            )}
          </div>
        </section>
      )}

      {!det && dados && (
        <div className="rl-dois">
          <section className="rl-painel" aria-labelledby="rl-cx-contas" id="rl-cx-contas">
            <h3 className="rl-tit">De onde vem o saldo de hoje</h3>
            {contas.length ? (
              <div className="rl-tw">
                <table className="fazenda-table rl-tab">
                  <caption className="rl-sr">Saldo de hoje por conta bancária</caption>
                  <thead><tr><th scope="col">Conta</th><th scope="col" className="r">Saldo hoje</th></tr></thead>
                  <tbody>
                    {contas.map((c) => {
                      const sem = c.pendente_saldo_abertura || (dados.regras_v2 && (c.saldo_abertura == null || !c.data_saldo_abertura));
                      return (
                        <tr key={c.id}>
                          <td><span style={{ display: "inline-flex", gap: ".35rem", alignItems: "center" }}><Landmark size={14} aria-hidden /> {c.nome}</span>
                            {dados.regras_v2 && (
                              <span className="sub" style={sem ? { color: "var(--st-logo-fg)" } : undefined}>
                                {sem ? <><AlertTriangle size={11} aria-hidden style={{ verticalAlign: "-1px" }} /> Informe o saldo de abertura</>
                                  : `Abertura de ${brl(c.saldo_abertura!)} em ${dmy(c.data_saldo_abertura!)} + tudo que passou na conta até hoje`}
                              </span>
                            )}
                          </td>
                          <td className={`r${c.saldo < 0 ? " neg" : ""}`}>{brl(c.saldo)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot><tr><td>Total</td><td className="r">{brl(dados.saldo_inicial)}</td></tr></tfoot>
                </table>
              </div>
            ) : <p style={{ margin: 0, fontSize: ".84rem", color: "var(--text-muted)" }}>Nenhuma conta corrente cadastrada. <a href="/parametros?sub=financeiro&pf=contas">Cadastrar</a>.</p>}
            <p style={{ margin: ".55rem 0 0", fontSize: ".76rem", color: "var(--text-muted)" }}>Pagamento com data futura não entra no saldo de hoje: aparece na projeção, no dia dele.</p>
          </section>
          <section className="rl-painel" aria-labelledby="rl-cx-res">
            <h3 className="rl-tit" id="rl-cx-res">Reserva</h3>
            {reserva.origem === "parametro" ? (<>
              <p style={{ margin: "0 0 .4rem", fontSize: "1.3rem", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{brl0(reserva.valor)}</p>
              <p style={{ margin: 0, fontSize: ".84rem", color: "var(--text-muted)" }}>
                {reserva.meses ? `Cobre ${reserva.meses.toLocaleString("pt-BR")} meses de saída média. ` : ""}
                Folga mínima na projeção: <b style={{ color: (dados.folga_minima ?? 0) < 0 ? "var(--st-venc-fg)" : "var(--text)" }}>{brl0(dados.folga_minima)}</b>
                {(dados.folga_minima ?? 0) < 0 ? " — a reserva é furada em algum dia." : " — a reserva fica intacta."}
              </p>
            </>) : reserva.origem === "sugerida" ? (<>
              <p style={{ margin: "0 0 .4rem", fontSize: ".86rem" }}>Nenhuma reserva definida. Pelo histórico, a sugestão é <b>{brl0(reserva.valor)}</b> ({reserva.meses} meses de saída média).</p>
              <p style={{ margin: 0, fontSize: ".8rem", color: "var(--text-muted)" }}>Para adotar, grave em <a href="/configuracoes?aba=parametros" style={{ color: "var(--text-accent)", fontWeight: 600 }}>Configurações › Parâmetros</a>, no campo “Caixa Real — fundo de reserva”.</p>
            </>) : (
              <p style={{ margin: 0, fontSize: ".84rem", color: "var(--text-muted)" }}>Sem reserva definida e sem histórico de saídas para sugerir uma: a tela só alerta quando o caixa fica negativo.</p>
            )}
          </section>
        </div>
      )}

      <NotasMetodo titulo="O que entra na projeção"
        entra={[
          ["Saldo de hoje", dados?.regras_v2 ? "Saldo de abertura de cada conta (o do extrato numa data) + tudo que entrou e saiu dela até hoje. Pagamento com data futura não conta." : "A soma do que entrou e saiu de cada conta bancária cadastrada."],
          ["Contas em aberto", "Pelo vencimento. Vencidas e não pagas entram hoje, marcadas “vencido”. Sem vencimento ficam de fora (o aviso diz quantas)."],
          ["Cartão de crédito", dados?.regras_v2 ? "A compra no cartão entra no vencimento da fatura, numa linha só por fatura — inclusive a fatura ainda aberta." : "Com as regras novas, a fatura aberta do cartão entra no vencimento."],
          ["Pagamento agendado", "Baixado com data futura: sai do saldo no dia dele, não hoje."],
          ["Fôlego", "Saldo de hoje ÷ saída média por dia dos últimos 90 dias: quantos dias o dinheiro de hoje paga o ritmo de gastos."],
          ["Posso comprar?", "Desconta as parcelas da série do servidor a partir do dia de cada uma. É uma simulação: nada é lançado."],
        ]}
        naoEntra={["Transferências entre contas próprias (não mudam o total).", "Desgaste dos bens (depreciação não é dinheiro).", "Vale de funcionário: o fornecedor recebe o total; o acerto é na folha."]} />
      {dados && r && (
        <Conferencia fecha={Math.abs(dados.saldo_inicial + dados.total_entradas - dados.total_saidas - dados.saldo_final) < 0.02}
          texto={`Saldo de hoje ${brl(dados.saldo_inicial)} + entradas ${brl(dados.total_entradas)} − saídas ${brl(dados.total_saidas)} = saldo em ${dm(serie[serie.length - 1]?.data ?? hoje)} (${brl(dados.saldo_final)}).`} />
      )}
    </RelatorioShell>
  );
}

function DiaDetalhe({ data, saldo, itens }: { data: string; saldo: number; itens: ReturnType<typeof agruparItens> }) {
  return (<>
    {itens.map((it, k) => (
      <tr key={it.chave}>
        <td style={{ whiteSpace: "nowrap" }}>{k === 0 ? <>{diaSemana(data)} {dm(data)}</> : <span className="rl-sr">{dm(data)}</span>}</td>
        <td>{it.nome}
          {it.tags.length > 0 && (
            <span className="sub">{it.tags.map((t) => (
              <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: ".2rem", marginRight: ".5rem", color: t.startsWith("vencido") ? "var(--st-venc-fg)" : undefined }}>
                {t.startsWith("vencido") ? <AlertTriangle size={11} aria-hidden /> : t === "pagamento agendado" ? <CalendarClock size={11} aria-hidden /> : null}{t}
              </span>
            ))}</span>
          )}
        </td>
        <td className="r">{it.entra ? brl(it.valor) : ""}</td>
        <td className="r">{it.entra ? "" : brl(it.valor)}</td>
      </tr>
    ))}
    <tr className="tot"><td colSpan={3}>Saldo no fim de {dm(data)}</td><td className={`r${saldo < 0 ? " neg" : ""}`}>{brl(saldo)}</td></tr>
  </>);
}

function ResultadoSimulacao({ sim, reserva, reservaSugerida, dias }: { sim: Extract<ReturnType<typeof simularCompra>, { ok: true }>; reserva: number; reservaSugerida: boolean; dias: number }) {
  const a = sim.menorSem, b = sim.menorCom;
  const caixa = (titulo: string, v: { saldo: number; data: string }, destaque: boolean) => (
    <div style={{ flex: "1 1 12rem", border: `1px solid ${destaque ? "var(--rl-a)" : "var(--border)"}`, borderRadius: "var(--r-sm)", padding: ".6rem .75rem", background: destaque ? "var(--surface-2)" : "var(--surface)" }}>
      <span style={{ display: "block", fontSize: ".74rem", color: "var(--text-muted)" }}>{titulo}</span>
      <b style={{ fontSize: "1.35rem", fontVariantNumeric: "tabular-nums", color: v.saldo < 0 ? "var(--st-venc-fg)" : "var(--text)" }}>{brl(v.saldo, 0)}</b>
      <span style={{ display: "block", fontSize: ".74rem", color: "var(--text-muted)" }}>em {dmy(v.data)}</span>
    </div>
  );
  const sug = reservaSugerida ? " sugerida" : "";
  const veredito = {
    pode: { icone: <CheckCircle2 size={17} aria-hidden />, cor: "var(--st-pago-fg)", txt: <><b>Pode comprar.</b> O caixa não desce {reserva > 0 ? `abaixo da reserva${sug}` : "de zero"} nos próximos {dias} dias.</> },
    reserva: { icone: <AlertTriangle size={17} aria-hidden />, cor: "var(--st-logo-fg)", txt: <><b>Dá para comprar, mas entra na reserva{sug}.</b> O menor saldo fica em {brl(b.saldo, 0)} ({dm(b.data)}), abaixo de {brl(reserva, 0)}.</> },
    negativo: { icone: <CircleAlert size={17} aria-hidden />, cor: "var(--st-venc-fg)", txt: <><b>Com a compra o caixa fica negativo</b> a partir de {dm(sim.primeiroNegativoCom!)}: menor saldo {brl(b.saldo, 0)} em {dm(b.data)}.</> },
    jaAperta: { icone: <CircleAlert size={17} aria-hidden />, cor: "var(--st-venc-fg)", txt: <><b>O caixa já aperta sem a compra.</b> Com ela, o buraco vai de {brl(a.saldo, 0)} para {brl(b.saldo, 0)} ({dm(b.data)}).</> },
  }[sim.veredito];
  return (<>
    <div style={{ display: "flex", flexWrap: "wrap", gap: ".6rem" }}>
      {caixa(`Sem a compra · menor saldo em ${dias} dias`, a, false)}
      {caixa(`Com a compra · menor saldo em ${dias} dias`, b, true)}
    </div>
    <p style={{ margin: ".7rem 0 0", display: "flex", gap: ".45rem", alignItems: "flex-start", color: veredito.cor }}>{veredito.icone}<span style={{ color: "var(--text)" }}>{veredito.txt}</span></p>
    {sim.sugestao && <p style={{ margin: ".4rem 0 0", fontSize: ".84rem" }}>Com a 1ª parcela a partir de <b>{dmy(sim.sugestao)}</b>, a compra não aprofunda o aperto.</p>}
    <p style={{ margin: ".4rem 0 0", fontSize: ".76rem", color: "var(--text-muted)" }}>
      {sim.parcelas.length > 1 ? `${sim.parcelas.length} parcelas de cerca de ${brl(sim.parcelas[0].valor)}` : `Uma parcela de ${brl(sim.parcelas[0].valor)}`}
      {sim.foraDaJanela ? `; ${sim.foraDaJanela} cai(em) depois dos ${dias} dias e não entra(m) nesta conta — aumente o horizonte para ver.` : "."}
    </p>
  </>);
}
