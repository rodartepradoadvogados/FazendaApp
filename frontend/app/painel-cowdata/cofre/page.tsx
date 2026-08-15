"use client";
// Painel CowData > Suporte — 2 sub-abas (pedido explícito do usuário,
// ago/2026): "Acesso CowData" (entrar numa fazenda como suporte, pelo fluxo
// de 3 janelas — ver AcessoCowDataModal.tsx) e "Auditoria de Acessos
// CowData" (histórico de entrada/saída + toda ação/escrita feita durante
// cada sessão). Rota continua /painel-cowdata/cofre (ver layout.tsx).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, ClipboardList, Lock, LogIn, LogOut, ShieldAlert, XCircle } from "lucide-react";
import {
  fetchFazendasCofre, fetchSessoesAtivasCofre, fetchPedidosRecentesCofre,
  fetchAuditoriaRecenteCofre, fetchAcoesSuporte, aprovarPedidoCofre, negarPedidoCofre, encerrarSessaoCofre,
  atualizarFazenda, LABEL_NIVEL_SIGILO_EQUIPE_COWDATA,
  type FazendaCofre, type SessaoAcessoSuporte, type PedidoAcessoSuporte, type AuditoriaAcessoSuporte, type AcaoAuditoriaSuporte,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { AcessoCowDataModal } from "@/components/AcessoCowDataModal";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";

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
const LABEL_STATUS: Record<string, string> = { aprovado: "Aprovado", aguardando_aprovacao: "Aguardando aprovação", negado: "Negado" };

function Cartao({ titulo, subtitulo, acao, children }: { titulo: string; subtitulo: string; acao?: React.ReactNode; children: React.ReactNode }) {
  const COR = usePainelCowDataCor();
  return (
    <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", marginBottom: "1.2rem", overflow: "hidden" }}>
      <div style={{ padding: "1rem 1.2rem 0.7rem", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.8rem" }}>
        <div>
          <h2 style={{ fontSize: "0.95rem", fontWeight: 700 }}>{titulo}</h2>
          <p style={{ fontSize: "0.76rem", color: COR.mudo, marginTop: "0.15rem" }}>{subtitulo}</p>
        </div>
        {acao}
      </div>
      <div style={{ overflowX: "auto" }}>{children}</div>
    </div>
  );
}
function Th({ children }: { children?: React.ReactNode }) {
  const COR = usePainelCowDataCor();
  return <th style={{ textAlign: "left", padding: "0.5rem 1.2rem", fontSize: "0.68rem", color: COR.mudo, textTransform: "uppercase", letterSpacing: "0.04em", borderTop: `1px solid ${COR.borda}` }}>{children}</th>;
}
function Td({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  const COR = usePainelCowDataCor();
  return <td style={{ padding: "0.55rem 1.2rem", fontSize: "0.8rem", borderTop: `1px solid ${COR.borda}`, ...style }}>{children}</td>;
}
function Vazio({ colSpan, texto }: { colSpan: number; texto: string }) {
  const COR = usePainelCowDataCor();
  return <tr><td colSpan={colSpan} style={{ padding: "1.2rem", textAlign: "center", color: COR.mudo, fontSize: "0.8rem", borderTop: `1px solid ${COR.borda}` }}>{texto}</td></tr>;
}

type Aba = "acesso" | "auditoria";

export default function SuporteCowData() {
  const COR = usePainelCowDataCor();
  const CORES_STATUS: Record<string, string> = { aprovado: COR.verde, aguardando_aprovacao: COR.dourado, negado: COR.vermelho };
  const router = useRouter();
  const [aba, setAba] = useState<Aba>("acesso");
  const [fazendas, setFazendas] = useState<FazendaCofre[]>([]);
  const [sessoes, setSessoes] = useState<SessaoAcessoSuporte[]>([]);
  const [pedidos, setPedidos] = useState<PedidoAcessoSuporte[]>([]);
  const [auditoria, setAuditoria] = useState<AuditoriaAcessoSuporte[]>([]);
  const [acoes, setAcoes] = useState<AcaoAuditoriaSuporte[]>([]);
  const [modalAberto, setModalAberto] = useState(false);
  const [mostrarPoliticas, setMostrarPoliticas] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  function carregarTudo() {
    fetchFazendasCofre().then(setFazendas).catch((e) => setErro(e.message));
    fetchSessoesAtivasCofre().then(setSessoes).catch(() => {});
    fetchPedidosRecentesCofre().then(setPedidos).catch(() => {});
    fetchAuditoriaRecenteCofre().then(setAuditoria).catch(() => {});
    fetchAcoesSuporte().then(setAcoes).catch(() => {});
  }
  useEffect(() => {
    carregarTudo();
    const t = setInterval(carregarTudo, 30_000);
    return () => clearInterval(t);
  }, []);

  async function alternarAprovacao(f: FazendaCofre) {
    await atualizarFazenda(f.id, { exige_aprovacao_suporte: !f.exige_aprovacao_suporte });
    carregarTudo();
  }
  async function aprovar(id: number) { await aprovarPedidoCofre(id); carregarTudo(); }
  async function negar(id: number) { await negarPedidoCofre(id); carregarTudo(); }
  async function encerrar(id: number) { await encerrarSessaoCofre(id); carregarTudo(); }

  const ordSessoes = useOrdenacao(sessoes);
  const ordPedidos = useOrdenacao(pedidos);
  const ordAuditoria = useOrdenacao(auditoria);
  const ordAcoes = useOrdenacao(acoes);

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.2rem", flexWrap: "wrap", gap: "0.8rem" }}>
        <div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Lock size={20} style={{ color: COR.dourado }} /> Suporte
          </h1>
          <p style={{ color: COR.mudo, fontSize: "0.85rem", marginTop: "0.2rem", maxWidth: "42rem" }}>
            Todo acesso de suporte da CowData a uma fazenda-cliente passa por pedido, motivo de uma lista fechada,
            assunto do chamado e prazo curto (30 min) — fica registrado com protocolo, em auditoria própria.
          </p>
        </div>
        {aba === "acesso" && (
          <button onClick={() => setModalAberto(true)} style={{
            background: COR.dourado, color: COR.bg, border: "none", borderRadius: "var(--r-sm)", padding: "0.55rem 1rem",
            fontSize: "0.82rem", fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: "0.4rem",
          }}>
            <LogIn size={15} /> Acessar fazenda
          </button>
        )}
      </div>

      <div className="flex items-center gap-2" style={{ margin: "1rem 0", borderBottom: `1px solid ${COR.borda}` }}>
        {([["acesso", "Acesso CowData"], ["auditoria", "Auditoria de Acessos CowData"]] as const).map(([id, label]) => (
          <button key={id} onClick={() => setAba(id)} style={{
            background: "none", border: "none", cursor: "pointer", padding: "0.6rem 0.9rem", fontSize: "0.82rem",
            fontWeight: 700, color: aba === id ? COR.dourado : COR.mudo,
            borderBottom: aba === id ? `2px solid ${COR.dourado}` : "2px solid transparent",
          }}>
            {label}
          </button>
        ))}
      </div>

      {erro && <p style={{ color: COR.vermelho, fontSize: "0.82rem", margin: "0.8rem 0" }}>{erro}</p>}

      {aba === "acesso" && (
        <div>
          <Cartao titulo="Sessões ativas agora" subtitulo={`${sessoes.length} sessão(ões) em andamento`}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Protocolo" campo="protocolo" coluna={ordSessoes.coluna} dir={ordSessoes.dir} ordenar={ordSessoes.ordenar} />
                  <ThOrdenavel label="Fazenda" campo="fazenda_nome" coluna={ordSessoes.coluna} dir={ordSessoes.dir} ordenar={ordSessoes.ordenar} />
                  <ThOrdenavel label="Membro" campo="membro_nome" coluna={ordSessoes.coluna} dir={ordSessoes.dir} ordenar={ordSessoes.ordenar} />
                  <ThOrdenavel label="Nível" campo="nivel_sigilo" coluna={ordSessoes.coluna} dir={ordSessoes.dir} ordenar={ordSessoes.ordenar} />
                  <ThOrdenavel label="Motivo" campo="motivo" coluna={ordSessoes.coluna} dir={ordSessoes.dir} ordenar={ordSessoes.ordenar} />
                  <ThOrdenavel label="Iniciada" campo="iniciada_em" coluna={ordSessoes.coluna} dir={ordSessoes.dir} ordenar={ordSessoes.ordenar} />
                  <ThOrdenavel label="Expira" campo="segundos_restantes" coluna={ordSessoes.coluna} dir={ordSessoes.dir} ordenar={ordSessoes.ordenar} />
                  <Th></Th>
                </tr>
              </thead>
              <tbody>
                {sessoes.length === 0 && <Vazio colSpan={8} texto="Nenhuma sessão ativa no momento." />}
                {ordSessoes.linhasOrdenadas.map((s) => (
                  <tr key={s.id}>
                    <Td style={{ color: COR.mudo, fontVariantNumeric: "tabular-nums" }}>{s.protocolo || "—"}</Td>
                    <Td style={{ fontWeight: 600 }}>{s.fazenda_nome}</Td>
                    <Td>{s.membro_nome ?? "—"}</Td>
                    <Td style={{ color: COR.mudo }}>{LABEL_NIVEL_SIGILO_EQUIPE_COWDATA[s.nivel_sigilo]}</Td>
                    <Td style={{ color: COR.mudo }}>{s.motivo}</Td>
                    <Td>{formatarHora(s.iniciada_em)}</Td>
                    <Td style={{ color: s.segundos_restantes <= 300 ? COR.vermelho : COR.mudo }}>{expiraLabel(s)}</Td>
                    <Td>
                      <button onClick={() => encerrar(s.id)} title="Encerrar sessão" style={{
                        background: "transparent", border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", color: COR.mudo,
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
              <thead>
                <tr>
                  <ThOrdenavel label="Protocolo" campo="protocolo" coluna={ordPedidos.coluna} dir={ordPedidos.dir} ordenar={ordPedidos.ordenar} />
                  <ThOrdenavel label="Fazenda" campo="fazenda_nome" coluna={ordPedidos.coluna} dir={ordPedidos.dir} ordenar={ordPedidos.ordenar} />
                  <ThOrdenavel label="Solicitante" campo="solicitante_nome" coluna={ordPedidos.coluna} dir={ordPedidos.dir} ordenar={ordPedidos.ordenar} />
                  <ThOrdenavel label="Motivo" campo="motivo" coluna={ordPedidos.coluna} dir={ordPedidos.dir} ordenar={ordPedidos.ordenar} />
                  <ThOrdenavel label="Assunto" campo="assunto_chamado" coluna={ordPedidos.coluna} dir={ordPedidos.dir} ordenar={ordPedidos.ordenar} />
                  <ThOrdenavel label="Status" campo="status" coluna={ordPedidos.coluna} dir={ordPedidos.dir} ordenar={ordPedidos.ordenar} />
                  <ThOrdenavel label="Pedido em" campo="pedido_em" coluna={ordPedidos.coluna} dir={ordPedidos.dir} ordenar={ordPedidos.ordenar} />
                  <Th></Th>
                </tr>
              </thead>
              <tbody>
                {pedidos.length === 0 && <Vazio colSpan={8} texto="Nenhum pedido ainda." />}
                {ordPedidos.linhasOrdenadas.map((p) => (
                  <tr key={p.id}>
                    <Td style={{ color: COR.mudo, fontVariantNumeric: "tabular-nums" }}>{p.protocolo || "—"}</Td>
                    <Td style={{ fontWeight: 600 }}>{p.fazenda_nome}</Td>
                    <Td>{p.solicitante_nome ?? "—"}</Td>
                    <Td style={{ color: COR.mudo }}>{p.motivo}</Td>
                    <Td style={{ color: COR.mudo, maxWidth: "14rem" }}>{p.assunto_chamado ?? "—"}</Td>
                    <Td>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", color: CORES_STATUS[p.status] }}>
                        <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: CORES_STATUS[p.status] }} />
                        {LABEL_STATUS[p.status]}
                      </span>
                    </Td>
                    <Td style={{ color: COR.mudo }}>{formatarData(p.pedido_em)}</Td>
                    <Td>
                      {p.status === "aguardando_aprovacao" && (
                        <div style={{ display: "flex", gap: "0.4rem" }}>
                          <button onClick={() => aprovar(p.id)} title="Aprovar" style={{ background: "transparent", border: `1px solid ${COR.verde}`, borderRadius: "var(--r-sm)", color: COR.verde, cursor: "pointer", padding: "0.25rem 0.4rem" }}>
                            <CheckCircle2 size={13} />
                          </button>
                          <button onClick={() => negar(p.id)} title="Negar" style={{ background: "transparent", border: `1px solid ${COR.vermelho}`, borderRadius: "var(--r-sm)", color: COR.vermelho, cursor: "pointer", padding: "0.25rem 0.4rem" }}>
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

          <Cartao titulo="Política de aprovação por fazenda" subtitulo="Quais fazendas exigem aprovação prévia antes de liberar o acesso"
            acao={<button onClick={() => setMostrarPoliticas((v) => !v)} style={{ background: "transparent", border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", color: COR.mudo, cursor: "pointer", padding: "0.3rem 0.6rem", fontSize: "0.72rem" }}>{mostrarPoliticas ? "Ocultar" : "Ver/editar"}</button>}>
            {mostrarPoliticas && (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr><Th>Fazenda</Th><Th>Plano</Th><Th>Exige aprovação prévia?</Th></tr></thead>
                <tbody>
                  {fazendas.map((f) => (
                    <tr key={f.id}>
                      <Td style={{ fontWeight: 600 }}>{f.nome}</Td>
                      <Td style={{ color: COR.mudo }}>{f.plano_nome || "—"}</Td>
                      <Td>
                        <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
                          <input type="checkbox" checked={f.exige_aprovacao_suporte} onChange={() => alternarAprovacao(f)} /> {f.exige_aprovacao_suporte ? "Sim" : "Não"}
                        </label>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Cartao>

          <p style={{ fontSize: "0.76rem", color: COR.mudo, display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.4rem" }}>
            <ShieldAlert size={13} /> Sessões expiram sozinhas em 30 minutos, mesmo sem encerramento manual.
          </p>
        </div>
      )}

      {aba === "auditoria" && (
        <div>
          <Cartao titulo="Entradas e saídas" subtitulo={`Últimas ${auditoria.length} entrada(s), todas as fazendas`}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Quando" campo="quando" coluna={ordAuditoria.coluna} dir={ordAuditoria.dir} ordenar={ordAuditoria.ordenar} />
                  <ThOrdenavel label="Fazenda" campo="fazenda_nome" coluna={ordAuditoria.coluna} dir={ordAuditoria.dir} ordenar={ordAuditoria.ordenar} />
                  <ThOrdenavel label="Membro" campo="membro_nome" coluna={ordAuditoria.coluna} dir={ordAuditoria.dir} ordenar={ordAuditoria.ordenar} />
                  <ThOrdenavel label="Nível" campo="nivel_sigilo" coluna={ordAuditoria.coluna} dir={ordAuditoria.dir} ordenar={ordAuditoria.ordenar} />
                  <ThOrdenavel label="Ação" campo="acao" coluna={ordAuditoria.coluna} dir={ordAuditoria.dir} ordenar={ordAuditoria.ordenar} />
                </tr>
              </thead>
              <tbody>
                {auditoria.length === 0 && <Vazio colSpan={5} texto="Nenhuma entrada de auditoria ainda." />}
                {ordAuditoria.linhasOrdenadas.map((a) => (
                  <tr key={a.id}>
                    <Td style={{ color: COR.mudo }}>{formatarData(a.quando)}</Td>
                    <Td style={{ fontWeight: 600 }}>{a.fazenda_nome}</Td>
                    <Td>{a.membro_nome ?? "—"}</Td>
                    <Td style={{ color: COR.mudo }}>{a.nivel_sigilo ? LABEL_NIVEL_SIGILO_EQUIPE_COWDATA[a.nivel_sigilo] : "—"}</Td>
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

          <Cartao titulo="Ações realizadas durante os acessos" subtitulo={`Últimas ${acoes.length} escrita(s) tentada(s) — permitidas e bloqueadas`}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Quando" campo="quando" coluna={ordAcoes.coluna} dir={ordAcoes.dir} ordenar={ordAcoes.ordenar} />
                  <ThOrdenavel label="Protocolo" campo="protocolo" coluna={ordAcoes.coluna} dir={ordAcoes.dir} ordenar={ordAcoes.ordenar} />
                  <ThOrdenavel label="Fazenda" campo="fazenda_nome" coluna={ordAcoes.coluna} dir={ordAcoes.dir} ordenar={ordAcoes.ordenar} />
                  <ThOrdenavel label="Membro" campo="membro_nome" coluna={ordAcoes.coluna} dir={ordAcoes.dir} ordenar={ordAcoes.ordenar} />
                  <ThOrdenavel label="Nível" campo="nivel_sigilo" coluna={ordAcoes.coluna} dir={ordAcoes.dir} ordenar={ordAcoes.ordenar} />
                  <ThOrdenavel label="Ação" campo="metodo" coluna={ordAcoes.coluna} dir={ordAcoes.dir} ordenar={ordAcoes.ordenar} />
                  <Th>Resultado</Th>
                </tr>
              </thead>
              <tbody>
                {acoes.length === 0 && <Vazio colSpan={7} texto="Nenhuma ação registrada ainda." />}
                {ordAcoes.linhasOrdenadas.map((a) => (
                  <tr key={a.id}>
                    <Td style={{ color: COR.mudo }}>{formatarData(a.quando)}</Td>
                    <Td style={{ color: COR.mudo, fontVariantNumeric: "tabular-nums" }}>{a.protocolo || "—"}</Td>
                    <Td style={{ fontWeight: 600 }}>{a.fazenda_nome}</Td>
                    <Td>{a.membro_nome ?? "—"}</Td>
                    <Td style={{ color: COR.mudo }}>{a.nivel_sigilo ? LABEL_NIVEL_SIGILO_EQUIPE_COWDATA[a.nivel_sigilo] : "—"}</Td>
                    <Td style={{ fontFamily: "monospace", fontSize: "0.74rem" }}>{a.metodo} {a.caminho}</Td>
                    <Td>
                      {a.bloqueado
                        ? <span style={{ color: COR.vermelho, display: "inline-flex", alignItems: "center", gap: "0.3rem" }}><XCircle size={13} /> Bloqueada</span>
                        : <span style={{ color: COR.verde, display: "inline-flex", alignItems: "center", gap: "0.3rem" }}><CheckCircle2 size={13} /> {a.status_code ?? "ok"}</span>}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Cartao>

          <p style={{ fontSize: "0.76rem", color: COR.mudo, display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.4rem" }}>
            <ClipboardList size={13} /> Esta mesma auditoria também aparece, filtrada por fazenda, em Configurações › Auditoria CowData — visível só para o contratante-administrador de cada fazenda.
          </p>
        </div>
      )}

      {modalAberto && (
        <AcessoCowDataModal
          onClose={() => setModalAberto(false)}
          onEntrou={() => router.push("/")}
        />
      )}
    </div>
  );
}
