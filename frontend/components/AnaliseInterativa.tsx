"use client";
import { useEffect, useMemo, useState } from "react";
import { LineChart as LineChartIcon, Info } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import { fetchIndicadoresMensais, type IndicadoresMensais } from "@/lib/api";

type Eixo = "mes" | "ano";

type Metrica = { key: string; label: string; unidade: "pct" | "n" | "kg" | "dias" };

// As ~20 métricas pedidas para cruzamento — cada uma vem pronta (por mês) do
// backend em /reproducao/indicadores-mensais; "variação" é a diferença mês a
// mês, já calculada no servidor.
const METRICAS: Metrica[] = [
  { key: "taxa_concepcao", label: "Taxa de concepção", unidade: "pct" },
  { key: "num_servicos", label: "Número de serviços", unidade: "n" },
  { key: "animais_inseminados", label: "Animais inseminados", unidade: "n" },
  { key: "qtd_positivos", label: "Quantidade de positivos", unidade: "n" },
  { key: "qtd_negativos", label: "Quantidade de negativos", unidade: "n" },
  { key: "animais_prenhes", label: "Animais prenhes", unidade: "n" },
  { key: "perdas_prenhez", label: "Perdas de prenhez", unidade: "n" },
  { key: "num_secagens", label: "Número de secagens", unidade: "n" },
  { key: "del_medio", label: "DEL (média)", unidade: "dias" },
  { key: "producao_leite", label: "Produção de leite (média)", unidade: "kg" },
  { key: "variacao_del", label: "Aumento de DEL (mês a mês)", unidade: "dias" },
  { key: "variacao_producao_leite", label: "Aumento de produção de leite (mês a mês)", unidade: "kg" },
  { key: "num_coberturas", label: "Número de coberturas", unidade: "n" },
  { key: "num_ias", label: "Número de IAs", unidade: "n" },
  { key: "num_montas_naturais", label: "Número de montas naturais", unidade: "n" },
  { key: "num_ia_cio", label: "Número de IA em cio", unidade: "n" },
  { key: "num_iatf", label: "Número de IATF", unidade: "n" },
];

const CORES = ["var(--dourado-light)", "var(--blue)", "var(--green-light)", "var(--red)", "var(--amber)", "#8B3A56", "#5A8FA3"];

const rotuloMes = (m: string) => {
  const [ano, mes] = m.split("-");
  return `${mes}/${ano.slice(2)}`;
};

function agregarPorAno(meses: string[], serie: (number | null)[], unidade: Metrica["unidade"]) {
  const porAno = new Map<string, (number | null)[]>();
  meses.forEach((m, i) => {
    const ano = m.slice(0, 4);
    (porAno.get(ano) ?? porAno.set(ano, []).get(ano)!).push(serie[i]);
  });
  const anos = Array.from(porAno.keys()).sort();
  const valores = anos.map((ano) => {
    const vals = (porAno.get(ano) || []).filter((v): v is number => v !== null);
    if (!vals.length) return null;
    if (unidade === "n") return vals.reduce((a, b) => a + b, 0);
    return Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10;
  });
  return { rotulos: anos, valores };
}

const UNIDADE_LABEL: Record<Metrica["unidade"], string> = { pct: "%", n: "", kg: "kg", dias: "d" };

/**
 * Substitui o gráfico fixo "Concepção por mês" por uma ferramenta configurável:
 * o usuário escolhe quais métricas cruzar (Y) e o eixo de tempo (ano/mês); o
 * gráfico é recalculado automaticamente. Métricas em escalas muito diferentes
 * (ex.: % e kg) são normalizadas (0–100% do próprio máximo) quando há mais de
 * uma selecionada, para permitir comparação visual — os valores reais
 * continuam disponíveis no tooltip.
 */
export default function AnaliseInterativa() {
  const [dados, setDados] = useState<IndicadoresMensais | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selecionadas, setSelecionadas] = useState<string[]>(["taxa_concepcao", "num_servicos"]);
  const [eixo, setEixo] = useState<Eixo>("mes");

  useEffect(() => {
    fetchIndicadoresMensais().then(setDados).catch((e) => setError(e.message));
  }, []);

  const toggle = (key: string) =>
    setSelecionadas((p) => (p.includes(key) ? p.filter((k) => k !== key) : [...p, key]));

  const { rotulos, seriesPorMetrica } = useMemo(() => {
    if (!dados) return { rotulos: [] as string[], seriesPorMetrica: {} as Record<string, (number | null)[]> };
    if (eixo === "mes") {
      return { rotulos: dados.meses, seriesPorMetrica: dados.series };
    }
    const seriesPorMetrica: Record<string, (number | null)[]> = {};
    let rotulos: string[] = [];
    for (const m of METRICAS) {
      const bruta = dados.series[m.key] || [];
      const { rotulos: anos, valores } = agregarPorAno(dados.meses, bruta, m.unidade);
      rotulos = anos;
      seriesPorMetrica[m.key] = valores;
    }
    return { rotulos, seriesPorMetrica };
  }, [dados, eixo]);

  const normalizar = selecionadas.length > 1;
  const chartData = useMemo(() => {
    return rotulos.map((r, i) => {
      const linha: Record<string, any> = { rotulo: eixo === "mes" ? rotuloMes(r) : r };
      selecionadas.forEach((key) => {
        const serie = seriesPorMetrica[key] || [];
        const v = serie[i];
        linha[key] = v;
        if (normalizar) {
          const max = Math.max(1e-9, ...serie.filter((x): x is number => x !== null).map(Math.abs));
          linha[`${key}__norm`] = v === null ? null : Math.round((v / max) * 1000) / 10;
        }
      });
      return linha;
    });
  }, [rotulos, selecionadas, seriesPorMetrica, normalizar, eixo]);

  const metricaPorKey = (key: string) => METRICAS.find((m) => m.key === key)!;

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };

  return (
    <div className="card mb-4">
      <div className="card-header mb-2 flex items-center gap-2"><LineChartIcon size={16} /> Análise interativa — cruzamento de métricas</div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginBottom: "0.75rem" }}>
        Escolha uma ou mais métricas e o eixo de tempo — o gráfico é montado automaticamente.
      </p>

      {error && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>Sem dados: {error}.</p>}

      <div className="flex flex-wrap items-center gap-3 mb-3">
        <div>
          <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Eixo X</label>
          <select style={selStyle} value={eixo} onChange={(e) => setEixo(e.target.value as Eixo)}>
            <option value="mes">Mês</option>
            <option value="ano">Ano</option>
          </select>
        </div>
      </div>

      <div className="flex flex-wrap gap-x-3 gap-y-1 mb-3" style={{ maxHeight: "6.5rem", overflowY: "auto", padding: "0.4rem", border: "1px solid var(--border)", borderRadius: "8px" }}>
        {METRICAS.map((m) => (
          <label key={m.key} className="flex items-center gap-1" style={{ fontSize: "0.75rem" }}>
            <input type="checkbox" checked={selecionadas.includes(m.key)} onChange={() => toggle(m.key)} /> {m.label}
          </label>
        ))}
      </div>

      {normalizar && (
        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
          <Info size={12} /> Mais de uma métrica selecionada — valores normalizados (% do máximo de cada uma) para comparar na mesma escala; passe o mouse para ver o valor real.
        </p>
      )}

      {!dados && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && !selecionadas.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Selecione ao menos uma métrica.</p>}

      {dados && !!selecionadas.length && (
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="rotulo" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
            <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} domain={normalizar ? [0, 100] : undefined} />
            <Tooltip
              contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, fontSize: "0.78rem" }}
              formatter={(value: any, name: any, item: any) => {
                const key = item?.dataKey?.toString().replace("__norm", "") || name;
                const m = metricaPorKey(key);
                const real = item?.payload?.[key];
                return [`${real ?? "—"}${UNIDADE_LABEL[m.unidade]}`, m.label];
              }}
            />
            <Legend wrapperStyle={{ fontSize: "0.75rem" }} formatter={(key: string) => metricaPorKey(key.replace("__norm", "")).label} />
            {selecionadas.map((key, i) => (
              <Line key={key} type="monotone" dataKey={normalizar ? `${key}__norm` : key} stroke={CORES[i % CORES.length]} strokeWidth={2} dot={{ r: 2 }} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
