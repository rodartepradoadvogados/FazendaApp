"use client";
// Sub-tela: Assistente Virtual — conversa (tool-use nos dados reais da
// fazenda) + gestão dos "ensinamentos" (base de conhecimento em texto que
// entra no prompt do Assistente, ver backend/fazenda/rules/assistente.py).
// Restrita ao dono da fazenda (ou usuário liberado por ele) — o item de menu
// já só aparece para quem tem acesso (ver app/app/menu/page.tsx), mas os
// endpoints também travam sozinhos (403) se alguém chegar aqui sem permissão.
import { useEffect, useRef, useState } from "react";
import { Sparkles, Send, BookOpen, Plus, Pencil, Trash2, X, Check } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { LinhaPills, MobPill } from "@/components/mobile/lancar/comum";
import {
  perguntarAssistente, fetchEnsinamentos, criarEnsinamento, atualizarEnsinamento, excluirEnsinamento,
  type AssistenteEnsinamento,
} from "@/lib/api";

type Mensagem = { autor: "usuario" | "assistente" | "erro"; texto: string };
type Aba = "conversa" | "ensinamentos";

export default function Assistente({ onVoltar }: { onVoltar: () => void }) {
  const [aba, setAba] = useState<Aba>("conversa");
  return (
    <div>
      <MobVoltar titulo="Assistente Virtual" onVoltar={onVoltar} />
      <LinhaPills>
        <MobPill ativa={aba === "conversa"} onClick={() => setAba("conversa")}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}><Sparkles size={14} /> Conversa</span>
        </MobPill>
        <MobPill ativa={aba === "ensinamentos"} onClick={() => setAba("ensinamentos")}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}><BookOpen size={14} /> Ensinamentos</span>
        </MobPill>
      </LinhaPills>
      {aba === "conversa" ? <ConversaView /> : <EnsinamentosView />}
    </div>
  );
}

// ── Conversa ──────────────────────────────────────────────────────────────
function ConversaView() {
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [historico, setHistorico] = useState<any[]>([]);
  const [pergunta, setPergunta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens]);

  async function enviar() {
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
  }

  return (
    <div>
      {!mensagens.length && (
        <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem", marginBottom: "0.8rem" }}>
          Pergunte sobre indicadores, um animal, agenda, financeiro, estoque, sanidade ou análise reprodutiva —
          as respostas usam só os dados que você tem permissão de ver.
        </p>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxHeight: "60vh", overflowY: "auto", marginBottom: "0.8rem" }}>
        {mensagens.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.autor === "usuario" ? "flex-end" : "flex-start",
            maxWidth: "85%", padding: "0.6rem 0.8rem", borderRadius: "var(--r-app)", fontSize: "0.86rem", whiteSpace: "pre-wrap",
            background: m.autor === "usuario" ? "var(--mob-vinho)" : m.autor === "erro" ? "var(--mob-vermelho)" : "var(--mob-surface-2)",
            color: m.autor === "usuario" ? "var(--mob-dourado-pale)" : m.autor === "erro" ? "#fff" : "var(--mob-text)",
          }}>
            {m.texto}
          </div>
        ))}
        {enviando && <p style={{ color: "var(--mob-muted)", fontSize: "0.82rem" }}>Consultando…</p>}
        <div ref={fimRef} />
      </div>

      <div style={{ display: "flex", gap: "0.5rem" }}>
        <input
          className="mob-input"
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") enviar(); }}
          placeholder="Pergunte algo…"
          style={{ flex: 1 }}
        />
        <button type="button" onClick={enviar} disabled={enviando || !pergunta.trim()} className="mob-btn" style={{ width: "auto", padding: "0.9rem 1rem" }}>
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}

// ── Ensinamentos ──────────────────────────────────────────────────────────
function EnsinamentosView() {
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

  return (
    <div>
      <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem", marginBottom: "0.8rem" }}>
        Texto livre que o Assistente sempre considera antes de responder — não é treinamento de IA, é só uma
        base de conhecimento sobre esta fazenda que você mantém.
      </p>

      {erro && <p style={{ color: "var(--mob-vermelho)", fontSize: "0.85rem", marginBottom: "0.6rem", fontWeight: 600 }}>{erro}</p>}

      {(criando || editandoId != null) ? (
        <MobCard style={{ marginBottom: "0.8rem" }}>
          <input className="mob-input" value={titulo} onChange={(e) => setTitulo(e.target.value)}
            placeholder="Título curto (ex.: Regra do lote 04)" style={{ marginBottom: "0.6rem" }} />
          <textarea className="mob-input" value={texto} onChange={(e) => setTexto(e.target.value)}
            placeholder="O que o Assistente deve saber…" rows={4} style={{ marginBottom: "0.6rem", resize: "vertical" }} />
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" onClick={salvar} className="mob-btn" style={{ flex: 1 }}>
              <Check size={16} /> Salvar
            </button>
            <button type="button" onClick={fecharForm} className="mob-btn-2" style={{ flex: 1 }}>
              <X size={16} /> Cancelar
            </button>
          </div>
        </MobCard>
      ) : (
        <button type="button" onClick={abrirNovo} className="mob-btn-2" style={{ marginBottom: "0.9rem" }}>
          <Plus size={16} /> Novo ensinamento
        </button>
      )}

      {itens === null ? (
        <p style={{ color: "var(--mob-muted)", padding: "1rem 0" }}>Carregando…</p>
      ) : itens.length === 0 ? (
        <p style={{ color: "var(--mob-muted)", padding: "1rem 0", textAlign: "center" }}>Nenhum ensinamento cadastrado ainda.</p>
      ) : (
        itens.map((e, idx) => (
          <MobCard key={e.id} alt={(idx % 2) as 0 | 1} style={{ marginBottom: "0.5rem", opacity: e.ativo ? 1 : 0.6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.9rem", flex: 1, minWidth: 0 }}>{e.titulo}</span>
              <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
                <button type="button" onClick={() => abrirEdicao(e)} aria-label="Editar" style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--mob-muted)", padding: 0, display: "flex" }}>
                  <Pencil size={16} />
                </button>
                <button type="button" onClick={() => excluir(e)} aria-label="Apagar" style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--mob-vermelho)", padding: 0, display: "flex" }}>
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
            <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.3rem", whiteSpace: "pre-wrap" }}>{e.texto}</p>
            <button type="button" onClick={() => alternarAtivo(e)} className="mob-pill" style={{ marginTop: "0.5rem" }}>
              {e.ativo ? "Ativo — toque para desativar" : "Desativado — toque para ativar"}
            </button>
          </MobCard>
        ))
      )}
    </div>
  );
}
