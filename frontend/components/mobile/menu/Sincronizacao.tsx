"use client";
// Sub-tela: Sincronização offline — mostra a fila de lançamentos/fotos
// pendentes e erros técnicos para diagnóstico quando a rede falha.
import { useMemo, useState } from "react";
import { WifiOff, RefreshCw, Trash2, AlertCircle, CheckCircle } from "lucide-react";
import { MobVoltar, MobCard, MobBarraProgresso } from "@/components/mobile/ui";
import { usePendentes, sincronizar, descartarPendente, useOnline, useSincProgresso } from "@/lib/offline";
import { Carregando, Vazio } from "@/components/mobile/menu/comum";

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const agora = Date.now();
  const diff = Math.floor((agora - d.getTime()) / 1000);
  if (diff < 60) return "agora";
  if (diff < 3600) return `há ${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)}h`;
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function statusLabel(status: string): string {
  if (status === "pendente") return "⏳ Aguardando envio";
  if (status === "erro") return "❌ Erro permanente";
  return status;
}

function statusCor(status: string): string {
  if (status === "erro") return "var(--mob-vermelho, #d32f2f)";
  if (status === "pendente") return "var(--mob-ambar, #f57c00)";
  return "var(--mob-verde, #388e3c)";
}

const estiloCard: React.CSSProperties = {
  background: "var(--mob-surface-2)",
  border: "1px solid var(--mob-border)",
  borderRadius: 10,
  padding: "1rem",
  marginBottom: "0.8rem",
  fontSize: "0.9rem",
  lineHeight: 1.5,
};

const estiloHeader: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: "0.6rem",
  fontWeight: 500,
};

const estiloFila: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "0.5rem",
};

const estiloInfo: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: "0.5rem",
  fontSize: "0.85rem",
  color: "var(--mob-muted)",
  marginTop: "0.5rem",
};

const estiloBotoes: React.CSSProperties = {
  display: "flex",
  gap: "0.5rem",
  marginTop: "0.7rem",
};

const estiloBotao: React.CSSProperties = {
  flex: 1,
  padding: "0.5rem",
  background: "var(--mob-acao)",
  color: "white",
  border: "none",
  borderRadius: 6,
  fontSize: "0.85rem",
  cursor: "pointer",
  fontWeight: 500,
};

export default function Sincronizacao({ onVoltar }: { onVoltar: () => void }) {
  const online = useOnline();
  const pendentes_items = usePendentes();
  const [sincronizando, setSincronizando] = useState(false);
  // Progresso REAL da rodada em andamento (feitos/total) — ver useSincProgresso
  // em lib/offline.ts; usado pela barra abaixo em vez de só um spinner.
  const progresso = useSincProgresso();
  const [excluindo, setExcluindo] = useState<string | null>(null);

  const grupos = useMemo(() => {
    const pendentes_list = pendentes_items.filter((i) => i.status === "pendente");
    const erros_list = pendentes_items.filter((i) => i.status === "erro");
    return { pendentes: pendentes_list, erros: erros_list };
  }, [pendentes_items]);

  const handleSincronizar = async () => {
    setSincronizando(true);
    try {
      await sincronizar();
    } catch (e) {
      console.error("Erro ao sincronizar:", e);
    } finally {
      setSincronizando(false);
    }
  };

  const handleDescartar = async (id: string) => {
    if (!window.confirm("Descartar este lançamento? Você terá que fazer novamente.")) return;
    setExcluindo(id);
    try {
      await descartarPendente(id);
    } catch (e) {
      console.error("Erro ao descartar:", e);
    } finally {
      setExcluindo(null);
    }
  };

  return (
    <>
      <MobVoltar titulo="Sincronização" onVoltar={onVoltar} />
      <div style={{ padding: "1rem" }}>
        <h2 style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "1.2rem", marginBottom: "1rem" }}>
          <WifiOff size={24} /> Sincronização Offline
        </h2>

        {/* Status de conexão */}
        <div
          style={{
            ...estiloCard,
            borderColor: online ? "var(--mob-verde)" : "var(--mob-ambar)",
            background: online ? "rgba(56, 142, 60, 0.1)" : "rgba(245, 124, 0, 0.1)",
          }}
        >
          <div style={estiloHeader}>
            <span>{online ? "🟢 Conectado" : "🔴 Sem conexão"}</span>
            <button
              onClick={handleSincronizar}
              disabled={sincronizando}
              style={{
                ...estiloBotao,
                opacity: sincronizando ? 0.6 : 1,
                cursor: sincronizando ? "not-allowed" : "pointer",
                width: "auto",
                padding: "0.5rem 1rem",
                background: "var(--mob-acao)",
              }}
            >
              {sincronizando ? (
                <>
                  <RefreshCw size={16} style={{ display: "inline", marginRight: "0.3rem", animation: "spin 1s linear infinite" }} />
                  Sincronizando...
                </>
              ) : (
                <>
                  <RefreshCw size={16} style={{ display: "inline", marginRight: "0.3rem" }} />
                  Sincronizar
                </>
              )}
            </button>
          </div>
          <p style={{ margin: "0.5rem 0 0 0", fontSize: "0.85rem", color: "var(--mob-muted)" }}>
            {pendentes_items.length === 0
              ? "Nenhum lançamento aguardando envio."
              : `${pendentes_items.length} lançamento(s) aguardando sincronização.`}
          </p>
          {progresso && <MobBarraProgresso feitos={progresso.feitos} total={progresso.total} rotulo="Enviando" />}
        </div>

        {/* Blocos por status */}
        {grupos.pendentes.length > 0 && (
          <div style={{ marginTop: "1.5rem" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.8rem", color: "var(--mob-ambar)" }}>
              ⏳ Aguardando envio ({grupos.pendentes.length})
            </h3>
            <div style={estiloFila}>
              {grupos.pendentes.map((item) => (
                <div key={item.id} style={estiloCard}>
                  <div style={estiloHeader}>
                    <span style={{ fontWeight: 600 }}>{item.descricao || "Sem descrição"}</span>
                    <span style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>Tentativa {item.tentativas || 0}</span>
                  </div>
                  <div style={estiloInfo}>
                    <div>
                      <strong>Tipo:</strong> {item.tipo === "form" ? "📷 Foto/arquivo" : "📝 Dados"}
                    </div>
                    <div>
                      <strong>Criado:</strong> {formatarData(item.criadoEm)}
                    </div>
                    <div>
                      <strong>Rota:</strong> {item.caminho}
                    </div>
                    <div>
                      <strong>Método:</strong> {item.metodo}
                    </div>
                  </div>
                  {item.debugUltimoErro && (
                    <div
                      style={{
                        background: "rgba(211, 47, 47, 0.1)",
                        border: "1px solid var(--mob-vermelho, #d32f2f)",
                        borderRadius: 6,
                        padding: "0.6rem",
                        marginTop: "0.6rem",
                        fontSize: "0.8rem",
                        color: "var(--mob-vermelho, #d32f2f)",
                        fontFamily: "monospace",
                        wordBreak: "break-word",
                      }}
                    >
                      <strong>Diagnóstico:</strong> {item.debugUltimoErro}
                    </div>
                  )}
                  {item.proximaTentativaEm && (
                    <div style={{ ...estiloInfo, marginTop: "0.6rem" }}>
                      <div style={{ gridColumn: "1 / -1" }}>
                        <strong>Próxima tentativa:</strong> {formatarData(item.proximaTentativaEm)}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {grupos.erros.length > 0 && (
          <div style={{ marginTop: "1.5rem" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.8rem", color: "var(--mob-vermelho, #d32f2f)" }}>
              ❌ Erros permanentes ({grupos.erros.length})
            </h3>
            <div style={estiloFila}>
              {grupos.erros.map((item) => (
                <div key={item.id} style={{ ...estiloCard, borderColor: "var(--mob-vermelho, #d32f2f)" }}>
                  <div style={estiloHeader}>
                    <span style={{ fontWeight: 600 }}>{item.descricao || "Sem descrição"}</span>
                  </div>
                  <div style={estiloInfo}>
                    <div>
                      <strong>Tipo:</strong> {item.tipo === "form" ? "📷 Foto/arquivo" : "📝 Dados"}
                    </div>
                    <div>
                      <strong>Criado:</strong> {formatarData(item.criadoEm)}
                    </div>
                    <div>
                      <strong>Rota:</strong> {item.caminho}
                    </div>
                    <div>
                      <strong>Tentativas:</strong> {item.tentativas || 0}
                    </div>
                  </div>
                  {item.erro && (
                    <div
                      style={{
                        background: "rgba(211, 47, 47, 0.15)",
                        border: "1px solid var(--mob-vermelho, #d32f2f)",
                        borderRadius: 6,
                        padding: "0.6rem",
                        marginTop: "0.6rem",
                        fontSize: "0.85rem",
                        color: "var(--mob-vermelho, #d32f2f)",
                      }}
                    >
                      <strong>Erro:</strong> {item.erro}
                    </div>
                  )}
                  {item.debugUltimoErro && (
                    <div
                      style={{
                        background: "rgba(25, 25, 25, 0.8)",
                        borderRadius: 6,
                        padding: "0.6rem",
                        marginTop: "0.6rem",
                        fontSize: "0.75rem",
                        color: "#bbb",
                        fontFamily: "monospace",
                        wordBreak: "break-word",
                        overflowX: "auto",
                      }}
                    >
                      <strong>Debug:</strong> {item.debugUltimoErro}
                    </div>
                  )}
                  <div style={estiloBotoes}>
                    <button
                      onClick={() => handleDescartar(item.id)}
                      disabled={excluindo === item.id}
                      style={{
                        ...estiloBotao,
                        background: "var(--mob-vermelho, #d32f2f)",
                        opacity: excluindo === item.id ? 0.6 : 1,
                      }}
                    >
                      {excluindo === item.id ? "Descartando..." : "Descartar"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {pendentes_items.length === 0 && (
          <Vazio>
            <CheckCircle size={48} style={{ opacity: 0.5 }} />
            <p>Todos os lançamentos foram sincronizados com sucesso! ✨</p>
          </Vazio>
        )}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </>
  );
}
