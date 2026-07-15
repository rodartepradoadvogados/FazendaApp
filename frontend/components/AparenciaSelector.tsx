"use client";
import { useEffect, useState } from "react";
import { Sun, Moon, Columns2, Wine, Leaf } from "lucide-react";
import { TabBar } from "@/components/ui";
import { aplicarTema, aplicarPaleta, type Paleta } from "@/components/ThemeSwitcher";

type Tema = "claro" | "misto" | "escuro";

const TEMAS_SITE = [
  { id: "claro" as Tema, label: "Claro", icon: Sun },
  { id: "misto" as Tema, label: "Misto", icon: Columns2, title: "Tema misto (barra vinho)" },
  { id: "escuro" as Tema, label: "Escuro", icon: Moon },
];
const TEMAS_APP = [
  { id: "claro" as Tema, label: "Claro", icon: Sun },
  { id: "escuro" as Tema, label: "Escuro", icon: Moon },
];
const PALETAS = [
  { id: "vinho" as Paleta, label: "Vinho", icon: Wine, title: "Paleta Vinho (padrão)" },
  { id: "verde" as Paleta, label: "Verde", icon: Leaf, title: "Paleta Verde" },
];

/**
 * Seletor de Aparência — usado em Configurações (site, variant="site") e no
 * Menu do app (variant="app", sem opção "Misto"). Tema e paleta são
 * independentes: trocar uma não mexe na outra.
 */
export function AparenciaSelector({ variant = "site" }: { variant?: "site" | "app" }) {
  const [tema, setTema] = useState<Tema>("misto");
  const [paleta, setPaleta] = useState<Paleta>("vinho");

  useEffect(() => {
    const el = document.documentElement;
    const t = (el.getAttribute("data-theme") as Tema) || "misto";
    const p = (el.getAttribute("data-paleta") as Paleta) || "vinho";
    setTema(variant === "app" && t === "misto" ? "claro" : t);
    setPaleta(p === "verde" ? "verde" : "vinho");
  }, [variant]);

  function mudarTema(t: Tema) {
    setTema(t);
    aplicarTema(t);
  }
  function mudarPaleta(p: Paleta) {
    setPaleta(p);
    aplicarPaleta(p);
  }

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-start sm:gap-8">
      <div>
        <p style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "0.4rem" }}>Tema</p>
        <TabBar abas={variant === "app" ? TEMAS_APP : TEMAS_SITE} ativa={tema} onChange={mudarTema} />
      </div>
      <div>
        <p style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "0.4rem" }}>Paleta</p>
        <TabBar abas={PALETAS} ativa={paleta} onChange={mudarPaleta} />
      </div>
    </div>
  );
}
