"use client";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Syringe, AlertTriangle, Filter, Search, CalendarClock, ClipboardList, Baby, Pencil, Trash2, Check, X, Shield, Droplets, HeartPulse, Activity } from "lucide-react";
import { fetchSanidade, fetchCalendarioSanitario, fetchEventosSanitarios, fetchAnimais, fetchRelatorioBezerras, editarAplicacaoSanidade, excluirAplicacaoSanidade, excluirCalendarioSanitario, ehAdmin, formatDate, fetchAgenda } from "@/lib/api";
import { RESPONSAVEIS, VIAS_APLICACAO } from "@/lib/constants";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { SelecaoAnimaisTabela } from "@/components/SelecaoAnimaisTabela";
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
  data: string | null; ano: number | null; mes: string | null;
};

const CORES = ["var(--vinho-light, #8B3A56)", "var(--dourado)", "var(--blue)", "var(--amber)", "var(--green-light)", "var(--red)", "#7A5C99", "#4C9AA8"];
const UNIDADES_APLIC = ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"];

function AplicacoesView() {
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

  const carregar = () => fetchSanidade().then((d) => setRegs(d.aplicacoes)).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

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
                <thead><tr><th>Data</th><th>Animal</th><th>Produto</th><th>Categoria</th><th style={{ textAlign: "right" }}>Dose</th>{admin && <th style={{ textAlign: "right" }}>Ações</th>}</tr></thead>
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
                          <td colSpan={admin ? 6 : 5} style={{ background: "var(--surface-2)", padding: "0.6rem" }}>
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

/* ───────────────────────── Relatório sanitário de bezerras (colostragem + teste de sangue/IgG) ───────────────────────── */
type LinhaBezerra = {
  numero: string; nome: string | null; sexo: string | null; categoria_abrev: string | null;
  grupo_primario: string | null; data_nasc: string | null; idade_meses: number | null; ativo: boolean;
  tomou_colostro: boolean | null; litros_colostro: number | null; brix_colostro: number | null;
  classe_colostro: "ouro" | "prata" | "bronze" | null; data_colostro: string | null;
  hora_parto: string | null; hora_colostro: string | null; peso_nascer_kg: number | null;
  brix_soro: number | null; proteina_serica: number | null;
  classe_soro: "sucesso" | "alerta" | "falha" | null;
  classe_colostragem: "excelente" | "boa" | "aceitavel" | "ruim" | null;
  apenas_colostro_po: boolean; sem_mensuracao: boolean; data_teste_sangue: string | null;
};

const LABEL_CLASSE_COLOSTRO: Record<string, { txt: string; cor: string }> = {
  ouro: { txt: "Ouro", cor: "var(--dourado-light)" }, prata: { txt: "Prata", cor: "var(--text-muted)" },
  bronze: { txt: "Bronze", cor: "var(--red)" },
};
const LABEL_CLASSE_SORO: Record<string, { txt: string; cor: string }> = {
  sucesso: { txt: "Sucesso", cor: "var(--green-light)" }, alerta: { txt: "Alerta", cor: "var(--amber)" },
  falha: { txt: "Falha", cor: "var(--red)" },
};
const LABEL_CLASSE_COLOSTRAGEM: Record<string, { txt: string; cor: string }> = {
  excelente: { txt: "Excelente", cor: "var(--green-light)" }, boa: { txt: "Boa", cor: "var(--dourado-light)" },
  aceitavel: { txt: "Aceitável", cor: "var(--amber)" }, ruim: { txt: "Ruim", cor: "var(--red)" },
};

const COLUNAS_BEZERRAS = [
  { header: "Data", key: "data_teste_sangue" }, { header: "Nº", key: "numero" }, { header: "Nome", key: "nome" },
  { header: "Categoria", key: "categoria_abrev" }, { header: "Lote", key: "grupo_primario" }, { header: "Idade (meses)", key: "idade_meses" },
  { header: "Tomou colostro", key: "tomou_colostroFmt" }, { header: "Litros", key: "litros_colostro" },
  { header: "Brix colostro (%)", key: "brix_colostro" }, { header: "Classe colostro", key: "classe_colostroFmt" },
  { header: "Brix soro (%)", key: "brix_soro" }, { header: "Proteína sérica (g/dL)", key: "proteina_serica" },
  { header: "Eficiência colostragem", key: "classe_colostragemFmt" }, { header: "Classe soro", key: "classe_soroFmt" },
];

function RelatorioBezerrasView() {
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [modo, setModo] = useState<"todos" | "animal" | "lote" | "selecao">("todos");
  const [faixaEtaria, setFaixaEtaria] = useState("");
  const [numeroFiltro, setNumeroFiltro] = useState("");
  const [loteFiltro, setLoteFiltro] = useState("");
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [dados, setDados] = useState<LinhaBezerra[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchAnimais().then(setAnimais).catch(() => {}); }, []);

  useEffect(() => {
    const filtros: { faixaEtaria?: string; numero?: string; lote?: string; numeros?: string[] } = {};
    if (faixaEtaria) filtros.faixaEtaria = faixaEtaria;
    if (modo === "animal" && numeroFiltro) filtros.numero = numeroFiltro;
    if (modo === "lote" && loteFiltro) filtros.lote = loteFiltro;
    if (modo === "selecao" && selecionados.size) filtros.numeros = Array.from(selecionados);
    fetchRelatorioBezerras(filtros).then(setDados).catch((e) => setErro(e.message));
  }, [faixaEtaria, modo, numeroFiltro, loteFiltro, selecionados]);

  const lotes = useMemo(
    () => Array.from(new Set(animais.map((a) => a.grupo_primario).filter(Boolean))).sort() as string[],
    [animais]
  );

  const toggleSelecionado = (numero: string) => setSelecionados((prev) => {
    const novo = new Set(prev);
    novo.has(numero) ? novo.delete(numero) : novo.add(numero);
    return novo;
  });
  const toggleTodos = () => setSelecionados((prev) => (prev.size === animais.length ? new Set() : new Set(animais.map((a) => a.numero))));

  const linhasExport = (dados || []).map((l) => ({
    ...l, tomou_colostroFmt: l.tomou_colostro == null ? "—" : l.tomou_colostro ? "Sim" : "Não",
    classe_colostroFmt: l.classe_colostro ? LABEL_CLASSE_COLOSTRO[l.classe_colostro].txt : "—",
    classe_soroFmt: l.classe_soro ? LABEL_CLASSE_SORO[l.classe_soro].txt : "—",
    classe_colostragemFmt: l.classe_colostragem ? LABEL_CLASSE_COLOSTRAGEM[l.classe_colostragem].txt : (l.apenas_colostro_po ? "Só colostro em pó" : l.sem_mensuracao ? "Sem mensuração" : "—"),
  }));

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          Indicadores de colostragem e teste de sangue (IgG) por animal — inclusive já adultos, para rastrear na fase
          adulta problemas que vieram de má colostragem na cria.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Faixa etária</label>
            <select style={selStyle} value={faixaEtaria} onChange={(e) => setFaixaEtaria(e.target.value)}>
              <option value="">Todas</option>
              <option value="ate_12">Bezerras (até 12 meses)</option>
              <option value="acima_12">Acima de 12 meses (novilhas/vacas)</option>
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ver</label>
            <select style={selStyle} value={modo} onChange={(e) => setModo(e.target.value as typeof modo)}>
              <option value="todos">Todos os animais</option>
              <option value="animal">Um animal</option>
              <option value="lote">Por lote atual</option>
              <option value="selecao">Seleção de vários animais</option>
            </select></div>
          {modo === "animal" && (
            <div style={{ gridColumn: "span 2" }}><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
              <AnimalPicker animais={animais} value={numeroFiltro} onChange={setNumeroFiltro} /></div>
          )}
          {modo === "lote" && (
            <div style={{ gridColumn: "span 2" }}><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lote</label>
              <select style={selStyle} value={loteFiltro} onChange={(e) => setLoteFiltro(e.target.value)}>
                <option value="">Selecione…</option>
                {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
              </select></div>
          )}
        </div>
        {modo === "selecao" && (
          <SelecaoAnimaisTabela
            animais={animais} selecionados={selecionados} toggle={toggleSelecionado} toggleTodos={toggleTodos}
            colunas={[
              { header: "Grupo", render: (a) => a.grupo_primario || "—" },
              { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
            ]}
          />
        )}
      </div>

      {erro && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {erro}.</span></div>}
      {!dados && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span className="flex items-center gap-2"><Baby size={14} /> Relatório sanitário de bezerras ({dados.length})</span>
            <ExportarBotoes titulo="Relatório sanitário de bezerras" nomeArquivoBase="relatorio_bezerras" colunas={COLUNAS_BEZERRAS} linhas={linhasExport} />
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "560px" }}>
            <table className="fazenda-table">
              <thead>
                <tr>
                  <th>Nº</th><th>Nome</th><th>Categoria</th><th>Lote</th><th style={{ textAlign: "right" }}>Idade (m)</th>
                  <th>Colostro?</th><th style={{ textAlign: "right" }}>Litros</th><th style={{ textAlign: "right" }}>Brix colostro</th>
                  <th>Classe colostro</th><th style={{ textAlign: "right" }}>Brix soro</th>
                  <th style={{ textAlign: "right" }}>Prot. sérica</th><th>Eficiência (IgG)</th>
                </tr>
              </thead>
              <tbody>
                {dados.map((l) => {
                  const grave = l.classe_soro === "falha" || l.classe_colostragem === "ruim" || l.classe_colostro === "bronze";
                  const trStyle: React.CSSProperties = grave
                    ? { background: "rgba(192,57,43,0.12)", borderLeft: "3px solid var(--red)" }
                    : {};
                  return (
                    <tr key={l.numero} style={trStyle}>
                      <td style={{ fontWeight: 700 }}>{l.numero}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.nome || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.categoria_abrev || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.grupo_primario || "—"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.idade_meses ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.tomou_colostro == null ? "—" : l.tomou_colostro ? "Sim" : "Não"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.litros_colostro ?? "—"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.brix_colostro ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem", fontWeight: 700, color: l.classe_colostro ? LABEL_CLASSE_COLOSTRO[l.classe_colostro].cor : "var(--text-muted)" }}>
                        {l.classe_colostro ? LABEL_CLASSE_COLOSTRO[l.classe_colostro].txt : "—"}
                      </td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.brix_soro ?? "—"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.proteina_serica ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem", fontWeight: 700, color: l.classe_colostragem ? LABEL_CLASSE_COLOSTRAGEM[l.classe_colostragem].cor : "var(--text-muted)" }}>
                        {l.classe_colostragem
                          ? LABEL_CLASSE_COLOSTRAGEM[l.classe_colostragem].txt
                          : l.apenas_colostro_po
                            ? <span style={{ color: "var(--blue)" }}>Só colostro em pó</span>
                            : l.sem_mensuracao
                              ? <span style={{ color: "var(--text-muted)" }}>Sem mensuração</span>
                              : "—"}
                      </td>
                    </tr>
                  );
                })}
                {!dados.length && <tr><td colSpan={12} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum animal encontrado com esses filtros.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

// ─────────────────────────── Doença / Motivo (curativa) ───────────────────────────
// Resumo dos tratamentos curativos agrupados pelo motivo (atividade) e pela
// categoria do produto — uma leitura rápida do "por que" das aplicações.
function DoencaMotivoView() {
  const [regs, setRegs] = useState<any[] | null>(null);
  useEffect(() => { fetchSanidade().then((d) => setRegs(d.aplicacoes)).catch(() => setRegs([])); }, []);
  const grupos = useMemo(() => {
    const m = new Map<string, { motivo: string; total: number; ultima: string | null }>();
    for (const r of regs || []) {
      const motivo = (r.atividade || r.categoria || "Não informado") as string;
      const g = m.get(motivo) || { motivo, total: 0, ultima: null };
      g.total += 1;
      if (!g.ultima || (r.data_aplicacao && r.data_aplicacao > g.ultima)) g.ultima = r.data_aplicacao || g.ultima;
      m.set(motivo, g);
    }
    return Array.from(m.values()).sort((a, b) => b.total - a.total);
  }, [regs]);
  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center gap-2"><HeartPulse size={16} /> Doença / Motivo dos tratamentos</div>
      {!regs ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : !grupos.length ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum tratamento curativo lançado ainda.</p>
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
          {grupos.map((g) => (
            <div key={g.motivo} className="flex items-center justify-between" style={{ padding: "0.55rem 0.8rem", borderBottom: "1px solid var(--border)" }}>
              <span style={{ fontSize: "0.86rem", fontWeight: 600 }}>{g.motivo}</span>
              <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{g.total} caso(s){g.ultima ? ` · último ${formatDate(g.ultima)}` : ""}</span>
            </div>
          ))}
        </div>
      )}
      <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
        O cadastro de doenças e princípios ativos fica em Configurações › Cadastro › Sanitário.
      </p>
    </div>
  );
}

// ─────────────────────────── BST (aba separada) ───────────────────────────
function BstView() {
  const [dados, setDados] = useState<any | null>(null);
  useEffect(() => { fetchAgenda().then(setDados).catch(() => setDados(null)); }, []);
  const aptos = dados?.bst_elegiveis || [];
  const excl = dados?.bst_excluidos || [];
  const th: React.CSSProperties = { textAlign: "left", padding: "0.4rem 0.6rem", fontSize: "0.72rem", textTransform: "uppercase", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" };
  const td: React.CSSProperties = { padding: "0.4rem 0.6rem", fontSize: "0.82rem", borderBottom: "1px solid var(--border)" };
  const Tabela = ({ titulo, lista, cor }: { titulo: string; lista: any[]; cor: string }) => (
    <div className="card">
      <div className="card-header mb-2 flex items-center gap-2" style={{ color: cor }}><Droplets size={15} /> {titulo} ({lista.length})</div>
      {!lista.length ? <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Nenhuma vaca.</p> : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr><th style={th}>Nº</th><th style={th}>Lote</th><th style={{ ...th, textAlign: "right" }}>DEL</th></tr></thead>
            <tbody>{lista.map((b: any) => (
              <tr key={b.numero_matriz}><td style={{ ...td, fontWeight: 700 }}>{b.numero_matriz}</td><td style={td}>{b.grupo || "—"}</td><td style={{ ...td, textAlign: "right" }}>{b.del_dias ?? "—"}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        BST (somatotropina bovina) — vacas aptas e excluídas do dia. Próxima visita BST: <strong>{dados?.proxima_visita_bst ? formatDate(dados.proxima_visita_bst) : "—"}</strong>.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Tabela titulo="BST — Aptas" lista={aptos} cor="var(--green-light)" />
        <Tabela titulo="BST — Excluídas" lista={excl} cor="var(--amber)" />
      </div>
    </div>
  );
}

type AbaSanidade = "curativa" | "preventiva" | "bst";
const ABAS_SANIDADE = [
  { id: "curativa", label: "Curativa", icon: HeartPulse, title: "Tratamentos curativos: aplicações, doença/motivo, protocolos e mastite" },
  { id: "preventiva", label: "Preventiva", icon: Shield, title: "Manejo preventivo: calendário/preventivo sanitário" },
  { id: "bst", label: "BST", icon: Droplets, title: "Somatotropina bovina — aptas e excluídas" },
] as const satisfies readonly { id: AbaSanidade; label: string; icon: any; title: string }[];

type AbaCurativa = "curativo" | "doenca" | "bezerras";
const ABAS_CURATIVA = [
  { id: "curativo", label: "Curativo (aplicações)", icon: ClipboardList, title: "Medicamentos aplicados no rebanho" },
  { id: "doenca", label: "Doença / Motivo", icon: Activity, title: "Tratamentos por doença/motivo" },
  { id: "bezerras", label: "Relatório de bezerras", icon: Baby, title: "Colostragem e teste de sangue (IgG) por animal" },
] as const satisfies readonly { id: AbaCurativa; label: string; icon: any; title: string }[];

export default function SanidadePage() {
  const [aba, setAba] = useState<AbaSanidade>("curativa");
  const [abaCur, setAbaCur] = useState<AbaCurativa>("curativo");

  const subNavTree: SubNavNode[] = useMemo(() => ABAS_SANIDADE.map((a) => ({
    id: a.id, label: a.label, icon: a.icon,
    children: a.id === "curativa" ? ABAS_CURATIVA.map((c) => ({ id: c.id, label: c.label, icon: c.icon })) : undefined,
  })), []);
  const onSelectSubNav = useCallback((id: string) => {
    if (ABAS_CURATIVA.some((c) => c.id === id)) { setAba("curativa"); setAbaCur(id as AbaCurativa); }
    else setAba(id as AbaSanidade);
  }, []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: aba === "curativa" ? abaCur : aba, onSelect: onSelectSubNav }), [subNavTree, aba, abaCur, onSelectSubNav]));

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Syringe size={22} style={{ color: "var(--dourado)" }} /> Sanidade</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Sanidade curativa e preventiva, mais o controle de BST.</p>
      </div>

      {aba === "curativa" && (
        <>
          {abaCur === "curativo" && <AplicacoesView />}
          {abaCur === "doenca" && <DoencaMotivoView />}
          {abaCur === "bezerras" && <RelatorioBezerrasView />}
        </>
      )}
      {aba === "preventiva" && <CalendarioSanitarioView />}
      {aba === "bst" && <BstView />}
    </div>
  );
}
