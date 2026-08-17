"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, Stethoscope, AlertTriangle, Check, X, Mail, CalendarPlus, Download, ClipboardEdit, ArrowRight } from "lucide-react";
import { fetchAgendaVeterinario, registrarReconfirmacao, enviarDiagnosticoEmail, atualizarParametro } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { exportarFichaPDF, exportarMultiExcel, type ColunaExport } from "@/lib/export";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

type Item = {
  numero_matriz: string; categoria: string; peso: number | null;
  lote_atual: string | null;
  dias_inseminada: number | null; data_servico: string | null;
  inseminador: string | null; touro: string | null; tipo_servico: string | null; metodo: string | null;
  tocada: boolean; reconfirmada: boolean;
  data_diagnostico: string | null; diagnostico: string | null;
  data_reconfirmacao: string | null; diagnostico_reconfirmacao: string | null;
  tem_servico?: boolean;
  atrasada?: boolean; dias_para_parto?: number | null; motivo?: string;
  data_dg_negativo?: string | null; del_projetado_proximo_servico?: number | null;
  pev_dias_restantes_projetado?: number | null; proxima_data_dg_estimada?: string | null;
};
type Listas = Record<string, Item[]>;

const fmtDia = (iso: string | null | undefined) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
// Resultado de toque/reconfirmação em uma letra — P(renha)/V(azia)/I(ndefinido).
const badgeTexto = (v: string | null | undefined) => (v === "POSITIVO" ? "P" : v === "NEGATIVO" ? "V" : v === "INDEFINIDO" ? "I" : "—");
const corBadge = (v: string | null | undefined) => (v === "POSITIVO" ? "var(--green-light)" : v === "NEGATIVO" ? "var(--red)" : v === "INDEFINIDO" ? "var(--dourado-light)" : "var(--text-muted)");
function BadgeDiag({ v }: { v: string | null | undefined }) {
  return <span style={{ fontWeight: 700, color: corBadge(v) }}>{badgeTexto(v)}</span>;
}

const LISTAS: {
  key: string; label: string; color: string; extra?: "dias_para_parto" | "motivo"; reconfirmavel?: boolean;
  acao?: "toque" | "toque_ou_reconfirmacao"; vazia?: boolean; lancar?: boolean;
}[] = [
  { key: "inseminadas_1_29", label: "Inseminadas 1–29 dias", color: "var(--blue)", acao: "toque" },
  { key: "inseminadas_30_59", label: "Inseminadas 30–59 dias — toque", color: "var(--dourado)", acao: "toque" },
  { key: "inseminadas_60_mais", label: "Inseminadas 60+ dias — reconfirmação", color: "var(--amber)", reconfirmavel: true },
  { key: "novilhas_aptas_vazias", label: "Novilhas aptas vazias (≥300 kg)", color: "var(--green-light)" },
  { key: "verificar_aptidao", label: "Verificar aptidão (≥280 kg, nunca servida)", color: "var(--text-muted)" },
  { key: "novilhas_gestantes", label: "Novilhas gestantes", color: "var(--green-light)", extra: "dias_para_parto", acao: "toque_ou_reconfirmacao" },
  { key: "vacas_gestantes", label: "Vacas gestantes", color: "var(--green-light)", extra: "dias_para_parto", acao: "toque_ou_reconfirmacao" },
  { key: "verificar_pre_parto", label: "Verificar pré-parto (até 30 dias p/ parto)", color: "var(--red)", extra: "dias_para_parto" },
  { key: "vazias_por_diagnostico", label: "Vazias por diagnóstico (negativo/perda) — novo serviço", color: "var(--red)", extra: "motivo", vazia: true },
  { key: "pendentes_classificacao", label: "Pendentes de classificação (dado faltante)", color: "var(--text-muted)", extra: "motivo", lancar: true },
  // Só aparece (pílula com contagem > 0) quando o parâmetro
  // "usa_adesivo_deteccao_cio" está ativo — ver Configurações > Parâmetros.
  { key: "observacao_cio", label: "Observação de cio — adesivo de repasse (15–28 dias)", color: "var(--dourado)" },
];

/** Rótulo de Status por lista — a categoria em que o animal foi classificado
 * já É o status dele; só precisa de uma versão curta/legível por lista,
 * com a variação "atrasada" quando fizer sentido. */
function statusDe(cfg: typeof LISTAS[number], it: Item): string {
  switch (cfg.key) {
    case "inseminadas_1_29": return "Aguardando toque";
    case "inseminadas_30_59": return it.atrasada ? "Toque atrasado" : "Aguardando toque";
    case "inseminadas_60_mais": return it.atrasada ? "Reconfirmação atrasada" : "Aguardando reconfirmação";
    case "novilhas_aptas_vazias": return "Apta, vazia";
    case "verificar_aptidao": return "Verificar aptidão";
    case "novilhas_gestantes":
    case "vacas_gestantes": return "Gestante confirmada";
    case "verificar_pre_parto": return "Pré-parto";
    case "vazias_por_diagnostico": return "Vazia — aguardando novo serviço";
    case "pendentes_classificacao": return "Pendente de classificação";
    case "observacao_cio": return "Observação de cio (adesivo)";
    default: return cfg.label;
  }
}

/** Colunas/linhas de uma categoria — compartilhado entre a exportação por
 * categoria (dentro de ListaTabela) e a exportação combinada (várias
 * categorias escolhidas de uma vez, no cabeçalho da página). */
function colunasDaCategoria(cfg: typeof LISTAS[number]): ColunaExport[] {
  return [
    { header: "Matriz", key: "numero_matriz" }, { header: "Categoria", key: "categoria" },
    { header: "Lote atual", key: "lote_atual" }, { header: "Dias insem.", key: "dias_inseminada" },
    { header: "Inseminador", key: "inseminador" }, { header: "Nome do touro", key: "touro" },
    { header: "Tipo de inseminação", key: "tipo_servico" }, { header: "Método", key: "metodo" },
    { header: "Resultado 1º toque", key: "diagnostico_fmt" }, { header: "Data 1º toque", key: "data_diagnostico_fmt" },
    { header: "Res. Reconf.", key: "diagnostico_reconfirmacao_fmt" }, { header: "Data Reconfirmação", key: "data_reconfirmacao_fmt" },
    { header: "Status", key: "status_fmt" },
    ...(cfg.extra === "dias_para_parto" ? [{ header: "Dias p/ parto", key: "dias_para_parto" }] : []),
    ...(cfg.extra === "motivo" ? [{ header: "Motivo", key: "motivo" }] : []),
    ...(cfg.vazia ? [
      { header: "Data DG negativo", key: "data_dg_negativo_fmt" },
      { header: "DEL projetado no próximo serviço", key: "del_projetado_proximo_servico" },
      { header: "PEV projetado (dias restantes)", key: "pev_dias_restantes_projetado" },
      { header: "Data do próximo DG (estimada)", key: "proxima_data_dg_estimada_fmt" },
    ] : []),
  ];
}
function linhasDaCategoria(itens: Item[], cfg: typeof LISTAS[number]): Record<string, unknown>[] {
  return itens.map((it) => ({
    ...it,
    diagnostico_fmt: badgeTexto(it.diagnostico), data_diagnostico_fmt: fmtDia(it.data_diagnostico),
    diagnostico_reconfirmacao_fmt: badgeTexto(it.diagnostico_reconfirmacao), data_reconfirmacao_fmt: fmtDia(it.data_reconfirmacao),
    status_fmt: statusDe(cfg, it),
    data_dg_negativo_fmt: fmtDia(it.data_dg_negativo), proxima_data_dg_estimada_fmt: fmtDia(it.proxima_data_dg_estimada),
  }));
}

function FormReconfirmacao({ numero, onSalvo, onCancelar }: { numero: string; onSalvo: (numero: string) => void; onCancelar: () => void }) {
  const [data, setData] = useState(new Date().toISOString().slice(0, 10));
  const [resultado, setResultado] = useState<"positivo" | "negativo">("positivo");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.5rem", fontSize: "0.78rem" };

  async function salvar() {
    setSalvando(true); setErro(null);
    try {
      await registrarReconfirmacao({ numero_matriz: numero, data_reconfirmacao: data, resultado });
      onSalvo(numero);
    } catch (e: any) { setErro(e.message); } finally { setSalvando(false); }
  }

  return (
    <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
      <input type="date" style={selStyle} value={data} onChange={(e) => setData(e.target.value)} />
      <select style={selStyle} value={resultado} onChange={(e) => setResultado(e.target.value as any)}>
        <option value="positivo">Positivo (gestante confirmada)</option>
        <option value="negativo">Negativo (perda de prenhez)</option>
      </select>
      <button onClick={salvar} disabled={salvando} className="btn-primary" title="Salvar a reconfirmação de prenhez desta matriz" style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
        <Check size={13} /> {salvando ? "Salvando…" : "Salvar"}
      </button>
      <button onClick={onCancelar} title="Cancelar" style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
        <X size={13} />
      </button>
      {erro && <span style={{ color: "var(--red)", fontSize: "0.75rem" }}>{erro}</span>}
    </div>
  );
}

function FormEnviarDiagnostico({ numero, onEnviado, onCancelar }: { numero: string; onEnviado: (numero: string) => void; onCancelar: () => void }) {
  const [email, setEmail] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.5rem", fontSize: "0.78rem" };

  async function enviar() {
    if (!email.trim()) { setErro("Informe o e-mail do destinatário."); return; }
    setEnviando(true); setErro(null);
    try {
      await enviarDiagnosticoEmail(numero, email.trim());
      onEnviado(numero);
    } catch (e: any) { setErro(e.message); } finally { setEnviando(false); }
  }

  return (
    <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
      <input type="email" placeholder="e-mail do destinatário" style={{ ...selStyle, minWidth: "12rem" }} value={email} onChange={(e) => setEmail(e.target.value)} />
      <button onClick={enviar} disabled={enviando} className="btn-primary" title="Enviar o último diagnóstico desta matriz por e-mail" style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
        <Mail size={13} /> {enviando ? "Enviando…" : "Enviar"}
      </button>
      <button onClick={onCancelar} title="Cancelar" style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
        <X size={13} />
      </button>
      {erro && <span style={{ color: "var(--red)", fontSize: "0.75rem" }}>{erro}</span>}
    </div>
  );
}

/** "Lançar", em Pendentes de classificação: janela suspensa com as duas
 * frentes que podem estar faltando para esta matriz — sempre pode lançar
 * IA/cobertura; só oferece toque/retoque se já existir um serviço para
 * diagnosticar (tem_servico). Cada opção só leva para /lancamentos com a
 * matriz pré-selecionada — o lançamento em si acontece lá, sem duplicar a
 * lógica (vínculo financeiro, detecção de aborto etc.) aqui dentro. */
function PopupLancarPendente({ numero, temServico, onFechar }: { numero: string; temServico?: boolean; onFechar: () => void }) {
  const linkStyle: React.CSSProperties = {
    display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
    padding: "0.5rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)",
    background: "var(--surface-2)", color: "var(--text)", fontSize: "0.8rem", textDecoration: "none",
  };
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onFechar}>
      <div className="card" style={{ maxWidth: "360px", width: "90%" }} onClick={(e) => e.stopPropagation()}>
        <div className="card-header mb-2 flex items-center justify-between">
          <span>Lançar — matriz {numero}</span>
          <button onClick={onFechar} title="Fechar" style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={16} /></button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <Link href={`/lancamentos?ir=inseminacao&numero_matriz=${encodeURIComponent(numero)}`} style={linkStyle}>
            1. Lançar IA/cobertura <ArrowRight size={14} />
          </Link>
          {temServico ? (
            <Link href={`/lancamentos?ir=diagnostico&numero_matriz=${encodeURIComponent(numero)}`} style={linkStyle}>
              2. Lançar toque/retoque <ArrowRight size={14} />
            </Link>
          ) : (
            <div style={{ ...linkStyle, opacity: 0.5, cursor: "not-allowed" }} title="Esta matriz ainda não tem nenhum serviço reprodutivo lançado para diagnosticar">
              2. Lançar toque/retoque — sem serviço pendente
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

type DadosAgendaVet = {
  listas: Listas; totais: Record<string, number>; data_referencia: string; projetado?: boolean;
  ultimo_servico?: string | null; proxima_visita_reprodutiva?: string | null; intervalo_visita_reprodutiva?: number;
};

export default function AgendaVeterinarioPage() {
  const hoje = new Date().toISOString().slice(0, 10);
  const [dados, setDados] = useState<DadosAgendaVet | null>(null);
  const [dataRef, setDataRef] = useState(hoje);
  const [modo, setModo] = useState<"atual" | "projecao">("atual");
  const [error, setError] = useState<string | null>(null);
  const [abertas, setAbertas] = useState<Set<string>>(new Set());
  const [reconfirmando, setReconfirmando] = useState<string | null>(null);
  const [enviandoDg, setEnviandoDg] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [lancandoPendente, setLancandoPendente] = useState<Item | null>(null);

  // Janela suspensa em 2 passos para configurar a próxima visita reprodutiva
  // quando o modo "projeção" não tem para onde projetar (parâmetro em 0/vazio
  // ou nenhum serviço lançado ainda).
  const [passoAgendar, setPassoAgendar] = useState<null | "confirmar" | "definir">(null);
  const [novaData, setNovaData] = useState("");
  const [salvandoParam, setSalvandoParam] = useState(false);
  const [avisoParam, setAvisoParam] = useState<string | null>(null);

  // Exportação combinada — escolher uma, várias ou todas as categorias e
  // exportar juntas num único arquivo (Excel com uma aba por categoria, ou
  // PDF com uma seção por categoria), independente de a pílula estar aberta.
  const [painelExportar, setPainelExportar] = useState(false);
  const [selecionadasExport, setSelecionadasExport] = useState<Set<string>>(new Set());
  const [exportando, setExportando] = useState<"excel" | "pdf" | null>(null);

  function carregar() {
    fetchAgendaVeterinario(dataRef !== hoje ? dataRef : undefined).then(setDados).catch((e) => setError(e.message));
  }
  useEffect(carregar, [dataRef]);

  // A metadata (último serviço / próxima visita sugerida) não depende da
  // data de referência escolhida — assim que carrega uma vez, já sabemos se
  // o modo "projeção" tem para onde ir.
  useEffect(() => {
    if (modo === "atual") { setDataRef(hoje); return; }
    if (dados?.proxima_visita_reprodutiva) setDataRef(dados.proxima_visita_reprodutiva);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modo]);

  const toggle = (k: string) => setAbertas((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const intervaloImplicito = dados?.ultimo_servico && novaData
    ? Math.round((new Date(novaData + "T00:00:00").getTime() - new Date(dados.ultimo_servico + "T00:00:00").getTime()) / 86400000)
    : null;

  async function confirmarComoParametro() {
    if (intervaloImplicito == null) return;
    setSalvandoParam(true);
    try {
      await atualizarParametro("intervalo_visita_reprodutiva", intervaloImplicito);
      setPassoAgendar(null);
      setAvisoParam(null);
      setSucesso(`Intervalo da visita reprodutiva definido em ${intervaloImplicito} dia(s). A próxima visita passa a ser calculada automaticamente.`);
      setDataRef(novaData);
    } catch (e: any) {
      setAvisoParam(e.message);
    } finally {
      setSalvandoParam(false);
    }
  }

  function recusarComoParametro() {
    setPassoAgendar(null);
    setAvisoParam("Para que a próxima visita reprodutiva seja sugerida automaticamente, vá em Configurações > Parâmetros e defina o intervalo entre serviços.");
  }

  const categoriasComDados = dados ? LISTAS.filter((l) => (dados.totais[l.key] ?? 0) > 0) : [];
  const subtituloExport = dados
    ? `Data de referência: ${fmtDia(dados.data_referencia)}${dados.projetado ? " (cenário projetado)" : " (data atual)"}`
    : "";

  function abrirPainelExportar() {
    if (!painelExportar) setSelecionadasExport(new Set(categoriasComDados.map((l) => l.key)));
    setPainelExportar((v) => !v);
  }
  function alternarSelecao(key: string) {
    setSelecionadasExport((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n; });
  }
  function montarSecoes() {
    return categoriasComDados
      .filter((l) => selecionadasExport.has(l.key))
      .map((l) => ({ titulo: l.label, colunas: colunasDaCategoria(l), linhas: linhasDaCategoria(dados!.listas[l.key] ?? [], l) }));
  }
  async function exportarSelecionadas(formato: "excel" | "pdf") {
    setExportando(formato);
    try {
      const secoes = montarSecoes();
      if (formato === "excel") {
        await exportarMultiExcel("Agenda Reprodutiva", secoes, "agenda_reprodutiva_combinado");
      } else {
        await exportarFichaPDF("Agenda Reprodutiva", subtituloExport, secoes, "agenda_reprodutiva_combinado");
      }
    } catch {
      // erro já mostrado ao usuário dentro de exportarMultiExcel/exportarFichaPDF (lib/export.ts)
    } finally {
      setExportando(null);
    }
  }

  if (error) return <div className="alert-critico"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>;
  if (!dados) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  return (
    <div className="animate-in">
      <div className="mb-4">
        <h2 className="text-xl font-bold flex items-center gap-2"><Stethoscope size={20} style={{ color: "var(--dourado)" }} /> Agenda Reprodutiva</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Roteiro da visita reprodutiva, na data de referência {fmtDia(dados.data_referencia)}. Machos e bezerras nunca
          entram em nenhuma lista; os demais só entram (exceto em "Verificar aptidão") ao atingir 15 meses e 300 kg.
          Toque entre 30–59 dias; reconfirmação a partir de 60 dias.
        </p>
        <div className="flex items-center gap-4 mt-2" style={{ flexWrap: "wrap" }}>
          <label style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
            <input type="radio" name="modoAgendaRepro" checked={modo === "atual"} onChange={() => setModo("atual")} /> Data atual
          </label>
          <label style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
            <input type="radio" name="modoAgendaRepro" checked={modo === "projecao"} onChange={() => setModo("projecao")} /> Projeção — próxima visita reprodutiva agendada
          </label>
          <button onClick={abrirPainelExportar} disabled={categoriasComDados.length === 0}
            title="Exportar a lista completa, escolhendo quais categorias incluir"
            style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem", padding: "0.35rem 0.7rem", borderRadius: "var(--r-sm)",
              border: "1px solid var(--dourado)", background: painelExportar ? "rgba(212,160,23,0.15)" : "transparent",
              color: "var(--dourado-light)", cursor: categoriasComDados.length === 0 ? "not-allowed" : "pointer", opacity: categoriasComDados.length === 0 ? 0.5 : 1 }}>
            <Download size={14} /> Exportar lista completa
          </button>
        </div>
      </div>

      {painelExportar && (
        <div className="card mb-3" style={{ padding: "0.9rem 1rem" }}>
          <div className="flex items-center justify-between mb-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>Exportar lista completa</span>
            <div className="flex items-center gap-2">
              <button onClick={() => setSelecionadasExport(new Set(categoriasComDados.map((l) => l.key)))}
                style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
                Selecionar todas
              </button>
              <button onClick={() => setSelecionadasExport(new Set())}
                style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
                Nenhuma
              </button>
            </div>
          </div>
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>{subtituloExport}</p>
          <div className="flex flex-wrap gap-3 mb-3">
            {categoriasComDados.map((l) => (
              <label key={l.key} style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem", color: "var(--text)", cursor: "pointer" }}>
                <input type="checkbox" checked={selecionadasExport.has(l.key)} onChange={() => alternarSelecao(l.key)} />
                {l.label} ({dados.totais[l.key]})
              </label>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => exportarSelecionadas("excel")} disabled={selecionadasExport.size === 0 || exportando !== null}
              className="btn-primary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem" }}>
              {exportando === "excel" ? "Gerando…" : "Exportar Excel"}
            </button>
            <button onClick={() => exportarSelecionadas("pdf")} disabled={selecionadasExport.size === 0 || exportando !== null}
              className="btn-primary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem" }}>
              {exportando === "pdf" ? "Gerando…" : "Exportar PDF"}
            </button>
            {selecionadasExport.size === 0 && <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Selecione ao menos uma categoria.</span>}
          </div>
        </div>
      )}

      {modo === "projecao" && !dados.proxima_visita_reprodutiva && (
        <div className="mb-3" style={{ background: "rgba(198,58,58,0.12)", border: "1px solid var(--red)", borderRadius: "var(--r-sm)", padding: "0.75rem 1rem", fontSize: "0.85rem" }}>
          <div className="flex items-center gap-2" style={{ color: "var(--red)" }}>
            <AlertTriangle size={16} /><span>Não há próxima visita reprodutiva agendada.</span>
          </div>
          {avisoParam ? (
            <p style={{ marginTop: "0.4rem", color: "var(--text-muted)" }}>{avisoParam}</p>
          ) : (
            <button onClick={() => setPassoAgendar("confirmar")} className="btn-primary mt-2"
              style={{ fontSize: "0.78rem", padding: "0.35rem 0.7rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
              <CalendarPlus size={14} /> Deseja agendar a próxima visita reprodutiva?
            </button>
          )}
        </div>
      )}

      {dados.projetado && (
        <div className="mb-3 flex items-center gap-2" style={{ background: "rgba(212,160,23,0.15)", border: "1px solid var(--dourado)", borderRadius: "var(--r-sm)", padding: "0.6rem 1rem", color: "var(--dourado-light)", fontSize: "0.85rem" }}>
          <AlertTriangle size={16} />
          <span>
            Cenário projetado para {fmtDia(dados.data_referencia)} — classificação simulada com os dados já lançados
            hoje, como se aquela fosse a data da visita reprodutiva; novos lançamentos até lá podem mudar o resultado.
          </span>
        </div>
      )}

      {sucesso && (
        <div className="mb-3 flex items-center gap-2" style={{ background: "rgba(45, 138, 86, 0.15)", border: "1px solid var(--green-light)", borderRadius: "var(--r-sm)", padding: "0.6rem 1rem", color: "var(--green-light)", fontSize: "0.85rem" }}>
          <Check size={16} /><span>{sucesso}</span>
        </div>
      )}

      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        {LISTAS.map((l) => {
          const n = dados.totais[l.key] ?? 0;
          const ativa = abertas.has(l.key);
          if (n === 0) return null;
          return (
            <button key={l.key} onClick={() => toggle(l.key)}
              style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
                border: "1px solid " + (ativa ? l.color : "var(--border)"),
                background: ativa ? "rgba(94,26,46,0.25)" : "transparent",
                color: ativa ? l.color : "var(--text-muted)", fontWeight: ativa ? 700 : 500 }}>
              {ativa ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              {l.label} ({n})
            </button>
          );
        })}
      </div>

      {LISTAS.filter((l) => abertas.has(l.key) && (dados.totais[l.key] ?? 0) > 0).map((l) => (
        <ListaTabela key={l.key} cfg={l} itens={dados.listas[l.key] ?? []}
          reconfirmando={reconfirmando} setReconfirmando={setReconfirmando}
          onSalvo={(numero) => { setReconfirmando(null); setSucesso(`Reconfirmação registrada para a matriz ${numero}.`); carregar(); }}
          enviandoDg={enviandoDg} setEnviandoDg={setEnviandoDg}
          onDgEnviado={(numero) => { setEnviandoDg(null); setSucesso(`Diagnóstico enviado por e-mail (matriz ${numero}).`); }}
          onLancar={setLancandoPendente} />
      ))}

      {LISTAS.every((l) => (dados.totais[l.key] ?? 0) === 0) && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum animal para classificar no momento.</p>
      )}

      {lancandoPendente && (
        <PopupLancarPendente numero={lancandoPendente.numero_matriz} temServico={lancandoPendente.tem_servico} onFechar={() => setLancandoPendente(null)} />
      )}

      {passoAgendar === "confirmar" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div className="card" style={{ maxWidth: "420px", width: "90%" }}>
            <div className="card-header mb-2">Agendar a próxima visita reprodutiva?</div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
              Não há uma próxima visita reprodutiva agendada. Deseja definir a data agora?
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setPassoAgendar(null)} style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>Não</button>
              <button onClick={() => { setNovaData(""); setPassoAgendar("definir"); }} className="btn-primary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem" }}>Sim</button>
            </div>
          </div>
        </div>
      )}

      {passoAgendar === "definir" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div className="card" style={{ maxWidth: "460px", width: "90%" }}>
            <div className="card-header mb-2">Data da próxima visita reprodutiva</div>
            {!dados.ultimo_servico ? (
              <>
                <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
                  Ainda não há nenhum serviço reprodutivo lançado — não é possível calcular o intervalo automaticamente.
                  Vá em Configurações &gt; Parâmetros e defina o intervalo entre serviços manualmente.
                </p>
                <div className="flex justify-end">
                  <button onClick={() => setPassoAgendar(null)} className="btn-primary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem" }}>Entendi</button>
                </div>
              </>
            ) : (
              <>
                <label style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "block", marginBottom: "0.75rem" }}>
                  Escreva a data da próxima visita reprodutiva
                  <input type="date" value={novaData} onChange={(e) => setNovaData(e.target.value)} min={dados.ultimo_servico}
                    style={{ display: "block", marginTop: "0.3rem", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.85rem" }} />
                </label>
                {intervaloImplicito != null && intervaloImplicito > 0 && (
                  <div className="mb-3" style={{ background: "rgba(212,160,23,0.15)", border: "1px solid var(--dourado)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem", color: "var(--dourado-light)", fontSize: "0.8rem" }}>
                    Essa data considerará <strong>{intervaloImplicito} dia(s)</strong> de intervalo entre o último serviço
                    ({fmtDia(dados.ultimo_servico)}) e o serviço lançado. Deseja colocar esse intervalo como parâmetro?
                  </div>
                )}
                {avisoParam && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{avisoParam}</p>}
                <div className="flex justify-end gap-2">
                  <button onClick={() => setPassoAgendar(null)} style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>Cancelar</button>
                  <button onClick={recusarComoParametro} disabled={intervaloImplicito == null || intervaloImplicito <= 0}
                    style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
                    Não
                  </button>
                  <button onClick={confirmarComoParametro} disabled={salvandoParam || intervaloImplicito == null || intervaloImplicito <= 0} className="btn-primary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem" }}>
                    {salvandoParam ? "Salvando…" : "Sim, salvar como parâmetro"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Botão de ação de registro (toque/reconfirmação) por linha — cada lista usa
// no máximo um: link para /lancamentos pré-selecionando a matriz (toque/DG
// antecipado, mesmo padrão de "Ir para Inseminação") ou o mini-form inline já
// existente (reconfirmação, que não precisa de tela própria).
function botaoRegistroLabel(cfg: typeof LISTAS[number]): string {
  if (cfg.key === "inseminadas_1_29") return "Registrar DG antecipado";
  return "Registrar toque";
}
function CelulaAcaoRegistro({ cfg, it, reconfirmando, setReconfirmando, onSalvo }: {
  cfg: typeof LISTAS[number]; it: Item;
  reconfirmando: string | null; setReconfirmando: (n: string | null) => void; onSalvo: (numero: string) => void;
}) {
  const linkBtn: React.CSSProperties = { fontSize: "0.72rem", padding: "0.25rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--dourado)", background: "transparent", color: "var(--dourado-light)", cursor: "pointer", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.3rem" };
  if (cfg.reconfirmavel) {
    if (reconfirmando === it.numero_matriz) {
      return <FormReconfirmacao numero={it.numero_matriz} onSalvo={onSalvo} onCancelar={() => setReconfirmando(null)} />;
    }
    return <button onClick={() => setReconfirmando(it.numero_matriz)} style={{ ...linkBtn, border: "1px solid var(--dourado)" }}>Registrar reconfirmação</button>;
  }
  if (cfg.acao === "toque") {
    return <Link href={`/lancamentos?ir=diagnostico&numero_matriz=${encodeURIComponent(it.numero_matriz)}`} style={linkBtn}>{botaoRegistroLabel(cfg)}</Link>;
  }
  if (cfg.acao === "toque_ou_reconfirmacao") {
    if (!it.tocada) {
      return <Link href={`/lancamentos?ir=diagnostico&numero_matriz=${encodeURIComponent(it.numero_matriz)}`} style={linkBtn}>Registrar toque</Link>;
    }
    if (!it.reconfirmada) {
      if (reconfirmando === it.numero_matriz) {
        return <FormReconfirmacao numero={it.numero_matriz} onSalvo={onSalvo} onCancelar={() => setReconfirmando(null)} />;
      }
      return <button onClick={() => setReconfirmando(it.numero_matriz)} style={linkBtn}>Registrar reconfirmação</button>;
    }
    return <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>—</span>;
  }
  return null;
}

function ListaTabela({ cfg, itens, reconfirmando, setReconfirmando, onSalvo, enviandoDg, setEnviandoDg, onDgEnviado, onLancar }: {
  cfg: typeof LISTAS[number]; itens: Item[];
  reconfirmando: string | null; setReconfirmando: (n: string | null) => void; onSalvo: (numero: string) => void;
  enviandoDg: string | null; setEnviandoDg: (n: string | null) => void; onDgEnviado: (numero: string) => void;
  onLancar: (it: Item) => void;
}) {
  const ord = useOrdenacao(itens);
  const colunasExport = colunasDaCategoria(cfg);
  const linhasExport = linhasDaCategoria(ord.linhasOrdenadas, cfg);
  const temAcaoRegistro = cfg.reconfirmavel || !!cfg.acao;
  return (
    <div className="card mb-3" style={{ overflowX: "auto" }}>
      <div className="card-header mb-2 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <span>{cfg.label}</span>
        <ExportarBotoes titulo={`Agenda Reprodutiva — ${cfg.label}`} colunas={colunasExport} linhas={linhasExport} nomeArquivoBase={`agenda_veterinario_${cfg.key}`} />
      </div>
      <table className="fazenda-table">
        <thead><tr>
          <ThOrdenavel label="Matriz" campo="numero_matriz" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Categoria" campo="categoria" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Lote atual" campo="lote_atual" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Dias insem." campo="dias_inseminada" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Inseminador" campo="inseminador" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Nome do touro" campo="touro" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Tipo" campo="tipo_servico" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Método" campo="metodo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Result. 1º toque" campo="diagnostico" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Data 1º toque" campo="data_diagnostico" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Res. Reconf." campo="diagnostico_reconfirmacao" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Data Reconfirmação" campo="data_reconfirmacao" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <th>Status</th>
          {cfg.extra === "dias_para_parto" && <ThOrdenavel label="Dias p/ parto" campo="dias_para_parto" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />}
          {cfg.extra === "motivo" && <ThOrdenavel label="Motivo" campo="motivo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />}
          {cfg.vazia && <ThOrdenavel label="Data DG negativo" campo="data_dg_negativo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />}
          {cfg.vazia && <ThOrdenavel label="DEL projetado no próximo serviço" campo="del_projetado_proximo_servico" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />}
          {cfg.vazia && <th>Novo serviço</th>}
          {cfg.lancar && <th>Lançar</th>}
          {temAcaoRegistro && <th></th>}
          <th>DG por e-mail</th>
        </tr></thead>
        <tbody>
          {ord.linhasOrdenadas.map((it) => (
            <tr key={it.numero_matriz}>
              <td style={{ fontWeight: 700 }}>{it.numero_matriz}</td>
              <td style={{ fontSize: "0.78rem", textTransform: "capitalize" }}>{it.categoria}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.lote_atual ?? "—"}</td>
              <td>{it.dias_inseminada ?? "—"}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.inseminador ?? "—"}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.touro ?? "—"}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.tipo_servico ?? "—"}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.metodo ?? "—"}</td>
              <td><BadgeDiag v={it.diagnostico} /></td>
              <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(it.data_diagnostico)}</td>
              <td><BadgeDiag v={it.diagnostico_reconfirmacao} /></td>
              <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(it.data_reconfirmacao)}</td>
              <td style={{ fontSize: "0.78rem" }}>{statusDe(cfg, it)}</td>
              {cfg.extra === "dias_para_parto" && <td>{it.dias_para_parto ?? "—"}</td>}
              {cfg.extra === "motivo" && <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{it.motivo}</td>}
              {cfg.vazia && <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(it.data_dg_negativo)}</td>}
              {cfg.vazia && (
                <td style={{ fontSize: "0.78rem" }}>
                  {it.del_projetado_proximo_servico ?? "—"}
                  {it.pev_dias_restantes_projetado != null && (
                    <div style={{ color: "var(--red)", fontSize: "0.7rem", fontWeight: 600 }}>PEV projet. {it.pev_dias_restantes_projetado} dias</div>
                  )}
                </td>
              )}
              {cfg.vazia && (
                <td>
                  <Link href={`/lancamentos?ir=inseminacao&numero_matriz=${encodeURIComponent(it.numero_matriz)}`}
                    style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--dourado)", background: "transparent", color: "var(--dourado-light)", cursor: "pointer", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.3rem", whiteSpace: "nowrap" }}>
                    Novo Serviço
                  </Link>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.68rem", marginTop: "0.2rem", whiteSpace: "nowrap" }}>
                    Próx. DG estim.: {fmtDia(it.proxima_data_dg_estimada)}
                  </div>
                </td>
              )}
              {cfg.lancar && (
                <td>
                  <button onClick={() => onLancar(it)} title="Lançar IA/cobertura ou toque/retoque para esta matriz"
                    style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--dourado)", background: "transparent", color: "var(--dourado-light)", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                    <ClipboardEdit size={13} /> Lançar
                  </button>
                </td>
              )}
              {temAcaoRegistro && (
                <td>
                  <CelulaAcaoRegistro cfg={cfg} it={it} reconfirmando={reconfirmando} setReconfirmando={setReconfirmando} onSalvo={onSalvo} />
                </td>
              )}
              <td>
                {enviandoDg === it.numero_matriz ? (
                  <FormEnviarDiagnostico numero={it.numero_matriz} onEnviado={onDgEnviado} onCancelar={() => setEnviandoDg(null)} />
                ) : (
                  <button onClick={() => setEnviandoDg(it.numero_matriz)} title="Enviar o último diagnóstico de gestação desta matriz por e-mail"
                    style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                    <Mail size={13} /> Enviar
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
