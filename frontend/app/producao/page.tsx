"use client";
import { useEffect, useMemo, useState } from "react";
import { Milk, AlertTriangle, Filter, TrendingUp, FlaskConical, Scale, Droplets, Syringe } from "lucide-react";
import { fetchControles, fetchQualidadeLeite, fetchRelatorioControleEntrega, fetchAnimais, fetchAgenda, fetchRelatorioBst, ehAdmin } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { SecaoRecolhivel, MultiFiltro, Indicador } from "@/components/ui";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { AnimalPicker } from "@/components/AnimalPicker";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { AnimalRow } from "@/components/AnimalModal";
import { TabelasStatusBst } from "@/components/PainelLancarBst";

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
  ordem_parto: number | null; data_ult_parto: string | null;
  ordenha1_kg: number | null; ordenha2_kg: number | null; ordenha3_kg: number | null; grupo_primario: string | null;
  usuario_nome?: string | null;
};

const LOTES_LACTACAO = ["01", "02", "03"];
// Nome do mês (o filtro de mês não repete o ano — o ano tem seu próprio filtro).
const MESES_NOME: Record<string, string> = {
  "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril", "05": "Maio", "06": "Junho",
  "07": "Julho", "08": "Agosto", "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro",
};
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
  solidos_totais_pct: number | null; esd_pct: number | null; lactose_pct: number | null; nul: number | null; observacao: string | null;
  // Bonificação/penalização estimada (#548) — comparação contra as faixas
  // cadastradas em Configurações > Parâmetros; null = sem faixa ativa cadastrada.
  bonificacao_por_litro?: number | null;
  bonificacao_detalhe?: { indicador: string; valor: number; ajuste_por_litro: number }[];
};

function formatarReaisPorLitro(v: number) {
  return `${v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 3, maximumFractionDigits: 4 })}/L`;
}
const INDICADORES_QUALIDADE = [
  { key: "ccs", label: "CCS", unidade: "mil céls./mL" },
  { key: "cbt", label: "CBT", unidade: "mil UFC/mL" },
  { key: "gordura_pct", label: "Gordura", unidade: "%" },
  { key: "proteina_pct", label: "Proteína", unidade: "%" },
  { key: "solidos_totais_pct", label: "Sólidos totais (ST)", unidade: "%" },
  { key: "esd_pct", label: "ESD", unidade: "%" },
  { key: "lactose_pct", label: "Lactose", unidade: "%" },
  { key: "nul", label: "NUL (ureia)", unidade: "mg/dL" },
] as const;

type RelatorioControleEntrega = {
  data_inicio: string; data_fim: string; dias_periodo: number; dias_com_controle: number;
  media_diaria_controle_kg: number | null; controle_projetado_kg: number | null; desvio_padrao_pct: number | null;
  entrega_projetada_kg: number | null; receita_projetada: number | null; preco_medio_kg: number | null;
  nao_entregue_kg: number | null; leite_bezerros_kg_dia: number; bezerros_kg: number; bezerros_fonte: string; equipe_kg: number | null;
};

function ProducaoLeiteira() {
  const admin = ehAdmin();
  const [regs, setRegs] = useState<Ctrl[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fAno, setFAno] = useState<string[]>([]);
  const [fMes, setFMes] = useState<string[]>([]);
  const [fDelMin, setFDelMin] = useState("");
  const [fDelMax, setFDelMax] = useState("");
  const [fOrdemParto, setFOrdemParto] = useState<string[]>([]);

  const [ucModo, setUcModo] = useState<"animal" | "lote" | "rebanho">("rebanho");
  const [ucN, setUcN] = useState<1 | 2 | 3 | "todos">(1);
  const [ucAnimal, setUcAnimal] = useState("");
  const [ucLotes, setUcLotes] = useState<string[]>([]);
  // Lista real de animais (para o seletor "lista vermelha" — Nº/Grupo/Categoria/Sit.Rep./DEL).
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  useEffect(() => { fetchAnimais().then(setAnimais).catch(() => {}); }, []);

  const [qualidade, setQualidade] = useState<Qualidade[] | null>(null);
  const [qualidadeErro, setQualidadeErro] = useState<string | null>(null);
  // #548 — se não há nenhuma faixa de bonificação ativa cadastrada em
  // Configurações > Parâmetros, a coluna de ajuste estimado mostra um aviso
  // em vez de "R$ 0,00" (que seria um valor incorreto, não "sem bônus").
  const [qlTemFaixasBonificacao, setQlTemFaixasBonificacao] = useState(true);
  const [qlIndicador, setQlIndicador] = useState<(typeof INDICADORES_QUALIDADE)[number]["key"]>("ccs");
  const [qlDe, setQlDe] = useState("");
  const [qlAte, setQlAte] = useState("");
  // Duas caixas de seleção independentes (em vez de um único filtro exclusivo) —
  // dá para ver tanque e animal juntos ou isolar só um dos dois.
  const [qlTanque, setQlTanque] = useState(true);
  const [qlIndividual, setQlIndividual] = useState(true);

  useEffect(() => {
    fetchQualidadeLeite()
      .then((d) => { setQualidade(d.registros); setQlTemFaixasBonificacao(!!d.tem_faixas_bonificacao); })
      .catch((e) => setQualidadeErro(e.message));
  }, []);

  const qlFiltrados = useMemo(() => {
    if (!qualidade) return [];
    return qualidade.filter((r) =>
      (!qlDe || r.data_coleta >= qlDe) && (!qlAte || r.data_coleta <= qlAte) &&
      (r.numero_matriz ? qlIndividual : qlTanque)
    );
  }, [qualidade, qlDe, qlAte, qlTanque, qlIndividual]);

  const qlIndicadorInfo = INDICADORES_QUALIDADE.find((i) => i.key === qlIndicador)!;
  const qlSerie = useMemo(() => {
    return qlFiltrados
      .map((r) => ({ data: r.data_coleta, total: r[qlIndicador] }))
      .filter((d): d is { data: string; total: number } => d.total != null)
      .sort((a, b) => a.data.localeCompare(b.data));
  }, [qlFiltrados, qlIndicador]);
  const qlAtual = qlSerie.length ? qlSerie[qlSerie.length - 1].total : null;
  const qlMedia = qlSerie.length ? media(qlSerie.map((d) => d.total)) : null;

  // #548 — coletas ordenadas da mais recente para a mais antiga, para a
  // tabela de bonificação estimada por lançamento (e para achar a última).
  const qlRecentes = useMemo(
    () => [...qlFiltrados].sort((a, b) => b.data_coleta.localeCompare(a.data_coleta)),
    [qlFiltrados],
  );
  const qlBonificacaoUltima = qlRecentes.find((r) => r.bonificacao_por_litro != null)?.bonificacao_por_litro ?? null;
  const pagQlRecentes = usePaginacao(qlRecentes);

  // Controle × Entregue — período próprio (default: últimos 30 dias até hoje).
  const hojeISO = new Date().toISOString().slice(0, 10);
  const inicio30DiasISO = new Date(Date.now() - 29 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const [ceIni, setCeIni] = useState(inicio30DiasISO);
  const [ceFim, setCeFim] = useState(hojeISO);
  const [ce, setCe] = useState<RelatorioControleEntrega | null>(null);
  const [ceErro, setCeErro] = useState<string | null>(null);
  useEffect(() => {
    fetchRelatorioControleEntrega(ceIni || undefined, ceFim || undefined).then(setCe).catch((e) => setCeErro(e.message));
  }, [ceIni, ceFim]);

  useEffect(() => {
    fetchControles().then((d) => setRegs(d.controles)).catch((e) => setError(e.message));
  }, []);

  const delMin = fDelMin === "" ? null : Number(fDelMin);
  const delMax = fDelMax === "" ? null : Number(fDelMax);

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((r) =>
      (fAno.length === 0 || (r.ano !== null && fAno.includes(String(r.ano)))) &&
      (fMes.length === 0 || (r.data ? fMes.includes(r.data.slice(5, 7)) : false)) &&
      (delMin === null || (r.del !== null && r.del >= delMin)) &&
      (delMax === null || (r.del !== null && r.del <= delMax)) &&
      (fOrdemParto.length === 0 || (r.ordem_parto !== null && fOrdemParto.includes(String(r.ordem_parto))))
    );
  }, [regs, fAno, fMes, delMin, delMax, fOrdemParto]);

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

  // Produção acumulada e projeção de 305 dias por lactação (animal + ordem de
  // parto). Total estimado na lactação = média diária × DEL atual; projeção de
  // 305 dias = média diária × 305 — leitura simples para o produtor.
  const lactacoes305 = useMemo(() => {
    const by = new Map<string, Ctrl[]>();
    comProd.forEach((r) => {
      const chave = `${r.numero}||${r.ordem_parto ?? "?"}`;
      (by.get(chave) ?? by.set(chave, []).get(chave)!).push(r);
    });
    return Array.from(by.entries()).map(([chave, arr]) => {
      const [numero, ordem] = chave.split("||");
      const vals = arr.map((r) => r.producao_kg!);
      const med = media(vals);
      const dels = arr.map((r) => r.del).filter((v): v is number => v != null);
      const delAtual = dels.length ? Math.max(...dels) : null;
      return {
        numero, ordem_parto: ordem === "?" ? null : Number(ordem), raca: arr[0].raca,
        media: med, del_atual: delAtual, n: arr.length,
        total_estimado: delAtual != null ? Math.round(med * delAtual) : null,
        projecao_305: Math.round(med * 305),
      };
    }).sort((a, b) => (b.projecao_305 - a.projecao_305));
  }, [comProd]);
  const ordLact305 = useOrdenacao(lactacoes305);
  const COLUNAS_305 = [
    { header: "Vaca", key: "numero" }, { header: "Ordem parto", key: "ordem_parto" }, { header: "Média/dia (kg)", key: "media" },
    { header: "DEL atual", key: "del_atual" }, { header: "Total na lactação (kg)", key: "total_estimado" }, { header: "Projeção 305d (kg)", key: "projecao_305" }, { header: "Controles", key: "n" },
  ];

  const filtradosOrdenadosBase = useMemo(() => [...filtrados].sort((a, b) => comparaNumero(a.numero, b.numero)), [filtrados]);
  const filtradosExport = useMemo(() => filtradosOrdenadosBase.map((r) => ({
    ...r, dataFmt: r.data ? new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR") : "—",
    producaoFmt: r.producao_kg != null ? r.producao_kg : "—",
  })), [filtradosOrdenadosBase]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const badgeStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", background: "var(--surface-2)", borderRadius: "999px", padding: "0.1rem 0.55rem", whiteSpace: "nowrap" };

  const animaisDisponiveis = useMemo(() => opcoes(regs ?? [], (r) => r.numero), [regs]);
  const lotesDisponiveis = useMemo(() => opcoes(regs ?? [], (r) => r.grupo_primario), [regs]);

  // Escopo do painel "Últimos controles": por animal, por lote (um selecionado) ou rebanho todo em lactação
  // (lotes cujo código de 2 dígitos é 01/02/03 — mesma convenção usada em Rebanho/Lançamentos).
  const ucNumerosEscopo = useMemo(() => {
    if (!regs) return new Set<string>();
    if (ucModo === "animal") return new Set(ucAnimal ? [ucAnimal] : []);
    if (ucModo === "lote") return new Set(ucLotes.length ? regs.filter((r) => r.grupo_primario && ucLotes.includes(r.grupo_primario)).map((r) => r.numero) : []);
    return new Set(regs.filter((r) => LOTES_LACTACAO.includes(codigoLote(r.grupo_primario) || "")).map((r) => r.numero));
  }, [regs, ucModo, ucAnimal, ucLotes]);

  // Últimos N controles por animal do escopo (ou todos), ordenados mais recente primeiro.
  const ucRegistros = useMemo(() => {
    if (!regs || !ucNumerosEscopo.size) return [];
    const porAnimal = new Map<string, Ctrl[]>();
    regs.forEach((r) => { if (ucNumerosEscopo.has(r.numero)) (porAnimal.get(r.numero) ?? porAnimal.set(r.numero, []).get(r.numero)!).push(r); });
    const linhas: Ctrl[] = [];
    porAnimal.forEach((arr) => {
      const ord = [...arr].sort((a, b) => (a.data! > b.data! ? -1 : 1));
      linhas.push(...(ucN === "todos" ? ord : ord.slice(0, ucN)));
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
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <MultiFiltro label="Ano" opcoes={opcoes(regs, (r) => r.ano === null ? null : String(r.ano))} selecionados={fAno} onChange={setFAno} />
              <MultiFiltro label="Mês" opcoes={opcoes(regs, (r) => r.data ? r.data.slice(5, 7) : null)} selecionados={fMes} onChange={setFMes} formatar={(v) => MESES_NOME[v] || v} />
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>DEL de (dias)</label>
                <input type="number" min={0} inputMode="numeric" placeholder="ex.: 30" style={selStyle} value={fDelMin} onChange={(e) => setFDelMin(e.target.value)} /></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>DEL até (dias)</label>
                <input type="number" min={0} inputMode="numeric" placeholder="ex.: 120" style={selStyle} value={fDelMax} onChange={(e) => setFDelMax(e.target.value)} /></div>
              <MultiFiltro label="Ordem de parto" opcoes={opcoes(regs, (r) => r.ordem_parto === null ? null : String(r.ordem_parto))} selecionados={fOrdemParto} onChange={setFOrdemParto} formatar={(v) => `${v}ª`} />
            </div>
            {(fAno.length > 0 || fMes.length > 0 || fDelMin || fDelMax || fOrdemParto.length > 0) && <button className="btn-ghost" title="Remover todos os filtros aplicados (ano, mês, faixa de DEL e ordem de parto)" style={{ marginTop: "0.75rem", fontSize: "0.75rem" }} onClick={() => { setFAno([]); setFMes([]); setFDelMin(""); setFDelMax(""); setFOrdemParto([]); }}>Limpar filtros</button>}
          </div>

          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Milk size={14} /> Últimos controles leiteiros</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ver</label>
                <select style={selStyle} value={String(ucN)} onChange={(e) => setUcN(e.target.value === "todos" ? "todos" : (Number(e.target.value) as 1 | 2 | 3))}>
                  <option value={1}>Último controle</option>
                  <option value={2}>2 últimos controles</option>
                  <option value={3}>3 últimos controles</option>
                  <option value="todos">Todos os controles</option>
                </select></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Por</label>
                <select style={selStyle} value={ucModo} onChange={(e) => setUcModo(e.target.value as any)}>
                  <option value="rebanho">Rebanho todo em lactação</option>
                  <option value="lote">Lote/grupo</option>
                  <option value="animal">Um animal</option>
                </select></div>
              {ucModo === "animal" && (
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
                  <AnimalPicker animais={animais.length ? animais : animaisDisponiveis.map((n) => ({ numero: n }))} value={ucAnimal} onChange={setUcAnimal} /></div>
              )}
              {ucModo === "lote" && (
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lote(s)/grupo(s)</label>
                  <LotePicker opcoes={opcoesLoteDeAnimais(animais, lotesDisponiveis)} selecionados={ucLotes} onChange={setUcLotes} /></div>
              )}
            </div>

            {ucRegistros.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-3">
                <Indicador categoria="producao" valor={`${ucMedia} kg`} cor="var(--green-light)" rotulo={`Média do ${ucLabelEscopo}`} />
                <Indicador categoria="producao" valor={`${ucMenor ?? "—"} kg`} rotulo="Menor" />
                <Indicador categoria="producao" valor={`${ucMediaManha || "—"} kg`} rotulo="Média ordenha — manhã" />
                <Indicador categoria="producao" valor={`${ucMediaNoite || "—"} kg`} rotulo="Média ordenha — noite" />
                <Indicador categoria="producao" valor={ucNumerosEscopo.size} rotulo="Vacas no filtro" />
                <Indicador categoria="producao" valor={ucRegistros.length} rotulo="Controles no filtro" />
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
                  {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
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
                      {admin && <td>{r.usuario_nome ?? "—"}</td>}
                    </tr>
                  ))}
                  {!ucRegistros.length && (
                    <tr><td colSpan={admin ? 7 : 6} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>
                      {ucModo === "animal" && !ucAnimal ? "Selecione um animal." : ucModo === "lote" && !ucLotes.length ? "Selecione um ou mais lotes." : "Nenhum controle encontrado."}
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <SecaoRecolhivel
            titulo="Qualidade do leite"
            icon={FlaskConical}
            badge={qualidade ? <span style={badgeStyle}>{qlFiltrados.length} coletas</span> : null}
            descricao="Indicadores das coletas de qualidade (CCS, CBT, gordura, proteína, sólidos, ESD, lactose) com série histórica por período.">
            {qualidadeErro ? (
              <div className="alert-critico"><AlertTriangle size={16} /><span>Não foi possível carregar a qualidade do leite: {qualidadeErro}.</span></div>
            ) : !qualidade ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                  <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Período — de</label>
                    <input type="date" style={selStyle} value={qlDe} onChange={(e) => setQlDe(e.target.value)} /></div>
                  <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>até</label>
                    <input type="date" style={selStyle} value={qlAte} onChange={(e) => setQlAte(e.target.value)} /></div>
                  <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Indicador</label>
                    <select style={selStyle} value={qlIndicador} onChange={(e) => setQlIndicador(e.target.value as any)}>
                      {INDICADORES_QUALIDADE.map((i) => <option key={i.key} value={i.key}>{i.label}</option>)}
                    </select></div>
                  <div>
                    <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Mostrar</label>
                    <div className="flex items-center gap-3" style={{ marginTop: "0.4rem" }}>
                      <label className="flex items-center gap-2" style={{ fontSize: "0.8rem" }} title="Amostras do tanque (rebanho todo, sem número de matriz)">
                        <input type="checkbox" checked={qlTanque} onChange={(e) => setQlTanque(e.target.checked)} /> Relatório do tanque
                      </label>
                      <label className="flex items-center gap-2" style={{ fontSize: "0.8rem" }} title="Amostras de uma vaca específica (ex.: investigação de mastite)">
                        <input type="checkbox" checked={qlIndividual} onChange={(e) => setQlIndividual(e.target.checked)} /> Relatório por animal
                      </label>
                    </div>
                  </div>
                </div>
                {!qlTanque && !qlIndividual && (
                  <p style={{ color: "var(--amber)", fontSize: "0.8rem", marginBottom: "0.75rem" }}>Selecione ao menos um dos dois relatórios acima.</p>
                )}
                <div className="grid grid-cols-2 gap-4 mb-3">
                  <Indicador categoria="producao" valor={`${qlAtual ?? "—"} ${qlAtual != null ? qlIndicadorInfo.unidade : ""}`} cor="var(--green-light)" rotulo={`${qlIndicadorInfo.label} atual (última coleta)`} />
                  <Indicador categoria="producao" valor={`${qlMedia ?? "—"} ${qlMedia != null ? qlIndicadorInfo.unidade : ""}`} rotulo={`${qlIndicadorInfo.label} média no período`} />
                </div>
                {qlSerie.length ? <LineChart dados={qlSerie} /> : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem coletas de qualidade do leite no filtro.</p>}

                {/* #548 — bonificação/penalização estimada por qualidade, contra as
                    faixas de CCS/CBT/gordura/proteína cadastradas em Configurações >
                    Parâmetros (cada laticínio tem a sua própria tabela). */}
                <div className="mt-4">
                  <h4 style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                    Bonificação/penalização estimada por qualidade
                  </h4>
                  {!qlTemFaixasBonificacao ? (
                    <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
                      Nenhuma faixa de bonificação cadastrada — configure em <strong>Configurações &gt; Parâmetros</strong> as
                      faixas de CCS, CBT, gordura e proteína do seu laticínio para ver aqui o valor estimado por litro.
                    </p>
                  ) : (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                        <Indicador
                          categoria="producao"
                          valor={qlBonificacaoUltima != null ? formatarReaisPorLitro(qlBonificacaoUltima) : "—"}
                          cor={qlBonificacaoUltima != null && qlBonificacaoUltima < 0 ? "var(--red)" : "var(--green-light)"}
                          rotulo="Ajuste estimado (última coleta com faixa aplicável)"
                        />
                      </div>
                      <div className="overflow-x-auto">
                        <table className="fazenda-table">
                          <thead>
                            <tr>
                              <th>Data</th><th>Tipo</th><th>CCS</th><th>CBT</th><th>Gordura %</th><th>Proteína %</th>
                              <th>Ajuste estimado</th>
                            </tr>
                          </thead>
                          <tbody>
                            {pagQlRecentes.linhasPagina.map((r) => (
                              <tr key={r.id}>
                                <td style={{ fontSize: "0.78rem" }}>{new Date(r.data_coleta + "T00:00:00").toLocaleDateString("pt-BR")}</td>
                                <td style={{ fontSize: "0.78rem" }}>{r.numero_matriz ? `Vaca ${r.numero_matriz}` : "Tanque"}</td>
                                <td style={{ textAlign: "right" }}>{r.ccs ?? "—"}</td>
                                <td style={{ textAlign: "right" }}>{r.cbt ?? "—"}</td>
                                <td style={{ textAlign: "right" }}>{r.gordura_pct ?? "—"}</td>
                                <td style={{ textAlign: "right" }}>{r.proteina_pct ?? "—"}</td>
                                <td style={{
                                  textAlign: "right", fontWeight: 600,
                                  color: r.bonificacao_por_litro != null && r.bonificacao_por_litro < 0 ? "var(--red)" : undefined,
                                }}>
                                  {r.bonificacao_por_litro != null ? formatarReaisPorLitro(r.bonificacao_por_litro) : "—"}
                                </td>
                              </tr>
                            ))}
                            {!qlRecentes.length && (
                              <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>
                                Sem coletas no filtro.
                              </td></tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                      <Paginacao pagina={pagQlRecentes.pagina} totalPaginas={pagQlRecentes.totalPaginas} totalLinhas={pagQlRecentes.totalLinhas}
                        tamanhoPagina={pagQlRecentes.tamanhoPagina} onMudarPagina={pagQlRecentes.setPagina} onMudarTamanho={pagQlRecentes.setTamanhoPagina} />
                    </>
                  )}
                </div>
              </>
            )}
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Controle leiteiro × Entregue"
            icon={Scale}
            badge={ce ? <span style={badgeStyle}>{ce.dias_periodo} dias</span> : null}
            descricao="Fecha, no período, o leite do controle contra o entregue ao laticínio — separando bezerros e equipe/família (só quilos).">
            {ceErro ? (
              <div className="alert-critico"><AlertTriangle size={16} /><span>Não foi possível carregar: {ceErro}.</span></div>
            ) : !ce ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
            ) : (
            <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Período — de</label>
                <input type="date" style={selStyle} value={ceIni} onChange={(e) => setCeIni(e.target.value)} /></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Período — até</label>
                <input type="date" style={selStyle} value={ceFim} onChange={(e) => setCeFim(e.target.value)} /></div>
            </div>

            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem", lineHeight: 1.5 }}>
              Tudo em <strong>quilos de leite</strong>, projetado para o período filtrado ({ce.dias_periodo} dias).
              O <strong>Controle projetado</strong> é a média diária do rebanho ({ce.media_diaria_controle_kg ?? "—"} kg/dia,
              de {ce.dias_com_controle} dia(s) pesado(s)) multiplicada pelos dias do período. O <strong>Entregue</strong> vem
              do lançamento mensal do laticínio, rateado por dia do mês (28–31 conforme o mês) e projetado para o período; a
              <strong> Receita média</strong> segue o mesmo rateio. O <strong>não entregue</strong> (Controle − Entregue) é
              dividido entre <strong>Bezerros</strong> (leite/dia da dieta lançada × dias) e <strong>Equipe/família</strong>
              (o que sobra). O <strong>Desvio padrão %</strong> mede a variação diária do controle no período — até 5% indica
              que a média projeta bem; acima disso, a projeção fica menos confiável.
            </p>

            {ce.desvio_padrao_pct != null && ce.desvio_padrao_pct > 5 && (
              <p style={{ fontSize: "0.76rem", color: "var(--amber)", marginBottom: "0.5rem" }}>
                Produção diária oscilou {ce.desvio_padrao_pct}% no período (acima dos 5%) — a projeção do controle é menos confiável.
              </p>
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <Indicador categoria="producao" valor={ce.controle_projetado_kg != null ? `${ce.controle_projetado_kg.toLocaleString("pt-BR")} kg` : "—"} rotulo="Controle projetado" />
              <Indicador categoria="producao" valor={ce.entrega_projetada_kg != null ? `${ce.entrega_projetada_kg.toLocaleString("pt-BR")} kg` : "—"} rotulo="Entregue projetado" />
              <Indicador categoria="producao" valor={ce.nao_entregue_kg != null ? `${ce.nao_entregue_kg.toLocaleString("pt-BR")} kg` : "—"} cor="var(--dourado-light)" rotulo="Não entregue" />
              <Indicador categoria="producao" valor={ce.receita_projetada != null ? ce.receita_projetada.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) : "—"} rotulo={`Receita média${ce.preco_medio_kg != null ? ` (${ce.preco_medio_kg.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}/kg)` : ""}`} />
            </div>

            <div className="overflow-x-auto">
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <th>Item</th><th style={{ textAlign: "right" }}>Quilos (período)</th><th>Como é calculado</th>
                </tr></thead>
                <tbody>
                  <tr><td style={{ fontWeight: 700 }}>Controle projetado</td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{ce.controle_projetado_kg != null ? ce.controle_projetado_kg.toLocaleString("pt-BR") : "—"}</td>
                    <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>média diária {ce.media_diaria_controle_kg ?? "—"} kg × {ce.dias_periodo} dias</td></tr>
                  <tr><td>Entregue projetado</td>
                    <td style={{ textAlign: "right" }}>{ce.entrega_projetada_kg != null ? ce.entrega_projetada_kg.toLocaleString("pt-BR") : "—"}</td>
                    <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>entrega mensal ÷ dias do mês × dias do período</td></tr>
                  <tr><td style={{ fontWeight: 700 }}>Não entregue</td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{ce.nao_entregue_kg != null ? ce.nao_entregue_kg.toLocaleString("pt-BR") : "—"}</td>
                    <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>Controle − Entregue</td></tr>
                  <tr><td>↳ Bezerros</td>
                    <td style={{ textAlign: "right" }}>{ce.bezerros_kg.toLocaleString("pt-BR")}</td>
                    <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{ce.leite_bezerros_kg_dia} kg/dia (dieta {ce.bezerros_fonte === "dieta_lancada" ? "lançada" : "CSV"}) × {ce.dias_periodo} dias</td></tr>
                  <tr><td>↳ Equipe/família</td>
                    <td style={{ textAlign: "right", color: ce.equipe_kg != null && ce.equipe_kg < 0 ? "var(--red)" : undefined }}>{ce.equipe_kg != null ? ce.equipe_kg.toLocaleString("pt-BR") : "—"}</td>
                    <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>Não entregue − Bezerros (residual)</td></tr>
                  <tr><td style={{ fontWeight: 700 }}>Desvio padrão %</td>
                    <td style={{ textAlign: "right", fontWeight: 700, color: ce.desvio_padrao_pct == null ? "var(--text-muted)" : ce.desvio_padrao_pct <= 5 ? "var(--green-light)" : "var(--amber)" }}>{ce.desvio_padrao_pct != null ? `${ce.desvio_padrao_pct}%` : "—"}</td>
                    <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>variação diária do controle (tolerância 5%)</td></tr>
                </tbody>
              </table>
            </div>
            {ce.equipe_kg != null && ce.equipe_kg < 0 && (
              <p style={{ fontSize: "0.76rem", color: "var(--red)", marginTop: "0.5rem" }}>
                Equipe/família ficou negativo — o leite lançado para bezerros na dieta é maior que o não entregue. Revise a
                dieta dos bezerros ou os lançamentos de controle/entrega do período.
              </p>
            )}
            </>
            )}
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Curva de Lactação e evolução do rebanho"
            icon={TrendingUp}
            badge={<span style={badgeStyle}>{curva.length} faixas · {serie.length} controles</span>}
            descricao="Produção média por faixa de DEL (curva de lactação) e a evolução da produção total do rebanho controle a controle.">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Ranking de Produção (top 20 por média)"
            badge={<span style={badgeStyle}>{ranking.length} vacas</span>}
            descricao="Vacas ordenadas por produção média no filtro, com pico, última pesagem e número de pesagens.">
            <div className="flex items-center justify-end mb-3">
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
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Produção na lactação e projeção de 305 dias"
            icon={TrendingUp}
            badge={<span style={badgeStyle}>{lactacoes305.length} lactações</span>}
            descricao="Por lactação (vaca + ordem de parto), a média diária, o total acumulado estimado e a projeção de produção em 305 dias. Use o filtro de ordem de parto acima para comparar 1ª, 2ª, 3ª lactação.">
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              Total na lactação = média diária × DEL atual · Projeção 305 dias = média diária × 305. Estimativas a partir
              das pesagens do controle leiteiro dentro do filtro selecionado.
            </p>
            <div className="flex items-center justify-end mb-3">
              <ExportarBotoes titulo="Produção na lactação e projeção 305 dias" nomeArquivoBase="producao_305dias" colunas={COLUNAS_305} linhas={lactacoes305} />
            </div>
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <ThOrdenavel label="Vaca" campo="numero" coluna={ordLact305.coluna} dir={ordLact305.dir} ordenar={ordLact305.ordenar} />
                  <ThOrdenavel label="Ordem parto" campo="ordem_parto" coluna={ordLact305.coluna} dir={ordLact305.dir} ordenar={ordLact305.ordenar} />
                  <ThOrdenavel label="Média/dia (kg)" campo="media" coluna={ordLact305.coluna} dir={ordLact305.dir} ordenar={ordLact305.ordenar} alinhar="right" />
                  <ThOrdenavel label="DEL atual" campo="del_atual" coluna={ordLact305.coluna} dir={ordLact305.dir} ordenar={ordLact305.ordenar} alinhar="right" />
                  <ThOrdenavel label="Total na lactação (kg)" campo="total_estimado" coluna={ordLact305.coluna} dir={ordLact305.dir} ordenar={ordLact305.ordenar} alinhar="right" />
                  <ThOrdenavel label="Projeção 305d (kg)" campo="projecao_305" coluna={ordLact305.coluna} dir={ordLact305.dir} ordenar={ordLact305.ordenar} alinhar="right" />
                  <ThOrdenavel label="Controles" campo="n" coluna={ordLact305.coluna} dir={ordLact305.dir} ordenar={ordLact305.ordenar} alinhar="right" />
                </tr></thead>
                <tbody>
                  {ordLact305.linhasOrdenadas.map((l, i) => (
                    <tr key={`${l.numero}-${l.ordem_parto}-${i}`}>
                      <td style={{ fontWeight: 700 }}>{l.numero}</td>
                      <td>{l.ordem_parto != null ? `${l.ordem_parto}ª` : "—"}</td>
                      <td style={{ textAlign: "right", color: "var(--green-light)", fontWeight: 600 }}>{l.media}</td>
                      <td style={{ textAlign: "right" }}>{l.del_atual ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{l.total_estimado != null ? l.total_estimado.toLocaleString("pt-BR") : "—"}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>{l.projecao_305.toLocaleString("pt-BR")}</td>
                      <td style={{ textAlign: "right", color: "var(--text-muted)" }}>{l.n}</td>
                    </tr>
                  ))}
                  {!lactacoes305.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma lactação no filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Registros filtrados"
            badge={<span style={badgeStyle}>{filtrados.length} registros</span>}
            descricao="Lista completa dos controles leiteiros que atendem aos filtros de ano, mês e faixa de DEL selecionados acima.">
            <div className="flex items-center justify-end mb-3">
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
                  {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
                </tr></thead>
                <tbody>
                  {ordFiltrados.linhasOrdenadas.map((r, i) => (
                    <tr key={`${r.numero}-${r.data}-${i}`}>
                      <td style={{ fontWeight: 700 }}>{r.numero}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{r.raca}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.data ? new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td>{r.del ?? "—"}</td>
                      <td>{r.producao_kg != null ? `${r.producao_kg} kg` : "—"}</td>
                      {admin && <td style={{ fontSize: "0.78rem" }}>{r.usuario_nome ?? "—"}</td>}
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td colSpan={admin ? 6 : 5} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum registro no filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>
        </>
      )}
    </div>
  );
}

type AplicacaoBst = {
  numero_matriz: string; data_aplicacao: string | null; produto: string; dose: number | null;
  unidade: string | null; responsavel: string | null; lote: string | null; categoria: string | null;
};

function RelatoriosBstView() {
  const [historico, setHistorico] = useState<AplicacaoBst[] | null>(null);
  const [agenda, setAgenda] = useState<any | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [fLote, setFLote] = useState<string[]>([]);
  const [fAnimal, setFAnimal] = useState("");
  const [fDe, setFDe] = useState("");
  const [fAte, setFAte] = useState("");

  const carregar = () => {
    fetchRelatorioBst().then((d) => setHistorico(d.aplicacoes)).catch((e) => setErro(e.message));
    fetchAgenda().then(setAgenda).catch(() => setAgenda(null));
  };
  useEffect(() => { carregar(); }, []);

  const opcoesLote = useMemo(
    () => Array.from(new Set((historico ?? []).map((r) => r.lote).filter(Boolean))).sort() as string[],
    [historico]
  );

  const filtrado = useMemo(() => (historico ?? []).filter((r) => {
    if (fLote.length && !(r.lote && fLote.includes(r.lote))) return false;
    if (fAnimal && !r.numero_matriz.toLowerCase().includes(fAnimal.toLowerCase())) return false;
    if (fDe && (!r.data_aplicacao || r.data_aplicacao < fDe)) return false;
    if (fAte && (!r.data_aplicacao || r.data_aplicacao > fAte)) return false;
    return true;
  }), [historico, fLote, fAnimal, fDe, fAte]);

  const vacasDistintas = useMemo(() => new Set(filtrado.map((r) => r.numero_matriz)).size, [filtrado]);
  const nuncaAplicadas: any[] = agenda?.bst_nunca_aplicados ?? [];

  const th: React.CSSProperties = { textAlign: "left", padding: "0.4rem 0.6rem", fontSize: "0.72rem", textTransform: "uppercase", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" };
  const td: React.CSSProperties = { padding: "0.4rem 0.6rem", fontSize: "0.82rem", borderBottom: "1px solid var(--border)" };

  if (erro) return <p style={{ color: "var(--red)" }}>{erro}</p>;

  return (
    <div className="px-6 pt-6 space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card"><div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Próxima aplicação BST</div><div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{agenda?.proxima_visita_bst ? new Date(agenda.proxima_visita_bst + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</div></div>
        <div className="card"><div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Aplicações no filtro</div><div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{filtrado.length}</div></div>
        <div className="card"><div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Vacas distintas aplicadas</div><div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{vacasDistintas}</div></div>
        <div className="card"><div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Incluir no próximo BST</div><div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--amber)" }}>{nuncaAplicadas.length}</div></div>
      </div>

      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
        Situação atual das candidatas (leitura). Para lançar uma aplicação, agendar ou marcar animal como inapto, use{" "}
        <strong>Lançamentos › Produção › BST</strong>.
      </p>
      <TabelasStatusBst agenda={agenda} />

      <div className="card">
        <div className="card-header mb-2 flex items-center gap-2"><Filter size={14} /> Filtrar histórico</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Nº do animal</label>
            <input value={fAnimal} onChange={(e) => setFAnimal(e.target.value)} placeholder="Buscar…" style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }} /></div>
          <MultiFiltro label="Lote" opcoes={opcoesLote} selecionados={fLote} onChange={setFLote} />
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
            <input type="date" value={fDe} onChange={(e) => setFDe(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
            <input type="date" value={fAte} onChange={(e) => setFAte(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }} /></div>
        </div>
      </div>

      <div className="card">
        <div className="card-header mb-2 flex items-center gap-2"><Syringe size={14} /> Histórico de aplicações ({filtrado.length})</div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr><th style={th}>Data</th><th style={th}>Nº</th><th style={th}>Lote</th><th style={th}>Categoria</th><th style={th}>Produto</th><th style={{ ...th, textAlign: "right" }}>Dose</th><th style={th}>Responsável</th></tr></thead>
            <tbody>
              {filtrado.map((r, i) => (
                <tr key={`${r.numero_matriz}-${r.data_aplicacao}-${i}`}>
                  <td style={td}>{r.data_aplicacao ? new Date(r.data_aplicacao + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                  <td style={{ ...td, fontWeight: 700 }}>{r.numero_matriz}</td>
                  <td style={td}>{r.lote || "—"}</td>
                  <td style={td}>{r.categoria || "—"}</td>
                  <td style={td}>{r.produto}</td>
                  <td style={{ ...td, textAlign: "right" }}>{r.dose != null ? `${r.dose} ${r.unidade || ""}` : "—"}</td>
                  <td style={td}>{r.responsavel || "—"}</td>
                </tr>
              ))}
              {!filtrado.length && <tr><td colSpan={7} style={{ ...td, textAlign: "center", color: "var(--text-muted)" }}>Nenhuma aplicação no filtro.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

type AbaProducao = "leiteira" | "bst";
const ABAS_PRODUCAO = [
  { id: "leiteira" as const, label: "Produção leiteira", icon: Milk, title: "Série histórica, curva de lactação e ranking por vaca" },
  { id: "bst" as const, label: "Relatórios de BST", icon: Droplets, title: "Dados gerenciais e filtros de aplicação de BST (somatotropina bovina)" },
];

export default function ProducaoPage() {
  const [aba, setAba] = useState<AbaProducao>("leiteira");
  const subNavTree: SubNavNode[] = useMemo(() => ABAS_PRODUCAO.map((a) => ({ id: a.id, label: a.label, icon: a.icon })), []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: aba, onSelect: (id: string) => setAba(id as AbaProducao) }), [subNavTree, aba]));

  return aba === "bst" ? <RelatoriosBstView /> : <ProducaoLeiteira />;
}
