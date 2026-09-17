"use client";
// Botão "Instalar" do site completo (desktop) — mesma ideia do
// components/mobile/InstalarApp.tsx (o aviso automático do navegador nem
// sempre aparece, então damos um caminho explícito), mas para quem acessa
// o site completo num computador, não o /app de campo no celular. Some
// sozinho quando já está instalado (display-mode: standalone) ou quando o
// navegador nunca dispara beforeinstallprompt (Safari) — sem instrução
// manual aqui, ao contrário do InstalarApp, porque este cabe só em
// Chrome/Edge desktop.
import { useEffect, useState } from "react";
import { Download } from "lucide-react";

type PromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

export function InstalarSite() {
  const [evento, setEvento] = useState<PromptEvent | null>(null);

  useEffect(() => {
    const standalone = window.matchMedia("(display-mode: standalone)").matches
      || (window.navigator as unknown as { standalone?: boolean }).standalone === true;
    if (standalone) return;

    const aoPrompt = (e: Event) => { e.preventDefault(); setEvento(e as PromptEvent); };
    const aoInstalar = () => setEvento(null);
    window.addEventListener("beforeinstallprompt", aoPrompt);
    window.addEventListener("appinstalled", aoInstalar);
    return () => {
      window.removeEventListener("beforeinstallprompt", aoPrompt);
      window.removeEventListener("appinstalled", aoInstalar);
    };
  }, []);

  if (!evento) return null;

  async function instalar() {
    if (!evento) return;
    await evento.prompt();
    try { await evento.userChoice; } catch { /* ignore */ }
    setEvento(null);
  }

  return (
    <button
      type="button"
      onClick={instalar}
      title="Instalar o site como aplicativo neste computador"
      aria-label="Instalar o site como aplicativo neste computador"
      className="btn-ghost"
      style={{
        display: "inline-flex", alignItems: "center", gap: "0.35rem",
        padding: "0.4rem 0.7rem", fontSize: "0.78rem", whiteSpace: "nowrap",
      }}
    >
      <Download size={15} /> Instalar
    </button>
  );
}
