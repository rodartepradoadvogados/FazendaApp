"use client";
// Faixa fixa que só aparece quando uma chamada de rede é rejeitada (queda de
// conexão) — authFetch dispara window "cowdata:offline" no .catch (ver
// lib/api.ts). Nunca desloga o usuário: uma falha de rede é estado recuperável,
// não "sessão perdida". O botão "Tentar novamente" reaproveita checkHealth()
// (já exportado em lib/api.ts) e some a faixa se a API voltou.
//
// Tom âmbar (--amber) de propósito: distingue-se da faixa vermelha de suporte
// (SuporteBanner.tsx). Fica ABAIXO dela (zIndex 99 < 100) e desce empilhando
// --faixas-topo-h, o token que soma todas as tarjas fixas (ver globals.css).
import { useEffect, useRef, useState } from "react";
import { WifiOff } from "lucide-react";
import { checkHealth } from "@/lib/api";

export function OfflineBanner() {
  const [offline, setOffline] = useState(false);
  const [tentando, setTentando] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function aoCair() {
      setOffline(true);
    }
    function aoVoltar() {
      setOffline(false);
    }
    window.addEventListener("cowdata:offline", aoCair);
    window.addEventListener("online", aoVoltar);
    return () => {
      window.removeEventListener("cowdata:offline", aoCair);
      window.removeEventListener("online", aoVoltar);
    };
  }, []);

  // Publica a altura real em --offline-banner-h (0px quando oculto) para que
  // --faixas-topo-h (globals.css) continue somando as tarjas fixas certo.
  useEffect(() => {
    if (!offline) {
      document.documentElement.style.setProperty("--offline-banner-h", "0px");
      return;
    }
    const el = ref.current;
    if (!el) return;
    const publicar = () => document.documentElement.style.setProperty("--offline-banner-h", `${el.offsetHeight}px`);
    publicar();
    const ro = new ResizeObserver(publicar);
    ro.observe(el);
    return () => {
      ro.disconnect();
      document.documentElement.style.setProperty("--offline-banner-h", "0px");
    };
  }, [offline]);

  async function tentar() {
    setTentando(true);
    const ok = await checkHealth();
    setTentando(false);
    if (ok) setOffline(false);
  }

  if (!offline) return null;

  return (
    <div ref={ref} role="status" style={{
      position: "fixed", top: "var(--faixas-topo-h, 0px)", left: 0, right: 0, zIndex: 99,
      background: "var(--amber)", color: "#FFF9EC", padding: "0.5rem 1rem",
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.8rem",
      flexWrap: "wrap", minHeight: "2.6rem", boxShadow: "0 2px 6px rgba(0,0,0,0.25)",
    }}>
      <span style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", fontWeight: 600 }}>
        <WifiOff size={16} />
        Sem conexão com o servidor. Suas alterações não estão sendo enviadas.
      </span>
      <button type="button" onClick={tentar} disabled={tentando}
        style={{
          fontSize: "0.78rem", fontWeight: 700, padding: "0.35rem 0.75rem", borderRadius: "var(--r-sm)",
          border: "1px solid #FFF9EC", background: "transparent", color: "#FFF9EC", cursor: "pointer", whiteSpace: "nowrap",
        }}>
        {tentando ? "Verificando…" : "Tentar novamente"}
      </button>
    </div>
  );
}
