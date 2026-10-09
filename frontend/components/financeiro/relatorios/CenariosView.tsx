"use client";
// Relatórios › Plano › Cenários — "E se…?" (Fase C). Uma tabela editável no
// topo: a coluna Real (do servidor) e até 3 cenários nomeados, com valores
// ABSOLUTOS e "voltar ao real" por campo; embaixo, o resultado de cada cenário
// × real (seta + melhor/pior) e o saldo de caixa de 12 meses a partir do saldo
// de hoje do Caixa real. Os cenários ficam neste navegador, por fazenda (ver
// lib/relatorioCenarios.ts); os cenários por conta (PlanejamentoCenario,
// Importar para Pedidos) continuam na tela anterior.
import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { AlertTriangle, ArrowRight, Calculator, Plus, RotateCcw, Undo2, X } from "lucide-react";
import { fetchCaixaReal, fetchDreCascata, fetchEstratificacaoRebanho, fetchResultadoPorLitro, getFazendaAtual } from "@/lib/api";
import { ESTADO_INICIAL, brl, brlSinal, delta, mesCurto, mesLongo, num, MENOS } from "@/lib/relatorioContexto";
import { temResultadoPorLitro } from "@/lib/relatorioLitro";
import {
  CAMPOS, MAX_CENARIOS, SAIDAS, ajustarMes, arredondar, calcular, cenariosExemplo, chaveArmazenamento, lerCampo, lerCenarios, mesesProjecao,
  periodoBaseReal, realDe, valoresBase, type Campo, type Cenario, type FontesReal, type Real, type Resultado, type Saida, type Valores,
} from "@/lib/relatorioCenarios";
import type { RelatorioParaExportar } from "@/lib/export";
import { Conferencia, NotasMetodo, PainelGrafico, RelatorioShell } from "./RelatorioShell";
import { GraficoSaldo, LegendaSaldo, type SerieSaldo } from "./graficosPlano";
import { CSS_PLANO } from "./estilosPlano";
import { useContextoRelatorio, type TravasContexto } from "./useContextoRelatorio";
import { useRegrasV2Estado, type PropsRelatorio } from "./comum";

type Num = Exclude<keyof Valores, "mes">;
const FMT: Record<Saida["f"], (v: number) => string> = {
  brl0: (v) => brl(v, 0), brl: (v) => brl(v, 2), pct: (v) => `${v < 0 ? MENOS : ""}${num(v * 100, 1)}%`,
  n1: (v) => num(v, 1), n0: (v) => `${v < 0 ? MENOS : ""}${num(v, 0)}`, x: (v) => `${num(v, 1)}×`,
};
const FMT_D: Record<Saida["f"], (v: number) => string> = {
  brl0: (v) => brlSinal(v, 0), brl: (v) => brlSinal(v, 2), pct: (v) => `${v > 0 ? "+" : MENOS}${num(v * 100, 1)} p.p.`,
  n1: (v) => `${v > 0 ? "+" : MENOS}${num(v, 1)}`, n0: (v) => `${v > 0 ? "+" : MENOS}${num(v, 0)}`, x: (v) => `${v > 0 ? "+" : MENOS}${num(v, 1)}×`,
};
const fmtCampo = (c: Campo, v: number) => (c.pct ? num(v * 100, c.casas) : num(v, c.casas));
const textoCampo = (c: Campo, v: number) => `${v < 0 ? "-" : ""}${fmtCampo(c, Math.abs(v))}`;
const ESTILOS: SerieSaldo["estilo"][] = ["a", "b", "c"];

export default function CenariosView(props: PropsRelatorio) {
  const { hoje, centros, ccPadrao } = props;
  const regras = useRegrasV2Estado();
  const base = useMemo(() => periodoBaseReal(hoje), [hoje]);
  const ccReal = regras.ativa ? ccPadrao : "todos";
  const travas: TravasContexto = useMemo(() => ({
    per: base.cod, cmp: "nada", reg: "comp", cc: ccReal,
    porque: `Os cenários usam como Real a média dos últimos 3 meses fechados${ccReal !== "todos" ? `, centro ${ccReal}` : ""} e partem do saldo de hoje do Caixa real.${regras.ativa === false ? " Com as regras antigas, a fazenda inteira." : ""}`,
  }), [base.cod, ccReal, regras.ativa]);
  const padrao = useMemo(() => ESTADO_INICIAL(hoje, ccPadrao), [hoje, ccPadrao]);
  const ctx = useContextoRelatorio(padrao, travas);
  const meses = useMemo(() => mesesProjecao(hoje), [hoje]);

  const [fontes, setFontes] = useState<FontesReal | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    if (regras.ativa === null) return;
    let vivo = true;
    const cc = ccReal === "todos" ? null : ccReal;
    Promise.allSettled([
      fetchResultadoPorLitro({ data_inicio: base.ini, data_fim: base.fim, regime: "competencia", centro_custo: cc }),
      fetchDreCascata({ data_inicio: base.ini, data_fim: base.fim, regime: "caixa" }),
      fetchCaixaReal(undefined, hoje),
      fetchEstratificacaoRebanho(),
    ]).then(([l, d, c, e]) => {
      if (!vivo) return;
      if (l.status === "rejected") { setErro((l.reason as Error).message); return; }
      setErro(null);
      setFontes({
        ini: base.ini, fim: base.fim, litro: l.value.atual,
        dreCaixa: d.status === "fulfilled" ? d.value : null,
        caixa: c.status === "fulfilled" ? { saldo_inicial: c.value.saldo_inicial, fundo_reserva: c.value.fundo_reserva } : null,
        vacasLactacao: e.status === "fulfilled" ? e.value.estratos?.vacas_lactacao ?? 0 : null,
      });
    });
    return () => { vivo = false; };
  }, [regras.ativa, ccReal, base.ini, base.fim, hoje, tentativa]);

  const real: Real | null = useMemo(() => (fontes ? realDe(fontes, hoje) : null), [fontes, hoje]);
  // A coluna Real mostra o real no formato de cada campo (o mesmo número com que um cenário começa —
  // "Realista" sem mudança dá "= real"); a conferência usa o real sem arredondar.
  const vReal = useMemo(() => (real ? valoresBase(real, hoje) : null), [real, hoje]);
  const resReal = useMemo(() => (real && vReal ? calcular(vReal, real, meses) : null), [real, vReal, meses]);
  const resCheio = useMemo(() => (real ? calcular(valoresBase(real, hoje, true), real, meses) : null), [real, hoje, meses]);

  // Cenários do dono: deste navegador, por fazenda.
  const chave = chaveArmazenamento(typeof window === "undefined" ? null : getFazendaAtual()?.id);
  const [editados, setEditados] = useState<Cenario[] | null>(null);
  // Os salvos neste navegador (ou os exemplos), lidos quando o Real chega; depois, o que a pessoa editar.
  const iniciais = useMemo(() => {
    if (!real) return null;
    let salvos: Cenario[] | null = null;
    try { salvos = lerCenarios(window.localStorage.getItem(chave)); } catch { /* armazenamento bloqueado: começa dos exemplos */ }
    return salvos ? ajustarMes(salvos, meses) : cenariosExemplo(valoresBase(real, hoje));
  }, [real, chave, meses, hoje]);
  const cens = editados ?? iniciais;
  const mudar = (fn: (cs: Cenario[]) => Cenario[]) => setEditados((cs) => {
    const novo = fn(cs ?? iniciais ?? []);
    try { window.localStorage.setItem(chave, JSON.stringify(novo)); } catch { /* sem armazenamento: vale só nesta visita */ }
    return novo;
  });
  const valorReal = (c: Campo) => (c.tipo === "mes" ? meses[4] : arredondar(real?.v[c.k as Num] ?? 0, c));

  const resultados: Resultado[] = useMemo(() => (real && cens ? cens.map((c) => calcular(c.v, real, meses)) : []), [real, cens, meses]);
  const semLitro = !!fontes && !temResultadoPorLitro(fontes.litro);
  const estado = regras.ativa === null || (!fontes && !erro) || (fontes && !cens) ? "carregando" : erro && !fontes ? "erro" : "ok";
  const rotBase = `${mesCurto(base.ini.slice(0, 7))}–${mesCurto(base.fim.slice(0, 7))}`;

  const frase = resReal && cens && resultados.length ? [
    { t: `O real (média de ${rotBase}${ccReal !== "todos" ? `, ${ccReal}` : ""}) dá ` },
    ...(resReal.sobraL != null ? [{ t: `${brl(resReal.sobraL)} por litro`, b: true }, { t: " de sobra do custeio e " }] : []),
    { t: `${brl(resReal.sobraMes, 0)} por mês`, b: true }, { t: "; com parcelas e retirada, o saldo chega a " }, { t: brl(resReal.fim, 0), b: true }, { t: ` em ${mesCurto(meses[11])}. ` },
    ...cens.flatMap((c, k) => [
      { t: `${k ? "; " : ""}${c.nome}: ` },
      { t: resultados[k].sobraL != null ? `${brl(resultados[k].sobraL!)}/L` : "sem litros", b: true },
      { t: `, menor saldo ${brl(resultados[k].mnS, 0)} em ${mesCurto(resultados[k].mnYm)}` },
    ]),
    { t: "." },
  ] : [];

  const exportar = (): RelatorioParaExportar | null => {
    if (!resReal || !cens) return null;
    const cols = ["Real", ...cens.map((c) => c.nome)];
    return {
      titulo: "Cenários — E se…?", pergunta: "E se…?", nomeArquivoBase: "cenarios",
      contexto: { periodo: `real = média de ${rotBase}; projeção ${mesCurto(meses[0])} a ${mesCurto(meses[11])}`, comparacao: null, regime: "pelo mês do gasto (competência)", centro: ccReal === "todos" ? "todos os centros" : ccReal },
      colunas: [{ header: "Campo ou indicador", tipo: "texto" }, ...cols.map((h) => ({ header: h, tipo: "texto" as const }))],
      linhas: [
        { valores: ["Valores preenchidos", ...cols.map(() => "")], total: true },
        ...CAMPOS.map((c) => ({ valores: [`${c.nome}${c.un ? ` (${c.un})` : ""}`, c.tipo === "mes" ? "—" : textoCampo(c, vReal![c.k as Num]), ...cens.map((x) => (c.tipo === "mes" ? mesCurto(x.v.mes) : textoCampo(c, x.v[c.k as Num])))] })),
        { valores: ["Resultado", ...cols.map(() => "")], total: true },
        ...SAIDAS.map((o) => ({ valores: [o.nome, ...[resReal, ...resultados].map((x) => (x[o.k] == null ? "—" : FMT[o.f](x[o.k] as number)))] })),
        { valores: ["Saldo no fim de cada mês", ...cols.map(() => "")], total: true },
        ...meses.map((ym, i) => ({ valores: [mesLongo(ym), ...[resReal, ...resultados].map((x) => brl(x.pts[i].s, 0))] })),
      ],
      notas: ["Real: Resultado por litro, DRE pelo dia do pagamento, Caixa real e Rebanho do servidor. Cenários: valores preenchidos pelo dono, guardados neste navegador."],
    };
  };

  // O servidor arredonda o R$/L em 4 casas: a conferência aceita até meio décimo de milésimo.
  const conf = !!resCheio && real?.coeL != null && real.sobraL != null && resCheio.coeL != null && resCheio.sobraL != null
    && Math.abs(resCheio.coeL - real.coeL) < 6e-5 && Math.abs(resCheio.sobraL - real.sobraL) < 6e-5;

  return (<>
    <style>{CSS_PLANO}</style>
    <RelatorioShell ctx={ctx} hoje={hoje} centros={centros} grupo="Plano" nome="Cenários" pergunta="E se…?"
      onIrGrupo={props.onIrGrupo} estado={estado} erro={erro || regras.erro} onTentarDeNovo={() => { setErro(null); setTentativa((t) => t + 1); }}
      frase={frase} rotuloCmp={null} exportar={exportar}
      avisos={semLitro ? (
        <div className="rl-aviso" role="status"><AlertTriangle size={18} aria-hidden /><div>
          <b>Sem leite e custo em {rotBase}: a coluna Real fica sem preço, litros e custos.</b>
          <p>Preencha os cenários com os seus números — eles calculam do mesmo jeito. Para o Real aparecer, lance a venda do leite e a entrega mensal (veja o Resultado por litro).</p>
        </div></div>
      ) : null}>
      {real && vReal && resReal && cens && (<>
        <TabelaEntrada real={real} vReal={vReal} cens={cens} meses={meses} valorReal={valorReal} mudar={mudar} rotBase={rotBase} />
        <TabelaResultado resReal={resReal} cens={cens} resultados={resultados} meses={meses} />
        <PainelGrafico titulo="Saldo de caixa no fim de cada mês"
          legenda={<LegendaSaldo series={serieSaldo(resReal, vReal, cens, resultados)} />}
          tabela={{ cabecalho: ["Mês", "Real (se nada mudar)", ...cens.map((c) => c.nome)], linhas: [
            ["hoje", brl(vReal.saldo, 0), ...cens.map((c) => brl(c.v.saldo, 0))],
            ...meses.map((ym, i) => [mesLongo(ym), brl(resReal.pts[i].s, 0), ...resultados.map((x) => brl(x.pts[i].s, 0))]),
          ] }}>
          <GraficoSaldo rotulos={["hoje", ...meses.map(mesCurto)]} series={serieSaldo(resReal, vReal, cens, resultados)} reserva={vReal.res}
            descricao={`Saldo de caixa de hoje a ${mesCurto(meses[11])}: real termina em ${brl(resReal.fim, 0)}; ${cens.map((c, k) => `${c.nome} ${brl(resultados[k].fim, 0)}, menor saldo ${brl(resultados[k].mnS, 0)}`).join("; ")}.`} />
        </PainelGrafico>
        <NotasMetodo titulo="Como os cenários são calculados"
          entra={[
            ["Real", `Média de ${rotBase} pelo mês do gasto${ccReal !== "todos" ? `, centro ${ccReal}` : ""} — os mesmos números do Resultado por litro. Saldo inicial = saldo de hoje do Caixa real.`],
            ["Mês", `${num(real.diasMes, 1)} dias por mês (média dos 3 meses). Receita = preço líquido × litros por dia × dias.`],
            ["Comida", `% da receita BRUTA do leite (a convenção do RMCA); a bruta é a líquida × ${num(real.fatorBruto, 3)} (Funrural, Senar e descontos do real).`],
            ["Ponto de equilíbrio", "Litros por dia que pagam mão de obra e outros custeios com o que sobra de cada litro depois da comida."],
            ["Caixa", "Sobra do custeio − parcelas da dívida − retirada, todo mês; a compra à vista sai no mês escolhido. Contas já lançadas a pagar e a receber não entram: elas estão no Caixa real."],
            ["Onde ficam", "Os cenários ficam neste navegador, para esta fazenda (o servidor guarda os cenários por conta da tela anterior, que continuam valendo)."],
          ]}
          naoEntra={["Desgaste dos bens (não é dinheiro).", "Variação de estoque.", "Investimentos já lançados (veja o Caixa real)."]}>
          <p style={{ margin: ".6rem 0 .3rem" }}><b>De onde vem cada número do Real</b></p>
          <dl>{CAMPOS.filter((c) => c.tipo !== "mes" && c.k !== "compra").map((c) => (
            <div key={c.k} style={{ display: "contents" }}><dt>{c.nome}</dt><dd>{real.origem[c.k] ?? "—"}</dd></div>
          ))}</dl>
          <p style={{ margin: ".7rem 0 0" }}>
            Projeção conta a conta, mês a mês, com “Importar para Pedidos”: <button type="button" className="rl-linkbtn" style={{ color: "var(--text-accent)", fontWeight: 700 }}
              onClick={() => props.onIrRelatorio("planejamento_financeiro")}>Cenários por conta (tela anterior)</button>.
          </p>
        </NotasMetodo>
        {real.coeL != null && (
          <Conferencia fecha={conf} texto={conf
            ? `Com os valores reais, o modelo reproduz o Resultado por litro de ${rotBase}: custo de custeio ${brl(resCheio!.coeL!, 4)}/L e sobra ${brl(resCheio!.sobraL!, 4)}/L (servidor: ${brl(real.coeL, 4)} e ${brl(real.sobraL!, 4)}).`
            : `O modelo não reproduz o Resultado por litro (${brl(real.coeL)}/L) — avise o suporte.`} />
        )}
      </>)}
    </RelatorioShell>
  </>);
}

function serieSaldo(resReal: Resultado, vReal: Valores, cens: Cenario[], resultados: Resultado[]): SerieSaldo[] {
  return [
    { nome: "Real (se nada mudar)", vals: [vReal.saldo, ...resReal.pts.map((p) => p.s)], estilo: "real" },
    ...cens.map((c, k) => ({ nome: c.nome, vals: [c.v.saldo, ...resultados[k].pts.map((p) => p.s)], estilo: ESTILOS[k] })),
  ];
}

// ── Entrada: Real × até 3 cenários ────────────────────────────────────────
function CampoNum({ c, valor, rotulo, onConfirmar }: { c: Campo; valor: number; rotulo: string; onConfirmar: (v: number) => void }) {
  const [texto, setTexto] = useState<string | null>(null);
  const invalido = texto != null && lerCampo(texto, c) == null;
  const confirmar = (t: string) => { const v = lerCampo(t, c); if (v == null) return; setTexto(null); if (v !== valor) onConfirmar(v); };
  return (
    <input className="rl-in" inputMode="decimal" aria-label={rotulo} aria-invalid={invalido || undefined}
      style={invalido ? { borderColor: "var(--st-venc-fg)" } : undefined}
      value={texto ?? textoCampo(c, valor)} onFocus={(e) => e.currentTarget.select()}
      onChange={(e) => setTexto(e.target.value)} onBlur={(e) => { if (texto != null) confirmar(e.currentTarget.value); }}
      onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => { if (e.key === "Enter") { e.preventDefault(); confirmar(e.currentTarget.value); } }} />
  );
}

function TabelaEntrada({ real, vReal, cens, meses, valorReal, mudar, rotBase }: {
  real: Real; vReal: Valores; cens: Cenario[]; meses: string[]; valorReal: (c: Campo) => number | string;
  mudar: (fn: (cs: Cenario[]) => Cenario[]) => void; rotBase: string;
}) {
  const setCampo = (k: number, campo: keyof Valores, v: number | string) => mudar((cs) => cs.map((c, i) => (i === k ? { ...c, v: { ...c.v, [campo]: v } } : c)));
  return (
    <section className="rl-painel" aria-labelledby="rl-cen-in">
      <h3 className="rl-tit" id="rl-cen-in"><Calculator size={15} aria-hidden style={{ verticalAlign: "-2px" }} /> Preencha os cenários</h3>
      <p style={{ margin: "0 0 .6rem", fontSize: ".84rem", color: "var(--text-muted)", maxWidth: "80ch" }}>
        A coluna <b style={{ color: "var(--text)" }}>Real</b> vem dos lançamentos (média de {rotBase}) e do saldo de hoje. Cada cenário aceita qualquer número, em valor absoluto: digite e tecle Enter.
      </p>
      <p className="rl-hintdeslize" aria-hidden><ArrowRight size={14} /> Deslize a tabela para o lado para ver os {cens.length} cenários.</p>
      <div className="rl-tw">
        <table className="fazenda-table rl-cvt">
          <caption className="rl-sr">Valores do real e de cada cenário</caption>
          <thead><tr>
            <th scope="col" className="stk">Campo</th>
            <th scope="col" style={{ textAlign: "right" }}>Real</th>
            {cens.map((c, k) => (
              <th key={k} scope="col" className="cvh">
                <label className="rl-sr" htmlFor={`rl-cn-${k}`}>Nome do cenário {k + 1}</label>
                <input id={`rl-cn-${k}`} className="rl-in rl-nomecen" defaultValue={c.nome} key={c.nome} maxLength={24}
                  onBlur={(e) => { const n = e.currentTarget.value.trim() || `Cenário ${k + 1}`; if (n !== c.nome) mudar((cs) => cs.map((x, i) => (i === k ? { ...x, nome: n } : x))); }}
                  onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
                <span style={{ display: "flex", gap: ".3rem", marginTop: ".35rem" }}>
                  <button type="button" className="rl-mini" onClick={() => mudar((cs) => cs.map((x, i) => (i === k ? { ...x, v: { ...valoresBaseDe(real, vReal, meses) } } : x)))}>
                    <Undo2 size={12} aria-hidden /> Voltar tudo ao real
                  </button>
                  {cens.length > 1 && (
                    <button type="button" className="rl-mini" aria-label={`Remover o cenário ${c.nome}`} onClick={() => mudar((cs) => cs.filter((_, i) => i !== k))}><X size={12} aria-hidden /></button>
                  )}
                </span>
              </th>
            ))}
          </tr></thead>
          <tbody>
            {CAMPOS.map((c, i) => {
              const sep = i === 0 || CAMPOS[i - 1].grupo !== c.grupo ? <tr key={`g-${c.grupo}`} className="sec"><th scope="rowgroup" className="stk">{c.grupo}</th><td colSpan={1 + cens.length} /></tr> : null;
              const r = valorReal(c);
              const semReal = c.tipo !== "mes" && c.k !== "compra" && real.v[c.k as Num] == null;
              return [sep, (
                <tr key={c.k}>
                  <th scope="row" className="stk">{c.nome}{c.un && <small>{c.un}</small>}</th>
                  <td className="r" style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {c.tipo === "mes" ? <span className="mut">—</span> : semReal ? <><span className="mut">—</span><span className="orig">{real.origem[c.k]}</span></> : <span className={(r as number) < 0 ? "neg" : undefined}>{textoCampo(c, r as number)}</span>}
                  </td>
                  {cens.map((cen, k) => {
                    if (c.tipo === "mes") {
                      return (
                        <td key={k}><div className="cvc">
                          <label className="rl-sr" htmlFor={`rl-cv-${k}-mes`}>{c.nome} · {cen.nome}</label>
                          <select id={`rl-cv-${k}-mes`} className="rl-in" value={cen.v.mes} onChange={(e) => setCampo(k, "mes", e.target.value)}>
                            {meses.map((ym) => <option key={ym} value={ym}>{mesCurto(ym)}</option>)}
                          </select>
                        </div></td>
                      );
                    }
                    const v = cen.v[c.k as Num], rv = r as number, dif = arredondar(v, c) !== arredondar(rv, c);
                    const d = v - rv;
                    return (
                      <td key={k}>
                        <div className="cvc">
                          <CampoNum c={c} valor={v} rotulo={`${c.nome}${c.un ? ` (${c.un})` : ""} · ${cen.nome}`} onConfirmar={(x) => setCampo(k, c.k as Num, x)} />
                          {dif ? (
                            <button type="button" className="rl-mini" title="Voltar ao real" aria-label={`Voltar ${c.nome} ao real em ${cen.nome}`} onClick={() => setCampo(k, c.k as Num, rv)}>
                              <RotateCcw size={12} aria-hidden />
                            </button>
                          ) : <span style={{ width: 30, display: "inline-block" }} aria-hidden />}
                        </div>
                        <small>{dif ? `${d > 0 ? "+" : MENOS}${c.pct ? `${num(Math.abs(d) * 100, 1)} p.p.` : num(Math.abs(d), c.casas)} vs real` : "= real"}</small>
                      </td>
                    );
                  })}
                </tr>
              )];
            })}
          </tbody>
        </table>
      </div>
      <div className="rl-acoes rl-noprint" style={{ marginTop: ".7rem" }}>
        {cens.length < MAX_CENARIOS
          ? <button type="button" className="rl-btn" onClick={() => mudar((cs) => [...cs, { nome: `Cenário ${cs.length + 1}`, v: valoresBaseDe(real, vReal, meses) }])}><Plus size={14} aria-hidden /> Adicionar cenário</button>
          : <span style={{ fontSize: ".8rem", color: "var(--text-muted)" }}>Até {MAX_CENARIOS} cenários.</span>}
        <button type="button" className="rl-btn" onClick={() => mudar(() => cenariosExemplo(valoresBaseDe(real, vReal, meses)))}><RotateCcw size={14} aria-hidden /> Restaurar os exemplos</button>
      </div>
    </section>
  );
}

/** O real arredondado no formato de cada campo (o começo de um cenário). */
function valoresBaseDe(real: Real, vReal: Valores, meses: string[]): Valores {
  const b = { ...vReal, mes: meses[4] };
  for (const c of CAMPOS) if (c.tipo !== "mes") b[c.k as Num] = arredondar(real.v[c.k as Num] ?? 0, c);
  return b;
}

// ── Resultado × real ──────────────────────────────────────────────────────
function TabelaResultado({ resReal, cens, resultados, meses }: { resReal: Resultado; cens: Cenario[]; resultados: Resultado[]; meses: string[] }) {
  return (
    <section className="rl-painel" aria-labelledby="rl-cen-out">
      <h3 className="rl-tit" id="rl-cen-out">Resultado de cada cenário × real</h3>
      <div className="rl-tw">
        <table className="fazenda-table rl-cvt">
          <caption className="rl-sr">Indicadores do real e de cada cenário, com a diferença para o real</caption>
          <thead><tr><th scope="col" className="stk">Indicador</th><th scope="col" style={{ textAlign: "right" }}>Real</th>
            {cens.map((c, k) => <th key={k} scope="col" style={{ textAlign: "right" }}>{c.nome}</th>)}</tr></thead>
          <tbody>
            {SAIDAS.map((o) => {
              const b = resReal[o.k] as number | null;
              const neg = (v: number | null) => v != null && v < 0 && (o.f === "brl0" || o.f === "brl");
              return (
                <tr key={o.k} className={o.main ? "main" : undefined}>
                  <th scope="row" className="stk">{o.nome}{o.k === "mnS" && <small>mês do menor saldo no real: {mesCurto(resReal.mnYm || meses[0])}</small>}</th>
                  <td className="r"><b className={neg(b) ? "neg" : undefined}>{b == null ? "—" : FMT[o.f](b)}</b></td>
                  {resultados.map((x, k) => {
                    const v = x[o.k] as number | null;
                    if (v == null) return <td key={k} className="r"><b className="mut">—</b></td>;
                    const d = delta(v, b, o.bom);
                    const igual = !d || FMT_D[o.f](d.abs).replace(/[+−-]/g, "") === FMT_D[o.f](0).replace(/[+−-]/g, "") || d.igual;
                    return (
                      <td key={k} className="r">
                        <b className={neg(v) ? "neg" : undefined}>{FMT[o.f](v)}</b>
                        {igual ? <small>= real</small> : (
                          <small><span className={`rl-dt ${d!.melhor ? "bom" : "ruim"}`}><span aria-hidden>{d!.abs > 0 ? "▲" : "▼"}</span> {FMT_D[o.f](d!.abs)} · {d!.melhor ? "melhor" : "pior"}</span></small>
                        )}
                        {o.k === "mnS" && <small>em {mesCurto(x.mnYm || meses[0])}</small>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

