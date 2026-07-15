"use client";
import { useEffect, useMemo, useState } from "react";
import { Sparkles, Search, AlertTriangle } from "lucide-react";
import {
  fetchCatalogoRelatorioPersonalizado, gerarRelatorioPersonalizado,
  type ParametroRelatorioPersonalizado,
} from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";

const MAX_PARAMETROS = 10;
const MAX_PARAMETROS_GRAFICO = 5;
const MAX_ANIMAIS_GRAFICO = 80;

const CORES = ["#c9a24b", "#8B3A56", "#4a90a4", "#7a9e5e", "#b45f5f"];

const inputStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

/**
 * Relatório personalizado (Análise) — v1 livre: escolha até 10 parâmetros
 * (um valor por animal) para montar uma tabela e, opcionalmente, um gráfico
 * de barras com até 5 desses parâmetros (só os numéricos). Se algum parâmetro
 * de data for escolhido, abre um filtro de período (de/até).
 */
export default function RelatorioPersonalizado() {
  const [catalogo, setCatalogo] = useState<ParametroRelatorioPersonalizado[]>([]);
  const [selecionados, setSelecionados] = useState<string[]>([]);
  const [montarGrafico, setMontarGrafico] = useState(false);
  const [parametrosGrafico, setParametrosGrafico] = useState<string[]>([]);
  const [dataDe, setDataDe] = useState("");
  const [dataAte, setDataAte] = useState("");
  const [resultado, setResultado] = useState<{ colunas: ParametroRelatorioPersonalizado[]; linhas: Record<string, any>[] } | null>(null);
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
      if (prev.length >= MAX_PARAMETROS) return prev;
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
    }).then(setResultado).catch((e) => setErro(e.message)).finally(() => setCarregando(false));
  };

  const linhasGrafico = useMemo(() => {
    if (!resultado) return [];
    return resultado.linhas.slice(0, MAX_ANIMAIS_GRAFICO);
  }, [resultado]);

  const colunasExport = useMemo(
    () => resultado ? [{ header: "Nº animal", key: "numero" }, ...resultado.colunas.filter((c) => c.id !== "numero").map((c) => ({ header: c.label, key: c.id }))] : [],
    [resultado]
  );

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Sparkles size={22} style={{ color: "var(--dourado-light)" }} /> Relatório personalizado</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Escolha até {MAX_PARAMETROS} parâmetros para montar sua própria tabela (um valor por animal) e, se quiser, um gráfico com até {MAX_PARAMETROS_GRAFICO} deles.
          Versão inicial — vamos lapidar conforme o uso.
        </p>
      </div>

      <div className="card mb-4">
        <div className="card-header mb-3">Parâmetros ({selecionados.length}/{MAX_PARAMETROS})</div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from(porCategoria.entries()).map(([categoria, params]) => (
            <div key={categoria}>
              <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.35rem" }}>{categoria}</p>
              <div className="space-y-1">
                {params.map((p) => {
                  const marcado = selecionados.includes(p.id);
                  const desabilitado = !marcado && selecionados.length >= MAX_PARAMETROS;
                  return (
                    <label key={p.id} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", cursor: desabilitado ? "not-allowed" : "pointer", opacity: desabilitado ? 0.5 : 1 }}>
                      <input type="checkbox" checked={marcado} disabled={desabilitado} onChange={() => alternarParametro(p.id)} />
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
                  <Tooltip contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", fontSize: "0.8rem" }} />
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
                    <th>Nº animal</th>
                    {resultado.colunas.filter((c) => c.id !== "numero").map((c) => <th key={c.id}>{c.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {resultado.linhas.map((l) => (
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
