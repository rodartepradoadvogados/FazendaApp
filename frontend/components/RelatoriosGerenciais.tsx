"use client";

import { useEffect, useState } from "react";
import { Activity, TrendingUp, Stethoscope, Repeat, Timer, Target, Milk } from "lucide-react";
import {
  BarChart, Bar, LineChart, Line, ComposedChart, ScatterChart, Scatter,
  XAxis, YAxis, ZAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
  CartesianGrid, Legend,
} from "recharts";
import { SecaoRecolhivel } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { fetchRelatorioGerencial } from "@/lib/api";

// ── Estilos e paletas compartilhados ──
const tip = {
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: "0.8rem",
} as const;

const tipBox: React.CSSProperties = { ...tip, color: "var(--text)", padding: "0.5rem 0.7rem" };

const inputStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: 6, padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "6rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: 2 };
const filtrosRow: React.CSSProperties = { display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "flex-end", marginBottom: "0.9rem" };
const axisTick = { fill: "var(--text-muted)", fontSize: 10 } as const;

// Cores do semáforo / séries.
const COR: Record<string, string> = {
  verde: "var(--green-light)",
  amarelo: "var(--amber)",
  vermelho: "var(--red)",
  azul: "var(--blue)",
};
const AZUL = "var(--blue)";
const DOURADO = "var(--dourado-light)";
const VERDE = "var(--green-light)";
const AMBER = "var(--amber)";

// ── Utilitários ──
function Desc({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", lineHeight: 1.55, margin: "0 0 0.9rem" }}>
      {children}
    </p>
  );
}
function Carregando() {
  return <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>;
}
function ErroMsg({ msg }: { msg: string }) {
  return <p style={{ color: "var(--red)", opacity: 0.85, fontSize: "0.85rem" }}>{msg}</p>;
}

// Hook: busca um relatório gerencial e refaz quando os parâmetros mudam.
function useGerencial(nome: string, params?: Record<string, string | number>) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const chave = JSON.stringify(params || {});
  useEffect(() => {
    let vivo = true;
    setLoading(true);
    setError(null);
    fetchRelatorioGerencial(nome, params)
      .then((d) => { if (vivo) { setData(d); setLoading(false); } })
      .catch((e) => { if (vivo) { setError(e?.message || "Erro ao carregar dados"); setLoading(false); } });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nome, chave]);
  return { data, loading, error };
}

// Extrai os números de um rótulo de faixa (ex.: "8-14" → [8, 14]).
function numerosFaixa(faixa: unknown): number[] {
  return (String(faixa).match(/\d+/g) || []).map(Number);
}
function faixaNaBanda(faixa: unknown, min: number, max: number): boolean {
  const n = numerosFaixa(faixa);
  if (!n.length) return false;
  const ini = n[0];
  const fim = n.length > 1 ? n[1] : n[0];
  return fim >= min && ini <= max;
}

// ── Card 1: Distribuição de DEL por serviço ──
function CardDistribuicaoDel() {
  const [ordem, setOrdem] = useState(1);
  const [delMin, setDelMin] = useState(0);
  const [delMax, setDelMax] = useState(350);
  const { data, loading, error } = useGerencial("distribuicao-del", { ordem, del_min: delMin, del_max: delMax });

  const pontos: any[] = (data?.pontos || []).map((p: any, i: number) => ({ ...p, x: i + 1 }));
  const ordTabela = useOrdenacao<any>(data?.tabela || []);

  return (
    <>
      <Desc>
        Cada ponto é a 1ª inseminação de uma vaca, mostrando o DEL na ocasião — mede a velocidade com que o
        sistema devolve os animais ao serviço. VERDE: inseminada no período desejado (do PEV até a meta).
        AMARELO: inseminada antes do fim do PEV. VERMELHO: inseminada acima da meta. Exibe só animais até 350 DEL.
      </Desc>

      <div style={filtrosRow}>
        <div>
          <label style={labelStyle}>Ordem do serviço</label>
          <select style={{ ...inputStyle, width: "8rem" }} value={ordem} onChange={(e) => setOrdem(Number(e.target.value))}>
            <option value={1}>1º</option>
            <option value={2}>2º</option>
            <option value={3}>3º</option>
            <option value={4}>4º ou mais</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>DEL de</label>
          <input type="number" style={inputStyle} value={delMin} onChange={(e) => setDelMin(Number(e.target.value))} />
        </div>
        <div>
          <label style={labelStyle}>DEL até</label>
          <input type="number" style={inputStyle} value={delMax} onChange={(e) => setDelMax(Number(e.target.value))} />
        </div>
      </div>

      {loading ? <Carregando /> : error ? <ErroMsg msg={error} /> : (
        <>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ top: 12, right: 20, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis type="number" dataKey="x" name="Ordem" tick={false} axisLine={{ stroke: "var(--border)" }}
                domain={[0, (pontos.length || 1) + 1]} height={12} />
              <YAxis type="number" dataKey="del" name="DEL" tick={axisTick} domain={[0, 350]} width={40}
                label={{ value: "DEL (dias)", angle: -90, position: "insideLeft", fill: "var(--text-muted)", fontSize: 10 }} />
              <ZAxis range={[45, 45]} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={tip as any}
                formatter={(v: any, n: any) => (n === "DEL" ? [`${v} dias`, "DEL"] : [v, n])} />
              {data?.pev != null && (
                <ReferenceLine y={data.pev} stroke={VERDE} strokeDasharray="5 4"
                  label={{ value: "PEV", position: "insideTopRight", fill: VERDE, fontSize: 11 }} />
              )}
              {data?.meta != null && (
                <ReferenceLine y={data.meta} stroke="var(--red)" strokeDasharray="5 4"
                  label={{ value: "Meta", position: "insideBottomRight", fill: "var(--red)", fontSize: 11 }} />
              )}
              <Scatter data={pontos as any} fill={AZUL}>
                {pontos.map((p, i) => <Cell key={i} fill={COR[p.cor] || AZUL} />)}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>

          {data?.tabela?.length > 0 && (
            <table className="fazenda-table" style={{ marginTop: "0.9rem" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Parâmetro" campo="label" coluna={ordTabela.coluna} dir={ordTabela.dir} ordenar={ordTabela.ordenar} />
                  <ThOrdenavel label="Vacas" campo="vacas" coluna={ordTabela.coluna} dir={ordTabela.dir} ordenar={ordTabela.ordenar} />
                  <ThOrdenavel label="Atual" campo="atual" coluna={ordTabela.coluna} dir={ordTabela.dir} ordenar={ordTabela.ordenar} />
                  <ThOrdenavel label="Meta" campo="meta" coluna={ordTabela.coluna} dir={ordTabela.dir} ordenar={ordTabela.ordenar} />
                </tr>
              </thead>
              <tbody>
                {ordTabela.linhasOrdenadas.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.label}</td>
                    <td>{r.vacas}</td>
                    <td style={{ color: COR[r.cor] || "var(--text)", fontWeight: 700 }}>{r.atual}%</td>
                    <td>{r.meta}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data?.total != null && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>
              Total de animais: {data.total}
            </p>
          )}
        </>
      )}
    </>
  );
}

// ── Card 2: Distribuição das prenhezes por DEL ──
function TooltipPrenhez({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div style={tipBox}>
      <div style={{ fontWeight: 700, marginBottom: 2 }}>{label}</div>
      <div style={{ color: AZUL }}>Prenhezes: {r.prenhezes}</div>
      <div style={{ color: DOURADO }}>Acumulado: {r.acumulado_pct}%</div>
      <div style={{ color: "var(--text-muted)" }}>IEP projetado: {r.iep_projetado} dias</div>
    </div>
  );
}
function CardPrenhezesPorDel() {
  const [delMin, setDelMin] = useState(0);
  const [delMax, setDelMax] = useState(400);
  const { data, loading, error } = useGerencial("prenhezes-por-del", { del_min: delMin, del_max: delMax });

  return (
    <>
      <Desc>
        A cada intervalo de 21 dias após o PEV, quantas prenhezes foram produzidas (barras azuis) e o acumulado
        percentual (linha amarela). Na escala superior, o IEP (Intervalo Entre Partos) projetado dos animais que
        emprenharam a cada ciclo. Queremos a linha amarela subindo cedo — indica vacas emprenhando rápido e IEP baixo.
      </Desc>

      <div style={filtrosRow}>
        <div>
          <label style={labelStyle}>DEL de</label>
          <input type="number" style={inputStyle} value={delMin} onChange={(e) => setDelMin(Number(e.target.value))} />
        </div>
        <div>
          <label style={labelStyle}>DEL até</label>
          <input type="number" style={inputStyle} value={delMax} onChange={(e) => setDelMax(Number(e.target.value))} />
        </div>
      </div>

      {loading ? <Carregando /> : error ? <ErroMsg msg={error} /> : (
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={(data?.barras || []) as any} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="faixa" tick={axisTick} />
            <YAxis yAxisId="left" tick={axisTick} width={40} />
            <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={axisTick} width={44} />
            <Tooltip content={<TooltipPrenhez />} />
            <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
            <Bar yAxisId="left" dataKey="prenhezes" name="Prenhezes" fill={AZUL} radius={[2, 2, 0, 0]} />
            <Line yAxisId="right" type="monotone" dataKey="acumulado_pct" name="Acumulado %" stroke={DOURADO} strokeWidth={2} dot={{ r: 2 }} />
          </ComposedChart>
        </ResponsiveContainer>
      )}
      {!loading && !error && data?.pev != null && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>
          PEV: {data.pev} dias · Total de prenhezes: {data.total}
        </p>
      )}
    </>
  );
}

// ── Card 3: Distribuição de dias para diagnóstico de prenhez ──
function TooltipSimples({ active, payload, label, chave, rotulo }: any) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div style={tipBox}>
      <div style={{ fontWeight: 700, marginBottom: 2 }}>{label}</div>
      <div style={{ color: AZUL }}>{rotulo}: {r[chave]}</div>
      {r.pct != null && <div style={{ color: "var(--text-muted)" }}>Percentual: {r.pct}%</div>}
    </div>
  );
}
function CardDiasDiagnostico() {
  const { data, loading, error } = useGerencial("dias-diagnostico");
  const min = data?.ideal_min;
  const max = data?.ideal_max;

  return (
    <>
      <Desc>
        Quando as vacas estão sendo tocadas. A faixa ideal (amarela) é quando as prenhezes deveriam ser
        identificadas, conforme os dados de manejo; as barras mostram quando foram de fato identificadas. Maiores
        concentrações na faixa ideal indicam rotina de checagem cumprida.
      </Desc>

      {loading ? <Carregando /> : error ? <ErroMsg msg={error} /> : (
        <>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={(data?.barras || []) as any} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="faixa" tick={axisTick} />
              <YAxis tick={axisTick} width={40} />
              <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }}
                content={<TooltipSimples chave="servicos" rotulo="Serviços" />} />
              <Bar dataKey="servicos" name="Serviços" radius={[2, 2, 0, 0]}>
                {(data?.barras || []).map((b: any, i: number) => (
                  <Cell key={i} fill={faixaNaBanda(b.faixa, min, max) ? AMBER : AZUL} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          {min != null && max != null && (
            <p style={{ color: "var(--amber)", fontSize: "0.78rem", marginTop: "0.5rem", fontWeight: 600 }}>
              Faixa ideal de diagnóstico: {min} a {max} dias
            </p>
          )}
        </>
      )}
    </>
  );
}

// ── Cards 4 e 5: BarChart de serviços por faixa (com pct no tooltip) ──
function CardBarrasFaixa({ nome, desc }: { nome: string; desc: React.ReactNode }) {
  const { data, loading, error } = useGerencial(nome);
  return (
    <>
      <Desc>{desc}</Desc>
      {loading ? <Carregando /> : error ? <ErroMsg msg={error} /> : (
        <>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={(data?.barras || []) as any} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="faixa" tick={axisTick} />
              <YAxis tick={axisTick} width={40} />
              <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }}
                content={<TooltipSimples chave="servicos" rotulo="Serviços" />} />
              <Bar dataKey="servicos" name="Serviços" fill={AZUL} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          {data?.total != null && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>
              Total de serviços: {data.total}
            </p>
          )}
        </>
      )}
    </>
  );
}

// ── Card 6: Taxa de serviço e taxa de prenhez por DEL ──
function TooltipTaxa({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div style={tipBox}>
      <div style={{ fontWeight: 700, marginBottom: 2 }}>{label}</div>
      <div style={{ color: "var(--text-muted)" }}>Vacas: {r.vacas}</div>
      <div style={{ color: AZUL }}>Taxa de serviço: {r.taxa_servico}%</div>
      <div style={{ color: DOURADO }}>Taxa de prenhez: {r.taxa_prenhez}%</div>
      <div style={{ color: VERDE }}>Acumulado prenhas: {r.acumulado_prenhas_pct}%</div>
    </div>
  );
}
function CardTaxaServicoPrenhez() {
  const { data, loading, error } = useGerencial("taxa-servico-prenhez");
  return (
    <>
      <Desc>
        Combina Taxa de Serviço e Taxa de Prenhez — os índices que melhor representam a velocidade em produzir
        prenhezes — com o acumulado de vacas prenhas por faixa de DEL.
      </Desc>

      {loading ? <Carregando /> : error ? <ErroMsg msg={error} /> : (
        <>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={(data?.linhas || []) as any} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="faixa" tick={axisTick} />
              <YAxis yAxisId="left" tickFormatter={(v) => `${v}%`} tick={axisTick} width={44} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={axisTick} width={44} />
              <Tooltip content={<TooltipTaxa />} />
              <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
              <Bar yAxisId="left" dataKey="taxa_servico" name="Taxa de serviço" fill={AZUL} radius={[2, 2, 0, 0]} />
              <Bar yAxisId="left" dataKey="taxa_prenhez" name="Taxa de prenhez" fill={DOURADO} radius={[2, 2, 0, 0]} />
              <Line yAxisId="right" type="monotone" dataKey="acumulado_prenhas_pct" name="Acumulado prenhas" stroke={VERDE} strokeWidth={2} dot={{ r: 2 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: "0.6rem", lineHeight: 1.5 }}>
            Parâmetros de eficiência: 50% do rebanho prenhe até 100 dias, 75% até 150 dias, e não mais de 10%
            chegando aos 300 dias sem prenhez.
          </p>
        </>
      )}
    </>
  );
}

// ── Card 7: Fluxo mensal de vacas em lactação ──
function TooltipFluxo({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div style={tipBox}>
      <div style={{ fontWeight: 700, marginBottom: 2 }}>{label}</div>
      <div style={{ color: AMBER }}>A secar: {r.secar}</div>
      <div style={{ color: AZUL }}>A parir: {r.parir}</div>
      <div style={{ color: DOURADO }}>Saldo em lactação: {r.saldo_lactacao}</div>
    </div>
  );
}
function CardFluxoLactacao() {
  const [meses, setMeses] = useState(8);
  const { data, loading, error } = useGerencial("fluxo-lactacao", { meses });
  const ordLinhas = useOrdenacao<any>(data?.linhas || []);

  return (
    <>
      <Desc>
        Projeta o saldo de vacas em leite nos próximos meses. Partindo do total atual em lactação, as barras mostram
        as vacas a secar e a parir a cada mês; a linha amarela é o saldo projetado de vacas em lactação. Permite
        antecipar o nível de produção leiteira.
      </Desc>

      <div style={filtrosRow}>
        <div>
          <label style={labelStyle}>Meses a projetar</label>
          <input type="number" min={1} max={24} style={inputStyle} value={meses}
            onChange={(e) => setMeses(Math.max(1, Math.min(24, Number(e.target.value) || 1)))} />
        </div>
      </div>

      {loading ? <Carregando /> : error ? <ErroMsg msg={error} /> : (
        <>
          <p style={{ color: "var(--dourado-light)", fontWeight: 700, fontSize: "0.9rem", margin: "0 0 0.6rem" }}>
            Vacas em lactação hoje: {data?.lactacao_inicial}
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={(data?.linhas || []) as any} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="mes" tick={axisTick} />
              <YAxis tick={axisTick} width={40} />
              <Tooltip content={<TooltipFluxo />} />
              <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
              <Bar dataKey="secar" name="A secar" fill={AMBER} radius={[2, 2, 0, 0]} />
              <Bar dataKey="parir" name="A parir" fill={AZUL} radius={[2, 2, 0, 0]} />
              <Line type="monotone" dataKey="saldo_lactacao" name="Saldo em lactação" stroke={DOURADO} strokeWidth={2} dot={{ r: 2 }} />
            </ComposedChart>
          </ResponsiveContainer>

          {data?.linhas?.length > 0 && (
            <table className="fazenda-table" style={{ marginTop: "0.9rem" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Mês" campo="mes" coluna={ordLinhas.coluna} dir={ordLinhas.dir} ordenar={ordLinhas.ordenar} />
                  <ThOrdenavel label="Vacas a secar" campo="secar" coluna={ordLinhas.coluna} dir={ordLinhas.dir} ordenar={ordLinhas.ordenar} />
                  <ThOrdenavel label="Vacas a parir" campo="parir" coluna={ordLinhas.coluna} dir={ordLinhas.dir} ordenar={ordLinhas.ordenar} />
                  <ThOrdenavel label="Saldo em lactação" campo="saldo_lactacao" coluna={ordLinhas.coluna} dir={ordLinhas.dir} ordenar={ordLinhas.ordenar} />
                </tr>
              </thead>
              <tbody>
                {ordLinhas.linhasOrdenadas.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.mes}</td>
                    <td>{r.secar}</td>
                    <td>{r.parir}</td>
                    <td style={{ color: "var(--dourado-light)", fontWeight: 700 }}>{r.saldo_lactacao}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}

// ── Componente principal ──
export default function RelatoriosGerenciais() {
  return (
    <div className="animate-in">
      <SecaoRecolhivel
        titulo="Distribuição de DEL por serviço"
        icon={Activity}
        defaultAberta={false}
        descricao="Velocidade com que o sistema devolve os animais ao serviço, por ordem de inseminação."
      >
        <CardDistribuicaoDel />
      </SecaoRecolhivel>

      <SecaoRecolhivel
        titulo="Distribuição das prenhezes por DEL"
        icon={TrendingUp}
        defaultAberta={false}
        descricao="Prenhezes produzidas e acumulado percentual a cada ciclo de 21 dias após o PEV."
      >
        <CardPrenhezesPorDel />
      </SecaoRecolhivel>

      <SecaoRecolhivel
        titulo="Distribuição de dias para diagnóstico de prenhez"
        icon={Stethoscope}
        defaultAberta={false}
        descricao="Quando as prenhezes foram identificadas × faixa ideal de diagnóstico."
      >
        <CardDiasDiagnostico />
      </SecaoRecolhivel>

      <SecaoRecolhivel
        titulo="Intervalo entre serviços"
        icon={Repeat}
        defaultAberta={false}
        descricao="Distribuição, em dias, do intervalo entre serviços consecutivos."
      >
        <CardBarrasFaixa
          nome="intervalo-servicos"
          desc={
            <>Distribuição, em dias, do intervalo entre serviços consecutivos. Reforça a importância de uma rotina
            rígida de checagem de prenhezes para acelerar a velocidade dos serviços.</>
          }
        />
      </SecaoRecolhivel>

      <SecaoRecolhivel
        titulo="Dias para re-inseminação"
        icon={Timer}
        defaultAberta={false}
        descricao="Dias desde a identificação como VAZIA até a re-inseminação."
      >
        <CardBarrasFaixa
          nome="dias-reinseminacao"
          desc={
            <>Distribuição, em dias, desde que a vaca foi identificada como VAZIA até ser re-inseminada. Quanto mais
            concentrado nos primeiros dias, mais ágil está a re-inseminação.</>
          }
        />
      </SecaoRecolhivel>

      <SecaoRecolhivel
        titulo="Taxa de serviço e taxa de prenhez por DEL"
        icon={Target}
        defaultAberta={false}
        descricao="Índices de velocidade em produzir prenhezes + acumulado de vacas prenhas."
      >
        <CardTaxaServicoPrenhez />
      </SecaoRecolhivel>

      <SecaoRecolhivel
        titulo="Fluxo mensal de vacas em lactação"
        icon={Milk}
        defaultAberta={false}
        descricao="Projeção do saldo de vacas em leite nos próximos meses."
      >
        <CardFluxoLactacao />
      </SecaoRecolhivel>
    </div>
  );
}
