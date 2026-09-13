"use client";
// Cofre (menu "Suporte") em versão mobile-nativa do Painel CowData —
// mesmas 2 abas do desktop (app/painel-cowdata/cofre/page.tsx): "Acesso
// CowData" (sessões ativas, pedidos recentes, política de aprovação por
// fazenda, botão "Acessar fazenda" que abre o fluxo de 3 janelas em
// AcessoCowDataModal) e "Auditoria de Acessos CowData" (entradas/saídas +
// ações realizadas durante os acessos). Rota continua /painel-cowdata/cofre.
//
// Cada <table> do desktop vira uma lista de cartões empilhados aqui (uma
// linha = um cartão) — a UI de ordenação por coluna (ThOrdenavel) não faz
// sentido em cartão empilhado, então cada lista usa uma ordenação padrão fixa
// em vez da ordenação interativa do desktop: sessões por expiração mais
// próxima primeiro, e pedidos/auditoria/ações pela mais recente primeiro.
// Mesma leitura de dados (5 fontes) e mesmo polling de 30s do desktop.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, ClipboardList, LogIn, LogOut, ShieldAlert, XCircle } from "lucide-react";
import {
  fetchFazendasCofre, fetchSessoesAtivasCofre, fetchPedidosRecentesCofre,
  fetchAuditoriaRecenteCofre, fetchAcoesSuporte, aprovarPedidoCofre, negarPedidoCofre, encerrarSessaoCofre,
  atualizarFazenda, LABEL_NIVEL_SIGILO_EQUIPE_COWDATA,
  type FazendaCofre, type SessaoAcessoSuporte, type PedidoAcessoSuporte, type AuditoriaAcessoSuporte, type AcaoAuditoriaSuporte,
} from "@/lib/api";
import { AcessoCowDataModal } from "@/components/AcessoCowDataModal";
import { usePainelCowDataCor, usePainelCowDataEstilos, type CoresPainelCowData } from "@/lib/painelCowDataTema";
import { CabecalhoMobilePainelCowData, CorpoMobilePainelCowData, BotaoMobile } from "@/components/painel-cowdata/mobile/ComumMobile";

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

type Cor = CoresPainelCowData;

function Secao({ titulo, subtitulo, acao, children, cor }: {
  titulo: string; subtitulo: string; acao?: React.ReactNode; children: React.ReactNode; cor: Cor;
}) {
  return (
    <div style={{ background: cor.painelAlt, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", overflow: "hidden" }}>
      <div style={{ padding: "0.9rem 1rem 0.7rem", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.6rem" }}>
        <div>
          <h2 style={{ fontSize: "0.86rem", fontWeight: 700, margin: 0 }}>{titulo}</h2>
          <p style={{ fontSize: "0.72rem", color: cor.mudo, margin: "0.15rem 0 0" }}>{subtitulo}</p>
        </div>
        {acao}
      </div>
      <div style={{ padding: "0 1rem 1rem", display: "flex", flexDirection: "column", gap: "0.55rem" }}>{children}</div>
    </div>
  );
}
function CartaoVazio({ texto, cor }: { texto: string; cor: Cor }) {
  return <div style={{ padding: "1rem", textAlign: "center", color: cor.mudo, fontSize: "0.78rem" }}>{texto}</div>;
}
function CartaoLinha({ cor, children }: { cor: Cor; children: React.ReactNode }) {
  return <div style={{ background: cor.painel, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.7rem 0.85rem" }}>{children}</div>;
}

type Aba = "acesso" | "auditoria";

export default function CofreMobile() {
  const COR = usePainelCowDataCor();
  const estilos = usePainelCowDataEstilos();
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
    fetchSessoesAtivasCofre().then(setSessoes).catch((e) => setErro(e.message));
    fetchPedidosRecentesCofre().then(setPedidos).catch((e) => setErro(e.message));
    fetchAuditoriaRecenteCofre().then(setAuditoria).catch((e) => setErro(e.message));
    fetchAcoesSuporte().then(setAcoes).catch((e) => setErro(e.message));
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

  // Sem ordenação interativa por coluna (não cabe em cartão empilhado) —
  // ordem padrão fixa por lista, ver nota no topo do arquivo.
  const sessoesOrdenadas = [...sessoes].sort((a, b) => a.segundos_restantes - b.segundos_restantes);
  const pedidosOrdenados = [...pedidos].sort((a, b) => +new Date(b.pedido_em) - +new Date(a.pedido_em));
  const auditoriaOrdenada = [...auditoria].sort((a, b) => +new Date(b.quando) - +new Date(a.quando));
  const acoesOrdenadas = [...acoes].sort((a, b) => +new Date(b.quando) - +new Date(a.quando));

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <CabecalhoMobilePainelCowData
        titulo="Suporte"
        subtitulo="Todo acesso de suporte da CowData a uma fazenda-cliente passa por pedido, motivo, assunto do chamado e prazo curto (30 min) — com protocolo, em auditoria própria."
        cor={COR}
        acao={aba === "acesso" ? (
          <BotaoMobile estilos={estilos} onClick={() => setModalAberto(true)} style={{ width: "auto", padding: "0.5rem 0.8rem", whiteSpace: "nowrap", flexShrink: 0 }}>
            <LogIn size={14} /> Acessar
          </BotaoMobile>
        ) : undefined}
      />

      <div style={{ display: "flex", borderBottom: `1px solid ${COR.borda}`, flexShrink: 0 }}>
        {([["acesso", "Acesso CowData"], ["auditoria", "Auditoria de Acessos CowData"]] as const).map(([id, label]) => (
          <button key={id} onClick={() => setAba(id)} style={{
            flex: 1, background: "none", border: "none", cursor: "pointer", padding: "0.7rem 0.4rem", fontSize: "0.76rem",
            fontWeight: 700, color: aba === id ? COR.dourado : COR.mudo,
            borderBottom: aba === id ? `2px solid ${COR.dourado}` : "2px solid transparent", marginBottom: "-1px",
          }}>
            {label}
          </button>
        ))}
      </div>

      <CorpoMobilePainelCowData>
        {erro && <p style={{ color: COR.vermelho, fontSize: "0.8rem", margin: 0 }}>{erro}</p>}

        {aba === "acesso" && (
          <>
            <Secao titulo="Sessões ativas agora" subtitulo={`${sessoes.length} sessão(ões) em andamento`} cor={COR}>
              {sessoesOrdenadas.length === 0 && <CartaoVazio texto="Nenhuma sessão ativa no momento." cor={COR} />}
              {sessoesOrdenadas.map((s) => {
                const expirando = s.segundos_restantes <= 300;
                return (
                  <CartaoLinha key={s.id} cor={COR}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                      <div style={{ fontWeight: 700, fontSize: "0.84rem" }}>{s.fazenda_nome}</div>
                      <div style={{ fontSize: "0.68rem", color: COR.mudo, fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>{s.protocolo || "—"}</div>
                    </div>
                    <div style={{ fontSize: "0.76rem", color: COR.mudo, marginTop: "0.3rem" }}>
                      {s.membro_nome ?? "—"} · {LABEL_NIVEL_SIGILO_EQUIPE_COWDATA[s.nivel_sigilo]}
                    </div>
                    <div style={{ fontSize: "0.76rem", color: COR.mudo, marginTop: "0.15rem" }}>{s.motivo}</div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.5rem" }}>
                      <span style={{ fontSize: "0.72rem", color: COR.mudo }}>Iniciada {formatarHora(s.iniciada_em)}</span>
                      <span style={{ fontSize: "0.72rem", fontWeight: 700, color: expirando ? COR.vermelho : COR.mudo }}>{expiraLabel(s)}</span>
                    </div>
                    <BotaoMobile variante="ghost" estilos={estilos} onClick={() => encerrar(s.id)} style={{ marginTop: "0.6rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "0.35rem" }}>
                      <LogOut size={13} /> Encerrar
                    </BotaoMobile>
                  </CartaoLinha>
                );
              })}
            </Secao>

            <Secao titulo="Pedidos recentes" subtitulo={`Últimos ${pedidos.length} pedido(s), todos os status`} cor={COR}>
              {pedidosOrdenados.length === 0 && <CartaoVazio texto="Nenhum pedido ainda." cor={COR} />}
              {pedidosOrdenados.map((p) => (
                <CartaoLinha key={p.id} cor={COR}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                    <div style={{ fontWeight: 700, fontSize: "0.84rem" }}>{p.fazenda_nome}</div>
                    <div style={{ fontSize: "0.68rem", color: COR.mudo, fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>{p.protocolo || "—"}</div>
                  </div>
                  <div style={{ fontSize: "0.76rem", color: COR.mudo, marginTop: "0.3rem" }}>{p.solicitante_nome ?? "—"} · {p.motivo}</div>
                  {p.assunto_chamado && <div style={{ fontSize: "0.76rem", color: COR.mudo, marginTop: "0.15rem" }}>{p.assunto_chamado}</div>}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.5rem" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", color: CORES_STATUS[p.status], fontSize: "0.74rem", fontWeight: 700 }}>
                      <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: CORES_STATUS[p.status] }} />
                      {LABEL_STATUS[p.status]}
                    </span>
                    <span style={{ fontSize: "0.7rem", color: COR.mudo }}>{formatarData(p.pedido_em)}</span>
                  </div>
                  {p.status === "aguardando_aprovacao" && (
                    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.6rem" }}>
                      <button onClick={() => aprovar(p.id)} style={{
                        flex: 1, background: "transparent", border: `1px solid ${COR.verde}`, borderRadius: "var(--r-sm)", color: COR.verde,
                        cursor: "pointer", padding: "0.4rem", fontSize: "0.76rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "0.3rem",
                      }}>
                        <CheckCircle2 size={13} /> Aprovar
                      </button>
                      <button onClick={() => negar(p.id)} style={{
                        flex: 1, background: "transparent", border: `1px solid ${COR.vermelho}`, borderRadius: "var(--r-sm)", color: COR.vermelho,
                        cursor: "pointer", padding: "0.4rem", fontSize: "0.76rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "0.3rem",
                      }}>
                        <XCircle size={13} /> Negar
                      </button>
                    </div>
                  )}
                </CartaoLinha>
              ))}
            </Secao>

            <Secao
              titulo="Política de aprovação por fazenda"
              subtitulo="Quais fazendas exigem aprovação prévia antes de liberar o acesso"
              cor={COR}
              acao={
                <button onClick={() => setMostrarPoliticas((v) => !v)} style={{
                  background: "transparent", border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", color: COR.mudo,
                  cursor: "pointer", padding: "0.3rem 0.6rem", fontSize: "0.72rem", flexShrink: 0,
                }}>
                  {mostrarPoliticas ? "Ocultar" : "Ver/editar"}
                </button>
              }
            >
              {mostrarPoliticas && fazendas.length === 0 && <CartaoVazio texto="Nenhuma fazenda encontrada." cor={COR} />}
              {mostrarPoliticas && fazendas.map((f) => (
                <CartaoLinha key={f.id} cor={COR}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem" }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700, fontSize: "0.84rem" }}>{f.nome}</div>
                      <div style={{ fontSize: "0.72rem", color: COR.mudo, marginTop: "0.1rem" }}>{f.plano_nome || "—"}</div>
                    </div>
                    <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", cursor: "pointer", flexShrink: 0, color: COR.mudo }}>
                      <input type="checkbox" checked={f.exige_aprovacao_suporte} onChange={() => alternarAprovacao(f)} />
                      {f.exige_aprovacao_suporte ? "Sim" : "Não"}
                    </label>
                  </div>
                </CartaoLinha>
              ))}
            </Secao>

            <p style={{ fontSize: "0.76rem", color: COR.mudo, display: "flex", alignItems: "center", gap: "0.4rem", margin: 0 }}>
              <ShieldAlert size={13} style={{ flexShrink: 0 }} /> Sessões expiram sozinhas em 30 minutos, mesmo sem encerramento manual.
            </p>
          </>
        )}

        {aba === "auditoria" && (
          <>
            <Secao titulo="Entradas e saídas" subtitulo={`Últimas ${auditoria.length} entrada(s), todas as fazendas`} cor={COR}>
              {auditoriaOrdenada.length === 0 && <CartaoVazio texto="Nenhuma entrada de auditoria ainda." cor={COR} />}
              {auditoriaOrdenada.map((a) => (
                <CartaoLinha key={a.id} cor={COR}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                    <div style={{ fontWeight: 700, fontSize: "0.84rem" }}>{a.fazenda_nome}</div>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", color: a.acao === "entrada" ? COR.verde : COR.mudo, fontSize: "0.76rem", fontWeight: 700, flexShrink: 0 }}>
                      {a.acao === "entrada" ? <LogIn size={13} /> : <LogOut size={13} />}
                      {a.acao === "entrada" ? "Entrada" : "Saída"}
                    </span>
                  </div>
                  <div style={{ fontSize: "0.76rem", color: COR.mudo, marginTop: "0.3rem" }}>
                    {a.membro_nome ?? "—"} · {a.nivel_sigilo ? LABEL_NIVEL_SIGILO_EQUIPE_COWDATA[a.nivel_sigilo] : "—"}
                  </div>
                  <div style={{ fontSize: "0.7rem", color: COR.mudo, marginTop: "0.3rem" }}>{formatarData(a.quando)}</div>
                </CartaoLinha>
              ))}
            </Secao>

            <Secao titulo="Ações realizadas durante os acessos" subtitulo={`Últimas ${acoes.length} escrita(s) tentada(s) — permitidas e bloqueadas`} cor={COR}>
              {acoesOrdenadas.length === 0 && <CartaoVazio texto="Nenhuma ação registrada ainda." cor={COR} />}
              {acoesOrdenadas.map((a) => (
                <CartaoLinha key={a.id} cor={COR}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                    <div style={{ fontWeight: 700, fontSize: "0.84rem" }}>{a.fazenda_nome}</div>
                    <div style={{ fontSize: "0.68rem", color: COR.mudo, fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>{a.protocolo || "—"}</div>
                  </div>
                  <div style={{ fontSize: "0.76rem", color: COR.mudo, marginTop: "0.3rem" }}>
                    {a.membro_nome ?? "—"} · {a.nivel_sigilo ? LABEL_NIVEL_SIGILO_EQUIPE_COWDATA[a.nivel_sigilo] : "—"}
                  </div>
                  <div style={{ fontFamily: "monospace", fontSize: "0.74rem", marginTop: "0.3rem", wordBreak: "break-all" }}>{a.metodo} {a.caminho}</div>
                  <div style={{ marginTop: "0.4rem" }}>
                    {a.bloqueado
                      ? <span style={{ color: COR.vermelho, display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.74rem" }}><XCircle size={13} /> Bloqueada</span>
                      : <span style={{ color: COR.verde, display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.74rem" }}><CheckCircle2 size={13} /> {a.status_code ?? "ok"}</span>}
                  </div>
                  <div style={{ fontSize: "0.7rem", color: COR.mudo, marginTop: "0.3rem" }}>{formatarData(a.quando)}</div>
                </CartaoLinha>
              ))}
            </Secao>

            <p style={{ fontSize: "0.76rem", color: COR.mudo, display: "flex", alignItems: "center", gap: "0.4rem", margin: 0 }}>
              <ClipboardList size={13} style={{ flexShrink: 0 }} /> Esta mesma auditoria também aparece, filtrada por fazenda, em Configurações › Auditoria CowData — visível só para o contratante-administrador de cada fazenda.
            </p>
          </>
        )}
      </CorpoMobilePainelCowData>

      {modalAberto && (
        <AcessoCowDataModal
          onClose={() => setModalAberto(false)}
          onEntrou={() => router.push("/")}
        />
      )}
    </div>
  );
}
