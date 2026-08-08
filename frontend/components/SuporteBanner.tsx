"use client";
// Faixa fixa no topo do conteúdo, visível em toda a fazenda, enquanto a
// sessão foi aberta a partir do Painel CowData como suporte (ver
// lib/api.ts::entrarComoSuporte e backend/main.py::_bloquear_modo_suporte).
// Nunca aparece pra quem entrou direto na fazenda como administrador.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { getModoSuporte, encerrarModoSuporte, type ModoSuporte } from "@/lib/api";

export function SuporteBanner() {
  const router = useRouter();
  const [modo, setModo] = useState<ModoSuporte | null>(null);
  const [agora, setAgora] = useState<number>(0);
  const [encerrando, setEncerrando] = useState(false);

  useEffect(() => {
    setModo(getModoSuporte());
    setAgora(Date.now());
    const t = setInterval(() => setAgora(Date.now()), 15_000);
    return () => clearInterval(t);
  }, []);

  if (!modo) return null;

  const restanteMin = Math.max(0, Math.round((new Date(modo.expiraEm).getTime() - agora) / 60000));
  const horaExpira = new Date(modo.expiraEm).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

  async function encerrar() {
    setEncerrando(true);
    await encerrarModoSuporte();
    router.replace("/painel-cowdata");
  }

  return (
    <div style={{
      position: "sticky", top: 0, zIndex: 25, display: "flex", alignItems: "center", justifyContent: "space-between",
      gap: "0.8rem", flexWrap: "wrap", padding: "0.55rem 1rem", background: "var(--amber)", color: "#1A1200",
    }}>
      <span style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", fontWeight: 700 }}>
        <ShieldAlert size={16} />
        Modo suporte CowData — {modo.fazendaNome}
        {restanteMin > 0 ? ` — expira às ${horaExpira} (${restanteMin} min)` : " — expirando"}
      </span>
      <button type="button" onClick={encerrar} disabled={encerrando}
        style={{
          fontSize: "0.78rem", fontWeight: 700, padding: "0.3rem 0.7rem", borderRadius: "var(--r-sm)",
          border: "1px solid #1A1200", background: "transparent", color: "#1A1200", cursor: "pointer",
        }}>
        {encerrando ? "Encerrando…" : "Encerrar sessão de suporte"}
      </button>
    </div>
  );
}
