"use client";
// Faixa "Instalar aplicativo" do app de campo. O aviso automático do navegador
// nem sempre aparece, então damos um caminho explícito:
//  • Android/Chrome: captura o evento beforeinstallprompt e instala com 1 toque.
//  • iPhone/Safari: mostra o passo a passo (Compartilhar → Adicionar à Tela).
// Some quando já está instalado (standalone) ou quando o usuário dispensa.
import { useEffect, useState } from "react";
import { Download, X, Share } from "lucide-react";

type PromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

const CHAVE_DISPENSADO = "mob_instalar_dispensado";

export function InstalarApp() {
  const [evento, setEvento] = useState<PromptEvent | null>(null);
  const [ehIos, setEhIos] = useState(false);
  const [visivel, setVisivel] = useState(false);

  useEffect(() => {
    // Já instalado (aberto em tela cheia) → nunca mostra.
    const standalone = window.matchMedia("(display-mode: standalone)").matches
      || (window.navigator as unknown as { standalone?: boolean }).standalone === true;
    if (standalone) return;
    if (localStorage.getItem(CHAVE_DISPENSADO) === "1") return;

    const ua = window.navigator.userAgent || "";
    const ios = /iphone|ipad|ipod/i.test(ua);
    setEhIos(ios);
    if (ios) { setVisivel(true); return; } // Safari não dispara beforeinstallprompt

    const aoPrompt = (e: Event) => {
      e.preventDefault();
      setEvento(e as PromptEvent);
      setVisivel(true);
    };
    window.addEventListener("beforeinstallprompt", aoPrompt);
    // Se instalar por fora, esconde.
    const aoInstalar = () => setVisivel(false);
    window.addEventListener("appinstalled", aoInstalar);
    return () => {
      window.removeEventListener("beforeinstallprompt", aoPrompt);
      window.removeEventListener("appinstalled", aoInstalar);
    };
  }, []);

  function dispensar() {
    setVisivel(false);
    try { localStorage.setItem(CHAVE_DISPENSADO, "1"); } catch { /* ignore */ }
  }

  async function instalar() {
    if (!evento) return;
    await evento.prompt();
    try { await evento.userChoice; } catch { /* ignore */ }
    setEvento(null);
    setVisivel(false);
  }

  if (!visivel) return null;

  return (
    <div style={{
      margin: "0 0 0.9rem", padding: "0.8rem 0.9rem", borderRadius: 14,
      background: "var(--mob-surface)", border: "1px solid var(--mob-acao)",
      boxShadow: "var(--mob-sombra)", position: "relative",
    }}>
      <button type="button" onClick={dispensar} aria-label="Dispensar"
        style={{ position: "absolute", top: 8, right: 8, background: "none", border: "none", color: "var(--mob-muted)", cursor: "pointer" }}>
        <X size={16} />
      </button>
      {ehIos ? (
        <div style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", paddingRight: "1.2rem" }}>
          <Share size={20} style={{ color: "var(--mob-acao)", flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: "0.85rem", color: "var(--mob-text)" }}>
            <strong>Instalar na tela inicial:</strong> toque em <strong>Compartilhar</strong> (o quadrado
            com a seta ↑, na barra de baixo do Safari) e depois em <strong>“Adicionar à Tela de Início”</strong>.
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", gap: "0.7rem", alignItems: "center", paddingRight: "1.2rem" }}>
          <div style={{ fontSize: "0.85rem", color: "var(--mob-text)", flex: 1 }}>
            <strong>Instale o app da Fazenda</strong> no celular — abre como aplicativo e funciona no campo.
          </div>
          <button type="button" onClick={instalar} className="mob-btn"
            style={{ width: "auto", padding: "0.6rem 0.9rem", flexShrink: 0 }}>
            <Download size={17} /> Instalar
          </button>
        </div>
      )}
    </div>
  );
}
