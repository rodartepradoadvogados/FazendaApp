"use client";
import { useEffect, useMemo, useState } from "react";
import { Milk, AlertTriangle, Filter, TrendingUp, FlaskConical, Scale } from "lucide-react";
import { fetchControles, fetchQualidadeLeite, fetchRelatorioLeiteItalac } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

// Comparação numérica quando possível, senão alfabética — mesmo critério usado
// em toda a auditoria de ordenação (crescente por padrão em toda listagem).
function comparaNumero(a: string, b: string) {
  return isNaN(+a) || isNaN(+b) ? a.localeCompare(b) : +a - +b;
}

const COLUNAS_RANKING = [
  { header: "Vaca", key: "numero" }, { header: "Raça", key: "raca" }, { header: "Média (kg)", key: "media" },
  { header: "Pico (kg)", key: "pico" }, { header: "Última (kg)", key: "ultima" }, { header: "Pesagens", key: "n" },
];
const COLUNAS_FILTRADOS = [
  { header: "Vaca", key: "numero" }, { header: "Raça", key: "raca" }, { header: "Data", key: "dataFmt" },
  { header: "DEL (dias)", key: "del" }, { header: "Produção (kg)", key: "producaoFmt" },
];

type Ctrl = {
  numero: string; raca: string; data: string | null; ano: number | null; producao_kg: number | null; del: number | null;
  ordenha1_kg: number | null; ordenha2_kg: number | null; ordenha3_kg: number | null; grupo_primario: string | null;
};

const LOTES_LACTACAO = ["01", "02", "03"];
const codigoLote = (g: string | null) => (g && g.length >= 2 && /\d\d/.test(g.slice(0, 2)) ? g.slice(0, 2) : null);

const FAIXAS: [number, number, string][] = [
  [0, 30, "0-30"], [31, 60, "31-60"], [61, 90, "61-90"], [91, 120, "91-120"],
  [121, 150, "121-150"], [151, 200, "151-200"], [201, 300, "201-300"], [301, 9999, "301+"],
];

function media(v: number[]) { return v.length ? Math.round((10 * v.reduce((a, b) => a + b, 0)) / v.length) / 10 : 0; }
function opcoes<T>(a: T[], f: (x: T) => string | null) {
  const s = new Set<string>(); a.forEach((x) => { const v = f(x); if (v) s.add(v); });
  return Array.from(s).sort((x, y) => (isNaN(+x) || isNaN(+y) ? x.localeCompare(y) : +x - +y));
}

// Linha simples (produção do rebanho por controle)
function LineChart({ dados }: { dados: { data: string; total: number }[] }) {
  const W = 760, H = 220, m = { t: 14, r: 16, b: 40, l: 44 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const max = Math.max(1, ...dados.map((d) => d.total));
  const x = (i: number) => m.l + (iw / Math.max(1, dados.length - 1)) * i;
  const y = (v: number) => m.t + ih - (v / max) * ih;
  const pts = dados.map((d, i) => `${x(i)},${y(d.total)}`).join(" ");
  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ minWidth: 520 }} role="img">
        {[0, 0.5, 1].map((g) => (
          <g key={g}>
            <line x1={m.l} x2={W - m.r} y1={y(max * g)} y2={y(max * g)} stroke="var(--border)" />
            <text x={4} y={y(max * g) + 3} fontSize="9" fill="var(--text-muted)">{Math.round(max * g)}</text>
          </g>
        ))}
        {dados.length > 1 && <polyline points={pts} fill="none" stroke="var(--green-light)" strokeWidth="2" />}
        {dados.map((d, i) => (
          <circle key={i} cx={x(i)} cy={y(d.total)} r="2.5" fill="var(--green-light)"><title>{d.data}: {d.total} kg</title></circle>
        ))}
        {dados.map((d, i) => (i % Math.ceil(dados.length / 12 || 1) === 0) && (
          <text key={i} x={x(i)} y={H - m.b + 14} fontSize="8" fill="var(--text-muted)" textAnchor="middle"
            transform={`rotate(45 ${x(i)} ${H - m.b + 14})`}>{d.data.slice(5)}</text>
        ))}
      </svg>
    </div>
  );
}

type Qualidade = {
  id: number; numero_matriz: string | null; data_coleta: string;
  ccs: number | null; cbt: number | null; gordura_pct: number | null; proteina_pct: number | null;
  solidos_totais_pct: number | null; esd_pct: number | null; lactose_pct: number | null; observacao: string | null;
};
const INDICADORES_QUALIDADE = [
  { key: "ccs", label: "CCS", unidade: "mil céls./mL" },
  { key: "cbt", label: "CBT", unidade: "mil UFC/mL" },
  { key: "gordura_pct", label: "Gordura", unidade: "%" },
  { key: "proteina_pct", label: "Proteína", unidade: "%" },
  { key: "solidos_totais_pct", label: "Sólidos totais (ST)", unidade: "%" },
  { key: "esd_pct", label: "ESD", unidade: "%" },
  { key: "lactose_pct", label: "Lactose", unidade: "%" },
] as const;

type LinhaLeiteItalac = {
  competencia: string; controle_leiteiro_kg: number | null; controles_no_mes: number;
  entrega_litros: number | null; italac_litros: number | null; italac_receita: number | null;
  preco_medio_litro: number | null; ccs_medio: number | null; gordura_media_pct: number | null;
  nao_entregue_kg: number | null; consumo_bezerros_estimado_litros: number | null; consumo_outros_estimado_litros: number | null;
};

export default function ProducaoPage() {
  const [regs, setRegs] = useState<Ctrl[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fAno, setFAno] = useState("");
  const [fMes, setFMes] = useState("");
  const [fDelMin, setFDelMin] = useState("");
  const [fDelMax, setFDelMax] = useState("");

  const [ucModo, setUcModo] = useState<"animal" | "lote" | "rebanho">("rebanho");
  const [ucN, setUcN] = useState<1 | 2 | 3>(1);
  const [ucAnimal, setUcAnimal] = useState("");
  const [ucLote, setUcLote] = useState("");

  const [qualidade, setQualidade] = useState<Qualidade[] | null>(null);
  const [qlIndicador, setQlIndicador] = useState<(typeof INDICADORES_QUALIDADE)[number]["key"]>("ccs");
  const [qlDe, setQlDe] = useState("");
  const [qlAte, setQlAte] = useState("");

  useEffect(() => {
    fetchQualidadeLeite().then((d) => setQualidade(d.registros)).catch(() => {});
  }, []);

  const qlFiltrados = useMemo(() => {
    if (!qualidade) return [];
    return qualidade.filter((r) => (!qlDe || r.data_coleta >= qlDe) && (!qlAte || r.data_coleta <= qlAte));
  }, [qualidade, qlDe, qlAte]);

  const qlIndicadorInfo = INDICADORES_QUALIDADE.find((i) => i.key === qlIndicador)!;
  const qlSerie = useMemo(() => {
    return qlFiltrados
      .map((r) => ({ data: r.data_coleta, total: r[qlIndicador] }))
      .filter((d): d is { data: string; total: number } => d.total != null)
      .sort((a, b) => a.data.localeCompare(b.data));
  }, [qlFiltrados, qlIndicador]);
  const qlAtual = qlSerie.length ? qlSerie[qlSerie.length - 1].total : null;
  const qlMedia = qlSerie.length ? media(qlSerie.map((d) => d.total)) : null;

  const [relatorioItalac, setRelatorioItalac] = useState<{
    linhas: LinhaLeiteItalac[]; efetivo_bezerros: number; consumo_bezerros_dia_litros: number; consumo_bezerros_mes_litros: number;
  } | null>(null);
  useEffect(() => {
    fetchRelatorioLeiteItalac().then(setRelatorioItalac).catch(() => {});
  }, []);
  const ordItalac = useOrdenacao<LinhaLeiteItalac>(relatorioItalac?.linhas ?? []);

  useEffect(() => {
    fetchControles().then((d) => setRegs(d.controles)).catch((e) => setError(e.message));
  }, []);

  const delMin = fDelMin === "" ? null : Number(fDelMin);
  const delMax = fDelMax === "" ? null : Number(fDelMax);

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((r) =>
      (!fAno || String(r.ano) === fAno) &&
      (!fMes || (r.data ? r.data.slice(0, 7) === fMes : false)) &&
      (delMin === null || (r.del !== null && r.del >= delMin)) &&
      (delMax === null || (r.del !== null && r.del <= delMax))
    );
  }, [regs, fAno, fMes, delMin, delMax]);

  const comProd = useMemo(() => filtrados.filter((r) => r.producao_kg !== null && r.producao_kg > 0), [filtrados]);

  const curva = useMemo(() => FAIXAS.map(([lo, hi, rot]) => {
    const vals = comProd.filter((r) => r.del !== null && r.del >= lo && r.del <= hi).map((r) => r.producao_kg!);
    return { rot, media: media(vals), n: vals.length };
  }).filter((c) => c.n > 0), [comProd]);
  const maxCurva = Math.max(1, ...curva.map((c) => c.media));

  const serie = useMemo(() => {
    const by = new Map<string, number[]>();
    comProd.forEach((r) => { if (r.data) (by.get(r.data) ?? by.set(r.data, []).get(r.data)!).push(r.producao_kg!); });
    return Array.from(by.keys()).sort().slice(-18).map((data) => ({ data, total: Math.round(by.get(data)!.reduce((a, b) => a + b, 0) * 10) / 10, vacas: by.get(data)!.length }));
  }, [comProd]);

  const ranking = useMemo(() => {
    const by = new Map<string, Ctrl[]>();
    comProd.forEach((r) => (by.get(r.numero) ?? by.set(r.numero, []).get(r.numero)!).push(r));
    return Array.from(by.entries()).map(([numero, arr]) => {
      const ord = [...arr].sort((a, b) => (a.data! < b.data! ? -1 : 1));
      const vals = ord.map((r) => r.producao_kg!);
      return { numero, raca: arr[0].raca, media: media(vals), pico: Math.max(...vals), ultima: vals[vals.length - 1], n: arr.length };
    }).sort((a, b) => b.media - a.media);
  }, [comProd]);

  const filtradosOrdenadosBase = useMemo(() => [...filtrados].sort((a, b) => comparaNumero(a.numero, b.numero)), [filtrados]);
  const filtradosExport = useMemo(() => filtradosOrdenadosBase.map((r) => ({
    ...r, dataFmt: r.data ? new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR") : "—",
    producaoFmt: r.producao_kg != null ? r.producao_kg : "—",
  })), [filtradosOrdenadosBase]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  const animaisDisponiveis = useMemo(() => opcoes(regs ?? [], (r) => r.numero), [regs]);
  const lotesDisponiveis = useMemo(() => opcoes(regs ?? [], (r) => r.grupo_primario), [regs]);

  // Escopo do painel "Últimos controles": por animal, por lote (um selecionado) ou rebanho todo em lactação
  // (lotes cujo código de 2 dígitos é 01/02/03 — mesma convenção usada em Rebanho/Lançamentos).
  const ucNumerosEscopo = useMemo(() => {
    if (!regs) return new Set<string>();
    if (ucModo === "animal") return new Set(ucAnimal ? [ucAnimal] : []);
    if (ucModo === "lote") return new Set(ucLote ? regs.filter((r) => r.grupo_primario === ucLote).map((r) => r.numero) : []);
    return new Set(regs.filter((r) => LOTES_LACTACAO.includes(codigoLote(r.grupo_primario) || "")).map((r) => r.numero));
  }, [regs, ucModo, ucAnimal, ucLote]);

  // Últimos N controles por animal do escopo, ordenados mais recente primeiro.
  const ucRegistros = useMemo(() => {
    if (!regs || !ucNumerosEscopo.size) return [];
    const porAnimal = new Map<string, Ctrl[]>();
    regs.forEach((r) => { if (ucNumerosEscopo.has(r.numero)) (porAnimal.get(r.numero) ?? porAnimal.set(r.numero, []).get(r.numero)!).push(r); });
    const linhas: Ctrl[] = [];
    porAnimal.forEach((arr) => {
      const ord = [...arr].sort((a, b) => (a.data! > b.data! ? -1 : 1));
      linhas.push(...ord.slice(0, ucN));
    });
    return linhas.sort((a, b) => (a.numero === b.numero ? (a.data! < b.data! ? 1 : -1) : a.numero.localeCompare(b.numero)));
  }, [regs, ucNumerosEscopo, ucN]);

  // Linhas exibidas na tabela, já com a "noite" resolvida como campo próprio
  // (ordenha3 quando há 3 ordenhas, senão ordenha2) para poder ordenar por ela.
  const ucLinhas = useMemo(
    () => ucRegistros.map((r) => ({ ...r, noite_kg: r.ordenha3_kg ?? r.ordenha2_kg })),
    [ucRegistros]
  );

  // Relatório único do filtro selecionado: média e menor do próprio conjunto
  // mostrado na tabela (o mesmo escopo do animal/lote/rebanho filtrado), média
  // por ordenha (manhã/noite), quantidade de vacas e de controles do filtro.
  const ucValoresProducao = useMemo(() => ucRegistros.map((r) => r.producao_kg).filter((v): v is number => v != null), [ucRegistros]);
  const ucMedia = useMemo(() => media(ucValoresProducao), [ucValoresProducao]);
  const ucMenor = useMemo(() => (ucValoresProducao.length ? Math.min(...ucValoresProducao) : null), [ucValoresProducao]);
  const ucMediaManha = useMemo(() => media(ucRegistros.filter((r) => r.ordenha1_kg != null).map((r) => r.ordenha1_kg!)), [ucRegistros]);
  const ucMediaNoite = useMemo(() => {
    // "Noite" = última ordenha do dia lançada — ordenha3 quando há 3, senão ordenha2.
    const valores = ucRegistros.map((r) => (r.ordenha3_kg ?? r.ordenha2_kg)).filter((v): v is number => v != null);
    return media(valores);
  }, [ucRegistros]);
  const ucLabelEscopo = ucModo === "lote" ? "lote" : ucModo === "animal" ? "animal" : "rebanho";

  const ordUltimos = useOrdenacao(ucLinhas);
  const ordRanking = useOrdenacao(ranking);
  const ordFiltrados = useOrdenacao(filtradosOrdenadosBase);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Milk size={22} style={{ color: "var(--dourado-light)" }} /> Produção Leiteira
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Curva de lactação, evolução e ranking — filtre por ano, mês ou faixa de DEL (de/até).</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o controle leiteiro</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && (
        <>
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ano</label>
                <select style={selStyle} value={fAno} onChange={(e) => setFAno(e.target.value)}><option value="">Todos</option>{opcoes(regs, (r) => r.ano === null ? null : String(r.ano)).map((o) => <option key={o}>{o}</option>)}</select></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Mês</label>
                <select style={selStyle} value={fMes} onChange={(e) => setFMes(e.target.value)}><option value="">Todos</option>{opcoes(regs, (r) => r.data ? r.data.slice(0, 7) : null).map((o) => <option key={o}>{o}</option>)}</select></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>DEL de (dias)</label>
                <input type="number" min={0} inputMode="numeric" placeholder="ex.: 30" style={selStyle} value={fDelMin} onChange={(e) => setFDelMin(e.target.value)} /></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>DEL até (dias)</label>
                <input type="number" min={0} inputMode="numeric" placeholder="ex.: 120" style={selStyle} value={fDelMax} onChange={(e) => setFDelMax(e.target.value)} /></div>
            </div>
            {(fAno || fMes || fDelMin || fDelMax) && <button className="btn-ghost" style={{ marginTop: "0.75rem", fontSize: "0.75rem" }} onClick={() => { setFAno(""); setFMes(""); setFDelMin(""); setFDelMax(""); }}>Limpar filtros</button>}
          </div>

          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Milk size={14} /> Últimos controles leiteiros</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ver</label>
                <select style={selStyle} value={ucN} onChange={(e) => setUcN(Number(e.target.value) as 1 | 2 | 3)}>
                  <option value={1}>Último controle</option>
                  <option value={2}>2 últimos controles</option>
                  <option value={3}>3 últimos controles</option>
                </select></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Por</label>
                <select style={selStyle} value={ucModo} onChange={(e) => setUcModo(e.target.value as any)}>
                  <option value="rebanho">Rebanho todo em lactação</option>
                  <option value="lote">Lote/grupo</option>
                  <option value="animal">Um animal</option>
                </select></div>
              {ucModo === "animal" && (
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
                  <select style={selStyle} value={ucAnimal} onChange={(e) => setUcAnimal(e.target.value)}>
                    <option value="">Selecione…</option>{animaisDisponiveis.map((n) => <option key={n}>{n}</option>)}
                  </select></div>
              )}
              {ucModo === "lote" && (
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lote/grupo</label>
                  <select style={selStyle} value={ucLote} onChange={(e) => setUcLote(e.target.value)}>
                    <option value="">Selecione…</option>{lotesDisponiveis.map((l) => <option key={l}>{l}</option>)}
                  </select></div>
              )}
            </div>

            {ucRegistros.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-3">
                <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{ucMedia} kg</p>
                  <p className="kpi-label">Média do {ucLabelEscopo}</p></div>
                <div className="kpi-card"><p className="kpi-value">{ucMenor ?? "—"} kg</p><p className="kpi-label">Menor</p></div>
                <div className="kpi-card"><p className="kpi-value">{ucMediaManha || "—"} kg</p><p className="kpi-label">Média ordenha — manhã</p></div>
                <div className="kpi-card"><p className="kpi-value">{ucMediaNoite || "—"} kg</p><p className="kpi-label">Média ordenha — noite</p></div>
                <div className="kpi-card"><p className="kpi-value">{ucNumerosEscopo.size}</p><p className="kpi-label">Vacas no filtro</p></div>
                <div className="kpi-card"><p className="kpi-value">{ucRegistros.length}</p><p className="kpi-label">Controles no filtro</p></div>
              </div>
            )}

            <div className="overflow-x-auto" style={{ maxHeight: "360px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <ThOrdenavel label="Vaca" campo="numero" coluna={ordUltimos.coluna} dir={ordUltimos.dir} ordenar={ordUltimos.ordenar} />
                  <ThOrdenavel label="Lote" campo="grupo_primario" coluna={ordUltimos.coluna} dir={ordUltimos.dir} ordenar={ordUltimos.ordenar} />
                  <ThOrdenavel label="Data" campo="data" coluna={ordUltimos.coluna} dir={ordUltimos.dir} ordenar={ordUltimos.ordenar} />
                  <ThOrdenavel label="Manhã (kg)" campo="ordenha1_kg" coluna={ordUltimos.coluna} dir={ordUltimos.dir} ordenar={ordUltimos.ordenar} alinhar="right" />
                  <ThOrdenavel label="Noite (kg)" campo="noite_kg" coluna={ordUltimos.coluna} dir={ordUltimos.dir} ordenar={ordUltimos.ordenar} alinhar="right" />
                  <ThOrdenavel label="Total (kg)" campo="producao_kg" coluna={ordUltimos.coluna} dir={ordUltimos.dir} ordenar={ordUltimos.ordenar} alinhar="right" />
                </tr></thead>
                <tbody>
                  {ordUltimos.linhasOrdenadas.map((r, i) => (
                    <tr key={`${r.numero}-${r.data}-${i}`}>
                      <td style={{ fontWeight: 700 }}>{r.numero}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.grupo_primario || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.data ? new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td style={{ textAlign: "right" }}>{r.ordenha1_kg ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{r.noite_kg ?? "—"}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>{r.producao_kg ?? "—"}</td>
                    </tr>
                  ))}
                  {!ucRegistros.length && (
                    <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>
                      {ucModo === "animal" && !ucAnimal ? "Selecione um animal." : ucModo === "lote" && !ucLote ? "Selecione um lote." : "Nenhum controle encontrado."}
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><FlaskConical size={14} /> Qualidade do leite</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Período — de</label>
                <input type="date" style={selStyle} value={qlDe} onChange={(e) => setQlDe(e.target.value)} /></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>até</label>
                <input type="date" style={selStyle} value={qlAte} onChange={(e) => setQlAte(e.target.value)} /></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Indicador</label>
                <select style={selStyle} value={qlIndicador} onChange={(e) => setQlIndicador(e.target.value as any)}>
                  {INDICADORES_QUALIDADE.map((i) => <option key={i.key} value={i.key}>{i.label}</option>)}
                </select></div>
            </div>
            <div className="grid grid-cols-2 gap-4 mb-3">
              <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{qlAtual ?? "—"} {qlAtual != null ? qlIndicadorInfo.unidade : ""}</p>
                <p className="kpi-label">{qlIndicadorInfo.label} atual (última coleta)</p></div>
              <div className="kpi-card"><p className="kpi-value">{qlMedia ?? "—"} {qlMedia != null ? qlIndicadorInfo.unidade : ""}</p>
                <p className="kpi-label">{qlIndicadorInfo.label} média no período</p></div>
            </div>
            {qlSerie.length ? <LineChart dados={qlSerie} /> : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem coletas de qualidade do leite no filtro.</p>}
          </div>

          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Scale size={14} /> Controle leiteiro × Entrega mensal × ITALAC</div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              Compara o que foi pesado no controle leiteiro, o que foi entregue ao laticínio (lançamento mensal) e o que a
              ITALAC faturou (contas gerenciais). A diferença entre pesado e entregue é consumo próprio da fazenda — parte
              dela é a projeção de leite na dieta das bezerras/bezerros; o restante é consumo estimado da equipe/família.
            </p>
            {relatorioItalac && relatorioItalac.efetivo_bezerros > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
                <div className="kpi-card"><p className="kpi-value">{relatorioItalac.efetivo_bezerros}</p>
                  <p className="kpi-label">Bezerras/bezerros no rebanho</p></div>
                <div className="kpi-card"><p className="kpi-value">{relatorioItalac.consumo_bezerros_dia_litros} L</p>
                  <p className="kpi-label">Leite na dieta/dia (projetado)</p></div>
                <div className="kpi-card"><p className="kpi-value">{relatorioItalac.consumo_bezerros_mes_litros} L</p>
                  <p className="kpi-label">Projeção mensal de consumo</p></div>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <ThOrdenavel label="Competência" campo="competencia" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} />
                  <ThOrdenavel label="Controle (kg)" campo="controle_leiteiro_kg" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} alinhar="right" />
                  <ThOrdenavel label="Entregue (L)" campo="entrega_litros" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} alinhar="right" />
                  <ThOrdenavel label="ITALAC (L)" campo="italac_litros" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} alinhar="right" />
                  <ThOrdenavel label="Receita ITALAC (R$)" campo="italac_receita" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} alinhar="right" />
                  <ThOrdenavel label="Preço médio (R$/L)" campo="preco_medio_litro" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} alinhar="right" />
                  <ThOrdenavel label="CCS médio" campo="ccs_medio" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} alinhar="right" />
                  <ThOrdenavel label="Não entregue (kg)" campo="nao_entregue_kg" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} alinhar="right" />
                  <ThOrdenavel label="Bezerros (L, est.)" campo="consumo_bezerros_estimado_litros" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} alinhar="right" />
                  <ThOrdenavel label="Equipe/fazenda (L, est.)" campo="consumo_outros_estimado_litros" coluna={ordItalac.coluna} dir={ordItalac.dir} ordenar={ordItalac.ordenar} alinhar="right" />
                </tr></thead>
                <tbody>
                  {ordItalac.linhasOrdenadas.map((l) => (
                    <tr key={l.competencia}>
                      <td>{l.competencia}</td>
                      <td style={{ textAlign: "right" }}>{l.controle_leiteiro_kg ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.entrega_litros ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.italac_litros ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.italac_receita != null ? l.italac_receita.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) : "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.preco_medio_litro != null ? l.preco_medio_litro.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) : "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.ccs_medio ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.nao_entregue_kg ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.consumo_bezerros_estimado_litros ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.consumo_outros_estimado_litros ?? "—"}</td>
                    </tr>
                  ))}
                  {!ordItalac.linhasOrdenadas.length && (
                    <tr><td colSpan={10} style={{ color: "var(--text-muted)" }}>Sem dados de controle leiteiro, entrega mensal ou receita da ITALAC ainda.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div className="card">
              <div className="card-header mb-3 flex items-center gap-2"><TrendingUp size={14} /> Curva de Lactação (média por DEL)</div>
              <div className="space-y-2">
                {curva.map((c) => (
                  <div key={c.rot} className="flex items-center gap-2">
                    <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", minWidth: "4rem" }}>{c.rot}d</span>
                    <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: "4px", height: "16px", overflow: "hidden" }}><div style={{ width: `${(c.media / maxCurva) * 100}%`, height: "100%", background: "var(--green-light)", minWidth: "2px" }} /></div>
                    <span style={{ fontSize: "0.75rem", fontWeight: 700, minWidth: "5.5rem", textAlign: "right" }}>{c.media} kg <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>({c.n})</span></span>
                  </div>
                ))}
                {!curva.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem dados no filtro.</p>}
              </div>
            </div>
            <div className="card">
              <div className="card-header mb-2">Produção do Rebanho por Controle (kg)</div>
              {serie.length ? <LineChart dados={serie} /> : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem dados no filtro.</p>}
            </div>
          </div>

          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center justify-between">
              <span>Ranking de Produção (top 20 por média)</span>
              <ExportarBotoes titulo="Ranking de Produção Leiteira" nomeArquivoBase="ranking_producao" colunas={COLUNAS_RANKING} linhas={ranking} />
            </div>
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Vaca" campo="numero" coluna={ordRanking.coluna} dir={ordRanking.dir} ordenar={ordRanking.ordenar} />
                <ThOrdenavel label="Raça" campo="raca" coluna={ordRanking.coluna} dir={ordRanking.dir} ordenar={ordRanking.ordenar} />
                <ThOrdenavel label="Média" campo="media" coluna={ordRanking.coluna} dir={ordRanking.dir} ordenar={ordRanking.ordenar} />
                <ThOrdenavel label="Pico" campo="pico" coluna={ordRanking.coluna} dir={ordRanking.dir} ordenar={ordRanking.ordenar} />
                <ThOrdenavel label="Última" campo="ultima" coluna={ordRanking.coluna} dir={ordRanking.dir} ordenar={ordRanking.ordenar} />
                <ThOrdenavel label="Pesagens" campo="n" coluna={ordRanking.coluna} dir={ordRanking.dir} ordenar={ordRanking.ordenar} />
              </tr></thead>
              <tbody>
                {ordRanking.linhasOrdenadas.slice(0, 20).map((v) => (
                  <tr key={v.numero}>
                    <td style={{ fontWeight: 700 }}>{v.numero}</td>
                    <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{v.raca}</td>
                    <td style={{ color: "var(--green-light)", fontWeight: 600 }}>{v.media} kg</td>
                    <td>{v.pico} kg</td><td>{v.ultima} kg</td>
                    <td style={{ color: "var(--text-muted)" }}>{v.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <div className="card-header mb-3 flex items-center justify-between">
              <span>Registros filtrados ({filtrados.length})</span>
              <ExportarBotoes titulo="Produção filtrada — Controle leiteiro" nomeArquivoBase="producao_filtrada" colunas={COLUNAS_FILTRADOS} linhas={filtradosExport} />
            </div>
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <ThOrdenavel label="Vaca" campo="numero" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Raça" campo="raca" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Data" campo="data" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="DEL (dias)" campo="del" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Produção (kg)" campo="producao_kg" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                </tr></thead>
                <tbody>
                  {ordFiltrados.linhasOrdenadas.map((r, i) => (
                    <tr key={`${r.numero}-${r.data}-${i}`}>
                      <td style={{ fontWeight: 700 }}>{r.numero}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{r.raca}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.data ? new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td>{r.del ?? "—"}</td>
                      <td>{r.producao_kg != null ? `${r.producao_kg} kg` : "—"}</td>
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum registro no filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
