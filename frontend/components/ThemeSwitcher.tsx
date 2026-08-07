"use client";
import { useEffect, useState } from "react";
import { Sun, Moon, Columns2 } from "lucide-react";
import { salvarPreferenciaPaleta } from "@/lib/api";
import { corTopo } from "@/lib/themeColorTopo";

type Tema = "claro" | "misto" | "escuro";
const CICLO: Tema[] = ["claro", "misto", "escuro"];
const PROXIMO: Record<Tema, Tema> = { claro: "misto", misto: "escuro", escuro: "claro" };
const META: Record<Tema, { label: string; icon: typeof Sun }> = {
  claro: { label: "Tema claro", icon: Sun },
  misto: { label: "Tema misto", icon: Columns2 },
  escuro: { label: "Tema escuro", icon: Moon },
};

// Cor da faixa do topo do navegador/app instalado (<meta name="theme-color">)
// — precisa acompanhar tema E paleta juntos, senão fica vinho mesmo com a
// paleta verde/azul escolhida. Mesma tabela usada no script anti-flash do layout.
function sincronizarCorTopo() {
  const escuro = document.documentElement.getAttribute("data-theme") === "escuro";
  const p = document.documentElement.getAttribute("data-paleta");
  const paleta = p === "verde" || p === "vinho" ? p : "azul";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", corTopo(escuro, paleta));
}

export function aplicarTema(t: Tema) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("tema", t); } catch { /* ignore */ }
  sincronizarCorTopo();
}

export type Paleta = "vinho" | "verde" | "azul";

export function aplicarPaleta(p: Paleta) {
  document.documentElement.setAttribute("data-paleta", p);
  try { localStorage.setItem("paleta", p); } catch { /* ignore */ }
  sincronizarCorTopo();
  salvarPreferenciaPaleta(p).catch(() => { /* offline/erro: fica só local, sincroniza no próximo login */ });
}

export function ThemeSwitcher() {
  const [tema, setTema] = useState<Tema>("claro");

  // Sincroniza com o que o script anti-flash já aplicou no <html>.
  useEffect(() => {
    const atual = (document.documentElement.getAttribute("data-theme") as Tema) || "claro";
    setTema(CICLO.includes(atual) ? atual : "claro");
  }, []);

  function ciclar() {
    const prox = PROXIMO[tema];
    setTema(prox);
    aplicarTema(prox);
  }

  const { label, icon: Icon } = META[tema];
  const proxLabel = META[PROXIMO[tema]].label;
  return (
    <button
      onClick={ciclar}
      title={`${label} — clique para ${proxLabel.toLowerCase()}`}
      aria-label={`Alternar tema (atual: ${label})`}
      className="btn-ghost"
      style={{
        display: "inline-flex", alignItems: "center", gap: "0.4rem", padding: "0.4rem 0.7rem", fontSize: "0.78rem",
        // Fica sobreposto ao conteúdo da página ao rolar — precisa de fundo
        // opaco (não o transparente padrão do .btn-ghost) para não misturar
        // com o texto por trás.
        background: "var(--surface-2)",
      }}
    >
      <Icon size={15} />
      <span className="hidden sm:inline">{label.replace("Tema ", "")}</span>
    </button>
  );
}
