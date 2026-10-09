"use client";
// Relatórios › Leite › Réguas de referência — "Como estou perto das referências?"
//
// Parecer jurídico de 08/10/2026 (itens 6 e 7) manda na tela:
//   - caixa de alerta no topo com o texto da API (textos.alerta), sem lista de fontes;
//   - botão do pop-up "Como calculamos e quão confiável é" (textos.modal + quadro de
//     fontes com ano e link, sem logos); o mesmo pop-up é o "Entendi" do primeiro
//     acesso e de cada versão nova (POST do aceite com versão + SHA-256);
//   - enquanto o aceite está pendente, nenhuma faixa (a API também não manda);
//   - sem semáforo, sem verde/vermelho, sem "meta", "média", "alvo", "eficiente":
//     faixa cinza neutra e a palavra "referência"; selo e validade na própria linha;
//   - "Reportar erro na faixa"; exportação só com autorização expressa (6.2).
// O número da fazenda vem do SERVIDOR (GET …/indicadores-fazenda: mesma DRE e mesmo
// Resultado por litro do período) — nenhuma conta nova aqui. Hoje nenhuma régua está
// publicada: a tela mostra o número da fazenda e, em cada régua, o porquê.
import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import {
  AlertTriangle, BadgeCheck, ChevronRight, CircleDashed, CircleHelp, Clock, ExternalLink, Flag, Info, Scale, ShieldHalf, X,
} from "lucide-react";
import {
  aceitarAvisoReguas, fetchIndicadoresReguas, fetchReguasReferencia, reportarErroRegua,
} from "@/lib/api";
import { ESTADO_INICIAL, REGIME_API, REGIME_NOME } from "@/lib/relatorioContexto";
import {
  NOME_SELO, NOME_SITUACAO, algumaFaixaVisivel, criteriosDoSelo, escalaRegua, formatarValorRegua, fraseReguas, limiteFaixa,
  linhasExportacaoReguas, linhasReguas, paragrafos, type LinhaReguaTela, type RespostaIndicadoresReguas, type RespostaReguas,
} from "@/lib/reguasReferencia";
import { exportarRelatorioExcel, exportarRelatorioPDF, type RelatorioParaExportar } from "@/lib/export";
import { NotasMetodo, RelatorioShell } from "./RelatorioShell";
import { useContextoRelatorio, type TravasContexto } from "./useContextoRelatorio";
import { PORQUE_CENTRO_REGRAS_ANTIGAS, useRegrasV2Estado, type PropsRelatorio } from "./comum";
import { useExportacaoComReguas, type GerarExportacao } from "./useExportacaoComReguas";
import { CSS_C4 } from "./estilosC4";

const dmy = (iso: string | null | undefined) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—");
const ICONE_SELO = { alta: BadgeCheck, media: ShieldHalf, baixa: CircleHelp } as const;
const ICONE_SITUACAO = { publicada: Scale, em_validacao: Clock, retirada: CircleDashed, vencida: Clock, sem_faixa: Info } as const;

export default function ReguasReferenciaView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const regras = useRegrasV2Estado();
  const travas: TravasContexto = useMemo(() => (regras.ativa === false
    ? { cc: "todos", cmpOrcado: false, porque: PORQUE_CENTRO_REGRAS_ANTIGAS }
    : { cmpOrcado: false }), [regras.ativa]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const { periodo, comparacao, efetivo } = ctx;

  const [reguas, setReguas] = useState<RespostaReguas | null>(null);
  const [ind, setInd] = useState<RespostaIndicadoresReguas | null>(null);
  const [indCmp, setIndCmp] = useState<RespostaIndicadoresReguas | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const [popup, setPopup] = useState<{ aberto: boolean; foco?: string }>({ aberto: false });
  const [aceiteAdiado, setAceiteAdiado] = useState(false);
  const [reportar, setReportar] = useState<LinhaReguaTela | null>(null);
  const [impressao, setImpressao] = useState<{ com: boolean; rodape: string | null } | null>(null);
  const cmpPeriodo = comparacao && comparacao.tipo === "periodo" ? comparacao.periodo : null;
  const centroApi = efetivo.cc === "todos" ? null : efetivo.cc;

  const carregarReguas = useCallback(() => fetchReguasReferencia().then((r) => { setReguas(r); return r; }), []);
  useEffect(() => {
    let vivo = true;
    fetchReguasReferencia().then((r) => { if (vivo) setReguas(r); }).catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [tentativa]);
  useEffect(() => {
    if (regras.ativa === null) return;
    let vivo = true;
    const base = { regime: REGIME_API[efetivo.reg], centro_custo: centroApi, hoje };
    Promise.all([
      fetchIndicadoresReguas({ ...base, data_inicio: periodo.ini, data_fim: periodo.fim }),
      cmpPeriodo ? fetchIndicadoresReguas({ ...base, data_inicio: cmpPeriodo.ini, data_fim: cmpPeriodo.fim }) : Promise.resolve(null),
    ]).then(([a, b]) => { if (vivo) { setInd(a); setIndCmp(b); setErro(null); } })
      .catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [regras.ativa, periodo.ini, periodo.fim, cmpPeriodo?.ini, cmpPeriodo?.fim, efetivo.reg, centroApi, hoje, tentativa]); // eslint-disable-line react-hooks/exhaustive-deps

  // Primeiro acesso (ou texto novo = hash novo): o pop-up abre sozinho com o "Entendi".
  const precisaAceite = !!reguas?.aceite_pendente && !aceiteAdiado;
  const linhas = useMemo(() => linhasReguas(reguas, ind), [reguas, ind]);
  const temFaixa = algumaFaixaVisivel(reguas);
  const rotuloCmp = cmpPeriodo ? comparacao!.rotulo : null;
  const estado = regras.ativa === null || ((!reguas || !ind) && !erro) ? "carregando" : erro && (!reguas || !ind) ? "erro" : "ok";

  const montarExportacao = (comReguas: boolean, rodape: string | null): RelatorioParaExportar => ({
    titulo: "Réguas de referência", pergunta: "Como estou perto das referências?",
    contexto: { periodo: periodo.label, comparacao: null, regime: REGIME_NOME[efetivo.reg], centro: efetivo.cc === "todos" ? "todos os centros" : efetivo.cc },
    colunas: [
      { header: "Indicador", tipo: "texto", width: 34 }, { header: "Número da fazenda", tipo: "texto", width: 20 },
      ...(comReguas ? [{ header: "Faixa de referência", tipo: "texto" as const, width: 34 }] : []),
      { header: "Como foi calculado", tipo: "texto", width: 52 },
    ],
    linhas: linhasExportacaoReguas(linhas, comReguas).map((v) => ({ valores: v })),
    notas: comReguas ? [] : ["Exportado sem as réguas de referência: só os números da fazenda, calculados com a DRE e o Resultado por litro do período."],
    nomeArquivoBase: "reguas_referencia",
    rodapeReguas: comReguas ? rodape : null,
  });
  const gerar: GerarExportacao = async (tipo, o) => {
    if (tipo === "imprimir") {
      setImpressao({ com: o.comReguas, rodape: o.rodape });
      // Espera o rodapé entrar na tela (mesmo bloco das réguas) antes de abrir a impressão.
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      window.print();
      return;
    }
    const r = montarExportacao(o.comReguas, o.rodape);
    if (tipo === "excel") await exportarRelatorioExcel(r); else await exportarRelatorioPDF(r);
  };
  useEffect(() => {
    if (!impressao) return;
    const fim = () => setImpressao(null);
    window.addEventListener("afterprint", fim);
    return () => window.removeEventListener("afterprint", fim);
  }, [impressao]);
  const exp = useExportacaoComReguas({
    relatorio: "reguas_referencia", temReguas: temFaixa, permitir: !!reguas?.exportacao?.permitir_com_reguas,
    modeloAutorizacao: reguas?.textos.exportacao_autorizacao?.texto, rotuloParametro: reguas?.textos.compartilhamento_parametro?.texto, gerar,
  });

  const frase = linhas.length ? [{ t: fraseReguas(linhas, periodo.label) }] : [];
  const criterios = criteriosDoSelo(reguas?.textos.modal?.texto);

  return (
    <>
      <style>{CSS_C4}</style>
      <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Leite" nome="Réguas de referência" pergunta="Como estou perto das referências?"
        onIrGrupo={props.onIrGrupo} estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => { setErro(null); setTentativa((t) => t + 1); }}
        frase={frase} exportar={() => montarExportacao(false, null)} aoExportar={exp.aoExportar}
        avisos={reguas ? (
          <CaixaAlerta reguas={reguas} temFaixa={temFaixa} pendente={reguas.aceite_pendente}
            onAbrir={() => setPopup({ aberto: true })} />
        ) : null}>
        <section className="rl-painel" aria-labelledby="rg-tit">
          <h3 className="rl-tit" id="rg-tit">Réguas · {periodo.curto}</h3>
          <div className="rg-leg" aria-hidden>
            {temFaixa && <span className="rg-faixa"><i style={{ background: "var(--rl-n3)" }} />Faixa de referência (cinza, não é meta)</span>}
            <span><svg width="14" height="14"><path d="M7 13 1 2h12z" style={{ fill: "var(--rl-a)" }} /></svg>Fazenda em {periodo.curto}</span>
            {rotuloCmp && <span><svg width="14" height="14"><circle cx="7" cy="7" r="5" style={{ fill: "var(--surface)", stroke: "var(--text-muted)", strokeWidth: 2 }} /></svg>{rotuloCmp}</span>}
          </div>
          <div className="rg-lista" data-impressao={impressao?.com ? "com" : "sem"}>
            {temFaixa && <p className="rg-so-sem">Impresso sem as faixas de referência. Para imprimir com elas, use o botão Imprimir desta tela e autorize o envio.</p>}
            {linhas.map((l) => (
              <LinhaRegua key={l.regua.codigo} l={l} reguas={reguas!} criterio={l.regua.fidedignidade ? criterios[l.regua.fidedignidade] : undefined}
                cmp={indCmp?.indicadores[l.regua.codigo]?.valor ?? null} rotuloCmp={rotuloCmp}
                onFontes={() => setPopup({ aberto: true, foco: l.regua.codigo })} onReportar={() => setReportar(l)}
                onRelatorio={(id) => props.onIrRelatorio(id)} />
            ))}
            {impressao?.com && impressao.rodape && <p className="rg-rodape">{impressao.rodape}</p>}
          </div>
        </section>
        <NotasMetodo titulo="De onde vem cada número desta tela"
          entra={[
            ["Número da fazenda", "Calculado pelo servidor com a DRE e o Resultado por litro do mesmo período, regime e centro (as mesmas linhas dos outros relatórios). A conta aparece embaixo de cada número."],
            ["Faixa de referência", "Vem da versão das réguas conferida todo mês. Só aparece quando a régua está liberada, depois que você confirma o aviso, e dentro da validade de 12 meses."],
            ["Situação de cada régua", "Publicada, em validação (ainda não liberada), retirada, vencida ou sem faixa. Fora de “publicada” nenhum número de faixa chega à tela."],
          ]}
          naoEntra={["Dados de outros clientes do CowData: não entram nas faixas.", "Logos das fontes: as fontes são citadas só pelo nome, ano e link, no quadro de fontes."]} />
      </RelatorioShell>
      {reguas && (popup.aberto || precisaAceite) && (
        <DialogoComoCalculamos reguas={reguas} foco={popup.foco} pedeAceite={reguas.aceite_pendente}
          onFechar={(aceitou) => {
            setPopup({ aberto: false });
            if (!aceitou && reguas.aceite_pendente) setAceiteAdiado(true);
          }}
          onAceito={async () => { const r = await carregarReguas(); setAceiteAdiado(false); return r; }} />
      )}
      {reportar && <DialogoReportar linha={reportar} versao={reguas?.versao_reguas ?? ""} onFechar={() => setReportar(null)} />}
      {exp.dialogo}
    </>
  );
}

function CaixaAlerta({ reguas, temFaixa, pendente, onAbrir }: { reguas: RespostaReguas; temFaixa: boolean; pendente: boolean; onAbrir: () => void }) {
  const ps = paragrafos(reguas.textos.alerta?.texto);
  return (
    <section className="rg-alerta" aria-labelledby="rg-alerta-t">
      {/* Texto 7.1 exatamente como a API manda (o primeiro parágrafo é o título). */}
      <p className="rg-alerta-t" id="rg-alerta-t"><AlertTriangle size={18} aria-hidden />{ps[0]}</p>
      {ps.slice(1).map((p, i) => <p key={i}>{p}</p>)}
      <p className="rg-datas">
        Versão {reguas.versao_reguas} · próxima conferência {dmy(reguas.proxima_conferencia)} · válida até {dmy(reguas.valido_ate)}
      </p>
      <div className="rg-acoes">
        <button type="button" className="rl-btn" onClick={onAbrir}><Info size={15} aria-hidden /> Como calculamos e quão confiável é</button>
        {!temFaixa && (
          <span className="rg-estado" role="status">
            <Clock size={13} aria-hidden />
            {pendente ? "Confirme o aviso para ver as faixas liberadas" : reguas.vencida ? "Validade vencida: faixas escondidas" : "Nenhuma faixa liberada nesta versão"}
          </span>
        )}
      </div>
    </section>
  );
}

function LinhaRegua({ l, reguas, criterio, cmp, rotuloCmp, onFontes, onReportar, onRelatorio }: {
  l: LinhaReguaTela; reguas: RespostaReguas; criterio?: string; cmp: number | null; rotuloCmp: string | null;
  onFontes: () => void; onReportar: () => void; onRelatorio: (id: string) => void;
}) {
  const r = l.regua, v = l.indicador?.valor ?? null;
  const IconeSit = ICONE_SITUACAO[r.situacao] ?? Info;
  const IconeSelo = r.fidedignidade ? ICONE_SELO[r.fidedignidade] : null;
  const temNumero = v != null;
  return (
    <div className="rg-linha" id={`rg-${r.codigo}`}>
      <div className="rg-nome">
        <b>{r.nome}</b>
        <small>{r.definicao_cowdata}</small>
        <div className="rg-meta">
          {l.faixaVisivel && IconeSelo && r.fidedignidade ? (<>
            <span className="rg-selo rg-faixa"><IconeSelo size={12} aria-hidden />Confiabilidade {NOME_SELO[r.fidedignidade].toLowerCase()}</span>
            <span className="rg-faixa">compilada em {dmy(r.compilado_em)} · válida até {dmy(r.vence_em)}</span>
          </>) : (
            <span className="rg-estado"><IconeSit size={12} aria-hidden />{NOME_SITUACAO[r.situacao]}</span>
          )}
        </div>
        {l.faixaVisivel && criterio && <span className="rg-crit rg-faixa">{NOME_SELO[r.fidedignidade!]}: {criterio}</span>}
        {l.faixaVisivel && (
          <div className="rg-meta rl-noprint">
            <button type="button" className="rg-lk" onClick={onFontes}>Quadro de fontes ({r.fontes.length})</button>
            <button type="button" className="rg-lk" onClick={onReportar}><Flag size={12} aria-hidden /> Reportar erro na faixa</button>
          </div>
        )}
      </div>
      <div className="rg-trilho">
        <Trilho l={l} reguas={reguas} cmp={cmp} rotuloCmp={rotuloCmp} />
        {l.faixaVisivel && l.faixaTexto && <p className="rg-ressalva rg-faixa"><b>{l.faixaTexto[0].toUpperCase() + l.faixaTexto.slice(1)}</b>{r.ressalva ? ` · ${r.ressalva}` : ""}</p>}
        {l.porque && <p className="rg-porque"><Info size={13} aria-hidden />{l.porque}</p>}
      </div>
      <div className="rg-valor">
        <span className="v">{l.valorTexto}</span>
        {temNumero ? <span className="p"><Info size={12} aria-hidden />{l.faixaVisivel ? <><span className="rg-faixa">{l.posicao}</span><span className="rg-so-sem">número da fazenda</span></> : "número da fazenda"}</span> : null}
        {temNumero && l.indicador?.conta && <span className="c">{l.indicador.conta}</span>}
        {!temNumero && l.indicador?.motivo && <span className="c">{l.indicador.motivo}</span>}
        {rotuloCmp && cmp != null && <span className="q">{rotuloCmp}: {formatarValorRegua(r.unidade, cmp)}</span>}
        {temNumero && l.indicador?.relatorio && (
          <button type="button" className="rg-lk rl-noprint" style={{ marginTop: ".3rem" }} onClick={() => onRelatorio(l.indicador!.relatorio!)}>
            Ver no relatório <ChevronRight size={12} aria-hidden />
          </button>
        )}
      </div>
    </div>
  );
}

/** Trilho cinza; faixa de referência em cinza mais escuro (só quando liberada); marcador da fazenda. Nunca verde/vermelho. */
function Trilho({ l, reguas, cmp, rotuloCmp }: { l: LinhaReguaTela; reguas: RespostaReguas; cmp: number | null; rotuloCmp: string | null }) {
  const r = l.regua, v = l.indicador?.valor ?? null;
  const vals = [v, cmp].filter((x): x is number => x != null);
  const esc = escalaRegua(r, vals.length ? (v ?? cmp) : null, reguas);
  if (!esc) return <p className="rg-porque" style={{ marginTop: 0 }}>Sem número da fazenda neste período para pôr no trilho.</p>;
  const lo = Math.min(esc.min, ...vals), hi = Math.max(esc.max, ...vals);
  const W = 460, H = 56, x = (t: number) => 8 + ((Math.min(Math.max(t, lo), hi) - lo) / (hi - lo || 1)) * (W - 16);
  const f = l.faixaVisivel ? r.faixa! : null;
  const a = f ? (f.min ?? lo) : 0, b = f ? (f.max ?? hi) : 0;
  const aria = `${r.nome}: fazenda em ${formatarValorRegua(r.unidade, v)}${l.faixaVisivel ? `; ${l.faixaTexto}; ${l.posicao}` : "; sem faixa de referência nesta versão"}.`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={aria}>
      <rect x={8} y={22} width={W - 16} height={10} style={{ fill: "var(--surface-2)", stroke: "var(--border)" }} />
      {f && (
        <g className="rg-faixa">
          <rect x={x(a)} y={22} width={Math.max(2, x(b) - x(a))} height={10} style={{ fill: "var(--rl-n3)" }} />
          {f.min != null && <><line x1={x(f.min)} x2={x(f.min)} y1={19} y2={35} style={{ stroke: "var(--text-muted)" }} /><text x={x(f.min)} y={48} textAnchor="middle">{limiteFaixa(r.unidade, f.min)}</text></>}
          {f.max != null && <><line x1={x(f.max)} x2={x(f.max)} y1={19} y2={35} style={{ stroke: "var(--text-muted)" }} /><text x={x(f.max)} y={48} textAnchor="middle">{f.min == null ? "até " : ""}{limiteFaixa(r.unidade, f.max)}</text></>}
        </g>
      )}
      {cmp != null && (
        <circle cx={x(cmp)} cy={27} r={6} style={{ fill: "var(--surface)", stroke: "var(--text-muted)", strokeWidth: 2 }}>
          <title>{`${rotuloCmp ?? "Comparação"}: ${formatarValorRegua(r.unidade, cmp)}`}</title>
        </circle>
      )}
      {v != null && (
        <g>
          <path d={`M${x(v)} 20 l-7 -12 h14 z`} style={{ fill: "var(--rl-a)" }} />
          <rect x={x(v) - 1.5} y={18} width={3} height={18} style={{ fill: "var(--rl-a)" }} />
        </g>
      )}
    </svg>
  );
}

/** Pop-up 7.2 "Como calculamos e quão confiável é" — e o modal "Entendi" (6.1.3) do primeiro acesso / versão nova. */
function DialogoComoCalculamos({ reguas, foco, pedeAceite, onFechar, onAceito }: {
  reguas: RespostaReguas; foco?: string; pedeAceite: boolean; onFechar: (aceitou: boolean) => void; onAceito: () => Promise<RespostaReguas>;
}) {
  const uid = useId();
  const ref = useRef<HTMLDialogElement>(null);
  const tituloRef = useRef<HTMLHeadingElement>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [atual, setAtual] = useState(reguas);
  const modal = atual.textos.modal;
  const publicadas = atual.reguas.filter((r) => r.situacao === "publicada" && r.exibir_faixa && r.fontes.length);
  const criterios = criteriosDoSelo(modal?.texto);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    const alvo = foco ? d?.querySelector<HTMLElement>(`#rf-${foco}`) : null;
    if (alvo) { alvo.scrollIntoView({ block: "center" }); alvo.focus({ preventScroll: true }); } else tituloRef.current?.focus();
  }, [foco]);
  const fechar = (aceitou: boolean) => { ref.current?.close(); onFechar(aceitou); };
  const entendi = async () => {
    setEnviando(true);
    setErro(null);
    try {
      await aceitarAvisoReguas(atual.aceite.versao, atual.aceite.sha256);
      await onAceito();
      fechar(true);
    } catch (e) {
      // 409: o texto mudou enquanto a tela estava aberta — recarrega e mostra o texto novo.
      try { setAtual(await onAceito()); } catch { /* mantém o texto atual */ }
      setErro(`${(e as Error).message} Leia o texto de novo e confirme.`);
    } finally {
      setEnviando(false);
    }
  };
  return (
    <dialog ref={ref} className="c4-dlg" aria-labelledby={`${uid}-t`} onCancel={(e) => { e.preventDefault(); fechar(false); }}>
      <div className="c4-h">
        <h2 id={`${uid}-t`} ref={tituloRef} tabIndex={-1}>Como calculamos e quão confiável é</h2>
        <button type="button" className="rl-btn" onClick={() => fechar(false)} aria-label={pedeAceite ? "Fechar sem confirmar (as faixas continuam escondidas)" : "Fechar"}>
          <X size={15} aria-hidden /> Fechar
        </button>
      </div>
      <div className="c4-b">
        {/* Texto 7.2 exatamente como a API manda; cada bloco começa pelo título dele. */}
        {paragrafos(modal?.texto).map((p, i) => {
          const [t, ...resto] = p.split("\n");
          return <p key={i} className="c4-txt"><b>{t}</b>{resto.join("\n")}</p>;
        })}
        <section aria-labelledby={`${uid}-q`}>
          <h3 id={`${uid}-q`}>Quadro de fontes</h3>
          {publicadas.length ? (
            <div className="rl-tw">
              <table className="fazenda-table rl-tab">
                <caption className="rl-sr">Fontes de cada régua liberada, com ano e link</caption>
                <thead><tr><th scope="col">Régua</th><th scope="col">Confiabilidade</th><th scope="col">Fontes (ano · link)</th></tr></thead>
                <tbody>
                  {publicadas.map((r) => (
                    <tr key={r.codigo} id={`rf-${r.codigo}`} tabIndex={-1}>
                      <th scope="row" style={{ textAlign: "left", fontWeight: 600, verticalAlign: "top" }}>{r.nome}<span className="sub" style={{ display: "block", fontWeight: 400, fontSize: ".74rem", color: "var(--text-muted)" }}>válida até {dmy(r.vence_em)}</span></th>
                      <td style={{ verticalAlign: "top" }}>{r.fidedignidade ? <>{NOME_SELO[r.fidedignidade]}{criterios[r.fidedignidade] ? <span style={{ display: "block", fontSize: ".74rem", color: "var(--text-muted)" }}>{criterios[r.fidedignidade]}</span> : null}</> : "—"}</td>
                      <td style={{ verticalAlign: "top" }}>
                        <ul style={{ margin: 0, paddingLeft: "1rem", display: "flex", flexDirection: "column", gap: ".3rem" }}>
                          {r.fontes.map((f) => (
                            <li key={f.id}>
                              {f.nome}{f.ano && !f.nome.includes(String(f.ano)) ? ` (${f.ano})` : ""} · {f.origem === "nacional" ? "nacional" : "internacional"}
                              {f.url && <> · <a href={f.url} target="_blank" rel="noopener noreferrer" style={{ whiteSpace: "nowrap" }}>abrir <ExternalLink size={11} aria-hidden style={{ verticalAlign: "-1px" }} /><span className="rl-sr"> {f.nome} (nova aba)</span></a></>}
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="c4-info" style={{ margin: 0 }}><Info size={16} aria-hidden />
              <span>{atual.aceite_pendente
                ? "As fontes de cada faixa aparecem aqui depois que você confirmar este aviso."
                : "Nenhuma faixa está liberada nesta versão, por isso o quadro de fontes está vazio. Cada faixa entra aqui com as fontes, o ano e o link quando for liberada."}</span>
            </p>
          )}
        </section>
        {erro && <div className="c4-erro" role="alert"><AlertTriangle size={16} aria-hidden /><span>{erro}</span></div>}
        {pedeAceite && modal?.disponivel_para_aceite === false && (
          <p className="c4-info" style={{ margin: 0 }}><Info size={16} aria-hidden /><span>{modal.pendente || "Este aviso ainda não pode ser confirmado."}</span></p>
        )}
      </div>
      <div className="c4-p">
        {pedeAceite && modal?.disponivel_para_aceite !== false ? (<>
          <button type="button" className="rl-btn" onClick={() => fechar(false)}>Agora não</button>
          <button type="button" className="c4-btn-pri" onClick={entendi} disabled={enviando}>{enviando ? "Registrando…" : modal?.botao || "Entendi"}</button>
        </>) : (
          <button type="button" className="c4-btn-pri" onClick={() => fechar(false)}>Fechar</button>
        )}
      </div>
    </dialog>
  );
}

function DialogoReportar({ linha, versao, onFechar }: { linha: LinhaReguaTela; versao: string; onFechar: () => void }) {
  const uid = useId();
  const ref = useRef<HTMLDialogElement>(null);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [feito, setFeito] = useState<string | null>(null);
  useEffect(() => { const d = ref.current; if (d && !d.open) d.showModal(); }, []);
  const fechar = () => { ref.current?.close(); onFechar(); };
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (texto.trim().length < 3 || enviando) return;
    setEnviando(true); setErro(null);
    try {
      const r = await reportarErroRegua(linha.regua.codigo, texto.trim());
      setFeito(`Recebido (nº ${r.id}). A equipe do CowData confere a faixa e responde por aqui; se o erro se confirmar, a faixa sai da tela até ser corrigida.`);
    } catch (err) { setErro((err as Error).message); } finally { setEnviando(false); }
  };
  return (
    <dialog ref={ref} className="c4-dlg rg-reportar" aria-labelledby={`${uid}-t`} onCancel={(e) => { e.preventDefault(); fechar(); }}>
      <form onSubmit={enviar}>
        <div className="c4-h">
          <h2 id={`${uid}-t`}>Reportar erro na faixa</h2>
          <button type="button" className="rl-btn" onClick={fechar}><X size={15} aria-hidden /> Fechar</button>
        </div>
        <div className="c4-b">
          <p style={{ margin: 0 }}><b>{linha.regua.nome}</b> · versão {versao}</p>
          {feito ? <p className="c4-info" role="status" style={{ margin: 0 }}><BadgeCheck size={16} aria-hidden /><span>{feito}</span></p> : (
            <div className="c4-campo">
              <label htmlFor={`${uid}-txt`}>O que está errado? (fonte, número, link, conta)</label>
              <textarea id={`${uid}-txt`} required minLength={3} maxLength={1000} value={texto} onChange={(e) => setTexto(e.target.value)} />
              <span style={{ fontSize: ".74rem", color: "var(--text-muted)" }}>{texto.length} de 1000 caracteres. Não escreva CPF nem dado pessoal.</span>
            </div>
          )}
          {erro && <div className="c4-erro" role="alert"><AlertTriangle size={16} aria-hidden /><span>{erro}</span></div>}
        </div>
        <div className="c4-p">
          {feito ? <button type="button" className="c4-btn-pri" onClick={fechar}>Fechar</button> : (<>
            <button type="button" className="rl-btn" onClick={fechar}>Cancelar</button>
            <button type="submit" className="c4-btn-pri" disabled={texto.trim().length < 3 || enviando}><Flag size={14} aria-hidden /> {enviando ? "Enviando…" : "Enviar"}</button>
          </>)}
        </div>
      </form>
    </dialog>
  );
}
