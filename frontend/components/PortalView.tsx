"use client";
import { useEffect, useMemo, useState } from "react";
import { MessageSquarePlus, Mail, ClipboardCheck, Send, CheckCircle2, ArrowLeft, DownloadCloud } from "lucide-react";
import { TabBar } from "@/components/ui";
import { PortalMencaoInput } from "@/components/PortalMencaoInput";
import {
  ABAS_PORTAL, ehAdmin,
  fetchPortalPermissoes, fetchPortalDestinatarios, fetchPortalMensagensPendentes, fetchPortalRelatoriosDisponiveis,
  enviarPortalMensagem, marcarPortalMensagemLida, resolverPortalMensagem, responderPortalMensagem,
  enviarPortalEmail, delegarPortalTarefa,
  fetchPortalOpcoesExportacao, solicitarPortalExportacao,
  fetchFotoCampoUrl,
  type PortalDestinatario, type PortalMensagem, type PortalOpcaoExportacao,
} from "@/lib/api";

type SubAba = "comunicacao" | "exportar";
type Acao = "mensagem" | "email" | "tarefa" | null;

export function PortalView() {
  const admin = ehAdmin();
  const [subAba, setSubAba] = useState<SubAba>("comunicacao");
  const [acao, setAcao] = useState<Acao>(null);
  const [destinatarios, setDestinatarios] = useState<PortalDestinatario[]>([]);
  const [podeDelegar, setPodeDelegar] = useState(false);
  const [pendentes, setPendentes] = useState<PortalMensagem[]>([]);

  const carregar = () => {
    fetchPortalDestinatarios().then(setDestinatarios).catch(() => {});
    fetchPortalPermissoes().then((d) => setPodeDelegar(d.pode_delegar_tarefa)).catch(() => {});
    fetchPortalMensagensPendentes().then(setPendentes).catch(() => {});
  };
  useEffect(() => { carregar(); }, []);

  const abas = [
    { id: "comunicacao" as SubAba, label: "Comunicação" },
    ...(admin ? [{ id: "exportar" as SubAba, label: "Exportar" }] : []),
  ];

  return (
    <div>
      <TabBar abas={abas} ativa={subAba} onChange={(a) => { setSubAba(a); setAcao(null); }} />

      {subAba === "comunicacao" && (
        acao ? (
          <div>
            <button className="btn-ghost" style={{ marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setAcao(null)}>
              <ArrowLeft size={15} /> Voltar
            </button>
            {acao === "mensagem" && <FormEnviarMensagem destinatarios={destinatarios} onEnviado={() => { setAcao(null); carregar(); }} />}
            {acao === "email" && <FormEnviarEmail destinatarios={destinatarios} onEnviado={() => setAcao(null)} />}
            {acao === "tarefa" && <FormDelegarTarefa destinatarios={destinatarios} onEnviado={() => { setAcao(null); carregar(); }} />}
          </div>
        ) : (
          <div>
            <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
              <CartaoAcao icone={<MessageSquarePlus size={22} />} cor="var(--dourado)" titulo="Enviar mensagem"
                descricao="Comunicado interno, com opção de pedir retorno." onClick={() => setAcao("mensagem")} />
              <CartaoAcao icone={<Mail size={22} />} cor="var(--azul, #2563eb)" titulo="Enviar e-mail"
                descricao="E-mail livre ou relatório gerencial em anexo." onClick={() => setAcao("email")} />
              {podeDelegar && (
                <CartaoAcao icone={<ClipboardCheck size={22} />} cor="var(--verde-light, #16a34a)" titulo="Delegar tarefa"
                  descricao="Vira pendência na Agenda e na central de alertas do destinatário." onClick={() => setAcao("tarefa")} />
              )}
            </div>

            <div className="mt-6">
              <div className="card-header" style={{ marginBottom: "0.5rem" }}>Pendentes de você resolver</div>
              {pendentes.length === 0 ? (
                <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nada pendente no Portal.</p>
              ) : (
                <div className="space-y-2">
                  {pendentes.map((m) => (
                    <ItemPendente key={m.id} m={m} onAtualizado={carregar} />
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      )}

      {subAba === "exportar" && <ExportarCarrinho />}
    </div>
  );
}

function CartaoAcao({ icone, cor, titulo, descricao, onClick }: { icone: React.ReactNode; cor: string; titulo: string; descricao: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="card" style={{
      textAlign: "left", cursor: "pointer", border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: "0.5rem",
    }}>
      <span style={{
        width: 42, height: 42, borderRadius: "50%", background: cor, color: "#fff",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {icone}
      </span>
      <span style={{ fontWeight: 700 }}>{titulo}</span>
      <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{descricao}</span>
    </button>
  );
}

function ItemPendente({ m, onAtualizado }: { m: PortalMensagem; onAtualizado: () => void }) {
  const [resposta, setResposta] = useState("");
  const [respondendo, setRespondendo] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  async function marcarLida() {
    setOcupado(true);
    try { await marcarPortalMensagemLida(m.id); onAtualizado(); } finally { setOcupado(false); }
  }
  async function resolver() {
    setOcupado(true);
    try { await resolverPortalMensagem(m.id); onAtualizado(); } finally { setOcupado(false); }
  }
  async function enviarResposta() {
    if (!resposta.trim()) return;
    setOcupado(true);
    try { await responderPortalMensagem(m.id, { corpo: resposta.trim() }); onAtualizado(); } finally { setOcupado(false); }
  }

  return (
    <div className="card" style={{ padding: "0.75rem" }}>
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase" }}>
        {m.tipo === "tarefa" ? "Tarefa" : m.tipo === "foto" ? "Foto" : "Mensagem"} de {m.remetente}{m.aba ? ` · ${m.aba}` : ""}
      </div>
      {m.tipo === "foto" && m.foto_campo_id != null && <MiniaturaFotoCampo id={m.foto_campo_id} />}
      <div style={{ fontSize: "0.88rem", margin: "0.3rem 0" }}>{m.corpo}</div>
      {m.tipo === "tarefa" ? (
        <button className="btn-primary" disabled={ocupado} onClick={marcarLida} style={{ fontSize: "0.8rem" }}>
          <CheckCircle2 size={14} /> Marcar como lida
        </button>
      ) : m.pede_retorno ? (
        respondendo ? (
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <input value={resposta} onChange={(e) => setResposta(e.target.value)} placeholder="Sua resposta…"
              style={{ flex: 1, border: "1px solid var(--border)", borderRadius: 6, padding: "0.35rem 0.5rem", background: "var(--surface-2)", color: "var(--text)", fontSize: "0.82rem" }} />
            <button className="btn-primary" disabled={ocupado || !resposta.trim()} onClick={enviarResposta} style={{ fontSize: "0.8rem" }}>Enviar</button>
          </div>
        ) : (
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button className="btn-primary" disabled={ocupado} onClick={() => setRespondendo(true)} style={{ fontSize: "0.8rem" }}>Responder</button>
            <button className="btn-ghost" disabled={ocupado} onClick={resolver} style={{ fontSize: "0.8rem" }}>Marcar resolvido</button>
          </div>
        )
      ) : (
        <button className="btn-primary" disabled={ocupado} onClick={marcarLida} style={{ fontSize: "0.8rem" }}>
          <CheckCircle2 size={14} /> Marcar como lida
        </button>
      )}
    </div>
  );
}

function MiniaturaFotoCampo({ id }: { id: number }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    let urlLocal: string | null = null;
    fetchFotoCampoUrl(id).then((u) => { if (!cancelado) { urlLocal = u; setUrl(u); } }).catch(() => {});
    return () => { cancelado = true; if (urlLocal) URL.revokeObjectURL(urlLocal); };
  }, [id]);

  if (!url) return null;
  return <img src={url} alt="Foto do campo" style={{ width: "100%", maxHeight: 180, objectFit: "cover", borderRadius: 8, display: "block", marginTop: "0.4rem" }} />;
}

function FormEnviarMensagem({ destinatarios, onEnviado }: { destinatarios: PortalDestinatario[]; onEnviado: () => void }) {
  const [ids, setIds] = useState<number[]>([]);
  const [aba, setAba] = useState("");
  const [corpo, setCorpo] = useState("");
  const [pedeRetorno, setPedeRetorno] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar() {
    setErro(null);
    if (!ids.length) return setErro("Selecione ao menos um destinatário.");
    if (!corpo.trim()) return setErro("Escreva a mensagem.");
    setEnviando(true);
    try {
      await enviarPortalMensagem({ destinatarios_usuario_id: ids, aba: aba || null, corpo: corpo.trim(), pede_retorno: pedeRetorno });
      onEnviado();
    } catch (e: any) { setErro(e.message || "Erro ao enviar."); } finally { setEnviando(false); }
  }

  return (
    <div className="card" style={{ maxWidth: 520, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div className="card-header">Enviar mensagem</div>
      <Campo label="Para">
        <PortalMencaoInput opcoes={destinatarios} selecionados={ids} onChange={setIds} />
      </Campo>
      <Campo label="Aba relacionada (opcional)">
        <select value={aba} onChange={(e) => setAba(e.target.value)} style={selectStyle}>
          <option value="">— nenhuma —</option>
          {ABAS_PORTAL.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
        </select>
      </Campo>
      <Campo label="Mensagem">
        <textarea value={corpo} onChange={(e) => setCorpo(e.target.value)} rows={4} style={{ ...selectStyle, resize: "vertical" }} />
      </Campo>
      <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem" }}>
        <input type="checkbox" checked={pedeRetorno} onChange={(e) => setPedeRetorno(e.target.checked)} />
        Pedir retorno (só sai dos alertas do destinatário quando ele responder ou marcar resolvido)
      </label>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      <button className="btn-primary" disabled={enviando} onClick={enviar} style={{ alignSelf: "flex-start" }}>
        <Send size={14} /> Enviar
      </button>
    </div>
  );
}

function FormEnviarEmail({ destinatarios, onEnviado }: { destinatarios: PortalDestinatario[]; onEnviado: () => void }) {
  const [ids, setIds] = useState<number[]>([]);
  const [assunto, setAssunto] = useState("");
  const [corpo, setCorpo] = useState("");
  const [modo, setModo] = useState<"livre" | "relatorio">("livre");
  const [relatorios, setRelatorios] = useState<Record<string, string>>({});
  const [relatorio, setRelatorio] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => { fetchPortalRelatoriosDisponiveis().then(setRelatorios).catch(() => {}); }, []);

  async function enviar() {
    setErro(null); setAviso(null);
    if (!ids.length) return setErro("Selecione ao menos um destinatário.");
    if (!assunto.trim()) return setErro("Informe o assunto.");
    if (modo === "relatorio" && (!relatorio || !dataInicio || !dataFim)) return setErro("Selecione o relatório e o período.");
    setEnviando(true);
    try {
      const destinatariosNomes = ids.map((id) => destinatarios.find((d) => d.id === id)?.nome).filter(Boolean).join(", ");
      await enviarPortalEmail({
        destinatarios_usuario_id: ids, assunto: assunto.trim(), corpo: corpo.trim() || undefined,
        ...(modo === "relatorio" ? { relatorio, data_inicio: dataInicio, data_fim: dataFim } : {}),
      });
      setAviso(`Em breve o resultado será enviado para ${destinatariosNomes || "o(s) destinatário(s)"}.`);
      setTimeout(onEnviado, 1500);
    } catch (e: any) { setErro(e.message || "Erro ao enviar."); } finally { setEnviando(false); }
  }

  return (
    <div className="card" style={{ maxWidth: 520, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div className="card-header">Enviar e-mail</div>
      <Campo label="Para (pode incluir você mesmo)">
        <PortalMencaoInput opcoes={destinatarios} selecionados={ids} onChange={setIds} />
      </Campo>
      <Campo label="Assunto">
        <input value={assunto} onChange={(e) => setAssunto(e.target.value)} style={selectStyle} />
      </Campo>
      <TabBar abas={[{ id: "livre" as const, label: "Mensagem livre" }, { id: "relatorio" as const, label: "Enviar relatório" }]} ativa={modo} onChange={setModo} />
      {modo === "livre" ? (
        <Campo label="Mensagem (opcional)">
          <textarea value={corpo} onChange={(e) => setCorpo(e.target.value)} rows={4} style={{ ...selectStyle, resize: "vertical" }} />
        </Campo>
      ) : (
        <>
          <Campo label="Relatório">
            <select value={relatorio} onChange={(e) => setRelatorio(e.target.value)} style={selectStyle}>
              <option value="">— selecione —</option>
              {Object.entries(relatorios).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </Campo>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Campo label="De"><input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} style={selectStyle} /></Campo>
            <Campo label="Até"><input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} style={selectStyle} /></Campo>
          </div>
        </>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      {aviso && <p style={{ color: "var(--verde-light, #16a34a)", fontSize: "0.82rem" }}>{aviso}</p>}
      <button className="btn-primary" disabled={enviando} onClick={enviar} style={{ alignSelf: "flex-start" }}>
        <Send size={14} /> Enviar
      </button>
    </div>
  );
}

function FormDelegarTarefa({ destinatarios, onEnviado }: { destinatarios: PortalDestinatario[]; onEnviado: () => void }) {
  const [ids, setIds] = useState<number[]>([]);
  const [corpo, setCorpo] = useState("");
  const [data, setData] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar() {
    setErro(null);
    if (!ids.length) return setErro("Selecione ao menos um destinatário.");
    if (!corpo.trim()) return setErro("Descreva a tarefa.");
    setEnviando(true);
    try {
      await delegarPortalTarefa({ destinatarios_usuario_id: ids, corpo: corpo.trim(), data_evento: data || undefined });
      onEnviado();
    } catch (e: any) { setErro(e.message || "Erro ao enviar."); } finally { setEnviando(false); }
  }

  return (
    <div className="card" style={{ maxWidth: 520, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div className="card-header">Delegar tarefa</div>
      <Campo label="Para">
        <PortalMencaoInput opcoes={destinatarios} selecionados={ids} onChange={setIds} />
      </Campo>
      <Campo label="Data (opcional — padrão hoje)">
        <input type="date" value={data} onChange={(e) => setData(e.target.value)} style={selectStyle} />
      </Campo>
      <Campo label="Tarefa">
        <textarea value={corpo} onChange={(e) => setCorpo(e.target.value)} rows={4} style={{ ...selectStyle, resize: "vertical" }} />
      </Campo>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      <button className="btn-primary" disabled={enviando} onClick={enviar} style={{ alignSelf: "flex-start" }}>
        <Send size={14} /> Delegar
      </button>
    </div>
  );
}

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.8rem", color: "var(--text-muted)", flex: 1 }}>
      {label}
      {children}
    </label>
  );
}

const selectStyle: React.CSSProperties = {
  border: "1px solid var(--border)", borderRadius: 6, padding: "0.4rem 0.5rem",
  background: "var(--surface-2)", color: "var(--text)", fontSize: "0.85rem", width: "100%",
};

// Carrinho de exportação: cada item marcado é uma tabela (ou relatório) que
// vai para o ZIP; itens com tem_periodo ganham um filtro de/até opcional —
// mesma lógica dos filtros do local de origem do dado.
function ExportarCarrinho() {
  const [opcoes, setOpcoes] = useState<PortalOpcaoExportacao[]>([]);
  const [selecionados, setSelecionados] = useState<Record<string, boolean>>({});
  const [periodos, setPeriodos] = useState<Record<string, { data_inicio: string; data_fim: string }>>({});
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => { fetchPortalOpcoesExportacao().then(setOpcoes).catch(() => {}); }, []);

  const marcados = useMemo(() => opcoes.filter((o) => selecionados[o.chave]), [opcoes, selecionados]);

  function alternar(chave: string) {
    setSelecionados((s) => ({ ...s, [chave]: !s[chave] }));
  }
  function mudarPeriodo(chave: string, campo: "data_inicio" | "data_fim", valor: string) {
    setPeriodos((p) => {
      const atual = p[chave] || { data_inicio: "", data_fim: "" };
      return { ...p, [chave]: { ...atual, [campo]: valor } };
    });
  }

  async function enviar() {
    setErro(null); setAviso(null);
    if (!marcados.length) return setErro("Marque ao menos um item do carrinho.");
    setEnviando(true);
    try {
      const itens = marcados.map((o) => ({
        chave: o.chave,
        ...(o.tem_periodo ? { data_inicio: periodos[o.chave]?.data_inicio || undefined, data_fim: periodos[o.chave]?.data_fim || undefined } : {}),
      }));
      const r = await solicitarPortalExportacao({ itens });
      setAviso(r.mensagem);
    } catch (e: any) { setErro(e.message || "Erro ao solicitar exportação."); } finally { setEnviando(false); }
  }

  return (
    <div className="card" style={{ maxWidth: 640, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div className="card-header">Exportar dados do sistema</div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>
        Marque os bancos de dados que quer exportar — funciona como um backup: os arquivos saem em CSV, um por item, dentro de um único ZIP.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {opcoes.map((o) => {
          const on = !!selecionados[o.chave];
          return (
            <div key={o.chave} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "0.6rem 0.75rem" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", cursor: "pointer" }}>
                <input type="checkbox" checked={on} onChange={() => alternar(o.chave)} />
                {o.rotulo}
              </label>
              {on && o.tem_periodo && (
                <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", paddingLeft: "1.6rem" }}>
                  <Campo label="De (opcional)">
                    <input type="date" value={periodos[o.chave]?.data_inicio || ""} onChange={(e) => mudarPeriodo(o.chave, "data_inicio", e.target.value)} style={selectStyle} />
                  </Campo>
                  <Campo label="Até (opcional)">
                    <input type="date" value={periodos[o.chave]?.data_fim || ""} onChange={(e) => mudarPeriodo(o.chave, "data_fim", e.target.value)} style={selectStyle} />
                  </Campo>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      {aviso && <p style={{ color: "var(--verde-light, #16a34a)", fontSize: "0.82rem" }}>{aviso}</p>}
      <button className="btn-primary" disabled={enviando || !marcados.length} onClick={enviar} style={{ alignSelf: "flex-start" }}>
        <DownloadCloud size={14} /> Enviar ({marcados.length})
      </button>
    </div>
  );
}
