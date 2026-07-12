"use client";
// RECRIA — Dossiê de Desempenho Zootécnico (bezerras e novilhas).
// Feito para uso simples: escolha a doença por botão, veja a curva de casos por
// idade com o "ponto crítico" pintado, e a incidência por fase. A aba
// Crescimento compara o peso real com a faixa-alvo. "Registrar caso" é o
// lançamento rápido que alimenta tudo.
import { useEffect, useState } from "react";
import { Baby, Activity, TrendingUp, PlusCircle, Trash2, AlertTriangle, Heart } from "lucide-react";
import { TabBar } from "@/components/ui";
import {
  fetchAnimais, fetchRecriaDoencas, fetchRecriaCurva, fetchRecriaPesoAlvoResumo,
  fetchRecriaOcorrencias, criarRecriaOcorrencia, excluirRecriaOcorrencia, fetchRecriaBenchmark,
  fetchRecriaIdadeParto, fetchRecriaTaxaPrenhez,
  type RecriaCurva, type RecriaOcorrencia, type RecriaBenchmark, type RecriaIdadeParto,
} from "@/lib/api";

type Aba = "saude" | "crescimento" | "reproducao" | "registrar";
const ABAS = [
  { id: "saude" as const, label: "Saúde por idade", icon: Activity, title: "Curva de casos de doença por idade (dias), com o ponto crítico e a incidência por fase" },
  { id: "crescimento" as const, label: "Crescimento", icon: TrendingUp, title: "Peso real médio por mês de idade comparado à faixa de peso-alvo, e benchmark Alta CRIA" },
  { id: "reproducao" as const, label: "Reprodução", icon: Heart, title: "Idade ao 1º parto (Wisconsin), custo de recria excedente e taxa de prenhez por ciclo de 21 dias" },
  { id: "registrar" as const, label: "Registrar caso", icon: PlusCircle, title: "Lançar um caso de doença (animal, doença e data) — alimenta a Saúde por idade" },
];

const hoje = () => new Date().toISOString().slice(0, 10);
const card: React.CSSProperties = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "1rem 1.1rem" };
const input: React.CSSProperties = { padding: "0.45rem 0.6rem", borderRadius: 8, fontSize: "0.9rem", background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)", width: "100%" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };

export default function RecriaPage() {
  const [aba, setAba] = useState<Aba>("saude");
  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Baby size={22} style={{ color: "var(--dourado)" }} /> Recria — Dossiê Zootécnico</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Acompanhamento de bezerras e novilhas: em que idade cada doença mais aparece (o <strong>ponto crítico</strong>), a incidência por fase e o crescimento em peso.
        </p>
      </div>
      <TabBar abas={ABAS} ativa={aba} onChange={setAba} />
      <div style={{ marginTop: "1rem" }}>
        {aba === "saude" && <AbaSaude />}
        {aba === "crescimento" && <AbaCrescimento />}
        {aba === "reproducao" && <AbaReproducao />}
        {aba === "registrar" && <AbaRegistrar />}
      </div>
    </div>
  );
}

// ─────────────────────────────── SAÚDE ───────────────────────────────
function AbaSaude() {
  const [doencas, setDoencas] = useState<{ doenca: string; casos: number }[] | null>(null);
  const [sel, setSel] = useState<string>("");
  const [dados, setDados] = useState<RecriaCurva | null>(null);
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    fetchRecriaDoencas().then((d) => {
      setDoencas(d);
      if (d.length && !sel) setSel(d[0].doenca);
    }).catch(() => setDoencas([]));
  }, []);
  useEffect(() => {
    if (!sel) { setDados(null); return; }
    setCarregando(true);
    fetchRecriaCurva(sel).then(setDados).catch(() => setDados(null)).finally(() => setCarregando(false));
  }, [sel]);

  if (doencas === null) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;
  if (!doencas.length) return (
    <div style={card}>
      <p style={{ fontSize: "0.9rem" }}>Ainda não há casos de doença registrados. Vá em <strong>Registrar caso</strong> e lance a primeira ocorrência — a curva aparece aqui automaticamente.</p>
    </div>
  );

  const pc = dados?.ponto_critico;
  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {/* Seletor de doença por botões grandes */}
      <div className="flex flex-wrap gap-2">
        {doencas.map((d) => (
          <button key={d.doenca} onClick={() => setSel(d.doenca)}
            style={{ padding: "0.5rem 1rem", borderRadius: 999, cursor: "pointer", fontSize: "0.85rem", fontWeight: sel === d.doenca ? 700 : 500,
              border: "1px solid " + (sel === d.doenca ? "var(--dourado)" : "var(--border)"),
              background: sel === d.doenca ? "rgba(94,26,46,0.4)" : "transparent",
              color: sel === d.doenca ? "var(--dourado-light)" : "var(--text-muted)" }}>
            {d.doenca} <span style={{ opacity: 0.7, fontSize: "0.78rem" }}>({d.casos})</span>
          </button>
        ))}
      </div>

      {carregando || !dados ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.6fr) minmax(0,1fr)", gap: "1rem", alignItems: "start" }} className="recria-grid">
          {/* Gráfico casos × idade */}
          <div style={card}>
            <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.7rem" }}>Casos de {dados.doenca} por idade (dias)</div>
            <CurvaBarras curva={dados.curva} janela={pc ? [pc.dia_min, pc.dia_max] : null} />
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
              A faixa em <span style={{ color: "var(--red)", fontWeight: 700 }}>vermelho</span> é o ponto crítico — onde a doença mais concentra os casos.
            </p>
          </div>

          {/* Painel de Insights */}
          <div style={{ display: "grid", gap: "0.7rem" }}>
            <div style={{ ...card, background: "var(--surface-2)" }}>
              <div style={{ fontSize: "0.7rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>Volume analisado</div>
              <div style={{ fontSize: "1.6rem", fontWeight: 800 }}>{dados.total_casos} <span style={{ fontSize: "0.9rem", fontWeight: 500, color: "var(--text-muted)" }}>casos</span></div>
            </div>
            {pc && (
              <div style={{ ...card, borderColor: "var(--red)", background: "rgba(165,56,43,0.08)" }}>
                <div style={{ fontSize: "0.7rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--red)", fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}><AlertTriangle size={13} /> Ponto crítico</div>
                <div style={{ fontSize: "1.5rem", fontWeight: 800 }}>{pc.dia_pico}º dia de vida</div>
                <div style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Janela {pc.dia_min}–{pc.dia_max} dias concentra <strong>{pc.pct_na_janela}%</strong> dos casos.</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Incidência por fase */}
      {dados && dados.incidencia_por_fase.some((f) => f.casos > 0) && (
        <div style={card}>
          <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.6rem" }}>Incidência por fase de idade</div>
          <div style={{ overflowX: "auto" }}>
            <table className="fazenda-table">
              <thead><tr><th>Fase</th><th>Casos</th><th>Animais afetados</th><th>Animais em risco</th><th>Incidência</th></tr></thead>
              <tbody>
                {dados.incidencia_por_fase.map((f) => {
                  const inc = f.incidencia_pct;
                  const cor = inc == null ? "var(--text-muted)" : inc >= 20 ? "var(--red)" : inc >= 8 ? "var(--amber)" : "var(--green-light)";
                  return (
                    <tr key={f.fase}>
                      <td style={{ fontWeight: 600 }}>{f.fase}</td>
                      <td>{f.casos}</td><td>{f.animais_afetados}</td><td>{f.animais_em_risco}</td>
                      <td><span style={{ fontWeight: 800, color: cor }}>{inc == null ? "—" : `${inc}%`}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <style>{`@media (max-width: 820px){ .recria-grid{ grid-template-columns: 1fr !important; } }`}</style>
    </div>
  );
}

function CurvaBarras({ curva, janela }: { curva: { dia: number; casos: number }[]; janela: [number, number] | null }) {
  if (!curva.length) return <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem casos.</p>;
  const max = Math.max(...curva.map((p) => p.casos), 1);
  const diaMax = Math.max(...curva.map((p) => p.dia));
  const diaMin = Math.min(...curva.map((p) => p.dia));
  const span = Math.max(diaMax - diaMin, 1);
  return (
    <div style={{ position: "relative", height: 180, display: "flex", alignItems: "flex-end", gap: 1, borderLeft: "1px solid var(--border)", borderBottom: "1px solid var(--border)", padding: "0 2px" }}>
      {janela && (
        <div title={`Ponto crítico: ${janela[0]}–${janela[1]} dias`} style={{
          position: "absolute", top: 0, bottom: 0,
          left: `${(100 * (janela[0] - diaMin)) / span}%`,
          width: `${(100 * (janela[1] - janela[0] + 1)) / span}%`,
          background: "rgba(165,56,43,0.14)", borderLeft: "1px dashed var(--red)", borderRight: "1px dashed var(--red)", pointerEvents: "none",
        }} />
      )}
      {curva.map((p) => {
        const dentro = janela && p.dia >= janela[0] && p.dia <= janela[1];
        return (
          <div key={p.dia} title={`${p.dia} dias: ${p.casos} caso(s)`}
            style={{ flex: 1, minWidth: 1, height: `${(100 * p.casos) / max}%`, background: dentro ? "var(--red)" : "var(--dourado)", borderRadius: "2px 2px 0 0", opacity: dentro ? 0.95 : 0.8 }} />
        );
      })}
      <span style={{ position: "absolute", left: 2, bottom: -18, fontSize: "0.65rem", color: "var(--text-muted)" }}>{diaMin} d</span>
      <span style={{ position: "absolute", right: 2, bottom: -18, fontSize: "0.65rem", color: "var(--text-muted)" }}>{diaMax} d</span>
    </div>
  );
}

// ─────────────────────────── CRESCIMENTO ───────────────────────────
function AbaCrescimento() {
  const [linhas, setLinhas] = useState<any[] | null>(null);
  useEffect(() => { fetchRecriaPesoAlvoResumo().then((d) => setLinhas(d.linhas)).catch(() => setLinhas([])); }, []);
  if (linhas === null) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;
  const comReal = linhas.filter((l) => l.peso_medio_real != null);
  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <BenchmarkAltaCria />
      <div style={card}>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: 0 }}>
          Peso real médio das bezerras por mês de idade, comparado à <strong>faixa de peso-alvo</strong> (cadastrável em Configurações › Cadastro › Recria).
          Verde = dentro do alvo, vermelho = fora.
        </p>
      </div>
      {!comReal.length && (
        <div style={card}><p style={{ fontSize: "0.9rem", margin: 0 }}>Ainda não há pesagens suficientes para montar a curva. Lance pesagens em <strong>Lançamentos › Produção › Pesagem corporal</strong>.</p></div>
      )}
      <div style={card}>
        <div style={{ overflowX: "auto" }}>
          <table className="fazenda-table">
            <thead><tr><th>Mês de idade</th><th>Peso real médio</th><th>Nº pesagens</th><th>Faixa-alvo (kg)</th><th>Situação</th></tr></thead>
            <tbody>
              {linhas.map((l) => {
                const st = l.dentro_do_alvo;
                const cor = st == null ? "var(--text-muted)" : st ? "var(--green-light)" : "var(--red)";
                const txt = st == null ? "—" : st ? "Dentro do alvo" : (l.peso_medio_real < (l.peso_min_alvo ?? 0) ? "Abaixo" : "Acima");
                return (
                  <tr key={l.mes}>
                    <td style={{ fontWeight: 600 }}>{l.mes}º mês</td>
                    <td>{l.peso_medio_real != null ? `${l.peso_medio_real} kg` : "—"}</td>
                    <td>{l.n_pesagens}</td>
                    <td>{l.peso_min_alvo != null ? `${l.peso_min_alvo}–${l.peso_max_alvo}` : "—"}</td>
                    <td><span style={{ fontWeight: 700, color: cor }}>{txt}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function BenchmarkAltaCria() {
  const [lista, setLista] = useState<RecriaBenchmark[] | null>(null);
  useEffect(() => { fetchRecriaBenchmark().then(setLista).catch(() => setLista([])); }, []);
  if (lista === null || !lista.length) return null;
  const corFaixa = (f?: string | null) =>
    f === "TOP 5%" || f === "TOP 10%" ? "var(--green-light)" : f === "TOP 25%" ? "var(--amber)" : f == null ? "var(--text-muted)" : "var(--red)";
  return (
    <div style={card}>
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.2rem" }}>Benchmark externo — Alta CRIA 2026</div>
      <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.9rem" }}>Onde a fazenda está em relação ao setor (TOP 5% = elite). A bolinha é a fazenda; o verde é a zona TOP.</p>
      <div style={{ display: "grid", gap: "0.9rem" }}>
        {lista.map((b) => {
          // Escala do pior (TOP 75) ao melhor (TOP 5). Barra sempre da esquerda (pior) p/ direita (melhor).
          const cortes = [b.top75, b.top50, b.top25, b.top10, b.top5].filter((x) => x != null) as number[];
          if (!cortes.length) return null;
          const lo = Math.min(...cortes, ...(b.valor_fazenda != null ? [b.valor_fazenda] : []));
          const hi = Math.max(...cortes, ...(b.valor_fazenda != null ? [b.valor_fazenda] : []));
          const span = Math.max(hi - lo, 0.0001);
          // posição: para "maior melhor", direita=maior. Para "menor melhor", invertido.
          const pos = (v: number) => {
            const p = (v - lo) / span; return b.melhor_e_maior ? p : 1 - p;
          };
          const top5p = pos(b.top5!); const top25p = pos(b.top25!);
          const zonaEsq = Math.min(top5p, 1) * 100;
          return (
            <div key={b.indicador}>
              <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>{b.indicador} <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>({b.unidade})</span></span>
                <span style={{ fontSize: "0.78rem" }}>
                  {b.valor_fazenda != null ? <><strong>{b.valor_fazenda}</strong> · <span style={{ color: corFaixa(b.faixa_fazenda), fontWeight: 700 }}>{b.faixa_fazenda}</span></> : <span style={{ color: "var(--text-muted)" }}>sem dado da fazenda</span>}
                </span>
              </div>
              <div style={{ position: "relative", height: 14, borderRadius: 999, background: "var(--surface-2)", border: "1px solid var(--border)", overflow: "hidden" }}>
                {/* zona TOP (do melhor até o TOP 25%) em verde */}
                <div style={{ position: "absolute", top: 0, bottom: 0, right: 0, width: `${100 - Math.min(top25p, 1) * 100}%`, background: "rgba(76,122,60,0.35)" }} />
                {/* marca do TOP 5% */}
                <div title="TOP 5%" style={{ position: "absolute", top: 0, bottom: 0, left: `${Math.min(top5p, 1) * 100}%`, width: 2, background: "var(--green-light)" }} />
                {/* bolinha da fazenda */}
                {b.valor_fazenda != null && (
                  <div title={`Fazenda: ${b.valor_fazenda}`} style={{ position: "absolute", top: "50%", left: `calc(${Math.min(Math.max(pos(b.valor_fazenda), 0), 1) * 100}% - 6px)`, transform: "translateY(-50%)", width: 12, height: 12, borderRadius: "50%", background: corFaixa(b.faixa_fazenda), border: "2px solid var(--surface)" }} />
                )}
              </div>
              <div className="flex items-center justify-between" style={{ fontSize: "0.62rem", color: "var(--text-muted)", marginTop: 2 }}>
                <span>pior (TOP 75%)</span><span>elite (TOP 5%) →</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────── REPRODUÇÃO ───────────────────────────
function AbaReproducao() {
  const [d, setD] = useState<RecriaIdadeParto | null>(null);
  const anoAtras = () => { const x = new Date(); x.setFullYear(x.getFullYear() - 1); return x.toISOString().slice(0, 10); };
  const [ini, setIni] = useState(anoAtras());
  const [fim, setFim] = useState(hoje());
  const [ciclos, setCiclos] = useState<any | null>(null);
  useEffect(() => { fetchRecriaIdadeParto().then(setD).catch(() => setD(null)); }, []);
  const calcularPrenhez = () => fetchRecriaTaxaPrenhez(ini, fim).then(setCiclos).catch(() => setCiclos(null));
  useEffect(() => { calcularPrenhez(); }, []);

  const st = d?.estatisticas;
  const fmtR$ = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const metaOk = (v: number, alvo: number, tol = 1) => Math.abs(v - alvo) <= tol;
  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {/* Wisconsin — idade ao 1º parto */}
      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.6rem" }}>Idade ao 1º parto (método Wisconsin)</div>
        {!st ? <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Ainda não há partos suficientes para calcular. Lance partos em <strong>Lançamentos › Reprodutivo › Parto/nascimento</strong>.</p> : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.7rem" }}>
            {[
              { rot: "Novilhas", v: st.n, sub: "" },
              { rot: "Idade média ao parto", v: `${st.media} m`, cor: metaOk(st.media, d!.meta_idade_parto, 1) ? "var(--green-light)" : "var(--amber)", sub: `meta ${d!.meta_idade_parto}m` },
              { rot: "Desvio-padrão", v: `${st.desvio_padrao} m`, cor: st.desvio_padrao <= 1.7 ? "var(--green-light)" : "var(--red)", sub: "meta < 1,7" },
              { rot: "Assimetria", v: st.assimetria, sub: "cauda de tardias" },
              { rot: "Mais nova / mais velha", v: `${st.idade_tipica_min}–${st.idade_tipica_max}`, sub: "meses (típico)" },
              { rot: "Amplitude típica", v: `${st.amplitude_tipica} m`, cor: st.amplitude_tipica < 6 ? "var(--green-light)" : "var(--amber)", sub: "meta < 6" },
            ].map((k) => (
              <div key={k.rot} style={{ background: "var(--surface-2)", borderRadius: 10, padding: "0.6rem 0.7rem" }}>
                <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{k.rot}</div>
                <div style={{ fontSize: "1.25rem", fontWeight: 800, color: (k as any).cor || "var(--text)" }}>{k.v}</div>
                {k.sub && <div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{k.sub}</div>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Distribuição idade ao parto */}
      {d && d.distribuicao.some((x) => x.n > 0) && (
        <div style={card}>
          <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.7rem" }}>Distribuição da idade ao 1º parto</div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 150, borderLeft: "1px solid var(--border)", borderBottom: "1px solid var(--border)", padding: "0 2px" }}>
            {d.distribuicao.map((x) => {
              const max = Math.max(...d.distribuicao.map((y) => y.pct), 1);
              const naMeta = Math.round(d.meta_idade_parto) === x.mes;
              return (
                <div key={x.mes} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%" }} title={`${x.mes} meses: ${x.n} (${x.pct}%)`}>
                  <div style={{ width: "100%", height: `${(100 * x.pct) / max}%`, background: naMeta ? "var(--green-light)" : "var(--dourado)", borderRadius: "2px 2px 0 0", opacity: 0.85 }} />
                  <span style={{ fontSize: "0.6rem", color: "var(--text-muted)", marginTop: 2 }}>{x.mes}</span>
                </div>
              );
            })}
          </div>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>Eixo: idade ao parto (meses). Verde = mês da meta ({d.meta_idade_parto}m).</p>
        </div>
      )}

      {/* Custo de recria excedente */}
      {d && d.custo_excedente.n > 0 && (
        <div style={{ ...card, borderColor: "var(--amber)", background: "rgba(180,124,30,0.06)" }}>
          <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.5rem" }}>Custo de recria excedente</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: "0.7rem" }}>
            <div><div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Total do rebanho</div><div style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--red)" }}>{fmtR$(d.custo_excedente.custo_total)}</div></div>
            <div><div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Por novilha</div><div style={{ fontSize: "1.2rem", fontWeight: 700 }}>{fmtR$(d.custo_excedente.custo_por_novilha)}</div></div>
            <div><div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Dias extras / novilha</div><div style={{ fontSize: "1.2rem", fontWeight: 700 }}>{d.custo_excedente.dias_por_novilha} d</div></div>
          </div>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Dias de recria além da meta de {d.meta_idade_parto} meses × custo diário (Configurações › Recria).</p>
        </div>
      )}

      {/* Taxa de prenhez 21 dias */}
      <div style={card}>
        <div className="flex items-center justify-between flex-wrap gap-2" style={{ marginBottom: "0.7rem" }}>
          <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>Taxa de prenhez (ciclos de 21 dias)</div>
          <div className="flex items-center gap-2">
            <input type="date" style={{ ...input, width: 150 }} value={ini} onChange={(e) => setIni(e.target.value)} />
            <span style={{ color: "var(--text-muted)" }}>até</span>
            <input type="date" style={{ ...input, width: 150 }} value={fim} onChange={(e) => setFim(e.target.value)} />
            <button className="btn-primary" onClick={calcularPrenhez} style={{ fontSize: "0.82rem" }}>Calcular</button>
          </div>
        </div>
        {!ciclos ? <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Escolha o período e clique em Calcular.</p> : !ciclos.ciclos?.length ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem serviços no período.</p>
        ) : (
          <>
            {ciclos.taxa_prenhez_media != null && (
              <p style={{ fontSize: "0.9rem", marginBottom: "0.6rem" }}>Taxa de prenhez média do período: <strong style={{ fontSize: "1.1rem", color: ciclos.taxa_prenhez_media >= 42.5 ? "var(--green-light)" : "var(--amber)" }}>{ciclos.taxa_prenhez_media}%</strong> <span style={{ color: "var(--text-muted)" }}>(meta &gt; 42,5%)</span></p>
            )}
            <div style={{ overflowX: "auto" }}>
              <table className="fazenda-table">
                <thead><tr><th>Ciclo</th><th>Período</th><th>Elegíveis</th><th>Servidos</th><th>Prenhes</th><th>Tx. Serviço</th><th>Tx. Concepção</th><th>Tx. Prenhez</th></tr></thead>
                <tbody>
                  {ciclos.ciclos.map((c: any) => (
                    <tr key={c.ciclo}>
                      <td style={{ fontWeight: 600 }}>{c.ciclo}</td>
                      <td style={{ fontSize: "0.78rem" }}>{c.inicio.split("-").reverse().join("/")}–{c.fim.split("-").reverse().join("/")}</td>
                      <td>{c.elegiveis}</td><td>{c.servidos}</td><td>{c.prenhes}</td>
                      <td>{c.taxa_servico != null ? `${c.taxa_servico}%` : "—"}</td>
                      <td>{c.taxa_concepcao != null ? `${c.taxa_concepcao}%` : "—"}</td>
                      <td><strong>{c.taxa_prenhez != null ? `${c.taxa_prenhez}%` : "—"}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────── REGISTRAR ───────────────────────────
function AbaRegistrar() {
  const [numeros, setNumeros] = useState<string[]>([]);
  const [doencasConhecidas, setDoencasConhecidas] = useState<string[]>([]);
  const [numero, setNumero] = useState("");
  const [doenca, setDoenca] = useState("");
  const [data, setData] = useState(hoje());
  const [obs, setObs] = useState("");
  const [lista, setLista] = useState<RecriaOcorrencia[] | null>(null);
  const [msg, setMsg] = useState<{ tipo: "ok" | "erro"; txt: string } | null>(null);
  const [salvando, setSalvando] = useState(false);

  const carregar = () => fetchRecriaOcorrencias().then(setLista).catch(() => setLista([]));
  useEffect(() => {
    fetchAnimais({ incluirMachos: true }).then((d: any) => setNumeros((d.animais || d || []).map((a: any) => a.numero).filter(Boolean))).catch(() => {});
    fetchRecriaDoencas().then((d) => setDoencasConhecidas(d.map((x) => x.doenca))).catch(() => {});
    carregar();
  }, []);

  async function salvar() {
    setMsg(null);
    if (!numero.trim()) { setMsg({ tipo: "erro", txt: "Informe o número do animal." }); return; }
    if (!doenca.trim()) { setMsg({ tipo: "erro", txt: "Informe a doença." }); return; }
    setSalvando(true);
    try {
      await criarRecriaOcorrencia({ numero_matriz: numero.trim(), doenca: doenca.trim(), data_ocorrencia: data, observacao: obs.trim() || undefined });
      setMsg({ tipo: "ok", txt: `Caso de ${doenca} no animal ${numero} registrado.` });
      setNumero(""); setObs(""); carregar();
      fetchRecriaDoencas().then((d) => setDoencasConhecidas(d.map((x) => x.doenca))).catch(() => {});
    } catch (e: any) { setMsg({ tipo: "erro", txt: e.message }); } finally { setSalvando(false); }
  }
  async function excluir(id: number) {
    if (!window.confirm("Excluir este caso?")) return;
    try { await excluirRecriaOcorrencia(id); carregar(); } catch (e: any) { setMsg({ tipo: "erro", txt: e.message }); }
  }

  const SUGESTOES = Array.from(new Set(["Diarreia", "Pneumonia", "TPB", "Infecção umbilical", ...doencasConhecidas]));
  return (
    <div style={{ display: "grid", gap: "1rem", maxWidth: 760 }}>
      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: "0.95rem", marginBottom: "0.7rem" }}>Registrar um caso de doença</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
          <div><label style={lbl}>Animal (número)</label>
            <input style={input} list="recria-animais" value={numero} onChange={(e) => setNumero(e.target.value)} placeholder="ex.: 145" />
            <datalist id="recria-animais">{numeros.map((n) => <option key={n} value={n} />)}</datalist></div>
          <div><label style={lbl}>Doença</label>
            <input style={input} list="recria-doencas" value={doenca} onChange={(e) => setDoenca(e.target.value)} placeholder="ex.: Diarreia" />
            <datalist id="recria-doencas">{SUGESTOES.map((d) => <option key={d} value={d} />)}</datalist></div>
          <div><label style={lbl}>Data do caso</label><input type="date" style={input} value={data} onChange={(e) => setData(e.target.value)} /></div>
          <div><label style={lbl}>Observação (opcional)</label><input style={input} value={obs} onChange={(e) => setObs(e.target.value)} /></div>
        </div>
        <div className="flex items-center gap-3 mt-3">
          <button className="btn-primary" onClick={salvar} disabled={salvando} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <PlusCircle size={15} /> {salvando ? "Salvando…" : "Registrar caso"}
          </button>
          {msg && <span style={{ fontSize: "0.82rem", color: msg.tipo === "ok" ? "var(--green-light)" : "var(--red)" }}>{msg.txt}</span>}
        </div>
      </div>

      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.6rem" }}>Casos registrados</div>
        {!lista ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : !lista.length ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum caso registrado ainda.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="fazenda-table">
              <thead><tr><th>Data</th><th>Animal</th><th>Doença</th><th>Obs.</th><th></th></tr></thead>
              <tbody>
                {lista.slice(0, 100).map((o) => (
                  <tr key={o.id}>
                    <td>{o.data_ocorrencia.split("-").reverse().join("/")}</td>
                    <td style={{ fontWeight: 600 }}>{o.numero_matriz}</td>
                    <td>{o.doenca}</td>
                    <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{o.observacao || "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem" }} onClick={() => excluir(o.id)}><Trash2 size={13} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
