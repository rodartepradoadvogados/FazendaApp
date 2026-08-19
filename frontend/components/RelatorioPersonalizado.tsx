"use client";
import { useEffect, useMemo, useState } from "react";
import { Sparkles, Search, AlertTriangle } from "lucide-react";
import {
  fetchCatalogoRelatorioPersonalizado, gerarRelatorioPersonalizado,
  type ParametroRelatorioPersonalizado, type ResumoRelatorioPersonalizado,
} from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

const MAX_PARAMETROS_GRAFICO = 8;
const MAX_ANIMAIS_GRAFICO = 80;

const CORES = ["#c9a24b", "#8B3A56", "#4a90a4", "#7a9e5e", "#b45f5f", "#5b8fb0", "#a15c9e", "#6b9e3f"];

const RESUMO_ITENS: { key: keyof ResumoRelatorioPersonalizado; label: string; sufixo?: string }[] = [
  { key: "quantidade_animais", label: "Quantidade de animais" },
  { key: "taxa_servico_pct", label: "Taxa de serviço", sufixo: "%" },
  { key: "taxa_concepcao_pct", label: "Taxa de concepção", sufixo: "%" },
  // Rótulo "Fêmeas prenhas" (não "Taxa de prenhez"): o campo é inventário —
  // % do rebanho APTO que está prenhe hoje — e não a taxa formal do
  // programa reprodutivo (PREG ÷ PG ELIG) de /reproducao/ciclos-21-dias, que
  // já usa esse mesmo nome "Taxa de prenhez". Mesmo texto usado na Capa
  // (Indicadores > Gerais) e nas outras 3 telas que mostram este campo.
  { key: "taxa_prenhez_pct", label: "Fêmeas prenhas", sufixo: "%" },
  { key: "novilhas_aptas_ate_meses", label: "Novilhas aptas até X meses" },
  { key: "quantidade_perda_prenhez", label: "Quantidade de perda de prenhez" },
  { key: "percentual_perda_prenhez_pct", label: "Percentual de perda de prenhez", sufixo: "%" },
  { key: "percentual_nascimento_macho_pct", label: "Nascimento de machos", sufixo: "%" },
  { key: "percentual_nascimento_femea_pct", label: "Nascimento de fêmeas", sufixo: "%" },
  { key: "taxa_cura_pct", label: "Taxa de cura", sufixo: "%" },
];

const inputStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

/**
 * Relatório personalizado — escolha livremente quantos parâmetros quiser (um
 * valor por animal) para montar sua própria tabela e, opcionalmente, um
 * gráfico de barras com até {MAX_PARAMETROS_GRAFICO} desses parâmetros (só os
 * numéricos). Se algum parâmetro de data for escolhido, abre um filtro de
 * período (de/até). O card "Resumo do período" traz métricas agregadas do
 * rebanho (taxas, novilhas aptas, nascimentos, cura) que não fazem sentido
 * por animal.
 */
export default function RelatorioPersonalizado() {
  const [catalogo, setCatalogo] = useState<ParametroRelatorioPersonalizado[]>([]);
  const [selecionados, setSelecionados] = useState<string[]>([]);
  const [montarGrafico, setMontarGrafico] = useState(false);
  const [parametrosGrafico, setParametrosGrafico] = useState<string[]>([]);
  const [dataDe, setDataDe] = useState("");
  const [dataAte, setDataAte] = useState("");
  const [novilhasAptasMeses, setNovilhasAptasMeses] = useState("15");
  const [resultado, setResultado] = useState<{ colunas: ParametroRelatorioPersonalizado[]; linhas: Record<string, any>[]; resumo: ResumoRelatorioPersonalizado } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  useEffect(() => { fetchCatalogoRelatorioPersonalizado().then(setCatalogo).catch((e) => setErro(e.message)); }, []);

  const porCategoria = useMemo(() => {
    const m = new Map<string, ParametroRelatorioPersonalizado[]>();
    catalogo.forEach((p) => { const arr = m.get(p.categoria) || []; arr.push(p); m.set(p.categoria, arr); });
    return m;
  }, [catalogo]);
  const porId = useMemo(() => new Map(catalogo.map((p) => [p.id, p])), [catalogo]);

  const temParametroData = useMemo(() => selecionados.some((id) => porId.get(id)?.tipo === "data"), [selecionados, porId]);
  const numericosSelecionados = useMemo(() => selecionados.filter((id) => porId.get(id)?.tipo === "numero"), [selecionados, porId]);

  function alternarParametro(id: string) {
    setSelecionados((prev) => {
      if (prev.includes(id)) {
        setParametrosGrafico((g) => g.filter((x) => x !== id));
        return prev.filter((x) => x !== id);
      }
      return [...prev, id];
    });
  }
  function alternarParametroGrafico(id: string) {
    setParametrosGrafico((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= MAX_PARAMETROS_GRAFICO) return prev;
      return [...prev, id];
    });
  }

  const gerar = () => {
    setErro(null);
    if (!selecionados.length) { setErro("Selecione ao menos 1 parâmetro."); return; }
    setCarregando(true);
    gerarRelatorioPersonalizado({
      parametros: selecionados,
      data_de: temParametroData ? (dataDe || undefined) : undefined,
      data_ate: temParametroData ? (dataAte || undefined) : undefined,
      novilhas_aptas_meses: Number(novilhasAptasMeses) || 15,
    }).then(setResultado).catch((e) => setErro(e.message)).finally(() => setCarregando(false));
  };

  const linhasGrafico = useMemo(() => {
    if (!resultado) return [];
    return resultado.linhas.slice(0, MAX_ANIMAIS_GRAFICO);
  }, [resultado]);

  const ord = useOrdenacao(resultado?.linhas ?? []);

  const colunasExport = useMemo(
    () => resultado ? [{ header: "Nº animal", key: "numero" }, ...resultado.colunas.filter((c) => c.id !== "numero").map((c) => ({ header: c.label, key: c.id }))] : [],
    [resultado]
  );

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Sparkles size={22} style={{ color: "var(--dourado-light)" }} /> Relatório personalizado</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Escolha quantos parâmetros quiser para montar sua própria tabela (um valor por animal) e, se quiser, um gráfico com até {MAX_PARAMETROS_GRAFICO} deles.
        </p>
      </div>

      <div className="card mb-4">
        <div className="card-header mb-3">Parâmetros ({selecionados.length} selecionado{selecionados.length !== 1 ? "s" : ""})</div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from(porCategoria.entries()).map(([categoria, params]) => (
            <div key={categoria}>
              <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.35rem" }}>{categoria}</p>
              <div className="space-y-1">
                {params.map((p) => {
                  const marcado = selecionados.includes(p.id);
                  return (
                    <label key={p.id} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", cursor: "pointer" }}>
                      <input type="checkbox" checked={marcado} onChange={() => alternarParametro(p.id)} />
                      {p.label}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {temParametroData && (
          <div className="grid grid-cols-2 gap-3 mt-4" style={{ maxWidth: "420px" }}>
            <div><label style={lbl}>Período — de</label><input type="date" style={inputStyle} value={dataDe} onChange={(e) => setDataDe(e.target.value)} /></div>
            <div><label style={lbl}>Período — até</label><input type="date" style={inputStyle} value={dataAte} onChange={(e) => setDataAte(e.target.value)} /></div>
          </div>
        )}

        <div className="mt-4" style={{ maxWidth: "320px" }}>
          <label style={lbl}>Novilhas aptas até quantos meses? (usado no Resumo do período)</label>
          <input type="number" min={1} style={inputStyle} value={novilhasAptasMeses} onChange={(e) => setNovilhasAptasMeses(e.target.value)} />
        </div>

        <div className="mt-4" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem", cursor: "pointer" }}>
            <input type="checkbox" checked={montarGrafico} onChange={(e) => setMontarGrafico(e.target.checked)} /> Montar gráfico
          </label>
          {montarGrafico && (
            <div className="mt-2">
              {!numericosSelecionados.length ? (
                <p style={{ fontSize: "0.78rem", color: "var(--amber)" }}>
                  <AlertTriangle size={12} style={{ display: "inline", marginRight: "0.2rem" }} />
                  Nenhum dos parâmetros escolhidos é numérico — selecione ao menos um parâmetro numérico para montar o gráfico.
                </p>
              ) : (
                <>
                  <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.3rem" }}>
                    Escolha até {MAX_PARAMETROS_GRAFICO} parâmetros numéricos para o gráfico ({parametrosGrafico.length}/{MAX_PARAMETROS_GRAFICO}):
                  </p>
                  <div className="flex flex-wrap gap-3">
                    {numericosSelecionados.map((id) => {
                      const p = porId.get(id)!;
                      const marcado = parametrosGrafico.includes(id);
                      const desabilitado = !marcado && parametrosGrafico.length >= MAX_PARAMETROS_GRAFICO;
                      return (
                        <label key={id} style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem", cursor: desabilitado ? "not-allowed" : "pointer", opacity: desabilitado ? 0.5 : 1 }}>
                          <input type="checkbox" checked={marcado} disabled={desabilitado} onChange={() => alternarParametroGrafico(id)} /> {p.label}
                        </label>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem", marginTop: "0.75rem" }}>{erro}</p>}
        <button className="btn-primary mt-4" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={gerar} disabled={carregando}>
          <Search size={14} /> {carregando ? "Gerando…" : "Gerar relatório"}
        </button>
      </div>

      {resultado && (
        <>
          <div className="card mb-4">
            <div className="card-header mb-3">Resumo do período</div>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
              Métricas agregadas do rebanho — não são por animal, por isso ficam à parte da tabela.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {RESUMO_ITENS.map((item) => {
                const v = resultado.resumo[item.key];
                return (
                  <div key={item.key} style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.7rem" }}>
                    <p style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--dourado-light)" }}>
                      {v === null || v === undefined ? "—" : `${v}${item.sufixo || ""}`}
                    </p>
                    <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{item.label}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {montarGrafico && !!parametrosGrafico.length && (
            <div className="card mb-4">
              <div className="card-header mb-3">Gráfico</div>
              {resultado.linhas.length > MAX_ANIMAIS_GRAFICO && (
                <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                  Mostrando os primeiros {MAX_ANIMAIS_GRAFICO} de {resultado.linhas.length} animais — refine o período para ver menos animais.
                </p>
              )}
              <ResponsiveContainer width="100%" height={360}>
                <BarChart data={linhasGrafico}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="numero" tick={{ fontSize: 10 }} interval={0} angle={-45} textAnchor="end" height={60} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", fontSize: "0.8rem" }} />
                  <Legend wrapperStyle={{ fontSize: "0.78rem" }} />
                  {parametrosGrafico.map((id, i) => (
                    <Bar key={id} dataKey={id} name={porId.get(id)?.label || id} fill={CORES[i % CORES.length]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>Tabela ({resultado.linhas.length} animal(is))</div>
              <ExportarBotoes titulo="Relatório personalizado" colunas={colunasExport} linhas={resultado.linhas} nomeArquivoBase="relatorio_personalizado" disabled={!resultado.linhas.length} />
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead>
                  <tr>
                    <ThOrdenavel label="Nº animal" campo="numero" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                    {resultado.colunas.filter((c) => c.id !== "numero").map((c) => (
                      <ThOrdenavel key={c.id} label={c.label} campo={c.id} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar={c.tipo === "numero" ? "right" : undefined} />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ord.linhasOrdenadas.map((l) => (
                    <tr key={l.numero}>
                      <td style={{ fontWeight: 700 }}>{l.numero}</td>
                      {resultado.colunas.filter((c) => c.id !== "numero").map((c) => (
                        <td key={c.id} style={{ fontSize: "0.8rem", textAlign: c.tipo === "numero" ? "right" : "left" }}>
                          {c.tipo === "booleano" ? (l[c.id] ? "Sim" : "Não") : (l[c.id] ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {!resultado.linhas.length && (
                    <tr><td colSpan={resultado.colunas.length} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum animal encontrado para o filtro.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
