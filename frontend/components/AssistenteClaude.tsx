"use client";
import { useEffect, useRef, useState } from "react";
import { Sparkles, X, Send, BookOpen, MessageCircle, Plus, Pencil, Trash2, Check } from "lucide-react";
import {
  perguntarAssistente, fetchAssistenteAcesso, fetchEnsinamentos, criarEnsinamento, atualizarEnsinamento,
  excluirEnsinamento, type AssistenteEnsinamento,
} from "@/lib/api";

type Mensagem = { autor: "usuario" | "assistente" | "erro"; texto: string };
type Aba = "conversa" | "ensinamentos";

/**
 * Botão flutuante do Assistente Virtual (protótipo) — abre um painel de chat
 * (tool-use nos dados reais, /assistente/perguntar), aberto a qualquer
 * usuário logado da fazenda piloto. Quem é admin ganha também a aba
 * Ensinamentos (base de conhecimento em texto — mesmos endpoints
 * /assistente/ensinamentos que o app usa, ver
 * components/mobile/menu/Assistente.tsx). Ver GET /assistente/acesso —
 * `liberado` decide se o botão aparece, `pode_treinar` se a aba aparece.
 */
export default function AssistenteClaude() {
  const [liberado, setLiberado] = useState(false);
  const [podeTreinar, setPodeTreinar] = useState(false);
  const [aberto, setAberto] = useState(false);
  const [aba, setAba] = useState<Aba>("conversa");
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [historico, setHistorico] = useState<any[]>([]);
  const [pergunta, setPergunta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchAssistenteAcesso()
      .then((r) => { setLiberado(r.liberado); setPodeTreinar(r.pode_treinar); })
      .catch(() => { setLiberado(false); setPodeTreinar(false); });
  }, []);

  useEffect(() => {
    const reduzMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    fimRef.current?.scrollIntoView({ behavior: reduzMovimento ? "auto" : "smooth" });
  }, [mensagens, aberto]);

  if (!liberado) return null;

  const enviar = async () => {
    const texto = pergunta.trim();
    if (!texto || enviando) return;
    setPergunta("");
    setMensagens((m) => [...m, { autor: "usuario", texto }]);
    setEnviando(true);
    try {
      const r = await perguntarAssistente(texto, historico);
      setMensagens((m) => [...m, { autor: "assistente", texto: r.resposta }]);
      setHistorico(r.historico);
    } catch (e: any) {
      setMensagens((m) => [...m, { autor: "erro", texto: e.message || "Erro ao consultar o assistente." }]);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setAberto((v) => !v)}
        title="Assistente Virtual (protótipo)"
        style={{
          position: "fixed", bottom: "1.5rem", right: "1.5rem", zIndex: 70,
          width: "3.2rem", height: "3.2rem", borderRadius: "50%", border: "none",
          background: "var(--dourado)", color: "#1a1a1a", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
        }}
      >
        {aberto ? <X size={22} /> : <Sparkles size={22} />}
      </button>

      {aberto && (
        <div style={{
          position: "fixed", bottom: "5.2rem", right: "1.5rem", zIndex: 70,
          width: "24rem", maxWidth: "calc(100vw - 2rem)", height: "30rem", maxHeight: "calc(100vh - 8rem)",
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "12px",
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)", display: "flex", flexDirection: "column", overflow: "hidden",
        }}>
          <div style={{ padding: "0.7rem 1rem 0", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.6rem" }}>
              <Sparkles size={16} style={{ color: "var(--dourado-light)" }} />
              <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>Assistente Virtual</span>
              <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginLeft: "auto" }}>protótipo</span>
            </div>
            {podeTreinar && (
              <div style={{ display: "flex", gap: "0.4rem" }}>
                <AbaBotao ativa={aba === "conversa"} onClick={() => setAba("conversa")} icone={<MessageCircle size={13} />} label="Conversa" />
                <AbaBotao ativa={aba === "ensinamentos"} onClick={() => setAba("ensinamentos")} icone={<BookOpen size={13} />} label="Ensinamentos" />
              </div>
            )}
          </div>

          {aba === "conversa" || !podeTreinar ? (
            <>
              <div style={{ flex: 1, overflowY: "auto", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {!mensagens.length && (
                  <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>
                    Pergunte sobre indicadores, um animal (pelo número), agenda, financeiro, estoque, sanidade ou
                    análise reprodutiva — as respostas usam só os dados que você tem permissão de ver no site.
                  </p>
                )}
                {mensagens.map((m, i) => (
                  <div key={i} style={{
                    alignSelf: m.autor === "usuario" ? "flex-end" : "flex-start",
                    maxWidth: "85%", padding: "0.5rem 0.7rem", borderRadius: "10px", fontSize: "0.8rem", whiteSpace: "pre-wrap",
                    background: m.autor === "usuario" ? "var(--dourado)" : m.autor === "erro" ? "var(--red)" : "var(--surface-2)",
                    color: m.autor === "usuario" ? "#1a1a1a" : m.autor === "erro" ? "#fff" : "var(--text)",
                  }}>
                    {m.texto}
                  </div>
                ))}
                {enviando && <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Consultando…</p>}
                <div ref={fimRef} />
              </div>

              <div style={{ padding: "0.6rem", borderTop: "1px solid var(--border)", display: "flex", gap: "0.4rem" }}>
                <input
                  value={pergunta}
                  onChange={(e) => setPergunta(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") enviar(); }}
                  placeholder="Pergunte algo…"
                  style={{ flex: 1, background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.4rem 0.6rem", fontSize: "0.8rem" }}
                />
                <button onClick={enviar} disabled={enviando || !pergunta.trim()} className="btn-primary" style={{ padding: "0.4rem 0.6rem" }}>
                  <Send size={14} />
                </button>
              </div>
            </>
          ) : (
            <EnsinamentosPainel />
          )}
        </div>
      )}
    </>
  );
}

function AbaBotao({ ativa, onClick, icone, label }: { ativa: boolean; onClick: () => void; icone: React.ReactNode; label: string }) {
  return (
    <button
      type="button" onClick={onClick}
      style={{
        display: "inline-flex", alignItems: "center", gap: "0.3rem", padding: "0.35rem 0.6rem",
        fontSize: "0.72rem", fontWeight: 600, borderRadius: "999px 999px 0 0", border: "none", cursor: "pointer",
        background: ativa ? "var(--surface-2)" : "transparent",
        color: ativa ? "var(--text)" : "var(--text-muted)",
      }}
    >
      {icone} {label}
    </button>
  );
}

/** Base de conhecimento em texto que o dono mantém — mesmos endpoints
 *  /assistente/ensinamentos que components/mobile/menu/Assistente.tsx usa. */
function EnsinamentosPainel() {
  const [itens, setItens] = useState<AssistenteEnsinamento[] | null>(null);
  const [erro, setErro] = useState("");
  const [criando, setCriando] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [titulo, setTitulo] = useState("");
  const [texto, setTexto] = useState("");

  async function carregar() {
    try {
      setItens(await fetchEnsinamentos());
    } catch (e: any) {
      setErro(e.message || "Erro ao carregar ensinamentos.");
    }
  }
  useEffect(() => { carregar(); }, []);

  function abrirNovo() {
    setEditandoId(null);
    setTitulo("");
    setTexto("");
    setCriando(true);
  }

  function abrirEdicao(e: AssistenteEnsinamento) {
    setCriando(false);
    setEditandoId(e.id);
    setTitulo(e.titulo);
    setTexto(e.texto);
  }

  function fecharForm() {
    setCriando(false);
    setEditandoId(null);
  }

  async function salvar() {
    if (!titulo.trim() || !texto.trim()) { setErro("Preencha título e texto."); return; }
    setErro("");
    try {
      if (editandoId != null) {
        await atualizarEnsinamento(editandoId, { titulo: titulo.trim(), texto: texto.trim(), ativo: true });
      } else {
        await criarEnsinamento({ titulo: titulo.trim(), texto: texto.trim() });
      }
      fecharForm();
      await carregar();
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar ensinamento.");
    }
  }

  async function alternarAtivo(e: AssistenteEnsinamento) {
    setErro("");
    try {
      await atualizarEnsinamento(e.id, { titulo: e.titulo, texto: e.texto, ativo: !e.ativo });
      await carregar();
    } catch (err: any) {
      setErro(err.message || "Erro ao atualizar ensinamento.");
    }
  }

  async function excluir(e: AssistenteEnsinamento) {
    if (!window.confirm(`Apagar o ensinamento "${e.titulo}"?`)) return;
    setErro("");
    try {
      await excluirEnsinamento(e.id);
      await carregar();
    } catch (err: any) {
      setErro(err.message || "Erro ao apagar ensinamento.");
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
    borderRadius: "8px", padding: "0.4rem 0.6rem", fontSize: "0.8rem", boxSizing: "border-box",
  };

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "0.75rem" }}>
      <p style={{ color: "var(--text-muted)", fontSize: "0.76rem", marginBottom: "0.7rem" }}>
        Texto livre que o Assistente sempre considera antes de responder — não é treinamento de IA, é só uma
        base de conhecimento sobre esta fazenda que você mantém.
      </p>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", marginBottom: "0.6rem", fontWeight: 600 }}>{erro}</p>}

      {(criando || editandoId != null) ? (
        <div style={{ border: "1px solid var(--border)", borderRadius: "10px", padding: "0.6rem", marginBottom: "0.7rem" }}>
          <input value={titulo} onChange={(e) => setTitulo(e.target.value)}
            placeholder="Título curto (ex.: Regra do lote 04)" style={{ ...inputStyle, marginBottom: "0.5rem" }} />
          <textarea value={texto} onChange={(e) => setTexto(e.target.value)}
            placeholder="O que o Assistente deve saber…" rows={4}
            style={{ ...inputStyle, marginBottom: "0.5rem", resize: "vertical" }} />
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <button type="button" onClick={salvar} className="btn-primary" style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.3rem", padding: "0.4rem" }}>
              <Check size={14} /> Salvar
            </button>
            <button type="button" onClick={fecharForm} style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.3rem", padding: "0.4rem", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", cursor: "pointer", fontSize: "0.8rem" }}>
              <X size={14} /> Cancelar
            </button>
          </div>
        </div>
      ) : (
        <button type="button" onClick={abrirNovo} style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", marginBottom: "0.8rem", padding: "0.4rem 0.7rem", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", cursor: "pointer", fontSize: "0.8rem" }}>
          <Plus size={14} /> Novo ensinamento
        </button>
      )}

      {itens === null ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Carregando…</p>
      ) : itens.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", textAlign: "center", padding: "1rem 0" }}>Nenhum ensinamento cadastrado ainda.</p>
      ) : (
        itens.map((e) => (
          <div key={e.id} style={{ border: "1px solid var(--border)", borderRadius: "10px", padding: "0.55rem 0.65rem", marginBottom: "0.5rem", opacity: e.ativo ? 1 : 0.6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", flex: 1, minWidth: 0 }}>{e.titulo}</span>
              <div style={{ display: "flex", gap: "0.4rem", flexShrink: 0 }}>
                <button type="button" onClick={() => abrirEdicao(e)} aria-label="Editar" style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 0, display: "flex" }}>
                  <Pencil size={14} />
                </button>
                <button type="button" onClick={() => excluir(e)} aria-label="Apagar" style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--red)", padding: 0, display: "flex" }}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.25rem", whiteSpace: "pre-wrap" }}>{e.texto}</p>
            <button type="button" onClick={() => alternarAtivo(e)} style={{ marginTop: "0.4rem", fontSize: "0.7rem", padding: "0.2rem 0.5rem", borderRadius: "999px", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
              {e.ativo ? "Ativo — clique para desativar" : "Desativado — clique para ativar"}
            </button>
          </div>
        ))
      )}
    </div>
  );
}
