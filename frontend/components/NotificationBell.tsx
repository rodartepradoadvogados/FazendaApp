"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, BellRing, X } from "lucide-react";
import { fetchNotificacoes, fetchAprovacoesContagem, ehAdmin, fetchPushChavePublica, subscribePush, unsubscribePush } from "@/lib/api";

type Item = { tipo: string; categoria: string; descricao: string; numero_animal: string | null; cor: string };

// base64url (formato da chave VAPID) -> Uint8Array, exigido pela Push API.
function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const base64Padded = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64Padded);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

type StatusPush = "indisponivel" | "podeAtivar" | "ativado" | "negado";

// Decide para qual página levar o usuário para resolver a pendência,
// a partir da categoria/tipo da notificação.
function destino(i: Item): string {
  const chave = `${i.categoria || ""} ${i.tipo || ""}`.toLowerCase();
  if (chave.includes("aprova")) return "/aprovacoes";
  if (chave.includes("portal")) return "/portal";
  if (chave.includes("financ")) return "/financeiro";
  if (chave.includes("estoque")) return "/estoque";
  // reprodutivo, sanidade e o restante são resolvidos na Agenda.
  return "/agenda";
}

export function NotificationBell() {
  const router = useRouter();
  const [itens, setItens] = useState<Item[]>([]);
  const [aberto, setAberto] = useState(false);
  const [erro, setErro] = useState(false);

  const [aprov, setAprov] = useState(0);
  const [statusPush, setStatusPush] = useState<StatusPush>("indisponivel");
  const [ativandoPush, setAtivandoPush] = useState(false);

  const carregar = () => {
    fetchNotificacoes().then((d) => { setItens(d.itens || []); setErro(false); }).catch(() => setErro(true));
    if (ehAdmin()) fetchAprovacoesContagem().then((d) => setAprov(d.pendentes || 0)).catch(() => {});
  };

  useEffect(() => {
    carregar();
    const h = setInterval(carregar, 5 * 60 * 1000);
    return () => clearInterval(h);
  }, []);

  // Push só é oferecido onde já existe um service worker ativo (hoje, o
  // PWA em /app — ver frontend/public/sw.js). Fora dali, o botão nem aparece.
  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    if (Notification.permission === "denied") { setStatusPush("negado"); return; }
    navigator.serviceWorker.getRegistration().then((reg) => {
      if (!reg) return; // sem SW registrado nesta página — não oferece push aqui
      reg.pushManager.getSubscription().then((sub) => setStatusPush(sub ? "ativado" : "podeAtivar"));
    }).catch(() => {});
  }, []);

  const ativarPush = async () => {
    setAtivandoPush(true);
    try {
      const permissao = await Notification.requestPermission();
      if (permissao !== "granted") { setStatusPush(permissao === "denied" ? "negado" : "podeAtivar"); return; }
      const reg = await navigator.serviceWorker.ready;
      const { chave_publica } = await fetchPushChavePublica();
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(chave_publica) as BufferSource,
      });
      const json = sub.toJSON();
      await subscribePush({ endpoint: json.endpoint!, keys: { p256dh: json.keys!.p256dh, auth: json.keys!.auth }, user_agent: navigator.userAgent });
      setStatusPush("ativado");
    } catch { /* mantém o botão para tentar de novo — falha silenciosa não trava o sino */ }
    finally { setAtivandoPush(false); }
  };

  const desativarPush = async () => {
    setAtivandoPush(true);
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) { await unsubscribePush(sub.endpoint); await sub.unsubscribe(); }
      setStatusPush("podeAtivar");
    } catch { /* idem */ }
    finally { setAtivandoPush(false); }
  };

  // Pendências de aprovação (Telegram) entram como um item no topo, para o admin.
  const itensExibidos: Item[] = aprov > 0
    ? [{ tipo: "aprovacao", categoria: "Aprovações", descricao: `${aprov} lançamento(s) do Telegram aguardando aprovação`, numero_animal: null, cor: "var(--amber)" }, ...itens]
    : itens;
  const total = itensExibidos.length;

  const irPara = (i: Item) => {
    setAberto(false);
    router.push(destino(i));
  };

  return (
    <>
      <button
        onClick={() => setAberto((a) => !a)}
        aria-label="Notificações de hoje"
        style={{
          position: "fixed", top: "1rem", right: "1.25rem", zIndex: 60,
          width: "2.5rem", height: "2.5rem", borderRadius: "999px",
          background: "var(--surface-2)", border: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer",
        }}
      >
        <Bell size={19} style={{ color: "#b8860b" }} />
        {/* Quando há erro de carregamento, mantemos o sino visível com um "!" âmbar discreto. */}
        {erro ? (
          <span style={{
            position: "absolute", top: "-4px", right: "-4px", minWidth: "1.1rem", height: "1.1rem",
            borderRadius: "999px", background: "var(--amber)", color: "#fff", fontSize: "0.7rem", fontWeight: 700,
            display: "flex", alignItems: "center", justifyContent: "center", padding: "0 0.25rem",
          }}>
            !
          </span>
        ) : total > 0 && (
          <span style={{
            position: "absolute", top: "-4px", right: "-4px", minWidth: "1.1rem", height: "1.1rem",
            borderRadius: "999px", background: "var(--red)", color: "#fff", fontSize: "0.65rem", fontWeight: 700,
            display: "flex", alignItems: "center", justifyContent: "center", padding: "0 0.25rem",
          }}>
            {total > 99 ? "99+" : total}
          </span>
        )}
      </button>

      {aberto && (
        <div onClick={() => setAberto(false)} style={{ position: "fixed", inset: 0, zIndex: 59 }}>
          <div onClick={(e) => e.stopPropagation()} className="card" style={{
            position: "fixed", top: "4rem", right: "1.25rem", width: "360px", maxWidth: "92vw",
            maxHeight: "70vh", overflowY: "auto", zIndex: 61, padding: "0.75rem",
          }}>
            <div className="flex items-center justify-between mb-2">
              <div className="card-header" style={{ margin: 0 }}>Hoje</div>
              <button className="btn-ghost" onClick={() => setAberto(false)} aria-label="Fechar"><X size={15} /></button>
            </div>
            {(statusPush === "podeAtivar" || statusPush === "ativado") && (
              <button
                className="btn-ghost"
                onClick={statusPush === "ativado" ? desativarPush : ativarPush}
                disabled={ativandoPush}
                style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", marginBottom: "0.6rem", width: "100%", justifyContent: "flex-start" }}
              >
                <BellRing size={13} />
                {ativandoPush ? "Aguarde…" : statusPush === "ativado" ? "Notificações push ativadas (clique para desativar)" : "Ativar notificações push neste dispositivo"}
              </button>
            )}
            {statusPush === "negado" && (
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                Notificações push bloqueadas — habilite nas permissões do navegador para este site.
              </p>
            )}
            {erro ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Não foi possível carregar as notificações agora.</p>
            ) : !total ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Nada pendente para hoje.</p>
            ) : (
              <div className="space-y-2">
                {itensExibidos.map((i, idx) => (
                  <div key={idx} onClick={() => irPara(i)} title="Ir para a página relacionada"
                    style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", padding: "0.45rem 0.5rem", borderRadius: "6px", background: "var(--surface-2)", cursor: "pointer", boxShadow: "inset 0 0 0 1px transparent", transition: "box-shadow 0.15s" }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.boxShadow = "inset 3px 0 0 var(--dourado)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.boxShadow = "inset 0 0 0 1px transparent"; }}
                  >
                    <span style={{ width: "8px", height: "8px", borderRadius: "999px", background: i.cor || "var(--dourado)", marginTop: "0.35rem", flexShrink: 0 }} />
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{i.categoria}</div>
                      <div style={{ fontSize: "0.82rem" }}>{i.descricao}{i.numero_animal ? ` (nº ${i.numero_animal})` : ""}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
