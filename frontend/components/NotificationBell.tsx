"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, X } from "lucide-react";
import { fetchNotificacoes } from "@/lib/api";

type Item = { tipo: string; categoria: string; descricao: string; numero_animal: string | null; cor: string };

// Decide para qual página levar o usuário para resolver a pendência,
// a partir da categoria/tipo da notificação.
function destino(i: Item): string {
  const chave = `${i.categoria || ""} ${i.tipo || ""}`.toLowerCase();
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

  const carregar = () => fetchNotificacoes().then((d) => { setItens(d.itens || []); setErro(false); }).catch(() => setErro(true));

  useEffect(() => {
    carregar();
    const h = setInterval(carregar, 5 * 60 * 1000);
    return () => clearInterval(h);
  }, []);

  const total = itens.length;

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
            {erro ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Não foi possível carregar as notificações agora.</p>
            ) : !total ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Nada pendente para hoje.</p>
            ) : (
              <div className="space-y-2">
                {itens.map((i, idx) => (
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
