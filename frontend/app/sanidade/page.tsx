"use client";
import { useEffect, useMemo, useState } from "react";
import { Syringe, AlertTriangle, Filter, Search, CalendarClock, ClipboardList } from "lucide-react";
import { fetchSanidade, fetchCalendarioSanitario, fetchEventosSanitarios, formatDate } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";

const COLUNAS_SANIDADE = [
  { header: "Data", key: "data" }, { header: "Animal", key: "numero" }, { header: "Produto", key: "produto" },
  { header: "Categoria", key: "categoria" }, { header: "Dose", key: "dose" }, { header: "Atividade", key: "atividade" },
];

const COLUNAS_CALENDARIO = [
  { header: "Evento", key: "evento_sanitario_nome" }, { header: "Categoria alvo", key: "categoria_alvo" },
  { header: "Doença", key: "doenca_nome" }, { header: "Produto", key: "produto" }, { header: "Dosagem", key: "dosagem" },
  { header: "Frequência", key: "frequenciaFmt" }, { header: "Próxima ocorrência", key: "proxima_ocorrencia_fmt" },
];

type RegraCalendario = {
  id: number; evento_sanitario_id: number; evento_sanitario_nome: string; categoria_alvo: string | null;
  doenca_nome: string | null; produto: string | null; principio_ativo_nome: string | null; dosagem: string | null;
  frequencia_valor: number; frequencia_unidade: string; data_evento: string; proxima_ocorrencia: string; observacao: string | null;
};

const LABEL_FREQ: Record<string, string> = { dias: "dia(s)", meses: "mês(es)", anos: "ano(s)" };

function CalendarioSanitarioView() {
  const [regras, setRegras] = useState<RegraCalendario[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [eventos, setEventos] = useState<{ id: number; nome: string }[]>([]);
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [eventoId, setEventoId] = useState("");

  useEffect(() => { fetchEventosSanitarios().then(setEventos).catch(() => {}); }, []);
  useEffect(() => {
    fetchCalendarioSanitario({ dataInicio: ini || undefined, dataFim: fim || undefined, eventoSanitarioId: eventoId ? Number(eventoId) : undefined })
      .then(setRegras).catch((e) => setError(e.message));
  }, [ini, fim, eventoId]);

  const linhasExport = (regras || []).map((r) => ({
    ...r, frequenciaFmt: `a cada ${r.frequencia_valor} ${LABEL_FREQ[r.frequencia_unidade]}`,
    proxima_ocorrencia_fmt: formatDate(r.proxima_ocorrencia),
  }));

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Próxima ocorrência — de</label>
            <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Próxima ocorrência — até</label>
            <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Evento sanitário</label>
            <select style={selStyle} value={eventoId} onChange={(e) => setEventoId(e.target.value)}>
              <option value="">Todos</option>{eventos.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
            </select></div>
        </div>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!regras && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regras && (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span>Regras do calendário sanitário ({regras.length})</span>
            <ExportarBotoes titulo="Calendário sanitário" nomeArquivoBase="calendario_sanitario" colunas={COLUNAS_CALENDARIO} linhas={linhasExport} />
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "480px" }}>
            <table className="fazenda-table">
              <thead><tr><th>Evento</th><th>Categoria alvo</th><th>Doença</th><th>Produto</th><th>Dosagem</th><th>Frequência</th><th>Próxima ocorrência</th></tr></thead>
              <tbody>
                {regras.map((r) => (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 700 }}>{r.evento_sanitario_nome}</td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.categoria_alvo || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.doenca_nome || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.produto || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.dosagem || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>a cada {r.frequencia_valor} {LABEL_FREQ[r.frequencia_unidade]}</td>
                    <td style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--dourado-light)" }}>{formatDate(r.proxima_ocorrencia)}</td>
                  </tr>
                ))}
                {!regras.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma regra no filtro.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

type Aplic = {
  numero: string; raca: string; produto: string; categoria: string;
  dose: number | null; atividade: string | null; obs: string | null;
  data: string | null; ano: number | null; mes: string | null;
};

const CORES = ["var(--vinho-light, #8B3A56)", "var(--dourado)", "var(--blue)", "var(--amber)", "var(--green-light)", "var(--red)", "#7A5C99", "#4C9AA8"];

function AplicacoesView() {
  const [regs, setRegs] = useState<Aplic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fCat, setFCat] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [buscaProd, setBuscaProd] = useState("");
  const [buscaAnimal, setBuscaAnimal] = useState("");

  useEffect(() => { fetchSanidade().then((d) => setRegs(d.aplicacoes)).catch((e) => setError(e.message)); }, []);

  const opc = (f: (a: Aplic) => string | null) => {
    const s = new Set<string>(); (regs ?? []).forEach((a) => { const v = f(a); if (v) s.add(v); });
    return Array.from(s).sort();
  };

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((a) =>
      (!fCat || a.categoria === fCat) &&
      (!ini || (a.data ? a.data >= ini : false)) &&
      (!fim || (a.data ? a.data <= fim : false)) &&
      (!buscaProd || a.produto.toLowerCase().includes(buscaProd.toLowerCase())) &&
      (!buscaAnimal || a.numero.toLowerCase().includes(buscaAnimal.toLowerCase()))
    );
  }, [regs, fCat, ini, fim, buscaProd, buscaAnimal]);

  const porCategoria = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => by.set(a.categoria, (by.get(a.categoria) ?? 0) + 1));
    return Array.from(by.entries()).map(([cat, n]) => ({ cat, n })).sort((a, b) => b.n - a.n);
  }, [filtrados]);

  const porMes = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => { if (a.mes) by.set(a.mes, (by.get(a.mes) ?? 0) + 1); });
    return Array.from(by.keys()).sort().map((mes) => ({ mes, n: by.get(mes)! }));
  }, [filtrados]);

  const topProdutos = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => by.set(a.produto, (by.get(a.produto) ?? 0) + 1));
    return Array.from(by.entries()).map(([produto, n]) => ({ produto, n })).sort((a, b) => b.n - a.n).slice(0, 10);
  }, [filtrados]);

  const animaisTratados = new Set(filtrados.map((a) => a.numero)).size;
  const produtos = new Set(filtrados.map((a) => a.produto)).size;
  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text)", fontSize: "0.8rem" };

  return (
    <>
      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o SANIDADE.csv</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && <>
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria</label>
              <select style={selStyle} value={fCat} onChange={(e) => setFCat(e.target.value)}><option value="">Todas</option>{opc((a) => a.categoria).map((o) => <option key={o}>{o}</option>)}</select></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
              <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
              <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Produto</label>
              <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={buscaProd} onChange={(e) => setBuscaProd(e.target.value)} placeholder="ex.: Ivermectina" /></div></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
              <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={buscaAnimal} onChange={(e) => setBuscaAnimal(e.target.value)} placeholder="ex.: 068" /></div></div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="kpi-card"><p className="kpi-value">{filtrados.length}</p><p className="kpi-label">Aplicações</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{animaisTratados}</p><p className="kpi-label">Animais tratados</p></div>
          <div className="kpi-card"><p className="kpi-value">{produtos}</p><p className="kpi-label">Produtos distintos</p></div>
          <div className="kpi-card"><p className="kpi-value">{porCategoria.length}</p><p className="kpi-label">Categorias</p></div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div className="card">
            <div className="card-header mb-3">Aplicações por Categoria <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>(clique para filtrar)</span></div>
            <ResponsiveContainer width="100%" height={Math.max(180, porCategoria.length * 34)}>
              <BarChart data={porCategoria} layout="vertical" margin={{ left: 8 }}>
                <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 10 }} allowDecimals={false} />
                <YAxis type="category" dataKey="cat" tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={130} />
                <Tooltip contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="n" name="Aplicações" radius={[0, 3, 3, 0]} style={{ cursor: "pointer" }} onClick={(e: any) => e?.cat && setFCat((c) => c === e.cat ? "" : e.cat)}>
                  {porCategoria.map((_, i) => <Cell key={i} fill={CORES[i % CORES.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="card">
            <div className="card-header mb-3">Aplicações por Mês</div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={porMes}>
                <XAxis dataKey="mes" tick={{ fill: "var(--text-muted)", fontSize: 9 }} tickFormatter={(m) => m.slice(2)} />
                <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} allowDecimals={false} width={30} />
                <Tooltip contentStyle={tip} />
                <Line type="monotone" dataKey="n" name="Aplicações" stroke="var(--dourado-light)" strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card">
            <div className="card-header mb-3">Top Produtos</div>
            <table className="fazenda-table">
              <thead><tr><th>Produto</th><th style={{ textAlign: "right" }}>Aplic.</th></tr></thead>
              <tbody>{topProdutos.map((p) => <tr key={p.produto}><td style={{ fontSize: "0.8rem" }}>{p.produto}</td><td style={{ textAlign: "right", fontWeight: 700 }}>{p.n}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="card">
            <div className="card-header mb-3 flex items-center justify-between">
              <span>Aplicações</span>
              <div className="flex items-center gap-3">
                <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span>
                <ExportarBotoes titulo="Sanidade — Aplicações" nomeArquivoBase="sanidade" colunas={COLUNAS_SANIDADE} linhas={filtrados} />
              </div>
            </div>
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table">
                <thead><tr><th>Data</th><th>Animal</th><th>Produto</th><th>Categoria</th><th style={{ textAlign: "right" }}>Dose</th></tr></thead>
                <tbody>
                  {filtrados.slice(0, 300).map((a, i) => (
                    <tr key={i}>
                      <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{a.data ? new Date(a.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td style={{ fontWeight: 700 }}>{a.numero}</td>
                      <td style={{ fontSize: "0.75rem" }}>{a.produto}</td>
                      <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{a.categoria}</td>
                      <td style={{ textAlign: "right" }}>{a.dose ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtrados.length > 300 && <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>Mostrando 300 de {filtrados.length} — refine os filtros.</p>}
            </div>
          </div>
        </div>
      </>}
    </>
  );
}

const ABAS_SANIDADE = [
  ["aplicacoes", "Aplicações", ClipboardList],
  ["calendario", "Calendário sanitário", CalendarClock],
] as const;

export default function SanidadePage() {
  const [aba, setAba] = useState<(typeof ABAS_SANIDADE)[number][0]>("aplicacoes");

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Syringe size={22} style={{ color: "var(--dourado)" }} /> Sanidade</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Medicamentos aplicados e calendário sanitário — filtre por categoria, data, produto, animal ou evento.</p>
      </div>

      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        {ABAS_SANIDADE.map(([id, label, Icon]) => (
          <button key={id} onClick={() => setAba(id)}
            style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
              border: "1px solid " + (aba === id ? "var(--dourado)" : "var(--border)"),
              background: aba === id ? "rgba(94,26,46,0.4)" : "transparent",
              color: aba === id ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: aba === id ? 700 : 500 }}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {aba === "aplicacoes" && <AplicacoesView />}
      {aba === "calendario" && <CalendarioSanitarioView />}
    </div>
  );
}
