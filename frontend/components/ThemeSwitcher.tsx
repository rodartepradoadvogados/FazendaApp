"use client";
import { useEffect, useState } from "react";
import { Sun, Moon, Columns2 } from "lucide-react";
import { salvarPreferenciaPaleta } from "@/lib/api";

type Tema = "claro" | "misto" | "escuro";
const CICLO: Tema[] = ["claro", "misto", "escuro"];
const PROXIMO: Record<Tema, Tema> = { claro: "misto", misto: "escuro", escuro: "claro" };
const META: Record<Tema, { label: string; icon: typeof Sun }> = {
  claro: { label: "Tema claro", icon: Sun },
  misto: { label: "Tema misto (barra vinho)", icon: Columns2 },
  escuro: { label: "Tema escuro", icon: Moon },
};

// Cor da faixa do topo do navegador/app instalado (<meta name="theme-color">)
// — precisa acompanhar tema E paleta juntos, senão fica vinho mesmo com a
// paleta verde escolhida. Mesma tabela usada no script anti-flash do layout.
function sincronizarCorTopo() {
  const escuro = document.documentElement.getAttribute("data-theme") === "escuro";
  const verde = document.documentElement.getAttribute("data-paleta") === "verde";
  const cor = verde ? (escuro ? "#16402B" : "#1F5C3D") : (escuro ? "#340F1C" : "#4A1525");
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", cor);
}

export function aplicarTema(t: Tema) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("tema", t); } catch { /* ignore */ }
  sincronizarCorTopo();
}

export type Paleta = "vinho" | "verde";

export function aplicarPaleta(p: Paleta) {
  document.documentElement.setAttribute("data-paleta", p);
  try { localStorage.setItem("paleta", p); } catch { /* ignore */ }
  sincronizarCorTopo();
  salvarPreferenciaPaleta(p).catch(() => { /* offline/erro: fica só local, sincroniza no próximo login */ });
}

export function ThemeSwitcher() {
  const [tema, setTema] = useState<Tema>("misto");

  // Sincroniza com o que o script anti-flash já aplicou no <html>.
  useEffect(() => {
    const atual = (document.documentElement.getAttribute("data-theme") as Tema) || "misto";
    setTema(CICLO.includes(atual) ? atual : "misto");
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
      style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", padding: "0.4rem 0.7rem", fontSize: "0.78rem" }}
    >
      <Icon size={15} />
      <span className="hidden sm:inline">{label.replace("Tema ", "")}</span>
    </button>
  );
}
