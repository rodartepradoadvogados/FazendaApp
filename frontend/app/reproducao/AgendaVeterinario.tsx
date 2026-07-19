"use client";
import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Stethoscope, AlertTriangle, Check, X, Mail } from "lucide-react";
import { fetchAgendaVeterinario, registrarReconfirmacao, enviarDiagnosticoEmail } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
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
  { key: "verificar_pre_parto", label: "Verificar pré-parto (31–60 dias p/ parto)", color: "var(--red)", extra: "dias_para_parto" },
  { key: "vazias_por_diagnostico", label: "Vazias por diagnóstico (negativo/perda) — novo serviço", color: "var(--red)", extra: "motivo" },
  { key: "pendentes_classificacao", label: "Pendentes de classificação (dado faltante)", color: "var(--text-muted)", extra: "motivo" },
  // Só aparece (pílula com contagem > 0) quando o parâmetro
  // "usa_adesivo_deteccao_cio" está ativo — ver Configurações > Parâmetros.
  { key: "observacao_cio", label: "Observação de cio — adesivo de repasse (15–28 dias)", color: "var(--dourado)" },
];

function FormReconfirmacao({ numero, onSalvo, onCancelar }: { numero: string; onSalvo: (numero: string) => void; onCancelar: () => void }) {
  const [data, setData] = useState(new Date().toISOString().slice(0, 10));
  const [resultado, setResultado] = useState<"positivo" | "negativo">("positivo");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.3rem 0.5rem", fontSize: "0.78rem" };

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
      <button onClick={onCancelar} title="Cancelar" style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", border: "1px solid var(--border)", borderRadius: "6px", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
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
  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.3rem 0.5rem", fontSize: "0.78rem" };

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
      <button onClick={onCancelar} title="Cancelar" style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", border: "1px solid var(--border)", borderRadius: "6px", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
        <X size={13} />
      </button>
      {erro && <span style={{ color: "var(--red)", fontSize: "0.75rem" }}>{erro}</span>}
    </div>
  );
}

export default function AgendaVeterinarioPage() {
  const hoje = new Date().toISOString().slice(0, 10);
  const [dados, setDados] = useState<{ listas: Listas; totais: Record<string, number>; data_referencia: string; projetado?: boolean } | null>(null);
  const [dataRef, setDataRef] = useState(hoje);
  const [error, setError] = useState<string | null>(null);
  const [abertas, setAbertas] = useState<Set<string>>(new Set());
  const [reconfirmando, setReconfirmando] = useState<string | null>(null);
  const [enviandoDg, setEnviandoDg] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  function carregar() {
    fetchAgendaVeterinario(dataRef !== hoje ? dataRef : undefined).then(setDados).catch((e) => setError(e.message));
  }
  useEffect(carregar, [dataRef]);

  const toggle = (k: string) => setAbertas((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  if (error) return <div className="alert-critico"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>;
  if (!dados) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  return (
    <div className="animate-in">
      <div className="mb-4">
        <h2 className="text-xl font-bold flex items-center gap-2"><Stethoscope size={20} style={{ color: "var(--dourado)" }} /> Agenda do veterinário</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Roteiro da visita reprodutiva, na data de referência {fmtDia(dados.data_referencia)}. Machos e bezerras nunca
          entram em nenhuma lista; os demais só entram (exceto em "Verificar aptidão") ao atingir 15 meses e 300 kg.
          Toque entre 30–59 dias; reconfirmação a partir de 60 dias.
        </p>
        <div className="flex items-center gap-2 mt-2" style={{ flexWrap: "wrap" }}>
          <label style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            Data de referência
            <input type="date" value={dataRef} onChange={(e) => setDataRef(e.target.value)}
              style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.3rem 0.5rem", fontSize: "0.8rem" }} />
          </label>
          {dataRef !== hoje && (
            <button onClick={() => setDataRef(hoje)}
              style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", borderRadius: "6px", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
              Voltar para hoje
            </button>
          )}
        </div>
      </div>

      {dados.projetado && (
        <div className="mb-3 flex items-center gap-2" style={{ background: "rgba(212,160,23,0.15)", border: "1px solid var(--dourado)", borderRadius: "8px", padding: "0.6rem 1rem", color: "var(--dourado-light)", fontSize: "0.85rem" }}>
          <AlertTriangle size={16} />
          <span>
            Cenário projetado para {fmtDia(dados.data_referencia)} — classificação simulada com os dados já lançados
            hoje, como se aquela fosse a data da visita (o "próximo serviço"); novos lançamentos até lá podem mudar o resultado.
          </span>
        </div>
      )}

      {sucesso && (
        <div className="mb-3 flex items-center gap-2" style={{ background: "rgba(45, 138, 86, 0.15)", border: "1px solid var(--green-light)", borderRadius: "8px", padding: "0.6rem 1rem", color: "var(--green-light)", fontSize: "0.85rem" }}>
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
    </div>
  );
}

function ListaTabela({ cfg, itens, reconfirmando, setReconfirmando, onSalvo, enviandoDg, setEnviandoDg, onDgEnviado }: {
  cfg: typeof LISTAS[number]; itens: Item[];
  reconfirmando: string | null; setReconfirmando: (n: string | null) => void; onSalvo: (numero: string) => void;
  enviandoDg: string | null; setEnviandoDg: (n: string | null) => void; onDgEnviado: (numero: string) => void;
}) {
  const ord = useOrdenacao(itens);
  const colunasExport = [
    { header: "Matriz", key: "numero_matriz" }, { header: "Categoria", key: "categoria" },
    { header: "Peso (kg)", key: "peso" }, { header: "Dias insem.", key: "dias_inseminada" },
    { header: "Data serviço", key: "data_servico_fmt" }, { header: "Toque", key: "tocada_fmt" },
    { header: "Reconfirmação", key: "reconfirmada_fmt" },
    ...(cfg.extra === "atrasada" ? [{ header: "Situação", key: "situacao_fmt" }] : []),
    ...(cfg.extra === "dias_para_parto" ? [{ header: "Dias p/ parto", key: "dias_para_parto" }] : []),
    ...(cfg.extra === "motivo" ? [{ header: "Motivo", key: "motivo" }] : []),
  ];
  const linhasExport = ord.linhasOrdenadas.map((it) => ({
    ...it, data_servico_fmt: fmtDia(it.data_servico), tocada_fmt: it.tocada ? "Sim" : "—",
    reconfirmada_fmt: it.reconfirmada ? "Sim" : "—", situacao_fmt: it.atrasada ? "Atrasada" : "No prazo",
  }));
  return (
    <div className="card mb-3" style={{ overflowX: "auto" }}>
      <div className="card-header mb-2 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <span>{cfg.label}</span>
        <ExportarBotoes titulo={`Agenda do veterinário — ${cfg.label}`} colunas={colunasExport} linhas={linhasExport} nomeArquivoBase={`agenda_veterinario_${cfg.key}`} />
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
                      style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", borderRadius: "6px", border: "1px solid var(--dourado)", background: "transparent", color: "var(--dourado-light)", cursor: "pointer" }}>
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
                    style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", borderRadius: "6px", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.3rem" }}>
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
