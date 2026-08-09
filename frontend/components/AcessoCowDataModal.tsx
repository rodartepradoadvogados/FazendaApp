"use client";
// Fluxo de 3 janelas para abrir uma sessão de suporte a partir do Painel
// CowData > Suporte > Acesso CowData — pedido explícito do usuário (ago/2026):
//   1) lista de fazendas → "Deseja entrar na Fazenda [nome]?"
//   2) "Plano: [nome] — módulos: [...]" → Confirmar
//   3) Motivo (lista fechada) + Assunto do chamado (livre) + Observação
//      (opcional), com nota sobre limite de 30 min e numeração de protocolo
//      automática → "Confirmar e entrar"
// Reaproveita a mecânica já existente de pedido→sessão (entrarComoSuporte,
// ver lib/api.ts) — só a apresentação em 3 passos é nova.
import { useEffect, useMemo, useState } from "react";
import { LogIn, ShieldAlert } from "lucide-react";
import { Modal } from "@/components/Modal";
import {
  fetchMotivosAcessoSuporte, fetchFazendasCofre, entrarComoSuporte,
  type FazendaCofre,
} from "@/lib/api";

const COR = {
  cartao: "#262E39", borda: "#39424F", mudo: "#9CA6B4", dourado: "#6B7F99", texto: "#F1F3F5", vermelho: "#b5544a",
};
const inputStyle: React.CSSProperties = {
  width: "100%", background: "#1A2028", border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)",
  padding: "0.5rem 0.65rem", color: COR.texto, fontSize: "0.85rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.72rem", color: COR.mudo, display: "block", marginBottom: "0.3rem" };
const btnPrimario: React.CSSProperties = {
  background: COR.dourado, color: "#1A2028", border: "none", borderRadius: "var(--r-sm)", padding: "0.55rem 1.1rem",
  fontSize: "0.85rem", fontWeight: 700, cursor: "pointer",
};
const btnGhost: React.CSSProperties = {
  background: "transparent", color: COR.mudo, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)",
  padding: "0.55rem 1.1rem", fontSize: "0.85rem", cursor: "pointer",
};

type Passo = "fazenda" | "plano" | "motivo";

export function AcessoCowDataModal({ onClose, onEntrou }: { onClose: () => void; onEntrou: () => void }) {
  const [passo, setPasso] = useState<Passo>("fazenda");
  const [fazendas, setFazendas] = useState<FazendaCofre[]>([]);
  const [motivos, setMotivos] = useState<string[]>([]);
  const [busca, setBusca] = useState("");
  const [fazendaId, setFazendaId] = useState<number | null>(null);
  const [motivo, setMotivo] = useState("");
  const [assunto, setAssunto] = useState("");
  const [observacao, setObservacao] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    fetchFazendasCofre().then(setFazendas).catch((e) => setErro(e.message));
    fetchMotivosAcessoSuporte().then(setMotivos).catch(() => {});
  }, []);

  const fazenda = useMemo(() => fazendas.find((f) => f.id === fazendaId) || null, [fazendas, fazendaId]);
  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return fazendas;
    return fazendas.filter((f) => f.nome.toLowerCase().includes(q));
  }, [fazendas, busca]);

  async function confirmarEEntrar() {
    if (!fazenda || !motivo || !assunto.trim()) { setErro("Preencha motivo e assunto do chamado."); return; }
    setEnviando(true); setErro(null);
    try {
      await entrarComoSuporte(fazenda.id, motivo, assunto.trim(), observacao.trim() || undefined);
      onEntrou();
    } catch (e: any) {
      setErro(e.message);
    } finally { setEnviando(false); }
  }

  if (passo === "fazenda") {
    return (
      <Modal title="Acesso CowData — escolha a fazenda" onClose={onClose} width="560px">
        <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar fazenda…" style={{ ...inputStyle, marginBottom: "0.7rem" }} />
        <div style={{ maxHeight: "50vh", overflowY: "auto", border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)" }}>
          {filtradas.length === 0 && <p style={{ padding: "1rem", color: COR.mudo, fontSize: "0.82rem" }}>Nenhuma fazenda encontrada.</p>}
          {filtradas.map((f) => (
            <button key={f.id} type="button" onClick={() => { setFazendaId(f.id); setPasso("plano"); }}
              style={{
                display: "block", width: "100%", textAlign: "left", padding: "0.6rem 0.8rem", background: "transparent",
                border: "none", borderBottom: `1px solid ${COR.borda}`, color: COR.texto, fontSize: "0.85rem", cursor: "pointer",
              }}>
              {f.nome}
              {f.exige_aprovacao_suporte && <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: COR.dourado }}>· exige aprovação prévia</span>}
            </button>
          ))}
        </div>
        {erro && <p style={{ color: COR.vermelho, fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      </Modal>
    );
  }

  if (passo === "plano" && fazenda) {
    return (
      <Modal title={`Deseja entrar na Fazenda ${fazenda.nome}?`} onClose={onClose} width="480px">
        <p style={{ fontSize: "0.85rem", marginBottom: "0.8rem" }}>
          Plano: <strong>{fazenda.plano_nome || "—"}</strong>
        </p>
        <p style={labelStyle}>Módulos contratados</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginBottom: "1.2rem" }}>
          {fazenda.modulos.length === 0 && <span style={{ color: COR.mudo, fontSize: "0.8rem" }}>Nenhum módulo ativo.</span>}
          {fazenda.modulos.map((m) => (
            <span key={m} style={{ fontSize: "0.72rem", padding: "0.2rem 0.55rem", borderRadius: "999px", border: `1px solid ${COR.borda}`, color: COR.mudo }}>
              {m}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button type="button" style={btnPrimario} onClick={() => setPasso("motivo")}>Confirmar</button>
          <button type="button" style={btnGhost} onClick={() => setPasso("fazenda")}>Voltar</button>
        </div>
      </Modal>
    );
  }

  if (passo === "motivo" && fazenda) {
    return (
      <Modal title={`Motivo do acesso — ${fazenda.nome}`} onClose={onClose} width="560px">
        <div style={{ marginBottom: "0.8rem" }}>
          <label style={labelStyle}>Motivo do acesso</label>
          <select value={motivo} onChange={(e) => setMotivo(e.target.value)} style={inputStyle}>
            <option value="">Selecione…</option>
            {motivos.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div style={{ marginBottom: "0.8rem" }}>
          <label style={labelStyle}>Assunto do chamado</label>
          <input value={assunto} onChange={(e) => setAssunto(e.target.value)} placeholder="ex.: Cliente relatou erro ao salvar lançamento" style={inputStyle} />
        </div>
        <div style={{ marginBottom: "0.9rem" }}>
          <label style={labelStyle}>Observação (opcional)</label>
          <textarea value={observacao} onChange={(e) => setObservacao(e.target.value)} rows={3} style={{ ...inputStyle, resize: "vertical" }} />
        </div>
        <p style={{ display: "flex", gap: "0.4rem", fontSize: "0.74rem", color: COR.mudo, marginBottom: "1rem", lineHeight: 1.5 }}>
          <ShieldAlert size={14} style={{ flexShrink: 0, marginTop: "0.1rem" }} />
          Obs.: o acesso dura, no máximo, 30 minutos, e fica registrado com motivo e chamado, com numeração de
          protocolo automática na tela do cliente e do membro CowData. Clique em &quot;Encerrar&quot; para finalizar
          o chamado, a qualquer momento antes do tempo limite de acesso.
        </p>
        {erro && <p style={{ color: COR.vermelho, fontSize: "0.8rem", marginBottom: "0.7rem" }}>{erro}</p>}
        <div className="flex items-center gap-2">
          <button type="button" style={{ ...btnPrimario, display: "flex", alignItems: "center", gap: "0.4rem", opacity: enviando ? 0.6 : 1 }} disabled={enviando} onClick={confirmarEEntrar}>
            <LogIn size={14} /> {enviando ? "Entrando…" : "Confirmar e entrar"}
          </button>
          <button type="button" style={btnGhost} onClick={() => setPasso("plano")} disabled={enviando}>Voltar</button>
        </div>
      </Modal>
    );
  }

  return null;
}
