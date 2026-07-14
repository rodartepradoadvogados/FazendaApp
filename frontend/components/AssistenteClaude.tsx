"use client";
import { useEffect, useRef, useState } from "react";
import { Sparkles, X, Send } from "lucide-react";
import { perguntarAssistente } from "@/lib/api";

type Mensagem = { autor: "usuario" | "assistente" | "erro"; texto: string };

/**
 * Botão flutuante do Assistente Claude (protótipo) — abre um painel de chat
 * simples que consulta os dados reais da fazenda via tool-use no backend
 * (/assistente/perguntar). Restrito a administradores enquanto o recurso
 * está em avaliação (mesmo gate do backend).
 */
export default function AssistenteClaude() {
  const [aberto, setAberto] = useState(false);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [historico, setHistorico] = useState<any[]>([]);
  const [pergunta, setPergunta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, aberto]);

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
        title="Assistente Claude (protótipo)"
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
          width: "22rem", maxWidth: "calc(100vw - 2rem)", height: "28rem", maxHeight: "calc(100vh - 8rem)",
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "12px",
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)", display: "flex", flexDirection: "column", overflow: "hidden",
        }}>
          <div style={{ padding: "0.7rem 1rem", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Sparkles size={16} style={{ color: "var(--dourado-light)" }} />
            <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>Assistente Claude</span>
            <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginLeft: "auto" }}>protótipo</span>
          </div>

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
        </div>
      )}
    </>
  );
}
