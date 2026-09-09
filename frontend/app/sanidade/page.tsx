"use client";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Syringe, AlertTriangle, Filter, Search, CalendarClock, ClipboardList, Pencil, Trash2, Check, X, Shield, HeartPulse, Activity, ChevronDown, ChevronRight, ListChecks, Percent, Route, History, FlaskConical, BookOpen } from "lucide-react";
import {
  fetchSanidade, fetchCalendarioSanitario, fetchEventosSanitarios, fetchLancamentosProtocolo, editarAplicacaoSanidade, confirmarExclusao, excluirCalendarioSanitario, ehAdmin, formatDate, today, fetchTaxaCura, type CasoTaxaCura, marcarCuraAplicacao, marcarCuraProtocolo,
  fetchCronogramasSanitarios, criarCronogramaSanitario,
  fetchCalendarioVisao, type JanelaCalendario, type JanelaCalendarioEvento,
  fetchEventosVidaVocabulario, fetchRelatorioEventosVida,
  fetchResultadosExame, atualizarResultadoExame, type ExameResultado,
  fetchMedicamentos,
  fetchRastreabilidadeSanitaria, type LinhaRastreabilidadeSanitaria,
} from "@/lib/api";
import { VIAS_APLICACAO } from "@/lib/constants";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { MultiFiltro, TabBar, Indicador, SecaoRecolhivel } from "@/components/ui";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import type { AnimalRow } from "@/components/AnimalModal";
import { HistoricoPreventivoView } from "@/components/sanidade/HistoricoPreventivoView";
import CatalogoFarmaciaConsulta from "@/components/sanidade/CatalogoFarmaciaConsulta";
import RemediosPorDoenca from "@/components/RemediosPorDoenca";
import { casaBusca } from "@/lib/busca";

const COLUNAS_SANIDADE = [
  { header: "Data", key: "data" }, { header: "Animal", key: "numero" }, { header: "Produto", key: "produto" },
  { header: "Categoria", key: "categoria" }, { header: "Dose", key: "dose" }, { header: "Atividade", key: "atividade" },
];

const COLUNAS_CALENDARIO = [
  { header: "Evento", key: "evento_sanitario_nome" }, { header: "Tipo", key: "tipoFmt" }, { header: "Categoria alvo", key: "categoria_alvo" },
  { header: "Doença", key: "doenca_nome" }, { header: "Produto", key: "produto" }, { header: "Dosagem", key: "dosagem" },
  { header: "Responsável", key: "responsavel" },
  { header: "Frequência", key: "frequenciaFmt" }, { header: "Próxima ocorrência", key: "proxima_ocorrencia_fmt" },
];

type RegraCalendario = {
  id: number; evento_sanitario_id: number; evento_sanitario_nome: string; categoria_alvo: string | null;
  doenca_nome: string | null; produto: string | null; principio_ativo_nome: string | null; dosagem: string | null;
  responsavel: string | null; veterinario: string | null; categoria_preventiva: string | null;
  servico_financeiro: string | null; usa_cronograma?: boolean;
  frequencia_valor: number; frequencia_unidade: string; data_evento: string; proxima_ocorrencia: string; observacao: string | null;
};

// vacina | exame | tratamento | legado (sem categoria — não é mais possível
// cadastrar assim, só sobra em eventos antigos) | todos.
const TIPOS_REGRA_FILTRO = [
  { v: "todos", l: "Todos" }, { v: "vacina", l: "Vacina" }, { v: "exame", l: "Exame" },
  { v: "tratamento", l: "Tratamento" }, { v: "legado", l: "Legado (sem categoria)" },
] as const;
function tipoRegra(r: { categoria_preventiva: string | null }): "vacina" | "exame" | "tratamento" | "legado" {
  if (r.categoria_preventiva === "exame") return "exame";
  if (r.categoria_preventiva === "vacina") return "vacina";
  if (r.categoria_preventiva === "tratamento") return "tratamento";
  return "legado";
}
const ROTULO_TIPO_REGRA: Record<ReturnType<typeof tipoRegra>, string> = {
  vacina: "Vacina", exame: "Exame", tratamento: "Tratamento", legado: "Legado (sem categoria)",
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

type LinhaEventoVida = {
  numero_matriz: string; nome: string | null; grupo_primario: string | null; categoria: string | null;
  data_evento: string; dias_restantes: number;
  // Presentes só quando o evento sanitário tem janela de aplicação cadastrada
  // (janela_de/janela_ate) — ver rotuloSituacaoJanela/corSituacaoJanela.
  situacao_janela?: "ainda_nao" | "na_janela" | "fora_da_janela";
  janela_inicio?: string; janela_fim?: string; dias_para_fechar_janela?: number;
  acao_fora_janela?: "sair" | "manter" | "notificar" | null;
};
const ROTULO_SITUACAO_JANELA: Record<string, string> = { ainda_nao: "Ainda não entrou", na_janela: "Na janela", fora_da_janela: "Fora da janela" };
const COR_SITUACAO_JANELA: Record<string, string> = { ainda_nao: "var(--text-muted)", na_janela: "var(--dourado-light)", fora_da_janela: "var(--red)" };
const ACAO_FORA_JANELA_LABEL_CURTO: Record<string, string> = { sair: "saiu", manter: "mantido pendente", notificar: "urgência" };

/**
 * Relatório de mudança de categoria/eventos de vida — "quais animais entrarão
 * em determinado calendário sanitário" na próxima aplicação, escolhendo um
 * evento sanitário já cadastrado por evento (herda o gatilho) ou um evento de
 * vida avulso (exploração livre, sem precisar cadastrar antes).
 */
function RelatorioEventosVidaView({
  eventoSanitarioIdInicial, dataIniInicial, dataFimInicial,
}: { eventoSanitarioIdInicial?: number; dataIniInicial?: string; dataFimInicial?: string } = {}) {
  const [eventos, setEventos] = useState<EventoPrev[]>([]);
  const [gatilhosVida, setGatilhosVida] = useState<{ gatilho: string; rotulo: string }[]>([]);
  const [eventoSanitarioId, setEventoSanitarioId] = useState(eventoSanitarioIdInicial ? String(eventoSanitarioIdInicial) : "");
  const [gatilho, setGatilho] = useState("");
  const [ini, setIni] = useState(dataIniInicial || "");
  const [fim, setFim] = useState(dataFimInicial || "");
  const [resultado, setResultado] = useState<{ rotulo: string; evento_sanitario_nome: string | null; animais: LinhaEventoVida[] } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    fetchEventosSanitarios().then((d: any[]) => setEventos(d.filter((e) => e.tipo_agendamento === "evento" && e.gatilho))).catch(() => {});
    fetchEventosVidaVocabulario().then(setGatilhosVida).catch(() => {});
  }, []);

  // Assim que a lista de eventos/gatilhos chega, escolhe um padrão (o 1º evento
  // cadastrado por evento, senão o 1º evento de vida) para já mostrar o
  // relatório abaixo dos filtros — sem precisar clicar em "Buscar" antes.
  useEffect(() => {
    if (eventoSanitarioId || gatilho) return;
    if (eventos.length) setEventoSanitarioId(String(eventos[0].id));
    else if (gatilhosVida.length) setGatilho(gatilhosVida[0].gatilho);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventos, gatilhosVida]);

  const buscar = useCallback(async () => {
    if (!eventoSanitarioId && !gatilho) { setErro("Escolha um evento sanitário cadastrado ou um evento de vida."); return; }
    setErro(null); setCarregando(true);
    try {
      const r = await fetchRelatorioEventosVida({
        eventoSanitarioId: eventoSanitarioId ? Number(eventoSanitarioId) : undefined,
        gatilho: eventoSanitarioId ? undefined : gatilho,
        dataInicio: ini || undefined, dataFim: fim || undefined,
      });
      setResultado(r);
    } catch (e: any) {
      setErro(e.message); setResultado(null);
    } finally {
      setCarregando(false);
    }
  }, [eventoSanitarioId, gatilho, ini, fim]);

  useEffect(() => { if (eventoSanitarioId || gatilho) buscar(); }, [eventoSanitarioId, gatilho, ini, fim, buscar]);

  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(resultado?.animais || []);
  const temJanela = !!(resultado?.animais || []).some((a) => a.situacao_janela);
  const linhasExport = (resultado?.animais || []).map((a) => ({
    ...a, dias_restantes_fmt: a.dias_restantes < 0 ? `${Math.abs(a.dias_restantes)}d atrás` : `em ${a.dias_restantes}d`,
    data_evento_fmt: formatDate(a.data_evento),
    situacao_janela_fmt: a.situacao_janela ? ROTULO_SITUACAO_JANELA[a.situacao_janela] : "",
  }));

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <>
      <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginBottom: "0.8rem" }}>
        Identifica quais animais entrarão em determinado calendário sanitário na próxima aplicação, com base no evento de
        vida (mudança de categoria) escolhido — desmama, aptidão, inseminação, secagem, parto etc.
      </p>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Evento sanitário cadastrado (por evento)</label>
            <select style={selStyle} value={eventoSanitarioId} onChange={(e) => { setEventoSanitarioId(e.target.value); if (e.target.value) setGatilho(""); }}>
              <option value="">— escolher pelo evento de vida abaixo —</option>
              {eventos.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ou evento de vida diretamente</label>
            <select style={selStyle} value={gatilho} disabled={!!eventoSanitarioId} onChange={(e) => setGatilho(e.target.value)}>
              <option value="">Selecione…</option>
              {gatilhosVida.map((g) => <option key={g.gatilho} value={g.gatilho}>{g.rotulo}</option>)}
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Data do evento — de</label>
            <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Data do evento — até</label>
            <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
        </div>
        <button className="btn-primary mt-3" onClick={buscar} disabled={carregando}>{carregando ? "Buscando…" : "Buscar"}</button>
      </div>

      {erro && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{erro}</span></div>}

      {resultado && (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span>{resultado.evento_sanitario_nome || resultado.rotulo} — {resultado.animais.length} animal(is) — clique no cabeçalho para ordenar</span>
            <ExportarBotoes
              titulo="Relatório de eventos de vida" nomeArquivoBase="relatorio_eventos_vida"
              colunas={[
                { header: "Nº", key: "numero_matriz" }, { header: "Nome", key: "nome" }, { header: "Lote", key: "grupo_primario" },
                { header: "Categoria", key: "categoria" }, { header: "Data do evento", key: "data_evento_fmt" }, { header: "Dias restantes", key: "dias_restantes_fmt" },
                ...(temJanela ? [{ header: "Situação da janela", key: "situacao_janela_fmt" }] : []),
              ]}
              linhas={linhasExport}
            />
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "480px" }}>
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Nº" campo="numero_matriz" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Lote" campo="grupo_primario" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Categoria" campo="categoria" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Data do evento" campo="data_evento" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Dias restantes" campo="dias_restantes" coluna={coluna} dir={dir} ordenar={ordenar} />
                {temJanela && <ThOrdenavel label="Situação da janela" campo="situacao_janela" coluna={coluna} dir={dir} ordenar={ordenar} />}
              </tr></thead>
              <tbody>
                {linhasOrdenadas.map((a) => (
                  <tr key={a.numero_matriz} onClick={() => { window.location.href = `/rebanho?aba=ficha&numero=${encodeURIComponent(a.numero_matriz)}`; }} style={{ cursor: "pointer" }}>
                    <td style={{ fontWeight: 700 }}>{a.numero_matriz}</td>
                    <td style={{ fontSize: "0.78rem" }}>{a.nome || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{a.grupo_primario || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{a.categoria || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(a.data_evento)}</td>
                    <td style={{ fontSize: "0.78rem", textAlign: "right", fontWeight: 600, color: a.dias_restantes < 0 ? "var(--red)" : "var(--dourado-light)" }}>
                      {a.dias_restantes < 0 ? `${Math.abs(a.dias_restantes)}d atrás` : `em ${a.dias_restantes}d`}
                    </td>
                    {temJanela && (
                      <td style={{ fontSize: "0.78rem" }}>
                        {a.situacao_janela ? (
                          <span style={{ fontWeight: 700, color: COR_SITUACAO_JANELA[a.situacao_janela] }}>
                            {ROTULO_SITUACAO_JANELA[a.situacao_janela]}
                            {a.situacao_janela === "na_janela" && a.dias_para_fechar_janela != null && ` — fecha em ${a.dias_para_fechar_janela}d`}
                            {a.situacao_janela === "fora_da_janela" && a.acao_fora_janela && ` (${ACAO_FORA_JANELA_LABEL_CURTO[a.acao_fora_janela] || a.acao_fora_janela})`}
                          </span>
                        ) : "—"}
                      </td>
                    )}
                  </tr>
                ))}
                {!resultado.animais.length && <tr><td colSpan={temJanela ? 7 : 6} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum animal encontrado.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

const LABEL_RESULTADO_EXAME: Record<string, string> = { positivo: "Positivo", negativo: "Negativo", indefinido: "Indefinido" };
const COR_RESULTADO_EXAME: Record<string, string> = { positivo: "var(--red)", negativo: "var(--green-light)", indefinido: "var(--amber)" };

/**
 * Relatório de resultados de exames preventivos (tuberculose, brucelose etc.)
 * lançados em Lançamentos > Sanitário > Preventivo — diagnóstico
 * (positivo/negativo/indefinido) ou valor numérico + banda. Editar/excluir
 * seguem o mesmo fluxo auditado usado no resto de Sanidade: qualquer usuário
 * pode pedir a exclusão, admin exclui na hora (ver excluir() abaixo).
 */
function RelatorioResultadosExameView({ eventos }: { eventos: EventoPrev[] }) {
  const admin = ehAdmin();
  const [eventoId, setEventoId] = useState("");
  const [resultadoFiltro, setResultadoFiltro] = useState("");
  const [dataDe, setDataDe] = useState("");
  const [dataAte, setDataAte] = useState("");
  const [linhas, setLinhas] = useState<ExameResultado[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [editVals, setEditVals] = useState({ data: "", resultado: "", valorNumerico: "", veterinario: "", observacao: "" });
  const [ocupado, setOcupado] = useState<number | null>(null);

  const eventosExame = useMemo(() => eventos.filter((e) => e.categoria_preventiva === "exame"), [eventos]);

  // Agrupado em 2 níveis pra navegação por clique: 1º nível por data (card),
  // 2º nível por tipo de exame dentro da data (sub-card) — a listagem de
  // diagnóstico dos animais só aparece dentro do sub-card, ao expandi-lo.
  const porData = useMemo(() => {
    const mapa = new Map<string, ExameResultado[]>();
    for (const l of linhas ?? []) {
      const arr = mapa.get(l.data_exame) ?? [];
      arr.push(l);
      mapa.set(l.data_exame, arr);
    }
    return Array.from(mapa.entries()).sort((a, b) => b[0].localeCompare(a[0]));
  }, [linhas]);

  const carregar = () =>
    fetchResultadosExame({
      eventoSanitarioId: eventoId ? Number(eventoId) : undefined,
      resultado: resultadoFiltro || undefined,
      dataDe: dataDe || undefined,
      dataAte: dataAte || undefined,
    }).then(setLinhas).catch((e) => setErro(e.message));

  useEffect(() => { carregar(); }, [eventoId, resultadoFiltro, dataDe, dataAte]);

  const iniciarEdicao = (l: ExameResultado) => {
    setEditId(l.id);
    setEditVals({
      data: l.data_exame ?? "", resultado: l.resultado ?? "",
      valorNumerico: l.valor_numerico == null ? "" : String(l.valor_numerico),
      veterinario: l.veterinario ?? "", observacao: l.observacao ?? "",
    });
    setErro(null);
  };

  const salvarEdicao = async (l: ExameResultado) => {
    setOcupado(l.id); setErro(null);
    try {
      await atualizarResultadoExame(l.id, {
        data_exame: editVals.data || undefined,
        resultado: (editVals.resultado || null) as ExameResultado["resultado"],
        valor_numerico: editVals.valorNumerico.trim() === "" ? null : Number(editVals.valorNumerico),
        veterinario: editVals.veterinario.trim() || null,
        observacao: editVals.observacao.trim() || null,
      });
      setEditId(null);
      await carregar();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(null); }
  };

  // Mesmo fluxo central e auditado de exclusão (POST /exclusoes/confirmar)
  // usado pelas outras telas de Sanidade — admin exclui na hora (e a marcação
  // "A descartar" causada por um diagnóstico positivo é desfeita
  // automaticamente, ver rules/exclusao_tipos/sanidade.py), operador vira uma
  // solicitação pendente de aprovação.
  const excluir = async (l: ExameResultado) => {
    const msg = admin
      ? `Excluir o exame de ${l.numero_matriz} em ${formatDate(l.data_exame)}? Isso não pode ser desfeito.`
      : `Solicitar a exclusão do exame de ${l.numero_matriz} em ${formatDate(l.data_exame)}? Um administrador precisa aprovar antes de ser excluído de fato.`;
    if (!window.confirm(msg)) return;
    setOcupado(l.id); setErro(null); setAvisoExclusao(null);
    try {
      const r = await confirmarExclusao("exame_resultado", String(l.id));
      if (r.status === "excluido") {
        await carregar();
      } else {
        setAvisoExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(null); }
  };

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center gap-2"><Shield size={16} /> Resultados de exames</div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginBottom: "0.8rem" }}>
        Diagnóstico (positivo/negativo/indefinido) ou valor numérico lançado em cada exame preventivo — positivo marca
        automaticamente "A descartar"; negativo é informativo (liberada); indefinido marca para repetir o exame.
      </p>
      {avisoExclusao && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{avisoExclusao}</p>}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Exame</label>
          <select style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
            value={eventoId} onChange={(e) => setEventoId(e.target.value)}>
            <option value="">Todos</option>
            {eventosExame.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
          </select></div>
        <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Resultado</label>
          <select style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
            value={resultadoFiltro} onChange={(e) => setResultadoFiltro(e.target.value)}>
            <option value="">Todos</option>
            <option value="positivo">Positivo</option>
            <option value="negativo">Negativo</option>
            <option value="indefinido">Indefinido</option>
          </select></div>
        <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
          <input type="date" style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
            value={dataDe} onChange={(e) => setDataDe(e.target.value)} /></div>
        <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
          <input type="date" style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
            value={dataAte} onChange={(e) => setDataAte(e.target.value)} /></div>
      </div>

      {erro && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {erro}.</span></div>}
      {!linhas && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {linhas && !porData.length && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum resultado no filtro.</p>
      )}

      {linhas && !!porData.length && (
        <div className="space-y-2">
          {porData.map(([data, itensData]) => (
            <SecaoRecolhivel
              key={data}
              titulo={formatDate(data)}
              icon={CalendarClock}
              badge={<span style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700 }}>{itensData.length} exame(s)</span>}
            >
              <div className="space-y-2">
                {agruparPorTipoExame(itensData).map(([tipo, itensTipo]) => (
                  <SecaoRecolhivel
                    key={tipo}
                    titulo={`${formatDate(data)} — ${tipo.toUpperCase()}`}
                    icon={FlaskConical}
                    badge={<span style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700 }}>{itensTipo.length} animal(is)</span>}
                  >
                    <div className="overflow-x-auto">
                      <table className="fazenda-table">
                        <thead><tr><th>Nº</th><th>Resultado</th><th>Veterinário</th><th>Ações</th></tr></thead>
                        <tbody>
                          {itensTipo.map((l) => (
                            <Fragment key={l.id}>
                              <tr>
                                <td style={{ fontWeight: 700 }}>{l.numero_matriz}</td>
                                <td style={{ fontSize: "0.78rem" }}>
                                  {l.resultado ? (
                                    <span style={{ fontWeight: 700, color: COR_RESULTADO_EXAME[l.resultado] }}>{LABEL_RESULTADO_EXAME[l.resultado]}</span>
                                  ) : l.valor_numerico != null ? (
                                    <>{l.valor_numerico}{l.banda ? ` (${l.banda === "abaixo" ? "abaixo da faixa" : l.banda === "acima" ? "acima da faixa" : "dentro da faixa"})` : ""}</>
                                  ) : "—"}
                                </td>
                                <td style={{ fontSize: "0.78rem" }}>{l.veterinario || "—"}</td>
                                <td>
                                  <div className="flex items-center gap-1">
                                    <button className="btn-ghost" style={{ padding: "0.2rem 0.4rem" }} title="Editar"
                                      disabled={ocupado === l.id} onClick={() => (editId === l.id ? setEditId(null) : iniciarEdicao(l))}>
                                      <Pencil size={13} />
                                    </button>
                                    <button className="btn-ghost" style={{ padding: "0.2rem 0.4rem", color: "var(--red)" }} title="Excluir"
                                      disabled={ocupado === l.id} onClick={() => excluir(l)}>
                                      <Trash2 size={13} />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                              {editId === l.id && (
                                <tr>
                                  <td colSpan={4}>
                                    <div className="grid grid-cols-2 md:grid-cols-5 gap-2 items-end" style={{ padding: "0.5rem 0" }}>
                                      <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Data</label>
                                        <input type="date" style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.4rem", fontSize: "0.78rem", width: "100%" }}
                                          value={editVals.data} onChange={(e) => setEditVals((v) => ({ ...v, data: e.target.value }))} /></div>
                                      <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Resultado</label>
                                        <select style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.4rem", fontSize: "0.78rem", width: "100%" }}
                                          value={editVals.resultado} onChange={(e) => setEditVals((v) => ({ ...v, resultado: e.target.value }))}>
                                          <option value="">—</option>
                                          <option value="positivo">Positivo</option>
                                          <option value="negativo">Negativo</option>
                                          <option value="indefinido">Indefinido</option>
                                        </select></div>
                                      <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Valor numérico</label>
                                        <input type="number" style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.4rem", fontSize: "0.78rem", width: "100%" }}
                                          value={editVals.valorNumerico} onChange={(e) => setEditVals((v) => ({ ...v, valorNumerico: e.target.value }))} /></div>
                                      <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Veterinário</label>
                                        <input style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.4rem", fontSize: "0.78rem", width: "100%" }}
                                          value={editVals.veterinario} onChange={(e) => setEditVals((v) => ({ ...v, veterinario: e.target.value }))} /></div>
                                      <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Observação</label>
                                        <input style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.4rem", fontSize: "0.78rem", width: "100%" }}
                                          value={editVals.observacao} onChange={(e) => setEditVals((v) => ({ ...v, observacao: e.target.value }))} /></div>
                                    </div>
                                    {erro && <p style={{ color: "var(--red)", fontSize: "0.76rem", marginBottom: "0.4rem" }}>{erro}</p>}
                                    <div className="flex items-center gap-2" style={{ paddingBottom: "0.5rem" }}>
                                      <button className="btn-primary" style={{ fontSize: "0.74rem" }} onClick={() => salvarEdicao(l)} disabled={ocupado === l.id}>
                                        <Check size={13} /> {ocupado === l.id ? "Salvando…" : "Salvar"}
                                      </button>
                                      <button className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={() => setEditId(null)}>
                                        <X size={13} /> Cancelar
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </SecaoRecolhivel>
                ))}
              </div>
            </SecaoRecolhivel>
          ))}
        </div>
      )}
    </div>
  );
}

// Agrupa os resultados de uma mesma data por tipo de exame (evento
// sanitário vinculado) — usado pelo 2º nível de RelatorioResultadosExameView.
function agruparPorTipoExame(itens: ExameResultado[]): [string, ExameResultado[]][] {
  const mapa = new Map<string, ExameResultado[]>();
  for (const l of itens) {
    const chave = l.evento_sanitario_nome || "Sem exame vinculado";
    const arr = mapa.get(chave) ?? [];
    arr.push(l);
    mapa.set(chave, arr);
  }
  return Array.from(mapa.entries()).sort((a, b) => a[0].localeCompare(b[0]));
}

const COR_CATEGORIA_PREVENTIVA: Record<string, string> = {
  vacina: "var(--blue)", exame: "#7A5C99", tratamento: "var(--amber)",
};

function maisDias(iso: string, dias: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + dias);
  return d.toISOString().split("T")[0];
}
function primeiroDiaMes(d: Date): string {
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().split("T")[0];
}
function ultimoDiaMes(d: Date): string {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0).toISOString().split("T")[0];
}

/**
 * Card CALENDÁRIO — visão em Lista ou Mês das próximas ocorrências das regras
 * (vacina/exame), agrupadas quando caem perto no tempo (parâmetro "janela de
 * agrupamento"), com estimativa de animais e sinalização de "vale chamar o
 * veterinário" quando a soma bate o mínimo configurado.
 */
function CalendarioVisualView({ onAbrirCronograma }: { onAbrirCronograma: (calendarioSanitarioId: number) => void }) {
  const [visualizacao, setVisualizacao] = useState<"lista" | "mes">("lista");
  const [mesAtual, setMesAtual] = useState(() => new Date());
  const [dados, setDados] = useState<{ janelas: JanelaCalendario[]; min_animais_agrupamento: number; janela_agrupamento_dias: number } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [diaSelecionado, setDiaSelecionado] = useState<string | null>(null);
  const [drillDown, setDrillDown] = useState<{ eventoId: number; ini: string; fim: string } | null>(null);

  useEffect(() => {
    const hoje = today();
    const filtro = visualizacao === "lista"
      ? { dataInicio: hoje, dataFim: maisDias(hoje, 180) }
      : { dataInicio: primeiroDiaMes(mesAtual), dataFim: ultimoDiaMes(mesAtual) };
    fetchCalendarioVisao(filtro).then(setDados).catch((e) => setErro(e.message));
  }, [visualizacao, mesAtual]);

  const eventosPlanos = useMemo(
    () => (dados?.janelas || []).flatMap((j) => j.eventos.map((e) => ({ ...e, janela: j }))),
    [dados]
  );

  const linhaEvento = (o: JanelaCalendarioEvento & { janela: JanelaCalendario }) => {
    const podeVerAnimais = !o.usa_cronograma && o.animais !== null && !o.estimativa;
    return (
      <div key={`${o.calendario_sanitario_id}-${o.data}`} style={{ padding: "0.55rem 0", borderTop: "1px solid var(--border)" }}>
        <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.4rem" }}>
          <div>
            <span style={{ fontWeight: 700 }}>{o.evento_sanitario_nome}</span>
            <span style={{ marginLeft: 8, fontSize: "0.68rem", color: COR_CATEGORIA_PREVENTIVA[o.categoria_preventiva || ""] || "var(--text-muted)", fontWeight: 700 }}>
              {o.categoria_preventiva ? ROTULO_TIPO_REGRA[o.categoria_preventiva as keyof typeof ROTULO_TIPO_REGRA] || o.categoria_preventiva : ""}
            </span>
            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              {o.categoria_alvo || "Todos os animais"} · {formatDate(o.data)}
            </div>
          </div>
          <div style={{ textAlign: "right", fontSize: "0.78rem" }}>
            <div>
              {o.animais == null ? "sem estimativa" : <>{o.estimativa ? "~" : ""}{o.animais} animal(is){o.estimativa && <span style={{ color: "var(--text-muted)" }}> (última aplicação)</span>}</>}
            </div>
            <div className="flex items-center gap-2" style={{ justifyContent: "flex-end", marginTop: "0.2rem" }}>
              {o.usa_cronograma && o.cronograma && (
                <button className="btn-secondary" style={{ fontSize: "0.7rem" }} onClick={() => onAbrirCronograma(o.calendario_sanitario_id)}>
                  Cronograma: {STATUS_CRONOGRAMA_LABEL[o.cronograma.status] || o.cronograma.status}
                </button>
              )}
              {podeVerAnimais && (
                <button className="btn-secondary" style={{ fontSize: "0.7rem" }} onClick={() => setDrillDown({ eventoId: o.evento_sanitario_id, ini: o.janela.data_inicio, fim: o.janela.data_fim })}>
                  Ver animais
                </button>
              )}
              {o.servico_financeiro && (
                <a className="btn-secondary" style={{ fontSize: "0.7rem", color: "var(--green-light)" }}
                  href={`/lancamentos?ir=financeiro_despesa&servico=${encodeURIComponent(o.servico_financeiro)}`}>
                  $ Financeiro
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  const diasComEvento = useMemo(() => {
    const mapa = new Map<string, (JanelaCalendarioEvento & { janela: JanelaCalendario })[]>();
    for (const o of eventosPlanos) {
      if (!mapa.has(o.data)) mapa.set(o.data, []);
      mapa.get(o.data)!.push(o);
    }
    return mapa;
  }, [eventosPlanos]);

  const gradeMes = useMemo(() => {
    const ano = mesAtual.getFullYear(), mes = mesAtual.getMonth();
    const primeiro = new Date(ano, mes, 1);
    const dias: (string | null)[] = Array(primeiro.getDay()).fill(null);
    const totalDias = new Date(ano, mes + 1, 0).getDate();
    for (let d = 1; d <= totalDias; d++) dias.push(new Date(ano, mes, d).toISOString().split("T")[0]);
    return dias;
  }, [mesAtual]);

  return (
    <div>
      <div className="flex items-center justify-between mb-3" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", margin: 0 }}>
          Próximas vacinas e exames, agrupados quando caem perto no tempo — mínimo de {dados?.min_animais_agrupamento ?? "…"} animais e janela de {dados?.janela_agrupamento_dias ?? "…"} dias (ajustável em Configurações › Parâmetros).
        </p>
        <div className="flex items-center gap-1">
          <button className={visualizacao === "lista" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.75rem" }} onClick={() => setVisualizacao("lista")}>Lista</button>
          <button className={visualizacao === "mes" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.75rem" }} onClick={() => setVisualizacao("mes")}>Mês</button>
        </div>
      </div>

      {erro && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{erro}</span></div>}
      {!dados && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && visualizacao === "lista" && (
        dados.janelas.length === 0
          ? <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma ocorrência nos próximos 180 dias.</p>
          : dados.janelas.map((j) => (
            <div key={j.data_inicio + j.data_fim} className="card mb-3">
              <div className="flex items-center justify-between mb-1">
                <span style={{ fontWeight: 700 }}>
                  {formatDate(j.data_inicio)}{j.data_fim !== j.data_inicio ? ` – ${formatDate(j.data_fim)}` : ""}
                </span>
                <span style={{
                  fontSize: "0.72rem", fontWeight: 700, padding: "0.2rem 0.55rem", borderRadius: 6,
                  color: j.sugerir_veterinario ? "var(--green-light)" : "var(--text-muted)",
                  background: j.sugerir_veterinario ? "rgba(76,175,128,0.12)" : "transparent",
                  border: j.sugerir_veterinario ? "none" : "1px solid var(--border)",
                }}>
                  {j.animais_total} animal(is){j.tem_estimativa ? " (estimado)" : ""} {j.sugerir_veterinario ? "· vale chamar o veterinário" : ""}
                </span>
              </div>
              {j.eventos.map((o) => linhaEvento({ ...o, janela: j }))}
            </div>
          ))
      )}

      {dados && visualizacao === "mes" && (
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <button className="btn-secondary" style={{ fontSize: "0.78rem" }} onClick={() => setMesAtual((d) => new Date(d.getFullYear(), d.getMonth() - 1, 1))}>‹ Anterior</button>
            <span style={{ fontWeight: 700 }}>{mesAtual.toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}</span>
            <button className="btn-secondary" style={{ fontSize: "0.78rem" }} onClick={() => setMesAtual((d) => new Date(d.getFullYear(), d.getMonth() + 1, 1))}>Próximo ›</button>
          </div>
          <div className="grid grid-cols-7 gap-1">
            {["D", "S", "T", "Q", "Q", "S", "S"].map((d, i) => (
              <div key={i} style={{ fontSize: "0.68rem", color: "var(--text-muted)", textAlign: "center" }}>{d}</div>
            ))}
            {gradeMes.map((iso, i) => {
              if (!iso) return <div key={i} />;
              const eventosDia = diasComEvento.get(iso) || [];
              const algumSugereVet = eventosDia.some((o) => o.janela.sugerir_veterinario);
              return (
                <button
                  key={iso}
                  onClick={() => eventosDia.length && setDiaSelecionado(iso)}
                  style={{
                    aspectRatio: "1", borderRadius: 8, fontSize: "0.72rem", padding: "0.3rem",
                    background: "var(--surface-2)", color: "var(--text)", textAlign: "left", cursor: eventosDia.length ? "pointer" : "default",
                    border: "1px solid " + (algumSugereVet ? "var(--dourado)" : "var(--border)"),
                  }}
                >
                  <div style={{ fontWeight: 700 }}>{Number(iso.split("-")[2])}</div>
                  {eventosDia.length > 0 && (
                    <div className="flex" style={{ gap: 2, flexWrap: "wrap", marginTop: 2 }}>
                      {eventosDia.slice(0, 4).map((o, idx) => (
                        <span key={idx} style={{ width: 6, height: 6, borderRadius: "50%", background: COR_CATEGORIA_PREVENTIVA[o.categoria_preventiva || ""] || "var(--text-muted)" }} />
                      ))}
                    </div>
                  )}
                </button>
              );
            })}
          </div>

          {diaSelecionado && (
            <div className="mt-4" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }}>
              <div className="flex items-center justify-between mb-1">
                <span style={{ fontWeight: 700 }}>{formatDate(diaSelecionado)}</span>
                <button className="btn-secondary" style={{ fontSize: "0.72rem" }} onClick={() => setDiaSelecionado(null)}>Fechar</button>
              </div>
              {(diasComEvento.get(diaSelecionado) || []).map((o) => linhaEvento(o))}
            </div>
          )}
        </div>
      )}

      {drillDown && (
        <div className="card mt-3">
          <div className="flex items-center justify-between mb-2">
            <span style={{ fontWeight: 700 }}>Quais animais entram nesta janela</span>
            <button className="btn-secondary" style={{ fontSize: "0.72rem" }} onClick={() => setDrillDown(null)}>Fechar</button>
          </div>
          <RelatorioEventosVidaView eventoSanitarioIdInicial={drillDown.eventoId} dataIniInicial={drillDown.ini} dataFimInicial={drillDown.fim} />
        </div>
      )}
    </div>
  );
}

// Exportado — reaproveitado também em Central de Protocolos > Acompanhamento
// > Sanitário > Preventivo (ver app/protocolos/page.tsx), mesmo componente,
// mesmos endpoints: não há dado nem lógica duplicada entre as duas telas.
export function CalendarioSanitarioView({ modoInicial }: { modoInicial?: "calendario" | "cronogramas" } = {}) {
  const [modo, setModo] = useState<"calendario" | "regras" | "cronogramas" | "exames">(modoInicial || "calendario");
  const [cronogramaFiltroCalendarioId, setCronogramaFiltroCalendarioId] = useState<number | null>(null);
  const [regras, setRegras] = useState<RegraCalendario[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [eventos, setEventos] = useState<EventoPrev[]>([]);
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [eventoId, setEventoId] = useState("");
  const [tipoFiltro, setTipoFiltro] = useState<"todos" | "vacina" | "exame" | "tratamento" | "legado">("todos");
  const [recarregar, setRecarregar] = useState(0);
  const admin = ehAdmin();

  useEffect(() => { fetchEventosSanitarios().then(setEventos).catch(() => {}); }, []);
  useEffect(() => {
    fetchCalendarioSanitario({ dataInicio: ini || undefined, dataFim: fim || undefined, eventoSanitarioId: eventoId ? Number(eventoId) : undefined })
      .then(setRegras).catch((e) => setError(e.message));
  }, [ini, fim, eventoId, recarregar]);

  const regrasFiltradas = useMemo(
    () => (regras || []).filter((r) => tipoFiltro === "todos" || tipoRegra(r) === tipoFiltro),
    [regras, tipoFiltro]
  );
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(regrasFiltradas);

  const linhasExport = regrasFiltradas.map((r) => ({
    ...r, tipoFmt: ROTULO_TIPO_REGRA[tipoRegra(r)],
    frequenciaFmt: `a cada ${r.frequencia_valor} ${LABEL_FREQ[r.frequencia_unidade]}`,
    proxima_ocorrencia_fmt: formatDate(r.proxima_ocorrencia),
  }));

  const excluir = async (r: RegraCalendario) => {
    if (!window.confirm(`Excluir a regra "${r.evento_sanitario_nome}" de ${formatDate(r.data_evento)}?`)) return;
    try { await excluirCalendarioSanitario(r.id); setRecarregar((n) => n + 1); }
    catch (e: any) { setError(e.message); }
  };
  // Serviço explícito cadastrado no evento (vale para vacina, exame ou
  // tratamento) tem prioridade; sem ele, só o exame ainda tem um "chute" por
  // nome (compatibilidade com regras antigas que nunca configuraram o campo).
  const servicoFinanceiro = (r: RegraCalendario) => r.servico_financeiro || (tipoRegra(r) === "exame" ? servicoDoExame(r.evento_sanitario_nome) : null);
  const lancarFinanceiro = (r: RegraCalendario) => {
    const servico = servicoFinanceiro(r);
    if (!servico) return;
    window.location.href = `/lancamentos?ir=financeiro_despesa&servico=${encodeURIComponent(servico)}`;
  };

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <>
      <div style={{ marginBottom: "0.75rem" }}>
        <h2 className="text-lg font-bold flex items-center gap-2"><Shield size={18} style={{ color: "var(--dourado)" }} /> Preventivo (calendário sanitário)</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Regras e próximas ocorrências de manejo preventivo (vacinas, exames e tratamentos). Para lançar um preventivo, use Lançamentos › Sanitário › Preventiva.</p>
      </div>

      <TabBar
        abas={[
          { id: "calendario", label: "Calendário", title: "Próximas vacinas e exames, em lista ou por mês, com sugestão de agrupamento" },
          { id: "regras", label: "Regras cadastradas", title: "Regras recorrentes já cadastradas" },
          { id: "cronogramas", label: "Cronogramas", title: "Acompanhamento das regras usa_cronograma: animais na lista de espera e decisão de execução" },
          { id: "exames", label: "Resultados de exames", title: "Diagnóstico/valor lançado em cada exame preventivo" },
        ] as const}
        ativa={modo}
        onChange={(id) => { setModo(id); if (id !== "cronogramas") setCronogramaFiltroCalendarioId(null); }}
      />

      {modo === "calendario" ? (
        <CalendarioVisualView onAbrirCronograma={(id) => { setCronogramaFiltroCalendarioId(id); setModo("cronogramas"); }} />
      ) : modo === "cronogramas" ? (
        <CronogramasSanitariosView calendarioIdInicial={cronogramaFiltroCalendarioId} onLimparFiltro={() => setCronogramaFiltroCalendarioId(null)} />
      ) : modo === "exames" ? <RelatorioResultadosExameView eventos={eventos} /> : (
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
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Tipo</label>
            <select style={selStyle} value={tipoFiltro} onChange={(e) => setTipoFiltro(e.target.value as any)}>
              {TIPOS_REGRA_FILTRO.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
            </select></div>
        </div>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!regras && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regras && (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span>Regras do calendário sanitário ({regrasFiltradas.length}) — clique no cabeçalho para ordenar</span>
            <ExportarBotoes titulo="Calendário sanitário" nomeArquivoBase="calendario_sanitario" colunas={COLUNAS_CALENDARIO} linhas={linhasExport} />
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "480px" }}>
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Evento" campo="evento_sanitario_nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <th>Tipo</th>
                <ThOrdenavel label="Categoria alvo" campo="categoria_alvo" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Doença" campo="doenca_nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <th>Produto</th><th>Dosagem</th><th>Responsável</th><th>Frequência</th>
                <ThOrdenavel label="Próxima ocorrência" campo="proxima_ocorrencia" coluna={coluna} dir={dir} ordenar={ordenar} />
                {admin && <th style={{ textAlign: "right" }}>Ações</th>}
              </tr></thead>
              <tbody>
                {linhasOrdenadas.map((r) => {
                  const ehExame = (r as any).categoria_preventiva === "exame";
                  const servico = servicoFinanceiro(r);
                  return (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 700 }}>{r.evento_sanitario_nome}{ehExame ? <span style={{ fontSize: "0.68rem", color: "var(--blue)", marginLeft: 6 }}>exame</span> : null}</td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {ROTULO_TIPO_REGRA[tipoRegra(r)]}
                    </td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.categoria_alvo || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.doenca_nome || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.produto || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.dosagem || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.responsavel || r.veterinario || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>a cada {r.frequencia_valor} {LABEL_FREQ[r.frequencia_unidade]}</td>
                    <td style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--dourado-light)" }}>{formatDate(r.proxima_ocorrencia)}</td>
                    {admin && (
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <span style={{ display: "inline-flex", gap: "0.35rem", alignItems: "center" }}>
                          {servico && (
                            <button title={`Lançar financeiro (${servico})`} onClick={() => lancarFinanceiro(r)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--green-light)", fontSize: "0.72rem", fontWeight: 700 }}>$ Financeiro</button>
                          )}
                          <a title="Editar em Central de Protocolos" href="/protocolos?aba=cadastro&tipo=sanitario&sub=preventivo" style={{ color: "var(--text-muted)", padding: 2 }}><Pencil size={14} /></a>
                          <button title="Excluir" onClick={() => excluir(r)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}><Trash2 size={14} /></button>
                        </span>
                      </td>
                    )}
                  </tr>
                  );
                })}
                {!regrasFiltradas.length && <tr><td colSpan={admin ? 10 : 9} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma regra no filtro.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
      </>
      )}
    </>
  );
}

// Cronogramas sanitários (regras usa_cronograma=True — ver
// fazenda/rules/cronograma_sanitario.py): 1 linha por ocorrência (aberta ou
// concluída), com contagem de animais por status na trilha do animal.
type CronogramaAnimalContagem = { sugerido: number; incluido: number; excluido: number; aplicado: number };
type Cronograma = {
  id: number; calendario_sanitario_id: number; evento_sanitario_nome: string; categoria_alvo: string | null;
  data_evento: string; data_original: string | null; status: string; modo_execucao: string | null;
  veterinario_nome: string | null; animais_contagem: CronogramaAnimalContagem;
};
const STATUS_CRONOGRAMA_LABEL: Record<string, string> = {
  aberto: "Aberto — aguardando decisão", agendado: "Agendado", concluido: "Concluído", cancelado: "Cancelado",
};
const STATUS_CRONOGRAMA_COR: Record<string, string> = {
  aberto: "var(--amber)", agendado: "var(--dourado-light)", concluido: "var(--green-light)", cancelado: "var(--text-muted)",
};
function CronogramasSanitariosView({ calendarioIdInicial, onLimparFiltro }: { calendarioIdInicial?: number | null; onLimparFiltro?: () => void } = {}) {
  const [cronogramas, setCronogramas] = useState<Cronograma[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFiltro, setStatusFiltro] = useState<"todos" | "aberto" | "agendado" | "concluido" | "cancelado">("todos");
  const [regrasCronograma, setRegrasCronograma] = useState<RegraCalendario[] | null>(null);
  const [novoAberto, setNovoAberto] = useState(false);
  const [novaRegraId, setNovaRegraId] = useState("");
  const [criando, setCriando] = useState(false);
  const [msgNovo, setMsgNovo] = useState<string | null>(null);

  const carregar = useCallback(() => {
    fetchCronogramasSanitarios(calendarioIdInicial ? { calendarioId: calendarioIdInicial } : undefined)
      .then(setCronogramas).catch((e) => setError(e.message));
  }, [calendarioIdInicial]);
  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => {
    fetchCalendarioSanitario().then((rs: RegraCalendario[]) => setRegrasCronograma(rs.filter((r) => r.usa_cronograma))).catch(() => {});
  }, []);

  const filtrados = useMemo(
    () => (cronogramas || []).filter((c) => statusFiltro === "todos" || c.status === statusFiltro),
    [cronogramas, statusFiltro]
  );
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(filtrados);

  // Só oferece regras usa_cronograma=True que ainda não têm um ciclo em
  // aberto — cada regra tem no máximo 1 cronograma aberto por vez.
  const regrasElegiveis = useMemo(() => {
    const todosCronogramas = cronogramas || [];
    return (regrasCronograma || []).filter((r) => !todosCronogramas.some(
      (c) => c.calendario_sanitario_id === r.id && (c.status === "aberto" || c.status === "agendado")
    ));
  }, [regrasCronograma, cronogramas]);

  const criarNovo = async () => {
    if (!novaRegraId) { setMsgNovo("Escolha uma regra."); return; }
    setCriando(true); setMsgNovo(null);
    try {
      await criarCronogramaSanitario(Number(novaRegraId));
      setNovoAberto(false); setNovaRegraId("");
      carregar();
    } catch (e: any) { setMsgNovo(e.message); }
    finally { setCriando(false); }
  };

  return (
    <>
      <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
        Ocorrências das regras do calendário sanitário marcadas "Usar cronograma sanitário" — cada linha é uma janela de
        aplicação (ex.: "Vacina Brucelose — Novilhas 3 meses"), com quem vai aplicar e quantos animais já entraram na lista.
      </p>
      {calendarioIdInicial && (
        <p style={{ fontSize: "0.78rem", marginBottom: "0.5rem" }}>
          Filtrado por uma regra específica. <button className="btn-secondary" style={{ fontSize: "0.72rem" }} onClick={onLimparFiltro}>Ver todos</button>
        </p>
      )}
      <div className="flex items-center justify-between my-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
          {(["todos", "aberto", "agendado", "concluido", "cancelado"] as const).map((s) => (
            <button key={s} type="button" className={statusFiltro === s ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.72rem" }} onClick={() => setStatusFiltro(s)}>
              {s === "todos" ? "Todos" : STATUS_CRONOGRAMA_LABEL[s]}
            </button>
          ))}
        </div>
        <button className="btn-primary" style={{ fontSize: "0.75rem" }} onClick={() => setNovoAberto((v) => !v)}>+ Novo cronograma</button>
      </div>

      {novoAberto && (
        <div className="card mb-3">
          <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Regra vinculada (obrigatório)</label>
          <select
            style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%", maxWidth: 420 }}
            value={novaRegraId} onChange={(e) => setNovaRegraId(e.target.value)}
          >
            <option value="">
              {regrasElegiveis.length ? "Selecione…" : "Nenhuma regra disponível (crie uma com \"usa_cronograma\" em Regras cadastradas)"}
            </option>
            {regrasElegiveis.map((r) => (
              <option key={r.id} value={r.id}>{r.evento_sanitario_nome} — {r.categoria_alvo || "Todos os animais"}</option>
            ))}
          </select>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
            Não é possível criar um cronograma sem vincular a uma regra já cadastrada — regras sem "Usar cronograma sanitário" marcado não aparecem aqui.
          </p>
          {msgNovo && <p style={{ color: "var(--red)", fontSize: "0.78rem" }}>{msgNovo}</p>}
          <div className="flex items-center gap-2 mt-2">
            <button className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={criarNovo} disabled={criando || !novaRegraId}>{criando ? "Criando…" : "Criar"}</button>
            <button className="btn-secondary" style={{ fontSize: "0.78rem" }} onClick={() => { setNovoAberto(false); setMsgNovo(null); }}>Cancelar</button>
          </div>
        </div>
      )}

      {error && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}>{error}</p>}
      <div className="overflow-x-auto">
        <table className="fazenda-table">
          <thead><tr>
            <ThOrdenavel label="Evento" campo="evento_sanitario_nome" coluna={coluna} dir={dir} ordenar={ordenar} />
            <ThOrdenavel label="Categoria alvo" campo="categoria_alvo" coluna={coluna} dir={dir} ordenar={ordenar} />
            <ThOrdenavel label="Data prevista" campo="data_evento" coluna={coluna} dir={dir} ordenar={ordenar} />
            <ThOrdenavel label="Status" campo="status" coluna={coluna} dir={dir} ordenar={ordenar} />
            <ThOrdenavel label="Veterinário" campo="veterinario_nome" coluna={coluna} dir={dir} ordenar={ordenar} />
            <th>Sugerido</th><th>Incluído</th><th>Excluído</th><th>Aplicado</th>
          </tr></thead>
          <tbody>
            {linhasOrdenadas.map((c) => (
              <tr key={c.id}>
                <td style={{ fontWeight: 700 }}>{c.evento_sanitario_nome}</td>
                <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{c.categoria_alvo || "—"}</td>
                <td style={{ fontSize: "0.78rem" }}>{formatDate(c.data_evento)}{c.data_original && c.data_original !== c.data_evento ? <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}> (adiado, era {formatDate(c.data_original)})</span> : null}</td>
                <td style={{ fontSize: "0.78rem", fontWeight: 600, color: STATUS_CRONOGRAMA_COR[c.status] || "var(--text-muted)" }}>{STATUS_CRONOGRAMA_LABEL[c.status] || c.status}</td>
                <td style={{ fontSize: "0.78rem" }}>{c.veterinario_nome || (c.modo_execucao === "propria" ? "Equipe própria" : "—")}</td>
                <td style={{ fontSize: "0.78rem", textAlign: "center" }}>{c.animais_contagem?.sugerido ?? 0}</td>
                <td style={{ fontSize: "0.78rem", textAlign: "center" }}>{c.animais_contagem?.incluido ?? 0}</td>
                <td style={{ fontSize: "0.78rem", textAlign: "center" }}>{c.animais_contagem?.excluido ?? 0}</td>
                <td style={{ fontSize: "0.78rem", textAlign: "center" }}>{c.animais_contagem?.aplicado ?? 0}</td>
              </tr>
            ))}
            {!linhasOrdenadas.length && <tr><td colSpan={9} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum cronograma no filtro.</td></tr>}
          </tbody>
        </table>
      </div>
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

const CORES = ["var(--vinho-light, #416180)", "var(--dourado)", "var(--blue)", "var(--amber)", "var(--green-light)", "var(--red)", "#7A5C99", "#4C9AA8"];
const UNIDADES_APLIC = ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"];

function AplicacoesView({ natureza = "curativo", autoEditarId = null }: { natureza?: "curativo" | "preventivo"; autoEditarId?: number | null }) {
  const [regs, setRegs] = useState<Aplic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);
  const [fCat, setFCat] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [buscaProd, setBuscaProd] = useState("");
  const [fOrdemParto, setFOrdemParto] = useState<string[]>([]);
  // Filtro por animal(is)/lote(s)/categoria(s) do animal — mesmo padrão de
  // seleção "todos ou vários" do lançamento de Aplicação: escolher lote(s) ou
  // categoria(s) abre a lista dos animais correspondentes para afinar a seleção.
  const [animaisSel, setAnimaisSel] = useState<Set<string>>(new Set());
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [selDosLotes, setSelDosLotes] = useState<Set<string>>(new Set());
  const [categoriasAnimalSel, setCategoriasAnimalSel] = useState<string[]>([]);
  const [selDasCategorias, setSelDasCategorias] = useState<Set<string>>(new Set());
  const [editId, setEditId] = useState<number | null>(null);
  const [editVals, setEditVals] = useState<{ data: string; produto: string; dose: string; unidade: string; via: string; responsavel: string; obs: string }>({ data: "", produto: "", dose: "", unidade: "", via: "", responsavel: "", obs: "" });
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [produtosCatalogo, setProdutosCatalogo] = useState<{ nome: string; quantidade: number | null; unidade: string | null }[]>([]);
  const [soComEstoque, setSoComEstoque] = useState(false);
  const admin = ehAdmin();

  // Exclusão múltipla — marca vários registros (individuais ou dentro de um
  // card de lote expandido) e exclui de uma vez. `expandidos` controla quais
  // cards de lote (BST, protocolo... qualquer grupo de aplicações lançadas
  // juntas) estão abertos para seleção individual, em vez do card recolhido.
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set());
  const [excluindoLote, setExcluindoLote] = useState(false);

  useEffect(() => {
    fetchMedicamentos({ incluir_sem_estoque: true })
      .then((m: any[]) => setProdutosCatalogo(m.map((x) => ({ nome: x.nome, quantidade: x.quantidade, unidade: x.unidade }))))
      .catch(() => setProdutosCatalogo([]));
  }, []);

  // Opções do filtro = união dos produtos que APARECEM nas aplicações carregadas
  // com o catálogo da farmácia (que traz o saldo). Sem a primeira parte, uma
  // aplicação antiga de produto já removido do estoque ficaria impossível de
  // filtrar; sem a segunda, não dava para escolher um produto ainda não usado.
  // `quantidade === null` = produto que não está no catálogo de estoque atual.
  const catalogoFiltrado = useMemo(() => {
    const porNome = new Map(produtosCatalogo.map((p) => [p.nome, p]));
    for (const r of regs || []) {
      if (r.produto && !porNome.has(r.produto)) porNome.set(r.produto, { nome: r.produto, quantidade: null, unidade: null });
    }
    const lista = Array.from(porNome.values());
    const visiveis = soComEstoque ? lista.filter((p) => (p.quantidade ?? 0) > 0) : lista;
    return visiveis.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  }, [produtosCatalogo, regs, soComEstoque]);
  // Se o produto selecionado sumir da lista ao marcar o checkbox, limpa o filtro para não deixar seleção invisível.
  useEffect(() => {
    if (soComEstoque && buscaProd && !catalogoFiltrado.some((p) => p.nome === buscaProd)) setBuscaProd("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [soComEstoque]);

  // Cada aba busca só o que é dela — legado/importado (natureza=null) conta
  // como curativo (ver Sanidade.natureza).
  const carregar = () => fetchSanidade().then((d) => setRegs(
    (d.aplicacoes as Aplic[]).filter((a) => natureza === "preventivo" ? a.natureza === "preventivo" : a.natureza !== "preventivo")
  )).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, [natureza]);

  // Vindo do popup "regra já agendada" (Lançamentos > Preventivo > Aplicações):
  // abre direto a edição do último evento lançado para aquele produto.
  useEffect(() => {
    if (!autoEditarId || !regs) return;
    const a = regs.find((r) => r.id === autoEditarId);
    if (a) iniciarEdicao(a);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoEditarId, regs]);

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

  // Passa pelo fluxo central e auditado de exclusão (POST /exclusoes/confirmar)
  // em vez do DELETE direto — admin ainda exclui na hora, mas agora QUALQUER
  // usuário logado pode pedir (operador vira uma SolicitacaoExclusao pendente
  // de aprovação, igual a qualquer outra exclusão do sistema). Isso também
  // conecta com o mesmo estorno de estoque e a mesma trilha de auditoria que
  // o painel de Exclusões já usa — antes o botão (só visível pra admin) batia
  // direto em DELETE /sanidade/aplicacoes/{id}, sem gerar esse rastro.
  const excluir = async (a: Aplic) => {
    const msg = admin
      ? `Excluir a aplicação de "${a.produto}" no animal ${a.numero}? Isso não pode ser desfeito.`
      : `Solicitar a exclusão da aplicação de "${a.produto}" no animal ${a.numero}? Um administrador precisa aprovar antes de ser excluída de fato.`;
    if (!window.confirm(msg)) return;
    setOcupado(a.id); setError(null); setAvisoExclusao(null);
    try {
      const r = await confirmarExclusao("sanidade", String(a.id));
      if (r.status === "excluido") {
        await carregar();
      } else {
        setAvisoExclusao(`Solicitação de exclusão enviada — aguardando aprovação de um administrador.`);
      }
    } catch (e: any) { setError(e.message); }
    finally { setOcupado(null); }
  };

  const excluirVarias = async (ids: number[]) => {
    if (!ids.length) return;
    const msg = admin
      ? `Excluir ${ids.length} aplicação(ões)? Isso não pode ser desfeito.`
      : `Solicitar a exclusão de ${ids.length} aplicação(ões)? Um administrador precisa aprovar antes de serem excluídas de fato.`;
    if (!window.confirm(msg)) return;
    setExcluindoLote(true); setError(null); setAvisoExclusao(null);
    let excluidas = 0, pendentes = 0;
    for (const id of ids) {
      try {
        const r = await confirmarExclusao("sanidade", String(id));
        if (r.status === "excluido") excluidas++; else pendentes++;
      } catch (e: any) { setError(e.message); }
    }
    setSelecionados(new Set());
    setExcluindoLote(false);
    if (excluidas) await carregar();
    if (pendentes) setAvisoExclusao(`${pendentes} solicitação(ões) de exclusão enviada(s) — aguardando aprovação de um administrador.`);
  };

  const toggleSelecionado = (id: number) => setSelecionados((prev) => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const toggleExpandido = (chave: string) => setExpandidos((prev) => {
    const n = new Set(prev); n.has(chave) ? n.delete(chave) : n.add(chave); return n;
  });

  const opc = (f: (a: Aplic) => string | null) => {
    const s = new Set<string>(); (regs ?? []).forEach((a) => { const v = f(a); if (v) s.add(v); });
    return Array.from(s).sort();
  };

  // Animais distintos já lançados (com lote/categoria) — dá para montar os
  // pickers padrão (AnimalPickerModal/LotePicker) sem precisar do cadastro
  // completo do rebanho, já que cada aplicação já carrega lote/categoria_animal.
  const animaisDeAplic = useMemo<AnimalRow[]>(() => {
    const porNumero = new Map<string, AnimalRow>();
    (regs ?? []).forEach((a) => {
      if (!porNumero.has(a.numero)) porNumero.set(a.numero, { numero: a.numero, grupo_primario: a.lote, categoria_abrev: a.categoria_animal });
    });
    return Array.from(porNumero.values());
  }, [regs]);
  const codigosLotesTodos = useMemo(
    () => Array.from(new Set(animaisDeAplic.map((a) => a.grupo_primario).filter((c): c is string => !!c))).sort(),
    [animaisDeAplic]
  );
  const animaisDosLotesSel = useMemo(() => {
    if (!lotesSel.length) return [];
    const cods = new Set(lotesSel);
    return animaisDeAplic.filter((a) => a.grupo_primario && cods.has(a.grupo_primario));
  }, [animaisDeAplic, lotesSel]);
  useEffect(() => {
    setSelDosLotes(new Set(animaisDosLotesSel.map((a) => a.numero)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lotesSel.join("|")]);
  const categoriasAnimalTodas = useMemo(
    () => Array.from(new Set(animaisDeAplic.map((a) => a.categoria_abrev).filter((c): c is string => !!c))).sort(),
    [animaisDeAplic]
  );
  const animaisDasCategoriasSel = useMemo(() => {
    if (!categoriasAnimalSel.length) return [];
    const cats = new Set(categoriasAnimalSel);
    return animaisDeAplic.filter((a) => a.categoria_abrev && cats.has(a.categoria_abrev));
  }, [animaisDeAplic, categoriasAnimalSel]);
  useEffect(() => {
    setSelDasCategorias(new Set(animaisDasCategoriasSel.map((a) => a.numero)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoriasAnimalSel.join("|")]);

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((a) =>
      (!fCat || a.categoria === fCat) &&
      (!ini || (a.data ? a.data >= ini : false)) &&
      (!fim || (a.data ? a.data <= fim : false)) &&
      (!buscaProd || a.produto === buscaProd) &&
      (animaisSel.size === 0 || animaisSel.has(a.numero)) &&
      (lotesSel.length === 0 || selDosLotes.has(a.numero)) &&
      (categoriasAnimalSel.length === 0 || selDasCategorias.has(a.numero)) &&
      (fOrdemParto.length === 0 || (a.ordem_parto !== null && fOrdemParto.includes(String(a.ordem_parto))))
    );
  }, [regs, fCat, ini, fim, buscaProd, animaisSel, lotesSel, selDosLotes, categoriasAnimalSel, selDasCategorias, fOrdemParto]);

  // Agrupa em "cards de lote" as aplicações que vieram do MESMO lançamento em
  // lote (BST, protocolo...) — mesma data/produto/atividade/responsável/dose/
  // unidade/usuário, ≥2 animais. Não há um id de lote explícito no banco;
  // esta é a mesma combinação de campos que só bate por coincidência entre
  // duas ações manuais DIFERENTES na prática (data+produto+responsável+dose
  // exatamente iguais). Um card recolhido oferece excluir tudo de uma vez;
  // expandido, mostra cada linha para marcar/excluir uma por uma.
  type ItemAplic = { tipo: "grupo"; chave: string; linhas: Aplic[] } | { tipo: "individual"; linha: Aplic };
  const itensExibicao = useMemo<ItemAplic[]>(() => {
    const porChave = new Map<string, Aplic[]>();
    for (const a of filtrados) {
      const chave = [a.data, a.produto, a.atividade, a.responsavel, a.dose, a.unidade, a.usuario_nome].join("␟");
      const lista = porChave.get(chave) || [];
      lista.push(a);
      porChave.set(chave, lista);
    }
    const itens: ItemAplic[] = [];
    for (const [chave, linhas] of porChave.entries()) {
      if (linhas.length > 1) itens.push({ tipo: "grupo", chave, linhas });
      else itens.push({ tipo: "individual", linha: linhas[0] });
    }
    // Mantém a ordem geral por data desc (mesma ordem que `filtrados`/`regs`
    // já trazem) — usa a posição do primeiro item de cada grupo/individual.
    const posicao = new Map(filtrados.map((a, i) => [a.id, i]));
    itens.sort((x, y) => {
      const px = x.tipo === "grupo" ? Math.min(...x.linhas.map((l) => posicao.get(l.id) ?? 0)) : (posicao.get(x.linha.id) ?? 0);
      const py = y.tipo === "grupo" ? Math.min(...y.linhas.map((l) => posicao.get(l.id) ?? 0)) : (posicao.get(y.linha.id) ?? 0);
      return px - py;
    });
    return itens;
  }, [filtrados]);
  const pagAplicacoes = usePaginacao(itensExibicao);

  // Quando há filtro por período (de/até), as linhas SEM data ficam de fora — conta quantas para avisar o usuário.
  const semDataExcluidas = useMemo(() => {
    if (!regs || (!ini && !fim)) return 0;
    return regs.filter((a) =>
      (!fCat || a.categoria === fCat) &&
      (!buscaProd || a.produto === buscaProd) &&
      (animaisSel.size === 0 || animaisSel.has(a.numero)) &&
      (lotesSel.length === 0 || selDosLotes.has(a.numero)) &&
      (categoriasAnimalSel.length === 0 || selDasCategorias.has(a.numero)) &&
      !a.data
    ).length;
  }, [regs, fCat, ini, fim, buscaProd, animaisSel, lotesSel, selDosLotes, categoriasAnimalSel, selDasCategorias]);

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
  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" };

  return (
    <>
      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importe os dados sanitários</a>.</span></div>}
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
              <select style={selStyle} value={buscaProd} onChange={(e) => setBuscaProd(e.target.value)}>
                <option value="">Todos</option>
                {!catalogoFiltrado.some((p) => p.nome === buscaProd) && buscaProd && <option value={buscaProd}>{buscaProd}</option>}
                {catalogoFiltrado.map((p) => (
                  <option key={p.nome} value={p.nome}>
                    {p.nome}{p.quantidade == null ? "" : ` — ${p.quantidade > 0 ? `${p.quantidade}${p.unidade ? ` ${p.unidade}` : ""}` : "sem estoque"}`}
                  </option>
                ))}
              </select>
              <label title="Mostrar no seletor apenas produtos com saldo em estoque" style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.7rem", color: "var(--text-muted)", cursor: "pointer", marginTop: "0.3rem" }}>
                <input type="checkbox" checked={soComEstoque} onChange={(e) => setSoComEstoque(e.target.checked)} /> Só com saldo em estoque
              </label>
            </div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal(is)</label>
              <AnimalPickerModal
                animais={animaisDeAplic} selecionados={animaisSel} onToggle={(n) => setAnimaisSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; })}
                placeholder="Todos" titulo="Filtrar por animal(is)"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || "—" },
                ]}
              />
            </div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lote(s)</label>
              <LotePicker opcoes={opcoesLoteDeAnimais(animaisDeAplic, codigosLotesTodos)} selecionados={lotesSel} onChange={setLotesSel} placeholder="Todos" />
            </div>
            <MultiFiltro label="Categoria do animal" opcoes={categoriasAnimalTodas} selecionados={categoriasAnimalSel} onChange={setCategoriasAnimalSel} />
            <MultiFiltro label="Ordem de parto" opcoes={opc((a) => a.ordem_parto == null ? null : String(a.ordem_parto))} selecionados={fOrdemParto} onChange={setFOrdemParto} formatar={(v) => `${v}ª`} />
          </div>
          {lotesSel.length > 0 && (
            <div style={{ marginTop: "0.6rem" }}>
              <AnimalPickerModal
                animais={animaisDosLotesSel} selecionados={selDosLotes} onToggle={(n) => setSelDosLotes((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; })}
                titulo="Ajustar animais do(s) lote(s) selecionado(s)" placeholder="Ajustar animais do(s) lote(s)…"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || "—" },
                ]}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                {selDosLotes.size} de {animaisDosLotesSel.length} animal(is) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir algum.
              </p>
            </div>
          )}
          {categoriasAnimalSel.length > 0 && (
            <div style={{ marginTop: "0.6rem" }}>
              <AnimalPickerModal
                animais={animaisDasCategoriasSel} selecionados={selDasCategorias} onToggle={(n) => setSelDasCategorias((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; })}
                titulo="Ajustar animais das categorias selecionadas" placeholder="Ajustar animais das categorias…"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || "—" },
                ]}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                {selDasCategorias.size} de {animaisDasCategoriasSel.length} animal(is) na(s) categoria(s) selecionada(s) — desmarque na janela acima para excluir algum.
              </p>
            </div>
          )}
        </div>

        {semDataExcluidas > 0 && (
          <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.75rem" }}>
            {semDataExcluidas} aplicaç{semDataExcluidas === 1 ? "ão" : "ões"} sem data não {semDataExcluidas === 1 ? "é exibida" : "são exibidas"} no filtro por período.
          </p>
        )}

        {/* Aplicações é o volume de atividade real da tela — vira a métrica-âncora
            em vez de competir em pé de igualdade com Animais tratados/Produtos
            distintos/Categorias, que continuam do lado, menores. */}
        <div className="card mb-4" style={{ padding: "1.1rem 1.3rem" }}>
          <div style={{ fontSize: ".68rem", fontWeight: 700, letterSpacing: ".13em", textTransform: "uppercase", color: "var(--text-muted)" }}>Aplicações</div>
          <div style={{ fontFamily: "var(--font-heading)", fontSize: "2.6rem", fontWeight: 800, lineHeight: 1, color: "var(--dourado-light)", marginTop: ".25rem", fontVariantNumeric: "tabular-nums" }}>
            {filtrados.length}
          </div>
          <div style={{ display: "flex", gap: "1.6rem", marginTop: ".9rem", paddingTop: ".8rem", borderTop: "1px solid var(--border)", flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--green-light)", fontVariantNumeric: "tabular-nums" }}>{animaisTratados}</div>
              <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Animais tratados</div>
            </div>
            <div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{produtos}</div>
              <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Produtos distintos</div>
            </div>
            <div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{porCategoria.length}</div>
              <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Categorias</div>
            </div>
          </div>
        </div>

        <SecaoRecolhivel titulo="Aplicações por Categoria e por Mês" descricao="Clique numa barra para filtrar as aplicações por categoria">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
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
            <div>
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
        </SecaoRecolhivel>

        <SecaoRecolhivel titulo="Aplicações" badge={<span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length} registro(s)</span>}
          descricao="Lista completa das aplicações que atendem aos filtros acima">
          {avisoExclusao && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{avisoExclusao}</p>}
          <div className="flex justify-between items-center mb-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <button className="btn-ghost" style={{ fontSize: "0.78rem", color: "var(--red)" }}
              disabled={!selecionados.size || excluindoLote}
              onClick={() => excluirVarias(Array.from(selecionados))}>
              <Trash2 size={14} /> {excluindoLote ? "Excluindo…" : `Excluir selecionados (${selecionados.size})`}
            </button>
            <ExportarBotoes titulo="Sanidade — Aplicações" nomeArquivoBase="sanidade" colunas={COLUNAS_SANIDADE} linhas={filtrados} />
          </div>
          <div>
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table">
                <thead><tr><th></th><th>Data</th><th>Animal</th><th>Produto</th><th>Categoria</th><th style={{ textAlign: "right" }}>Dose</th>{admin && <th style={{ textAlign: "left" }}>Usuário</th>}<th style={{ textAlign: "right" }}>Ações</th></tr></thead>
                <tbody>
                  {pagAplicacoes.linhasPagina.map((item) => {
                    if (item.tipo === "grupo") {
                      const { chave, linhas } = item;
                      const aberto = expandidos.has(chave);
                      const primeira = linhas[0];
                      const idsDoGrupo = linhas.map((l) => l.id);
                      const todasMarcadas = idsDoGrupo.every((id) => selecionados.has(id));
                      if (!aberto) {
                        return (
                          <tr key={chave} style={{ background: "var(--surface-2)", cursor: "pointer" }} onClick={() => toggleExpandido(chave)}>
                            <td onClick={(e) => e.stopPropagation()}>
                              <input type="checkbox" checked={todasMarcadas} onChange={() => setSelecionados((prev) => {
                                const n = new Set(prev);
                                if (todasMarcadas) idsDoGrupo.forEach((id) => n.delete(id)); else idsDoGrupo.forEach((id) => n.add(id));
                                return n;
                              })} />
                            </td>
                            <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{primeira.data ? new Date(primeira.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                            <td colSpan={2} style={{ fontWeight: 700 }}>
                              <span className="flex items-center gap-1"><ChevronRight size={13} /> {primeira.produto}{primeira.atividade ? ` — ${primeira.atividade}` : ""}
                                <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.75rem" }}> · {linhas.length} animais (lançados juntos)</span></span>
                            </td>
                            <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{primeira.categoria}</td>
                            <td style={{ textAlign: "right" }}>{primeira.dose ?? "—"}{primeira.unidade ? ` ${primeira.unidade}` : ""}</td>
                            {admin && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{primeira.usuario_nome ?? "—"}</td>}
                            <td style={{ textAlign: "right", whiteSpace: "nowrap" }} onClick={(e) => e.stopPropagation()}>
                              <button title={admin ? "Excluir todos deste lote" : "Solicitar exclusão de todos deste lote"} disabled={excluindoLote}
                                onClick={() => excluirVarias(idsDoGrupo)}
                                style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}>
                                <Trash2 size={14} />
                              </button>
                            </td>
                          </tr>
                        );
                      }
                      return (
                        <Fragment key={chave}>
                          <tr style={{ background: "var(--surface-2)", cursor: "pointer" }} onClick={() => toggleExpandido(chave)}>
                            <td colSpan={admin ? 8 : 7} style={{ fontSize: "0.78rem", fontWeight: 600 }}>
                              <span className="flex items-center gap-1"><ChevronDown size={13} /> {primeira.produto}{primeira.atividade ? ` — ${primeira.atividade}` : ""} · {linhas.length} animais — clique para recolher</span>
                            </td>
                          </tr>
                          {linhas.map((a) => (
                            <tr key={a.id}>
                              <td><input type="checkbox" checked={selecionados.has(a.id)} onChange={() => toggleSelecionado(a.id)} /></td>
                              <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{a.data ? new Date(a.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                              <td style={{ fontWeight: 700 }}>{a.numero}</td>
                              <td style={{ fontSize: "0.75rem" }}>{a.produto}</td>
                              <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{a.categoria}</td>
                              <td style={{ textAlign: "right" }}>{a.dose ?? "—"}{a.unidade ? ` ${a.unidade}` : ""}</td>
                              {admin && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.usuario_nome ?? "—"}</td>}
                              <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                                <button title={admin ? "Excluir" : "Solicitar exclusão"} disabled={ocupado === a.id} onClick={() => excluir(a)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}><Trash2 size={14} /></button>
                              </td>
                            </tr>
                          ))}
                        </Fragment>
                      );
                    }

                    const a = item.linha;
                    const editando = editId === a.id;
                    const inp: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.25rem 0.4rem", fontSize: "0.75rem", width: "100%" };
                    return (
                    <Fragment key={a.id}>
                      <tr>
                        <td><input type="checkbox" checked={selecionados.has(a.id)} onChange={() => toggleSelecionado(a.id)} /></td>
                        <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{a.data ? new Date(a.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                        <td style={{ fontWeight: 700 }}>{a.numero}</td>
                        <td style={{ fontSize: "0.75rem" }}>{a.produto}</td>
                        <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{a.categoria}</td>
                        <td style={{ textAlign: "right" }}>{a.dose ?? "—"}{a.unidade ? ` ${a.unidade}` : ""}</td>
                        {admin && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.usuario_nome ?? "—"}</td>}
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          {!editando && (
                            <span style={{ display: "inline-flex", gap: "0.3rem" }}>
                              {admin && <button title="Editar" onClick={() => iniciarEdicao(a)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2 }}><Pencil size={14} /></button>}
                              <button title={admin ? "Excluir" : "Solicitar exclusão"} disabled={ocupado === a.id} onClick={() => excluir(a)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}><Trash2 size={14} /></button>
                            </span>
                          )}
                        </td>
                      </tr>
                      {editando && (
                        <tr>
                          <td colSpan={admin ? 8 : 7} style={{ background: "var(--surface-2)", padding: "0.6rem" }}>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Data</label>
                                <input type="date" style={inp} value={editVals.data} onChange={(e) => setEditVals((s) => ({ ...s, data: e.target.value }))} /></div>
                              <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Produto</label>
                                <select style={inp} value={editVals.produto} onChange={(e) => setEditVals((s) => ({ ...s, produto: e.target.value }))}>
                                  <option value="">Selecione...</option>
                                  {!produtosCatalogo.some((p) => p.nome === editVals.produto) && editVals.produto && <option value={editVals.produto}>{editVals.produto}</option>}
                                  {produtosCatalogo.map((p) => <option key={p.nome} value={p.nome}>{p.nome}</option>)}
                                </select></div>
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
                                  {!nomesResponsaveis.includes(editVals.responsavel) && editVals.responsavel && <option value={editVals.responsavel}>{editVals.responsavel}</option>}
                                  {nomesResponsaveis.map((r) => <option key={r} value={r}>{r}</option>)}
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
              <Paginacao pagina={pagAplicacoes.pagina} totalPaginas={pagAplicacoes.totalPaginas} totalLinhas={pagAplicacoes.totalLinhas}
                tamanhoPagina={pagAplicacoes.tamanhoPagina} onMudarPagina={pagAplicacoes.setPagina} onMudarTamanho={pagAplicacoes.setTamanhoPagina} />
            </div>
          </div>
        </SecaoRecolhivel>
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
    casaBusca(r.numero, buscaAnimal) &&
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

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
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
  id: number; protocolo_id: number; protocolo_nome: string; protocolo_dia_inicial?: number; numero_matriz: string; data_inicio: string;
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
    casaBusca(l.numero_matriz, buscaAnimal) &&
    (!fProtocolo || l.protocolo_nome === fProtocolo) &&
    (!fStatus || statusDe(l) === fStatus) &&
    (!ini || l.data_inicio >= ini) &&
    (!fim || l.data_inicio <= fim)
  ), [lancs, buscaAnimal, fProtocolo, fStatus, ini, fim]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

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
                                <td>{a.etapa ? `D${a.etapa.dia - (l.protocolo_dia_inicial ?? 1)}` : "—"}</td>
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

// ─────────────────────────── Taxa de cura (curativa) ───────────────────────────
const LABEL_CATEGORIA: Record<string, string> = { vaca: "Vaca", novilha: "Novilha", bezerra: "Bezerra" };
const LABEL_LACTACAO: Record<string, string> = { lactacao: "Lactação", seca: "Seca" };

function TaxaCuraView() {
  const [dados, setDados] = useState<{
    casos: CasoTaxaCura[]; total: number; total_avaliados: number; curados: number; nao_curados: number;
    total_nao_avaliados: number; taxa_cura_pct: number | null; cobertura_avaliacao_pct: number | null;
  } | null>(null);
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [fLotes, setFLotes] = useState<string[]>([]);
  const [fCategorias, setFCategorias] = useState<string[]>([]);
  const [fLactacao, setFLactacao] = useState<string[]>([]);
  const [marcando, setMarcando] = useState<Set<string>>(new Set());

  const carregar = useCallback(() => {
    fetchTaxaCura().then(setDados).catch(() => setDados({
      casos: [], total: 0, total_avaliados: 0, curados: 0, nao_curados: 0,
      total_nao_avaliados: 0, taxa_cura_pct: null, cobertura_avaliacao_pct: null,
    }));
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  // Responde "curado? sim/não" para um caso já com o protocolo encerrado mas
  // sem avaliação — o mesmo POST que a Agenda usa, só que aqui fora dela
  // (Defeito 4: a Agenda esconde o evento depois de 60 dias sem resposta, mas
  // o caso nunca deixa de poder ser avaliado — só passa a responder por aqui).
  const marcar = async (c: CasoTaxaCura, curada: boolean) => {
    const chave = `${c.origem}-${c.id}`;
    setMarcando((p) => new Set(p).add(chave));
    try {
      if (c.origem === "protocolo") await marcarCuraProtocolo(c.id, curada);
      else await marcarCuraAplicacao(c.id, curada);
      carregar();
    } catch (err: any) {
      alert(err.message || "Erro ao marcar cura");
    } finally {
      setMarcando((p) => { const n = new Set(p); n.delete(chave); return n; });
    }
  };

  const lotesOpc = useMemo(() => Array.from(new Set((dados?.casos || []).map((c) => c.lote).filter((v): v is string => !!v))).sort(), [dados]);

  const dentroDoFiltro = useCallback((c: CasoTaxaCura) =>
    (!ini || (c.data || "") >= ini) && (!fim || (c.data || "") <= fim) &&
    (fLotes.length === 0 || (c.lote != null && fLotes.includes(c.lote))) &&
    (fCategorias.length === 0 || fCategorias.includes(c.categoria)) &&
    (fLactacao.length === 0 || fLactacao.includes(c.status_lactacao))
  , [ini, fim, fLotes, fCategorias, fLactacao]);

  // Casos já avaliados (curada true/false) — só eles entram no cálculo da
  // taxa de cura. Os não avaliados (protocolo encerrado, ninguém respondeu)
  // ficam à parte, listados abaixo com botões Sim/Não.
  const filtrados = useMemo(() => (dados?.casos || []).filter((c) => c.avaliado && dentroDoFiltro(c)), [dados, dentroDoFiltro]);
  const naoAvaliados = useMemo(() => (dados?.casos || []).filter((c) => !c.avaliado && dentroDoFiltro(c)), [dados, dentroDoFiltro]);

  const totalFiltro = filtrados.length;
  const curadosFiltro = filtrados.filter((c) => c.curada).length;
  const taxaFiltro = totalFiltro ? Math.round((1000 * curadosFiltro) / totalFiltro) / 10 : null;
  const totalComPendentesFiltro = totalFiltro + naoAvaliados.length;
  const coberturaFiltro = totalComPendentesFiltro ? Math.round((1000 * totalFiltro) / totalComPendentesFiltro) / 10 : null;

  // Comparação do próprio animal ao longo da vida: agrupa por número, mostra
  // a taxa de cura individual — só faz sentido comparar quem já teve mais de 1 caso.
  const porAnimal = useMemo(() => {
    const by = new Map<string, CasoTaxaCura[]>();
    filtrados.forEach((c) => { (by.get(c.numero) ?? by.set(c.numero, []).get(c.numero)!).push(c); });
    return Array.from(by.entries())
      .map(([numero, casos]) => {
        const curados = casos.filter((c) => c.curada).length;
        return { numero, casos: casos.length, curados, taxa: Math.round((1000 * curados) / casos.length) / 10 };
      })
      .filter((a) => a.casos > 1)
      .sort((a, b) => a.taxa - b.taxa);
  }, [filtrados]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Período — de</label>
            <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>até</label>
            <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
          <MultiFiltro label="Lote" opcoes={lotesOpc} selecionados={fLotes} onChange={setFLotes} />
          <MultiFiltro label="Categoria" opcoes={["vaca", "novilha", "bezerra"]} selecionados={fCategorias} onChange={setFCategorias} formatar={(v) => LABEL_CATEGORIA[v] || v} />
          <MultiFiltro label="Lactação/Seca" opcoes={["lactacao", "seca"]} selecionados={fLactacao} onChange={setFLactacao} formatar={(v) => LABEL_LACTACAO[v] || v} />
        </div>
      </div>

      {!dados ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <Indicador categoria="sanidade" valor={totalFiltro} rotulo="Casos avaliados" />
            <Indicador categoria="sanidade" valor={curadosFiltro} cor="var(--green-light)" rotulo="Curados" />
            <Indicador
              categoria="sanidade"
              valor={taxaFiltro != null ? `${taxaFiltro}%` : "—"}
              cor={taxaFiltro != null && taxaFiltro < 70 ? "var(--red)" : "var(--green-light)"}
              rotulo="Taxa de cura"
              title="Calculada só sobre os casos já avaliados (curado? sim/não respondido) — quem nunca respondeu não entra na conta, pra não inflar a taxa artificialmente."
              extra={
                <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>
                  {totalComPendentesFiltro > 0
                    ? `calculada sobre ${totalFiltro} de ${totalComPendentesFiltro} caso${totalComPendentesFiltro === 1 ? "" : "s"} avaliados`
                    : "sem casos no filtro"}
                </span>
              }
            />
            <Indicador
              categoria="sanidade"
              valor={naoAvaliados.length}
              cor={naoAvaliados.length > 0 ? "var(--red)" : "var(--green-light)"}
              rotulo="Não avaliados"
              title="Protocolos já encerrados (todas as aplicações do último dia realizadas) sem resposta 'curado?' — some da Agenda depois de 60 dias, mas continua respondível aqui embaixo."
              extra={
                coberturaFiltro != null ? (
                  <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>cobertura de avaliação: {coberturaFiltro}%</span>
                ) : null
              }
            />
          </div>

          <SecaoRecolhivel
            titulo="Casos não avaliados"
            badge={<span style={{ fontSize: "0.8rem", color: naoAvaliados.length ? "var(--red)" : "var(--dourado-light)", fontWeight: 400 }}>{naoAvaliados.length}</span>}
            descricao="Protocolos já encerrados sem resposta 'curado? sim/não' — enquanto não forem respondidos, ficam de fora do cálculo da taxa de cura acima. Responda aqui os casos que já saíram da Agenda (mais de 60 dias sem resposta)."
          >
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <th>Animal</th><th>Tratamento</th><th>Data</th><th>Lote</th><th>Categoria</th><th>Lactação/Seca</th><th>Curado?</th>
                </tr></thead>
                <tbody>
                  {naoAvaliados.slice().sort((a, b) => (b.data || "").localeCompare(a.data || "")).map((c) => {
                    const chave = `${c.origem}-${c.id}`;
                    return (
                      <tr key={chave}>
                        <td style={{ fontWeight: 700 }}>{c.numero}</td>
                        <td style={{ fontSize: "0.8rem" }}>{c.tratamento}</td>
                        <td style={{ fontSize: "0.78rem" }}>{c.data ? formatDate(c.data) : "—"}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{c.lote || "—"}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{LABEL_CATEGORIA[c.categoria] || "—"}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{LABEL_LACTACAO[c.status_lactacao] || "—"}</td>
                        <td>
                          <span className="flex items-center gap-1" style={{ fontSize: "0.72rem" }}>
                            <button className="btn-ghost" style={{ color: "var(--green-light)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(chave)} onClick={() => marcar(c, true)}>Sim</button>
                            <button className="btn-ghost" style={{ color: "var(--red)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(chave)} onClick={() => marcar(c, false)}>Não</button>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                  {!naoAvaliados.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum caso pendente de avaliação com esses filtros.</td></tr>}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Casos" badge={<span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span>}
            descricao="Lista completa dos casos avaliados que atendem aos filtros acima">
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <th>Animal</th><th>Tratamento</th><th>Data</th><th>Lote</th><th>Categoria</th><th>Lactação/Seca</th><th>Curado?</th>
                </tr></thead>
                <tbody>
                  {filtrados.slice().sort((a, b) => (b.data || "").localeCompare(a.data || "")).map((c) => (
                    <tr key={`${c.origem}-${c.id}`}>
                      <td style={{ fontWeight: 700 }}>{c.numero}</td>
                      <td style={{ fontSize: "0.8rem" }}>{c.tratamento}</td>
                      <td style={{ fontSize: "0.78rem" }}>{c.data ? formatDate(c.data) : "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{c.lote || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{LABEL_CATEGORIA[c.categoria] || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{LABEL_LACTACAO[c.status_lactacao] || "—"}</td>
                      <td style={{ fontWeight: 700, color: c.curada ? "var(--green-light)" : "var(--red)" }}>{c.curada ? "Sim" : "Não"}</td>
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum caso avaliado com esses filtros.</td></tr>}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Comparação do próprio animal ao longo da vida"
            descricao="Só animais com mais de um caso avaliado no filtro atual — a taxa de cura individual ajuda a identificar quem tem recidiva frequente">
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
              Só animais com mais de um caso avaliado no filtro atual — a taxa de cura individual ajuda a identificar quem tem recidiva frequente.
            </p>
            {porAnimal.length ? (
              <table className="fazenda-table">
                <thead><tr><th>Animal</th><th style={{ textAlign: "right" }}>Casos</th><th style={{ textAlign: "right" }}>Curados</th><th style={{ textAlign: "right" }}>Taxa individual</th></tr></thead>
                <tbody>
                  {porAnimal.map((a) => (
                    <tr key={a.numero}>
                      <td style={{ fontWeight: 700 }}>{a.numero}</td>
                      <td style={{ textAlign: "right" }}>{a.casos}</td>
                      <td style={{ textAlign: "right", color: "var(--green-light)" }}>{a.curados}</td>
                      <td style={{ textAlign: "right", fontWeight: 700, color: a.taxa < 70 ? "var(--red)" : "var(--green-light)" }}>{a.taxa}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum animal com mais de um caso no filtro atual.</p>
            )}
          </SecaoRecolhivel>
        </>
      )}
    </>
  );
}

const inputStyleRastreabilidade: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem",
};
const COLUNAS_RASTREABILIDADE = [
  { header: "Animal", key: "numero_animal" }, { header: "Nome", key: "nome_animal" },
  { header: "Tipo de evento", key: "tipo_evento" }, { header: "Data", key: "dataFmt" },
  { header: "GTA", key: "gta" }, { header: "Descrição", key: "descricao" },
  { header: "Produto", key: "produto" }, { header: "Resultado", key: "resultado" },
  { header: "Doença", key: "doenca" }, { header: "Responsável", key: "responsavel" },
  { header: "Contraparte", key: "contraparte" },
];

/**
 * Rastreabilidade sanitária (Sanidade > Rastreabilidade) — a resposta a "esse
 * animal, com essa GTA, teve qual histórico sanitário?": linha do tempo com
 * as GTAs de compra/venda do animal, aplicações, protocolos sanitários,
 * exames e doenças/ocorrências clínicas, filtrável por animal, período ou
 * número de GTA. Não emite GTA (documento oficial do órgão estadual) — só
 * consulta o que já foi lançado em Lançamentos > Compra/Venda de animal e
 * nas telas de Sanidade.
 */
function RastreabilidadeSanitariaView() {
  const [numero, setNumero] = useState("");
  const [gta, setGta] = useState("");
  const [dataDe, setDataDe] = useState("");
  const [dataAte, setDataAte] = useState("");
  const [linhas, setLinhas] = useState<LinhaRastreabilidadeSanitaria[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [buscou, setBuscou] = useState(false);

  const buscar = () => {
    setCarregando(true); setErro(null); setBuscou(true);
    fetchRastreabilidadeSanitaria({ numero, gta, dataDe, dataAte })
      .then(setLinhas)
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  };

  const linhasExport = useMemo(() => (linhas ?? []).map((l) => ({ ...l, dataFmt: formatDate(l.data) })), [linhas]);
  const animaisDistintos = useMemo(() => new Set((linhas ?? []).map((l) => l.numero_animal)).size, [linhas]);
  const gtasEncontrados = useMemo(() => Array.from(new Set((linhas ?? []).map((l) => l.gta).filter(Boolean))) as string[], [linhas]);

  const CORES_EVENTO: Record<string, string> = {
    "Compra": "var(--red)", "Venda": "var(--green-light)", "Aplicação sanitária": "var(--dourado-light)",
    "Protocolo sanitário": "var(--blue)", "Exame": "var(--amber)", "Doença (ocorrência clínica)": "var(--red)", "Baixa": "var(--text-muted)",
  };

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          Reconstrói a cadeia sanitária de um animal (ou de uma GTA): compra/venda com GTA, aplicações
          sanitárias, protocolos, exames e doenças registradas — em ordem cronológica. Informe ao menos
          o número do animal, a GTA ou um período.
        </p>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Número do animal</label>
            <input style={inputStyleRastreabilidade} value={numero} onChange={(e) => setNumero(e.target.value)} placeholder="ex.: 950" /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>GTA</label>
            <input style={inputStyleRastreabilidade} value={gta} onChange={(e) => setGta(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>De</label>
            <input type="date" style={inputStyleRastreabilidade} value={dataDe} onChange={(e) => setDataDe(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Até</label>
            <input type="date" style={inputStyleRastreabilidade} value={dataAte} onChange={(e) => setDataAte(e.target.value)} /></div>
          <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={buscar} disabled={carregando}>
            <Search size={13} /> {carregando ? "Buscando…" : "Buscar"}
          </button>
        </div>
      </div>

      {erro && <div className="alert-critico mb-4"><span>{erro}</span></div>}

      {!buscou && !erro && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Informe um filtro e clique em Buscar.</p>
      )}

      {linhas && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
            <Indicador categoria="geral" valor={String(linhas.length)} rotulo="Eventos" />
            <Indicador categoria="geral" valor={String(animaisDistintos)} rotulo="Animais" />
            <Indicador categoria="geral" valor={String(gtasEncontrados.length)} rotulo="GTAs distintas" />
          </div>
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>Linha do tempo sanitária</div>
              <ExportarBotoes titulo="Rastreabilidade sanitária" colunas={COLUNAS_RASTREABILIDADE} linhas={linhasExport} nomeArquivoBase="rastreabilidade_sanitaria" disabled={!linhas.length} />
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr>
                  <th>Animal</th><th>Evento</th><th>Data</th><th>GTA</th><th>Descrição</th><th>Produto</th>
                  <th>Resultado</th><th>Doença</th><th>Responsável</th><th>Contraparte</th>
                </tr></thead>
                <tbody>
                  {linhas.map((l, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 700 }}>{l.numero_animal}{l.nome_animal ? ` · ${l.nome_animal}` : ""}</td>
                      <td>
                        <span style={{
                          fontSize: "0.72rem", padding: "0.15rem 0.5rem", borderRadius: "999px", fontWeight: 700,
                          color: CORES_EVENTO[l.tipo_evento] || "var(--text)",
                        }}>{l.tipo_evento}</span>
                      </td>
                      <td style={{ fontSize: "0.8rem" }}>{formatDate(l.data)}</td>
                      <td style={{ fontSize: "0.78rem", fontWeight: l.gta ? 700 : 400, color: l.gta ? "var(--dourado-light)" : "var(--text-muted)" }}>{l.gta || "—"}</td>
                      <td style={{ fontSize: "0.8rem" }}>{l.descricao || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.produto || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.resultado || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.doenca || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.responsavel || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.contraparte || "—"}</td>
                    </tr>
                  ))}
                  {!linhas.length && <tr><td colSpan={10} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum evento sanitário encontrado para o filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}

type AbaSanidade = "curativa" | "preventiva" | "rastreabilidade" | "catalogo";
const ABAS_SANIDADE = [
  { id: "curativa", label: "Curativa", icon: HeartPulse, title: "Tratamentos curativos: aplicações, doença/motivo e protocolos" },
  { id: "preventiva", label: "Preventiva", icon: Shield, title: "Manejo preventivo: aplicações e calendário sanitário" },
  { id: "rastreabilidade", label: "Rastreabilidade", icon: Route, title: "Rastreabilidade sanitária/GTA: linha do tempo por animal ou por GTA" },
  { id: "catalogo", label: "Catálogo", icon: BookOpen, title: "Catálogo de farmácia mantido pelo Painel CowData — indicações, princípios ativos e marcas, com bula e carência (somente consulta)" },
] as const satisfies readonly { id: AbaSanidade; label: string; icon: any; title: string }[];

type AbaCurativa = "curativo" | "doenca" | "remedios" | "protocolos" | "taxa_cura";
const ABAS_CURATIVA = [
  { id: "curativo", label: "Curativo (aplicações)", icon: ClipboardList, title: "Medicamentos aplicados no rebanho" },
  { id: "doenca", label: "Doença / Motivo", icon: Activity, title: "Tratamentos por doença/motivo" },
  { id: "remedios", label: "Remédios por doença", icon: FlaskConical, title: "Ranking de medicamentos indicados por doença, com estoque ao vivo" },
  { id: "protocolos", label: "Protocolos sanitários", icon: ListChecks, title: "Protocolos multi-etapa lançados (mastite e outros)" },
  { id: "taxa_cura", label: "Taxa de cura", icon: Percent, title: "Taxa de cura dos tratamentos (aplicações e protocolos)" },
] as const satisfies readonly { id: AbaCurativa; label: string; icon: any; title: string }[];

type AbaPreventiva = "aplicacoes" | "calendario" | "historico";
const ABAS_PREVENTIVA = [
  { id: "aplicacoes", label: "Aplicações", icon: ClipboardList, title: "Aplicações preventivas já lançadas" },
  { id: "calendario", label: "Calendário sanitário", icon: CalendarClock, title: "Calendário, regras cadastradas, cronogramas e resultados de exames" },
  { id: "historico", label: "Histórico", icon: History, title: "Vacinas e exames já realizados, agrupados por produto/exame, com filtros" },
] as const satisfies readonly { id: AbaPreventiva; label: string; icon: any; title: string }[];

export default function SanidadePage() {
  const [aba, setAba] = useState<AbaSanidade>("curativa");
  const [abaCur, setAbaCur] = useState<AbaCurativa>("curativo");
  const [abaPrev, setAbaPrev] = useState<AbaPreventiva>("aplicacoes");
  // Vindo do popup "regra já agendada" em Lançamentos > Preventivo > Aplicações
  // (link "editar/dar baixa no último evento lançado"): abre direto na aba certa.
  const [autoEditarId, setAutoEditarId] = useState<number | null>(null);
  // Vindo de "Registrar cronograma deste evento" (Lançamentos > Sanitário >
  // Preventivo > Calendário sanitário): abre direto no card Cronogramas.
  const [modoPreventivoInicial, setModoPreventivoInicial] = useState<"calendario" | "cronogramas">("calendario");
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get("editar_aplicacao_id")) {
      setAba("preventiva"); setAbaPrev("aplicacoes");
      setAutoEditarId(Number(qs.get("editar_aplicacao_id")));
    }
    if (qs.get("ir") === "cronogramas") {
      setAba("preventiva"); setAbaPrev("calendario");
      setModoPreventivoInicial("cronogramas");
    }
  }, []);

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
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Sanidade curativa e preventiva. O relatório de BST fica em Produção › Relatórios de BST; para lançar/agendar uma aplicação, use Lançamentos › Produção › BST.</p>
      </div>

      {aba === "curativa" && (
        <>
          {abaCur === "curativo" && <AplicacoesView natureza="curativo" />}
          {abaCur === "doenca" && <DoencaMotivoView />}
          {abaCur === "remedios" && <RemediosPorDoenca />}
          {abaCur === "protocolos" && <ProtocolosSanitariosView />}
          {abaCur === "taxa_cura" && <TaxaCuraView />}
        </>
      )}
      {aba === "preventiva" && (
        <>
          {abaPrev === "aplicacoes" && <AplicacoesView natureza="preventivo" autoEditarId={autoEditarId} />}
          {abaPrev === "calendario" && <CalendarioSanitarioView modoInicial={modoPreventivoInicial} />}
          {abaPrev === "historico" && <HistoricoPreventivoView />}
        </>
      )}
      {aba === "rastreabilidade" && <RastreabilidadeSanitariaView />}
      {aba === "catalogo" && <CatalogoFarmaciaConsulta />}
    </div>
  );
}
