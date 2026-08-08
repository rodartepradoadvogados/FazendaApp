"use client";
import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Stethoscope, AlertTriangle, Check, X, Mail, CalendarPlus, Download } from "lucide-react";
import { fetchAgendaVeterinario, registrarReconfirmacao, enviarDiagnosticoEmail, atualizarParametro } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { exportarFichaPDF, exportarMultiExcel, type ColunaExport } from "@/lib/export";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

type Item = {
  numero_matriz: string; categoria: string; peso: number | null;
  dias_inseminada: number | null; data_servico: string | null;
  tocada: boolean; reconfirmada: boolean;
  diagnostico: string | null; diagnostico_reconfirmacao: string | null;
  atrasada?: boolean; dias_para_parto?: number | null; motivo?: string;
};
type Listas = Record<string, Item[]>;

const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");

const LISTAS: { key: string; label: string; color: string; extra?: "atrasada" | "dias_para_parto" | "motivo"; reconfirmavel?: boolean }[] = [
  { key: "inseminadas_1_29", label: "Inseminadas 1–29 dias", color: "var(--blue)" },
  { key: "inseminadas_30_59", label: "Inseminadas 30–59 dias — toque", color: "var(--dourado)", extra: "atrasada" },
  { key: "inseminadas_60_mais", label: "Inseminadas 60+ dias — reconfirmação", color: "var(--amber)", extra: "atrasada", reconfirmavel: true },
  { key: "novilhas_aptas_vazias", label: "Novilhas aptas vazias (≥300 kg)", color: "var(--green-light)" },
  { key: "verificar_aptidao", label: "Verificar aptidão (≥280 kg, nunca servida)", color: "var(--text-muted)" },
  { key: "novilhas_gestantes", label: "Novilhas gestantes", color: "var(--green-light)", extra: "dias_para_parto" },
  { key: "vacas_gestantes", label: "Vacas gestantes", color: "var(--green-light)", extra: "dias_para_parto" },
  { key: "verificar_pre_parto", label: "Verificar pré-parto (até 30 dias p/ parto)", color: "var(--red)", extra: "dias_para_parto" },
  { key: "vazias_por_diagnostico", label: "Vazias por diagnóstico (negativo/perda) — novo serviço", color: "var(--red)", extra: "motivo" },
  { key: "pendentes_classificacao", label: "Pendentes de classificação (dado faltante)", color: "var(--text-muted)", extra: "motivo" },
  // Só aparece (pílula com contagem > 0) quando o parâmetro
  // "usa_adesivo_deteccao_cio" está ativo — ver Configurações > Parâmetros.
  { key: "observacao_cio", label: "Observação de cio — adesivo de repasse (15–28 dias)", color: "var(--dourado)" },
];

/** Colunas/linhas de uma categoria — compartilhado entre a exportação por
 * categoria (dentro de ListaTabela) e a exportação combinada (várias
 * categorias escolhidas de uma vez, no cabeçalho da página). */
function colunasDaCategoria(cfg: typeof LISTAS[number]): ColunaExport[] {
  return [
    { header: "Matriz", key: "numero_matriz" }, { header: "Categoria", key: "categoria" },
    { header: "Peso (kg)", key: "peso" }, { header: "Dias insem.", key: "dias_inseminada" },
    { header: "Data serviço", key: "data_servico_fmt" }, { header: "Toque", key: "tocada_fmt" },
    { header: "Reconfirmação", key: "reconfirmada_fmt" },
    ...(cfg.extra === "atrasada" ? [{ header: "Situação", key: "situacao_fmt" }] : []),
    ...(cfg.extra === "dias_para_parto" ? [{ header: "Dias p/ parto", key: "dias_para_parto" }] : []),
    ...(cfg.extra === "motivo" ? [{ header: "Motivo", key: "motivo" }] : []),
  ];
}
function linhasDaCategoria(itens: Item[]): Record<string, unknown>[] {
  return itens.map((it) => ({
    ...it, data_servico_fmt: fmtDia(it.data_servico), tocada_fmt: it.tocada ? "Sim" : "—",
    reconfirmada_fmt: it.reconfirmada ? "Sim" : "—", situacao_fmt: it.atrasada ? "Atrasada" : "No prazo",
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
      .map((l) => ({ titulo: l.label, colunas: colunasDaCategoria(l), linhas: linhasDaCategoria(dados!.listas[l.key] ?? []) }));
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
            <input type="radio" name="modoAgendaRepro" checked={modo === "projecao"} onChange={() => setModo("projecao")} /> Projeção — próximo serviço agendado
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
            <AlertTriangle size={16} /><span>Não há próximo serviço agendado.</span>
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
            hoje, como se aquela fosse a data da visita (o "próximo serviço"); novos lançamentos até lá podem mudar o resultado.
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
          onDgEnviado={(numero) => { setEnviandoDg(null); setSucesso(`Diagnóstico enviado por e-mail (matriz ${numero}).`); }} />
      ))}

      {LISTAS.every((l) => (dados.totais[l.key] ?? 0) === 0) && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum animal para classificar no momento.</p>
      )}

      {passoAgendar === "confirmar" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div className="card" style={{ maxWidth: "420px", width: "90%" }}>
            <div className="card-header mb-2">Agendar a próxima visita reprodutiva?</div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
              Não há um próximo serviço agendado. Deseja definir a data da próxima visita reprodutiva agora?
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
            <div className="card-header mb-2">Data do próximo serviço</div>
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
                  Escreva a data do próximo serviço
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

function ListaTabela({ cfg, itens, reconfirmando, setReconfirmando, onSalvo, enviandoDg, setEnviandoDg, onDgEnviado }: {
  cfg: typeof LISTAS[number]; itens: Item[];
  reconfirmando: string | null; setReconfirmando: (n: string | null) => void; onSalvo: (numero: string) => void;
  enviandoDg: string | null; setEnviandoDg: (n: string | null) => void; onDgEnviado: (numero: string) => void;
}) {
  const ord = useOrdenacao(itens);
  const colunasExport = colunasDaCategoria(cfg);
  const linhasExport = linhasDaCategoria(ord.linhasOrdenadas);
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
          <ThOrdenavel label="Peso (kg)" campo="peso" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Dias insem." campo="dias_inseminada" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Data serviço" campo="data_servico" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Toque" campo="tocada" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ThOrdenavel label="Reconfirmação" campo="reconfirmada" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          {cfg.extra === "atrasada" && <ThOrdenavel label="Situação" campo="atrasada" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />}
          {cfg.extra === "dias_para_parto" && <ThOrdenavel label="Dias p/ parto" campo="dias_para_parto" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />}
          {cfg.extra === "motivo" && <ThOrdenavel label="Motivo" campo="motivo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />}
          {cfg.reconfirmavel && <th></th>}
          <th>DG por e-mail</th>
        </tr></thead>
        <tbody>
          {ord.linhasOrdenadas.map((it) => (
            <tr key={it.numero_matriz}>
              <td style={{ fontWeight: 700 }}>{it.numero_matriz}</td>
              <td style={{ fontSize: "0.78rem", textTransform: "capitalize" }}>{it.categoria}</td>
              <td>{it.peso ?? "—"}</td>
              <td>{it.dias_inseminada ?? "—"}</td>
              <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(it.data_servico)}</td>
              <td>{it.tocada ? <Check size={14} style={{ color: "var(--green-light)" }} /> : "—"}</td>
              <td>{it.reconfirmada ? <Check size={14} style={{ color: "var(--green-light)" }} /> : "—"}</td>
              {cfg.extra === "atrasada" && (
                <td>{it.atrasada ? <span style={{ color: "var(--red)", fontWeight: 600, fontSize: "0.75rem" }}>Atrasada</span> : <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>No prazo</span>}</td>
              )}
              {cfg.extra === "dias_para_parto" && <td>{it.dias_para_parto ?? "—"}</td>}
              {cfg.extra === "motivo" && <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{it.motivo}</td>}
              {cfg.reconfirmavel && (
                <td>
                  {reconfirmando === it.numero_matriz ? (
                    <FormReconfirmacao numero={it.numero_matriz} onSalvo={onSalvo} onCancelar={() => setReconfirmando(null)} />
                  ) : (
                    <button onClick={() => setReconfirmando(it.numero_matriz)}
                      style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--dourado)", background: "transparent", color: "var(--dourado-light)", cursor: "pointer" }}>
                      Registrar reconfirmação
                    </button>
                  )}
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
