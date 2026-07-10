"use client";
import { useEffect, useMemo, useState } from "react";
import { Syringe, AlertTriangle, Filter, Search, CalendarClock, ClipboardList, Baby } from "lucide-react";
import { fetchSanidade, fetchCalendarioSanitario, fetchEventosSanitarios, fetchAnimais, fetchRelatorioBezerras, formatDate } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { SelecaoAnimaisTabela } from "@/components/SelecaoAnimaisTabela";
import { TabBar } from "@/components/ui";

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

/* ───────────────────────── Relatório sanitário de bezerras (colostragem + teste de sangue/IgG) ───────────────────────── */
type LinhaBezerra = {
  numero: string; nome: string | null; sexo: string | null; categoria_abrev: string | null;
  grupo_primario: string | null; data_nasc: string | null; idade_meses: number | null; ativo: boolean;
  tomou_colostro: boolean | null; litros_colostro: number | null; brix_colostro: number | null;
  classe_colostro: "ouro" | "prata" | "bronze" | null; data_colostro: string | null;
  brix_soro: number | null; classe_soro: "sucesso" | "alerta" | "falha" | null; data_teste_sangue: string | null;
};

const LABEL_CLASSE_COLOSTRO: Record<string, { txt: string; cor: string }> = {
  ouro: { txt: "Ouro", cor: "var(--dourado-light)" }, prata: { txt: "Prata", cor: "var(--text-muted)" },
  bronze: { txt: "Bronze", cor: "var(--red)" },
};
const LABEL_CLASSE_SORO: Record<string, { txt: string; cor: string }> = {
  sucesso: { txt: "Sucesso", cor: "var(--green-light)" }, alerta: { txt: "Alerta", cor: "var(--amber)" },
  falha: { txt: "Falha", cor: "var(--red)" },
};

const COLUNAS_BEZERRAS = [
  { header: "Data", key: "data_teste_sangue" }, { header: "Nº", key: "numero" }, { header: "Nome", key: "nome" },
  { header: "Categoria", key: "categoria_abrev" }, { header: "Lote", key: "grupo_primario" }, { header: "Idade (meses)", key: "idade_meses" },
  { header: "Tomou colostro", key: "tomou_colostroFmt" }, { header: "Litros", key: "litros_colostro" },
  { header: "Brix colostro (%)", key: "brix_colostro" }, { header: "Classe colostro", key: "classe_colostroFmt" },
  { header: "Brix soro (%)", key: "brix_soro" }, { header: "Classe soro", key: "classe_soroFmt" },
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
                  <th>Classe colostro</th><th style={{ textAlign: "right" }}>Brix soro</th><th>Classe soro (IgG)</th>
                </tr>
              </thead>
              <tbody>
                {dados.map((l) => {
                  const grave = l.classe_soro === "falha" || l.classe_colostro === "bronze";
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
                      <td style={{ fontSize: "0.78rem", fontWeight: 700, color: l.classe_soro ? LABEL_CLASSE_SORO[l.classe_soro].cor : "var(--text-muted)" }}>
                        {l.classe_soro ? LABEL_CLASSE_SORO[l.classe_soro].txt : "—"}
                      </td>
                    </tr>
                  );
                })}
                {!dados.length && <tr><td colSpan={11} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum animal encontrado com esses filtros.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

type AbaSanidade = "aplicacoes" | "calendario" | "bezerras";
const ABAS_SANIDADE = [
  { id: "aplicacoes", label: "Aplicações", icon: ClipboardList, title: "Medicamentos aplicados no rebanho" },
  { id: "calendario", label: "Calendário sanitário", icon: CalendarClock, title: "Regras e próximas ocorrências de manejo sanitário" },
  { id: "bezerras", label: "Relatório sanitário de bezerras", icon: Baby, title: "Colostragem e teste de sangue (IgG) por animal" },
] as const satisfies readonly { id: AbaSanidade; label: string; icon: any; title: string }[];

export default function SanidadePage() {
  const [aba, setAba] = useState<AbaSanidade>("aplicacoes");

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Syringe size={22} style={{ color: "var(--dourado)" }} /> Sanidade</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Medicamentos aplicados e calendário sanitário — filtre por categoria, data, produto, animal ou evento.</p>
      </div>

      <TabBar<AbaSanidade> abas={ABAS_SANIDADE} ativa={aba} onChange={setAba} />

      {aba === "aplicacoes" && <AplicacoesView />}
      {aba === "calendario" && <CalendarioSanitarioView />}
      {aba === "bezerras" && <RelatorioBezerrasView />}
    </div>
  );
}
