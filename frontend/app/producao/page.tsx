"use client";
import { useEffect, useMemo, useState } from "react";
import { Milk, AlertTriangle, Filter, TrendingUp } from "lucide-react";
import { fetchControles } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";

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

  const filtradosExport = useMemo(() => filtrados.map((r) => ({
    ...r, dataFmt: r.data ? new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR") : "—",
    producaoFmt: r.producao_kg != null ? r.producao_kg : "—",
  })), [filtrados]);

  const ultimaData = serie.length ? serie[serie.length - 1] : null;
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

  // Média do lote/rebanho: produção do controle mais recente de cada animal do escopo (não a média dos N).
  const ucMediaAtual = useMemo(() => {
    const porAnimal = new Map<string, Ctrl>();
    ucRegistros.forEach((r) => {
      const atual = porAnimal.get(r.numero);
      if (!atual || (r.data && atual.data && r.data > atual.data)) porAnimal.set(r.numero, r);
    });
    return media(Array.from(porAnimal.values()).map((r) => r.producao_kg || 0));
  }, [ucRegistros]);

  const ucMediaManha = useMemo(() => media(ucRegistros.filter((r) => r.ordenha1_kg != null).map((r) => r.ordenha1_kg!)), [ucRegistros]);
  const ucMediaNoite = useMemo(() => {
    // "Noite" = última ordenha do dia lançada — ordenha3 quando há 3, senão ordenha2.
    const valores = ucRegistros.map((r) => (r.ordenha3_kg ?? r.ordenha2_kg)).filter((v): v is number => v != null);
    return media(valores);
  }, [ucRegistros]);

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
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-3">
                {ucModo !== "animal" && (
                  <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{ucMediaAtual} kg</p>
                    <p className="kpi-label">Média do {ucModo === "lote" ? "lote" : "rebanho"} (controle mais recente)</p></div>
                )}
                <div className="kpi-card"><p className="kpi-value">{ucMediaManha || "—"} kg</p><p className="kpi-label">Média por ordenha — manhã</p></div>
                <div className="kpi-card"><p className="kpi-value">{ucMediaNoite || "—"} kg</p><p className="kpi-label">Média por ordenha — noite</p></div>
              </div>
            )}

            <div className="overflow-x-auto" style={{ maxHeight: "360px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th>Vaca</th><th>Lote</th><th>Data</th><th style={{ textAlign: "right" }}>Manhã (kg)</th><th style={{ textAlign: "right" }}>Noite (kg)</th><th style={{ textAlign: "right" }}>Total (kg)</th></tr></thead>
                <tbody>
                  {ucRegistros.map((r, i) => (
                    <tr key={`${r.numero}-${r.data}-${i}`}>
                      <td style={{ fontWeight: 700 }}>{r.numero}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.grupo_primario || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.data ? new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td style={{ textAlign: "right" }}>{r.ordenha1_kg ?? "—"}</td>
                      <td style={{ textAlign: "right" }}>{r.ordenha3_kg ?? r.ordenha2_kg ?? "—"}</td>
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

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{ultimaData ? media(comProd.filter((r) => r.data === ultimaData.data).map((r) => r.producao_kg!)) : "—"} kg</p><p className="kpi-label">Média/vaca (último controle)</p></div>
            <div className="kpi-card"><p className="kpi-value">{new Set(comProd.map((r) => r.numero)).size}</p><p className="kpi-label">Vacas</p></div>
            <div className="kpi-card"><p className="kpi-value">{comProd.length}</p><p className="kpi-label">Pesagens</p></div>
            <div className="kpi-card"><p className="kpi-value" style={{ fontSize: "1.1rem" }}>{ultimaData?.data ?? "—"}</p><p className="kpi-label">Último controle</p></div>
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
              <thead><tr><th>Vaca</th><th>Raça</th><th>Média</th><th>Pico</th><th>Última</th><th>Pesagens</th></tr></thead>
              <tbody>
                {ranking.slice(0, 20).map((v) => (
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
                <thead><tr><th>Vaca</th><th>Raça</th><th>Data</th><th>DEL (dias)</th><th>Produção (kg)</th></tr></thead>
                <tbody>
                  {filtrados.map((r, i) => (
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
