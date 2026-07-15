"use client";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Syringe, AlertTriangle, Filter, Search, CalendarClock, ClipboardList, Pencil, Trash2, Check, X, Shield, HeartPulse, Activity, ChevronDown, ChevronRight, ListChecks } from "lucide-react";
import { fetchSanidade, fetchCalendarioSanitario, fetchEventosSanitarios, fetchLancamentosProtocolo, editarAplicacaoSanidade, excluirAplicacaoSanidade, excluirCalendarioSanitario, ehAdmin, formatDate } from "@/lib/api";
import { RESPONSAVEIS, VIAS_APLICACAO } from "@/lib/constants";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { MultiFiltro } from "@/components/ui";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";

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
const LABEL_CAT_PREV: Record<string, string> = { vacina: "Vacina", exame: "Exame", tratamento: "Tratamento" };

type EventoPrev = {
  id: number; nome: string; categoria_preventiva: string | null; doenca_nome: string | null;
  produto_padrao: string | null; dose_padrao: number | null; unidade_padrao: string | null;
};


// Exame → serviço financeiro correspondente (para o botão "Lançar financeiro").
function servicoDoExame(nome: string): string {
  const n = (nome || "").toLowerCase();
  if (n.includes("tubercul")) return "Exame de tuberculose";
  if (n.includes("brucel")) return "Exame de brucelose";
  return "Outros exames";
}

function CalendarioSanitarioView() {
  const [regras, setRegras] = useState<RegraCalendario[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [eventos, setEventos] = useState<EventoPrev[]>([]);
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [eventoId, setEventoId] = useState("");
  const [recarregar, setRecarregar] = useState(0);
  const admin = ehAdmin();

  useEffect(() => { fetchEventosSanitarios().then(setEventos).catch(() => {}); }, []);
  useEffect(() => {
    fetchCalendarioSanitario({ dataInicio: ini || undefined, dataFim: fim || undefined, eventoSanitarioId: eventoId ? Number(eventoId) : undefined })
      .then(setRegras).catch((e) => setError(e.message));
  }, [ini, fim, eventoId, recarregar]);

  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(regras || []);

  const linhasExport = (regras || []).map((r) => ({
    ...r, frequenciaFmt: `a cada ${r.frequencia_valor} ${LABEL_FREQ[r.frequencia_unidade]}`,
    proxima_ocorrencia_fmt: formatDate(r.proxima_ocorrencia),
  }));

  const excluir = async (r: RegraCalendario) => {
    if (!window.confirm(`Excluir a regra "${r.evento_sanitario_nome}" de ${formatDate(r.data_evento)}?`)) return;
    try { await excluirCalendarioSanitario(r.id); setRecarregar((n) => n + 1); }
    catch (e: any) { setError(e.message); }
  };
  const lancarFinanceiro = (r: RegraCalendario) => {
    window.location.href = `/lancamentos?ir=financeiro_despesa&servico=${encodeURIComponent(servicoDoExame(r.evento_sanitario_nome))}`;
  };

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <>
      <div style={{ marginBottom: "0.75rem" }}>
        <h2 className="text-lg font-bold flex items-center gap-2"><Shield size={18} style={{ color: "var(--dourado)" }} /> Preventivo (calendário sanitário)</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Regras e próximas ocorrências de manejo preventivo (vacinas, exames e tratamentos). Para lançar um preventivo, use Lançamentos › Sanitário › Preventiva.</p>
      </div>

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
            <span>Regras do calendário sanitário ({regras.length}) — clique no cabeçalho para ordenar</span>
            <ExportarBotoes titulo="Calendário sanitário" nomeArquivoBase="calendario_sanitario" colunas={COLUNAS_CALENDARIO} linhas={linhasExport} />
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "480px" }}>
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Evento" campo="evento_sanitario_nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Categoria alvo" campo="categoria_alvo" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Doença" campo="doenca_nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <th>Produto</th><th>Dosagem</th><th>Frequência</th>
                <ThOrdenavel label="Próxima ocorrência" campo="proxima_ocorrencia" coluna={coluna} dir={dir} ordenar={ordenar} />
                {admin && <th style={{ textAlign: "right" }}>Ações</th>}
              </tr></thead>
              <tbody>
                {linhasOrdenadas.map((r) => {
                  const ehExame = (r as any).categoria_preventiva === "exame";
                  return (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 700 }}>{r.evento_sanitario_nome}{ehExame ? <span style={{ fontSize: "0.68rem", color: "var(--blue)", marginLeft: 6 }}>exame</span> : null}</td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.categoria_alvo || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.doenca_nome || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.produto || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.dosagem || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>a cada {r.frequencia_valor} {LABEL_FREQ[r.frequencia_unidade]}</td>
                    <td style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--dourado-light)" }}>{formatDate(r.proxima_ocorrencia)}</td>
                    {admin && (
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <span style={{ display: "inline-flex", gap: "0.35rem", alignItems: "center" }}>
                          {ehExame && (
                            <button title="Lançar financeiro (exame)" onClick={() => lancarFinanceiro(r)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--green-light)", fontSize: "0.72rem", fontWeight: 700 }}>$ Financeiro</button>
                          )}
                          <a title="Editar em Lançamentos" href="/lancamentos?ir=calendario_sanitario" style={{ color: "var(--text-muted)", padding: 2 }}><Pencil size={14} /></a>
                          <button title="Excluir" onClick={() => excluir(r)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}><Trash2 size={14} /></button>
                        </span>
                      </td>
                    )}
                  </tr>
                  );
                })}
                {!regras.length && <tr><td colSpan={admin ? 8 : 7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma regra no filtro.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

type Aplic = {
  id: number; numero: string; raca: string; produto: string; categoria: string;
  dose: number | null; unidade: string | null; via: string | null; responsavel: string | null;
  atividade: string | null; obs: string | null; ordem_parto: number | null;
  lote: string | null; categoria_animal: string | null; natureza: string | null;
  data: string | null; ano: number | null; mes: string | null;
  usuario_nome?: string | null;
};

const CORES = ["var(--vinho-light, #8B3A56)", "var(--dourado)", "var(--blue)", "var(--amber)", "var(--green-light)", "var(--red)", "#7A5C99", "#4C9AA8"];
const UNIDADES_APLIC = ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"];

function AplicacoesView({ natureza = "curativo" }: { natureza?: "curativo" | "preventivo" }) {
  const [regs, setRegs] = useState<Aplic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fCat, setFCat] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [buscaProd, setBuscaProd] = useState("");
  const [buscaAnimal, setBuscaAnimal] = useState("");
  const [fOrdemParto, setFOrdemParto] = useState<string[]>([]);
  const [editId, setEditId] = useState<number | null>(null);
  const [editVals, setEditVals] = useState<{ data: string; produto: string; dose: string; unidade: string; via: string; responsavel: string; obs: string }>({ data: "", produto: "", dose: "", unidade: "", via: "", responsavel: "", obs: "" });
  const [ocupado, setOcupado] = useState<number | null>(null);
  const admin = ehAdmin();

  // Cada aba busca só o que é dela — legado/importado (natureza=null) conta
  // como curativo (ver Sanidade.natureza).
  const carregar = () => fetchSanidade().then((d) => setRegs(
    (d.aplicacoes as Aplic[]).filter((a) => natureza === "preventivo" ? a.natureza === "preventivo" : a.natureza !== "preventivo")
  )).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, [natureza]);

  const iniciarEdicao = (a: Aplic) => {
    setEditId(a.id);
    setEditVals({
      data: a.data ?? "", produto: a.produto ?? "", dose: a.dose == null ? "" : String(a.dose),
      unidade: a.unidade ?? "", via: a.via ?? "", responsavel: a.responsavel ?? "", obs: a.obs ?? "",
    });
    setError(null);
  };

  const salvarEdicao = async (a: Aplic) => {
    setOcupado(a.id); setError(null);
    try {
      await editarAplicacaoSanidade(a.id, {
        data_aplicacao: editVals.data || undefined,
        produto: editVals.produto.trim() || undefined,
        dose: editVals.dose.trim() === "" ? null : Number(editVals.dose),
        unidade: editVals.unidade || null,
        via: editVals.via.trim() || null,
        responsavel: editVals.responsavel.trim() || null,
        obs: editVals.obs.trim() || null,
      });
      setEditId(null);
      await carregar();
    } catch (e: any) { setError(e.message); }
    finally { setOcupado(null); }
  };

  const excluir = async (a: Aplic) => {
    if (!window.confirm(`Excluir a aplicação de "${a.produto}" no animal ${a.numero}? Isso não pode ser desfeito.`)) return;
    setOcupado(a.id); setError(null);
    try {
      await excluirAplicacaoSanidade(a.id);
      await carregar();
    } catch (e: any) { setError(e.message); }
    finally { setOcupado(null); }
  };

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
      (!buscaAnimal || a.numero.toLowerCase().includes(buscaAnimal.toLowerCase())) &&
      (fOrdemParto.length === 0 || (a.ordem_parto !== null && fOrdemParto.includes(String(a.ordem_parto))))
    );
  }, [regs, fCat, ini, fim, buscaProd, buscaAnimal, fOrdemParto]);

  // Quando há filtro por período (de/até), as linhas SEM data ficam de fora — conta quantas para avisar o usuário.
  const semDataExcluidas = useMemo(() => {
    if (!regs || (!ini && !fim)) return 0;
    return regs.filter((a) =>
      (!fCat || a.categoria === fCat) &&
      (!buscaProd || a.produto.toLowerCase().includes(buscaProd.toLowerCase())) &&
      (!buscaAnimal || a.numero.toLowerCase().includes(buscaAnimal.toLowerCase())) &&
      !a.data
    ).length;
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
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
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
            <MultiFiltro label="Ordem de parto" opcoes={opc((a) => a.ordem_parto == null ? null : String(a.ordem_parto))} selecionados={fOrdemParto} onChange={setFOrdemParto} formatar={(v) => `${v}ª`} />
          </div>
        </div>

        {semDataExcluidas > 0 && (
          <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.75rem" }}>
            {semDataExcluidas} aplicaç{semDataExcluidas === 1 ? "ão" : "ões"} sem data não {semDataExcluidas === 1 ? "é exibida" : "são exibidas"} no filtro por período.
          </p>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="kpi-card"><p className="kpi-value">{filtrados.length}</p><p className="kpi-label">Aplicações</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{animaisTratados}</p><p className="kpi-label">Animais tratados</p></div>
          <div className="kpi-card"><p className="kpi-value">{produtos}</p><p className="kpi-label">Produtos distintos</p></div>
          <div className="kpi-card"><p className="kpi-value">{porCategoria.length}</p><p className="kpi-label">Categorias</p></div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div className="card">
            <div className="card-header mb-3">Aplicações por Categoria <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>(clique para filtrar)</span></div>
            <div title="Clique numa barra para filtrar as aplicações por categoria">
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

        <div className="grid grid-cols-1 gap-4">
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
                <thead><tr><th>Data</th><th>Animal</th><th>Produto</th><th>Categoria</th><th style={{ textAlign: "right" }}>Dose</th>{admin && <th style={{ textAlign: "left" }}>Usuário</th>}{admin && <th style={{ textAlign: "right" }}>Ações</th>}</tr></thead>
                <tbody>
                  {filtrados.slice(0, 300).map((a) => {
                    const editando = editId === a.id;
                    const inp: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "5px", padding: "0.25rem 0.4rem", fontSize: "0.75rem", width: "100%" };
                    return (
                    <Fragment key={a.id}>
                      <tr>
                        <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{a.data ? new Date(a.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                        <td style={{ fontWeight: 700 }}>{a.numero}</td>
                        <td style={{ fontSize: "0.75rem" }}>{a.produto}</td>
                        <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{a.categoria}</td>
                        <td style={{ textAlign: "right" }}>{a.dose ?? "—"}{a.unidade ? ` ${a.unidade}` : ""}</td>
                        {admin && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.usuario_nome ?? "—"}</td>}
                        {admin && (
                          <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                            {!editando && (
                              <span style={{ display: "inline-flex", gap: "0.3rem" }}>
                                <button title="Editar" onClick={() => iniciarEdicao(a)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2 }}><Pencil size={14} /></button>
                                <button title="Excluir" disabled={ocupado === a.id} onClick={() => excluir(a)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}><Trash2 size={14} /></button>
                              </span>
                            )}
                          </td>
                        )}
                      </tr>
                      {editando && (
                        <tr>
                          <td colSpan={admin ? 7 : 5} style={{ background: "var(--surface-2)", padding: "0.6rem" }}>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Data</label>
                                <input type="date" style={inp} value={editVals.data} onChange={(e) => setEditVals((s) => ({ ...s, data: e.target.value }))} /></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Produto</label>
                                <input style={inp} value={editVals.produto} onChange={(e) => setEditVals((s) => ({ ...s, produto: e.target.value }))} /></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Dose</label>
                                <input type="number" step="any" style={inp} value={editVals.dose} onChange={(e) => setEditVals((s) => ({ ...s, dose: e.target.value }))} /></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Unidade</label>
                                <select style={inp} value={editVals.unidade} onChange={(e) => setEditVals((s) => ({ ...s, unidade: e.target.value }))}>
                                  <option value="">—</option>
                                  {!UNIDADES_APLIC.includes(editVals.unidade) && editVals.unidade && <option value={editVals.unidade}>{editVals.unidade}</option>}
                                  {UNIDADES_APLIC.map((u) => <option key={u} value={u}>{u}</option>)}
                                </select></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Via</label>
                                <select style={inp} value={editVals.via} onChange={(e) => setEditVals((s) => ({ ...s, via: e.target.value }))}>
                                  <option value="">—</option>
                                  {!VIAS_APLICACAO.includes(editVals.via) && editVals.via && <option value={editVals.via}>{editVals.via}</option>}
                                  {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
                                </select></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Responsável</label>
                                <select style={inp} value={editVals.responsavel} onChange={(e) => setEditVals((s) => ({ ...s, responsavel: e.target.value }))}>
                                  <option value="">—</option>
                                  {!RESPONSAVEIS.includes(editVals.responsavel) && editVals.responsavel && <option value={editVals.responsavel}>{editVals.responsavel}</option>}
                                  {RESPONSAVEIS.map((r) => <option key={r} value={r}>{r}</option>)}
                                </select></div>
                              <div style={{ gridColumn: "span 2" }}><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Observação</label>
                                <input style={inp} value={editVals.obs} onChange={(e) => setEditVals((s) => ({ ...s, obs: e.target.value }))} /></div>
                            </div>
                            <div className="flex gap-2 mt-2">
                              <button className="btn-primary" disabled={ocupado === a.id} onClick={() => salvarEdicao(a)} style={{ fontSize: "0.78rem" }}><Check size={13} /> {ocupado === a.id ? "…" : "Salvar"}</button>
                              <button className="btn-ghost" disabled={ocupado === a.id} onClick={() => setEditId(null)} style={{ fontSize: "0.78rem" }}><X size={13} /> Cancelar</button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                    );
                  })}
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

// ─────────────────────────── Doença / Motivo (curativa) ───────────────────────────
// Resumo dos tratamentos curativos agrupados pelo motivo (atividade) — cada
// doença/motivo é clicável e expande os casos, filtráveis por animal, lote,
// período e categoria do animal.
function DoencaMotivoView() {
  const [regs, setRegs] = useState<Aplic[] | null>(null);
  const [aberto, setAberto] = useState<string | null>(null);
  const [buscaAnimal, setBuscaAnimal] = useState("");
  const [fLote, setFLote] = useState("");
  const [fCategoria, setFCategoria] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");

  useEffect(() => { fetchSanidade().then((d) => setRegs(d.aplicacoes)).catch(() => setRegs([])); }, []);

  // A aba "Curativa" mostra o que não veio do calendário preventivo — dados
  // legados/importados (natureza=null) são tratados como curativo.
  const curativos = useMemo(() => (regs || []).filter((r) => r.natureza !== "preventivo"), [regs]);

  const filtrados = useMemo(() => curativos.filter((r) =>
    (!buscaAnimal || r.numero.toLowerCase().includes(buscaAnimal.toLowerCase())) &&
    (!fLote || r.lote === fLote) &&
    (!fCategoria || r.categoria_animal === fCategoria) &&
    (!ini || (r.data ? r.data >= ini : false)) &&
    (!fim || (r.data ? r.data <= fim : false))
  ), [curativos, buscaAnimal, fLote, fCategoria, ini, fim]);

  const lotesOpc = useMemo(() => Array.from(new Set(curativos.map((r) => r.lote).filter(Boolean))).sort() as string[], [curativos]);
  const categoriasOpc = useMemo(() => Array.from(new Set(curativos.map((r) => r.categoria_animal).filter(Boolean))).sort() as string[], [curativos]);

  const grupos = useMemo(() => {
    const m = new Map<string, { motivo: string; casos: Aplic[]; ultima: string | null }>();
    for (const r of filtrados) {
      const motivo = (r.atividade || r.categoria || "Não informado") as string;
      const g = m.get(motivo) || { motivo, casos: [], ultima: null };
      g.casos.push(r);
      if (!g.ultima || (r.data && r.data > g.ultima)) g.ultima = r.data || g.ultima;
      m.set(motivo, g);
    }
    return Array.from(m.values()).sort((a, b) => b.casos.length - a.casos.length);
  }, [filtrados]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const filtroAtivo = !!(buscaAnimal || fLote || fCategoria || ini || fim);

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
            <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={buscaAnimal} onChange={(e) => setBuscaAnimal(e.target.value)} placeholder="ex.: 068" /></div></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lote</label>
            <select style={selStyle} value={fLote} onChange={(e) => setFLote(e.target.value)}><option value="">Todos</option>{lotesOpc.map((l) => <option key={l} value={l}>{l}</option>)}</select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria do animal</label>
            <select style={selStyle} value={fCategoria} onChange={(e) => setFCategoria(e.target.value)}><option value="">Todas</option>{categoriasOpc.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
            <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
            <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
        </div>
      </div>

      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><HeartPulse size={16} /> Doença / Motivo dos tratamentos</div>
        {!regs ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : !grupos.length ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{filtroAtivo ? "Nenhum caso encontrado com esses filtros." : "Nenhum tratamento curativo lançado ainda."}</p>
        ) : (
          <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
            {grupos.map((g) => {
              const expandido = aberto === g.motivo;
              return (
                <Fragment key={g.motivo}>
                  <div
                    className="flex items-center justify-between"
                    style={{ padding: "0.55rem 0.8rem", borderBottom: "1px solid var(--border)", cursor: "pointer", background: expandido ? "var(--surface-2)" : "transparent" }}
                    onClick={() => setAberto(expandido ? null : g.motivo)}
                  >
                    <span className="flex items-center gap-2" style={{ fontSize: "0.86rem", fontWeight: 600 }}>
                      {expandido ? <ChevronDown size={14} /> : <ChevronRight size={14} />} {g.motivo}
                    </span>
                    <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{g.casos.length} caso(s){g.ultima ? ` · último ${formatDate(g.ultima)}` : ""}</span>
                  </div>
                  {expandido && (
                    <div style={{ borderBottom: "1px solid var(--border)", padding: "0.5rem 0.8rem", background: "var(--surface-1, var(--surface))" }}>
                      <div className="overflow-x-auto">
                        <table className="fazenda-table">
                          <thead><tr><th>Data</th><th>Animal</th><th>Lote</th><th>Categoria</th><th>Produto</th><th style={{ textAlign: "right" }}>Dose</th><th>Obs.</th></tr></thead>
                          <tbody>
                            {g.casos.slice().sort((a, b) => (b.data || "").localeCompare(a.data || "")).map((c) => (
                              <tr key={c.id}>
                                <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{c.data ? formatDate(c.data) : "—"}</td>
                                <td style={{ fontWeight: 700 }}>{c.numero}</td>
                                <td style={{ fontSize: "0.75rem" }}>{c.lote || "—"}</td>
                                <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{c.categoria_animal || "—"}</td>
                                <td style={{ fontSize: "0.75rem" }}>{c.produto}</td>
                                <td style={{ textAlign: "right", fontSize: "0.75rem" }}>{c.dose ?? "—"}{c.unidade ? ` ${c.unidade}` : ""}</td>
                                <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{c.obs || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </Fragment>
              );
            })}
          </div>
        )}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          O cadastro de doenças e princípios ativos fica em Configurações › Cadastro › Sanitário.
        </p>
      </div>
    </>
  );
}

// ─────────────────────────── Protocolos sanitários (curativa) ───────────────────────────
type EtapaProtocolo = { id: number; dia: number; produto: string; dosagem: number; unidade: string; via: string | null; observacao: string | null };
type AplicacaoProtocolo = { id: number; data_prevista: string; produto: string | null; realizada: boolean; data_realizacao: string | null; etapa: EtapaProtocolo | null };
type LancamentoProtocolo = {
  id: number; protocolo_id: number; protocolo_nome: string; numero_matriz: string; data_inicio: string;
  responsavel: string | null; observacao: string | null;
  classificacao_mastite: string | null; grau_mastite: number | null; agente: string | null;
  resultado_cmt: string | null; tetos_afetados: string | null; usuario_nome?: string | null;
  aplicacoes: AplicacaoProtocolo[];
};

function ProtocolosSanitariosView() {
  const [lancs, setLancs] = useState<LancamentoProtocolo[] | null>(null);
  const [aberto, setAberto] = useState<number | null>(null);
  const [buscaAnimal, setBuscaAnimal] = useState("");
  const [fProtocolo, setFProtocolo] = useState("");
  const [fStatus, setFStatus] = useState<"" | "andamento" | "concluido">("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");

  useEffect(() => { fetchLancamentosProtocolo().then(setLancs).catch(() => setLancs([])); }, []);

  const protocolosOpc = useMemo(() => Array.from(new Set((lancs || []).map((l) => l.protocolo_nome))).sort(), [lancs]);

  const statusDe = (l: LancamentoProtocolo): "andamento" | "concluido" =>
    l.aplicacoes.length && l.aplicacoes.every((a) => a.realizada) ? "concluido" : "andamento";

  const filtrados = useMemo(() => (lancs || []).filter((l) =>
    (!buscaAnimal || l.numero_matriz.toLowerCase().includes(buscaAnimal.toLowerCase())) &&
    (!fProtocolo || l.protocolo_nome === fProtocolo) &&
    (!fStatus || statusDe(l) === fStatus) &&
    (!ini || l.data_inicio >= ini) &&
    (!fim || l.data_inicio <= fim)
  ), [lancs, buscaAnimal, fProtocolo, fStatus, ini, fim]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
            <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={buscaAnimal} onChange={(e) => setBuscaAnimal(e.target.value)} placeholder="ex.: 068" /></div></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Protocolo</label>
            <select style={selStyle} value={fProtocolo} onChange={(e) => setFProtocolo(e.target.value)}><option value="">Todos</option>{protocolosOpc.map((p) => <option key={p} value={p}>{p}</option>)}</select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Status</label>
            <select style={selStyle} value={fStatus} onChange={(e) => setFStatus(e.target.value as typeof fStatus)}>
              <option value="">Todos</option><option value="andamento">Em andamento</option><option value="concluido">Concluído</option>
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
            <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
            <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
        </div>
      </div>

      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><ListChecks size={16} /> Protocolos sanitários lançados ({filtrados.length})</div>
        {!lancs ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : !filtrados.length ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo lançado com esses filtros.</p>
        ) : (
          <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
            {filtrados.map((l) => {
              const expandido = aberto === l.id;
              const status = statusDe(l);
              return (
                <Fragment key={l.id}>
                  <div
                    className="flex items-center justify-between"
                    style={{ padding: "0.55rem 0.8rem", borderBottom: "1px solid var(--border)", cursor: "pointer", background: expandido ? "var(--surface-2)" : "transparent" }}
                    onClick={() => setAberto(expandido ? null : l.id)}
                  >
                    <span className="flex items-center gap-2" style={{ fontSize: "0.86rem", fontWeight: 600 }}>
                      {expandido ? <ChevronDown size={14} /> : <ChevronRight size={14} />} {l.protocolo_nome} <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>— animal {l.numero_matriz}</span>
                    </span>
                    <span className="flex items-center gap-3" style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {formatDate(l.data_inicio)}
                      <span style={{ fontWeight: 700, color: status === "concluido" ? "var(--green-light)" : "var(--amber)" }}>
                        {status === "concluido" ? "Concluído" : "Em andamento"}
                      </span>
                    </span>
                  </div>
                  {expandido && (
                    <div style={{ borderBottom: "1px solid var(--border)", padding: "0.5rem 0.8rem", background: "var(--surface-1, var(--surface))" }}>
                      {(l.classificacao_mastite || l.responsavel) && (
                        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                          {l.classificacao_mastite && <>Mastite {l.classificacao_mastite}{l.grau_mastite ? ` (grau ${l.grau_mastite})` : ""}{l.tetos_afetados ? ` · tetos: ${l.tetos_afetados}` : ""}{l.agente ? ` · agente: ${l.agente}` : ""} · </>}
                          {l.responsavel && <>Responsável: {l.responsavel}</>}
                        </p>
                      )}
                      <div className="overflow-x-auto">
                        <table className="fazenda-table">
                          <thead><tr><th>Dia</th><th>Data prevista</th><th>Produto</th><th style={{ textAlign: "right" }}>Dose</th><th>Via</th><th>Realizada?</th><th>Data realização</th></tr></thead>
                          <tbody>
                            {l.aplicacoes.slice().sort((a, b) => (a.etapa?.dia ?? 0) - (b.etapa?.dia ?? 0)).map((a) => (
                              <tr key={a.id}>
                                <td>{a.etapa ? `D${a.etapa.dia}` : "—"}</td>
                                <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{formatDate(a.data_prevista)}</td>
                                <td style={{ fontSize: "0.75rem" }}>{a.produto || a.etapa?.produto || "—"}</td>
                                <td style={{ textAlign: "right", fontSize: "0.75rem" }}>{a.etapa ? `${a.etapa.dosagem} ${a.etapa.unidade}` : "—"}</td>
                                <td style={{ fontSize: "0.75rem" }}>{a.etapa?.via || "—"}</td>
                                <td style={{ fontSize: "0.75rem", fontWeight: 700, color: a.realizada ? "var(--green-light)" : "var(--text-muted)" }}>{a.realizada ? "Sim" : "Não"}</td>
                                <td style={{ fontSize: "0.75rem" }}>{a.data_realizacao ? formatDate(a.data_realizacao) : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </Fragment>
              );
            })}
          </div>
        )}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Lance um novo protocolo em Lançamentos › Sanitário › Curativa › Protocolo sanitário.
        </p>
      </div>
    </>
  );
}

type AbaSanidade = "curativa" | "preventiva";
const ABAS_SANIDADE = [
  { id: "curativa", label: "Curativa", icon: HeartPulse, title: "Tratamentos curativos: aplicações, doença/motivo e protocolos" },
  { id: "preventiva", label: "Preventiva", icon: Shield, title: "Manejo preventivo: aplicações e calendário sanitário" },
] as const satisfies readonly { id: AbaSanidade; label: string; icon: any; title: string }[];

type AbaCurativa = "curativo" | "doenca" | "protocolos";
const ABAS_CURATIVA = [
  { id: "curativo", label: "Curativo (aplicações)", icon: ClipboardList, title: "Medicamentos aplicados no rebanho" },
  { id: "doenca", label: "Doença / Motivo", icon: Activity, title: "Tratamentos por doença/motivo" },
  { id: "protocolos", label: "Protocolos sanitários", icon: ListChecks, title: "Protocolos multi-etapa lançados (mastite e outros)" },
] as const satisfies readonly { id: AbaCurativa; label: string; icon: any; title: string }[];

type AbaPreventiva = "aplicacoes" | "calendario";
const ABAS_PREVENTIVA = [
  { id: "aplicacoes", label: "Aplicações", icon: ClipboardList, title: "Aplicações preventivas já lançadas" },
  { id: "calendario", label: "Calendário sanitário", icon: CalendarClock, title: "Regras recorrentes do calendário preventivo" },
] as const satisfies readonly { id: AbaPreventiva; label: string; icon: any; title: string }[];

export default function SanidadePage() {
  const [aba, setAba] = useState<AbaSanidade>("curativa");
  const [abaCur, setAbaCur] = useState<AbaCurativa>("curativo");
  const [abaPrev, setAbaPrev] = useState<AbaPreventiva>("aplicacoes");

  const subNavTree: SubNavNode[] = useMemo(() => ABAS_SANIDADE.map((a) => ({
    id: a.id, label: a.label, icon: a.icon,
    children: a.id === "curativa"
      ? ABAS_CURATIVA.map((c) => ({ id: c.id, label: c.label, icon: c.icon }))
      : a.id === "preventiva"
        ? ABAS_PREVENTIVA.map((p) => ({ id: p.id, label: p.label, icon: p.icon }))
        : undefined,
  })), []);
  const onSelectSubNav = useCallback((id: string) => {
    if (ABAS_CURATIVA.some((c) => c.id === id)) { setAba("curativa"); setAbaCur(id as AbaCurativa); }
    else if (ABAS_PREVENTIVA.some((p) => p.id === id)) { setAba("preventiva"); setAbaPrev(id as AbaPreventiva); }
    else setAba(id as AbaSanidade);
  }, []);
  useSubNavRegister(useMemo(() => ({
    tree: subNavTree,
    activeId: aba === "curativa" ? abaCur : aba === "preventiva" ? abaPrev : aba,
    onSelect: onSelectSubNav,
  }), [subNavTree, aba, abaCur, abaPrev, onSelectSubNav]));

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Syringe size={22} style={{ color: "var(--dourado)" }} /> Sanidade</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Sanidade curativa e preventiva. O controle de BST ficou em Produção › Relatórios de BST.</p>
      </div>

      {aba === "curativa" && (
        <>
          {abaCur === "curativo" && <AplicacoesView natureza="curativo" />}
          {abaCur === "doenca" && <DoencaMotivoView />}
          {abaCur === "protocolos" && <ProtocolosSanitariosView />}
        </>
      )}
      {aba === "preventiva" && (
        <>
          {abaPrev === "aplicacoes" && <AplicacoesView natureza="preventivo" />}
          {abaPrev === "calendario" && <CalendarioSanitarioView />}
        </>
      )}
    </div>
  );
}
