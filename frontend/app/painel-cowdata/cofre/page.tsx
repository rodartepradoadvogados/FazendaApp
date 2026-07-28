"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, Clock, Lock, LogIn, LogOut, ShieldAlert, XCircle } from "lucide-react";
import {
  fetchMotivosAcessoSuporte, fetchFazendasCofre, fetchSessoesAtivasCofre, fetchPedidosRecentesCofre,
  fetchAuditoriaRecenteCofre, solicitarAcessoCofre, aprovarPedidoCofre, negarPedidoCofre, encerrarSessaoCofre,
  atualizarFazenda,
  type FazendaCofre, type SessaoAcessoSuporte, type PedidoAcessoSuporte, type AuditoriaAcessoSuporte,
} from "@/lib/api";

const COR = {
  cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8", dourado: "#e8c256", texto: "#e8ecf5",
  verde: "#3ecf8e", vermelho: "#e05c5c",
};
const inputStyle: React.CSSProperties = {
  background: "#0a0e1a", border: `1px solid ${COR.borda}`, borderRadius: "6px", padding: "0.45rem 0.6rem", color: COR.texto, fontSize: "0.82rem",
};

function formatarData(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function formatarHora(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
function expiraLabel(sessao: SessaoAcessoSuporte): string {
  if (sessao.segundos_restantes <= 300) return "expirando agora";
  const min = Math.round(sessao.segundos_restantes / 60);
  return `em ${min} min`;
}
const CORES_STATUS: Record<string, string> = { aprovado: COR.verde, aguardando_aprovacao: COR.dourado, negado: COR.vermelho };
const LABEL_STATUS: Record<string, string> = { aprovado: "Aprovado", aguardando_aprovacao: "Aguardando aprovação", negado: "Negado" };

function Cartao({ titulo, subtitulo, children }: { titulo: string; subtitulo: string; children: React.ReactNode }) {
  return (
    <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", marginBottom: "1.2rem", overflow: "hidden" }}>
      <div style={{ padding: "1rem 1.2rem 0.7rem" }}>
        <h2 style={{ fontSize: "0.95rem", fontWeight: 700 }}>{titulo}</h2>
        <p style={{ fontSize: "0.76rem", color: COR.mudo, marginTop: "0.15rem" }}>{subtitulo}</p>
      </div>
      <div style={{ overflowX: "auto" }}>{children}</div>
    </div>
  );
}
function Th({ children }: { children?: React.ReactNode }) {
  return <th style={{ textAlign: "left", padding: "0.5rem 1.2rem", fontSize: "0.68rem", color: COR.mudo, textTransform: "uppercase", letterSpacing: "0.04em", borderTop: `1px solid ${COR.borda}` }}>{children}</th>;
}
function Td({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <td style={{ padding: "0.55rem 1.2rem", fontSize: "0.8rem", borderTop: `1px solid ${COR.borda}`, ...style }}>{children}</td>;
}
function Vazio({ colSpan, texto }: { colSpan: number; texto: string }) {
  return <tr><td colSpan={colSpan} style={{ padding: "1.2rem", textAlign: "center", color: COR.mudo, fontSize: "0.8rem", borderTop: `1px solid ${COR.borda}` }}>{texto}</td></tr>;
}

export default function CofreAcessoCowData() {
  const [fazendas, setFazendas] = useState<FazendaCofre[]>([]);
  const [motivos, setMotivos] = useState<string[]>([]);
  const [sessoes, setSessoes] = useState<SessaoAcessoSuporte[]>([]);
  const [pedidos, setPedidos] = useState<PedidoAcessoSuporte[]>([]);
  const [auditoria, setAuditoria] = useState<AuditoriaAcessoSuporte[]>([]);
  const [mostrarForm, setMostrarForm] = useState(false);
  const [fazendaId, setFazendaId] = useState<number | "">("");
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  function carregarTudo() {
    fetchFazendasCofre().then(setFazendas).catch((e) => setErro(e.message));
    fetchSessoesAtivasCofre().then(setSessoes).catch(() => {});
    fetchPedidosRecentesCofre().then(setPedidos).catch(() => {});
    fetchAuditoriaRecenteCofre().then(setAuditoria).catch(() => {});
  }
  useEffect(() => {
    carregarTudo();
    fetchMotivosAcessoSuporte().then(setMotivos).catch(() => {});
    const t = setInterval(carregarTudo, 30_000);
    return () => clearInterval(t);
  }, []);

  const fazendaSelecionada = fazendas.find((f) => f.id === fazendaId);

  async function enviarPedido() {
    if (!fazendaId || !motivo) { setErro("Escolha a fazenda e o motivo."); return; }
    setEnviando(true); setErro(null);
    try {
      await solicitarAcessoCofre({ fazenda_id: fazendaId, motivo });
      setMostrarForm(false); setFazendaId(""); setMotivo("");
      carregarTudo();
    } catch (e: any) { setErro(e.message); } finally { setEnviando(false); }
  }
  async function alternarAprovacao(f: FazendaCofre) {
    await atualizarFazenda(f.id, { exige_aprovacao_suporte: !f.exige_aprovacao_suporte });
    carregarTudo();
  }
  async function aprovar(id: number) { await aprovarPedidoCofre(id); carregarTudo(); }
  async function negar(id: number) { await negarPedidoCofre(id); carregarTudo(); }
  async function encerrar(id: number) { await encerrarSessaoCofre(id); carregarTudo(); }

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.2rem" }}>
        <div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Lock size={20} style={{ color: COR.dourado }} /> Cofre de acesso
          </h1>
          <p style={{ color: COR.mudo, fontSize: "0.85rem", marginTop: "0.2rem", maxWidth: "42rem" }}>
            Todo acesso de suporte da CowData a uma fazenda-cliente passa por pedido, motivo de uma lista fechada e
            prazo curto — fica registrado em auditoria. Cada fazenda escolhe abaixo se esse acesso é liberado na
            hora ou exige aprovação prévia.
          </p>
        </div>
        <button onClick={() => setMostrarForm((v) => !v)} style={{
          background: COR.dourado, color: "#0a0e1a", border: "none", borderRadius: "8px", padding: "0.55rem 1rem",
          fontSize: "0.82rem", fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap",
        }}>
          {mostrarForm ? "Cancelar" : "+ Solicitar acesso"}
        </button>
      </div>

      {erro && <p style={{ color: COR.vermelho, fontSize: "0.82rem", margin: "0.8rem 0" }}>{erro}</p>}

      {mostrarForm && (
        <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "1.1rem 1.2rem", margin: "1rem 0", display: "flex", gap: "0.9rem", flexWrap: "wrap", alignItems: "flex-end" }}>
          <div>
            <label style={{ fontSize: "0.7rem", color: COR.mudo, display: "block", marginBottom: "0.25rem" }}>Fazenda</label>
            <select value={fazendaId} onChange={(e) => setFazendaId(e.target.value ? Number(e.target.value) : "")} style={{ ...inputStyle, minWidth: "14rem" }}>
              <option value="">Selecione…</option>
              {fazendas.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: "0.7rem", color: COR.mudo, display: "block", marginBottom: "0.25rem" }}>Motivo</label>
            <select value={motivo} onChange={(e) => setMotivo(e.target.value)} style={{ ...inputStyle, minWidth: "16rem" }}>
              <option value="">Selecione…</option>
              {motivos.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <button onClick={enviarPedido} disabled={enviando} style={{
            background: COR.dourado, color: "#0a0e1a", border: "none", borderRadius: "6px", padding: "0.5rem 1rem",
            fontSize: "0.8rem", fontWeight: 700, cursor: enviando ? "default" : "pointer", opacity: enviando ? 0.6 : 1,
          }}>
            {enviando ? "Enviando…" : "Solicitar"}
          </button>
          {fazendaSelecionada && (
            <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.76rem", color: COR.mudo, cursor: "pointer", marginLeft: "auto" }}>
              <input type="checkbox" checked={fazendaSelecionada.exige_aprovacao_suporte} onChange={() => alternarAprovacao(fazendaSelecionada)} />
              Esta fazenda exige aprovação prévia
            </label>
          )}
        </div>
      )}

      <div style={{ marginTop: "1.4rem" }}>
        <Cartao titulo="Sessões ativas agora" subtitulo={`${sessoes.length} sessão(ões) em andamento`}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><Th>Fazenda</Th><Th>Membro</Th><Th>Motivo</Th><Th>Iniciada</Th><Th>Expira</Th><Th></Th></tr></thead>
            <tbody>
              {sessoes.length === 0 && <Vazio colSpan={6} texto="Nenhuma sessão ativa no momento." />}
              {sessoes.map((s) => (
                <tr key={s.id}>
                  <Td style={{ fontWeight: 600 }}>{s.fazenda_nome}</Td>
                  <Td>{s.membro_nome ?? "—"}</Td>
                  <Td style={{ color: COR.mudo }}>{s.motivo}</Td>
                  <Td>{formatarHora(s.iniciada_em)}</Td>
                  <Td style={{ color: s.segundos_restantes <= 300 ? COR.vermelho : COR.mudo }}>{expiraLabel(s)}</Td>
                  <Td>
                    <button onClick={() => encerrar(s.id)} title="Encerrar sessão" style={{
                      background: "transparent", border: `1px solid ${COR.borda}`, borderRadius: "6px", color: COR.mudo,
                      cursor: "pointer", padding: "0.3rem 0.55rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.72rem",
                    }}>
                      <LogOut size={12} /> Encerrar
                    </button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </Cartao>

        <Cartao titulo="Pedidos recentes" subtitulo={`Últimos ${pedidos.length} pedido(s), todos os status`}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><Th>Fazenda</Th><Th>Solicitante</Th><Th>Motivo</Th><Th>Status</Th><Th>Aprovador</Th><Th>Pedido em</Th><Th></Th></tr></thead>
            <tbody>
              {pedidos.length === 0 && <Vazio colSpan={7} texto="Nenhum pedido ainda." />}
              {pedidos.map((p) => (
                <tr key={p.id}>
                  <Td style={{ fontWeight: 600 }}>{p.fazenda_nome}</Td>
                  <Td>{p.solicitante_nome ?? "—"}</Td>
                  <Td style={{ color: COR.mudo }}>{p.motivo}</Td>
                  <Td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", color: CORES_STATUS[p.status] }}>
                      <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: CORES_STATUS[p.status] }} />
                      {LABEL_STATUS[p.status]}
                    </span>
                  </Td>
                  <Td>{p.aprovador_nome ?? "—"}</Td>
                  <Td style={{ color: COR.mudo }}>{formatarData(p.pedido_em)}</Td>
                  <Td>
                    {p.status === "aguardando_aprovacao" && (
                      <div style={{ display: "flex", gap: "0.4rem" }}>
                        <button onClick={() => aprovar(p.id)} title="Aprovar" style={{ background: "transparent", border: `1px solid ${COR.verde}`, borderRadius: "6px", color: COR.verde, cursor: "pointer", padding: "0.25rem 0.4rem" }}>
                          <CheckCircle2 size={13} />
                        </button>
                        <button onClick={() => negar(p.id)} title="Negar" style={{ background: "transparent", border: `1px solid ${COR.vermelho}`, borderRadius: "6px", color: COR.vermelho, cursor: "pointer", padding: "0.25rem 0.4rem" }}>
                          <XCircle size={13} />
                        </button>
                      </div>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </Cartao>

        <Cartao titulo="Auditoria recente" subtitulo={`Últimas ${auditoria.length} entrada(s), todas as fazendas`}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><Th>Quando</Th><Th>Fazenda</Th><Th>Membro</Th><Th>Ação</Th></tr></thead>
            <tbody>
              {auditoria.length === 0 && <Vazio colSpan={4} texto="Nenhuma entrada de auditoria ainda." />}
              {auditoria.map((a) => (
                <tr key={a.id}>
                  <Td style={{ color: COR.mudo }}>{formatarData(a.quando)}</Td>
                  <Td style={{ fontWeight: 600 }}>{a.fazenda_nome}</Td>
                  <Td>{a.membro_nome ?? "—"}</Td>
                  <Td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", color: a.acao === "entrada" ? COR.verde : COR.mudo }}>
                      {a.acao === "entrada" ? <LogIn size={13} /> : <LogOut size={13} />}
                      {a.acao === "entrada" ? "Entrada" : "Saída"}
                    </span>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </Cartao>
      </div>

      <p style={{ fontSize: "0.76rem", color: COR.mudo, display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.4rem" }}>
        <ShieldAlert size={13} /> Sessões expiram sozinhas em 30 minutos, mesmo sem encerramento manual.
      </p>
    </div>
  );
}
